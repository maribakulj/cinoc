"""``layout_to_page`` : l'aller-retour, et ce que PAGE sait dire qu'ALTO ne sait pas.

Le parseur PAGE existait depuis le début, `page_to_layout` aussi — mais rien
n'écrivait dans l'autre sens, et le type `page_xml` restait mort. Ce qui est
vérifié ici est l'aller-retour complet : ce qu'on exporte doit se relire à
l'identique, sans quoi l'export n'est pas un format d'archive mais un affichage.
"""

from __future__ import annotations

from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Line,
    Region,
)
from cinoc.formats.pagexml.layout_map import layout_to_page, page_to_layout
from cinoc.formats.pagexml.parser import parse_pagexml
from cinoc.formats.pagexml.writer import write_pagexml


def _layout(reading_order: tuple[str, ...] = ()) -> CanonicalLayout:
    return CanonicalLayout(
        pages=(
            LayoutPage(
                width=600,
                height=400,
                regions=(
                    Region(
                        id="R1",
                        region_type="paragraph",
                        geometry=Geometry(bbox=BBox(x=10, y=10, width=300, height=80)),
                        lines=(Line(id="L1", text="le soleil luisoit"),),
                    ),
                    Region(
                        id="R2",
                        region_type="paragraph",
                        geometry=Geometry(
                            bbox=BBox(x=320, y=10, width=260, height=80)
                        ),
                        lines=(Line(id="L2", text="sur la ville"),),
                    ),
                ),
                reading_order=reading_order,
            ),
        )
    )


def _aller_retour(layout: CanonicalLayout) -> CanonicalLayout:
    return page_to_layout(parse_pagexml(write_pagexml(layout_to_page(layout))))


def test_the_round_trip_preserves_text_and_identity() -> None:
    relu = _aller_retour(_layout())
    page = relu.pages[0]
    assert [r.id for r in page.regions] == ["R1", "R2"]
    assert [ligne.text for r in page.regions for ligne in r.lines] == [
        "le soleil luisoit",
        "sur la ville",
    ]
    assert [ligne.id for r in page.regions for ligne in r.lines] == ["L1", "L2"]


def test_the_round_trip_preserves_the_page_size() -> None:
    page = _aller_retour(_layout()).pages[0]
    assert (page.width, page.height) == (600, 400)


def test_a_corrected_reading_order_survives_the_export() -> None:
    """Ce que PAGE sait dire et qu'ALTO ne sait pas.

    En ALTO, l'ordre n'est qu'implicite dans la suite des blocs : un ordre
    corrigé ne survit qu'en réarrangeant le document. PAGE le porte à part —
    c'est la raison de tenir ce format, et pas seulement un second export.
    """
    page = _aller_retour(_layout(reading_order=("R2", "R1"))).pages[0]
    assert page.reading_order == ("R2", "R1")
    # Les régions, elles, n'ont pas bougé : l'ordre est dit, pas joué.
    assert [r.id for r in page.regions] == ["R1", "R2"]


def test_a_bbox_becomes_a_polygon() -> None:
    """PAGE décrit des polygones. Une région sans coordonnées n'est pas
    ré-importable : une boîte est donc rendue en ses quatre coins."""
    document = layout_to_page(_layout())
    region = document.pages[0].regions[0]
    assert region.coords == ((10, 10), (310, 10), (310, 90), (10, 90))


def test_a_region_without_geometry_has_no_coords() -> None:
    """On ne fabrique pas une géométrie qu'on n'a pas."""
    nu = CanonicalLayout(
        pages=(LayoutPage(regions=(Region(id="R1", region_type="text"),)),)
    )
    assert layout_to_page(nu).pages[0].regions[0].coords is None


def test_the_export_is_deterministic() -> None:
    """Deux exports du même layout donnent les mêmes octets — invariant du banc."""
    layout = _layout(reading_order=("R2", "R1"))
    assert write_pagexml(layout_to_page(layout)) == write_pagexml(
        layout_to_page(layout)
    )
