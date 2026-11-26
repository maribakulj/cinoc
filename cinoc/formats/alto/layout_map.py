"""Mapper ``AltoDocument → CanonicalLayout`` — pont format ALTO ↔ modèle neutre.

Première moitié du pont de la tranche segmentation (l'assembleur inverse
``layout → ALTO`` est un épaississement ultérieur). Le parsing reste en amont
(``parse_alto`` ; couche 2) ; ici on **projette** la structure ALTO vers le
vocabulaire neutre ``CanonicalLayout`` (couche 1) que consomment les métriques
de structure.

L'unité de mesure ALTO (``MeasurementUnit``) passe dans
``CanonicalLayout.coordinate_unit`` et en revient : les coordonnées ne sont pas
converties, et un ALTO ``mm10`` réassemblé sans son unité se lirait en pixels.
Une unité inconnue (lecture tolérante) est signalée et prise pour des pixels.

Choix de tranche (largeur minimale) : le texte de ligne est la **jointure simple**
des ``<String>`` (la dé-césure ``HypPart1/HypPart2`` est une affaire de projection
``layout → texte``, différée). Les ``id`` de région absents sont **synthétisés**
de façon déterministe (``region_<n>`` en ordre document) pour rester uniques et
appariables.
"""

from __future__ import annotations

import logging
from typing import get_args

from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    CoordinateUnit,
    Geometry,
    LayoutPage,
    Line,
    Region,
    Word,
)
from cinoc.formats._geometry import Point
from cinoc.formats._region_ids import RegionIds
from cinoc.formats.alto.types import (
    AltoBBox,
    AltoBlock,
    AltoComposedBlock,
    AltoDocument,
    AltoGraphicalElement,
    AltoIllustration,
    AltoLine,
    AltoPage,
    AltoString,
    AltoTextBlock,
)

logger = logging.getLogger(__name__)

_NON_TEXT_TYPES = frozenset({"illustration", "graphical"})

_UNITS: frozenset[str] = frozenset(get_args(CoordinateUnit))


def _geometry(
    bbox: AltoBBox | None, polygon: tuple[Point, ...] | None
) -> Geometry | None:
    if bbox is None and not polygon:
        return None
    neutral = (
        BBox(x=bbox.hpos, y=bbox.vpos, width=bbox.width, height=bbox.height)
        if bbox is not None
        else None
    )
    return Geometry(bbox=neutral, polygon=tuple(polygon or ()))


def _word(string: AltoString) -> Word:
    return Word(
        text=string.content,
        geometry=_geometry(string.bbox, None),
        confidence=string.confidence,
        subs_type=string.subs_type,
        subs_content=string.subs_content,
    )


def _line(line: AltoLine) -> Line:
    words = tuple(_word(s) for s in line.strings)
    return Line(
        id=line.id,
        # ``line.text`` vient du parser, qui a lu les ``SP`` et les ``HYP``.
        # La jointure par espaces reste le repli des layouts construits à la
        # main (tests, segmenteurs), qui n'ont ni l'un ni l'autre.
        text=line.text or " ".join(w.text for w in words),
        geometry=_geometry(line.bbox, line.polygon),
        baseline=tuple(line.baseline or ()),
        words=words,
    )


def _region(block: AltoBlock, counter: RegionIds) -> Region:
    rid = block.id or counter.next_id()
    if isinstance(block, AltoTextBlock):
        return Region(
            id=rid,
            region_type=block.block_type or "text",
            geometry=_geometry(block.bbox, block.polygon),
            lines=tuple(_line(line) for line in block.lines),
        )
    if isinstance(block, AltoComposedBlock):
        return Region(
            id=rid,
            region_type=block.block_type or "composed",
            geometry=_geometry(block.bbox, block.polygon),
            regions=tuple(_region(child, counter) for child in block.blocks),
        )
    if isinstance(block, AltoIllustration):
        return Region(
            id=rid,
            region_type=block.block_type or "illustration",
            geometry=_geometry(block.bbox, block.polygon),
        )
    if isinstance(block, AltoGraphicalElement):
        return Region(
            id=rid,
            region_type="graphical",
            geometry=_geometry(block.bbox, block.polygon),
        )
    # Union fermée (discriminée par ``kind``) : aucune autre branche possible.
    raise AssertionError(f"bloc ALTO non géré : {block!r}")  # pragma: no cover


def _page(page: AltoPage, counter: RegionIds) -> LayoutPage:
    regions = tuple(_region(block, counter) for block in page.blocks)
    return LayoutPage(
        width=page.width,
        height=page.height,
        regions=regions,
        reading_order=tuple(region.id for region in regions),
    )


