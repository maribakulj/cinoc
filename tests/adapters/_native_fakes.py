"""Faux clients des sept moteurs distants, servis par cassette — aucun réseau.

Ce qui est faux est le **transport**, jamais le code de l'adaptateur : les SDK
(openai, anthropic, mistralai) sont remplacés dans ``sys.modules`` par des
modules minimaux dont le client rend un **modèle pydantic** construit sur le
corps de la cassette, comme le font les vrais SDK ; Azure, Google et Ollama
(``httpx`` direct) reçoivent un ``httpx.MockTransport``. Le chemin de production
— ``_openai_client``, ``_invoke_azure_di``, ``sdk_native``… — s'exécute donc en
entier.

Le faux SDK range dans un attribut **privé** un identifiant qui contient la clé
reçue : c'est ce que font les vrais (``_request_id``, ``_workspace_id`` chez
anthropic). Un sidecar qui le contiendrait aurait sérialisé l'objet par
``__dict__`` au lieu de son corps.
"""

from __future__ import annotations

import json
import sys
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, PrivateAttr

CASSETTES = Path(__file__).resolve().parents[1] / "fixtures" / "cassettes"

#: La clé que chaque faux client reçoit — elle ne doit apparaître dans aucun
#: sidecar, aucun cache, aucun ``RunResult``.
SECRET = "sk-cinoc-NE-DOIT-PAS-FUIR-0123456789"

#: Variable d'environnement de la clé, par fournisseur.
KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "mistral_ocr": "MISTRAL_API_KEY",
    "google_vision": "GOOGLE_VISION_API_KEY",
    "azure_di": "AZURE_DOC_INTEL_KEY",
}
AZURE_ENDPOINT = "https://cinoc-test.cognitiveservices.azure.com"
OLLAMA_HOST = "http://localhost:11434"


def wire(family: str, provider: str, scenario: str) -> dict[str, Any]:
    """Corps d'API d'une cassette (``llm/<p>.json`` ou ``ocr/<p>.json``)."""
    data = json.loads(
        (CASSETTES / family / f"{provider}.json").read_text(encoding="utf-8")
    )
    body: dict[str, Any] = data["responses"][scenario]
    return body


class SdkResponse(BaseModel):
    """Modèle de réponse d'un SDK : champs du fil + identifiant privé."""

    model_config = ConfigDict(extra="allow")
    _request_id: str | None = PrivateAttr(default=None)


def _sdk_response(body: dict[str, Any], api_key: str) -> SdkResponse:
    response = SdkResponse.model_validate(body)
    response._request_id = f"req-{api_key}"
    return response


#: ``Callable[[], dict]`` : la prochaine réponse à rendre (une file par cassette).
Next = Callable[[], dict[str, Any]]


class FakeHttpClient:
    """Client HTTP d'un faux SDK (``DefaultHttpxClient``, ``httpx2.Client``) :
    reçoit les crochets de coupure (``cut_on_cancel_hooks``), n'envoie rien. La
    coupure en vol se teste sur les vrais SDK (``test_cut_in_flight``)."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False

    def close(self) -> None:
        self.closed = True


def real_sdk_transport(
    monkeypatch: pytest.MonkeyPatch, sdk: str, transport: object
) -> None:
    """Sert un **vrai** SDK par ``transport`` (un ``httpx2.MockTransport``), en
    gardant le client HTTP que l'adaptateur construit — crochets de coupure
    compris : ``DefaultHttpxClient`` d'``openai``/``anthropic``, ``httpx2.Client``
    pour ``mistralai`` (seul ``transport`` est ajouté)."""
    import functools

    module: Any = pytest.importorskip("httpx2" if sdk == "mistralai" else sdk)
    name = "Client" if sdk == "mistralai" else "DefaultHttpxClient"
    monkeypatch.setattr(
        module, name, functools.partial(getattr(module, name), transport=transport)
    )


def fake_sdk_module(name: str, **attributes: object) -> types.ModuleType:
    """Module factice d'un SDK (openai, anthropic) : ses attributs, plus le
    ``DefaultHttpxClient`` que l'adaptateur construit."""
    module = types.ModuleType(name)
    module.DefaultHttpxClient = FakeHttpClient  # type: ignore[attr-defined]
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def install_fake_sdks(
    monkeypatch: pytest.MonkeyPatch, next_body: dict[str, Next]
) -> None:
    """Remplace ``openai``, ``anthropic`` et ``mistralai`` dans ``sys.modules``.

    ``next_body[nom]`` rend le corps de la prochaine réponse (``openai``,
    ``anthropic``, ``mistral`` pour le chat, ``mistral_ocr`` pour l'OCR).
    """

    class _Erreur(Exception):
        pass

    def _client(provider: str, method: str) -> type:
        class _Client:
            def __init__(self, api_key: str, **_: Any) -> None:
                self.api_key = api_key

                def call(**_kwargs: Any) -> SdkResponse:
                    return _sdk_response(next_body[provider](), self.api_key)

                leaf = types.SimpleNamespace(**{method: call})
                if provider == "openai":
                    self.chat = types.SimpleNamespace(completions=leaf)
                elif provider == "anthropic":
                    self.messages = leaf
                else:
                    self.chat = leaf

                def ocr(**_kwargs: Any) -> SdkResponse:
                    return _sdk_response(next_body["mistral_ocr"](), self.api_key)

                self.ocr = types.SimpleNamespace(process=ocr)

        return _Client

    openai = fake_sdk_module(
        "openai", OpenAI=_client("openai", "create"), OpenAIError=_Erreur
    )
    anthropic = fake_sdk_module(
        "anthropic", Anthropic=_client("anthropic", "create"), AnthropicError=_Erreur
    )
    for name, module in (("openai", openai), ("anthropic", anthropic)):
        monkeypatch.setitem(sys.modules, name, module)
    install_fake_mistralai(monkeypatch, _client("mistral", "complete"))


