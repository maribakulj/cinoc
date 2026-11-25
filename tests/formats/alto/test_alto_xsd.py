"""Ce que Cinoc **écrit** en ALTO est conforme au XSD officiel (P5d 7a, A9).

L9 de ``MIGRATION_COUCHE_2.md`` disait la sortie « conforme par construction »,
garantie par l'aller-retour. Un aller-retour prouve la fidélité à soi-même, pas
la conformité : l'audit du 2026-11-25 a trouvé 0 ALTO écrit sur 21 valide
(D-264). L'oracle est donc externe — ALTO 4.4 de loc.gov, vendorisé, chargé
sans réseau (``tests/formats/_xsd.py``).

Deux écrivains, tous deux couverts sur **chaque** ALTO du dépôt :

- ``write_alto`` sur un document lu (``parse_alto → write_alto``) ;
- le chemin de l'``AltoAssembler`` (``ALTO → CanonicalLayout → ALTO``).

L'entrée, elle, reste tolérante : la vérité terrain réelle n'est pas toujours
conforme, et la refuser ne mesurerait rien. Aucune validation à l'exécution.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from cinoc.formats.alto import parse_alto, write_alto
from cinoc.formats.alto.layout_map import alto_to_layout, layout_to_alto
from tests.formats._xsd import alto_errors

_REPO = Path(__file__).resolve().parents[3]

#: Tout ALTO du dépôt : fixtures de test, puis corpus s'ils sont présents
#: (``corpus/`` peut quitter l'arbre public, A4 — les fixtures restent).
_SOURCES = sorted(
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
    return write_alto(parse_alto(data))


def _assemble(data: bytes) -> bytes:
    # La composition exacte d'``AltoAssembler.execute`` (hors I/O).
    return write_alto(layout_to_alto(alto_to_layout(parse_alto(data))))


_WRITERS: dict[str, Callable[[bytes], bytes]] = {
    "write_alto": _rewrite,
    "assembler": _assemble,
}


def test_sources_are_not_vacuous() -> None:
    """Vert sur zéro fichier ressemblerait exactement à vert."""
    in_tests = [p for p in _SOURCES if _rel(p).startswith("tests/")]
    assert len(in_tests) >= 6, in_tests


@pytest.mark.parametrize("writer", sorted(_WRITERS))
@pytest.mark.parametrize("source", _SOURCES, ids=_rel)
def test_written_alto_is_valid_alto_4_4(source: Path, writer: str) -> None:
    written = _WRITERS[writer](source.read_bytes())
    errors = alto_errors(written)
    assert not errors, f"{_rel(source)} via {writer} :\n" + "\n".join(errors[:10])


def test_parser_stays_tolerant_of_invalid_input() -> None:
    """A9 : on valide ce qu'on écrit, jamais ce qu'on lit."""
    excerpt = (
        _REPO
        / "tests/fixtures/reference_corpus/bnl_waeschfra/waeschfra_p2_excerpt.alto.xml"
    ).read_bytes()
    assert alto_errors(excerpt), "la fixture devait être invalide (Page sans ID)"
    doc = parse_alto(excerpt)
    assert doc.pages and doc.pages[0].blocks
