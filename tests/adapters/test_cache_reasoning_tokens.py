"""P5f 8 (S22, D-294) — jetons de cache et de raisonnement lus dans le corps.

Chaque fournisseur rend, quand il en a, une ventilation de ses jetons : OpenAI
``prompt_tokens_details.cached_tokens`` / ``cache_write_tokens`` (parties de
``prompt_tokens``) et ``completion_tokens_details.reasoning_tokens`` (partie de
``completion_tokens``) ; Anthropic ``cache_read_input_tokens`` /
``cache_creation_input_tokens`` (qui **s'ajoutent** à ``input_tokens``, lequel
ne compte que l'entrée hors cache) et ``output_tokens_details.thinking_tokens``
(partie d'``output_tokens``) ; Mistral ``prompt_tokens_details.cached_tokens`` ;
Ollama rien. Avant S22, tout cela était jeté : un appel Anthropic servi à 95 %
depuis le cache n'en déclarait que 5 % en entrée, et un appel OpenAI facturait
au tarif plein des jetons payés moitié prix.

Règle de lecture : ``tokens_in`` = **toute** l'entrée (cache compris, pour les
quatre), ``tokens_out`` = toute la sortie (raisonnement compris) ; les comptes
de cache et de raisonnement en sont des **parties**. Un compte que la réponse
ne porte pas est ``None`` — jamais 0.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.llm._base import LLMCompletion, run_llm_step
from cinoc.adapters.llm.anthropic import _completion_from_message
from cinoc.adapters.llm.mistral import _completion_from_chat as mistral_completion
from cinoc.adapters.llm.ollama import _completion_from_chat as ollama_completion
from cinoc.adapters.llm.openai import _completion_from_chat as openai_completion
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.usage import ResourceUsage
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.adapters._native_fakes import real_sdk_transport, wire


def _parts(c: LLMCompletion) -> tuple[Any, ...]:
    return (
        c.tokens_in,
        c.tokens_out,
        c.tokens_cache_read,
        c.tokens_cache_write,
        c.tokens_reasoning,
    )


def test_openai_reads_cached_and_reasoning_tokens() -> None:
    # 2 048 en entrée dont 1 536 lus en cache ; 75 en sortie dont 64 de
    # raisonnement — les parties restent dans leur total, sans double compte.
    out = openai_completion(wire("llm", "openai", "cached"))
    assert _parts(out) == (2048, 75, 1536, None, 64)


def test_openai_reads_a_cache_write_when_the_body_has_one() -> None:
    body = wire("llm", "openai", "cached")
    body["usage"]["prompt_tokens_details"]["cache_write_tokens"] = 300
    assert openai_completion(body).tokens_cache_write == 300


def test_anthropic_counts_the_cache_inside_the_input() -> None:
    # input_tokens (105) = l'entrée HORS cache : l'entrée réelle en est la
    # somme avec les lectures (1 800) et les écritures (0) — 1 905.
    out = _completion_from_message(wire("llm", "anthropic", "cached"))
    assert _parts(out) == (1905, 40, 1800, 0, 28)


def test_mistral_reads_cached_tokens_and_no_reasoning() -> None:
    out = mistral_completion(wire("llm", "mistral", "cached"))
    assert _parts(out) == (1790, 12, 1024, None, None)


@pytest.mark.parametrize(
    ("read", "provider", "scenario"),
    [
        (openai_completion, "openai", "stop"),
        (_completion_from_message, "anthropic", "end_turn"),
        (mistral_completion, "mistral", "stop"),
        (lambda body: ollama_completion(body, "m"), "ollama", "stop"),
    ],
)
def test_a_body_without_details_says_none_never_zero(
    read: Any, provider: str, scenario: str
) -> None:
    out = read(wire("llm", provider, scenario))
    assert out.tokens_in is not None
    assert (out.tokens_cache_read, out.tokens_cache_write, out.tokens_reasoning) == (
        None,
        None,
        None,
    )


def test_a_zero_the_provider_wrote_stays_zero() -> None:
    body = wire("llm", "openai", "stop")
    body["usage"]["prompt_tokens_details"] = {"cached_tokens": 0}
    assert openai_completion(body).tokens_cache_read == 0


def test_an_unreadable_count_is_none() -> None:
    body = wire("llm", "anthropic", "cached")
    body["usage"]["cache_read_input_tokens"] = "beaucoup"
    out = _completion_from_message(body)
    # Lecture illisible : rien d'inventé — ni lu, ni ajouté à l'entrée.
    assert out.tokens_cache_read is None
    assert out.tokens_in == 105


def test_the_step_usage_carries_the_parts(tmp_path: Path) -> None:
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nx")
    body = wire("llm", "anthropic", "cached")
    output = run_llm_step(
        role="zero_shot",
        label="c",
        name="anthropic:c",
        prompt="Transcris.",
        inputs={
            ArtifactType.IMAGE: Artifact(
                id="p:i", document_id="p", type=ArtifactType.IMAGE, uri=str(image)
            )
        },
        context=RunContext(
            document_id="p",
            code_version="t",
            pipeline_name="x",
            workspace_uri=str(tmp_path),
        ),
        control=RunControl(),
        text_invoke=lambda _p: _completion_from_message(body),
        vision_invoke=lambda _p, _m, _b: _completion_from_message(body),
    )
    assert output.usage == ResourceUsage(
        tokens_in=1905,
        tokens_out=40,
        tokens_cache_read=1800,
        tokens_cache_write=0,
        tokens_reasoning=28,
    )


def test_usage_sums_the_parts_and_keeps_none() -> None:
    a = ResourceUsage(tokens_in=10, tokens_cache_read=4, tokens_reasoning=None)
    b = ResourceUsage(tokens_in=5, tokens_cache_read=None, tokens_reasoning=None)
    total = a.merged_with(b)
    assert total.tokens_cache_read == 4
    assert total.tokens_reasoning is None
    assert total.tokens_cache_write is None


# --------------------------------------------------------------------------- #
# Sous les **vrais** SDK (extras), transport factice — ignoré sans l'extra.
# --------------------------------------------------------------------------- #


def _usage_through(
    module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: str
) -> ResourceUsage | None:
    monkeypatch.setenv(env, "sk-test")
    tmp_path.mkdir(parents=True, exist_ok=True)
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nx")
    out = module.execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="p:i", document_id="p", type=ArtifactType.IMAGE, uri=str(image)
            )
        },
        {},
        RunContext(
            document_id="p",
            code_version="t",
            pipeline_name="x",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    usage: ResourceUsage | None = out.usage
    return usage


def test_openai_real_sdk_keeps_the_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """openai 3.x décode ``prompt_tokens_details``/``completion_tokens_details``
    sans les perdre ni ajouter de 0 absent du corps (``exclude_unset``)."""
    pytest.importorskip("openai")
    httpx2 = pytest.importorskip("httpx2")

    from cinoc.adapters.llm.openai import OpenAIAdapter

    body = wire("llm", "openai", "cached")
    transport = httpx2.MockTransport(lambda _r: httpx2.Response(200, json=body))
    real_sdk_transport(monkeypatch, "openai", transport)
    module = OpenAIAdapter(model="m", label="o", role="zero_shot")
    usage = _usage_through(module, tmp_path, monkeypatch, "OPENAI_API_KEY")
    assert usage == ResourceUsage(
        tokens_in=2048, tokens_out=75, tokens_cache_read=1536, tokens_reasoning=64
    )


def test_anthropic_real_sdk_keeps_the_cache_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")

    from cinoc.adapters.llm.anthropic import AnthropicAdapter

    body = wire("llm", "anthropic", "cached")
    transport = httpx2.MockTransport(lambda _r: httpx2.Response(200, json=body))
    real_sdk_transport(monkeypatch, "anthropic", transport)
    module = AnthropicAdapter(model="m", label="c", role="zero_shot")
    usage = _usage_through(module, tmp_path, monkeypatch, "ANTHROPIC_API_KEY")
    assert usage == ResourceUsage(
        tokens_in=1905,
        tokens_out=40,
        tokens_cache_read=1800,
        tokens_cache_write=0,
        tokens_reasoning=28,
    )


def test_mistral_real_sdk_keeps_the_cached_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mistralai 3.x : ``PromptTokensDetails.cached_tokens`` a un défaut 0 —
    absent du corps, il n'est pas inventé au dump (``exclude_unset``)."""
    pytest.importorskip("mistralai.client")
    httpx2 = pytest.importorskip("httpx2")

    from cinoc.adapters.llm.mistral import MistralAdapter

    bodies = iter((wire("llm", "mistral", "cached"), wire("llm", "mistral", "stop")))
    transport = httpx2.MockTransport(
        lambda _r: httpx2.Response(200, json=next(bodies))
    )
    real_sdk_transport(monkeypatch, "mistralai", transport)
    module = MistralAdapter(model="m", label="p", role="zero_shot")
    first = _usage_through(module, tmp_path / "a", monkeypatch, "MISTRAL_API_KEY")
    assert first is not None and first.tokens_cache_read == 1024
    second = _usage_through(module, tmp_path / "b", monkeypatch, "MISTRAL_API_KEY")
    assert second is not None and second.tokens_cache_read is None
