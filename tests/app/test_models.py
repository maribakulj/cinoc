"""P5f 8 (D-268, D-294) — les modèles se **demandent** au fournisseur.

``available_models`` interroge l'API (OpenAI, Anthropic, Mistral) ou le serveur
(Ollama) en direct ; la lecture du corps reçu est pure et testée sur cassette
(``tests/fixtures/cassettes/models/``, construites au format documenté des API,
à confirmer sur réponse réelle ; Ollama relevée sur un serveur 0.40.18). Les
SDK sont factices — seul le transport l'est : leur client rend un modèle
pydantic du corps, comme les vrais. Aucun appel facturé, aucune clé.

Rien n'est deviné : une capacité ou un cycle de vie non déclarés restent
``None`` (« inconnu »).
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest

from cinoc.adapters.llm import anthropic as anthropic_adapter
from cinoc.adapters.llm import mistral as mistral_adapter
from cinoc.adapters.llm import ollama as ollama_adapter
from cinoc.adapters.llm import openai as openai_adapter
from cinoc.adapters.llm._listing import ModelInfo
from cinoc.app.models import (
    ModelChoiceError,
    ModelListing,
    available_models,
    check_spec_models,
    model_providers,
)
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.modules.registry import ModuleResolutionError
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from tests.adapters._native_fakes import SdkResponse, install_fake_mistralai

_CASSETTES = Path(__file__).resolve().parents[1] / "fixtures" / "cassettes" / "models"


def _wire(provider: str, scenario: str) -> Any:
    data = json.loads((_CASSETTES / f"{provider}.json").read_text("utf-8"))
    return data["responses"][scenario]


# --------------------------------------------------------------------------- #
# Lecture du corps : ce que le fournisseur déclare, rien de plus
# --------------------------------------------------------------------------- #


def test_openai_declares_neither_vision_nor_lifecycle() -> None:
    models = openai_adapter.models_from_listing(_wire("openai", "list")["data"])
    assert [m.name for m in models] == [
        "gpt-test-ancien",
        "gpt-test-mini",
        "gpt-test-mini-2024-07-18",
    ]
    assert all(m.vision is None and m.lifecycle is None for m in models)
    assert models[0].retires_at == "2026-12-15"


def test_anthropic_reads_vision_and_lifecycle_when_given() -> None:
    items = _wire("anthropic", "page1")["data"] + _wire("anthropic", "page2")["data"]
    haiku, ancien, nu = (
        anthropic_adapter.models_from_listing(items)[i] for i in (1, 0, 2)
    )
    assert (haiku.name, haiku.vision, haiku.lifecycle) == (
        "claude-test-haiku-20251001",
        True,
        "active",
    )
    assert ancien.lifecycle == "deprecated"
    assert ancien.deprecated_at == "2026-06-01T00:00:00Z"
    assert ancien.retires_at == "2027-01-05T00:00:00Z"
    # Sans capacités ni cycle de vie : inconnus, pas « non ».
    assert (nu.vision, nu.lifecycle) == (None, None)


def test_mistral_reads_vision_ocr_aliases_and_deprecation() -> None:
    small, ocr, ancien = sorted(
        mistral_adapter.models_from_listing(_wire("mistral", "list")),
        key=lambda m: ("ancien" in m.name, "ocr" in m.name),
    )
    assert (small.vision, small.ocr, small.aliases) == (
        True,
        False,
        ("mistral-test-small-2506",),
    )
    assert (ocr.ocr, ocr.vision) == (True, False)
    assert ancien.deprecated_at == "2026-12-31T00:00:00Z"
    assert ancien.vision is None  # non déclarée


def test_ollama_reads_the_digest_and_declared_capabilities() -> None:
    qwen, texte = (
        ollama_adapter.model_from_tag(item)
        for item in _wire("ollama", "tags")["models"]
    )
    assert qwen is not None and texte is not None
    assert qwen.digest is not None and qwen.digest.startswith("fb90415cde1e")
    assert qwen.vision is True
    # Sans ``capabilities`` dans /api/tags : celles de /api/show, sinon inconnue.
    assert texte.vision is None
    shown = ollama_adapter.model_from_tag(
        _wire("ollama", "tags")["models"][1], _wire("ollama", "show_texte")
    )
    assert shown is not None and shown.vision is False


def test_an_ollama_name_without_tag_is_latest() -> None:
    assert ollama_adapter.same_model("texte-test", "texte-test:latest")
    assert not ollama_adapter.same_model("texte-test", "texte-test:7b")
    assert not ollama_adapter.same_model("qwen", "qwen-test:3b")


# --------------------------------------------------------------------------- #
# En direct, sous des SDK factices (transport seul)
# --------------------------------------------------------------------------- #


class _NotFound(Exception):
    pass


def _fake_openai(monkeypatch: pytest.MonkeyPatch, seen: list[dict[str, Any]]) -> None:
    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            seen.append(kwargs)
            items = _wire("openai", "list")["data"]
            self.models = types.SimpleNamespace(
                list=lambda: [SdkResponse.model_validate(i) for i in items]
            )

    module = types.ModuleType("openai")
    module.OpenAI = _Client  # type: ignore[attr-defined]
    module.OpenAIError = type("OpenAIError", (Exception,), {})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)


def _fake_anthropic(
    monkeypatch: pytest.MonkeyPatch, calls: list[tuple[str, Any]]
) -> None:
    pages = _wire("anthropic", "page1")["data"] + _wire("anthropic", "page2")["data"]

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(("init", kwargs))

            def lister(**kwargs: Any) -> list[SdkResponse]:
                calls.append(("list", kwargs))
                return [SdkResponse.model_validate(i) for i in pages]

            def retrieve(name: str) -> SdkResponse:
                calls.append(("retrieve", name))
                if name != "claude-test-haiku":
                    raise _NotFound(name)
                return SdkResponse.model_validate(_wire("anthropic", "retrieve_alias"))

            self.models = types.SimpleNamespace(list=lister, retrieve=retrieve)

    module = types.ModuleType("anthropic")
    module.Anthropic = _Client  # type: ignore[attr-defined]
    module.AnthropicError = Exception  # type: ignore[attr-defined]
    module.NotFoundError = _NotFound  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", module)


def test_openai_lists_the_models_of_the_instance_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []
    _fake_openai(monkeypatch, seen)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    listing = available_models("openai")
    assert listing.unavailable is None and len(listing.models) == 3
    assert seen[-1]["base_url"] == "https://api.openai.com/v1"
    assert seen[-1]["max_retries"] == 0
    # Un serveur auto-hébergé liste ses modèles, sans la clé d'OpenAI.
    available_models("openai", {"base_url": "http://gpu.lan:8000/v1"})
    assert seen[-1]["base_url"] == "http://gpu.lan:8000/v1"
    assert seen[-1]["api_key"] != "sk-test"


def test_anthropic_lists_every_page_and_resolves_an_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any]] = []
    _fake_anthropic(monkeypatch, calls)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://ailleurs.lan")
    listing = available_models("anthropic", wanted="claude-test-haiku")
    assert dict(calls)["init"]["base_url"] == "https://api.anthropic.com"
    assert ("list", {"limit": 1000}) in calls
    # L'alias n'est pas listé ; l'API le résout — il est offert, pas « absent ».
    assert listing.offers("claude-test-haiku")
    assert not listing.offers("claude-test-inexistant")


def test_mistral_lists_through_mistralai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    class _Mistral:
        def __init__(self, **kwargs: Any) -> None:
            seen.append(kwargs)
            self.models = types.SimpleNamespace(
                list=lambda: SdkResponse.model_validate(_wire("mistral", "list"))
            )

    install_fake_mistralai(monkeypatch, _Mistral)
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    listing = available_models("mistral_ocr")
    assert seen[0]["retry_config"] is None
    assert listing.offers("mistral-test-small-2506")  # un alias déclaré
    assert {m.name for m in listing.models} == {
        "mistral-test-small-latest",
        "mistral-test-ocr-latest",
        "mistral-test-ancien",
    }


def test_ollama_lists_the_installed_models(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=_wire("ollama", "tags"))
        return httpx.Response(200, json=_wire("ollama", "show_texte"))

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    listing = available_models("ollama", {"host": "http://s22.lan:11434"})
    assert [m.name for m in listing.models] == ["qwen-test:3b", "texte-test:latest"]
    assert [m.vision for m in listing.models] == [True, False]
    # /api/show seulement pour le modèle dont /api/tags tait les capacités.
    assert seen == ["GET /api/tags", "POST /api/show"]


@pytest.mark.parametrize(
    ("provider", "why"),
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("mistral", "MISTRAL_API_KEY"),
    ],
)
def test_a_listing_without_key_says_why(
    provider: str, why: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(why, raising=False)
    listing = available_models(provider)
    assert listing.models == ()
    assert listing.unavailable is not None and why in listing.unavailable


def test_a_listing_without_sdk_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    listing = available_models("anthropic")
    assert listing.unavailable is not None and "[anthropic]" in listing.unavailable


def test_an_unreachable_ollama_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    real = httpx.Client

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé", request=request)

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(refuse), **kw)
    )
    listing = available_models("ollama")
    assert listing.unavailable is not None and "injoignable" in listing.unavailable


def test_an_unknown_provider_names_the_known_ones() -> None:
    listing = available_models("bogus")
    assert listing.unavailable is not None
    assert all(p in listing.unavailable for p in model_providers())


# --------------------------------------------------------------------------- #
# Aucun modèle par défaut : une spec sans modèle est refusée, liste à l'appui
# --------------------------------------------------------------------------- #


def _spec(kind: str, settings: dict[str, Any]) -> RunSpec:
    name = f"{kind}:x"
    step = PipelineStep(
        id="vlm",
        kind="transcription",
        adapter_name=name,
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    return RunSpec(
        corpus=CorpusSpec(
            name="c", documents=(DocumentRef(id="d", image_uri="/tmp/d.png"),)
        ),
        pipelines=(
            PipelineSpec(name="p", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)),
        ),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="t", candidate_types=(ArtifactType.RAW_TEXT,), metric_names=()
                ),
            )
        ),
        adapter_kwargs={name: {"label": "x", "role": "zero_shot", **settings}},
    )


def _listing(monkeypatch: pytest.MonkeyPatch, listing: ModelListing) -> None:
    monkeypatch.setattr(
        "cinoc.app.models.available_models", lambda *_a, **_k: listing
    )


_TWO = ModelListing(
    provider="openai",
    models=(ModelInfo(name="gpt-test-a"), ModelInfo(name="gpt-test-b")),
)


def test_a_spec_without_model_is_refused_with_the_available_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _listing(monkeypatch, _TWO)
    with pytest.raises(ModelChoiceError) as refus:
        check_spec_models(_spec("openai", {}), live=False)
    message = str(refus.value)
    assert "aucun modèle par défaut" in message
    assert "gpt-test-a, gpt-test-b" in message


def test_a_missing_model_is_told_in_the_syntax_of_both_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S34b, n° 16 : le refus ne nommait que ``adapter_kwargs.…`` (spec YAML),
    alors qu'avec une recette il faut ``--set vlm.model=…`` — l'étape."""
    _listing(monkeypatch, _TWO)
    with pytest.raises(ModelChoiceError) as refus:
        check_spec_models(_spec("openai", {}), live=False)
    message = str(refus.value)
    assert "--set vlm.model=<modèle>" in message
    assert "adapter_kwargs" in message and "spec YAML" in message


