"""Orchestrateur de run (couche 6) — **coquille mince qui ne calcule pas**.

Câble les couches internes : construit les modules (registre), fait tourner
l'exécuteur (couche 4) par document, passe les artefacts au runner d'évaluation
(couche 3), assemble le ``RunResult`` + le ``RunManifest``. Il **n'évalue rien
lui-même** (l'assemblage métrique vit en ``evaluation``) et **n'exécute aucun
moteur** (les modules le font).

Exécution **parallèle** des unités ``(pipeline × document)`` sur un pool de
threads borné (gros corpus) : chaque unité est indépendante (sous-dossier
workspace par pipeline + fichiers nommés par ``document_id`` → aucune collision).
Le **déterminisme** est garanti par construction : l'exécution est concurrente,
mais l'assemblage du ``RunResult`` se fait **dans l'ordre du spec**, pas dans
l'ordre d'achèvement → sortie byte-identique au séquentiel (``max_workers=1``).
"""

from __future__ import annotations

import logging
import os
import re
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from cinoc.adapters.corpus._http import CorpusHttpError, download
from cinoc.adapters.layout.crop import crop_region
from cinoc.app.modules.registry import ModuleRegistry
from cinoc.app.portable_paths import portable_result, relativize_message
from cinoc.app.resume import ResumeStore, declared_inputs, unit_key
from cinoc.app.run_manifest import (
    SECRET_PLACEHOLDER,
    build_manifest,
    module_identities,
    secret_values,
    served_models,
)
from cinoc.app.security import safe_stem
from cinoc.domain.artifacts import Artifact, ArtifactType, StepArtifacts
from cinoc.domain.deadline import Deadline
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import CinocError, RunCancelledError
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest, utcnow
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.archaic import resolve_archaic_list
from cinoc.evaluation.metrics.archaic import make_air_metric, make_hcpr_metric
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.result import DocumentUsage, RunResult
from cinoc.evaluation.runner import evaluate_run
from cinoc.evaluation.scoring import unusable_ground_truths
from cinoc.pipeline.executor import (
    UNIT_FAILURES,
    PipelineExecutor,
    failure_reason,
)
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import DocumentExecution

logger = logging.getLogger(__name__)


class OrchestrationError(CinocError):
    """Run impossible à exécuter (document sans image, etc.)."""


class ArchiveIncompleteError(OrchestrationError):
    """Relecture hors ligne (``offline``) : une unité nécessaire manque à l'archive.

    Hors ligne, rien ne s'exécute : une unité absente — jamais produite, ou
    produite sous une autre empreinte (module relevé, binaire changé, réglage
    différent) — fait échouer le run au lieu d'être exécutée en silence.
    """


#: Sorties d'un run, indexées ``pipeline → document → étape → type → artefact``
#: (``by_step`` de chaque unité ; le pool d'une unité se lit par
#: ``latest_by_type``). Une unité en échec n'a aucune étape.
PipelineOutputs = Mapping[str, Mapping[str, StepArtifacts]]
#: Sink optionnel d'artefacts : reçoit les sorties **avant** le nettoyage du
#: workspace (les URI sont encore lisibles). La couche 6 (app) le fournit ;
#: l'orchestrateur l'invoque sans rien connaître de sa cible (un store, etc.).
ArtifactSink = Callable[[PipelineOutputs, RunManifest], None]
@dataclass(frozen=True)
class UnitProgress:
    """Une unité (concurrent × document) **terminée** : où en est le run, et ce
    qu'elle a donné. Le web en tire sa barre (SSE), la CLI une ligne (D-307)."""

    done: int
    total: int
    pipeline: str
    document_id: str
    #: ``ok`` / ``truncated`` / ``partial`` / ``failed`` (issue de l'unité), ou
    #: ``resumed`` : relue de l'archive, pas exécutée.
    outcome: str


#: Callback de progression, émis après chaque unité (succès **ou** échec isolé).
ProgressCallback = Callable[[UnitProgress], None]


#: Variable d'environnement (ops) : nombre de threads d'exécution par défaut.
_WORKERS_ENV = "CINOC_MAX_WORKERS"


