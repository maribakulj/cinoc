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
from cinoc.evaluation.statistics import EditCounts, ErrorCounts
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
                conditional_aggregate=(
                    MetricScore(
                        metric="cer", value=0.25, support=1, expected=2,
                        stat=EditCounts(
                            substitutions=1, deletions=0, insertions=0,
                            reference_length=4,
                        ),
                    ),
                    MetricScore(
                        metric="char_accuracy", value=0.0, support=1, expected=2,
                        stat=ErrorCounts(errors=44, reference_length=10),
                        untruncated_error_rate=4.4,
                    ),
                ),
            ),
        ),
        documents=(
            RunDocumentResult(
                document_id="d1", pipeline="tess", view="text",
                scores=(
                    MetricScore(
                        metric="cer", value=0.25,
                        stat=EditCounts(
                            substitutions=1, deletions=0, insertions=0,
                            reference_length=4,
                        ),
                    ),
                    MetricScore(metric="wer", value=None, support=None),
                    MetricScore(
                        metric="ins_rate", value=None,
                        stat=EditCounts(
                            substitutions=0, deletions=0, insertions=3,
                            reference_length=0,
                        ),
                        scalar_reason="zero_denominator",
                    ),
                ),
            ),
            RunDocumentResult(
                document_id="d2", pipeline="tess", view="text",
                scores=(MetricScore(metric="cer"),),
            ),
        ),
        usage=(
            DocumentUsage(
                document_id="d1", pipeline="tess",
                usage=ResourceUsage(duration_seconds=1.5),
            ),
            DocumentUsage(
                document_id="d2", pipeline="tess", usage=ResourceUsage(),
                outcome="failed", reason="engine", message="boom",
            ),
        ),
    )


def test_csv_exact_content() -> None:
    # ``expected`` (agrégat) et ``outcome`` (document) : un vide de ``d2`` se
    # lit « échec du moteur », celui du WER de ``d1`` « non applicable ». Puis
    # la durée de chaque unité (D-289, pilote D11) — vide pour l'échec. Les
    # comptes de la statistique, le motif d'un scalaire indéfini et le taux
    # non tronqué d'une exactitude sont publiés à côté (K1, B1).
    edits = "edit_counts:substitutions=1;deletions=0;insertions=0;reference_length=4"
    blank = "edit_counts:substitutions=0;deletions=0;insertions=3;reference_length=0"
    assert run_result_csv(_result()) == (
        "scope,view,pipeline,document_id,metric,value,support,expected,outcome,"
        "statistic,scalar_reason,untruncated_error_rate\n"
        f"aggregate,text,tess,,cer,0.25,1,2,,{edits},,\n"
        "aggregate,text,tess,,char_accuracy,0.0,1,2,,"
        "error_counts:errors=44;reference_length=10,,4.4\n"
        f"document,text,tess,d1,cer,0.25,,,ok,{edits},,\n"
        "document,text,tess,d1,wer,,,,ok,,,\n"
        f"document,text,tess,d1,ins_rate,,,,ok,{blank},zero_denominator,\n"
        "document,text,tess,d2,cer,,,,failed:engine,,,\n"
        "usage,,tess,d1,duration_seconds,1.5,,,ok,,,\n"
        "usage,,tess,d2,duration_seconds,,,,failed:engine,,,\n"
    )


def test_csv_is_deterministic() -> None:
    assert run_result_csv(_result()) == run_result_csv(_result())
