"""La réponse native de chaque moteur distant est gardée (P5f 3).

Défaut d'audit (D-260) : les sept adaptateurs distants ne gardaient du corps
rendu par l'API que le texte — ``page.markdown`` chez Mistral OCR,
``analyzeResult.content`` chez Azure, ``fullTextAnnotation.text`` chez Google, le
message et deux compteurs chez les LLM. Toute autre lecture (meilleur protocole,
projection vers ``LAYOUT``) imposait de re-payer l'appel.

Ce qui est vérifié, par fournisseur, sur cassette et sans réseau :

* le sidecar ``NATIVE_JSON`` **est** le corps reçu, sous sa forme canonique ;
* il ne contient **aucun secret** — la clé est bien passée par la requête (en
  en-tête, en *query string*, au client du SDK), elle n'arrive pas au disque ;
* la sortie texte **se relit** depuis le sidecar par la fonction de conversion
  de l'adaptateur, à l'octet près.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from cinoc.adapters._native import sdk_native
from cinoc.adapters.llm.anthropic import AnthropicAdapter, _completion_from_message
from cinoc.adapters.llm.mistral import MistralAdapter
from cinoc.adapters.llm.mistral import _completion_from_chat as mistral_completion
from cinoc.adapters.llm.ollama import OllamaAdapter
from cinoc.adapters.llm.ollama import _completion_from_chat as ollama_completion
from cinoc.adapters.llm.openai import OpenAIAdapter
from cinoc.adapters.llm.openai import _completion_from_chat as openai_completion
from cinoc.adapters.ocr.azure_di import AzureDocIntelAdapter
from cinoc.adapters.ocr.azure_di import _extract_text as azure_text
from cinoc.adapters.ocr.google_vision import GoogleVisionAdapter
from cinoc.adapters.ocr.google_vision import _extract_text as google_text
from cinoc.adapters.ocr.mistral_ocr import MistralOCRAdapter, _text_from_response
from cinoc.domain.artifacts import Artifact, ArtifactType, native_json_bytes
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.adapters._native_fakes import (
    SECRET,
    SdkResponse,
    install_fake_http,
    install_fake_sdks,
    set_keys,
    wire,
)

#: (moteur, cassette, scénario, fabrique, relecture sidecar → texte).
_ENGINES: list[tuple[str, str, str, Callable[[], Module], Callable[[Any], str]]] = [
    (
        "mistral_ocr",
        "ocr",
        "folio_a",
        lambda: MistralOCRAdapter(label="m"),
        _text_from_response,
    ),
    ("azure_di", "ocr", "folio_a", lambda: AzureDocIntelAdapter(label="a"), azure_text),
    (
        "google_vision",
        "ocr",
        "folio_a",
        lambda: GoogleVisionAdapter(label="g"),
        google_text,
    ),
    (
        "openai",
        "llm",
        "stop",
        lambda: OpenAIAdapter(label="o", role="zero_shot"),
        lambda n: openai_completion(n).text,
    ),
    (
        "anthropic",
        "llm",
        "end_turn",
        lambda: AnthropicAdapter(label="c", role="zero_shot"),
        lambda n: _completion_from_message(n).text,
    ),
    (
        "mistral",
        "llm",
        "stop",
        lambda: MistralAdapter(label="p", role="zero_shot"),
        lambda n: mistral_completion(n).text,
    ),
    (
        "ollama",
        "llm",
        "stop",
        lambda: OllamaAdapter(label="l", role="zero_shot", model="qwen2.5vl:3b"),
        lambda n: ollama_completion(n, "qwen2.5vl:3b").text,
    ),
]


def _execute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
    family: str,
    scenario: str,
    build: Callable[[], Module],
) -> tuple[Module, dict[ArtifactType, Artifact], list[httpx.Request]]:
    body = wire(family, engine, scenario)
    seen: list[httpx.Request] = []
    set_keys(monkeypatch)
    queues = {
        name: (lambda: body)
        for name in (
            "openai",
            "anthropic",
            "mistral",
            "mistral_ocr",
            "azure_di",
            "google_vision",
            "ollama",
        )
    }
    install_fake_sdks(monkeypatch, queues)
    install_fake_http(monkeypatch, queues, seen)
    image = tmp_path / "folio_a.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    module = build()
    out = module.execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="folio_a:img",
                document_id="folio_a",
                type=ArtifactType.IMAGE,
                uri=str(image),
            )
        },
        {},
        RunContext(
            document_id="folio_a",
            code_version="t",
            pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    return module, dict(out.artifacts), seen


@pytest.mark.parametrize(("engine", "family", "scenario", "build", "_read"), _ENGINES)
def test_the_sidecar_is_the_body_the_api_returned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
    family: str,
    scenario: str,
    build: Callable[[], Module],
    _read: Callable[[Any], str],
) -> None:
    module, artifacts, _ = _execute(
        tmp_path, monkeypatch, engine, family, scenario, build
    )
    assert ArtifactType.NATIVE_JSON in module.output_types
    sidecar = artifacts[ArtifactType.NATIVE_JSON]
    assert sidecar.uri is not None
    data = Path(sidecar.uri).read_bytes()
    assert json.loads(data) == wire(family, engine, scenario)
    # Forme canonique (clés triées) : deux réponses égales, mêmes octets.
    assert data == native_json_bytes(wire(family, engine, scenario))
    assert sidecar.id == f"folio_a:{module.name}:native_json"


@pytest.mark.parametrize(("engine", "family", "scenario", "build", "_read"), _ENGINES)
def test_no_secret_reaches_the_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
    family: str,
    scenario: str,
    build: Callable[[], Module],
    _read: Callable[[Any], str],
) -> None:
    """La clé passe par la requête ; elle n'arrive dans aucun fichier écrit."""
    _, artifacts, seen = _execute(
        tmp_path, monkeypatch, engine, family, scenario, build
    )
    if engine == "azure_di":  # en-tête, sur la soumission **et** la sonde
        assert all(r.headers["Ocp-Apim-Subscription-Key"] == SECRET for r in seen)
        assert len(seen) == 2
    elif engine == "google_vision":  # en query string
        assert seen[0].url.params["key"] == SECRET
    for path in tmp_path.iterdir():
        assert SECRET not in path.read_bytes().decode("utf-8", "replace"), path.name
    sidecar = Path(artifacts[ArtifactType.NATIVE_JSON].uri or "").read_text("utf-8")
    assert "Authorization" not in sidecar and "Ocp-Apim" not in sidecar
    assert "req-" not in sidecar  # l'identifiant privé du SDK n'y est pas


