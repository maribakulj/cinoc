"""Squelette ambulant de la tranche segmentation (T5), de bout en bout.

Prouve que l'enveloppe (LAYOUT + region_id + Module) porte le fan-out : source de
mise en page ``precomputed`` (régions seules) → reconnaissance **par région** →
LAYOUT rempli → métrique ``region_cer`` (CER par bloc agrégé page) → rapport. Tout
en ``precomputed`` (0 dépendance, déterministe, CI-safe).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.adapters.layout.precomputed import (
    PrecomputedLayoutSource,
    PrecomputedRegionRecognizer,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Line, Region
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.layout import region_cer
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run
from cinoc.pipeline.fanout import run_region_fanout
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from cinoc.reports.renderer import default_report_renderer

FIXED = datetime(2026, 1, 1, tzinfo=UTC)
LAYOUT_VIEW = EvaluationView(
    name="structure",
    candidate_types=frozenset({ArtifactType.LAYOUT}),
    metric_names=("region_cer",),
)


def _segmentation_layout() -> CanonicalLayout:
    """Sortie de segmentation : 2 régions, **aucune ligne** (texte à remplir)."""
    return CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(
                    Region(id="r1", region_type="text"),
                    Region(id="r2", region_type="text"),
                ),
                reading_order=("r1", "r2"),
            ),
        )
    )


def _gt_layout() -> CanonicalLayout:
    """GT : régions avec texte de référence."""
    return CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(
                    Region(id="r1", lines=(Line(text="hello world"),)),
                    Region(id="r2", lines=(Line(text="second block"),)),
                ),
            ),
        )
    )


def _scene(tmp_path: Path, regions: dict[str, str]) -> tuple[Artifact, RunContext]:
    """Pose image + mise en page + textes par région, renvoie l'IMAGE et un ctx."""
    image = tmp_path / "doc1.png"
    image.write_bytes(b"\x89PNG stub")
    (tmp_path / "doc1.layout.json").write_bytes(
        _segmentation_layout().model_dump_json().encode("utf-8")
    )
    import json

    (tmp_path / "doc1.eng.regions.json").write_text(
        json.dumps(regions), encoding="utf-8"
    )
    image_art = Artifact(
        id="doc1:initial:image",
        document_id="doc1",
        type=ArtifactType.IMAGE,
        uri=str(image),
    )
    context = RunContext(
        document_id="doc1",
        code_version="1.0",
        pipeline_name="seg",
        workspace_uri=str(tmp_path),
    )
    return image_art, context


def _run_skeleton(
    tmp_path: Path, regions: dict[str, str]
) -> CanonicalLayout:
    """Segmentation precomputed → fan-out reconnaissance → LAYOUT rempli."""
    image_art, context = _scene(tmp_path, regions)
    control = RunControl()
    layout_out = PrecomputedLayoutSource().execute(
        {ArtifactType.IMAGE: image_art}, {}, context, control
    )
    layout_art = layout_out.artifacts[ArtifactType.LAYOUT]
    assert layout_art.uri is not None
    seg_layout = CanonicalLayout.model_validate_json(
        Path(layout_art.uri).read_bytes()
    )
    filled, _usage = run_region_fanout(
        layout=seg_layout,
        page_image=image_art,
        recognizer=PrecomputedRegionRecognizer(source_label="eng"),
        context=context,
        control=control,
    )
    return filled


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


def _evaluate(tmp_path: Path, filled: CanonicalLayout) -> object:
    hyp_path = tmp_path / "doc1.assembled.layout.json"
    hyp_path.write_bytes(filled.model_dump_json().encode("utf-8"))
    gt_path = tmp_path / "doc1.gt_layout.json"
    gt_path.write_bytes(_gt_layout().model_dump_json().encode("utf-8"))
    doc = DocumentRef(
        id="doc1",
        ground_truths=(GroundTruthRef(type=ArtifactType.LAYOUT, uri=str(gt_path)),),
    )
    outputs = {
        "seg": {
            "doc1": {
                "ocr": {
                    ArtifactType.LAYOUT: Artifact(
                        id="doc1:assemble:layout",
                        document_id="doc1",
                        type=ArtifactType.LAYOUT,
                        uri=str(hyp_path),
                    )
                }
            }
        }
    }
    return evaluate_run(
        corpus=CorpusSpec(name="c", documents=(doc,)),
        evaluation=EvaluationSpec(views=(LAYOUT_VIEW,)),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=_manifest(),
    )


