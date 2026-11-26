"""Tests sur fixtures réalistes (sorties Tesseract / Gallica / Transkribus /
eScriptorium) : tolérance aux quirks réels + idempotence-modèle sur entrée réelle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.formats.alto import (
    AltoComposedBlock,
    AltoDocument,
    AltoIllustration,
    AltoTextBlock,
    parse_alto,
    write_alto,
)
from cinoc.formats.pagexml import (
    PAGE_NS,
    PageDocument,
    PageTextRegion,
    parse_pagexml,
    write_pagexml,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


# --- ALTO : Tesseract (v3) ---------------------------------------------------


def test_tesseract_alto_tolerates_metadata_and_extracts_text() -> None:
    doc = parse_alto(_read("tesseract.alto.xml"))
    assert doc.source_version == "v3"
    assert doc.measurement_unit == "pixel"  # OCRProcessing/Styles ignorés sans crash
    block = doc.pages[0].blocks[0]
    assert isinstance(block, AltoTextBlock)
    strings = block.lines[0].strings
    assert [s.content for s in strings] == ["Liberté", "égalité"]
    assert strings[0].confidence == 0.96  # WC parsé ; SP/CC/STYLEREFS ignorés


# --- ALTO : Gallica / BnF (v2, ComposedBlock + Illustration) -----------------


def test_gallica_alto_v2_composed_and_illustration() -> None:
    doc = parse_alto(_read("gallica.alto.xml"))
    assert doc.source_version == "v2"
    composed = doc.pages[0].blocks[0]
    assert isinstance(composed, AltoComposedBlock)
    assert composed.block_type == "article"
    assert isinstance(composed.blocks[0], AltoTextBlock)
    assert isinstance(composed.blocks[1], AltoIllustration)


# --- PAGE : Transkribus (2013, Metadata, Word, custom) -----------------------


def test_transkribus_page_line_level_text_wins_over_words() -> None:
    doc = parse_pagexml(_read("transkribus.page.xml"))
    assert doc.source_namespace.endswith("2013-07-15")  # type: ignore[union-attr]
    page = doc.pages[0]
    assert page.reading_order.flatten() == ("region_0",)  # type: ignore[union-attr]
    region = page.regions[0]
    assert isinstance(region, PageTextRegion)
    assert region.region_type == "paragraph"  # attribut custom ignoré
    line = region.text_lines[0]
    assert line.text == "Nostre Seigneur"  # TextEquiv de ligne, pas les Word
    assert line.confidence == 0.92
    # Les mots sont lus aussi, avec leur polygone (D-273 : ils étaient ignorés).
    assert [(w.id, w.text) for w in line.words] == [
        ("word_0", "Nostre"),
        ("word_1", "Seigneur"),
    ]
    assert line.words[1].coords == ((520, 310), (800, 310), (800, 360), (520, 360))


# --- PAGE : eScriptorium (2019, deux régions, ordre de lecture) --------------


def test_escriptorium_page_regions_and_reading_order() -> None:
    doc = parse_pagexml(_read("escriptorium.page.xml"))
    assert doc.source_namespace.endswith("2019-07-15")  # type: ignore[union-attr]
    page = doc.pages[0]
    assert page.reading_order.flatten() == ("main", "margin")  # type: ignore[union-attr]
    main = page.regions[0]
    assert isinstance(main, PageTextRegion)
    assert [line.text for line in main.text_lines] == [
        "In principio erat verbum",
        "et verbum erat apud Deum",
    ]


def test_word_level_fallback_when_no_line_text() -> None:
    """Une ligne segmentée uniquement en mots → texte reconstruit (T2)."""
    data = (
        f'<PcGts xmlns="{PAGE_NS}"><Page><TextRegion id="r"><TextLine id="l">'
        f"<Word><TextEquiv><Unicode>foo</Unicode></TextEquiv></Word>"
        f"<Word><TextEquiv><Unicode>bar</Unicode></TextEquiv></Word>"
        f"</TextLine></TextRegion></Page></PcGts>"
    ).encode()
    region = parse_pagexml(data).pages[0].regions[0]
    assert isinstance(region, PageTextRegion)
    assert region.text_lines[0].text == "foo bar"


# --- idempotence-modèle sur entrée réelle ------------------------------------


@pytest.mark.parametrize("name", ["tesseract.alto.xml", "gallica.alto.xml"])
def test_alto_model_idempotent_on_real_input(name: str) -> None:
    doc = parse_alto(_read(name))
    assert isinstance(doc, AltoDocument)
    # L'écrivain cible ALTO 4 : seule la version déclarée change.
    expected = doc.model_copy(update={"source_version": "v4"})
    assert parse_alto(write_alto(doc)) == expected


@pytest.mark.parametrize("name", ["transkribus.page.xml", "escriptorium.page.xml"])
def test_page_model_idempotent_on_real_input(name: str) -> None:
    doc = parse_pagexml(_read(name))
    assert isinstance(doc, PageDocument)
    # L'écrivain cible PAGE 2019 : seul l'espace de noms déclaré change.
    expected = doc.model_copy(update={"source_namespace": PAGE_NS})
    assert parse_pagexml(write_pagexml(doc)) == expected
