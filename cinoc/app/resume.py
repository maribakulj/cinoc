"""Reprise d'exécution : cache adressé par empreinte (couche 6).

Un run interrompu ou relancé ne ré-exécute pas les (pipeline × document) déjà
produits : les artefacts sont **persistés** sous une clé d'unité SHA-256 et
rechargés à l'identique. Périmètre strict : seule l'**exécution** est mise en
cache — l'**évaluation est toujours recalculée** (changer la vérité-terrain ou
les métriques re-note sans re-OCRiser ; aucun score n'est jamais en cache).

Clé d'unité = SHA-256 d'un JSON canonique : version de code + spec du pipeline
+ ``adapter_kwargs`` des modules du pipeline + identité du **contenu** de
l'image (taille + SHA-256 des octets — pas de mtime, déterministe entre
machines). Tout changement (paramètre, code, image) invalide la clé : pas de
journal d'invalidation, l'adressage par contenu suffit (≠ la source, qui
journalisait en NDJSON).

Ce qui est persisté est l'exécution **étape par étape** (``by_step`` + la
consommation de chaque étape) : une vue qui note une étape intermédiaire se
note encore sur un run rechargé. L'``usage`` mesuré au run d'origine est
restauré avec les artefacts (les ressources réellement consommées pour produire
le résultat — un coût de re-lecture de cache serait un mensonge économique).
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.documents import DocumentRef
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.usage import ResourceUsage
from cinoc.pipeline.types import DocumentExecution

logger = logging.getLogger(__name__)

#: Version du format de l'index d'une unité. **2** : une entrée par étape
#: (sorties + consommation), dans l'ordre d'exécution. La 1 (sans ce champ) ne
#: gardait que le pool et l'usage agrégé ; elle est invalidée, pas convertie.
#: L'issue (``outcome`` + ``message``) s'y ajoute sans changer de format : une
#: unité ``truncated`` est gardée — la rejouer la couperait à l'identique et la
#: ferait repayer — et relue ``truncated``. Une entrée sans ce champ est ``ok``
#: (le format 2 ne gardait que des réussites complètes).
CACHE_FORMAT = 2


def unit_key(
    *,
    code_version: str,
    pipeline: PipelineSpec,
    adapter_kwargs: Mapping[str, Mapping[str, object]],
    document: DocumentRef,
) -> str | None:
    """Empreinte d'une unité d'exécution ; ``None`` si l'image est illisible."""
    if document.image_uri is None:
        return None
    try:
        image_bytes = Path(document.image_uri).read_bytes()
    except OSError:
        return None
    relevant_kwargs = {
        step.adapter_name: dict(adapter_kwargs.get(step.adapter_name, {}))
        for step in pipeline.steps
    }
    payload = json.dumps(
        {
            "code_version": code_version,
            "pipeline": pipeline.model_dump(mode="json"),
            "adapter_kwargs": relevant_kwargs,
            "document_id": document.id,
            "image_size": len(image_bytes),
            "image_sha256": compute_content_hash(image_bytes),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


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

    def load(self, key: str) -> DocumentExecution | None:
        """Exécution d'une unité (sorties + consommation par étape), ou ``None``.

        ``None`` = absente, corrompue, incomplète **ou d'un format antérieur** :
        un index d'avant :data:`CACHE_FORMAT` ne gardait que le pool (dernier
        artefact par type) et l'usage agrégé. On n'en déduit pas ``by_step`` —
        la sortie écrasée d'une étape amont n'y est plus, et la reconstruire
        serait inventer : l'unité est ré-exécutée, puis réécrite au format courant.
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
        try:
            by_step = {
                entry["step"]: {
                    ArtifactType(type_name): Artifact.model_validate(artifact)
                    for type_name, artifact in entry["artifacts"].items()
                }
                for entry in data["steps"]
            }
            step_usage = {
                entry["step"]: ResourceUsage.model_validate(entry["usage"])
                for entry in data["steps"]
                if entry["usage"] is not None
            }
            outcome = data.get("outcome", "ok")
            message = data.get("message")
            if outcome not in ("ok", "truncated") or not (
                message is None or isinstance(message, str)
            ):
                return None
        except (AttributeError, TypeError, ValueError, KeyError, ValidationError):
            return None
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
        """
        unit_dir = self._base / key
        try:
            unit_dir.mkdir(parents=True, exist_ok=True)
            steps: list[dict[str, object]] = []
            for step_id, outputs in execution.by_step.items():
                stored: dict[str, object] = {}
                for artifact_type, artifact in outputs.items():
                    entry = artifact
                    if artifact.uri is not None and Path(artifact.uri).is_file():
                        suffix = Path(artifact.uri).suffix
                        name = f"{step_id}.{artifact_type.value}{suffix}"
                        destination = unit_dir / name
                        shutil.copyfile(artifact.uri, destination)
                        entry = artifact.model_copy(update={"uri": str(destination)})
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
                "message": execution.message,
            }
            (unit_dir / "index.json").write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("[resume] persistance dégradée (unité %s) : %s", key, exc)


__all__ = ["CACHE_FORMAT", "ResumeStore", "unit_key"]
