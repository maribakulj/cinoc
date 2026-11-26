"""Réponse Mistral OCR → ``CanonicalLayout`` (couche 5) : ce qu'elle dit, rien de plus.

Projection **pure** du corps de ``POST /v1/ocr`` — celui que garde le sidecar
``NATIVE_JSON`` —, donc identique à l'exécution et à la relecture d'une archive.
Elle ne lit que les **blocs** (``pages[].blocks``, OCR 4 et suivants, quand la
requête demande ``include_blocks``) : boîte de paragraphe, étiquette, contenu,
dans l'ordre de lecture du modèle.

**Aucune information absente n'est inventée pour satisfaire le schéma.**

- **Sans bloc, pas de mise en page** (``None``). Une réponse sans blocs ne
  porte que le markdown de la page — sans boîte —, les images avec leur boîte
  et, s'ils sont extraits, l'en-tête et le pied en chaînes sans boîte. En faire
  un ``LAYOUT`` donnerait une page dont les seules régions situées sont les
  figures : les métriques de structure y liraient un segmenteur qui n'a trouvé
  aucun bloc de texte (F1 ≈ 0, CER par région ≈ 2), alors qu'aucun ne lui a été
  demandé. Le texte reste dans ``RAW_TEXT``, la réponse dans le sidecar.
- **Un bloc = une région** : ``region_type`` = l'étiquette de Mistral (``text``,
  ``title``, ``list``, ``table``, ``image``, ``caption``, ``header``,
  ``footer``…), boîte = ses deux coins. Coordonnées en pixels de l'image de page
  que décrit ``dimensions`` ; une coordonnée non entière est **arrondie au pixel
  le plus proche** (``round`` : demi au pair) ; une boîte incomplète ou inversée
  n'est pas réparée — la région existe, **sans géométrie**. Jamais de boîte
  pleine page.
- **Le texte d'un bloc** : son ``content`` passé par ``markdown_to_text``, une
  **ligne sans géométrie et sans identifiant** par ligne de texte — ce sont des
  lignes de contenu, pas des lignes imprimées situées : les métriques qui
  apparient des lignes par identifiant s'y déclarent non applicables. Un bloc
  sans texte (une image) est une région **sans lignes**.
- **``Region.confidence``** = ``block_type_confidence_score`` : la confiance du
  modèle dans le bloc et son étiquette — l'analogue du score d'un détecteur.
  La confiance du **contenu** (``average_content_confidence_score``) n'est pas
  recopiée sur les lignes : elle porte sur le bloc entier, pas sur chacune ; elle
  reste dans le sidecar. Une confiance hors [0, 1] ou absente → ``None``.
- **Doublons évités** : ``images[]``, ``header`` et ``footer`` de la page ne sont
  pas projetés à côté des blocs — images, en-têtes et pieds y sont déjà, typés
  et situés (``image``, ``header``, ``footer``).
- Les **tableaux** restent du texte (une ligne par rangée) : leur structure en
  cellules est hors 1.0.

Format lu : modèles du SDK ``mistralai`` 3.9 (``OCRPageObject.blocks``,
``OCRBlockConfidenceScores``) et documentation « Basic OCR » (modèle
``mistral-ocr-4-1``). La cassette de test est **construite** d'après eux, à
confirmer sur une réponse réelle. L'adaptateur demande les blocs
(``include_blocks``, ``confidence_scores_granularity="block"``) sous le SDK
épinglé ``mistralai>=3,<4`` ; la 1.x ne les demandait pas et les retirait de la
réponse qu'elle décodait.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Line,
    Region,
)
from cinoc.formats.text import markdown_to_text

logger = logging.getLogger(__name__)

_CORNERS = ("top_left_x", "top_left_y", "bottom_right_x", "bottom_right_y")
_MAX_REGION_TYPE = 64


def _integer(value: object) -> int | None:
    """Un entier JSON (``True`` n'en est pas un), sinon ``None``."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _pixel(value: object) -> int | None:
    if isinstance(value, float):
        return round(value) if value == value and abs(value) != float("inf") else None
    return _integer(value)


def _geometry(block: Mapping[str, Any]) -> Geometry | None:
    """Boîte des deux coins, ou ``None`` si l'un manque ou si elle est inversée."""
    x0, y0, x1, y1 = (_pixel(block.get(key)) for key in _CORNERS)
    if x0 is None or y0 is None or x1 is None or y1 is None:
        return None
    if x1 < x0 or y1 < y0:
        return None
    return Geometry(bbox=BBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0))


def _confidence(block: Mapping[str, Any]) -> float | None:
    scores = block.get("confidence_scores")
    if not isinstance(scores, dict):
        return None
    value = scores.get("block_type_confidence_score")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        logger.warning("[mistral_ocr] confiance de bloc illisible : %r", value)
        return None
    if not 0.0 <= value <= 1.0:
        logger.warning("[mistral_ocr] confiance de bloc hors [0, 1] : %r", value)
        return None
    return float(value)


def _region_type(block: Mapping[str, Any]) -> str | None:
    label = block.get("type")
    if not isinstance(label, str) or not label:
        return None
    if len(label) > _MAX_REGION_TYPE:
        logger.warning("[mistral_ocr] étiquette de bloc trop longue : %r", label)
        return None
    return label


def _region(block: Mapping[str, Any], region_id: str) -> Region:
    content = block.get("content")
    text = markdown_to_text(content) if isinstance(content, str) else ""
    return Region(
        id=region_id,
        region_type=_region_type(block),
        geometry=_geometry(block),
        lines=tuple(Line(text=line) for line in text.split("\n") if line),
        confidence=_confidence(block),
    )


def _blocks(page: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    blocks = page.get("blocks")
    if not isinstance(blocks, list):
        return []
    return [block for block in blocks if isinstance(block, dict)]


def _page(page: Mapping[str, Any], rank: int) -> LayoutPage:
    index = _integer(page.get("index"))
    prefix = f"p{rank if index is None else index}"
    regions = tuple(
        _region(block, f"{prefix}_b{n}")
        for n, block in enumerate(_blocks(page), start=1)
    )
    dimensions = page.get("dimensions")
    if not isinstance(dimensions, dict):
        dimensions = {}
    width = _integer(dimensions.get("width"))
    height = _integer(dimensions.get("height"))
    return LayoutPage(
        width=width if width and width > 0 else None,
        height=height if height and height > 0 else None,
        regions=regions,
        reading_order=tuple(region.id for region in regions),
    )


def layout_from_response(native: object) -> CanonicalLayout | None:
    """Corps de ``POST /v1/ocr`` → ``CanonicalLayout``, ``None`` sans aucun bloc."""
    raw = native.get("pages") if isinstance(native, dict) else None
    if not isinstance(raw, list):
        return None
    pages = [page for page in raw if isinstance(page, dict)]
    if not any(_blocks(page) for page in pages):
        return None
    return CanonicalLayout(
        pages=tuple(_page(page, rank) for rank, page in enumerate(pages))
    )


__all__ = ["layout_from_response"]