def test_fanout_fills_each_region(tmp_path: Path) -> None:
    filled = _run_skeleton(
        tmp_path, {"r1": "hello world", "r2": "second blocX"}
    )
    page = filled.pages[0]
    assert page.regions[0].lines[0].text == "hello world"
    assert page.regions[1].lines[0].text == "second blocX"
    # l'ordre de lecture et la structure sont préservés
    assert page.reading_order == ("r1", "r2")


def test_end_to_end_region_cer(tmp_path: Path) -> None:
    # r1 exact (0/11) ; r2 1 substitution (1/12) → micro page = 1/23.
    filled = _run_skeleton(
        tmp_path, {"r1": "hello world", "r2": "second blocX"}
    )
    result = _evaluate(tmp_path, filled)
    aggregate = result.pipelines[0].aggregate[0]  # type: ignore[attr-defined]
    assert aggregate.metric == "region_cer"
    assert aggregate.value == pytest.approx(1 / 23)
    assert aggregate.support == 1
    doc_score = result.documents[0].scores[0]  # type: ignore[attr-defined]
    assert doc_score.value == pytest.approx(1 / 23)
    # Σ caractères de référence (11 + 12), dans la statistique (K1).
    assert doc_score.stat.reference_length == 23
    # C7 : la colonne de la métrique de structure apparaît sans rendu modifié.
    html = default_report_renderer().render(result)  # type: ignore[arg-type]
    assert "region_cer" in html


def test_partial_failure_does_not_abort_page(tmp_path: Path) -> None:
    # r2 absente des textes precomputed → reconnaissance échoue pour r2 seule.
    filled = _run_skeleton(tmp_path, {"r1": "hello world"})
    page = filled.pages[0]
    assert page.regions[0].lines[0].text == "hello world"
    assert page.regions[1].lines == ()  # r2 laissée vide, page non abattue
    # r1 exact (0/11) ; r2 vide → suppression totale de "second block" (12/12).
    result = _evaluate(tmp_path, filled)
    aggregate = result.pipelines[0].aggregate[0]  # type: ignore[attr-defined]
    assert aggregate.value == pytest.approx(12 / 23)


def test_fanout_is_deterministic(tmp_path: Path) -> None:
    first = _run_skeleton(tmp_path, {"r1": "a", "r2": "b"})
    second = _run_skeleton(tmp_path, {"r1": "a", "r2": "b"})
    assert first.model_dump_json() == second.model_dump_json()


def test_segmentation_only_layout_is_not_applicable() -> None:
    # hypothèse = régions sans lignes (niveau texte absent) → None.
    ctx = DocContext(
        document_id="doc1",
        reference=_gt_layout(),
        hypothesis=_segmentation_layout(),
    )
    assert region_cer.fn(ctx) is None


def test_recognizer_requires_region_id(tmp_path: Path) -> None:
    image = tmp_path / "doc1.png"
    image.write_bytes(b"stub")
    (tmp_path / "doc1.eng.regions.json").write_text("{}", encoding="utf-8")
    image_art = Artifact(
        id="doc1:initial:image",
        document_id="doc1",
        type=ArtifactType.IMAGE,
        uri=str(image),
    )
    context = RunContext(document_id="doc1", code_version="1.0", pipeline_name="seg")
    with pytest.raises(AdapterStepError, match="region_id"):
        PrecomputedRegionRecognizer(source_label="eng").execute(
            {ArtifactType.IMAGE: image_art}, {}, context, RunControl()
        )
