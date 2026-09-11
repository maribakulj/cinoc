"""Mapper ``PageDocument → CanonicalLayout`` — pont format PAGE ↔ modèle neutre.

Pendant de ``alto_to_layout`` pour PAGE XML (PRImA). Différences de convention
projetées vers le même vocabulaire neutre :

- géométrie en **polygones** (``Coords``) → ``Geometry.polygon`` (pas de bbox PAGE) ;
- niveau **ligne** sans mots (PAGE n'a pas de ``<String>``) → ``Line.text`` direct,
  ``Line.words = ()`` ;
- **ordre de lecture en arbre** (``ReadingOrder``) → liste plate via ``flatten()`` ;
- régions non-texte (``ImageRegion``…) → ``Region`` sans lignes, ``region_type``
  reprenant le label PRImA.

Les ``id`` de région absents sont synthétisés (``region_<n>``) comme côté ALTO.
"""

from __future__ import annotations

from cinoc.domain.layout import (
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Line,
    Region,
)
from cinoc.formats._geometry import Point
from cinoc.formats.pagexml.types import (
    PageDocument,
    PageGenericRegion,
    PagePage,
    PageRegion,
    PageTextLine,
    PageTextRegion,
    ReadingOrderGroup,
    ReadingOrderRef,
)


class _Counter:
    """Compteur déterministe pour les ``id`` de région manquants."""

    def __init__(self) -> None:
        self._n = 0

    def next_id(self) -> str:
        rid = f"region_{self._n}"
        self._n += 1
        return rid


def _geometry(coords: tuple[Point, ...] | None) -> Geometry | None:
    if not coords:
        return None
    return Geometry(polygon=coords)


def _line(line: PageTextLine) -> Line:
    return Line(
        id=line.id,
        text=line.text,
        geometry=_geometry(line.coords),
        baseline=tuple(line.baseline or ()),
        confidence=line.confidence,
    )


def _region(region: PageRegion, counter: _Counter) -> Region:
    rid = region.id or counter.next_id()
    if isinstance(region, PageTextRegion):
        return Region(
            id=rid,
            region_type=region.region_type or "text",
            geometry=_geometry(region.coords),
            lines=tuple(_line(line) for line in region.text_lines),
            regions=tuple(_region(child, counter) for child in region.regions),
        )
    if isinstance(region, PageGenericRegion):
        return Region(
            id=rid,
            region_type=region.region_type or region.region_name,
            geometry=_geometry(region.coords),
            regions=tuple(_region(child, counter) for child in region.regions),
        )
    raise AssertionError(f"région PAGE non gérée : {region!r}")  # pragma: no cover


def _page(page: PagePage, counter: _Counter) -> LayoutPage:
    regions = tuple(_region(region, counter) for region in page.regions)
    if page.reading_order is not None:
        reading_order = page.reading_order.flatten()
    else:
        reading_order = tuple(region.id for region in regions)
    return LayoutPage(
        width=page.image_width,
        height=page.image_height,
        regions=regions,
        reading_order=reading_order,
    )


def page_to_layout(document: PageDocument) -> CanonicalLayout:
    """Projette un ``PageDocument`` parsé vers le ``CanonicalLayout`` neutre."""
    counter = _Counter()
    return CanonicalLayout(
        pages=tuple(_page(page, counter) for page in document.pages)
    )


__all__ = ["layout_to_page", "page_to_layout"]


def _points_from_bbox(geometry: Geometry | None) -> tuple[Point, ...] | None:
    """Polygone d'une région : le polygone natif s'il existe, sinon la boîte.

    PAGE décrit des régions par un **polygone**, pas par un rectangle. Quand la
    mise en page neutre ne porte qu'une boîte — c'est le cas d'un ALTO, qui n'a
    que des rectangles — on la rend en ses quatre coins plutôt que de laisser la
    région sans coordonnées : un PAGE sans ``Coords`` n'est pas ré-importable.
    """
    if geometry is None:
        return None
    if geometry.polygon:
        return tuple(geometry.polygon)
    boite = geometry.bbox
    if boite is None:
        return None
    droite, bas = boite.x + boite.width, boite.y + boite.height
    return (
        (boite.x, boite.y),
        (droite, boite.y),
        (droite, bas),
        (boite.x, bas),
    )


def _page_line(line: Line) -> PageTextLine:
    return PageTextLine(
        id=line.id,
        coords=_points_from_bbox(line.geometry),
        baseline=tuple(line.baseline) if line.baseline else None,
        text=line.text,
        confidence=line.confidence,
    )


def _page_region(region: Region) -> PageTextRegion:
    return PageTextRegion(
        id=region.id,
        region_type=region.region_type,
        coords=_points_from_bbox(region.geometry),
        text_lines=tuple(_page_line(line) for line in region.lines),
        regions=tuple(_page_region(sous) for sous in region.regions),
    )


def _page_reading_order(page: LayoutPage) -> ReadingOrderGroup | None:
    """Ordre de lecture PAGE, s'il y en a un à écrire.

    PAGE le porte explicitement, contrairement à ALTO où il n'est qu'implicite
    dans l'ordre des blocs. C'est l'une des raisons de tenir ce format : un
    ordre corrigé à la main survit à l'export.
    """
    if not page.reading_order:
        return None
    return ReadingOrderGroup(
        ordered=True,
        children=tuple(ReadingOrderRef(region_ref=rid) for rid in page.reading_order),
    )


def _page_page(page: LayoutPage) -> PagePage:
    return PagePage(
        image_width=page.width,
        image_height=page.height,
        reading_order=_page_reading_order(page),
        regions=tuple(_page_region(region) for region in page.regions),
    )


def layout_to_page(layout: CanonicalLayout) -> PageDocument:
    """Assemble un ``CanonicalLayout`` en ``PageDocument`` sérialisable.

    Inverse de :func:`page_to_layout`. Les régions gardent leur **ordre
    déclaré** — contrairement à l'assemblage ALTO, qui les réordonne parce que
    ce format n'a pas d'autre façon d'exprimer la lecture ; ici l'ordre est
    écrit à part, donc le déplacer serait le dire deux fois.
    """
    return PageDocument(pages=tuple(_page_page(page) for page in layout.pages))
