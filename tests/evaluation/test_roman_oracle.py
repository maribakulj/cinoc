"""Oracle **``roman``** (PyPI, 5.2) pour la validation des numéraux de
``cinoc/evaluation/roman.py`` (D-287 ; P5e 10, D-290).

Le paquet ``roman`` (Mark Pilgrim, *Dive Into Python* ; ZPL 2.1) est la
grammaire canonique : ``M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})``,
de 1 à 4 999. Celle de Cinoc est la même où chaque ``{0,3}`` devient ``{0,4}``,
pour garder l'additif médiéval (D-121). Ce que ces tests établissent, en
**exécutant** ``roman.fromRoman`` :

- les **4 999 formes canoniques** (``roman.toRoman(1…4999)``) : même valeur,
  majuscules et minuscules ;
- les **137 256 chaînes de 1 à 6 lettres** sur ``IVXLCDM`` : 1 339 acceptées par
  les deux, à la même valeur ; **87 acceptées par Cinoc seul**, toutes
  additives (un chiffre écrit ``IIII``, ``XXXX`` ou ``CCCC`` : ``IIII``,
  ``VIIII``, ``XXXXIIII``…) et chacune de la valeur de sa forme canonique ;
  **aucune** acceptée par ``roman`` seul — Cinoc n'est pas plus strict ;
- écarts voulus, un par un : l'additif médiéval (ci-dessus) ; le ``j`` final
  médiéval (``viij`` = 8 pour Cinoc, refusé par ``roman``) ; ``N`` (zéro chez
  ``roman``, pas un numéral pour Cinoc : la lettre n'est pas dans son
  alphabet). ``MMMM`` n'est **pas** un écart : ``roman`` 5.x monte à 4 999.

Sautés hors du job CI ``oracle`` (extra ``oracle``) ; ``test_roman`` couvre la
grammaire sans le paquet.
"""

from __future__ import annotations

import itertools
import re

import pytest

from cinoc.evaluation.roman import roman_to_int

pytestmark = pytest.mark.oracle
roman = pytest.importorskip("roman")

#: Chiffre additif → sa forme canonique, du plus long au plus court.
_CANONICAL = (
    ("DCCCC", "CM"),
    ("CCCC", "CD"),
    ("LXXXX", "XC"),
    ("XXXX", "XL"),
    ("VIIII", "IX"),
    ("IIII", "IV"),
)
_ADDITIVE = re.compile(r"I{4}|X{4}|C{4}")


def _oracle(text: str) -> int | None:
    try:
        return int(roman.fromRoman(text))
    except roman.InvalidRomanNumeralError:
        return None


def _canonical(text: str) -> str:
    for additive, canonical in _CANONICAL:
        text = text.replace(additive, canonical)
    return text


def test_the_oracle_is_the_pinned_version() -> None:
    from importlib import metadata

    assert metadata.version("roman") == "5.2"


def test_every_canonical_form_has_the_oracle_value() -> None:
    for value in range(1, 5000):
        form = roman.toRoman(value)
        assert roman_to_int(form) == _oracle(form) == value, form
        assert roman_to_int(form.lower()) == _oracle(form.lower()) == value, form


def test_short_strings_agree_except_for_the_medieval_additive() -> None:
    both, cinoc_only, oracle_only = 0, [], []
    for length in range(1, 7):
        for letters in itertools.product("IVXLCDM", repeat=length):
            text = "".join(letters)
            ours, theirs = roman_to_int(text), _oracle(text)
            if ours is not None and theirs is not None:
                both += 1
                assert ours == theirs, text
            elif ours is not None:
                cinoc_only.append(text)
            elif theirs is not None:
                oracle_only.append(text)
    assert (both, len(cinoc_only), oracle_only) == (1339, 87, [])
    for text in cinoc_only:
        assert _ADDITIVE.search(text), text
        assert roman_to_int(text) == _oracle(_canonical(text)), text


@pytest.mark.parametrize(
    ("form", "ours", "theirs"),
    [
        ("IIII", 4, None),
        ("VIIII", 9, None),
        ("MCCCCXXXX", 1440, None),
        ("viij", 8, None),
        ("xiiij", 14, None),
        ("N", None, 0),
        ("MMMM", 4000, 4000),
        ("IIV", None, None),
        ("IXI", None, None),
    ],
)
def test_documented_gaps(form: str, ours: int | None, theirs: int | None) -> None:
    assert roman_to_int(form) == ours
    assert _oracle(form) == theirs


def test_a_final_medieval_j_is_the_only_extra_letter() -> None:
    """Toute forme canonique finissant par ``i`` s'écrit aussi en ``j`` final :
    Cinoc la lit à la même valeur, ``roman`` la refuse."""
    for value in range(1, 5000):
        form = roman.toRoman(value).lower()
        if form.endswith("i"):
            medieval = form[:-1] + "j"
            assert roman_to_int(medieval) == value, medieval
            assert _oracle(medieval) is None, medieval