def test_a_spec_without_model_says_why_the_list_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(ModelChoiceError, match="MISTRAL_API_KEY absente"):
        check_spec_models(_spec("mistral", {}), live=False)


def test_the_registry_refuses_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le run sans ``--check`` : le registre ne construit pas une instance sans
    modèle — il ne retombe sur aucun défaut."""
    _listing(monkeypatch, _TWO)
    registre = ModuleRegistry()
    register_default_modules(registre)
    for kind in ("openai", "anthropic", "mistral", "mistral_ocr", "ollama"):
        with pytest.raises(ModuleResolutionError, match="gpt-test-a"):
            registre.build(f"{kind}:x", {"label": "x"})


def test_check_refuses_a_model_the_provider_does_not_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D13 du pilote : ``--check`` acceptait un modèle absent."""
    _listing(monkeypatch, _TWO)
    with pytest.raises(ModelChoiceError, match="absent chez openai"):
        check_spec_models(_spec("openai", {"model": "gpt-test-z"}), live=True)
    assert check_spec_models(_spec("openai", {"model": "gpt-test-b"}), live=True) == ()


def test_check_says_it_cannot_verify_instead_of_refusing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fournisseur injoignable (ou pas de clé sur la machine qui relit) : une
    note, pas un refus — on n'affirme pas l'absence de ce qu'on n'a pas vu."""
    _listing(monkeypatch, ModelListing(provider="openai", unavailable="injoignable"))
    (note,) = check_spec_models(_spec("openai", {"model": "gpt-test-z"}), live=True)
    assert "non vérifié" in note and "injoignable" in note


def test_offline_check_does_not_call_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interdit(*_a: object, **_k: object) -> ModelListing:
        raise AssertionError("appel au fournisseur sans --check")

    monkeypatch.setattr("cinoc.app.models.available_models", interdit)
    assert check_spec_models(_spec("openai", {"model": "x"}), live=False) == ()


def test_a_recipe_without_model_is_refused_with_the_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une file sans modèle pour son VLM : refusée avant le run, le message
    liste les modèles du fournisseur (la page le reçoit en 422)."""
    from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run

    _listing(monkeypatch, _TWO)
    corpus = CorpusSpec(
        name="c", documents=(DocumentRef(id="d", image_uri=str(tmp_path / "d.png")),)
    )
    spec = plan_recipe_run(
        corpus,
        (RecipeEntry(recipe="vlm_seul", choices={"vlm": "openai"}),),
        run_id="r",
    )
    with pytest.raises(ModelChoiceError, match="gpt-test-a"):
        check_spec_models(spec, live=False)


def test_a_chain_names_the_model_of_its_ocr_engine(tmp_path: Path) -> None:
    """En chaîne, chaque étape a son modèle : le moteur OCR amont (Mistral OCR,
    kraken…) a le sien — faute de défaut, il fallait le dire."""
    from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run

    corpus = CorpusSpec(
        name="c", documents=(DocumentRef(id="d", image_uri=str(tmp_path / "d.png")),)
    )
    spec = plan_recipe_run(
        corpus,
        (
            RecipeEntry(
                recipe="ocr_puis_llm",
                choices={"ocr": "mistral_ocr", "correction": "mistral"},
                params={
                    "ocr": {"model": "mistral-test-ocr-latest"},
                    "correction": {"model": "mistral-test-small-latest"},
                },
            ),
        ),
        run_id="r",
    )
    assert spec.adapter_kwargs["mistral_ocr:ocr"]["model"] == "mistral-test-ocr-latest"
    assert spec.adapter_kwargs["mistral:correction"]["model"] == (
        "mistral-test-small-latest"
    )
