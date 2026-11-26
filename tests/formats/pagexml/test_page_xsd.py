"""Ce que Cinoc **écrit** en PAGE est conforme au XSD officiel (P5d 7b, A9).

Même oracle que pour ALTO (D-272) : PAGE 2019-07-15 de PRImA, vendorisé,
chargé sans réseau (``tests/formats/_xsd.py``). L'audit du 2026-11-25 avait
trouvé 0 PAGE écrit sur 11 valide (D-264).

Deux écrivains, couverts sur **chaque** fixture PAGE et ALTO du dépôt :

- ``write_pagexml`` sur un document lu (``parse_pagexml → write_pagexml``) ;
- le chemin du ``PageAssembler`` (``… → CanonicalLayout → layout_to_page →
  write_pagexml``), depuis un PAGE **et** depuis un ALTO — un ALTO lu puis
  exporté en PAGE est un chemin réel du banc.

PAGE est en pixels. Un layout dans une autre unité (``mm10`` des ALTO BNL) ne
se convertit pas sans une résolution qu'ALTO ne porte pas : il est **refusé**,
pas écrit faux.

L'entrée, elle, reste tolérante : aucune validation à l'exécution.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from cinoc.formats.alto import parse_alto
from cinoc.formats.alto.layout_map import alto_to_layout
from cinoc.formats.pagexml import PageWriteError, parse_pagexml, write_pagexml
from cinoc.formats.pagexml.layout_map import layout_to_page, page_to_layout
from tests.formats._xsd import page_errors

_REPO = Path(__file__).resolve().parents[3]

_PAGE_SOURCES = sorted(
    {
        *_REPO.glob("tests/formats/fixtures/*.page.xml"),
        *_REPO.glob("tests/fixtures/**/*.page.xml"),
    }
)

#: Tout ALTO du dépôt, comme ``test_alto_xsd`` (``corpus/`` peut quitter
#: l'arbre public, A4 — les fixtures restent).
_ALTO_SOURCES = sorted(
    {
        *_REPO.glob("tests/formats/fixtures/*.alto.xml"),
        *_REPO.glob("tests/fixtures/**/*.alto.xml"),
        *_REPO.glob("corpus/37-GT-BNL/*.xml"),
        *_REPO.glob("corpus/BnF-*/*.xml"),
    }
)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO).as_posix()


def _rewrite(data: bytes) -> bytes:
    return write_pagexml(parse_pagexml(data))


def _assemble(data: bytes) -> bytes:
    # La composition exacte de ``PageAssembler.execute`` (hors I/O).
    return write_pagexml(layout_to_page(page_to_layout(parse_pagexml(data))))


_PAGE_WRITERS: dict[str, Callable[[bytes], bytes]] = {
    "write_pagexml": _rewrite,
    "assembler": _assemble,
}


def _alto_in_pixels(path: Path) -> bool:
    return alto_to_layout(parse_alto(path.read_bytes())).coordinate_unit == "pixel"


def test_sources_are_not_vacuous() -> None:
    """Vert sur zéro fichier ressemblerait exactement à vert."""
    assert len(_PAGE_SOURCES) >= 2, _PAGE_SOURCES
    pixel = [p for p in _ALTO_SOURCES if _rel(p).startswith("tests/")]
    assert len([p for p in pixel if _alto_in_pixels(p)]) >= 5, pixel


@pytest.mark.parametrize("writer", sorted(_PAGE_WRITERS))
@pytest.mark.parametrize("source", _PAGE_SOURCES, ids=_rel)
def test_written_page_is_valid_page_2019(source: Path, writer: str) -> None:
    written = _PAGE_WRITERS[writer](source.read_bytes())
    errors = page_errors(written)
    assert not errors, f"{_rel(source)} via {writer} :\n" + "\n".join(errors[:10])


@pytest.mark.parametrize("source", _ALTO_SOURCES, ids=_rel)
def test_alto_exported_to_page_is_valid_or_refused(source: Path) -> None:
    """Un ALTO en pixels sort en PAGE valide ; dans une autre unité, refusé."""
    layout = alto_to_layout(parse_alto(source.read_bytes()))
    if layout.coordinate_unit != "pixel":
        with pytest.raises(PageWriteError, match="pixel"):
            write_pagexml(layout_to_page(layout))
        return
    errors = page_errors(write_pagexml(layout_to_page(layout)))
    assert not errors, f"{_rel(source)} :\n" + "\n".join(errors[:10])


def test_parser_stays_tolerant_of_invalid_input() -> None:
    """A9 : on valide ce qu'on écrit, jamais ce qu'on lit."""
    source = (_REPO / "tests/formats/fixtures/escriptorium.page.xml").read_bytes()
    assert page_errors(source), "la fixture devait être invalide (type « text »)"
    assert parse_pagexml(source).pages[0].regions
