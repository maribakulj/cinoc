"""Collecteur de données structurées : payload par pipeline × catégorie."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import StructuredDataPayload
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run
from cinoc.evaluation.structured_data import StructuredDataCollector

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def test_collector_aggregates_micro() -> None:
    collector = StructuredDataCollector()
    collector.observe("eng", "en 1515, fol. 3r", "en 1515, fol 3r")
    collector.observe("eng", "puis 1789", "puis 178")
    analysis = collector.build("text")
    assert analysis is not None
    payload = analysis.payload
    assert isinstance(payload, StructuredDataPayload)
    (row,) = payload.pipelines
    by_category = {c.category: c for c in row.categories}
    years = by_category["year"]
    assert (years.n_total, years.n_strict, years.n_value) == (2, 1, 1)
    assert years.strict_score == pytest.approx(0.5)
    assert years.lost == ("1789",)
    folios = by_category["foliation"]
    assert (folios.n_strict, folios.n_value) == (0, 1)


def test_collector_silent_without_signal() -> None:
    collector = StructuredDataCollector()
    collector.observe("eng", "bonjour", "bonjour")
    assert collector.build("text") is None


def test_through_evaluate_run(tmp_path: Path) -> None:
    gt = tmp_path / "doc1.gt.txt"
    gt.write_text("Paris, 1515, fol. 3r", encoding="utf-8")
    hyp = tmp_path / "doc1.hyp.txt"
    hyp.write_text("Paris 1515 fol 3r", encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="doc1",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            ),
        ),
    )
    outputs = {
        "eng": {
            "doc1": {
                ArtifactType.RAW_TEXT: Artifact(
                    id="doc1:raw",
                    document_id="doc1",
                    type=ArtifactType.RAW_TEXT,
                    uri=str(hyp),
                )
            }
        }
    }
    registry = MetricRegistry()
    register_default_metrics(registry)
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer", "numseq_strict", "numseq_value"),
    )
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(
            PipelineSpec(name="eng", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,), analyses="toutes"),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=manifest,
    )
    aggregate = {s.metric: s.value for s in result.pipelines[0].aggregate}
    assert aggregate["numseq_strict"] == pytest.approx(0.5)
    assert aggregate["numseq_value"] == pytest.approx(1.0)
    payloads = [
        a.payload
        for a in result.analyses
        if isinstance(a.payload, StructuredDataPayload)
    ]
    assert len(payloads) == 1
