"""``REFERENCE_TEXT`` (OCR de référence, ≠ vérité-terrain) en évaluation.

Lot C : une GT ``REFERENCE_TEXT`` (ex. OCR Gallica) **n'est pas scorée** par une
vue par défaut (pas de faux score d'exactitude) ; elle ne l'est que par une vue
*référence* dédiée qui déclare la projection ``reference_text → raw_text``
(opt-in explicite via le projecteur ``identity_text``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import ProjectionError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.projection import ProjectionSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.projectors import identity_text
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)

_REFERENCE_PROJECTION = ProjectionSpec(
    source_type=ArtifactType.REFERENCE_TEXT,
    target_type=ArtifactType.RAW_TEXT,
    projector_name="identity_text",
)


def test_identity_text_returns_str_unchanged() -> None:
    assert identity_text("abc", {}) == "abc"


def test_identity_text_rejects_non_str() -> None:
    with pytest.raises(ProjectionError, match="identity_text"):
        identity_text(123, {})


def _registry() -> MetricRegistry:
    registry = MetricRegistry()
    register_default_metrics(registry)
    return registry


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(
            PipelineSpec(name="ocr", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def _run(tmp_path: Path, view: EvaluationView) -> object:
    # Référence OCR "hello world" ; candidat "hello worlX" → 1 substitution.
    gt_path = tmp_path / "ref.gallica_ocr.txt"
    gt_path.write_text("hello world", encoding="utf-8")
    hyp_path = tmp_path / "hyp.txt"
    hyp_path.write_text("hello worlX", encoding="utf-8")
    hyp = Artifact(
        id="doc1:hyp", document_id="doc1", type=ArtifactType.RAW_TEXT, uri=str(hyp_path)
    )
    doc = DocumentRef(
        id="doc1",
        ground_truths=(
            GroundTruthRef(type=ArtifactType.REFERENCE_TEXT, uri=str(gt_path)),
        ),
    )
    return evaluate_run(
        corpus=CorpusSpec(name="c", documents=(doc,)),
        evaluation=EvaluationSpec(views=(view,)),
        pipeline_outputs={"ocr": {"doc1": {"ocr": {ArtifactType.RAW_TEXT: hyp}}}},
        registry=_registry(),
        manifest=_manifest(),
    )


def test_reference_view_scores_against_reference_text(tmp_path: Path) -> None:
    # Vue référence : projection reference_text → raw_text déclarée → le candidat
    # est comparé à la référence OCR (CER = 1/11), score distinct et explicite.
    view = EvaluationView(
        name="référence OCR (pas une vérité-terrain manuelle)",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        projections_by_source_type={ArtifactType.REFERENCE_TEXT: _REFERENCE_PROJECTION},
        metric_names=("cer",),
    )
    result = _run(tmp_path, view)
    aggregate = result.pipelines[0].aggregate[0]  # type: ignore[attr-defined]
    assert aggregate.metric == "cer"
    assert aggregate.value == pytest.approx(1 / 11)
    assert aggregate.support == 1


def test_default_view_ignores_reference_text(tmp_path: Path) -> None:
    # Vue par défaut (aucune projection) : une GT REFERENCE_TEXT n'alimente PAS
    # la référence RAW_TEXT → non applicable (None), surtout pas un faux score.
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    result = _run(tmp_path, view)
    aggregate = result.pipelines[0].aggregate[0]  # type: ignore[attr-defined]
    assert aggregate.value is None
    assert aggregate.support == 0
