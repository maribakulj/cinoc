"""``RunSpec`` : composition déclarative, au moins un pipeline."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationSpec
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run_spec import RunSpec


def test_valid_runspec() -> None:
    spec = RunSpec(
        corpus=CorpusSpec(name="c"),
        pipelines=(PipelineSpec(name="p", initial_inputs=(ArtifactType.IMAGE,)),),
        evaluation=EvaluationSpec(),
    )
    assert spec.run_id is None
    assert len(spec.pipelines) == 1
    assert spec.adapter_kwargs == {}


def test_requires_at_least_one_pipeline() -> None:
    with pytest.raises(ValidationError):
        RunSpec(
            corpus=CorpusSpec(name="c"),
            pipelines=(),
            evaluation=EvaluationSpec(),
        )


def _ocr_llm(name: str, *, llm_outputs: tuple[ArtifactType, ...]) -> PipelineSpec:
    from cinoc.domain.pipeline import PipelineStep

    return PipelineSpec(
        name=name,
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr",
                kind="ocr",
                adapter_name="x:ocr",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
            PipelineStep(
                id="llm",
                kind="post_correction",
                adapter_name="x:llm",
                input_types=(ArtifactType.RAW_TEXT,),
                output_types=llm_outputs,
            ),
        ),
    )


def _spec(*pipelines: PipelineSpec, target: str | None = None) -> RunSpec:
    from cinoc.domain.evaluation import EvaluationView

    view = EvaluationView(
        name="texte",
        candidate_types=frozenset(
            {ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT}
        ),
        metric_names=("cer",),
        target_step=target,
    )
    return RunSpec(
        corpus=CorpusSpec(name="c"),
        pipelines=pipelines,
        evaluation=EvaluationSpec(views=(view,)),
    )


def test_target_step_must_exist_in_every_pipeline() -> None:
    complet = _ocr_llm("complet", llm_outputs=(ArtifactType.CORRECTED_TEXT,))
    assert _spec(complet, target="ocr").evaluation.views[0].target_step == "ocr"
    seul = PipelineSpec(name="seul", initial_inputs=(ArtifactType.IMAGE,))
    with pytest.raises(CinocError, match="'llm' inconnue du pipeline 'seul'"):
        _spec(complet, seul, target="llm")


def test_a_scored_step_declaring_two_candidate_types_is_ambiguous() -> None:
    """Plus de précédence par type : l'étape visée doit déclarer **un** type
    candidat de la vue, sans quoi rien ne dit lequel noter."""
    double = _ocr_llm(
        "double",
        llm_outputs=(ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT),
    )
    with pytest.raises(CinocError, match="plusieurs types candidats"):
        _spec(double)
    # Viser l'étape amont, qui n'en déclare qu'un, lève l'ambiguïté.
    assert _spec(double, target="ocr").pipelines == (double,)
