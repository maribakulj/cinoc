"""``available_models`` sous les **vrais** SDK (extras), transport factice.

``tests/app/test_models.py`` prouve la lecture sur des SDK factices ; ce
fichier-ci prouve ce dont elle dépend — que ``models.list`` des vrais SDK rend,
une fois passé par ``sdk_native``, le corps des cassettes : pagination
d'Anthropic (``has_more``/``after_id``), alias résolu par ``models.retrieve``
(404 → absent), cartes Mistral. Ignoré sans les extras ; aucun réseau.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

import pytest

from cinoc.app.models import available_models

_CASSETTES = Path(__file__).resolve().parents[1] / "fixtures" / "cassettes" / "models"


def _wire(provider: str, scenario: str) -> Any:
    data = json.loads((_CASSETTES / f"{provider}.json").read_text("utf-8"))
    return data["responses"][scenario]


def _client(httpx2: Any, handle: Any) -> Any:
    return httpx2.Client(transport=httpx2.MockTransport(handle))


def test_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    openai = pytest.importorskip("openai")
    httpx2 = pytest.importorskip("httpx2")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    body = _wire("openai", "list")
    monkeypatch.setattr(
        openai,
        "OpenAI",
        functools.partial(
            openai.OpenAI,
            http_client=_client(httpx2, lambda _r: httpx2.Response(200, json=body)),
        ),
    )
    listing = available_models("openai")
    assert listing.unavailable is None
    assert [m.name for m in listing.models] == sorted(i["id"] for i in body["data"])
    assert all(m.vision is None for m in listing.models)


def test_anthropic_pages_and_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    anthropic = pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    urls: list[str] = []

    def handle(request: Any) -> Any:
        urls.append(str(request.url))
        if request.url.path == "/v1/models":
            page = "page2" if "after_id" in str(request.url) else "page1"
            return httpx2.Response(200, json=_wire("anthropic", page))
        if request.url.path == "/v1/models/claude-test-haiku":
            return httpx2.Response(200, json=_wire("anthropic", "retrieve_alias"))
        return httpx2.Response(
            404, json={"type": "error", "error": {"type": "not_found_error"}}
        )

    monkeypatch.setattr(
        anthropic,
        "Anthropic",
        functools.partial(anthropic.Anthropic, http_client=_client(httpx2, handle)),
    )
    listing = available_models("anthropic", wanted="claude-test-haiku")
    assert len(listing.models) == 3 and listing.offers("claude-test-haiku")
    assert urls[1].endswith("after_id=claude-test-ancien-20240229")
    absent = available_models("anthropic", wanted="claude-test-inexistant")
    assert absent.unavailable is None
    assert not absent.offers("claude-test-inexistant")


def test_mistral(monkeypatch: pytest.MonkeyPatch) -> None:
    client = pytest.importorskip("mistralai.client")
    httpx2 = pytest.importorskip("httpx2")
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    body = _wire("mistral", "list")
    monkeypatch.setattr(
        client,
        "Mistral",
        functools.partial(
            client.Mistral,
            client=_client(httpx2, lambda _r: httpx2.Response(200, json=body)),
        ),
    )
    listing = available_models("mistral")
    assert listing.unavailable is None
    assert listing.offers("mistral-test-small-2506")
    assert {m.name: m.vision for m in listing.models}["mistral-test-small-latest"]