@pytest.mark.parametrize(("engine", "family", "scenario", "build", "read"), _ENGINES)
def test_the_text_is_rebuilt_from_the_sidecar_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
    family: str,
    scenario: str,
    build: Callable[[], Module],
    read: Callable[[Any], str],
) -> None:
    """La conversion de l'adaptateur, appliquée au seul sidecar, rend le texte."""
    _, artifacts, _ = _execute(tmp_path, monkeypatch, engine, family, scenario, build)
    texte = next(
        a
        for t, a in artifacts.items()
        if t in (ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT)
    )
    native = json.loads(
        Path(artifacts[ArtifactType.NATIVE_JSON].uri or "").read_bytes()
    )
    assert read(native) == Path(texte.uri or "").read_text(encoding="utf-8")


def test_the_azure_sidecar_keeps_the_terminal_poll_not_the_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deux appels par page : la soumission (202, sans corps) et la sonde. Le
    sidecar est le corps de la sonde terminale — celui qui porte le résultat."""
    _, artifacts, _ = _execute(
        tmp_path,
        monkeypatch,
        "azure_di",
        "ocr",
        "folio_a",
        lambda: AzureDocIntelAdapter(label="a"),
    )
    native = json.loads(
        Path(artifacts[ArtifactType.NATIVE_JSON].uri or "").read_bytes()
    )
    assert native["status"] == "succeeded"
    assert native["analyzeResult"]["pages"][0]["words"][0]["confidence"] == 0.995


def test_sdk_native_reads_the_body_not_the_object() -> None:
    """``model_dump`` : ni l'attribut privé (identifiant de requête), ni un
    champ que le modèle aurait par défaut sans qu'il soit arrivé sur le fil."""

    class _AvecDefaut(SdkResponse):
        service_tier: str | None = None

    response = _AvecDefaut.model_validate({"id": "x", "choices": []})
    response._request_id = f"req-{SECRET}"
    assert sdk_native(response, "openai") == {"id": "x", "choices": []}


def test_sdk_native_refuses_what_is_not_a_model() -> None:
    with pytest.raises(AdapterStepError, match="modèle pydantic"):
        sdk_native({"id": "x"}, "openai")


def test_native_json_bytes_is_canonical() -> None:
    assert native_json_bytes({"b": 1, "a": "é"}) == native_json_bytes(
        {"a": "é", "b": 1}
    )
    assert native_json_bytes({"b": 1, "a": "é"}) == '{"a":"é","b":1}'.encode()
