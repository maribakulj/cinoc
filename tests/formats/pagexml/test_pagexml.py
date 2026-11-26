"""Tests du format PAGE : parsing, round-trip C14N, ordre de lecture, sécurité."""

from __future__ import annotations

import pytest

from cinoc.formats.pagexml import (
    PAGE_NS,
    PageDocument,
    PageGenericRegion,
    PagePage,
    PageParseError,
    PageTextLine,
    PageTextRegion,
    ReadingOrderGroup,
    ReadingOrderRef,
    parse_pagexml,
    write_pagexml,
)

_NS = f'xmlns="{PAGE_NS}"'

_PAGE = (
    f'<PcGts {_NS}><Page imageFilename="p.jpg" imageWidth="200" imageHeight="300">'
    f'<TextRegion id="r1" type="paragraph">'
    f'<Coords points="0,0 100,0 100,30"/>'
    f'<TextLine id="l1"><Coords points="0,0 100,0 100,30"/>'
    f'<Baseline points="0,25 100,25"/>'
    f'<TextEquiv index="1"><Unicode>variante</Unicode></TextEquiv>'
    f'<TextEquiv index="0" conf="0.95"><Unicode>Bonjour</Unicode></TextEquiv>'
    f"</TextLine></TextRegion>"
    f'<ImageRegion id="img1"><Coords points="0,50 50,50 50,100"/></ImageRegion>'
    f"</Page></PcGts>"
).encode()


def _rich_doc() -> PageDocument:
    line = PageTextLine(
        id="l1",
        coords=((0, 0), (100, 0), (100, 30)),
        baseline=((0, 25), (100, 25)),
        text="Bonjour",
        confidence=0.95,
    )
    separator = PageGenericRegion(
        region_name="SeparatorRegion", id="sep1", coords=((0, 40), (100, 40), (100, 42))
    )
    text_region = PageTextRegion(
        id="r1",
        region_type="paragraph",
        coords=((0, 0), (100, 0), (100, 30)),
        text_lines=(line,),
        regions=(separator,),
    )
    image = PageGenericRegion(
        region_name="ImageRegion", id="img1", region_type="photo",
        coords=((0, 50), (50, 50), (50, 100)),
    )
    reading_order = ReadingOrderGroup(
        id="g1",
        ordered=True,
        children=(
            ReadingOrderRef(region_ref="r1"),
            ReadingOrderGroup(
                id="g2", ordered=False, children=(ReadingOrderRef(region_ref="img1"),)
            ),
        ),
    )
    page = PagePage(
        image_filename="p.jpg",
        image_width=200,
        image_height=300,
        reading_order=reading_order,
        regions=(text_region, image),
    )
    return PageDocument(pages=(page,), source_namespace=PAGE_NS)


# --- parsing -----------------------------------------------------------------


def test_parse_namespace_and_page() -> None:
    doc = parse_pagexml(_PAGE)
    assert doc.source_namespace == PAGE_NS
    page = doc.pages[0]
    assert page.image_filename == "p.jpg"
    assert page.image_width == 200 and page.image_height == 300


def test_parse_text_region_and_line() -> None:
    region = parse_pagexml(_PAGE).pages[0].regions[0]
    assert isinstance(region, PageTextRegion)
    assert region.region_type == "paragraph"
    assert region.coords == ((0, 0), (100, 0), (100, 30))
    line = region.text_lines[0]
    assert line.baseline == ((0, 25), (100, 25))


def test_textequiv_lowest_index_wins() -> None:
    """index=0 (``Bonjour``, conf 0.95) doit primer sur index=1 (``variante``)."""
    line = parse_pagexml(_PAGE).pages[0].regions[0]
    assert isinstance(line, PageTextRegion)
    assert line.text_lines[0].text == "Bonjour"
    assert line.text_lines[0].confidence == 0.95


def test_parse_generic_region() -> None:
    image = parse_pagexml(_PAGE).pages[0].regions[1]
    assert isinstance(image, PageGenericRegion)
    assert image.region_name == "ImageRegion"
    assert image.id == "img1"


# --- ordre de lecture --------------------------------------------------------


def test_reading_order_flatten() -> None:
    assert _rich_doc().pages[0].reading_order.flatten() == ("r1", "img1")  # type: ignore[union-attr]


# --- round-trip & déterminisme ----------------------------------------------


def test_roundtrip_preserves_model() -> None:
    doc = _rich_doc()
    assert parse_pagexml(write_pagexml(doc)) == doc


def test_writer_is_deterministic() -> None:
    doc = _rich_doc()
    assert write_pagexml(doc) == write_pagexml(doc)


def test_roundtrip_empty_text_line() -> None:
    line = PageTextLine(id="l", text="")
    region = PageTextRegion(id="r", text_lines=(line,))
    doc = PageDocument(
        pages=(PagePage(image_width=10, image_height=10, regions=(region,)),),
        source_namespace=PAGE_NS,
    )
    assert parse_pagexml(write_pagexml(doc)) == doc


# --- erreurs & sécurité ------------------------------------------------------


def test_malformed_raises() -> None:
    with pytest.raises(PageParseError):
        parse_pagexml(b"<PcGts><unclosed>")


def test_empty_raises() -> None:
    with pytest.raises(PageParseError):
        parse_pagexml(b"")


def test_doctype_rejected() -> None:
    data = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE PcGts [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        f"<PcGts {_NS}><Page/></PcGts>"
    ).encode()
    with pytest.raises(PageParseError):
        parse_pagexml(data)