def _unit(document: AltoDocument) -> CoordinateUnit:
    unit = document.measurement_unit
    if unit is None:
        return "pixel"
    if unit not in _UNITS:
        logger.warning("[alto] unité de mesure %r inconnue, lue comme pixel", unit)
        return "pixel"
    return unit  # type: ignore[return-value]  # membre de CoordinateUnit, vérifié


def alto_to_layout(document: AltoDocument) -> CanonicalLayout:
    """Projette un ``AltoDocument`` parsé vers le ``CanonicalLayout`` neutre."""
    counter = RegionIds()
    return CanonicalLayout(
        pages=tuple(_page(page, counter) for page in document.pages),
        coordinate_unit=_unit(document),
    )


# --- assemblage inverse : CanonicalLayout → AltoDocument --------------------


def _alto_bbox(geometry: Geometry | None) -> AltoBBox | None:
    if geometry is None or geometry.bbox is None:
        return None
    b = geometry.bbox
    return AltoBBox(hpos=b.x, vpos=b.y, width=b.width, height=b.height)


def _alto_polygon(geometry: Geometry | None) -> tuple[Point, ...] | None:
    if geometry is None or not geometry.polygon:
        return None
    return geometry.polygon


def _alto_strings(line: Line) -> tuple[AltoString, ...]:
    """Mots → ``<String>``. Sans mots, le texte est segmenté sur les blancs."""
    if line.words:
        return tuple(
            AltoString(
                content=word.text,
                bbox=_alto_bbox(word.geometry),
                confidence=word.confidence,
                subs_type=word.subs_type,
                subs_content=word.subs_content,
            )
            for word in line.words
        )
    return tuple(AltoString(content=token) for token in line.text.split())


def _alto_line(line: Line) -> AltoLine:
    return AltoLine(
        id=line.id,
        bbox=_alto_bbox(line.geometry),
        polygon=_alto_polygon(line.geometry),
        baseline=tuple(line.baseline) or None,
        strings=_alto_strings(line),
        # Le texte dit où sont les blancs et la marque de coupure ; sans lui
        # l'écrivain ne peut que deviner.
        text=line.text,
    )


def _declared(region_type: str | None, default: str) -> str | None:
    """Le type à écrire : aucun si c'est celui que la lecture prête par défaut.

    ``alto_to_layout`` nomme ``text`` un ``TextBlock`` sans type ; le réécrire
    ferait dire à l'ALTO assemblé ce que la source ne disait pas.
    """
    return None if region_type == default else region_type


def _alto_block(region: Region) -> AltoBlock:
    bbox = _alto_bbox(region.geometry)
    polygon = _alto_polygon(region.geometry)
    if region.regions:
        return AltoComposedBlock(
            id=region.id,
            block_type=_declared(region.region_type, "composed"),
            bbox=bbox,
            polygon=polygon,
            blocks=tuple(_alto_block(child) for child in region.regions),
        )
    if region.region_type in _NON_TEXT_TYPES and not region.lines:
        return AltoIllustration(
            id=region.id,
            block_type=_declared(region.region_type, "illustration"),
            bbox=bbox,
            polygon=polygon,
        )
    return AltoTextBlock(
        id=region.id,
        block_type=_declared(region.region_type, "text"),
        bbox=bbox,
        polygon=polygon,
        lines=tuple(_alto_line(line) for line in region.lines),
    )


def _ordered_regions(page: LayoutPage) -> tuple[Region, ...]:
    """Régions dans l'ordre de lecture (sinon ordre des régions)."""
    if not page.reading_order:
        return page.regions
    by_id = {region.id: region for region in page.regions}
    ordered = [by_id[rid] for rid in page.reading_order if rid in by_id]
    ordered.extend(r for r in page.regions if r.id not in set(page.reading_order))
    return tuple(ordered)


def _alto_page(page: LayoutPage) -> AltoPage:
    return AltoPage(
        width=page.width,
        height=page.height,
        blocks=tuple(_alto_block(region) for region in _ordered_regions(page)),
    )


def layout_to_alto(layout: CanonicalLayout) -> AltoDocument:
    """Assemble un ``CanonicalLayout`` (rempli) en ``AltoDocument`` sérialisable."""
    return AltoDocument(
        pages=tuple(_alto_page(page) for page in layout.pages),
        measurement_unit=layout.coordinate_unit,
    )


__all__ = ["alto_to_layout", "layout_to_alto"]
