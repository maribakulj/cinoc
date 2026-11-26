"""``OpenAIAdapter`` : conformité Module + 3 modes (text_only/image/zero_shot)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.llm._base import LLMCompletion, normalize_llm_content
from cinoc.adapters.llm.openai import OpenAIAdapter
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError, RunCancelledError
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext


def _raw_text(path: Path) -> Artifact:
    return Artifact(
        id="doc1:ocr:raw_text",
        document_id="doc1",
        type=ArtifactType.RAW_TEXT,
        uri=str(path),
    )


def _image(path: Path) -> Artifact:
    path.write_bytes(b"\x89PNG\r\n\x1a\n fake-bytes")
    return Artifact(
        id="doc1:init:image",
        document_id="doc1",
        type=ArtifactType.IMAGE,
        uri=str(path),
    )


def _ctx(workspace: Path) -> RunContext:
    return RunContext(
        document_id="doc1",
        code_version="t",
        pipeline_name="p",
        workspace_uri=str(workspace),
    )


def _mock_text(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai", lambda **_: LLMCompletion(text)
    )


def _mock_vision(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai_vision",
        lambda **_: LLMCompletion(text),
    )


def test_satisfies_module_protocol() -> None:
    adapter = OpenAIAdapter(label="gpt", model="gpt-4o-mini")
    assert isinstance(adapter, Module)
    assert adapter.name == "openai:gpt"
    assert adapter.input_types == frozenset({ArtifactType.RAW_TEXT})
    assert adapter.output_types == frozenset(
        {ArtifactType.CORRECTED_TEXT, ArtifactType.NATIVE_JSON}
    )


def test_invalid_label_rejected() -> None:
    with pytest.raises(AdapterStepError):
        OpenAIAdapter(model="m", label="bad label")


def test_invalid_role_rejected() -> None:
    with pytest.raises(AdapterStepError):
        OpenAIAdapter(model="m", label="gpt", role="bogus")


def test_role_types() -> None:
    ti = OpenAIAdapter(model="m", label="a", role="text_and_image")
    assert ti.input_types == frozenset(
        {ArtifactType.RAW_TEXT, ArtifactType.IMAGE}
    )
    assert ti.output_types == frozenset(
        {ArtifactType.CORRECTED_TEXT, ArtifactType.NATIVE_JSON}
    )
    zs = OpenAIAdapter(model="m", label="b", role="zero_shot")
    assert zs.input_types == frozenset({ArtifactType.IMAGE})
    assert zs.output_types == frozenset(
        {ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON}
    )


def test_execute_produces_corrected_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ocr.txt").write_text("Hello wrld", encoding="utf-8")
    _mock_text(monkeypatch, "Hello world")
    adapter = OpenAIAdapter(model="m", label="gpt")
    out = adapter.execute(
        {ArtifactType.RAW_TEXT: _raw_text(tmp_path / "ocr.txt")},
        {},
        _ctx(tmp_path),
        RunControl(),
    )
    artifact = out.artifacts[ArtifactType.CORRECTED_TEXT]
    assert artifact.type == ArtifactType.CORRECTED_TEXT
    assert artifact.uri is not None
    assert Path(artifact.uri).read_text(encoding="utf-8") == "Hello world"
    assert artifact.content_hash is not None


def test_text_and_image_produces_corrected_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ocr.txt").write_text("Helo", encoding="utf-8")
    _mock_vision(monkeypatch, "Hello")
    adapter = OpenAIAdapter(model="m", label="v", role="text_and_image")
    out = adapter.execute(
        {
            ArtifactType.RAW_TEXT: _raw_text(tmp_path / "ocr.txt"),
            ArtifactType.IMAGE: _image(tmp_path / "doc1.png"),
        },
        {},
        _ctx(tmp_path),
        RunControl(),
    )
    artifact = out.artifacts[ArtifactType.CORRECTED_TEXT]
    assert artifact.uri is not None
    assert Path(artifact.uri).read_text(encoding="utf-8") == "Hello"


def test_zero_shot_produces_raw_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_vision(monkeypatch, "Transcribed text")
    adapter = OpenAIAdapter(model="m", label="v", role="zero_shot")
    out = adapter.execute(
        {ArtifactType.IMAGE: _image(tmp_path / "doc1.png")},
        {},
        _ctx(tmp_path),
        RunControl(),
    )
    artifact = out.artifacts[ArtifactType.RAW_TEXT]
    assert artifact.type == ArtifactType.RAW_TEXT
    assert artifact.uri is not None
    assert Path(artifact.uri).read_text(encoding="utf-8") == "Transcribed text"


def test_requires_workspace() -> None:
    adapter = OpenAIAdapter(model="m", label="gpt")
    ctx = RunContext(document_id="doc1", code_version="t", pipeline_name="p")
    with pytest.raises(AdapterStepError):
        adapter.execute(
            {ArtifactType.RAW_TEXT: _raw_text(Path("/tmp/x"))},
            {},
            ctx,
            RunControl(),
        )


def test_missing_input_raises(tmp_path: Path) -> None:
    adapter = OpenAIAdapter(model="m", label="gpt")
    with pytest.raises(AdapterStepError):
        adapter.execute({}, {}, _ctx(tmp_path), RunControl())


def test_zero_shot_missing_image_raises(tmp_path: Path) -> None:
    adapter = OpenAIAdapter(model="m", label="v", role="zero_shot")
    with pytest.raises(AdapterStepError):
        adapter.execute({}, {}, _ctx(tmp_path), RunControl())


def test_cancellation_raises(tmp_path: Path) -> None:
    adapter = OpenAIAdapter(model="m", label="gpt")
    control = RunControl()
    control.trigger_cancel()
    with pytest.raises(RunCancelledError):
        adapter.execute(
            {ArtifactType.RAW_TEXT: _raw_text(tmp_path / "x.txt")},
            {},
            _ctx(tmp_path),
            control,
        )


def test_normalize_llm_content() -> None:
    assert normalize_llm_content("abc") == "abc"
    assert normalize_llm_content(None) == ""
    assert normalize_llm_content(["a", "b"]) == "ab"
    assert normalize_llm_content([{"text": "x"}, {"text": "y"}]) == "xy"
