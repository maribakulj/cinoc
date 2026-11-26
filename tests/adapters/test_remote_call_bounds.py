"""P5f 7 (S20) — délais finis, une seule couche de retry, OCR cloud enveloppés,
tentatives comptées.

Aucun appel réseau : les SDK sont remplacés par des modules factices qui
**notent** ce qu'on leur passe (construction et appel), et Azure, Google et
Ollama reçoivent un ``httpx.MockTransport`` qui sert, dans l'ordre, une file de
réponses — 429 et 5xx compris. Les attentes sont injectées (``sleep``) ou
bornées par la ``Deadline`` : aucun test ne dort vraiment.

Chaque défaut est d'abord reproduit sur le code d'avant :

- les quatre moteurs LLM et les trois OCR distants tournaient sous une
  ``Deadline`` infinie (aucun appelant n'en passe) — Ollama, Azure et Google
  sans aucun délai, OpenAI et Anthropic sous le seul défaut de leur SDK ;
- OpenAI et Anthropic retentaient eux-mêmes (``max_retries=2`` par défaut),
  sous les cinq tentatives de Cinoc : jusqu'à 15 appels ;
- Mistral OCR, Azure et Google ne retentaient rien : un 429 perdait la page ;
- l'économie comptait une page par document, quel que soit le nombre d'appels.
"""

from __future__ import annotations

import json
import sys
import time
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from cinoc.adapters._native import sdk_native
from cinoc.adapters.llm.anthropic import AnthropicAdapter
from cinoc.adapters.llm.mistral import MistralAdapter
from cinoc.adapters.llm.ollama import OllamaAdapter
from cinoc.adapters.llm.openai import OpenAIAdapter
from cinoc.adapters.ocr.azure_di import AzureDocIntelAdapter
from cinoc.adapters.ocr.google_vision import GoogleVisionAdapter
from cinoc.adapters.ocr.mistral_ocr import MistralOCRAdapter
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError, DeadlineExceeded
from cinoc.pipeline.executor import failure_reason
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.adapters._native_fakes import (
    AZURE_ENDPOINT,
    OLLAMA_HOST,
    SdkResponse,
    fake_sdk_module,
    install_fake_mistralai,
    wire,
)

_SECRET = "sk-test-bornes"


def _ctx(tmp_path: Path) -> RunContext:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    # Deadline **infinie** : c'est ce que tout appelant passe aujourd'hui.
    return RunContext(
        document_id="d1",
        code_version="t",
        pipeline_name="p",
        workspace_uri=str(workspace),
    )


def _raw(tmp_path: Path) -> dict[ArtifactType, Artifact]:
    path = tmp_path / "ocr.txt"
    path.write_text("le texte ocr", encoding="utf-8")
    return {
        ArtifactType.RAW_TEXT: Artifact(
            id="d1:ocr:raw_text",
            document_id="d1",
            type=ArtifactType.RAW_TEXT,
            uri=str(path),
        )
    }


def _image(tmp_path: Path) -> dict[ArtifactType, Artifact]:
    path = tmp_path / "page.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfaux")
    return {
        ArtifactType.IMAGE: Artifact(
            id="d1:img", document_id="d1", type=ArtifactType.IMAGE, uri=str(path)
        )
    }


# --------------------------------------------------------------------------- #
# Faux SDK qui notent ce qu'on leur passe
# --------------------------------------------------------------------------- #


