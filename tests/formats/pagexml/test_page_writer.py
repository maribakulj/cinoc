"""``write_pagexml`` : ce que le XSD exige, dérivé ou dit absent — jamais inventé.

Chaque test vérifie deux choses : la sortie passe le XSD officiel PAGE 2019
(l'oracle, ``tests/formats/_xsd.py``), et la relecture rend ce qui a été écrit —
y compris l'**absence** d'une information.
"""

from __future__ import annotations

import logging

import pytest
from lxml import etree

from cinoc.formats.pagexml import (
    PAGE_NS,
    PageDocument,
    PageGenericRegion,
    PagePage,
    PageTextLine,
    PageTextRegion,
    PageWord,
    PageWriteError,
    ReadingOrderGroup,
    ReadingOrderRef,
    parse_pagexml,
    write_pagexml,
)
from tests.formats._xsd import page_errors


def _doc(*regions: PageTextRegion | PageGenericRegion, **page: object) -> PageDocument:
    fields: dict[str, object] = {"image_width": 600, "image_height": 400}
    fields.update(page)
    return PageDocument(
        pages=(PagePage(regions=regions, **fields),),  # type: ignore[arg-type]
        source_namespace=PAGE_NS,
    )


def _box(x: int = 0) -> tuple[tuple[int, int], ...]:
    return ((x, 0), (x + 10, 0), (x + 10, 10), (x, 10))


def _written(doc: PageDocument) -> etree._Element:
    data = write_pagexml(doc)
    assert page_errors(data) == []
    return etree.fromstring(data)


def _q(local: str) -> str:
    return f"{{{PAGE_NS}}}{local}"


def test_metadata_is_written_with_fixed_dates() -> None:
    """Le XSD exige ``Metadata`` ; un horodatage réel changerait l'empreinte de
    l'artefact à chaque run (déterminisme, ``CLAUDE.md`` §12)."""
    root = _written(_doc())
    metadata = root.find(_q("Metadata"))
    assert metadata is not None
    assert [(c.tag.split("}")[1], c.text) for c in metadata] == [
        ("Creator", "Cinoc"),
        ("Created", "1970-01-01T00:00:00Z"),
        ("LastChange", "1970-01-01T00:00:00Z"),
    ]


def test_a_2013_document_is_written_in_2019() -> None:
    old = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"
    doc = _doc().model_copy(update={"source_namespace": old})
    assert etree.QName(_written(doc)).namespace == PAGE_NS


@pytest.mark.parametrize("count", [0, 2])
def test_page_count_other_than_one_is_refused(count: int) -> None:
    """``PcGts`` porte exactement une ``Page``."""
    page = PagePage(image_width=1, image_height=1)
    with pytest.raises(PageWriteError, match="une page par fichier"):
        write_pagexml(PageDocument(pages=(page,) * count))


def test_unknown_page_size_is_refused() -> None:
    """``0`` serait une mesure fausse, pas une absence."""
    with pytest.raises(PageWriteError, match="dimensions"):
        write_pagexml(_doc(image_width=None))


def test_unknown_image_name_is_an_empty_name() -> None:
    root = _written(_doc())
    page = root.find(_q("Page"))
    assert page is not None and page.get("imageFilename") == ""
    assert parse_pagexml(etree.tostring(root)).pages[0].image_filename is None


def test_missing_geometry_is_marked_not_invented() -> None:
    """PAGE exige des coordonnées partout. Faute de les connaître, un polygone
    nul **marqué** : il ne couvre rien, et la relecture rend ``None``."""
    line = PageTextLine(id="l1", text="sans géométrie")
    region = PageTextRegion(id="r1", text_lines=(line,))
    doc = _doc(region)
    root = _written(doc)
    for tag in ("TextRegion", "TextLine"):
        el = root.find(f".//{_q(tag)}")
        assert el is not None and el.get("custom") == "coords {absent:true;}"
        coords = el.find(_q("Coords"))
        assert coords is not None and coords.get("points") == "0,0 0,0"
    assert parse_pagexml(write_pagexml(doc)) == doc


def test_a_type_outside_the_enumeration_goes_to_custom() -> None:
    """``TextRegion@type`` est énuméré ; un type libre passe dans
    ``structure {type:…;}`` (Transkribus, eScriptorium) et en revient."""
    regions = (
        PageTextRegion(id="r1", region_type="paragraph", coords=_box()),
        PageTextRegion(id="r2", region_type="text+gapfill", coords=_box(20)),
        PageTextRegion(id="r3", region_type="a;b{c}d\\e", coords=_box(40)),
        PageGenericRegion(
            region_name="ImageRegion", id="i1", region_type="photo", coords=_box(60)
        ),
        PageGenericRegion(
            region_name="GraphicRegion", id="g1", region_type="stamp", coords=_box(80)
        ),
    )
    doc = _doc(*regions)
    root = _written(doc)
    by_id = {el.get("id"): el for el in root.iter() if el.get("id")}
    assert by_id["r1"].get("type") == "paragraph"
    assert by_id["r1"].get("custom") is None
    assert by_id["r2"].get("type") is None
    assert by_id["r2"].get("custom") == "structure {type:text+gapfill;}"
    assert by_id["i1"].get("custom") == "structure {type:photo;}"
    assert by_id["g1"].get("type") == "stamp"
    assert parse_pagexml(write_pagexml(doc)) == doc