def _resolve_workers(max_workers: int | None, n_pending: int) -> int:
    """Nombre de threads effectif : argument > ``CINOC_MAX_WORKERS`` > CPU.

    Borné à ``[1, n_pending]`` — inutile de dépasser le nombre d'unités à exécuter.
    Une valeur invalide d'environnement est ignorée (dégradé sur le défaut CPU).
    """
    chosen = max_workers
    if chosen is None:
        raw = os.environ.get(_WORKERS_ENV)
        if raw is not None:
            try:
                chosen = int(raw)
            except ValueError:
                logger.warning(
                    "[orchestrator] %s=%r ignoré (entier attendu).", _WORKERS_ENV, raw
                )
    if chosen is None or chosen < 1:
        chosen = os.cpu_count() or 1
    return max(1, min(chosen, n_pending))


class _ProgressCounter:
    """Compteur d'unités traitées, thread-safe (pool d'exécution concurrent)."""

    def __init__(self, total: int, callback: ProgressCallback | None) -> None:
        self._total = total
        self._callback = callback
        self._done = 0
        self._lock = threading.Lock()

    def tick(self, pipeline: str, document_id: str, outcome: str) -> None:
        if self._callback is None:
            return
        with self._lock:
            self._done += 1
            done = self._done
        self._callback(
            UnitProgress(done, self._total, pipeline, document_id, outcome)
        )


