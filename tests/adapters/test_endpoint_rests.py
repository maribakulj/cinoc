"""Restes de S21 (D-293), fermés en S22 : la cible n'est pas une variable du
processus, et un serveur a **un** créneau, quel que soit l'adaptateur.

- ``ANTHROPIC_BASE_URL`` était lue (le SDK la lit en silence quand on ne lui
  passe pas d'endpoint) : la cible d'Anthropic est passée **explicitement**,
  la variable ne vaut plus qu'un avertissement ;
- l'adaptateur ``ollama`` natif appelait sans créneau réseau : une instance
  ``openai`` pointée sur le même serveur (``…:11434/v1``) ne partageait pas son
  quota avec lui.
"""

from __future__ import annotations

import logging
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest

from cinoc.adapters._resilience import endpoint_slot_key, network_slot
from cinoc.adapters.llm.anthropic import AnthropicAdapter
from cinoc.adapters.llm.ollama import OllamaAdapter
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError, DeadlineExceeded
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.adapters._native_fakes import SdkResponse, wire


def _ctx(tmp_path: Path) -> RunContext:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    return RunContext(
        document_id="d", code_version="t", pipeline_name="p",
        workspace_uri=str(workspace),
    )


def _raw(tmp_path: Path) -> dict[ArtifactType, Artifact]:
    texte = tmp_path / "ocr.txt"
    texte.write_text("le soleil", encoding="utf-8")
    return {
        ArtifactType.RAW_TEXT: Artifact(
            id="d:ocr", document_id="d", type=ArtifactType.RAW_TEXT, uri=str(texte)
        )
    }


# --------------------------------------------------------------------------- #
# ANTHROPIC_BASE_URL n'est plus lue
# --------------------------------------------------------------------------- #


def test_anthropic_base_url_is_not_read_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    seen: list[dict[str, Any]] = []

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            seen.append(kwargs)

            def create(**_: Any) -> SdkResponse:
                return SdkResponse.model_validate(wire("llm", "anthropic", "end_turn"))

            self.messages = types.SimpleNamespace(create=create)

    module = types.ModuleType("anthropic")
    module.Anthropic = _Client  # type: ignore[attr-defined]
    module.AnthropicError = type("AnthropicError", (Exception,), {})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", module)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://ailleurs.lan:9000")

    with caplog.at_level(logging.WARNING):
        adapter = AnthropicAdapter(label="c", model="m")
    adapter.execute(_raw(tmp_path), {}, _ctx(tmp_path), RunControl())

    # Passée explicitement : le SDK ne relit pas la variable.
    assert seen[0]["base_url"] == "https://api.anthropic.com"
    assert adapter.effective_settings()["base_url"] == "https://api.anthropic.com"
    assert "ANTHROPIC_BASE_URL n'est plus lue" in caplog.text


def test_anthropic_without_the_variable_says_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    with caplog.at_level(logging.WARNING):
        AnthropicAdapter(label="c", model="m")
    assert "ANTHROPIC_BASE_URL" not in caplog.text


# --------------------------------------------------------------------------- #
# Ollama natif : le créneau de son serveur, partagé avec openai /v1
# --------------------------------------------------------------------------- #


def test_ollama_and_an_openai_instance_on_the_same_server_share_one_slot() -> None:
    assert endpoint_slot_key("http://localhost:11434") == endpoint_slot_key(
        "http://localhost:11434/v1"
    )


def test_native_ollama_waits_for_the_slot_of_its_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le créneau de ``…:11434`` est tenu (par une instance ``openai`` sur
    ``…:11434/v1``) : l'adaptateur natif l'attend, dans son délai, au lieu de
    frapper le serveur en plus — et n'envoie rien."""
    host = "http://s22-occupe.lan:11434"
    envoyes: list[httpx.Request] = []
    vrai = httpx.Client

    def client(**kwargs: Any) -> httpx.Client:
        return vrai(
            transport=httpx.MockTransport(
                lambda r: envoyes.append(r) or httpx.Response(200, json={})
            ),
            **kwargs,
        )

    monkeypatch.setattr(httpx, "Client", client)
    slot = network_slot(endpoint_slot_key(f"{host}/v1"))
    for _ in range(64):  # le créneau entier, quel que soit le plafond
        if not slot.acquire(blocking=False):
            break
    try:
        adapter = OllamaAdapter(label="o", model="m", host=host, timeout=0.2)
        with pytest.raises((AdapterStepError, DeadlineExceeded), match="créneau"):
            adapter.execute(_raw(tmp_path), {}, _ctx(tmp_path), RunControl())
    finally:
        while True:
            try:
                slot.release()
            except ValueError:
                break
    assert envoyes == []


def test_native_ollama_does_not_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sous ``call_resilient``, toujours **sans retry** : un 500 d'un serveur
    local ne se répare pas en 30 s."""
    envoyes: list[httpx.Request] = []
    vrai = httpx.Client

    def client(**kwargs: Any) -> httpx.Client:
        return vrai(
            transport=httpx.MockTransport(
                lambda r: envoyes.append(r) or httpx.Response(500, json={})
            ),
            **kwargs,
        )

    monkeypatch.setattr(httpx, "Client", client)
    adapter = OllamaAdapter(label="o", model="m", host="http://s22-seul.lan:11434")
    with pytest.raises(AdapterStepError):
        adapter.execute(_raw(tmp_path), {}, _ctx(tmp_path), RunControl())
    assert len(envoyes) == 1
