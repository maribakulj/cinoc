"""``MistralOCRAdapter`` : contrat module, sortie texte, erreurs propres."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.ocr.mistral_ocr import MistralOCRAdapter
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext


def _ctx(workspace: Path) -> RunContext:
    return RunContext(
        document_id="d1", code_version="t", pipeline_name="p",
        workspace_uri=str(workspace),
    )


def _image(tmp_path: Path) -> Artifact:
    path = tmp_path / "page.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return Artifact(
        id="d1:img", document_id="d1", type=ArtifactType.IMAGE, uri=str(path)
    )


def test_satisfies_module_protocol() -> None:
    adapter = MistralOCRAdapter(label="ocr")
    assert isinstance(adapter, Module)
    assert adapter.name == "mistral_ocr:ocr"
    assert adapter.input_types == frozenset({ArtifactType.IMAGE})
    assert adapter.output_types == frozenset(
        {ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON}
    )


def test_execute_writes_markdown_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "cinoc.adapters.ocr.mistral_ocr._invoke_mistral_ocr",
        lambda **_: {"pages": [{"index": 0, "markdown": "# Page\n\ntexte reconnu"}]},
    )
    out = MistralOCRAdapter(label="ocr").execute(
        {ArtifactType.IMAGE: _image(tmp_path)}, {}, _ctx(tmp_path), RunControl()
    )
    artifact = out.artifacts[ArtifactType.RAW_TEXT]
    assert artifact.uri is not None
    assert "texte reconnu" in Path(artifact.uri).read_text(encoding="utf-8")


def test_missing_image_raises(tmp_path: Path) -> None:
    with pytest.raises(AdapterStepError):
        MistralOCRAdapter(label="ocr").execute({}, {}, _ctx(tmp_path), RunControl())
