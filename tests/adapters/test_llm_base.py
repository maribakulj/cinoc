"""Helpers partagés des adapters LLM/VLM : modes, image base64, écriture."""

from __future__ import annotations

from base64 import b64decode
from pathlib import Path

import pytest

from cinoc.adapters.llm._base import (
    DEFAULT_CORRECTION_PROMPT,
    DEFAULT_TRANSCRIPTION_PROMPT,
    default_prompt_for_role,
    llm_input_types,
    llm_output_type,
    load_image_b64,
    validate_role,
    write_text_artifact,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError


def _image_inputs(path: Path, data: bytes) -> dict[ArtifactType, Artifact]:
    path.write_bytes(data)
    return {
        ArtifactType.IMAGE: Artifact(
            id="d:i:image",
            document_id="d",
            type=ArtifactType.IMAGE,
            uri=str(path),
        )
    }


def test_llm_input_types_per_role() -> None:
    assert llm_input_types("text_only") == frozenset({ArtifactType.RAW_TEXT})
    assert llm_input_types("text_and_image") == frozenset(
        {ArtifactType.RAW_TEXT, ArtifactType.IMAGE}
    )
    assert llm_input_types("zero_shot") == frozenset({ArtifactType.IMAGE})


def test_llm_output_type_per_role() -> None:
    assert llm_output_type("text_only") == ArtifactType.CORRECTED_TEXT
    assert llm_output_type("text_and_image") == ArtifactType.CORRECTED_TEXT
    assert llm_output_type("zero_shot") == ArtifactType.RAW_TEXT


def test_default_prompt_for_role() -> None:
    assert default_prompt_for_role("text_only") == DEFAULT_CORRECTION_PROMPT
    assert default_prompt_for_role("text_and_image") == DEFAULT_CORRECTION_PROMPT
    assert default_prompt_for_role("zero_shot") == DEFAULT_TRANSCRIPTION_PROMPT


def test_validate_role_accepts_supported() -> None:
    assert validate_role("zero_shot", "X", frozenset({"zero_shot"})) == "zero_shot"


def test_validate_role_rejects_unsupported() -> None:
    with pytest.raises(AdapterStepError):
        validate_role("zero_shot", "X", frozenset({"text_only"}))


def test_load_image_b64_png(tmp_path: Path) -> None:
    media_type, b64 = load_image_b64(
        _image_inputs(tmp_path / "x.png", b"hello"), "X"
    )
    assert media_type == "image/png"
    assert b64decode(b64) == b"hello"


def test_load_image_b64_jpeg_media_type(tmp_path: Path) -> None:
    media_type, _ = load_image_b64(
        _image_inputs(tmp_path / "x.jpg", b"jpg"), "X"
    )
    assert media_type == "image/jpeg"


def test_load_image_b64_jp2_is_announced_as_jp2(tmp_path: Path) -> None:
    """Rouge avant D-303 : un JPEG 2000 partait annoncé ``image/png``."""
    media_type, _ = load_image_b64(_image_inputs(tmp_path / "x.JP2", b"j"), "X")
    assert media_type == "image/jp2"


def test_load_image_b64_unknown_suffix_is_refused(tmp_path: Path) -> None:
    """Hors de la table des imports, refus nommé — plus de défaut ``image/png``."""
    with pytest.raises(AdapterStepError, match=r"X : extension d'image non gérée"):
        load_image_b64(_image_inputs(tmp_path / "x.gif", b"g"), "X")


def test_load_image_b64_missing_raises() -> None:
    with pytest.raises(AdapterStepError):
        load_image_b64({}, "X")


def test_write_text_artifact_raw_vs_corrected(tmp_path: Path) -> None:
    raw = write_text_artifact(
        str(tmp_path), "d", "lbl", "k:lbl", "t",
        output_type=ArtifactType.RAW_TEXT,
    )
    corrected = write_text_artifact(
        str(tmp_path), "d", "lbl", "k:lbl", "t",
        output_type=ArtifactType.CORRECTED_TEXT,
    )
    assert ArtifactType.RAW_TEXT in raw
    assert ArtifactType.CORRECTED_TEXT in corrected
    # noms de fichiers distincts → raw et corrected ne se piétinent pas.
    assert raw[ArtifactType.RAW_TEXT].uri != corrected[ArtifactType.CORRECTED_TEXT].uri
