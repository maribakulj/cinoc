"""Round-trip JSON d'un ``RunResult`` (sauvegarde / rechargement)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.app.results import RunResultError, dump_run_result, load_run_result
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _sample() -> RunResult:
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    manifest = RunManifest(
        run_id="A",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(
            PipelineSpec(name="eng", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        view_specs=(view,),
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
                    MetricScore(metric="cer", value=0.25, support=1),
                ),
            ),
        ),
        cross_engine=(
            MetricScore(metric="text:cer:significance_p", value=0.5, support=1),
        ),
    )


def test_round_trip_preserves_everything(tmp_path: Path) -> None:
    result = _sample()
    path = tmp_path / "r.json"
    dump_run_result(result, path)
    loaded = load_run_result(path)
    assert loaded == result
    assert loaded.manifest.view_specs[0].candidate_types == frozenset(
        {ArtifactType.RAW_TEXT}
    )


def test_load_invalid_raises(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RunResultError):
        load_run_result(tmp_path / "bad.json")
