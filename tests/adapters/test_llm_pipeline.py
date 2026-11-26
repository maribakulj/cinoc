"""Pipelines multi-étapes OCR → LLM/VLM : ``text_only``, ``text_and_image``,
``zero_shot`` produisent l'artefact attendu via l'executor (DAG ``inputs_from``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.llm._base import LLMCompletion
from cinoc.adapters.llm.openai import OpenAIAdapter
from cinoc.adapters.ocr.precomputed import PrecomputedTextAdapter
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.pipeline.executor import PipelineExecutor


def _image(tmp_path: Path) -> Artifact:
    (tmp_path / "doc1.png").write_bytes(b"\x89PNG\r\n\x1a\n fake")
    return Artifact(
        id="doc1:init:image",
        document_id="doc1",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "doc1.png"),
    )


def test_ocr_then_llm_produces_corrected_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "doc1.eng.txt").write_text("Hello wrld", encoding="utf-8")
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai",
        lambda **_: LLMCompletion("Hello world"),
    )
    ocr = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="precomputed:eng",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    llm = PipelineStep(
        id="llm",
        kind="post_correction",
        adapter_name="openai:gpt",
        input_types=(ArtifactType.RAW_TEXT,),
        output_types=(ArtifactType.CORRECTED_TEXT,),
        inputs_from={ArtifactType.RAW_TEXT: "ocr"},
    )
    spec = PipelineSpec(
        name="ocr_llm", initial_inputs=(ArtifactType.IMAGE,), steps=(ocr, llm)
    )
    modules = {
        "precomputed:eng": PrecomputedTextAdapter(source_label="eng"),
        "openai:gpt": OpenAIAdapter(model="m", label="gpt"),
    }

    pool = PipelineExecutor("1.0").execute_document(
        spec,
        modules,
        {ArtifactType.IMAGE: _image(tmp_path)},
        document_id="doc1",
        workspace_uri=str(tmp_path),
    )

    assert ArtifactType.CORRECTED_TEXT in pool.artifacts
    corrected = pool.artifacts[ArtifactType.CORRECTED_TEXT]
    assert corrected.uri is not None
    assert Path(corrected.uri).read_text(encoding="utf-8") == "Hello world"


def test_ocr_then_vlm_correction_receives_image_and_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``text_and_image`` : le step LLM reçoit IMAGE (initial) ET RAW_TEXT (OCR)."""
    (tmp_path / "doc1.eng.txt").write_text("Helo", encoding="utf-8")
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai_vision",
        lambda **_: LLMCompletion("Hello"),
    )
    ocr = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="precomputed:eng",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    vlm = PipelineStep(
        id="llm",
        kind="post_correction",
        adapter_name="openai:gpt",
        input_types=(ArtifactType.RAW_TEXT, ArtifactType.IMAGE),
        output_types=(ArtifactType.CORRECTED_TEXT,),
        inputs_from={
            ArtifactType.RAW_TEXT: "ocr",
            ArtifactType.IMAGE: "__initial__",
        },
    )
    spec = PipelineSpec(
        name="ocr_vlm", initial_inputs=(ArtifactType.IMAGE,), steps=(ocr, vlm)
    )
    modules = {
        "precomputed:eng": PrecomputedTextAdapter(source_label="eng"),
        "openai:gpt": OpenAIAdapter(model="m", label="gpt", role="text_and_image"),
    }

    pool = PipelineExecutor("1.0").execute_document(
        spec,
        modules,
        {ArtifactType.IMAGE: _image(tmp_path)},
        document_id="doc1",
        workspace_uri=str(tmp_path),
    )

    corrected = pool.artifacts[ArtifactType.CORRECTED_TEXT]
    assert corrected.uri is not None
    assert Path(corrected.uri).read_text(encoding="utf-8") == "Hello"


def test_zero_shot_vlm_transcribes_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``zero_shot`` : un seul step VLM (IMAGE → RAW_TEXT), sans OCR amont."""
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai_vision",
        lambda **_: LLMCompletion("Transcribed"),
    )
    vlm = PipelineStep(
        id="vlm",
        kind="transcription",
        adapter_name="openai:v",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    spec = PipelineSpec(
        name="zero", initial_inputs=(ArtifactType.IMAGE,), steps=(vlm,)
    )
    modules = {"openai:v": OpenAIAdapter(model="m", label="v", role="zero_shot")}

    pool = PipelineExecutor("1.0").execute_document(
        spec,
        modules,
        {ArtifactType.IMAGE: _image(tmp_path)},
        document_id="doc1",
        workspace_uri=str(tmp_path),
    )

    raw = pool.artifacts[ArtifactType.RAW_TEXT]
    assert raw.uri is not None
    assert Path(raw.uri).read_text(encoding="utf-8") == "Transcribed"
