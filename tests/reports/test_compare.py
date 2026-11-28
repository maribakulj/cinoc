"""``compare_runs`` (deltas) + ``render_comparison`` (rapport autonome)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.reports.compare import compare_runs, render_comparison

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _result(run_id: str, cer: float | None) -> RunResult:
    manifest = RunManifest(
        run_id=run_id,
        corpus_name="c",
        n_documents=1,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="eng",
                view="text",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=cer, support=1),
                ),
            ),
        ),
    )


def test_delta_computed() -> None:
    deltas = compare_runs(_result("A", 0.30), _result("B", 0.25))
    assert len(deltas) == 1
    delta = deltas[0]
    assert (delta.pipeline, delta.view, delta.metric) == ("eng", "text", "cer")
    assert delta.value_a == 0.30
    assert delta.value_b == 0.25
    assert delta.delta == pytest.approx(-0.05)


def test_delta_none_when_value_missing() -> None:
    deltas = compare_runs(_result("A", 0.30), _result("B", None))
    assert deltas[0].delta is None


def test_render_comparison_is_autonomous_html() -> None:
    html = render_comparison(_result("A", 0.30), _result("B", 0.25))
    assert html.startswith("<!DOCTYPE html>")
    assert "comparaison" in html.lower()
    assert '<html lang="fr">' in html


def test_decimals_follow_the_report_language() -> None:
    """D22 du pilote : un rapport français écrivait « 0.3000 » (point) là où
    tout le reste du produit écrit « 0,3000 »."""
    fr = render_comparison(_result("A", 0.30), _result("B", 0.25))
    assert "0,3000" in fr and "-0,0500" in fr
    assert "0.3000" not in fr
    en = render_comparison(_result("A", 0.30), _result("B", 0.25), lang="en")
    assert "0.3000" in en and "-0.0500" in en
    assert '<html lang="en">' in en and "Metric" in en and "Métrique" not in en


def test_two_runs_with_the_same_id_are_told_apart() -> None:
    """D22 : ``A = run · B = run`` ne disait pas lequel était lequel. Chaque
    côté nomme sa source (le **nom** du fichier : aucun chemin local, D5) et
    l'heure de son run."""
    a = _result("run", 0.30)
    b = _result("run", 0.25).model_copy(
        update={
            "manifest": a.manifest.model_copy(
                update={"started_at": datetime(2026, 2, 3, 4, 5, tzinfo=UTC)}
            )
        }
    )
    html = render_comparison(a, b, source_a="avant.json", source_b="apres.json")
    assert "avant.json" in html and "apres.json" in html
    assert "2026-01-01 00:00 UTC" in html and "2026-02-03 04:05 UTC" in html