class _Status(Exception):
    """Erreur HTTP d'un SDK : ``status_code`` + en-têtes (forme des vrais)."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status
        self.headers: dict[str, str] = {}


def _install(
    monkeypatch: pytest.MonkeyPatch,
    seen: dict[str, list[dict[str, Any]]],
    replies: dict[str, list[object]],
) -> None:
    """``openai``, ``anthropic``, ``mistralai`` factices.

    ``seen["<sdk>:init"]`` reçoit les kwargs de construction du client,
    ``seen["<sdk>:call"]`` ceux de chaque appel ; ``replies[<sdk>]`` est la
    file des réponses — un corps (dict) ou une exception à lever.
    """

    def _client(sdk: str, path: tuple[str, ...]) -> type:
        class _Client:
            def __init__(self, **kwargs: Any) -> None:
                seen.setdefault(f"{sdk}:init", []).append(kwargs)

                def call(**call_kwargs: Any) -> SdkResponse:
                    seen.setdefault(f"{sdk}:call", []).append(call_kwargs)
                    reply = replies[sdk].pop(0)
                    if isinstance(reply, BaseException):
                        raise reply
                    assert isinstance(reply, dict)
                    return SdkResponse.model_validate(reply)

                node: object = types.SimpleNamespace(**{path[-1]: call})
                for name in reversed(path[1:-1]):
                    node = types.SimpleNamespace(**{name: node})
                setattr(self, path[0], node)

            def close(self) -> None:
                seen.setdefault(f"{sdk}:close", []).append({})

        return _Client

    class _Erreur(Exception):
        pass

    openai = fake_sdk_module(
        "openai",
        OpenAI=_client("openai", ("chat", "completions", "create")),
        OpenAIError=_Erreur,
    )
    anthropic = fake_sdk_module(
        "anthropic",
        Anthropic=_client("anthropic", ("messages", "create")),
        AnthropicError=_Erreur,
    )

    class _Mistral:
        def __init__(self, **kwargs: Any) -> None:
            seen.setdefault("mistralai:init", []).append(kwargs)

            def complete(**call_kwargs: Any) -> SdkResponse:
                seen.setdefault("mistralai:call", []).append(call_kwargs)
                reply = replies["mistralai"].pop(0)
                if isinstance(reply, BaseException):
                    raise reply
                assert isinstance(reply, dict)
                return SdkResponse.model_validate(reply)

            def process(**call_kwargs: Any) -> SdkResponse:
                seen.setdefault("mistralai:ocr", []).append(call_kwargs)
                reply = replies["mistral_ocr"].pop(0)
                if isinstance(reply, BaseException):
                    raise reply
                assert isinstance(reply, dict)
                return SdkResponse.model_validate(reply)

            self.chat = types.SimpleNamespace(complete=complete)
            self.ocr = types.SimpleNamespace(process=process)

    for name, module in (("openai", openai), ("anthropic", anthropic)):
        monkeypatch.setitem(sys.modules, name, module)
    install_fake_mistralai(monkeypatch, _Mistral)
    for env in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(env, _SECRET)


def _no_wait(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Les attentes entre tentatives sont notées, jamais dormies."""
    waits: list[float] = []

    def wait(self: RunControl, seconds: float) -> bool:
        waits.append(seconds)
        return self.is_cancelled()

    monkeypatch.setattr(RunControl, "wait", wait)
    return waits


# --------------------------------------------------------------------------- #
# Une seule couche de retry, un délai fini par appel
# --------------------------------------------------------------------------- #


_LLM_CASES: dict[str, tuple[Callable[[], object], str, str, str]] = {
    # sdk : (adaptateur, cassette, scénario, kwarg de délai à l'appel)
    "openai": (
        lambda: OpenAIAdapter(model="m", label="g"), "openai", "stop", "timeout"
    ),
    "anthropic": (
        lambda: AnthropicAdapter(model="m", label="c"),
        "anthropic",
        "end_turn",
        "timeout",
    ),
    "mistralai": (
        lambda: MistralAdapter(model="m", label="m"), "mistral", "stop", "timeout_ms"
    ),
}


