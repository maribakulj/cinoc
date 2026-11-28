"""diacritic_err : détection des caractères à diacritique, cas N/A, alignement."""

from __future__ import annotations

from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.diacritics import _is_diacritic, diacritic_error


def _ctx(reference: str, hypothesis: str) -> DocContext:
    return DocContext(document_id="d", reference=reference, hypothesis=hypothesis)


def test_is_diacritic_detects_accented_letters() -> None:
    assert _is_diacritic("ä") and _is_diacritic("é") and _is_diacritic("ñ")


def test_is_diacritic_excludes_plain_and_ligatures() -> None:
    assert not _is_diacritic("a")
    assert not _is_diacritic("ß")  # base, pas de diacritique
    assert not _is_diacritic("æ")  # ligature, pas un accent


def test_diacritic_error_none_when_reference_has_no_diacritics() -> None:
    obs = diacritic_error.fn(_ctx("hello world", "helo wrld"))
    assert obs.value is None and obs.stat.total == 0  # indéfini, pas 0


def test_diacritic_error_perfect() -> None:
    obs = diacritic_error.fn(_ctx("café", "café"))
    assert obs is not None and obs.value == 0.0 and obs.stat.total == 1


def test_diacritic_error_substituted_diacritic() -> None:
    # « ü » lu « u » : 1 diacritique en réf, 1 faux → 1.0 (poids 1).
    obs = diacritic_error.fn(_ctx("Müller", "Muller"))
    assert obs is not None and obs.value == 1.0 and obs.stat.total == 1


def test_diacritic_error_partial() -> None:
    # « é » et « è » en réf ; seul « é » est faux → 0.5 sur 2 cibles.
    obs = diacritic_error.fn(_ctx("éxè", "exè"))
    assert obs is not None and obs.value == 0.5 and obs.stat.total == 2
