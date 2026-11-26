"""``crop_region`` — découpe l'image d'un bloc pour l'OCR par région (couche 5).

Brique du pipeline **hybride** « segmentation externe → OCR des blocs » : le
fan-out (couche 4) fournit une **boîte relative** ``(x0, y0, x1, y1) ∈ [0, 1]``
(la couche 4 a déjà neutralisé les unités, ALTO ``mm10`` vs pixels) ; ici on
ouvre l'image, on convertit en pixels et on découpe — le crop réel vit en
couche 5 car il dépend de ``PIL`` (interdit à ``pipeline``).

``Pillow`` est un extra optionnel, importé **paresseusement** : importer ce
module n'exige pas la lib, seule l'exécution.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.types import RunContext

_RelBox = tuple[float, float, float, float]


def crop_region(
    page_image: Artifact, rel_bbox: _RelBox, region_id: str, context: RunContext
) -> Artifact:
    """Découpe ``rel_bbox`` (relatif) de l'image page → artefact ``IMAGE`` du bloc."""
    if page_image.uri is None:
        raise AdapterStepError("crop_region : image page sans URI.")
    if context.workspace_uri is None:
        raise AdapterStepError("crop_region : workspace requis pour écrire le crop.")
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AdapterStepError(
            "crop_region : Pillow non installé (pip install 'cinoc[images]')."
        ) from exc
    try:
        with Image.open(page_image.uri) as image:
            width, height = image.size
            box = (
                max(0, min(width, round(rel_bbox[0] * width))),
                max(0, min(height, round(rel_bbox[1] * height))),
                max(0, min(width, round(rel_bbox[2] * width))),
                max(0, min(height, round(rel_bbox[3] * height))),
            )
            if box[2] <= box[0] or box[3] <= box[1]:
                raise AdapterStepError(
                    f"crop_region : boîte vide pour la région {region_id!r}."
                )
            crop = image.crop(box)
            stem = quote(region_id, safe="")
            out_path = Path(context.workspace_uri) / (
                f"{quote(context.document_id, safe='')}.{stem}.crop.png"
            )
            crop.save(out_path)
    except OSError as exc:
        raise AdapterStepError(
            f"crop_region : image illisible ({page_image.uri!r}) : {exc}"
        ) from exc
    return Artifact(
        id=f"{context.document_id}:crop:{region_id}",
        document_id=context.document_id,
        type=ArtifactType.IMAGE,
        uri=str(out_path),
        content_hash=compute_content_hash(out_path.read_bytes()),
        region_id=region_id,
    )


__all__ = ["crop_region"]
