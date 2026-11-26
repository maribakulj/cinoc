"""Mêmes réglages d'inférence pour les quatre fournisseurs, écrits au manifeste (P5f 1).

Défaut d'audit (D-260) : OpenAI et Mistral passaient ``temperature=0``, Anthropic
et Ollama rien ; aucun ``seed`` ; ``max_tokens`` codé à 4 096 chez Anthropic et
absent ailleurs ; Ollama sans ``num_ctx`` ni ``num_predict`` (l'entrée tronquée
par le défaut du serveur). Le banc comparait des réglages différents, et le
manifeste n'en gardait aucun.

Les requêtes sont construites par des fonctions pures (``_request_kwargs``) que
les clients réseau appellent : on vérifie ce qui partirait sur le fil sans SDK
ni réseau. Pour Ollama, le vrai ``_invoke_ollama`` tourne contre un faux client.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.llm import anthropic as anthropic_mod
from cinoc.adapters.llm import mistral as mistral_mod
from cinoc.adapters.llm import openai as openai_mod
from cinoc.adapters.llm._base import (
    DEFAULT_CORRECTION_PROMPT,
    DEFAULT_MAX_TOKENS,
    DEFAULT_SEED,
    DEFAULT_TEMPERATURE,
    InferenceSettings,
    LLMCompletion,
)
from cinoc.adapters.llm.anthropic import AnthropicAdapter
from cinoc.adapters.llm.mistral import MistralAdapter
from cinoc.adapters.llm.ollama import DEFAULT_NUM_CTX, OllamaAdapter
from cinoc.adapters.llm.openai import OpenAIAdapter
from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_ADAPTERS = (OpenAIAdapter, MistralAdapter, OllamaAdapter, AnthropicAdapter)


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


# --------------------------------------------------------------------------- #
# Défauts explicites et identiques
# --------------------------------------------------------------------------- #


def test_the_defaults_are_named_and_explicit() -> None:
    assert (DEFAULT_TEMPERATURE, DEFAULT_SEED, DEFAULT_MAX_TOKENS) == (0.0, 0, 8192)


@pytest.mark.parametrize("cls", _ADAPTERS[:3])
def test_three_providers_share_the_same_defaults(cls: type) -> None:
    settings = cls(label="x", model="m").effective_settings()
    assert {k: settings[k] for k in ("temperature", "top_p", "seed", "max_tokens")} == {
        "temperature": 0.0,
        "top_p": None,
        "seed": 0,
        "max_tokens": 8192,
    }


def test_anthropic_shares_max_tokens_and_says_what_it_cannot_send() -> None:
    """L'API Anthropic n'accepte plus ``temperature``/``top_p`` (400 depuis la
    version d'API 2026-10-21 ; absents du SDK 2.x) et n'a jamais eu de ``seed`` :
    le manifeste l'écrit (``None`` = non transmis), il ne prétend pas un 0."""
    settings = AnthropicAdapter(label="x", model="m").effective_settings()
    assert {k: settings[k] for k in ("temperature", "top_p", "seed", "max_tokens")} == {
        "temperature": None,
        "top_p": None,
        "seed": None,
        "max_tokens": 8192,
    }


@pytest.mark.parametrize("key", ["temperature", "top_p", "seed"])
def test_anthropic_refuses_a_setting_its_api_rejects(key: str) -> None:
    with pytest.raises(AdapterStepError, match=key):
        AnthropicAdapter(label="x", model="m", **{key: 0.5 if key != "seed" else 1})


def test_ollama_pins_num_ctx_and_num_predict() -> None:
    settings = OllamaAdapter(label="x", model="m").effective_settings()
    assert settings["num_ctx"] == DEFAULT_NUM_CTX == 16384
    assert settings["max_tokens"] == 8192  # envoyé comme options.num_predict


@pytest.mark.parametrize(
    "bad",
    [
        {"max_tokens": 0},
        {"max_tokens": True},
        {"max_tokens": 12.5},
        {"temperature": -0.1},
        {"temperature": 2.5},
        {"temperature": "0"},
        {"top_p": 0.0},
        {"top_p": 1.5},
        {"seed": -1},
        {"seed": 1.5},
    ],
)
def test_an_invalid_setting_is_refused_at_construction(bad: dict[str, Any]) -> None:
    with pytest.raises(AdapterStepError):
        InferenceSettings.build(**bad)


def test_an_integer_temperature_is_read_as_a_float() -> None:
    """YAML écrit ``temperature: 0`` : un entier, pas une erreur."""
    assert InferenceSettings.build(temperature=0).temperature == 0.0


# --------------------------------------------------------------------------- #
# Transmis aux API
# --------------------------------------------------------------------------- #

_CUSTOM = InferenceSettings.build(temperature=0.2, top_p=0.9, seed=7, max_tokens=1000)


def test_openai_request_carries_every_setting() -> None:
    kwargs = openai_mod._request_kwargs("gpt", [{"role": "user"}], _CUSTOM)
    assert kwargs == {
        "model": "gpt",
        "messages": [{"role": "user"}],
        "temperature": 0.2,
        "top_p": 0.9,
        "seed": 7,
        # ``max_completion_tokens`` et non ``max_tokens`` : déprécié, et refusé
        # par les modèles de raisonnement (doc du SDK openai 3.59).
        "max_completion_tokens": 1000,
    }


def test_a_setting_left_to_none_is_not_sent() -> None:
    settings = InferenceSettings.build(temperature=None, seed=None)
    kwargs = openai_mod._request_kwargs("gpt", [], settings)
    assert (
        "temperature" not in kwargs and "seed" not in kwargs and "top_p" not in kwargs
    )


def test_mistral_request_carries_every_setting() -> None:
    kwargs = mistral_mod._request_kwargs("small", "texte", _CUSTOM)
    assert kwargs == {
        "model": "small",
        "messages": [{"role": "user", "content": "texte"}],
        "temperature": 0.2,
        "top_p": 0.9,
        "random_seed": 7,
        "max_tokens": 1000,
    }


def test_anthropic_request_sends_max_tokens_and_no_sampling() -> None:
    adapter = AnthropicAdapter(label="x", model="m", max_tokens=1000)
    kwargs = anthropic_mod._request_kwargs("claude", "texte", adapter._settings)
    assert kwargs == {
        "model": "claude",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": "texte"}],
    }


def test_ollama_payload_carries_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    envoye: dict[str, Any] = {}

    class _Reponse:
        def raise_for_status(self) -> None: ...

        def json(self) -> dict[str, Any]:
            return {"message": {"content": "corrigé"}, "done_reason": "stop"}

    class _Client:
        def __init__(self, **_: Any) -> None: ...

        def close(self) -> None: ...

        def post(self, url: str, json: dict[str, Any]) -> _Reponse:  # noqa: A002
            envoye["payload"] = json
            return _Reponse()

    import httpx

    monkeypatch.setattr(httpx, "Client", _Client)
    source = tmp_path / "brut.txt"
    source.write_text("du texte", encoding="utf-8")
    OllamaAdapter(
        label="x", model="m", temperature=0.2, seed=7, max_tokens=1000, num_ctx=4096
    ).execute(
        {
            ArtifactType.RAW_TEXT: Artifact(
                id="t", document_id="d", type=ArtifactType.RAW_TEXT, uri=str(source)
            )
        },
        {},
        RunContext(
            document_id="d",
            code_version="1",
            pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    assert envoye["payload"]["options"] == {
        "temperature": 0.2,
        "seed": 7,
        "num_predict": 1000,
        "num_ctx": 4096,
    }


@pytest.mark.parametrize("kind", ["openai", "mistral", "ollama", "anthropic"])
def test_the_registry_passes_the_settings_through(kind: str) -> None:
    kwargs: dict[str, Any] = {"label": "x", "model": "m", "max_tokens": 1234}
    if kind != "anthropic":
        kwargs.update(temperature=0.3, seed=5)
    module = _registry().build(f"{kind}:x", kwargs)
    settings = module.effective_settings()  # type: ignore[attr-defined]
    assert settings["max_tokens"] == 1234
    if kind != "anthropic":
        assert (settings["temperature"], settings["seed"]) == (0.3, 5)


# --------------------------------------------------------------------------- #
# Écrits au manifeste — les défauts compris
# --------------------------------------------------------------------------- #


def _llm_spec(tmp_path: Path, llm_kwargs: dict[str, Any]) -> RunSpec:
    (tmp_path / "d.gt.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "d.eng.txt").write_text("alpha", encoding="utf-8")
    document = DocumentRef(
        id="d",
        image_uri=str(tmp_path / "d.png"),
        ground_truths=(
            GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "d.gt.txt")),
        ),
    )
    pipeline = PipelineSpec(
        name="A",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr",
                kind="ocr",
                adapter_name="precomputed:eng",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
            PipelineStep(
                id="llm",
                kind="post_correction",
                adapter_name="openai:gpt",
                input_types=(ArtifactType.RAW_TEXT,),
                output_types=(ArtifactType.CORRECTED_TEXT,),
            ),
        ),
    )
    view = EvaluationView(
        name="corrected",
        candidate_types=frozenset({ArtifactType.CORRECTED_TEXT}),
        metric_names=("cer",),
    )
    return RunSpec(
        corpus=CorpusSpec(name="c", documents=(document,)),
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=(view,)),
        adapter_kwargs={
            "precomputed:eng": {"source_label": "eng"},
            "openai:gpt": {"model": "m", "label": "gpt", **llm_kwargs},
        },
        run_id="t",
    )


