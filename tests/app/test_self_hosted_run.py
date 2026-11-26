"""Critère de P5f 6 (S21, D-293) : **un run compare OpenAI distant et un serveur
OpenAI-compatible local**, de bout en bout (spec → registre → exécution →
``RunResult`` → rapport).

Deux instances du **même** adaptateur dans un même run — ce que la variable de
processus ``OPENAI_BASE_URL`` rendait impossible. Le faux SDK ``openai`` ne
simule que le **transport** : il répond selon le ``base_url`` reçu, comme deux
serveurs différents, et note la clé que chaque client a reçue.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.analysis import EconomicsPayload
from cinoc.reports import default_report_renderer
from tests.adapters._native_fakes import SdkResponse, fake_sdk_module, wire

_KEY = "sk-openai-pour-openai-seulement"
_LOCAL = "http://127.0.0.1:11434/v1"


def _local_body() -> dict[str, Any]:
    """Corps ``chat.completion`` d'un serveur local (forme d'Ollama ``/v1``)."""
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": 1764115200,
        "model": "qwen2.5vl:3b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Le Petit Journal"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 6, "total_tokens": 126},
    }


def _install(monkeypatch: pytest.MonkeyPatch, seen: list[dict[str, Any]]) -> None:
    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            seen.append(kwargs)
            base_url = kwargs["base_url"]

            def create(**_: Any) -> SdkResponse:
                body = (
                    wire("llm", "openai", "stop")
                    if base_url == "https://api.openai.com/v1"
                    else _local_body()
                )
                return SdkResponse.model_validate(body)

            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=create)
            )

    class _Erreur(Exception):
        pass

    module = fake_sdk_module("openai", OpenAI=_Client, OpenAIError=_Erreur)
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.setenv("OPENAI_API_KEY", _KEY)


def _pipeline(name: str, llm: str) -> PipelineSpec:
    return PipelineSpec(
        name=name,
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
                adapter_name=llm,
                input_types=(ArtifactType.RAW_TEXT,),
                output_types=(ArtifactType.CORRECTED_TEXT,),
            ),
        ),
    )


def _spec(tmp_path: Path) -> RunSpec:
    (tmp_path / "d.gt.txt").write_text("Le Petit Journal", encoding="utf-8")
    (tmp_path / "d.eng.txt").write_text("Le Petlt Journa1", encoding="utf-8")
    document = DocumentRef(
        id="d",
        image_uri=str(tmp_path / "d.png"),
        ground_truths=(
            GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "d.gt.txt")),
        ),
    )
    return RunSpec(
        corpus=CorpusSpec(name="c", documents=(document,)),
        pipelines=(
            _pipeline("openai_distant", "openai:distant"),
            _pipeline("serveur_local", "openai:local"),
        ),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="corrected",
                    candidate_types=frozenset({ArtifactType.CORRECTED_TEXT}),
                    metric_names=("cer",),
                ),
            ),
            analyses=("economics",),
        ),
        adapter_kwargs={
            "precomputed:eng": {"source_label": "eng"},
            "openai:distant": {"label": "distant", "model": "gpt-4o-mini"},
            "openai:local": {
                "label": "local",
                "model": "qwen2.5vl:3b",
                "base_url": _LOCAL,
                "self_hosted": True,
            },
        },
        run_id="s21",
    )


def test_a_run_compares_remote_openai_and_a_local_openai_compatible_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []
    _install(monkeypatch, seen)
    registry = ModuleRegistry()
    register_default_modules(registry)

    result = run(_spec(tmp_path), registry=registry, code_version="1")

    # Deux serveurs, la clé d'OpenAI au seul OpenAI.
    by_url = {kw["base_url"]: kw["api_key"] for kw in seen}
    assert set(by_url) == {"https://api.openai.com/v1", _LOCAL}
    assert by_url["https://api.openai.com/v1"] == _KEY
    assert by_url[_LOCAL] != _KEY
    assert _KEY not in result.model_dump_json()

    # Le manifeste nomme chaque cible et chaque modèle servi.
    kwargs = result.manifest.adapter_kwargs
    assert kwargs["openai:distant"]["base_url"] == "https://api.openai.com/v1"
    assert kwargs["openai:local"]["base_url"] == _LOCAL
    assert result.manifest.served_models == {
        "openai:distant": ("gpt-4o-mini-2024-07-18",),
        "openai:local": ("qwen2.5vl:3b",),
    }

    # L'économie : tarifé d'un côté, auto-hébergé de l'autre.
    (economics,) = [
        a.payload for a in result.analyses if isinstance(a.payload, EconomicsPayload)
    ]
    rows = {r.pipeline: r for r in economics.pipelines}
    distant, local = rows["openai_distant"], rows["serveur_local"]
    assert distant.basis.startswith("machine+jetons")
    assert distant.self_hosted == ()
    assert local.basis == "machine" and local.self_hosted == ("openai/qwen2.5vl:3b",)
    assert local.cost_eur is not None and distant.cost_eur is not None
    assert local.tokens_in == 120  # mesurés, montrés, pas facturés

    # Le rapport montre les deux, dans les deux langues.
    fr = default_report_renderer().render(result)
    en = default_report_renderer().render(result, lang="en")
    assert "auto-hébergé : openai/qwen2.5vl:3b" in fr
    assert "self-hosted: openai/qwen2.5vl:3b" in en
    assert "tarif inconnu" not in fr
