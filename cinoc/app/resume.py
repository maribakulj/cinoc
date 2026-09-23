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

L'``usage`` mesuré au run d'origine est restauré avec les artefacts (les
ressources réellement consommées pour produire le résultat — un coût de
re-lecture de cache serait un mensonge économique).
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

logger = logging.getLogger(__name__)


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

    def load(
        self, key: str
    ) -> tuple[dict[ArtifactType, Artifact], ResourceUsage] | None:
        """Artefacts + usage d'une unité, ou ``None`` (absent/corrompu)."""
        index = self._base / key / "index.json"
        try:
            data = json.loads(index.read_bytes())
            artifacts = {
                ArtifactType(type_name): Artifact.model_validate(entry)
                for type_name, entry in data["artifacts"].items()
            }
            usage = ResourceUsage.model_validate(data["usage"])
        except (OSError, ValueError, KeyError, ValidationError):
            return None
        for artifact in artifacts.values():
            if artifact.uri is not None and not Path(artifact.uri).is_file():
                return None  # entrée incomplète → ré-exécution
        return artifacts, usage

    def save(
        self,
        key: str,
        artifacts: Mapping[ArtifactType, Artifact],
        usage: ResourceUsage,
    ) -> None:
        """Persiste fichiers + index ; best-effort (un échec n'abat pas le run)."""
        unit_dir = self._base / key
        try:
            unit_dir.mkdir(parents=True, exist_ok=True)
            stored: dict[str, dict[str, object]] = {}
            for artifact_type, artifact in artifacts.items():
                entry = artifact
                if artifact.uri is not None and Path(artifact.uri).is_file():
                    suffix = Path(artifact.uri).suffix
                    destination = unit_dir / f"{artifact_type.value}{suffix}"
                    shutil.copyfile(artifact.uri, destination)
                    entry = artifact.model_copy(update={"uri": str(destination)})
                stored[artifact_type.value] = entry.model_dump(mode="json")
            payload = {"artifacts": stored, "usage": usage.model_dump(mode="json")}
            (unit_dir / "index.json").write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("[resume] persistance dégradée (unité %s) : %s", key, exc)


__all__ = ["ResumeStore", "unit_key"]
