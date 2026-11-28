"""Section structure : Region-F1 + CER par région, rendu lecture seule (M5)."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.structure import StructureSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _result(pipelines: tuple[PipelineResult, ...]) -> RunResult:
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(
            PipelineSpec(name="seg", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    return RunResult(manifest=manifest, pipelines=pipelines)


def test_renders_region_f1_and_cer() -> None:
    pipe = PipelineResult(
        pipeline="seg",
        view="structure (mise en page)",
        conditional_aggregate=(
            MetricScore(metric="region_detection", value=0.82, support=3),
            MetricScore(metric="region_cer", value=0.0345, support=120),
        ),
    )
    html = StructureSection().render(_result((pipe,)), SectionContext())
    assert html is not None
    assert "Region-F1" in html
    assert "0,8200" in html and "0,0345" in html


def test_absent_without_region_metrics() -> None:
    # Run texte-seul : aucune métrique structure → section absente (pas vide).
    pipe = PipelineResult(
        pipeline="eng",
        view="text",
        conditional_aggregate=(MetricScore(metric="cer", value=0.1, support=10),),
    )
    assert StructureSection().render(_result((pipe,)), SectionContext()) is None
