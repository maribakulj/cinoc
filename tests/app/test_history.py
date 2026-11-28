"""Trait d'union ``RunResult`` ↔ historique : enregistrement + analyse de série."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.adapters.storage.history_store import HistoryRecord, HistoryStore, SeriesKey
from cinoc.app.history import record_run, records_from_run, series_insight
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult


def _view(profile: str | None = "flat_text") -> EvaluationView:
    return EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer", "wer"),
        normalization_profile=profile,
    )


def _run(
    run_id: str,
    cer: float,
    when: datetime,
    *,
    corpus: str = "corpusA",
    view: EvaluationView | None = None,
) -> RunResult:
    manifest = RunManifest(
        run_id=run_id,
        corpus_name=corpus,
        n_documents=2,
        code_version="0.1.0",
        started_at=when,
        completed_at=when,
        view_specs=(view or _view(),),
    )
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="tesseract",
                view="text",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=cer, support=2),
                    MetricScore(metric="wer", value=None),  # non applicable → ignoré
                ),
            ),
        ),
    )


def test_records_from_run_skips_none() -> None:
    recs = records_from_run(_run("r1", 0.1, datetime(2026, 1, 1, tzinfo=UTC)))
    assert len(recs) == 1  # wer None écarté
    rec = recs[0]
    assert rec.metric == "cer" and rec.value == 0.1
    assert rec.run_id == "r1" and rec.corpus_name == "corpusA"
    assert rec.code_version == "0.1.0" and rec.pipeline == "tesseract"
    assert rec.normalization_profile == "flat_text"


def test_records_carry_the_view_profile_and_keep_series_apart(
    tmp_path: Path,
) -> None:
    """D-288 : le profil de la vue est lu au manifeste ; un run sous un autre
    profil ou sur un autre corpus ouvre une autre série."""
    store = HistoryStore(tmp_path / "h.db")
    jan, feb, mar = (datetime(2026, m, 1, tzinfo=UTC) for m in (1, 2, 3))
    record_run(store, _run("r1", 0.10, jan))
    record_run(store, _run("r2", 0.30, feb, view=_view("nfc")))
    record_run(store, _run("r3", 0.50, mar, corpus="corpusB"))
    assert store.regressions("text", "cer") == ()
    key = SeriesKey("corpusA", "flat_text", "tesseract", "text")
    assert [r.run_id for r in store.history(key, "cer")] == ["r1"]
    assert len(store.series("text", "cer")) == 3


def test_view_missing_from_manifest_is_not_recorded_under_a_guess(
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = _run("r1", 0.1, datetime(2026, 1, 1, tzinfo=UTC))
    bare = result.model_copy(
        update={"manifest": result.manifest.model_copy(update={"view_specs": ()})}
    )
    with caplog.at_level(logging.WARNING):
        assert records_from_run(bare) == ()
    assert "profil inconnu" in caplog.text


def test_record_run_then_query_and_regression(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    assert record_run(store, _run("r1", 0.10, datetime(2026, 1, 1, tzinfo=UTC))) == 1
    record_run(store, _run("r2", 0.20, datetime(2026, 2, 1, tzinfo=UTC)))

    hist = store.history(SeriesKey("corpusA", "flat_text", "tesseract", "text"), "cer")
    assert [r.value for r in hist] == [0.10, 0.20]

    regs = store.regressions("text", "cer")
    assert len(regs) == 1 and regs[0].latest == 0.20


def _record(run_id: str, completed_at: str, value: float) -> HistoryRecord:
    return HistoryRecord(
        run_id=run_id,
        completed_at=completed_at,
        corpus_name="c",
        normalization_profile="flat_text",
        code_version="1.0",
        pipeline="tesseract",
        view="text",
        metric="cer",
        value=value,
    )


def test_series_insight_trend_and_significant_shift() -> None:
    # 6 runs à 0.30 puis 6 à 0.10 (un jour d'écart) : tendance descendante,
    # rupture Pettitt significative — le premier run du nouveau régime est r07.
    records = [
        _record(f"r{i + 1:02d}", f"2026-01-{i + 1:02d}T00:00:00", value)
        for i, value in enumerate([0.30] * 6 + [0.10] * 6)
    ]
    insight = series_insight(records)
    assert insight.trend is not None
    assert insight.trend.slope_per_day < 0 and insight.trend.n_points == 12
    assert insight.rupture is not None and insight.rupture.significant
    assert insight.rupture.delta == pytest.approx(-0.2)
    assert insight.rupture_run_id == "r07"


def test_series_insight_sorts_chronologically() -> None:
    # L'analyse trie elle-même (Pettitt dépend de l'ordre) : entrée renversée
    # → même verdict que l'entrée chronologique.
    records = [
        _record(f"r{i + 1:02d}", f"2026-01-{i + 1:02d}T00:00:00", value)
        for i, value in enumerate([0.30] * 6 + [0.10] * 6)
    ]
    assert series_insight(list(reversed(records))) == series_insight(records)


def test_series_insight_skips_unreadable_timestamp_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    records = [
        _record("r1", "2026-01-01T00:00:00", 0.30),
        _record("rX", "pas-une-date", 0.99),
        _record("r2", "2026-01-02T00:00:00", 0.20),
    ]
    with caplog.at_level(logging.WARNING):
        insight = series_insight(records)
    assert "horodatage illisible" in caplog.text and "rX" in caplog.text
    assert insight.trend is not None and insight.trend.n_points == 2


def test_series_insight_short_series_degrades_to_none() -> None:
    insight = series_insight([_record("r1", "2026-01-01T00:00:00", 0.30)])
    assert insight.trend is None
    assert insight.rupture is None
    assert insight.rupture_run_id is None
