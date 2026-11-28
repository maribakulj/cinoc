"""Bag-of-Words : précision/rappel/F1 sur le multiset de tokens, ordre libre."""

from __future__ import annotations

import pytest

from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metrics.bow import bow_f1, bow_precision, bow_recall
from cinoc.evaluation.statistics import MatchCounts


def _ctx(reference: object, hypothesis: object) -> DocContext:
    return DocContext(document_id="d", reference=reference, hypothesis=hypothesis)


def test_perfect_and_order_independent() -> None:
    # Mots identiques mais ordre inversé → P=R=F1=1 (sac de mots).
    ctx = _ctx("le chat noir", "noir chat le")
    assert bow_precision.fn(ctx).value == 1.0
    assert bow_recall.fn(ctx).value == 1.0
    assert bow_f1.fn(ctx).value == 1.0


def test_partial_overlap_pr_f1() -> None:
    # réf 3 mots, hyp 4 mots, 2 communs (le, noir) → tp=2.
    ctx = _ctx("le chat noir", "le noir gris vert")
    p = bow_precision.fn(ctx)
    r = bow_recall.fn(ctx)
    assert p.value == pytest.approx(2 / 4) and r.value == pytest.approx(2 / 3)
    # Même statistique (tp, fp, fn) pour les trois : fp = |hyp| − tp, fn = |réf| − tp.
    assert p.stat == r.stat == MatchCounts(tp=2, fp=2, fn=1)
    f1 = 2 * (2 / 4) * (2 / 3) / ((2 / 4) + (2 / 3))
    assert bow_f1.fn(ctx).value == pytest.approx(f1)


def test_multiset_caps_true_positives() -> None:
    # 'a' attendu 2×, produit 3× → tp('a')=2 (min), pas 3.
    ctx = _ctx("a a b", "a a a")
    # tp = min(2,3) pour 'a' + min(1,0) pour 'b' = 2 ; |hyp|=3, |réf|=3
    assert bow_precision.fn(ctx).value == pytest.approx(2 / 3)
    assert bow_recall.fn(ctx).value == pytest.approx(2 / 3)


def test_degenerate_cases() -> None:
    both_empty = _ctx("", "")
    # Ni mot attendu ni mot produit : F1, P et R indéfinis (dénominateur nul).
    assert bow_f1.fn(both_empty).value is None
    assert bow_f1.fn(both_empty).stat == MatchCounts(tp=0, fp=0, fn=0)
    # hyp vide, réf non vide → rappel 0
    assert bow_recall.fn(_ctx("a b", "")).value == 0.0
    # réf vide, hyp non vide → précision 0
    assert bow_precision.fn(_ctx("", "a b")).value == 0.0


def test_higher_is_better_and_type_guard() -> None:
    for metric in (bow_precision, bow_recall, bow_f1):
        assert metric.spec.higher_is_better is True
        with pytest.raises(EvaluationError):
            metric.fn(_ctx(1, "x"))
