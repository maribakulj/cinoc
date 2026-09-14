"""``OllamaStructuredClient`` — le producteur LLM de la correction structurée.

Cette brique était la seule de la chaîne de correction à n'avoir **aucun** test :
`cinoc correct --producer ollama` traversait 46 lignes que le gate ne regardait
pas. Ce qui est vérifié ici est le **contrat**, pas la qualité d'un modèle :

* la requête posée à ``ollama`` (dont ``num_ctx`` **explicite** — le défaut du
  serveur est 2048 jetons et il tronque en silence) ;
* la traduction des échecs de transport vers la liste blanche de
  recouvrabilité de ``saknussemm``. Une exception hors liste ferait échouer le
  run au lieu d'être réessayée : confondre les deux, c'est soit abandonner sur
  un incident passager, soit réessayer en boucle une requête fautive.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any

import httpx
import pytest

from cinoc.adapters.correction.ollama_structured import (
    OllamaStructuredClient,
    _bare_schema,
)

#: Les classes d'erreur attendues appartiennent au contrat de ``saknussemm`` :
#: sans la bibliothèque, il n'y a pas de contrat à vérifier.
_needs_saknussemm = pytest.mark.skipif(
    importlib.util.find_spec("saknussemm") is None,
    reason="saknussemm absent — les classes d'erreur du contrat viennent de là.",
)

_SCHEMA = {"type": "object", "properties": {"lines": {"type": "array"}}}


def _fake_client(
    *,
    payload: Any = None,
    status: int = 200,
    text: str | None = None,
    raises: Exception | None = None,
    captured: dict[str, Any] | None = None,
) -> type:
    """Faux ``httpx.AsyncClient`` : capture la requête, rend la réponse voulue."""

    class _Fake:
        def __init__(self, **kwargs: Any) -> None:
            if captured is not None:
                captured["ctor"] = kwargs

        async def __aenter__(self) -> _Fake:
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def post(self, url: str, json: Any = None) -> httpx.Response:
            if captured is not None:
                captured["url"] = url
                captured["body"] = json
            if raises is not None:
                raise raises
            request = httpx.Request("POST", url)
            if text is not None:
                return httpx.Response(status, text=text, request=request)
            return httpx.Response(status, json=payload, request=request)

    return _Fake


def _call(
    monkeypatch: pytest.MonkeyPatch,
    client: OllamaStructuredClient,
    fake: type,
    **kwargs: Any,
) -> tuple[dict[str, Any], Any]:
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    return asyncio.run(
        client.complete_structured(
            "",
            kwargs.pop("model", "gemma4:e2b"),
            kwargs.pop("system_prompt", "corrige"),
            kwargs.pop("user_payload", {"lines": ["le ſoleil"]}),
            kwargs.pop("json_schema", _SCHEMA),
            **kwargs,
        )
    )


# --------------------------------------------------------------------------- #
# Le schéma nu — fonction pure, aucune dépendance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "envelope",
    [
        {"schema": _SCHEMA},  # enveloppe « response_format » courante
        {"json_schema": {"name": "x", "schema": _SCHEMA}},  # enveloppe OpenAI
        _SCHEMA,  # déjà nu
    ],
)
def test_the_schema_is_unwrapped_whatever_the_envelope(envelope: dict) -> None:
    """``format`` d'ollama attend le schéma nu : lui passer l'enveloppe OpenAI
    ne lève pas, le serveur contraint simplement sur le mauvais objet."""
    assert _bare_schema(envelope) == _SCHEMA


def test_an_unrecognised_envelope_is_passed_through() -> None:
    """Une forme inconnue traverse telle quelle plutôt que d'être vidée : le
    serveur dira ce qui ne va pas, on ne le devine pas à sa place."""
    inconnu = {"anyOf": [{"type": "object"}]}
    assert _bare_schema(inconnu) == inconnu


# --------------------------------------------------------------------------- #
# La requête posée au serveur
# --------------------------------------------------------------------------- #


@_needs_saknussemm
def test_the_request_pins_num_ctx_and_carries_the_bare_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``num_ctx`` explicite : le défaut d'ollama (2048) coupe une page de
    journal au milieu d'une chaîne, et le JSON tronqué ressemble alors à une
    hallucination du modèle."""
    captured: dict[str, Any] = {}
    fake = _fake_client(
        payload={"message": {"content": '{"lines": ["le soleil"]}'}},
        captured=captured,
    )
    parsed, raw = _call(
        monkeypatch,
        OllamaStructuredClient(host="http://ollama.test:11434/"),
        fake,
        json_schema={"schema": _SCHEMA},
    )

    assert parsed == {"lines": ["le soleil"]}
    assert raw is None
    # Le ``/`` final de l'hôte ne doit pas produire ``//api/chat``.
    assert captured["url"] == "http://ollama.test:11434/api/chat"
    body = captured["body"]
    assert body["model"] == "gemma4:e2b"
    assert body["stream"] is False
    assert body["format"] == _SCHEMA
    assert body["options"] == {"temperature": 0.0, "num_ctx": 8192}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][0]["content"] == "corrige"
    assert json.loads(body["messages"][1]["content"]) == {"lines": ["le ſoleil"]}