def run(
    spec: RunSpec,
    *,
    registry: ModuleRegistry,
    code_version: str,
    deadline: Deadline | None = None,
    control: RunControl | None = None,
    artifact_sink: ArtifactSink | None = None,
    on_progress: ProgressCallback | None = None,
    resume_store: ResumeStore | None = None,
    max_workers: int | None = None,
    offline: bool = False,
    paths_root: Path | None = None,
) -> RunResult:
    """Exécute ``spec`` et renvoie le ``RunResult`` (manifeste + métriques).

    ``control`` (optionnel) porte l'**annulation coopérative** de bout en bout :
    le worker d'un job (``JobRunner``, couche 6) le déclenche, l'exécuteur le
    sonde avant chaque étape. Absent → un ``RunControl`` neutre est utilisé.

    ``artifact_sink`` (optionnel) reçoit les artefacts produits **avant** le
    nettoyage du workspace (URI encore lisibles) : c'est par lui qu'un LAYOUT
    produit est persisté (ex. ``SegmentationStore``) sans que l'orchestrateur
    connaisse la destination, et sans second chemin d'exécution.

    ``resume_store`` (optionnel) : cache d'**exécution** adressé par empreinte
    (``app.resume``) — une unité (pipeline × document) déjà produite à
    l'identique est rechargée au lieu d'être ré-exécutée ; l'évaluation, elle,
    est toujours recalculée. Accédé **uniquement en thread principal** (chargement
    avant le pool, persistance après) → aucune contrainte de concurrence sur lui.

    ``max_workers`` (optionnel) : taille du pool de threads d'exécution. ``None``
    → ``CINOC_MAX_WORKERS`` puis ``os.cpu_count()``. ``1`` = séquentiel strict
    (référence de déterminisme). Les unités sont indépendantes ; l'assemblage
    final est **ordonné par le spec**, donc le résultat ne dépend pas du nombre de
    threads.

    ``offline`` (exige ``resume_store``) : **relecture** de l'archive, sans aucun
    appel de moteur. Chaque unité est lue dans l'archive — échecs archivés
    compris, restitués comme échecs — et une unité absente lève
    :class:`ArchiveIncompleteError` au lieu d'être exécutée. Les binaires de
    l'identité sont ceux de l'archive (rien ne tourne, rien n'est sondé).
    L'évaluation, elle, est recalculée comme toujours : c'est tout l'objet.

    ``paths_root`` : racine des chemins locaux de la spec (dossier du fichier de
    run). Le ``RunResult`` n'en porte alors aucun absolu — images, archive et
    messages d'échec y sont relatifs (``app.portable_paths``). Absente, les
    chemins passent tels que la spec les donne.
    """
    if offline and resume_store is None:
        raise OrchestrationError(
            "relecture hors ligne : une archive est requise (--resume-dir)."
        )
    started_at = utcnow()
    root = paths_root.resolve() if paths_root is not None else None
    needed = sorted(
        {step.adapter_name for pipeline in spec.pipelines for step in pipeline.steps}
    )
    modules = {
        name: registry.build(name, spec.adapter_kwargs.get(name, {}))
        for name in needed
    }
    # Une seule identité par module, lue une fois : l'empreinte des étapes, la
    # clé de reprise et le manifeste en dérivent tous trois.
    identities = module_identities(
        spec,
        modules,
        recorded_binaries=(
            resume_store.recorded_binaries()
            if offline and resume_store is not None
            else None
        ),
    )
    executor = PipelineExecutor(code_version, identities)
    metric_registry = MetricRegistry()
    register_default_metrics(metric_registry)
    _bind_archaic_metrics(metric_registry, spec)
    # F8, D9 : une vérité terrain référencée mais absente du disque, ou qui ne
    # se décode pas, est refusée **avant** le premier appel de moteur — jamais
    # payée pour rien.
    unusable = unusable_ground_truths(spec.corpus, spec.evaluation, metric_registry)
    if unusable:
        shown = ", ".join(f"{document} → {uri}" for document, uri in unusable[:5])
        more = f" (+{len(unusable) - 5})" if len(unusable) > 5 else ""
        raise OrchestrationError(
            f"{len(unusable)} vérité(s) terrain référencée(s) mais absente(s) du "
            f"disque ou illisible(s) : {shown}{more}. Rien n'a été exécuté."
        )

    documents = spec.corpus.documents
    total_units = len(spec.pipelines) * len(documents)
    progress = _ProgressCounter(total_units, on_progress)
    with TemporaryDirectory(prefix="cinoc-run-") as workspace:
        # Un sous-dossier de workspace **par pipeline** : deux pipelines qui
        # partagent un `adapter_name` écriraient sinon le même fichier de sortie.
        # Au sein d'un pipeline, chaque document écrit un fichier nommé par son id
        # (`workspace_artifact_path`, stem injectif) → deux documents concurrents
        # ne se marchent jamais dessus, l'exécution parallèle est sûre.
        workspaces: dict[str, Path] = {}
        for index, pipeline in enumerate(spec.pipelines):
            pipeline_workspace = Path(workspace) / f"pipeline{index}"
            pipeline_workspace.mkdir()
            workspaces[pipeline.name] = pipeline_workspace

        # 0) Images **référence** (corpus curé) : matérialisées en local une fois
        #    par document — les moteurs lisent un fichier, jamais une URL ; la
        #    spec d'origine (→ RunResult/rapport) garde la référence épinglée.
        documents, unreachable = _materialize_remote_images(
            documents, Path(workspace) / "images"
        )

        # 1) Reprise (thread principal) : les unités déjà produites à l'identique
        #    sont rechargées ; les autres sont mises en file d'exécution. Les
        #    échecs sont archivés mais retentés — sauf hors ligne, où ils sont
        #    restitués et où une unité absente arrête le run.
        # Une ``DocumentExecution`` par unité, **échecs compris** : l'issue est
        # conservée, jamais remplacée par un dict vide qui se lirait « absent ».
        results: dict[tuple[str, str], DocumentExecution] = {}
        secrets = secret_values(spec.adapter_kwargs, modules)
        digests: dict[Path, str] = {}  # fichiers d'entrée, hachés une fois
        pending: list[tuple[PipelineSpec, DocumentRef, str | None]] = []
        # Unités relues de l'archive : leur durée est celle de leur première
        # exécution, et le ``RunResult`` le dit (D10, pilote D-281).
        resumed: set[tuple[str, str]] = set()
        for pipeline in spec.pipelines:
            for document in documents:
                if document.id in unreachable:
                    # Image distante injoignable : unité échouée (comme un échec
                    # d'adapter isolé), le reste du corpus tourne normalement.
                    message = _redact(
                        unreachable[document.id], secrets, workspace, root
                    )
                    results[(pipeline.name, document.id)] = DocumentExecution.failed(
                        "infrastructure", message
                    )
                    progress.tick(pipeline.name, document.id, "failed")
                    continue
                key = (
                    unit_key(
                        pipeline=pipeline,
                        identities=identities,
                        document=document,
                        inputs=declared_inputs(pipeline, modules, document),
                        digests=digests,
                    )
                    if resume_store is not None
                    else None
                )
                cached = (
                    resume_store.load(key, failures=offline)
                    if resume_store and key
                    else None
                )
                if cached is not None:
                    results[(pipeline.name, document.id)] = cached
                    resumed.add((pipeline.name, document.id))
                    progress.tick(pipeline.name, document.id, "resumed")
                else:
                    pending.append((pipeline, document, key))
        if offline and pending:
            _refuse_missing(pending, resume_store)

        # 2) Exécution **parallèle** des unités non-cachées. OCR (sous-processus)
        #    et LLM/cloud (I/O HTTP) libèrent le GIL → les threads donnent un
        #    speedup réel sans sérialiser les artefacts. Un échec isolé d'unité
        #    (`AdapterStepError`/`PipelineStepError`) n'abat pas le banc ; seule
        #    l'annulation (`RunCancelledError`) arrête tout le run.
        saves: list[tuple[str, DocumentExecution]] = []
        if pending:
            workers = _resolve_workers(max_workers, len(pending))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_to_unit = {
                    pool.submit(
                        executor.execute_document,
                        pipeline,
                        modules,
                        _initial_inputs(document),
                        document_id=document.id,
                        deadline=deadline,
                        control=control,
                        workspace_uri=str(workspaces[pipeline.name]),
                        # Découpe réelle des blocs pour les étapes ``fanout`` du
                        # pipeline hybride (seg → OCR par région). Inerte hors
                        # fan-out ; PIL importé paresseusement (seul le crop l'exige).
                        cropper=crop_region,
                    ): (pipeline, document, key)
                    for pipeline, document, key in pending
                }
                try:
                    for future in as_completed(future_to_unit):
                        pipeline, document, key = future_to_unit[future]
                        unit = (pipeline.name, document.id)
                        try:
                            execution = future.result()
                        except UNIT_FAILURES as exc:
                            message = _redact(str(exc), secrets, workspace, root)
                            logger.warning(
                                "[orchestrator] concurrent %r · document %r "
                                "échoué : %s",
                                pipeline.name,
                                document.id,
                                message,
                            )
                            # Ce que l'unité a fait facturer avant d'échouer
                            # reste compté (P5f 7).
                            results[unit] = DocumentExecution.failed(
                                failure_reason(exc),
                                message,
                                billed=getattr(exc, "billed", None),
                            )
                            if key is not None:
                                # Archivé (l'archive dit ce qui a échoué), mais
                                # une reprise normale le retentera.
                                saves.append((key, results[unit]))
                            progress.tick(*unit, "failed")
                            continue
                        if execution.message is not None:
                            # Une coupure se signale par un message (étape,
                            # plafond) : même règle que pour un échec — borné,
                            # sans secret ni chemin de workspace.
                            execution = replace(
                                execution,
                                message=_redact(
                                    execution.message, secrets, workspace, root
                                ),
                            )
                        results[unit] = execution
                        if key is not None:
                            saves.append((key, execution))
                        progress.tick(*unit, execution.outcome)
                except RunCancelledError:
                    # Annulation coopérative : on cesse de planifier (les unités
                    # non démarrées sont annulées) et on propage — le run s'arrête.
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise

        # 3) Reprise : persistance des unités exécutées (thread principal, post-pool),
        #    et des binaires sous lesquels elles l'ont été (relecture hors ligne).
        if resume_store is not None and saves:
            for saved_key, saved in saves:
                resume_store.save(saved_key, saved)
            resume_store.record_binaries(
                {name: identity.binaries for name, identity in identities.items()}
            )

        # 4) Assemblage **déterministe** : ordre du spec, indépendant de l'ordre
        #    d'achèvement des threads → `RunResult` byte-identique au séquentiel.
        pipeline_outputs: dict[str, dict[str, StepArtifacts]] = {}
        usage_records: list[DocumentUsage] = []
        for pipeline in spec.pipelines:
            per_document: dict[str, StepArtifacts] = {}
            for document in documents:
                execution = results[(pipeline.name, document.id)]
                per_document[document.id] = execution.by_step
                usage_records.append(
                    DocumentUsage(
                        document_id=document.id,
                        pipeline=pipeline.name,
                        usage=execution.usage,
                        outcome=execution.outcome,
                        reason=execution.reason,
                        message=execution.message,
                        line_outcomes=execution.line_outcomes,
                        step_issues=dict(execution.step_issues),
                        resumed=(pipeline.name, document.id) in resumed,
                    )
                )
            pipeline_outputs[pipeline.name] = per_document

        completed_at = utcnow()
        manifest = build_manifest(
            spec,
            identities,
            code_version,
            started_at,
            completed_at,
            served=served_models(spec, pipeline_outputs),
            artifacts_dir=(
                str(resume_store.base_dir) if resume_store is not None else None
            ),
        )
        # Sink avant la sortie du ``with`` : les URI des artefacts (LAYOUT…)
        # pointent encore dans le workspace vivant. Best-effort côté appelant.
        if artifact_sink is not None:
            artifact_sink(pipeline_outputs, manifest)
        result = evaluate_run(
            corpus=spec.corpus,
            evaluation=spec.evaluation,
            pipeline_outputs=pipeline_outputs,
            registry=metric_registry,
            manifest=manifest,
            usage=tuple(usage_records),
        )
        return portable_result(result, root) if root is not None else result