@pytest.mark.parametrize("sdk", sorted(_LLM_CASES))
def test_the_sdk_never_retries_on_its_own(
    sdk: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``max_retries=0`` (OpenAI, Anthropic) et ``retry_config=None`` (Mistral) :
    la seule politique de retry est celle de Cinoc. Avant : le SDK ajoutait ses
    deux tentatives à chacune des cinq de Cinoc."""
    build, cassette, scenario, _ = _LLM_CASES[sdk]
    seen: dict[str, list[dict[str, Any]]] = {}
    _install(monkeypatch, seen, {sdk: [wire("llm", cassette, scenario)]})
    adapter = build()
    adapter.execute(_raw(tmp_path), {}, _ctx(tmp_path), RunControl())  # type: ignore[attr-defined]
    (init,) = seen[f"{sdk}:init"]
    if sdk == "mistralai":
        assert "retry_config" in init and init["retry_config"] is None
    else:
        assert init.get("max_retries") == 0


@pytest.mark.parametrize("sdk", sorted(_LLM_CASES))
def test_every_llm_call_has_a_finite_timeout(
    sdk: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sous une ``Deadline`` infinie (ce que passe tout appelant), l'appel part
    quand même avec un délai fini : le défaut du moteur (600 s)."""
    build, cassette, scenario, key = _LLM_CASES[sdk]
    seen: dict[str, list[dict[str, Any]]] = {}
    _install(monkeypatch, seen, {sdk: [wire("llm", cassette, scenario)]})
    build().execute(_raw(tmp_path), {}, _ctx(tmp_path), RunControl())  # type: ignore[attr-defined]
    (call,) = seen[f"{sdk}:call"]
    limit = 600_000 if key == "timeout_ms" else 600.0
    assert key in call, f"{sdk} : aucun délai transmis à l'appel"
    assert 0 < call[key] <= limit


def test_the_timeout_is_set_by_the_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le réglage existant ``timeout`` (Tesseract, segmenteurs) vaut pour les
    moteurs distants : la spec le règle, le registre le transmet."""
    registry = ModuleRegistry()
    register_default_modules(registry)
    seen: dict[str, list[dict[str, Any]]] = {}
    _install(monkeypatch, seen, {"openai": [wire("llm", "openai", "stop")]})
    module = registry.build("openai:g", {"model": "m", "label": "g", "timeout": 30})
    module.execute(_raw(tmp_path), {}, _ctx(tmp_path), RunControl())
    (call,) = seen["openai:call"]
    assert 0 < call["timeout"] <= 30.0


@pytest.mark.parametrize(
    "build",
    [
        lambda: OpenAIAdapter(model="m", label="g", timeout=0),
        lambda: OllamaAdapter(model="m", label="o", timeout=-1),
        lambda: AzureDocIntelAdapter(label="a", timeout=0),
        lambda: GoogleVisionAdapter(label="v", timeout=10_000),
        lambda: MistralOCRAdapter(model="m", label="m", timeout=0),
    ],
)
def test_an_unbounded_or_null_timeout_is_refused(build: Callable[[], object]) -> None:
    with pytest.raises(AdapterStepError, match="timeout"):
        build()


def test_openai_retries_a_429_itself_only_through_cinoc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un 429 puis un succès : deux appels au SDK — ni plus (le SDK ne
    retente pas en dessous), ni moins (Cinoc retente)."""
    waits = _no_wait(monkeypatch)
    seen: dict[str, list[dict[str, Any]]] = {}
    _install(
        monkeypatch, seen, {"openai": [_Status(429), wire("llm", "openai", "stop")]}
    )
    OpenAIAdapter(
        model="m", label="g"
    ).execute(_raw(tmp_path), {}, _ctx(tmp_path), RunControl())
    assert len(seen["openai:call"]) == 2
    assert len(waits) == 1


# --------------------------------------------------------------------------- #
# OCR cloud : enveloppés par la même politique
# --------------------------------------------------------------------------- #


def _http_queue(
    monkeypatch: pytest.MonkeyPatch,
    replies: list[httpx.Response | Exception | Callable[[], httpx.Response]],
    seen: list[httpx.Request],
    timeouts: list[object] | None = None,
) -> None:
    """``httpx.Client`` servi par une file : chaque requête prend la suivante."""
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            return reply()
        return reply

    def client(**kwargs: Any) -> httpx.Client:
        if timeouts is not None:
            timeouts.append(kwargs.get("timeout"))
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    monkeypatch.setattr(httpx, "Client", client)


def _azure_202() -> httpx.Response:
    return httpx.Response(
        202,
        headers={"Operation-Location": f"{AZURE_ENDPOINT}/operations/r1?v=1"},
    )


def _azure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", AZURE_ENDPOINT)
    monkeypatch.setenv("AZURE_DOC_INTEL_KEY", _SECRET)


def test_azure_retries_a_throttled_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """429 sur la soumission → attendre, resoumettre ; la page n'est plus perdue.
    Une seule soumission acceptée : une page facturée."""
    _no_wait(monkeypatch)
    _azure_env(monkeypatch)
    seen: list[httpx.Request] = []
    _http_queue(
        monkeypatch,
        [
            httpx.Response(429, headers={"Retry-After": "2"}),
            _azure_202(),
            httpx.Response(200, json=wire("ocr", "azure_di", "folio_a")),
        ],
        seen,
    )
    adapter = AzureDocIntelAdapter(label="a")
    output = adapter.execute(_image(tmp_path), {}, _ctx(tmp_path), RunControl())
    assert [r.method for r in seen] == ["POST", "POST", "GET"]
    assert ArtifactType.RAW_TEXT in output.artifacts
    assert output.usage is not None and output.usage.billed_pages == 1


def test_azure_retries_a_failing_poll_without_resubmitting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un 503 sur la **sonde** se retente sur la sonde : resoumettre ferait
    analyser — et facturer — la page deux fois."""
    _no_wait(monkeypatch)
    _azure_env(monkeypatch)
    seen: list[httpx.Request] = []
    _http_queue(
        monkeypatch,
        [
            _azure_202(),
            httpx.Response(503),
            httpx.Response(200, json=wire("ocr", "azure_di", "folio_a")),
        ],
        seen,
    )
    output = AzureDocIntelAdapter(label="a").execute(
        _image(tmp_path), {}, _ctx(tmp_path), RunControl()
    )
    assert [r.method for r in seen] == ["POST", "GET", "GET"]
    assert output.usage is not None and output.usage.billed_pages == 1


def test_google_retries_a_server_error_and_a_cut_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5xx puis lecture coupée puis succès. La lecture coupée a pu être traitée
    (et facturée) par le service : elle compte ; le 503, refusé, non."""
    _no_wait(monkeypatch)
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", _SECRET)
    seen: list[httpx.Request] = []
    _http_queue(
        monkeypatch,
        [
            httpx.Response(503),
            httpx.ReadError("coupée"),
            httpx.Response(200, json=wire("ocr", "google_vision", "folio_a")),
        ],
        seen,
    )
    output = GoogleVisionAdapter(label="v").execute(
        _image(tmp_path), {}, _ctx(tmp_path), RunControl()
    )
    assert len(seen) == 3
    assert output.usage is not None and output.usage.billed_pages == 2


def test_a_refused_connection_is_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une connexion refusée n'a rien envoyé : rien n'a pu être facturé."""
    _no_wait(monkeypatch)
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", _SECRET)
    _http_queue(
        monkeypatch,
        [
            httpx.ConnectError("refusée"),
            httpx.Response(200, json=wire("ocr", "google_vision", "folio_a")),
        ],
        [],
    )
    output = GoogleVisionAdapter(label="v").execute(
        _image(tmp_path), {}, _ctx(tmp_path), RunControl()
    )
    assert output.usage is not None and output.usage.billed_pages == 1


def test_mistral_ocr_retries_a_429(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_wait(monkeypatch)
    seen: dict[str, list[dict[str, Any]]] = {}
    _install(
        monkeypatch,
        seen,
        {"mistral_ocr": [_Status(429), wire("ocr", "mistral_ocr", "folio_a")]},
    )
    output = MistralOCRAdapter(model="m", label="m").execute(
        _image(tmp_path), {}, _ctx(tmp_path), RunControl()
    )
    assert len(seen["mistralai:ocr"]) == 2
    (init,) = seen["mistralai:init"]
    assert "retry_config" in init and init["retry_config"] is None
    assert all(0 < c["timeout_ms"] <= 120_000 for c in seen["mistralai:ocr"])
    assert output.usage is not None and output.usage.billed_pages == 1


@pytest.mark.parametrize("engine", ["azure_di", "google_vision"])
def test_cloud_ocr_runs_under_a_finite_timeout(
    engine: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Avant : ``httpx.Client(timeout=None)`` — une connexion pendue gelait
    l'unité pour toujours."""
    _azure_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", _SECRET)
    replies: list[httpx.Response | Exception] = (
        [_azure_202(), httpx.Response(200, json=wire("ocr", "azure_di", "folio_a"))]
        if engine == "azure_di"
        else [httpx.Response(200, json=wire("ocr", "google_vision", "folio_a"))]
    )
    timeouts: list[object] = []
    _http_queue(monkeypatch, replies, [], timeouts)
    adapter = (
        AzureDocIntelAdapter(label="a")
        if engine == "azure_di"
        else GoogleVisionAdapter(label="v")
    )
    adapter.execute(_image(tmp_path), {}, _ctx(tmp_path), RunControl())
    (timeout,) = timeouts
    assert isinstance(timeout, (int, float)) and 0 < timeout <= 120.0


def test_ollama_runs_under_a_finite_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timeouts: list[object] = []
    _http_queue(
        monkeypatch,
        [httpx.Response(200, json=wire("llm", "ollama", "stop"))],
        [],
        timeouts,
    )
    OllamaAdapter(model="m", label="o", host=OLLAMA_HOST).execute(
        _raw(tmp_path), {}, _ctx(tmp_path), RunControl()
    )
    (timeout,) = timeouts
    assert isinstance(timeout, (int, float)) and 0 < timeout <= 600.0


def test_a_timed_out_ollama_call_is_a_deadline_not_an_engine_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un délai dépassé n'est pas une panne du moteur (D3) : motif
    ``cancelled`` (« arrêtée (délai) »), pas ``engine``."""

    def slow() -> httpx.Response:
        time.sleep(0.05)  # le délai de l'étape (10 ms) est écoulé
        raise httpx.ReadTimeout("trop long")

    _http_queue(monkeypatch, [slow], [])
    with pytest.raises(DeadlineExceeded) as raised:
        OllamaAdapter(model="m", label="o", host=OLLAMA_HOST, timeout=0.01).execute(
            _raw(tmp_path), {}, _ctx(tmp_path), RunControl()
        )
    assert failure_reason(raised.value) == "cancelled"


def test_a_page_answered_at_the_second_attempt_is_billed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corps relu = corps servi : la page retentée garde la réponse de la
    tentative qui a abouti, et un sidecar qui la relit rend le même texte."""
    _no_wait(monkeypatch)
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", _SECRET)
    body = wire("ocr", "google_vision", "folio_a")
    _http_queue(monkeypatch, [httpx.Response(429), httpx.Response(200, json=body)], [])
    output = GoogleVisionAdapter(label="v").execute(
        _image(tmp_path), {}, _ctx(tmp_path), RunControl()
    )
    sidecar = output.artifacts[ArtifactType.NATIVE_JSON]
    assert sidecar.uri is not None
    relu = json.loads(Path(sidecar.uri).read_text(encoding="utf-8"))
    assert relu == sdk_native(SdkResponse.model_validate(body), "x")


def test_a_refused_answer_is_billed_even_though_the_unit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un refus est écarté (unité ``failed``), mais ses jetons ont été
    facturés : ils accompagnent l'erreur jusqu'à l'économie."""
    seen: dict[str, list[dict[str, Any]]] = {}
    body = wire("llm", "anthropic", "refusal")
    _install(monkeypatch, seen, {"anthropic": [body]})
    with pytest.raises(AdapterStepError) as raised:
        AnthropicAdapter(model="m", label="c").execute(
            _raw(tmp_path), {}, _ctx(tmp_path), RunControl()
        )
    billed = raised.value.billed
    assert billed is not None
    assert billed.tokens_in == body["usage"]["input_tokens"]
    assert billed.tokens_out == body["usage"]["output_tokens"]
