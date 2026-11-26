"""Projection layout→texte sur **données réelles** (BnL « D'Wäschfra », 1868, CC0).

Deux niveaux :
- **déterministe** (toujours) : l'extrait ALTO ABBYY réel committé se projette en
  texte allemand réel et traverse le runner (réserve §9 ProjectionSpec levée sur
  du vrai) ;
- **`live`** (opt-in) : un vrai Tesseract sur une vraie image (chemin via
  ``CINOC_BNL_IMAGE``) → ALTO → mêmes mappers → projection — le chemin compétitif
  réel, sans committer d'image lourde.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.projection import ProjectionSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.projectors import layout_to_text
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.representations import load_representation
from cinoc.evaluation.runner import evaluate_run

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures" / "reference_corpus" / "bnl_waeschfra"
    / "waeschfra_p2_excerpt.alto.xml"
)
FIXED = datetime(2026, 1, 1, tzinfo=UTC)
_LAYOUT_TO_TEXT = ProjectionSpec(
    source_type=ArtifactType.LAYOUT,
    target_type=ArtifactType.RAW_TEXT,
    projector_name="layout_to_text",
)


def test_real_alto_projects_to_german_text() -> None:
    layout = load_representation(str(_FIXTURE), ArtifactType.LAYOUT)
    text = layout_to_text(layout, {})
    assert isinstance(text, str)
    assert "Actualität" in text  # vrai mot du journal réel
    assert len(text) > 400  # extrait de 3 blocs réels


def test_real_alto_scored_through_runner() -> None:
    # GT = ALTO réel ; candidat = le même ALTO réel → projeté texte des deux côtés,
    # CER = 0 : la projection traverse le vrai runner et reste applicable (pas None).
    doc = DocumentRef(
        id="waeschfra_p2",
        ground_truths=(
            GroundTruthRef(type=ArtifactType.LAYOUT, uri=str(_FIXTURE)),
        ),
    )
    candidate = Artifact(
        id="waeschfra_p2:cand:layout",
        document_id="waeschfra_p2",
        type=ArtifactType.LAYOUT,
        uri=str(_FIXTURE),
    )
    registry = MetricRegistry()
    register_default_metrics(registry)
    result = evaluate_run(
        corpus=CorpusSpec(name="bnl", documents=(doc,)),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="text-of-layout",
                    candidate_types=frozenset({ArtifactType.LAYOUT}),
                    projection=_LAYOUT_TO_TEXT,
                    metric_names=("cer",),
                ),
            )
        ),
        pipeline_outputs={
            "abbyy": {"waeschfra_p2": {"ocr": {ArtifactType.LAYOUT: candidate}}}
        },
        registry=registry,
        manifest=RunManifest(
            run_id="r",
            corpus_name="bnl",
            n_documents=1,
            pipeline_specs=(
                PipelineSpec(name="abbyy", initial_inputs=(ArtifactType.IMAGE,)),
            ),
            code_version="1.0",
            started_at=FIXED,
            completed_at=FIXED,
        ),
    )
    aggregate = result.pipelines[0].aggregate[0]
    assert aggregate.metric == "cer"
    assert aggregate.value == 0.0
    assert aggregate.support == 1


@pytest.mark.live
def test_live_tesseract_real_image_through_mappers() -> None:
    """Vrai Tesseract sur une vraie image → ALTO → mappers → projection texte.

    Opt-in : exige le binaire ``tesseract`` et ``CINOC_BNL_IMAGE`` pointant une
    image réelle (TIFF/PNG non committé). Prouve le chemin compétitif de bout en
    bout sur de la vraie donnée.
    """
    if shutil.which("tesseract") is None:
        pytest.skip("binaire tesseract absent")
    image = os.environ.get("CINOC_BNL_IMAGE")
    if not image or not Path(image).is_file():
        pytest.skip("CINOC_BNL_IMAGE non fourni")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "out"
        subprocess.run(
            ["tesseract", image, str(base), "-l", "deu", "alto"],
            check=True, capture_output=True,
        )
        alto_path = base.with_suffix(".xml")
        layout = load_representation(str(alto_path), ArtifactType.LAYOUT)
        text = layout_to_text(layout, {})
    assert isinstance(text, str)
    assert sum(c.isalpha() for c in text) > 50  # vrai texte reconnu, non vide