def _bind_archaic_metrics(registry: MetricRegistry, spec: RunSpec) -> None:
    """Relie ``air``/``hcpr`` à la liste archaïque du run (``metadata``).

    ``air`` est déjà au registre (liste par défaut) ; on le **relie** à la liste
    effective (no-op si défaut), et on **enregistre ``hcpr``** seulement si une vue
    le demande (liste configurée au plan — cf. ``evaluation_views``). Les deux côtés
    lisent la **même** ``metadata["archaic_list"]`` → ils s'accordent.
    """
    resolved = resolve_archaic_list(spec.metadata.get("archaic_list"))
    registry.register_document_metric(make_air_metric(resolved.chars))
    wants_hcpr = any("hcpr" in view.metric_names for view in spec.evaluation.views)
    if wants_hcpr:
        registry.register_document_metric(make_hcpr_metric(resolved.chars))


#: Schémas d'une image **référence** (corpus curé HF/IIIF) à matérialiser au run.
_REMOTE_SCHEMES = ("http://", "https://")
#: Suffixe de fichier image plausible (dérivé de l'URL) ; sinon repli ``.img``
#: (PIL/tesseract sniffent le contenu, l'extension n'est qu'un confort).
_SAFE_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def _materialize_remote_images(
    documents: tuple[DocumentRef, ...], images_dir: Path
) -> tuple[tuple[DocumentRef, ...], dict[str, str]]:
    """Télécharge les images **distantes** du corpus dans le workspace du run.

    Un corpus **curé** (HF/IIIF) porte des images en *référence* (URL épinglée),
    pas en octets : les moteurs, eux, lisent un **fichier local**. On matérialise
    donc chaque image distante **une fois par document** via le fetch durci
    (anti-SSRF, plafond ``IMAGE_MAX_BYTES``, écriture atomique) — ce qui rend
    aussi la **reprise** opérante (``unit_key`` hache les octets). La copie vit
    dans le workspace temporaire (nettoyé en fin de run) ; la **spec d'origine
    n'est pas réécrite** → le ``RunResult``/rapport garde l'URL de référence.

    Renvoie ``(documents exécutables, {id irrécupérable: raison})`` : une image
    injoignable n'abat pas le banc (philosophie « échec isolé d'unité ») — ses
    unités sont marquées échouées (motif ``infrastructure``), le reste tourne.
    """
    localized: list[DocumentRef] = []
    failed: dict[str, str] = {}
    for document in documents:
        uri = document.image_uri
        if uri is None or not uri.startswith(_REMOTE_SCHEMES):
            localized.append(document)
            continue
        images_dir.mkdir(parents=True, exist_ok=True)
        suffix = PurePosixPath(urlsplit(uri).path).suffix
        if not _SAFE_SUFFIX.fullmatch(suffix):
            suffix = ".img"
        dest = images_dir / safe_stem(document.id, suffix=suffix)
        try:
            download(uri, dest)
        except CorpusHttpError as exc:
            logger.warning(
                "[orchestrator] image distante irrécupérable (document %r) : %s",
                document.id,
                exc,
            )
            failed[document.id] = f"image distante irrécupérable : {exc}"
            localized.append(document)
            continue
        localized.append(document.model_copy(update={"image_uri": str(dest)}))
    return tuple(localized), failed


