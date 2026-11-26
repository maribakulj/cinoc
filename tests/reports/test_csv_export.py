"""Export CSV : lecture pure du RunResult, ordre et valeurs exactes."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.result import (
    DocumentUsage,
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.reports.csv_export import run_result_csv

FIXED = datetime(2026, 6, 1, tzinfo=UTC)


def _result() -> RunResult:
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=1,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="tess", view="text",
                aggregate=(
                    MetricScore(metric="cer", value=0.25, support=1, expected=2),
                ),
            ),
        ),
        documents=(
            RunDocumentResult(
                document_id="d1", pipeline="tess", view="text",
                scores=(
                    MetricScore(metric="cer", value=0.25, support=4),
                    MetricScore(metric="wer", value=None, support=None),
                ),
            ),
            RunDocumentResult(
                document_id="d2", pipeline="tess", view="text",
                scores=(MetricScore(metric="cer"),),
            ),
        ),
        usage=(
            DocumentUsage(document_id="d1", pipeline="tess", usage=ResourceUsage()),
            DocumentUsage(
                document_id="d2", pipeline="tess", usage=ResourceUsage(),
                outcome="failed", reason="engine", message="boom",
            ),
        ),
    )


def test_csv_exact_content() -> None:
    # ``expected`` (agrégat) et ``outcome`` (document) : un vide de ``d2`` se
    # lit « échec du moteur », celui du WER de ``d1`` « non applicable ».
    assert run_result_csv(_result()) == (
        "scope,view,pipeline,document_id,metric,value,support,expected,outcome\n"
        "aggregate,text,tess,,cer,0.25,1,2,\n"
        "document,text,tess,d1,cer,0.25,4,,ok\n"
        "document,text,tess,d1,wer,,,,ok\n"
        "document,text,tess,d2,cer,,,,failed:engine\n"
    )


def test_csv_is_deterministic() -> None:
    assert run_result_csv(_result()) == run_result_csv(_result())