@_needs_saknussemm
def test_the_payload_keeps_its_accents_and_long_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ensure_ascii=False`` : un ``ſ`` échappé en ``\\u017f`` traverse mais
    gonfle le contexte, et c'est exactement ce corpus-là qu'on corrige."""
    captured: dict[str, Any] = {}
    fake = _fake_client(payload={"message": {"content": "{}"}}, captured=captured)
    _call(
        monkeypatch,
        OllamaStructuredClient(),
        fake,
        user_payload={"lines": ["étoile ſon"]},
    )
    assert "étoile ſon" in captured["body"]["messages"][1]["content"]


@_needs_saknussemm
def test_num_ctx_and_temperature_are_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake = _fake_client(payload={"message": {"content": "{}"}}, captured=captured)
    _call(
        monkeypatch,
        OllamaStructuredClient(num_ctx=32768, timeout=12.0),
        fake,
        temperature=0.7,
    )
    assert captured["body"]["options"] == {"temperature": 0.7, "num_ctx": 32768}
    assert captured["ctor"]["timeout"] == 12.0


# --------------------------------------------------------------------------- #
# La traduction des échecs — la liste blanche de recouvrabilité
# --------------------------------------------------------------------------- #


@_needs_saknussemm
@pytest.mark.parametrize("status", [400, 404, 422])
def test_a_4xx_is_permanent(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    """Réessayer une requête fautive la referait échouer à l'identique."""
    from saknussemm.core.protocols import ProviderPermanentError

    with pytest.raises(ProviderPermanentError, match=str(status)):
        _call(monkeypatch, OllamaStructuredClient(), _fake_client(status=status))


@_needs_saknussemm
@pytest.mark.parametrize("status", [500, 502, 503])
def test_a_5xx_is_transient(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    from saknussemm.core.protocols import ProviderTransientError

    with pytest.raises(ProviderTransientError, match=str(status)):
        _call(monkeypatch, OllamaStructuredClient(), _fake_client(status=status))


@_needs_saknussemm
@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectTimeout("délai dépassé"),
        httpx.ReadTimeout("lecture trop lente"),
        httpx.ConnectError("connexion refusée"),
    ],
)
def test_an_unreachable_server_is_transient(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    """Un serveur local qui charge un modèle de plusieurs Go est injoignable un
    moment : c'est un incident passager, pas une requête fautive."""
    from saknussemm.core.protocols import ProviderTransientError

    with pytest.raises(ProviderTransientError, match="injoignable"):
        _call(monkeypatch, OllamaStructuredClient(), _fake_client(raises=exc))


@_needs_saknussemm
def test_a_truncated_answer_is_transient_and_shows_what_came_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le cas que ``num_ctx`` existe pour éviter : la réponse est coupée, donc
    illisible en JSON. L'extrait dans le message évite de conclure « le modèle
    hallucine » là où c'est le serveur qui a tranché."""
    from saknussemm.core.protocols import ProviderTransientError

    fake = _fake_client(payload={"message": {"content": '{"lines": ["le sol'}})
    with pytest.raises(ProviderTransientError, match="tronquée") as capture:
        _call(monkeypatch, OllamaStructuredClient(), fake)
    assert "le sol" in str(capture.value)


@_needs_saknussemm
def test_a_json_answer_that_is_not_an_object_is_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``[...]`` est du JSON valide : sans ce contrôle, l'appelant recevrait une
    liste là où il attend un objet et casserait plus loin, hors contexte."""
    from saknussemm.core.protocols import ProviderTransientError

    fake = _fake_client(payload={"message": {"content": "[1, 2]"}})
    with pytest.raises(ProviderTransientError, match="list"):
        _call(monkeypatch, OllamaStructuredClient(), fake)


@_needs_saknussemm
@pytest.mark.parametrize("body", [{}, {"message": None}, {"message": {}}])
def test_an_answer_without_content_is_transient(
    monkeypatch: pytest.MonkeyPatch, body: dict
) -> None:
    """Réponse 200 mais vide : le ``or {}`` / ``or ""`` du code ramène une chaîne
    vide, qui n'est pas du JSON — donc une erreur nommée, jamais un ``{}`` muet."""
    from saknussemm.core.protocols import ProviderTransientError

    with pytest.raises(ProviderTransientError):
        _call(monkeypatch, OllamaStructuredClient(), _fake_client(payload=body))