def test_non_text_regions_keep_their_element() -> None:
    separator = PageGenericRegion(region_name="SeparatorRegion", id="s", coords=_box())
    root = _written(_doc(separator))
    assert root.find(f".//{_q('SeparatorRegion')}") is not None
    assert root.find(f".//{_q('TextRegion')}") is None


def test_unknown_region_element_is_refused() -> None:
    bizarre = PageGenericRegion(region_name="FooRegion", id="f", coords=_box())
    with pytest.raises(PageWriteError, match="FooRegion"):
        write_pagexml(_doc(bizarre))


def test_sub_regions_come_before_lines() -> None:
    """Le XSD place les sous-régions (``RegionType``) avant les lignes."""
    inner = PageGenericRegion(region_name="SeparatorRegion", id="s", coords=_box())
    line = PageTextLine(id="l", coords=_box(), text="x")
    outer = PageTextRegion(id="r", coords=_box(), text_lines=(line,), regions=(inner,))
    region = _written(_doc(outer)).find(f".//{_q('TextRegion')}")
    assert region is not None
    assert [c.tag.split("}")[1] for c in region] == [
        "Coords", "SeparatorRegion", "TextLine"
    ]


def test_ids_are_derived_and_references_follow(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``xsd:ID`` : présent, unique, ``NCName``. Un identifiant qui ne l'est
    pas est remplacé (et dit), et l'ordre de lecture suit le renommage ; une
    référence qui ne mène nulle part est retirée (``IDREF``)."""
    regions = (
        PageTextRegion(id="r:1", coords=_box()),
        PageTextRegion(id="r2", coords=_box(20)),
        PageTextRegion(id="r2", coords=_box(40)),
        PageTextRegion(coords=_box(60), text_lines=(PageTextLine(text="x"),)),
    )
    order = ReadingOrderGroup(
        children=(
            ReadingOrderRef(region_ref="r:1"),
            ReadingOrderRef(region_ref="fantome"),
            ReadingOrderGroup(
                ordered=False, children=(ReadingOrderRef(region_ref="x"),)
            ),
            ReadingOrderRef(region_ref="r2"),
        )
    )
    with caplog.at_level(logging.WARNING):
        root = _written(_doc(*regions, reading_order=order))
    ids = [el.get("id") for el in root.iter(_q("TextRegion"))]
    assert ids == ["region_1", "r2", "region_2", "region_3"]
    group = root.find(f".//{_q('OrderedGroup')}")
    assert group is not None and group.get("id") == "ro_1"
    refs = [(r.get("index"), r.get("regionRef")) for r in group]
    assert refs == [("0", "region_1"), ("1", "r2")]
    assert "'r:1'" in caplog.text and "fantome" in caplog.text


def test_out_of_schema_values_are_brought_back(
    caplog: pytest.LogCaptureFixture,
) -> None:
    line = PageTextLine(
        id="l", coords=((-5, 2), (10, 2), (10, 9)), baseline=((1, 1),),
        text="x", confidence=87.0,
    )
    with caplog.at_level(logging.WARNING):
        root = _written(_doc(PageTextRegion(id="r", coords=_box(), text_lines=(line,))))
    el = root.find(f".//{_q('TextLine')}")
    assert el is not None
    coords = el.find(_q("Coords"))
    assert coords is not None and coords.get("points") == "0,2 10,2 10,9"
    assert el.find(_q("Baseline")) is None
    text_equiv = el.find(_q("TextEquiv"))
    assert text_equiv is not None and text_equiv.get("conf") is None
    assert "négatives" in caplog.text and "87.0" in caplog.text


def test_words_round_trip() -> None:
    """Les mots portent position et confiance ; ils étaient ignorés (D-264)."""
    words = (
        PageWord(id="w1", coords=_box(), text="Nostre", confidence=0.5),
        PageWord(id="w2", coords=_box(20), text="Seigneur"),
        PageWord(id="w3", text="sans-boite"),
    )
    line = PageTextLine(id="l", coords=_box(), words=words, text="Nostre Seigneur")
    doc = _doc(PageTextRegion(id="r", coords=_box(), text_lines=(line,)))
    _written(doc)
    assert parse_pagexml(write_pagexml(doc)) == doc


def test_missing_word_ids_are_derived() -> None:
    line = PageTextLine(id="l", coords=_box(), words=(PageWord(text="a"),), text="a")
    root = _written(_doc(PageTextRegion(id="r", coords=_box(), text_lines=(line,))))
    word = root.find(f".//{_q('Word')}")
    assert word is not None and word.get("id") == "word_1"


def test_empty_reading_order_groups_are_not_written() -> None:
    order = ReadingOrderGroup(children=(ReadingOrderRef(region_ref="absente"),))
    root = _written(_doc(PageTextRegion(id="r", coords=_box()), reading_order=order))
    assert root.find(f".//{_q('ReadingOrder')}") is None
