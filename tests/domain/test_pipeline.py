from __future__ import annotations

import typing

import pytest

from cinoc.domain import (
    INITIAL_STEP_ID,
    ArtifactType,
    PipelineMode,
    PipelineSpec,
    PipelineStep,
)
from cinoc.domain.errors import CinocError


def test_pipeline_mode_values():
    """Les quatre modes d'une étape LLM/VLM.

    ``refine`` (D-236) est le seul dont l'entrée **et** la sortie sont du texte
    corrigé : c'est lui qui rend une chaîne de correcteurs exprimable.
    """
    assert set(typing.get_args(PipelineMode)) == {
        "text_only",
        "text_and_image",
        "zero_shot",
        "refine",
    }


def test_reserved_step_id_rejected():
    with pytest.raises(CinocError):
        PipelineStep(id=INITIAL_STEP_ID, kind="ocr", adapter_name="t")


def test_bad_step_id_rejected():
    with pytest.raises(CinocError):
        PipelineStep(id="bad id", kind="ocr", adapter_name="t")


def test_spec_step_lookup():
    step = PipelineStep(
        id="ocr", kind="ocr", adapter_name="t",
        output_types=(ArtifactType.RAW_TEXT,),
    )
    spec = PipelineSpec(name="p", steps=(step,))
    assert spec.step_by_id("ocr") is step
    assert spec.step_by_id("x") is None
