"""Tests de bord ALTO : tolérances du parser et variantes du writer."""

from __future__ import annotations

from cinoc.formats.alto import (
    AltoDocument,
    AltoGraphicalElement,
    AltoPage,
    AltoTextBlock,
    parse_alto,
    write_alto,
)

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'


def test_unknown_namespace_gives_none_version() -> None:
    data = b'<alto xmlns="http://example.org/other"><Layout><Page/></Layout></alto>'
    assert parse_alto(data).source_version is None


def test_non_numeric_bbox_is_tolerated() -> None:
    data = (
        f"<alto {_NS}><Layout><Page><PrintSpace>"
        f'<TextBlock HPOS="abc" VPOS="0" WIDTH="10" HEIGHT="10"/>'
        f"</PrintSpace></Page></Layout></alto>"
    ).encode()
    block = parse_alto(data).pages[0].blocks[0]
    assert isinstance(block, AltoTextBlock)
    assert block.bbox is None


def test_malformed_polygon_is_dropped() -> None:
    data = (
        f"<alto {_NS}><Layout><Page><PrintSpace><TextBlock><TextLine>"
        f'<Shape><Polygon POINTS="garbage"/></Shape><String CONTENT="x"/>'
        f"</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
    ).encode()
    block = parse_alto(data).pages[0].blocks[0]
    assert isinstance(block, AltoTextBlock)
    assert block.lines[0].polygon is None


def test_graphical_element_parsed() -> None:
    data = (
        f"<alto {_NS}><Layout><Page><PrintSpace>"
        f'<GraphicalElement ID="g1" HPOS="0" VPOS="0" WIDTH="5" HEIGHT="5"/>'
        f"</PrintSpace></Page></Layout></alto>"
    ).encode()
    element = parse_alto(data).pages[0].blocks[0]
    assert isinstance(element, AltoGraphicalElement)
    assert element.id == "g1"


def test_blocks_without_printspace_are_read() -> None:
    data = (
        f"<alto {_NS}><Layout><Page>"
        f'<TextBlock ID="b1"><TextLine><String CONTENT="hi"/></TextLine></TextBlock>'
        f"</Page></Layout></alto>"
    ).encode()
    block = parse_alto(data).pages[0].blocks[0]
    assert isinstance(block, AltoTextBlock)
    assert block.id == "b1"


def test_writer_always_writes_alto_4() -> None:
    """Un document lu en v2 ou sans namespace ressort en ALTO 4 (seule cible)."""
    for version in ("v2", "none"):
        doc = AltoDocument(pages=(AltoPage(id="p"),), source_version=version)
        assert parse_alto(write_alto(doc)).source_version == "v4"
