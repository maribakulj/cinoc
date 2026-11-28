"""Moteur partagé ``preservation_counts`` + **parité bit-à-bit** mufi/diacritic.

La factorisation de ``mufi_err``/``diacritic_err`` dans
:func:`preservation_counts` doit être **à valeur constante** : les métriques
existantes ne bougent pas. On le prouve en confrontant la sortie des métriques
aux comptes bruts du moteur, sur des cas aux valeurs dérivées à la main.
"""

from __future__ import annotations

from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.diacritics import diacritic_error
from cinoc.evaluation.metrics.philology import mufi_error
from cinoc.evaluation.preservation import preservation_counts

_LONG_S = "ſ"
_THORN = "þ"


def _ctx(reference: str, hypothesis: str) -> DocContext:
    return DocContext(document_id="d", reference=reference, hypothesis=hypothesis)


def test_counts_none_when_no_target() -> None:
    assert preservation_counts("hello", "helo", lambda c: c == "z") == (0, 0)


def test_counts_total_and_wrong() -> None:
    # deux ſ cibles ; le 1er substitué (replace), le 2e conservé → (2, 1).
    ref, hyp = f"{_LONG_S}a{_LONG_S}", f"sa{_LONG_S}"
    assert preservation_counts(ref, hyp, lambda c: c == _LONG_S) == (2, 1)


def test_counts_delete_is_wrong() -> None:
    # cible supprimée → comptée fausse.
    assert preservation_counts(f"a{_THORN}b", "ab", lambda c: c == _THORN) == (1, 1)


def test_mufi_parity_matches_engine() -> None:
    # mufi_err == n_wrong / n_total du moteur partagé (parité bit-à-bit).
    ref, hyp = f"me{_LONG_S}{_THORN}e", "messe"
    counts = preservation_counts(ref, hyp, lambda c: c in {_LONG_S, _THORN})
    assert counts is not None
    n_total, n_wrong = counts
    obs = mufi_error.fn(_ctx(ref, hyp))
    assert obs is not None
    assert obs.value == n_wrong / n_total
    assert obs.stat.total == n_total


def test_diacritic_parity_matches_engine() -> None:
    ref, hyp = "café crème", "cafe creme"  # é, è perdus
    counts = preservation_counts(ref, hyp, lambda c: c in {"é", "è"})
    assert counts is not None
    n_total, n_wrong = counts
    obs = diacritic_error.fn(_ctx(ref, hyp))
    assert obs is not None
    assert obs.value == n_wrong / n_total
    assert obs.stat.total == n_total