#: Unités nommées au plus dans le message d'une archive incomplète.
_MISSING_SHOWN = 10


def _refuse_missing(
    pending: list[tuple[PipelineSpec, DocumentRef, str | None]],
    store: ResumeStore | None,
) -> None:
    """Hors ligne : nomme les unités absentes de l'archive et arrête le run."""
    names = [f"{pipeline.name} × {document.id}" for pipeline, document, _ in pending]
    shown = ", ".join(names[:_MISSING_SHOWN])
    if len(names) > _MISSING_SHOWN:
        shown += f", … (+{len(names) - _MISSING_SHOWN})"
    where = store.base_dir if store is not None else "?"
    sans_cle = sum(1 for _, _, key in pending if key is None)
    detail = (
        f" Dont {sans_cle} sans image lisible : une unité sans image n'a pas "
        "d'empreinte, elle n'est jamais archivée."
        if sans_cle
        else ""
    )
    raise ArchiveIncompleteError(
        f"relecture hors ligne : {len(names)} unité(s) absente(s) de l'archive "
        f"{where} — {shown}. Une unité manque si elle n'a jamais été produite, "
        "si l'un de ses fichiers a disparu, si un fichier d'entrée lu par un "
        "module a changé, est apparu ou a disparu (sortie pré-calculée, ALTO "
        "voisin, sidecar OCR), ou si elle l'a été sous une autre empreinte "
        "(version d'un module, binaire, réglage ou endpoint "
        f"différents).{detail} Rien n'a été "
        "exécuté ; relancez sans --offline pour les produire."
    )