def install_fake_mistralai(monkeypatch: pytest.MonkeyPatch, client: type) -> None:
    """``mistralai`` 3.x factice : le client vit dans ``mistralai.client``
    (depuis la 2.x), le paquet racine n'exporte plus ``Mistral``. Avec lui,
    ``httpx2`` (sa dépendance, dont l'adaptateur construit le client HTTP)."""
    racine = types.ModuleType("mistralai")
    racine.__path__ = []  # type: ignore[attr-defined]  # un paquet, pas un module
    sous = types.ModuleType("mistralai.client")
    sous.Mistral = client  # type: ignore[attr-defined]
    racine.client = sous  # type: ignore[attr-defined]
    httpx2 = types.ModuleType("httpx2")
    httpx2.Client = FakeHttpClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mistralai", racine)
    monkeypatch.setitem(sys.modules, "mistralai.client", sous)
    monkeypatch.setitem(sys.modules, "httpx2", httpx2)


def install_fake_http(
    monkeypatch: pytest.MonkeyPatch,
    next_body: dict[str, Next],
    seen: list[httpx.Request] | None = None,
) -> None:
    """``httpx.Client`` reçoit un ``MockTransport`` : Azure, Google, Ollama.

    Azure suit son flux réel : ``POST …:analyze`` → 202 + ``Operation-Location``,
    puis la sonde rend le corps terminal de la cassette.
    """
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        url = str(request.url)
        if url.startswith(AZURE_ENDPOINT) and request.method == "POST":
            return httpx.Response(
                202,
                headers={
                    "Operation-Location": f"{AZURE_ENDPOINT}/documentintelligence/"
                    "documentModels/prebuilt-read/analyzeResults/r-1"
                    "?api-version=2024-11-30"
                },
            )
        if url.startswith(AZURE_ENDPOINT):
            return httpx.Response(200, json=next_body["azure_di"]())
        if "vision.googleapis.com" in url:
            return httpx.Response(200, json=next_body["google_vision"]())
        if url == f"{OLLAMA_HOST}/api/tags":
            # Sonde du digest (``OllamaAdapter.system_binaries``), avant la
            # première page : elle ne consomme pas la file des réponses.
            return httpx.Response(200, json={"models": []})
        if url.startswith(OLLAMA_HOST):
            return httpx.Response(200, json=next_body["ollama"]())
        raise AssertionError(f"requête inattendue : {url}")

    def client(**kwargs: Any) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    monkeypatch.setattr(httpx, "Client", client)


def set_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in set(KEY_ENV.values()):
        monkeypatch.setenv(env, SECRET)
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", AZURE_ENDPOINT)


def cut_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plus aucun SDK importable, plus aucun appel de moteur : hors ligne.

    Seule passe la sonde du digest Ollama (``GET /api/tags``, que
    ``system_binaries`` lit avant la première page pour la clé d'unité) :
    ce n'est pas une inférence, et elle rend ici une liste vide — digest
    inconnu, comme un serveur sans le modèle. Toute autre requête échoue.
    """
    for name in ("openai", "anthropic", "mistralai", "mistralai.client"):
        monkeypatch.setitem(sys.modules, name, None)
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        raise AssertionError("appel réseau pendant une relecture hors ligne")

    def client(**kwargs: Any) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    monkeypatch.setattr(httpx, "Client", client)


class OllamaStream:
    """La réponse **diffusée** d'un faux client Ollama (``client.stream``) :
    le corps non diffusé rendu en un seul morceau NDJSON, ``done`` posé — ce
    que le vrai serveur envoie en dernier."""

    def __init__(self, response: Any) -> None:
        self._response = response

    def __enter__(self) -> OllamaStream:
        return self

    def __exit__(self, *_: object) -> None: ...

    def raise_for_status(self) -> None:
        self._response.raise_for_status()

    def iter_lines(self) -> Iterator[str]:
        yield json.dumps({"done": True, **self._response.json()})


__all__ = [
    "OllamaStream",
    "AZURE_ENDPOINT",
    "CASSETTES",
    "KEY_ENV",
    "OLLAMA_HOST",
    "SECRET",
    "SdkResponse",
    "cut_network",
    "install_fake_http",
    "install_fake_mistralai",
    "install_fake_sdks",
    "set_keys",
    "wire",
]
