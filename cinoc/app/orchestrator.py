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
from datetime import datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from cinoc.adapters.corpus._http import CorpusHttpError, download
from cinoc.adapters.layout.crop import crop_region
from cinoc.app.modules.registry import ModuleRegistry
from cinoc.app.resume import ResumeStore, unit_key
from cinoc.app.security import safe_stem
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import AdapterStepError, CinocError, RunCancelledError
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest, utcnow
from cinoc.domain.run_spec import RunSpec
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.archaic import resolve_archaic_list
from cinoc.evaluation.metrics.archaic import make_air_metric, make_hcpr_metric
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.result import DocumentUsage, RunResult
from cinoc.evaluation.runner import evaluate_run
from cinoc.pipeline.executor import PipelineExecutor, PipelineStepError
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl

logger = logging.getLogger(__name__)


class OrchestrationError(CinocError):
    """Run impossible à exécuter (document sans image, etc.)."""


#: Sorties d'un run, indexées ``pipeline → document → type → artefact``.
PipelineOutputs = Mapping[str, Mapping[str, Mapping[ArtifactType, Artifact]]]
#: Sink optionnel d'artefacts : reçoit les sorties **avant** le nettoyage du
#: workspace (les URI sont encore lisibles). La couche 6 (app) le fournit ;
#: l'orchestrateur l'invoque sans rien connaître de sa cible (un store, etc.).
ArtifactSink = Callable[[PipelineOutputs, RunManifest], None]
#: Callback de progression : ``(unités traitées, total)``. Émis après chaque
#: document (succès **ou** échec isolé). Une unité = un (concurrent × document).
ProgressCallback = Callable[[int, int], None]


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

    def tick(self) -> None:
        if self._callback is None:
            return
        with self._lock:
            self._done += 1
            done = self._done
        self._callback(done, self._total)


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
    """
    started_at = utcnow()
    needed = sorted(
        {step.adapter_name for pipeline in spec.pipelines for step in pipeline.steps}
    )
    modules = {
        name: registry.build(name, spec.adapter_kwargs.get(name, {}))
        for name in needed
    }
    executor = PipelineExecutor(code_version)
    metric_registry = MetricRegistry()
    register_default_metrics(metric_registry)
    _bind_archaic_metrics(metric_registry, spec)

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
        #    sont rechargées ; les autres sont mises en file d'exécution.
        results: dict[tuple[str, str], dict[ArtifactType, Artifact]] = {}
        usage_by_unit: dict[tuple[str, str], ResourceUsage] = {}
        pending: list[tuple[PipelineSpec, DocumentRef, str | None]] = []
        for pipeline in spec.pipelines:
            for document in documents:
                if document.id in unreachable:
                    # Image distante injoignable : unité échouée (comme un échec
                    # d'adapter isolé), le reste du corpus tourne normalement.
                    results[(pipeline.name, document.id)] = {}
                    progress.tick()
                    continue
                key = (
                    unit_key(
                        code_version=code_version,
                        pipeline=pipeline,
                        adapter_kwargs=spec.adapter_kwargs,
                        document=document,
                    )
                    if resume_store is not None
                    else None
                )
                cached = resume_store.load(key) if resume_store and key else None
                if cached is not None:
                    artifacts, cached_usage = cached
                    results[(pipeline.name, document.id)] = dict(artifacts)
                    usage_by_unit[(pipeline.name, document.id)] = cached_usage
                    progress.tick()
                else:
                    pending.append((pipeline, document, key))

        # 2) Exécution **parallèle** des unités non-cachées. OCR (sous-processus)
        #    et LLM/cloud (I/O HTTP) libèrent le GIL → les threads donnent un
        #    speedup réel sans sérialiser les artefacts. Un échec isolé d'unité
        #    (`AdapterStepError`/`PipelineStepError`) n'abat pas le banc ; seule
        #    l'annulation (`RunCancelledError`) arrête tout le run.
        saves: list[tuple[str, Mapping[ArtifactType, Artifact], ResourceUsage]] = []
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
                        except (AdapterStepError, PipelineStepError) as exc:
                            logger.warning(
                                "[orchestrator] concurrent %r · document %r "
                                "échoué : %s",
                                pipeline.name,
                                document.id,
                                exc,
                            )
                            results[unit] = {}
                            progress.tick()
                            continue
                        results[unit] = dict(execution.artifacts)
                        usage_by_unit[unit] = execution.usage
                        if key is not None:
                            saves.append((key, execution.artifacts, execution.usage))
                        progress.tick()
                except RunCancelledError:
                    # Annulation coopérative : on cesse de planifier (les unités
                    # non démarrées sont annulées) et on propage — le run s'arrête.
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise

        # 3) Reprise : persistance des unités exécutées (thread principal, post-pool).
        if resume_store is not None:
            for saved_key, saved_artifacts, saved_usage in saves:
                resume_store.save(saved_key, saved_artifacts, saved_usage)

        # 4) Assemblage **déterministe** : ordre du spec, indépendant de l'ordre
        #    d'achèvement des threads → `RunResult` byte-identique au séquentiel.
        pipeline_outputs: dict[str, dict[str, dict[ArtifactType, Artifact]]] = {}
        usage_records: list[DocumentUsage] = []
        for pipeline in spec.pipelines:
            per_document: dict[str, dict[ArtifactType, Artifact]] = {}
            for document in documents:
                unit = (pipeline.name, document.id)
                per_document[document.id] = results[unit]
                if unit in usage_by_unit:
                    usage_records.append(
                        DocumentUsage(
                            document_id=document.id,
                            pipeline=pipeline.name,
                            usage=usage_by_unit[unit],
                        )
                    )
            pipeline_outputs[pipeline.name] = per_document

        completed_at = utcnow()
        manifest = _manifest(
            spec,
            modules,
            code_version,
            started_at,
            completed_at,
            system_binaries=_collect_system_binaries(modules),
            artifacts_dir=(
                str(resume_store.base_dir) if resume_store is not None else None
            ),
        )
        # Sink avant la sortie du ``with`` : les URI des artefacts (LAYOUT…)
        # pointent encore dans le workspace vivant. Best-effort côté appelant.
        if artifact_sink is not None:
            artifact_sink(pipeline_outputs, manifest)
        return evaluate_run(
            corpus=spec.corpus,
            evaluation=spec.evaluation,
            pipeline_outputs=pipeline_outputs,
            registry=metric_registry,
            manifest=manifest,
            usage=tuple(usage_records),
        )


def _bind_archaic_metrics(registry: MetricRegistry, spec: RunSpec) -> None:
    """Relie ``air``/``hcpr`` à la liste archaïque du run (``metadata``).

    ``air`` est déjà au registre (liste par défaut) ; on le **relie** à la liste
    effective (no-op si défaut), et on **enregistre ``hcpr``** seulement si une vue
    le demande (liste configurée au plan — cf. ``run_planning``). Les deux côtés
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
) -> tuple[tuple[DocumentRef, ...], frozenset[str]]:
    """Télécharge les images **distantes** du corpus dans le workspace du run.

    Un corpus **curé** (HF/IIIF) porte des images en *référence* (URL épinglée),
    pas en octets : les moteurs, eux, lisent un **fichier local**. On matérialise
    donc chaque image distante **une fois par document** via le fetch durci
    (anti-SSRF, plafond ``IMAGE_MAX_BYTES``, écriture atomique) — ce qui rend
    aussi la **reprise** opérante (``unit_key`` hache les octets). La copie vit
    dans le workspace temporaire (nettoyé en fin de run) ; la **spec d'origine
    n'est pas réécrite** → le ``RunResult``/rapport garde l'URL de référence.

    Renvoie ``(documents exécutables, ids irrécupérables)`` : une image
    injoignable n'abat pas le banc (philosophie « échec isolé d'unité ») — ses
    unités sont marquées échouées, le reste du corpus tourne.
    """
    localized: list[DocumentRef] = []
    failed: set[str] = set()
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
            failed.add(document.id)
            localized.append(document)
            continue
        localized.append(document.model_copy(update={"image_uri": str(dest)}))
    return tuple(localized), frozenset(failed)


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