def _initial_inputs(document: DocumentRef) -> dict[ArtifactType, Artifact]:
    if document.image_uri is None:
        raise OrchestrationError(
            f"document {document.id!r} : image_uri requis (axe image→texte)."
        )
    return {
        ArtifactType.IMAGE: Artifact(
            id=f"{document.id}:initial:image",
            document_id=document.id,
            type=ArtifactType.IMAGE,
            uri=document.image_uri,
        )
    }


#: Plafond d'un message d'échec : une explication, pas une trace complète.
_MESSAGE_MAX = 1000


def _redact(
    message: str,
    secrets: tuple[str, ...],
    workspace: str,
    root: Path | None = None,
) -> str:
    """Message d'échec **sans secret**, borné : il voyage avec le ``RunResult``.

    Un moteur peut citer dans son erreur ce qu'il a reçu (une URL à jeton, un
    en-tête) ; le message suit alors le même chemin que le manifeste, donc la
    même règle : le fait reste, la valeur non. Le workspace temporaire, lui,
    change à chaque run : remplacé par ``<workspace>``, il ne rend pas le
    ``RunResult`` instable (déterminisme). Un chemin sous ``root`` (l'image du
    document) y devient relatif, comme la référence d'image du ``RunResult``.
    """
    for secret in secrets:
        message = message.replace(secret, SECRET_PLACEHOLDER)
    message = message.replace(workspace, "<workspace>")
    if root is not None:
        message = relativize_message(message, root)
    # Le chemin sous le workspace garde le séparateur du système : sous Windows
    # ``<workspace>\pipeline0/dump.json``. Normalisé en ``/``, le message est le
    # même sur toutes les plateformes, comme le reste du ``RunResult``.
    message = re.sub(
        r"<workspace>[^\s'\"]*",
        lambda m: m.group(0).replace("\\", "/"),
        message,
    )
    if len(message) > _MESSAGE_MAX:
        message = message[: _MESSAGE_MAX - 1] + "…"
    return message


__all__ = [
    "ArchiveIncompleteError",
    "ArtifactSink",
    "OrchestrationError",
    "PipelineOutputs",
    "ProgressCallback",
    "UnitProgress",
    "run",
]
