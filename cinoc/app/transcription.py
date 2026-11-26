"""Transcription hybride locale : images → run hybride → fichiers ALTO (couche 6).

Le run **hybride** (segmentation → OCR par région → assemblage ALTO) part
d'**images sans vérité-terrain** et produit un ALTO par page. Ce module fournit
les deux bouts que le transport câble autour de la recette hybride
(``segmentation_puis_lecture``, par ``plan_recipe_run``) :

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
from cinoc.domain.artifacts import ArtifactType, latest_by_type
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import CinocError
from cinoc.formats.images import IMAGE_SUFFIXES

logger = logging.getLogger(__name__)

#: Extensions d'image reconnues dans un dossier de transcription.


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
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )
    if not paths:
        raise TranscriptionError(
            f"aucune image reconnue dans {folder} "
            f"(extensions : {list(IMAGE_SUFFIXES)})."
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
    """Écrit un ALTO par **(pipeline, document)**. Retourne les chemins.

    Nom de sortie ``<doc>.<pipeline>.alto.xml`` (``/`` → ``_`` ; les ``id`` de
    document sont déjà sans ``..`` ni absolu, garanti par ``DocumentRef``, et le
    nom de pipeline est assaini de la même façon).

    **Le nom portait le seul document.** Comparer deux chaînes qui produisent
    toutes deux de l'ALTO — exactement ce qu'un banc fait — les faisait donc
    écrire dans le même fichier : le dernier écrasait l'autre, sans un mot, et
    le compte annoncé (« 2 ALTO écrits ») restait juste alors qu'un seul
    survivait. Découvert en exécutant les deux chaînes NDNP côte à côte.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for pipeline_name, by_document in outputs.items():
        pipeline = _safe(pipeline_name)
        for document_id, by_step in by_document.items():
            artifact = latest_by_type(by_step).get(ArtifactType.ALTO_XML)
            if artifact is None or artifact.uri is None:
                continue
            target = out_dir / f"{_safe(document_id)}.{pipeline}.alto.xml"
            shutil.copyfile(artifact.uri, target)
            written.append(target)
            logger.info(
                "[transcription] %s · %s → %s", pipeline_name, document_id, target
            )
    return sorted(written)


def _safe(name: str) -> str:
    """Composant de nom de fichier sûr : ``/`` et ``.`` ne doivent pas creuser
    d'arborescence ni couper l'extension attendue, et un nom de pipeline
    (``segmentation_puis_lecture · tesseract_layout → tesseract + alto``,
    D-298) n'a rien à faire d'espaces ni de flèches dans un nom de fichier :
    chaque suite de caractères hors ``[A-Za-z0-9_-]`` devient un ``_``."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")


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
        for document_id, by_step in by_document.items():
            artifact = latest_by_type(by_step).get(ArtifactType.LAYOUT)
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
