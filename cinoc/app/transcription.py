"""Transcription hybride locale : images → run hybride → fichiers ALTO (couche 6).

Le run **hybride** (segmentation → OCR par région → assemblage ALTO) part
d'**images sans vérité-terrain** et produit un ALTO par page. Ce module fournit
les deux bouts que le transport (CLI / web) câble autour de ``plan_hybrid_run`` :

- ``corpus_from_images`` : un dossier d'images → ``CorpusSpec`` (1 image = 1
  document, id dérivé du nom de fichier, **aucune GT**) ;
- ``write_alto_files`` : copie chaque ``ALTO_XML`` produit vers
  ``<out>/<doc>.alto.xml``. Branché en **sink d'orchestrateur** par l'appelant
  (CLI / web) → écrit **avant** le nettoyage du workspace (URIs encore lisibles,
  même mécanisme que le sink de segmentation).
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from cinoc.app.orchestrator import PipelineOutputs
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import CinocError

logger = logging.getLogger(__name__)

#: Extensions d'image reconnues dans un dossier de transcription.
_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".jp2"})


class TranscriptionError(CinocError):
    """Entrée de transcription invalide (dossier introuvable, sans image…)."""


def _doc_id(stem: str, taken: set[str]) -> str:
    """``stem`` → identifiant de document **valide et unique** (``_DOC_ID_RE``).

    Réduit aux caractères sûrs (accents/espaces → ``_``) pour rester lisible ;
    une collision (deux radicaux qui se réduisent au même) est désambiguïsée par
    un suffixe ``-N`` plutôt que par un hash (le nom de fichier de sortie reste
    lisible)."""
    base = re.sub(r"[^A-Za-z0-9_.\-]+", "_", stem).strip("_.-") or "doc"
    candidate = base
    index = 2
    while candidate in taken:
        candidate = f"{base}-{index}"
        index += 1
    taken.add(candidate)
    return candidate


def corpus_from_images(
    directory: str | Path, *, name: str | None = None
) -> CorpusSpec:
    """``CorpusSpec`` d'un dossier d'images locales (1 image = 1 document, sans GT).

    Images triées par nom (déterminisme) ; l'id de document dérive du radical du
    fichier. Dossier introuvable ou sans image reconnue → ``TranscriptionError``.
    """
    folder = Path(directory)
    if not folder.is_dir():
        raise TranscriptionError(f"dossier d'images introuvable : {folder}")
    paths = sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXT
    )
    if not paths:
        raise TranscriptionError(
            f"aucune image reconnue dans {folder} "
            f"(extensions : {sorted(_IMAGE_EXT)})."
        )
    taken: set[str] = set()
    documents = tuple(
        DocumentRef(
            id=_doc_id(p.stem, taken),
            image_uri=str(p.resolve()),
            ground_truths=(),
        )
        for p in paths
    )
    return CorpusSpec(name=name or folder.name, documents=documents)


def write_alto_files(out_dir: Path, outputs: PipelineOutputs) -> list[Path]:
    """Écrit un ALTO par document portant un ``ALTO_XML``. Retourne les chemins.

    Nom de sortie ``<doc>.alto.xml`` (``/`` → ``_`` ; les ``id`` de document sont
    déjà sans ``..`` ni absolu, garanti par ``DocumentRef``)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for by_document in outputs.values():
        for document_id, artifacts in by_document.items():
            artifact = artifacts.get(ArtifactType.ALTO_XML)
            if artifact is None or artifact.uri is None:
                continue
            target = out_dir / f"{document_id.replace('/', '_')}.alto.xml"
            shutil.copyfile(artifact.uri, target)
            written.append(target)
            logger.info("[transcription] %s → %s", document_id, target)
    return sorted(written)


def write_layout_files(out_dir: Path, outputs: PipelineOutputs) -> list[Path]:
    """Écrit un ``LAYOUT`` JSON par document segmenté. Retourne les chemins.

    Jumeau de :func:`write_alto_files`, pour la sortie d'un run de segmentation
    seule. Même convention de nom (``<doc>.layout.json``), donc **relisible**
    par ``precomputed_layout`` : on peut segmenter une fois, puis rejouer
    plusieurs reconnaissances sur la même mise en page sans re-segmenter.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for by_document in outputs.values():
        for document_id, artifacts in by_document.items():
            artifact = artifacts.get(ArtifactType.LAYOUT)
            if artifact is None or artifact.uri is None:
                continue
            target = out_dir / f"{document_id.replace('/', '_')}.layout.json"
            shutil.copyfile(artifact.uri, target)
            written.append(target)
            logger.info("[transcription] %s → %s", document_id, target)
    return sorted(written)


__all__ = [
    "TranscriptionError",
    "corpus_from_images",
    "write_alto_files",
    "write_layout_files",
]
