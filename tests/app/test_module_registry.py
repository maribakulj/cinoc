"""Registre + factory de modules : résolution, validations, rôles LLM."""

from __future__ import annotations

import pytest

from cinoc.app.modules.registry import (
    ModuleRegistry,
    ModuleResolutionError,
    register_default_modules,
)
from cinoc.domain.artifacts import ArtifactType
from cinoc.pipeline.protocols import Module


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def test_builds_precomputed_module() -> None:
    module = _registry().build("precomputed:tesseract", {"source_label": "tesseract"})
    assert isinstance(module, Module)
    assert module.name == "precomputed:tesseract"


def test_kinds_listed() -> None:
    assert _registry().kinds() == (
        "alto_assembler",
        "alto_source",
        "anthropic",
        "azure_di",
        "calamari",
        "google_vision",
        "kraken",
        "layout_to_text",
        "mistral",
        "mistral_ocr",
        "ner",
        "ollama",
        "openai",
        "pero",
        "pp_doclayout",
        "precomputed",
        "precomputed_layout",
        "precomputed_region",
        "preprocess",
        "reading_order",
        "remote_segmenter",
        "saknussemm",
        "tesseract",
        "vote",
    )


def test_builds_tesseract_module() -> None:
    module = _registry().build("tesseract:fra", {"label": "fra", "lang": "fra"})
    assert module.name == "tesseract:fra"


def test_tesseract_alto_kwarg_enables_alto_output() -> None:
    plain = _registry().build("tesseract:fra", {"label": "fra"})
    assert ArtifactType.ALTO_XML not in plain.output_types
    with_alto = _registry().build("tesseract:fra", {"label": "fra", "alto": True})
    assert ArtifactType.ALTO_XML in with_alto.output_types


def test_builds_pero_and_calamari_modules() -> None:
    pero = _registry().build("pero:c0", {"label": "c0", "model": "config.ini"})
    assert pero.name == "pero:c0"
    assert pero.output_types == frozenset({ArtifactType.RAW_TEXT})
    cal = _registry().build("calamari:c0", {"label": "c0", "model": "ckpt"})
    assert cal.name == "calamari:c0"
    assert cal.output_types == frozenset({ArtifactType.RAW_TEXT})


def test_pero_requires_model() -> None:
    with pytest.raises(ModuleResolutionError):
        _registry().build("pero:c0", {"label": "c0"})


def test_builds_ner_module() -> None:
    module = _registry().build("ner:c0", {"label": "c0", "model": "fr_core_news_sm"})
    assert module.name == "ner:c0"
    assert module.output_types == frozenset({ArtifactType.ENTITIES})
    assert ArtifactType.RAW_TEXT in module.input_types


def test_ner_requires_label() -> None:
    with pytest.raises(ModuleResolutionError):
        _registry().build("ner:c0", {})


def test_pp_doclayout_model_from_env_and_kwarg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # L'image Space bake la variante légère via CINOC_PPDOCLAYOUT_MODEL ; un kwarg
    # explicite l'emporte ; défaut = -L.
    monkeypatch.delenv("CINOC_PPDOCLAYOUT_MODEL", raising=False)
    assert _registry().build("pp_doclayout", {})._model == "PP-DocLayout-L"
    monkeypatch.setenv("CINOC_PPDOCLAYOUT_MODEL", "PP-DocLayout-S")
    assert _registry().build("pp_doclayout", {})._model == "PP-DocLayout-S"
    assert (
        _registry().build("pp_doclayout", {"model": "PP-DocLayout-M"})._model
        == "PP-DocLayout-M"
    )


def test_builds_remote_segmenter_module() -> None:
    module = _registry().build(
        "remote_segmenter", {"endpoint": "https://example.org/seg"}
    )
    assert module.name == "remote_segmenter"
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert module.output_types == frozenset({ArtifactType.LAYOUT})


def test_remote_segmenter_requires_endpoint() -> None:
    with pytest.raises(ModuleResolutionError):
        _registry().build("remote_segmenter", {})


def test_builds_azure_di_module() -> None:
    module = _registry().build("azure_di:c0", {"label": "c0", "lang": "fra"})
    assert module.name == "azure_di:c0"
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert module.output_types == frozenset({ArtifactType.RAW_TEXT})


def test_builds_google_vision_module() -> None:
    # Le planificateur passe un `lang` à tout moteur OCR : le builder le tolère
    # (Vision détecte la langue, pas de hint) et résout le bon module.
    module = _registry().build("google_vision:c0", {"label": "c0", "lang": "fra"})
    assert module.name == "google_vision:c0"
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert module.output_types == frozenset({ArtifactType.RAW_TEXT})


def test_builds_anthropic_with_role() -> None:
    module = _registry().build(
        "anthropic:claude", {"label": "claude", "role": "zero_shot"}
    )
    assert module.name == "anthropic:claude"
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert module.output_types == frozenset({ArtifactType.RAW_TEXT})


def test_builds_openai_with_vision_role() -> None:
    module = _registry().build(
        "openai:v", {"label": "v", "role": "text_and_image"}
    )
    assert module.input_types == frozenset(
        {ArtifactType.RAW_TEXT, ArtifactType.IMAGE}
    )


def test_unknown_kind_raises() -> None:
    with pytest.raises(ModuleResolutionError):
        ModuleRegistry().build("mystery:x", {})


def test_missing_source_label_raises() -> None:
    with pytest.raises(ModuleResolutionError):
        _registry().build("precomputed:x", {})


def test_name_mismatch_raises() -> None:
    # nom déclaré "tesseract" mais kwargs construisent "pero" -> incohérence
    with pytest.raises(ModuleResolutionError):
        _registry().build("precomputed:tesseract", {"source_label": "pero"})