def test_the_manifest_carries_the_effective_settings_defaults_included(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai", lambda **_: LLMCompletion("alpha")
    )
    result = run(_llm_spec(tmp_path, {}), registry=_registry(), code_version="1")
    assert result.manifest.adapter_kwargs["openai:gpt"] == {
        "label": "gpt",
        # Le modèle demandé (aucun défaut : la spec le nomme, S22), le mode et
        # le prompt **par défaut** compris (S9) : ils changent la sortie.
        "model": "m",
        "role": "text_only",
        "prompt": DEFAULT_CORRECTION_PROMPT,
        "temperature": 0.0,
        "top_p": None,
        "seed": 0,
        "max_tokens": 8192,
        "base_url": "https://api.openai.com/v1",
    }
    # Un module sans réglages d'inférence garde ses kwargs tels quels.
    assert result.manifest.adapter_kwargs["precomputed:eng"] == {"source_label": "eng"}


def test_the_manifest_carries_what_the_user_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai", lambda **_: LLMCompletion("alpha")
    )
    spec = _llm_spec(tmp_path, {"temperature": 0, "max_tokens": 2048, "seed": 3})
    result = run(spec, registry=_registry(), code_version="1")
    kwargs = result.manifest.adapter_kwargs["openai:gpt"]
    assert (kwargs["temperature"], kwargs["max_tokens"], kwargs["seed"]) == (
        0.0,
        2048,
        3,
    )
