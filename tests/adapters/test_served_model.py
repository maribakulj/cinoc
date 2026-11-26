"""Le modèle **servi** est lu dans la réponse de chaque fournisseur qui le rend (S9).

Défaut d'audit (D-260) : le manifeste ne gardait que l'alias **demandé**
(``gpt-4o-mini``), qui peut désigner un autre modèle d'un mois à l'autre — et la
tarification s'indexait dessus. Chaque conversion lit désormais ``model`` dans le
**corps** (celui que garde le sidecar), et l'étape le déclare
(``StepOutput.served_models``) ; l'exécuteur l'estampille dans la provenance.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters._native import public_endpoint, served_model
from cinoc.adapters.llm._base import LLMCompletion, run_llm_step
from cinoc.adapters.llm.anthropic import _completion_from_message
from cinoc.adapters.llm.mistral import _completion_from_chat as mistral_completion
from cinoc.adapters.llm.ollama import _completion_from_chat as ollama_completion
from cinoc.adapters.llm.openai import _completion_from_chat as openai_completion
from cinoc.adapters.ocr.azure_di import AzureDocIntelAdapter
from cinoc.adapters.ocr.mistral_ocr import MistralOCRAdapter
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.adapters._native_fakes import install_fake_sdks, set_keys, wire


@pytest.mark.parametrize(
    ("provider", "scenario", "read", "attendu"),
    [
        ("openai", "stop", openai_completion, "gpt-4o-mini-2024-07-18"),
        (
            "anthropic",
            "end_turn",
            _completion_from_message,
            "claude-haiku-4-5-20251001",
        ),
        ("mistral", "stop", mistral_completion, "mistral-small-2506"),
        (
            "ollama",
            "stop",
            lambda b: ollama_completion(b, "qwen2.5vl:3b"),
            "qwen2.5vl:3b",
        ),
    ],
)
def test_each_conversion_reads_the_served_model_from_the_body(
    provider: str, scenario: str, read: object, attendu: str
) -> None:
    completion = read(wire("llm", provider, scenario))  # type: ignore[operator]
    assert completion.model == attendu


def test_a_silent_response_serves_no_model() -> None:
    assert served_model({"choices": []}) is None
    assert served_model({"model": ""}) is None
    assert served_model([]) is None
    assert openai_completion({"choices": []}).model is None


def _context(tmp_path: Path) -> RunContext:
    return RunContext(
        document_id="d", code_version="1", pipeline_name="p",
        workspace_uri=str(tmp_path),
    )


def test_the_llm_step_declares_what_was_served(tmp_path: Path) -> None:
    source = tmp_path / "d.txt"
    source.write_text("texte", encoding="utf-8")
    inputs = {
        ArtifactType.RAW_TEXT: Artifact(
            id="t", document_id="d", type=ArtifactType.RAW_TEXT, uri=str(source)
        )
    }
    kwargs = dict(
        role="text_only", label="x", name="openai:x", prompt="{ocr_text}",
        inputs=inputs, context=_context(tmp_path), control=RunControl(),
        vision_invoke=None,
    )
    served = run_llm_step(
        text_invoke=lambda _p: LLMCompletion("ok", model="gpt-4o-2024-08-06"),
        **kwargs,  # type: ignore[arg-type]
    )
    assert served.served_models == ("gpt-4o-2024-08-06",)
    silent = run_llm_step(text_invoke=lambda _p: LLMCompletion("ok"), **kwargs)  # type: ignore[arg-type]
    assert silent.served_models == ()


def test_mistral_ocr_declares_the_served_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_keys(monkeypatch)
    install_fake_sdks(
        monkeypatch, {"mistral_ocr": lambda: wire("ocr", "mistral_ocr", "folio_a")}
    )
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG")
    output = MistralOCRAdapter(label="m").execute(
        {ArtifactType.IMAGE: Artifact(
            id="i", document_id="d", type=ArtifactType.IMAGE, uri=str(image)
        )},
        {},
        _context(tmp_path),
        RunControl(),
    )
    assert output.served_models == ("mistral-ocr-2505",)
    assert MistralOCRAdapter(label="m").effective_settings() == {
        "model": "mistral-ocr-latest"
    }


def test_the_azure_endpoint_is_read_once_and_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AZURE_DOC_INTEL_ENDPOINT", "https://k:s@res.cognitiveservices.azure.com/"
    )
    adapter = AzureDocIntelAdapter(label="az")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", "https://autre.example")
    assert adapter.effective_settings() == {
        "endpoint": "https://res.cognitiveservices.azure.com/",
        "model": "prebuilt-read",
        "api_version": "2024-11-30",
    }


def test_an_endpoint_is_written_without_credentials_or_query() -> None:
    assert public_endpoint("http://u:p@h:8000/v1?key=s#f") == "http://h:8000/v1"
