"""Diff GT↔hypothèse caractère à caractère : marquage, échappement, déterminisme."""

from __future__ import annotations

import html
import re
from pathlib import Path

from cinoc.evaluation._alignment import char_counts
from cinoc.reports.text_diff import char_diff


def test_equal_strings_have_no_markup() -> None:
    ref, hyp = char_diff("abcd", "abcd")
    assert ref == "abcd" and hyp == "abcd"
    assert "<del" not in ref and "<ins" not in hyp


def test_substitution_marks_both_sides() -> None:
    # « m » (GT) vs « rn » (hyp) : la confusion OCR classique.
    ref, hyp = char_diff("chemin", "chernin")
    assert ref == 'che<del class="d-del">m</del>in'
    assert hyp == 'che<ins class="d-ins">rn</ins>in'


def test_pure_deletion_only_marks_reference() -> None:
    ref, hyp = char_diff("abc", "ac")  # « b » supprimé
    assert '<del class="d-del">b</del>' in ref
    assert "<ins" not in hyp


def test_pure_insertion_only_marks_hypothesis() -> None:
    ref, hyp = char_diff("ac", "abc")  # « b » inséré
    assert "<del" not in ref
    assert '<ins class="d-ins">b</ins>' in hyp


def test_segments_are_escaped() -> None:
    # Chaque segment est échappé avant marquage (anti-XSS), y compris dans <del>.
    ref, hyp = char_diff("<x>", "y")
    assert "<x>" not in ref
    assert '<del class="d-del">&lt;x&gt;</del>' == ref
    assert '<ins class="d-ins">y</ins>' == hyp


def test_is_deterministic() -> None:
    assert char_diff("Bonjour", "Bnjuor") == char_diff("Bonjour", "Bnjuor")


_BNL_MINI = Path(__file__).parents[1] / "fixtures" / "reference_corpus" / "bnl_mini"
_MARQUE = re.compile(r'<(del|ins) class="d-(?:del|ins)">(.*?)</\1>', re.DOTALL)


def _marques(fragment: str) -> int:
    """Caractères surlignés d'un côté du diff (texte échappé décodé)."""
    return sum(len(html.unescape(m.group(2))) for m in _MARQUE.finditer(fragment))


def _assert_same_edits_as_the_cer(reference: str, hypothesis: str) -> None:
    substitutions, deletions, insertions = char_counts(reference, hypothesis)
    ref, hyp = char_diff(reference, hypothesis)
    assert _marques(ref) == substitutions + deletions
    assert _marques(hyp) == substitutions + insertions


def test_the_diff_highlights_the_edits_the_cer_counts() -> None:
    """Reste de S14 (D-286) : aligné par ``difflib``, le diff surlignait
    « un un » lu « uaun » comme 3 caractères supprimés et 2 insérés là où le
    CER compte une substitution et une suppression."""
    _assert_same_edits_as_the_cer("un un", "uaun")
    ref, hyp = char_diff("un un", "uaun")
    assert ref == 'u<del class="d-del">n </del>un'
    assert hyp == 'u<ins class="d-ins">a</ins>un'


def test_the_diff_highlights_the_cer_edits_on_bnl_mini() -> None:
    """Sur les 150 couples réels de ``bnl_mini`` (34 où ``difflib`` surlignait
    plus que le CER ne compte), chaque côté surligne exactement S + D et
    S + I caractères."""
    couples = 0
    for gt in sorted(_BNL_MINI.glob("*.gt.txt")):
        reference = gt.read_text(encoding="utf-8")
        stem = gt.name.removesuffix(".gt.txt")
        for hyp in sorted(_BNL_MINI.glob(f"{stem}.*.txt")):
            if hyp != gt:
                hypothesis = hyp.read_text(encoding="utf-8")
                _assert_same_edits_as_the_cer(reference, hypothesis)
                couples += 1
    assert couples == 150
