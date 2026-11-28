"""Runs répétés : une fourchette, jamais une décimale isolée.

Une décimale isolée ne dit pas si l'écart qu'on lui fait porter dépasse le
bruit du dispositif. Ce module réduit ``n`` exécutions de la **même** spec à
une fourchette par ``(pipeline, vue, métrique)``, pour qu'on puisse voir si une
comparaison tient debout.

Ce qui varie n'est pas le code : c'est le modèle — un LLM à température nulle
n'est pas déterministe pour autant — et, sur une API, la version servie
derrière un même nom.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cinoc.app.variance import run_repeatedly, summarize_runs
from cinoc.domain.errors import CinocError
from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult


def _result(*valeurs: float | None, metric: str = "cer") -> RunResult:
    return RunResult(
        manifest=RunManifest(
            run_id="r",
            corpus_name="corpus-test",
            n_documents=1,
            code_version="1.0",
            started_at=datetime(2026, 8, 21, tzinfo=UTC),
            completed_at=datetime(2026, 8, 21, tzinfo=UTC),
        ),
        pipelines=tuple(
            PipelineResult(
                pipeline=f"p{i}",
                view="text",
                conditional_aggregate=(MetricScore(metric=metric, value=v),),
            )
            for i, v in enumerate(valeurs)
        ),
    )


def test_a_spread_is_computed_over_the_runs() -> None:
    runs = [_result(0.10), _result(0.12), _result(0.11)]
    spread = summarize_runs(runs).spreads[0]
    assert (spread.n, spread.minimum, spread.maximum) == (3, 0.10, 0.12)
    assert spread.median_value == pytest.approx(0.11)
    assert spread.spread == pytest.approx(0.02 / 0.11)


def test_a_single_run_is_flagged_as_such() -> None:
    """C'est exactement la confusion que ce module existe pour empêcher :
    un run unique ne devient pas une mesure stable parce qu'on l'a résumé."""
    spread = summarize_runs([_result(0.10)]).spreads[0]
    assert spread.is_single_run
    assert spread.spread == pytest.approx(0.0)


def test_a_zero_median_yields_no_spread_rather_than_a_false_zero() -> None:
    """Diviser par zéro dirait « parfaitement stable » là où on ne sait pas."""
    spread = summarize_runs([_result(0.0), _result(0.0)]).spreads[0]
    assert spread.spread is None


def test_inapplicable_values_are_not_counted_as_zero() -> None:
    """``None`` = non applicable, pas « zéro » : compter une absence comme une
    valeur inventerait de la stabilité."""
    spread = summarize_runs([_result(0.10), _result(None), _result(0.14)]).spreads[0]
    assert spread.n == 2
    assert (spread.minimum, spread.maximum) == (0.10, 0.14)


def test_nothing_to_summarize_is_refused() -> None:
    with pytest.raises(CinocError, match="aucun run"):
        summarize_runs([])


def test_the_widest_metric_comes_first() -> None:
    """C'est elle qui borne ce qu'on a le droit d'affirmer."""
    runs = [
        _result(0.10, 0.20),
        _result(0.11, 0.40),
    ]
    pires = summarize_runs(runs).widest()
    assert pires[0].pipeline == "p1"  # étendue 100 % contre 10 %
    assert pires[0].spread > pires[1].spread


def test_each_run_is_executed_once_and_in_order() -> None:
    vus: list[int] = []

    def _execute(index: int):
        vus.append(index)
        return _result(0.10 + index / 100)

    results, variance = run_repeatedly(_execute, 3)
    assert vus == [0, 1, 2]
    assert len(results) == 3
    assert variance.runs == 3
    assert variance.corpus == "corpus-test"


def test_zero_runs_is_refused() -> None:
    with pytest.raises(CinocError, match="minimum 1"):
        run_repeatedly(lambda _: _result(0.1), 0)
