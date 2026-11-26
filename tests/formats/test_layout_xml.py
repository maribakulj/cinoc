"""Une seule reconnaissance ALTO/PAGE → ``CanonicalLayout`` (P5g 6, D-303).

Trois copies vivaient en couches 3, 5 et 6 ; ``formats/layout_xml.py`` est la
seule, et un verrou interdit qu'une quatrième renaisse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.domain.errors import FormatError
from cinoc.formats.alto import AltoDocument, AltoPage, write_alto
from cinoc.formats.layout_xml import layout_xml_kind, parse_layout_xml

ROOT = Path(__file__).resolve().parents[2]
ALTO = (
    ROOT / "tests/fixtures/reference_corpus/bnl_waeschfra/waeschfra_p2_excerpt.alto.xml"
)


def test_an_alto_is_read_as_alto() -> None:
    data = ALTO.read_bytes()
    assert layout_xml_kind(data) == "ALTO"
    assert any(page.regions for page in parse_layout_xml(data).pages)


def test_a_page_is_recognised_by_its_root_not_its_name() -> None:
    data = b'<?xml version="1.0"?><PcGts xmlns="x"><Page/></PcGts>'
    assert layout_xml_kind(data) == "PAGE"
    assert parse_layout_xml(data).pages  # lu par le lecteur PAGE, pas l'ALTO


def test_an_unreadable_xml_raises() -> None:
    with pytest.raises((ValueError, FormatError)):
        parse_layout_xml(b"<alto")


def test_no_other_copy_of_the_sniffing() -> None:
    """Verrou : la reconnaissance au contenu (``pcgts`` en tête) ne vit qu'ici."""
    copies = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "cinoc").rglob("*.py")
        if "__pycache__" not in p.parts
        and p.name != "layout_xml.py"
        and b'b"pcgts"' in p.read_bytes()
    ]
    assert not copies, copies


def test_round_trip_through_the_writer() -> None:
    document = AltoDocument(pages=(AltoPage(id="p1", width=10, height=10),))
    assert layout_xml_kind(write_alto(document)) == "ALTO"
