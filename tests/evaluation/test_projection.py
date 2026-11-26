"""Projecteur ``layout_to_text`` + exécution de ``ProjectionSpec`` par le runner.

Premier consommateur de ``ProjectionSpec`` (réserve §9) : une vue projette un
candidat **structuré** (LAYOUT) vers du **texte**, ce qui permet de le noter avec
les métriques texte (CER) contre une référence — structurée ou texte.
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
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Line, Region
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.projection import ProjectionSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.projectors import get_projector, layout_to_text
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)
_LAYOUT_TO_TEXT = ProjectionSpec(
    source_type=ArtifactType.LAYOUT,
    target_type=ArtifactType.RAW_TEXT,
    projector_name="layout_to_text",
)


def _layout(*regions: Region, reading_order: tuple[str, ...] = ()) -> CanonicalLayout:
    return CanonicalLayout(
        pages=(LayoutPage(regions=regions, reading_order=reading_order),)
    )


def _region(rid: str, *lines: str) -> Region:
    return Region(id=rid, lines=tuple(Line(text=t) for t in lines))


# --- projecteur en isolation -------------------------------------------------


def test_layout_to_text_joins_lines_and_regions() -> None:
    layout = _layout(_region("r1", "hello", "world"), _region("r2", "second"))
    assert layout_to_text(layout, {}) == "hello\nworld\n\nsecond"


def test_layout_to_text_honors_reading_order() -> None:
    layout = _layout(_region("r1", "A"), _region("r2", "B"), reading_order=("r2", "r1"))
    assert layout_to_text(layout, {}) == "B\n\nA"


def test_layout_to_text_flattens_nested_regions() -> None:
    inner = _region("sub", "deep")
    outer = Region(id="r1", lines=(Line(text="top"),), regions=(inner,))
    assert layout_to_text(_layout(outer), {}) == "top\ndeep"


def test_layout_to_text_rejects_non_layout() -> None:
    with pytest.raises(ProjectionError, match="CanonicalLayout"):
        layout_to_text("not a layout", {})


def test_get_projector_unknown_raises() -> None:
    with pytest.raises(EvaluationError, match="projecteur inconnu"):
        get_projector("nope")


# --- exécution par le runner -------------------------------------------------


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
            PipelineSpec(name="seg", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def _layout_artifact(tmp_path: Path, name: str, layout: CanonicalLayout) -> Artifact:
    path = tmp_path / name
    path.write_bytes(layout.model_dump_json().encode("utf-8"))
    return Artifact(
        id=f"doc1:{name}",
        document_id="doc1",
        type=ArtifactType.LAYOUT,
        uri=str(path),
    )


def _run(tmp_path: Path, view: EvaluationView) -> object:
    ref = _layout(_region("r1", "hello world"), _region("r2", "second block"))
    bad = _layout(_region("r1", "hello world"), _region("r2", "second blocX"))
    gt = _layout_artifact(tmp_path, "gt.json", ref)
    hyp = _layout_artifact(tmp_path, "hyp.json", bad)
    doc = DocumentRef(
        id="doc1",
        ground_truths=(GroundTruthRef(type=ArtifactType.LAYOUT, uri=gt.uri),),
    )
    return evaluate_run(
        corpus=CorpusSpec(name="c", documents=(doc,)),
        evaluation=EvaluationSpec(views=(view,)),
        pipeline_outputs={"seg": {"doc1": {"ocr": {ArtifactType.LAYOUT: hyp}}}},
        registry=_registry(),
        manifest=_manifest(),
    )


def test_layout_candidate_scored_by_text_metric_via_projection(tmp_path: Path) -> None:
    view = EvaluationView(
        name="text-of-layout",
        candidate_types=frozenset({ArtifactType.LAYOUT}),
        projection=_LAYOUT_TO_TEXT,
        metric_names=("cer",),
    )
    result = _run(tmp_path, view)
    aggregate = result.pipelines[0].aggregate[0]  # type: ignore[attr-defined]
    assert aggregate.metric == "cer"
    # ref = "hello world\n\nsecond block", mise à plat par le profil par défaut
    # (D-285) : "hello world second block" (24 car.), 1 substitution → 1/24.
    assert aggregate.value == pytest.approx(1 / 24)
    assert aggregate.support == 1


def test_layout_candidate_without_projection_is_not_applicable(tmp_path: Path) -> None:
    # même corpus LAYOUT, mais la vue ne déclare AUCUNE projection → cer (texte)
    # ne peut pas s'appliquer : None, pas un score factice.
    view = EvaluationView(
        name="no-projection",
        candidate_types=frozenset({ArtifactType.LAYOUT}),
        metric_names=("cer",),
    )
    result = _run(tmp_path, view)
    aggregate = result.pipelines[0].aggregate[0]  # type: ignore[attr-defined]
    assert aggregate.value is None
    assert aggregate.support == 0
