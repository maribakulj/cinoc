"""mufi_err : détection des caractères MUFI / médiévaux, cas N/A, alignement."""

from __future__ import annotations

from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.philology import _is_mufi, mufi_error

_LONG_S = "ſ"  # ſ s long médiéval (set explicite)
_THORN = "þ"  # þ thorn (set explicite)
_PUA = ""  # zone d'usage privé (MUFI)
_LATIN_EXT_D = "ꝓ"  # ꝓ p à boucle (Latin Extended-D, abréviation latine)
_LIGATURE = "ﬀ"  # ﬀ ligature latine


def _ctx(reference: str, hypothesis: str) -> DocContext:
    return DocContext(document_id="d", reference=reference, hypothesis=hypothesis)


def test_is_mufi_detects_special_chars() -> None:
    assert _is_mufi(_LONG_S)
    assert _is_mufi(_THORN)
    assert _is_mufi(_LATIN_EXT_D)
    assert _is_mufi(_PUA)
    assert _is_mufi(_LIGATURE)


def test_is_mufi_excludes_plain_letters() -> None:
    assert not _is_mufi("a")
    assert not _is_mufi("e")
    assert not _is_mufi("é")  # é : accent ordinaire → relève de diacritic_err


def test_mufi_error_none_when_reference_has_none() -> None:
    obs = mufi_error.fn(_ctx("hello world", "helo wrld"))
    assert obs.value is None and obs.stat.total == 0  # indéfini, pas 0


def test_mufi_error_perfect() -> None:
    ref = f"me{_LONG_S}se"
    obs = mufi_error.fn(_ctx(ref, ref))
    assert obs is not None and obs.value == 0.0 and obs.stat.total == 1


def test_mufi_error_substituted_long_s() -> None:
    # ſ (s long) lu « s » moderne : 1 cible, 1 faux → 1.0.
    obs = mufi_error.fn(_ctx(f"me{_LONG_S}se", "messe"))
    assert obs is not None and obs.value == 1.0 and obs.stat.total == 1


def test_mufi_error_partial() -> None:
    # deux cibles (ſ, þ) ; seule ſ est fausse → 0.5 sur 2.
    obs = mufi_error.fn(_ctx(f"{_LONG_S}a{_THORN}", f"a{_THORN}"))
    assert obs is not None and obs.value == 0.5 and obs.stat.total == 2