def _collect_system_binaries(modules: Mapping[str, Module]) -> dict[str, str]:
    """Versions des **binaires externes** des modules exécutés (reproductibilité).

    Un module qui enveloppe un binaire système (ex. tesseract) expose
    ``system_binaries() -> dict[str, str]`` ; on le détecte par **duck-typing**
    (hors ``Module`` Protocol — le contrat d'exécution reste unique) et on fusionne.
    Le hook est best-effort côté module (binaire absent → ``{}``) → pas de garde
    ici, pas de panne. Seuls les modules réellement construits sont sondés.
    """
    binaries: dict[str, str] = {}
    for module in modules.values():
        probe = getattr(module, "system_binaries", None)
        if callable(probe):
            binaries.update(probe())
    return binaries


def _manifest(
    spec: RunSpec,
    modules: Mapping[str, Module],
    code_version: str,
    started_at: datetime,
    completed_at: datetime,
    *,
    system_binaries: dict[str, str],
    artifacts_dir: str | None = None,
) -> RunManifest:
    names = sorted(modules)
    return RunManifest(
        run_id=spec.run_id or f"run-{started_at.strftime('%Y%m%dT%H%M%S')}",
        corpus_name=spec.corpus.name,
        n_documents=len(spec.corpus.documents),
        pipeline_specs=spec.pipelines,
        adapter_kwargs={
            name: dict(spec.adapter_kwargs.get(name, {})) for name in names
        },
        # Reproductibilité (R-2) : la version de chaque module exécuté entre dans
        # l'empreinte. `module_versions` = version d'*adapter* ; la version du
        # *binaire* externe (ex. tesseract) est captée à l'exécution dans
        # `system_binaries_lock` via le hook `system_binaries()` (duck-typing).
        module_versions={name: modules[name].version for name in names},
        system_binaries_lock=system_binaries,
        view_specs=spec.evaluation.views,
        code_version=code_version,
        started_at=started_at,
        completed_at=completed_at,
        metadata=spec.metadata,
        artifacts_dir=artifacts_dir,
    )


__all__ = ["ArtifactSink", "OrchestrationError", "PipelineOutputs", "run"]
