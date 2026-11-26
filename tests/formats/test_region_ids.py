"""Les ``id`` de région synthétisés : une règle, une implémentation (S29a).

``alto.layout_map`` et ``pagexml.layout_map`` tenaient chacun un ``_Counter``
identique : deux copies d'une règle d'identité, qui pouvaient diverger sans
qu'aucun test ne le voie — la même page, lue en ALTO puis en PAGE, n'aurait
plus nommé ses régions de la même façon.
"""

from __future__ import annotations

import ast
from pathlib import Path

from cinoc.formats import parse_alto, parse_pagexml
from cinoc.formats.alto.layout_map import alto_to_layout
from cinoc.formats.pagexml.layout_map import page_to_layout

CINOC = Path(__file__).resolve().parents[2] / "cinoc"

_ALTO = b"""<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>
<Page ID="p1" WIDTH="100" HEIGHT="100"><PrintSpace>
<TextBlock><TextLine><String CONTENT="a"/></TextLine></TextBlock>
<TextBlock><TextLine><String CONTENT="b"/></TextLine></TextBlock>
</PrintSpace></Page></Layout></alto>"""

_COORDS = '<Coords points="0,0 9,0 9,9"/>'
_PAGE = f"""<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
<Page imageFilename="x.png" imageWidth="100" imageHeight="100">
<TextRegion>{_COORDS}<TextLine>{_COORDS}<TextEquiv><Unicode>a</Unicode></TextEquiv>
</TextLine></TextRegion>
<TextRegion>{_COORDS}<TextLine>{_COORDS}<TextEquiv><Unicode>b</Unicode></TextEquiv>
</TextLine></TextRegion></Page></PcGts>""".encode()


def test_anonymous_regions_get_the_same_ids_from_alto_and_page() -> None:
    alto = alto_to_layout(parse_alto(_ALTO))
    page = page_to_layout(parse_pagexml(_PAGE))
    expected = ["region_0", "region_1"]
    assert [r.id for r in alto.pages[0].regions] == expected
    assert [r.id for r in page.pages[0].regions] == expected


def test_one_implementation_of_the_rule() -> None:
    """Verrou : un seul module de ``cinoc/`` définit un ``next_id``."""
    owners = sorted(
        path.relative_to(CINOC).as_posix()
        for path in CINOC.rglob("*.py")
        if "__pycache__" not in path.parts
        and any(
            isinstance(node, ast.FunctionDef) and node.name == "next_id"
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )
    )
    assert owners == ["formats/_region_ids.py"]
