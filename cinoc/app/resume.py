"""Reprise d'exécution : cache adressé par empreinte, et **archive** du run (couche 6).

Un run interrompu ou relancé ne ré-exécute pas les (pipeline × document) déjà
produits : les artefacts sont **persistés** sous une clé d'unité SHA-256 et
rechargés à l'identique. Périmètre strict : seule l'**exécution** est mise en
cache — l'**évaluation est toujours recalculée** (changer la vérité-terrain ou
les métriques re-note sans re-OCRiser ; aucun score n'est jamais en cache).

Clé d'unité = SHA-256 d'un JSON canonique : la forme du pipeline, l'**empreinte
de chaque étape** (``cinoc.pipeline.fingerprint.step_fingerprint`` : la brique,
la version du module, ses réglages effectifs — défauts et endpoint lu dans
l'environnement compris — et ses binaires système), et l'identité du
**contenu** de l'image (taille + SHA-256 des octets — pas de mtime, déterministe
entre machines). La clé **dérive** de la provenance : ``parameters_hash`` de
chaque artefact est l'empreinte de son étape. La version du paquet n'y entre
plus : une correction de métrique ne rejoue aucune inférence.

S'y ajoute le **contenu des fichiers d'entrée** que chaque module déclare lire
pour l'unité (hook facultatif ``unit_inputs(document)``, comme
``system_binaries``/``effective_settings``) : une brique ``precomputed`` ne lit
pas l'image mais ``<stem>.<label>.txt`` posé à côté, et une sortie corrigée sous
la même image était resservie périmée. Un fichier déclaré mais absent est haché
« absent » : qu'il apparaisse ou disparaisse invalide l'unité. Seul son **nom**
entre dans la clé, pas son dossier : l'archive et son corpus se déplacent.

Ce qui est persisté est l'exécution **étape par étape** (``by_step`` + la
consommation de chaque étape) : une vue qui note une étape intermédiaire se
note encore sur un run rechargé. L'``usage`` mesuré au run d'origine est
restauré avec les artefacts (les ressources réellement consommées pour produire
le résultat — un coût de re-lecture de cache serait un mensonge économique).

L'**image** d'une page n'est stockée qu'une fois, quel que soit le nombre de
pipelines qui la lisent : rangée par son contenu sous ``images/<sha256><suffixe>``
et nommée par chaque unité relativement à son dossier (``../images/…``) — la
règle de toujours, donc aucun format nouveau. Une archive d'avant, qui la
recopiait sous chaque unité, se relit telle quelle (D20 du pilote D-281 :
45 Mo pour 10 pages × 4 pipelines). Un nom relatif qui sortirait de l'archive
n'est jamais suivi : l'unité est alors incomplète.

Les sidecars voyagent comme le reste : la réponse native d'un moteur distant
(``NATIVE_JSON``) est copiée sous ``<étape>.native_json.json`` et rechargée avec
son étape ; un fichier disparu rend l'unité incomplète, donc ré-exécutée.

Le dossier **est** l'archive du run (``RunManifest.artifacts_dir``) : il garde
aussi les unités **en échec** (issue, motif, message) — une archive complète dit
ce qui a échoué —, mais une reprise normale les **ré-exécute** (un échec se
retente) ; seule une relecture hors ligne (``--offline``) les restitue. Et il
garde les **binaires** sous lesquels ses unités ont été produites
(``binaries.json``) : un run hors ligne n'exécute rien, il ne sonde donc pas le
tesseract de la machine qui relit — il reprend ceux de l'archive.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import cast, get_args

from pydantic import ValidationError

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.documents import DocumentRef
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.usage import FailureReason, ResourceUsage, UnitOutcome
from cinoc.pipeline.fingerprint import ModuleIdentity, canonical_json, step_fingerprint
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.types import DocumentExecution

logger = logging.getLogger(__name__)

#: Version du format de l'index d'une unité. **3** : une entrée par étape
#: (sorties + consommation, ordre d'exécution), l'issue (``outcome``, ``reason``,
#: ``message``) — unités en échec comprises —, sous une clé faite des empreintes
#: d'étape. Le format entre dans la clé : un index d'un format antérieur n'est
#: plus jamais trouvé — invalidé, pas converti. Une unité ``truncated`` est
#: gardée (la rejouer la couperait à l'identique et la ferait repayer) et relue
#: ``truncated``.
CACHE_FORMAT = 3

#: Issues relues (``failed`` ne l'est que hors ligne, voir :meth:`ResumeStore.load`)
#: et motifs d'échec — tirés des ``Literal`` de ``domain``, pas recopiés.
_OUTCOMES = frozenset(get_args(UnitOutcome))
_REASONS = frozenset(get_args(FailureReason))
#: Binaires des unités de l'archive, ``{adapter_name: {binaire: version}}``.
_BINARIES = "binaries.json"
#: Sous-dossier des images, rangées par contenu (une par page, tous pipelines).
IMAGES_DIR = "images"
#: Haché d'un fichier d'entrée déclaré qui n'existe pas (ou n'est pas un fichier).
ABSENT = "absent"
#: Haché d'un fichier d'entrée qui existe mais ne se lit pas.
UNREADABLE = "illisible"


def declared_inputs(
    pipeline: PipelineSpec, modules: Mapping[str, Module], document: DocumentRef
) -> dict[str, tuple[Path, ...]]:
    """``{adapter_name: fichiers}`` que les modules du pipeline lisent pour
    ``document``, par le hook **facultatif** ``unit_inputs(document)``.

    Détecté par duck-typing, hors du ``Module`` Protocol, comme
    ``system_binaries``/``effective_settings`` : un module qui ne lit que ses
    artefacts d'entrée n'a rien à déclarer.
    """
    found: dict[str, tuple[Path, ...]] = {}
    for name in sorted({step.adapter_name for step in pipeline.steps}):
        probe = getattr(modules[name], "unit_inputs", None)
        if callable(probe):
            found[name] = tuple(Path(path) for path in probe(document))
    return found


def _file_digest(path: Path, digests: dict[Path, str]) -> str:
    """Haché du contenu de ``path`` (mémoïsé pour le run), ou un marqueur."""
    if path not in digests:
        if not path.is_file():
            digests[path] = ABSENT
        else:
            try:
                digests[path] = compute_content_hash(path.read_bytes())
            except OSError:
                digests[path] = UNREADABLE
    return digests[path]


def unit_key(
    *,
    pipeline: PipelineSpec,
    identities: Mapping[str, ModuleIdentity],
    document: DocumentRef,
    inputs: Mapping[str, Sequence[Path]],
    digests: dict[Path, str] | None = None,
) -> str | None:
    """Empreinte d'une unité d'exécution ; ``None`` si l'image est illisible.

    Dérivée des empreintes d'étape — les ``parameters_hash`` que l'exécuteur
    estampille, calculés par la même fonction sur les mêmes identités.
    ``identities`` doit couvrir **chaque** module du pipeline ; ``inputs``
    (:func:`declared_inputs`) dit quels fichiers chacun lit pour l'unité, et
    leur contenu entre dans la clé. ``digests`` mémoïse ces hachés le temps
    d'un run (un sidecar commun au corpus n'est lu qu'une fois).
    """
    if document.image_uri is None:
        return None
    try:
        image_bytes = Path(document.image_uri).read_bytes()
    except OSError:
        return None
    memo = digests if digests is not None else {}
    payload = canonical_json(
        {
            "format": CACHE_FORMAT,
            "pipeline": pipeline.model_dump(mode="json", exclude={"steps"}),
            "steps": [
                step_fingerprint(step, identities[step.adapter_name])
                for step in pipeline.steps
            ],
            "inputs": [
                [
                    [path.name, _file_digest(path, memo)]
                    for path in inputs.get(step.adapter_name, ())
                ]
                for step in pipeline.steps
            ],
            "document_id": document.id,
            "image_size": len(image_bytes),
            "image_sha256": compute_content_hash(image_bytes),
        }
    )
    return sha256(payload).hexdigest()


def repetition_dir(base: Path, index: int, times: int) -> Path:
    """Archive de la répétition ``index`` (0-based) sur ``times`` (``--repeat``).

    Un run unique archive dans ``base`` ; répété, chaque run a son dossier neuf
    ``base/repetition-<k>`` : aucune répétition ne relit une autre (sinon on
    mesurerait le cache, pas le dispositif), et chacune se re-note hors ligne.
    """
    return base if times <= 1 else base / f"repetition-{index + 1}"


def _rebased(artifact: Artifact, unit_dir: Path, base: Path) -> Artifact | None:
    """Un fichier archivé est nommé relativement au dossier de son unité : on le
    rattache au dossier où l'archive se trouve **maintenant**.

    ``None`` si le nom sort de l'archive (``base``) : une archive se télécharge,
    et un ``../..`` ne doit pas y désigner un fichier de la machine qui la relit.
    """
    uri = artifact.uri
    if uri is None or "://" in uri or Path(uri).is_absolute():
        return artifact
    resolved = Path(os.path.normpath(unit_dir / uri))
    if not resolved.is_relative_to(Path(os.path.normpath(base))):
        return None
    return artifact.model_copy(update={"uri": str(resolved)})


class ResumeStore:
    """Cache disque des sorties d'exécution, adressé par clé d'unité."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._base.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        """Où les artefacts sont **conservés**.

        Ce cache porte deux rôles pour un seul mécanisme : éviter de
        ré-exécuter, et — parce que ``save`` **copie** les fichiers et réécrit
        leur chemin — garder les sorties au-delà du workspace, qui est
        temporaire et effacé à la sortie. Le second rôle n'était nommé nulle
        part ; le manifeste l'enregistre désormais.
        """
        return self._base

    def load(self, key: str, *, failures: bool = False) -> DocumentExecution | None:
        """Exécution d'une unité (sorties + consommation par étape), ou ``None``.

        ``None`` = absente, corrompue, incomplète **ou d'un format antérieur**
        (la clé porte le format, donc un index ancien n'est plus atteint ; s'il
        l'était, on n'en déduirait pas ``by_step`` : l'unité est ré-exécutée,
        puis réécrite au format courant). Une unité **en échec** n'est rendue
        que si ``failures`` (relecture hors ligne) : une reprise normale la
        retente.
        """
        index = self._base / key / "index.json"
        try:
            data = json.loads(index.read_bytes())
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("format") != CACHE_FORMAT:
            logger.info(
                "[resume] unité %s : cache d'un format antérieur, ré-exécutée.", key
            )
            return None
        unit_dir = self._base / key
        try:
            rebased = {
                entry["step"]: {
                    ArtifactType(type_name): _rebased(
                        Artifact.model_validate(artifact), unit_dir, self._base
                    )
                    for type_name, artifact in entry["artifacts"].items()
                }
                for entry in data["steps"]
            }
            step_usage = {
                entry["step"]: ResourceUsage.model_validate(entry["usage"])
                for entry in data["steps"]
                if entry["usage"] is not None
            }
            outcome = data["outcome"]
            reason = data.get("reason")
            message = data.get("message")
            if outcome not in _OUTCOMES or not (
                message is None or isinstance(message, str)
            ):
                return None
        except (AttributeError, TypeError, ValueError, KeyError, ValidationError):
            return None
        by_step: dict[str, dict[ArtifactType, Artifact]] = {}
        for step_id, found in rebased.items():
            kept: dict[ArtifactType, Artifact] = {}
            for artifact_type, artifact in found.items():
                if artifact is None:
                    logger.warning(
                        "[resume] unité %s : un fichier nommé hors de l'archive "
                        "n'est pas suivi ; unité ré-exécutée.",
                        key,
                    )
                    return None
                kept[artifact_type] = artifact
            by_step[step_id] = kept
        if outcome == "failed":
            if not (failures and isinstance(reason, str) and message is not None):
                return None
            if reason not in _REASONS:
                return None
            try:
                billed = (
                    ResourceUsage.model_validate(data["billed"])
                    if data.get("billed") is not None
                    else None
                )
            except ValidationError:
                return None
            return DocumentExecution.failed(
                cast(FailureReason, reason), message, billed=billed
            )
        for outputs in by_step.values():
            for artifact in outputs.values():
                if artifact.uri is not None and not Path(artifact.uri).is_file():
                    return None  # entrée incomplète → ré-exécution
        return DocumentExecution(
            by_step=by_step, step_usage=step_usage, outcome=outcome, message=message
        )

    def save(self, key: str, execution: DocumentExecution) -> None:
        """Persiste fichiers + index ; best-effort (un échec n'abat pas le run).

        Une entrée par étape, **dans l'ordre d'exécution** (une liste : l'ordre
        est ce qui désigne l'étape la plus aval). Les fichiers sont nommés par
        étape et par type — deux étapes de même type ne s'écrasent plus.

        **Atomique** : l'unité est écrite dans un dossier temporaire voisin
        (``.<clé>.partiel``, même parent, donc mêmes noms relatifs vers
        ``../images/``), puis renommée. Une écriture coupée ne laisse jamais,
        sous le nom qui fait foi, un index ancien et des fichiers neufs à moitié
        copiés — l'unité d'avant reste entière, ou rien n'y est.
        """
        unit_dir = self._base / key
        partial = self._base / f".{key}.partiel"
        try:
            if partial.exists():
                shutil.rmtree(partial)  # reste d'une écriture coupée
            partial.mkdir(parents=True)
            steps: list[dict[str, object]] = []
            for step_id, outputs in execution.by_step.items():
                stored: dict[str, object] = {}
                for artifact_type, artifact in outputs.items():
                    entry = artifact
                    if artifact.uri is not None and Path(artifact.uri).is_file():
                        if artifact_type is ArtifactType.IMAGE:
                            name = self._store_image(Path(artifact.uri))
                        else:
                            suffix = Path(artifact.uri).suffix
                            name = f"{step_id}.{artifact_type.value}{suffix}"
                            shutil.copyfile(artifact.uri, partial / name)
                        # Relatif au dossier de l'unité : l'archive se déplace,
                        # se télécharge, se re-note ailleurs (P5h).
                        entry = artifact.model_copy(update={"uri": name})
                    stored[artifact_type.value] = entry.model_dump(mode="json")
                usage = execution.step_usage.get(step_id)
                steps.append(
                    {
                        "step": step_id,
                        "artifacts": stored,
                        "usage": (
                            usage.model_dump(mode="json") if usage is not None else None
                        ),
                    }
                )
            payload = {
                "format": CACHE_FORMAT,
                "steps": steps,
                "outcome": execution.outcome,
                "reason": execution.reason,
                "message": execution.message,
                # Ce qu'une unité en échec a fait facturer (champ additif :
                # absent d'une entrée antérieure → rien de facturé connu).
                "billed": (
                    execution.billed.model_dump(mode="json")
                    if execution.billed is not None
                    else None
                ),
            }
            (partial / "index.json").write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            self._publish(partial, unit_dir)
        except OSError as exc:
            logger.warning("[resume] persistance dégradée (unité %s) : %s", key, exc)

    @staticmethod
    def _publish(partial: Path, unit_dir: Path) -> None:
        """Met l'unité écrite sous son nom. Un dossier ne se remplace pas d'un
        seul renommage s'il n'est pas vide : l'ancien est d'abord écarté (un
        renommage), puis le neuf prend sa place, puis l'ancien est effacé. Coupé
        entre les deux renommages, l'archive n'a plus l'unité : elle sera
        ré-exécutée (ou, hors ligne, refusée) — jamais lue à moitié."""
        if unit_dir.exists():
            aside = unit_dir.with_name(f".{unit_dir.name}.ancien")
            if aside.exists():
                shutil.rmtree(aside)
            unit_dir.replace(aside)
            partial.replace(unit_dir)
            shutil.rmtree(aside)
        else:
            partial.replace(unit_dir)

    def _store_image(self, source: Path) -> str:
        """Range une image par son contenu, une fois ; renvoie son nom relatif
        au dossier d'une unité (``../images/<sha256><suffixe>``).

        Le même contenu a le même nom : la deuxième unité qui lit la page ne
        recopie rien. Écrite sous un nom temporaire puis renommée — une copie
        interrompue ne laisse pas un fichier tronqué sous un nom qui ferait foi.
        """
        payload = source.read_bytes()
        name = f"{compute_content_hash(payload)}{source.suffix.lower()}"
        images = self._base / IMAGES_DIR
        destination = images / name
        if not destination.is_file():
            images.mkdir(exist_ok=True)
            partial = images / f".{name}.partiel"
            partial.write_bytes(payload)
            partial.replace(destination)
        return f"../{IMAGES_DIR}/{name}"

    def recorded_binaries(self) -> dict[str, dict[str, str]]:
        """Binaires sous lesquels l'archive a été produite, par module (``{}`` si
        aucun n'a été inscrit ou si le fichier est illisible)."""
        try:
            data = json.loads((self._base / _BINARIES).read_bytes())
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(name): {str(k): str(v) for k, v in binaries.items()}
            for name, binaries in data.items()
            if isinstance(binaries, dict)
        }

    def record_binaries(self, binaries: Mapping[str, Mapping[str, str]]) -> None:
        """Inscrit les binaires des modules qui viennent de produire des unités.

        Par module, le dernier run qui en a produit l'emporte — comme pour les
        unités elles-mêmes, réécrites sous leur clé. Best-effort.
        """
        merged = self.recorded_binaries()
        merged.update({name: dict(values) for name, values in binaries.items()})
        try:
            (self._base / _BINARIES).write_text(
                json.dumps(merged, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("[resume] binaires non inscrits : %s", exc)


__all__ = [
    "ABSENT",
    "CACHE_FORMAT",
    "IMAGES_DIR",
    "UNREADABLE",
    "ResumeStore",
    "declared_inputs",
    "repetition_dir",
    "unit_key",
]
