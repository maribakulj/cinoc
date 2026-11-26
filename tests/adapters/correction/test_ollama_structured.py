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
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from cinoc.adapters.correction.ollama_structured import (
    OllamaStructuredClient,
    _bare_schema,
)
from cinoc.pipeline.run_control import RunControl

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
) -> Any:
    """``httpx.AsyncClient`` servi par un ``MockTransport`` : capture la requête
    (``ctor``, ``url``, ``body``, ``sent``), rend la réponse voulue — un corps
    d'un bloc, que le flux lit comme son dernier morceau."""
    real = httpx.AsyncClient

    def handle(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            captured.setdefault("sent", []).append(captured["body"])
        if raises is not None:
            raise raises
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=payload)

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        if captured is not None:
            captured["ctor"] = kwargs
        return real(transport=httpx.MockTransport(handle), **kwargs)

    return factory


def _call(
    monkeypatch: pytest.MonkeyPatch,
    client: OllamaStructuredClient,
    fake: Any,
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
        payload={"message": {"content": '{"lines": ["le soleil"]}'}, "done": True},
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
    assert body["stream"] is True  # en flux : interruptible en vol
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
    fake = _fake_client(
        payload={"message": {"content": "{}"}, "done": True}, captured=captured
    )
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
    fake = _fake_client(
        payload={"message": {"content": "{}"}, "done": True}, captured=captured
    )
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
def test_an_unreadable_answer_without_stop_reason_is_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans ``done_reason``, un JSON illisible n'est pas une troncature prouvée :
    il reste réessayable. L'extrait dans le message dit ce qui est revenu."""
    from saknussemm.core.protocols import ProviderTransientError

    fake = _fake_client(
        payload={"message": {"content": '{"lines": ["le sol'}, "done": True}
    )
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

    fake = _fake_client(payload={"message": {"content": "[1, 2]"}, "done": True})
    with pytest.raises(ProviderTransientError, match="list"):
        _call(monkeypatch, OllamaStructuredClient(), fake)


@_needs_saknussemm
@pytest.mark.parametrize(
    "body",
    [{"done": True}, {"message": None, "done": True}, {"message": {}, "done": True}],
)
def test_an_answer_without_content_is_transient(
    monkeypatch: pytest.MonkeyPatch, body: dict
) -> None:
    """Réponse 200 mais vide : le ``or {}`` / ``or ""`` du code ramène une chaîne
    vide, qui n'est pas du JSON — donc une erreur nommée, jamais un ``{}`` muet."""
    from saknussemm.core.protocols import ProviderTransientError

    with pytest.raises(ProviderTransientError):
        _call(monkeypatch, OllamaStructuredClient(), _fake_client(payload=body))


@_needs_saknussemm
def test_a_truncated_answer_is_permanent_and_sent_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le cas que ``num_ctx`` existe pour éviter, quand il arrive quand même :
    ``done_reason: length`` dit que le serveur a coupé. Le rejouer couperait à
    l'identique : erreur **permanente**, que ``saknussemm`` ne rejoue pas."""
    from saknussemm.core.protocols import ProviderPermanentError

    captured: dict[str, Any] = {}
    fake = _fake_client(
        payload={
            "message": {"content": '{"lines": ["le sol'},
            "done": True,
            "done_reason": "length",
        },
        captured=captured,
    )
    with pytest.raises(ProviderPermanentError, match="length") as capture:
        _call(monkeypatch, OllamaStructuredClient(), fake)
    assert len(captured["sent"]) == 1
    assert capture.value.retryable is False
    assert "num_ctx" in str(capture.value)


# --------------------------------------------------------------------------- #
# En flux : même corps, et un arrêt coupe l'appel en vol (S29a)
# --------------------------------------------------------------------------- #


def _streamed(chunks: list[dict[str, Any]]) -> Any:
    """Le serveur répond en morceaux NDJSON (``stream: true``)."""
    real = httpx.AsyncClient
    content = "".join(json.dumps(c) + "\n" for c in chunks).encode()
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, content=content))
    return lambda **kw: real(transport=transport, **kw)


@_needs_saknussemm
def test_the_stream_rebuilds_the_non_streamed_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le texte est concaténé, le dernier morceau porte arrêt et jetons : le
    corps gardé (sidecar ``NATIVE_JSON``) est celui du mode non diffusé."""
    final = {"model": "m", "done": True, "done_reason": "stop", "eval_count": 7,
             "message": {"role": "assistant", "content": ""}}
    chunks = [
        {"model": "m", "message": {"role": "assistant", "content": '{"lines": '},
         "done": False},
        {"model": "m", "message": {"role": "assistant", "content": '["le soleil"]}'},
         "done": False},
        final,
    ]
    client = OllamaStructuredClient()
    parsed, _ = _call(monkeypatch, client, _streamed(chunks))
    assert parsed == {"lines": ["le soleil"]}
    assert client.responses == [
        {**final, "message": {"role": "assistant",
                              "content": '{"lines": ["le soleil"]}'}}
    ]


@_needs_saknussemm
@pytest.mark.parametrize(
    ("chunks", "motif"),
    [
        ([{"error": "model runner has unexpectedly stopped"}], "unexpectedly"),
        ([{"message": {"content": '{"li'}, "done": False}], "interrompue"),
        ([{"message": {"content": "x"}, "done": False}, "pas du JSON"], "illisible"),
    ],
    ids=["erreur-en-flux", "flux-interrompu", "morceau-illisible"],
)
def test_a_broken_stream_is_transient(
    monkeypatch: pytest.MonkeyPatch, chunks: list[Any], motif: str
) -> None:
    """Une erreur de génération arrive **dans** le flux (en 200), un flux peut
    s'arrêter avant son dernier morceau : incidents passagers, réessayables."""
    from saknussemm.core.protocols import ProviderTransientError

    real = httpx.AsyncClient
    content = "".join(
        (c if isinstance(c, str) else json.dumps(c)) + "\n" for c in chunks
    ).encode()
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, content=content))
    with pytest.raises(ProviderTransientError, match=motif):
        _call(monkeypatch, OllamaStructuredClient(),
              lambda **kw: real(transport=transport, **kw))


class _Silent(BaseHTTPRequestHandler):
    """Reçoit la demande puis se tait 10 s (un modèle qui encode sa page)."""

    release = threading.Event()

    def do_POST(self) -> None:  # noqa: N802 — API de http.server
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.release.wait(10)
        try:
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except OSError:
            return

    def log_message(self, *_: object) -> None: ...


@pytest.fixture
def silent() -> Iterator[str]:
    handler = type("Handler", (_Silent,), {"release": threading.Event()})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    handler.release.set()
    httpd.shutdown()
    httpd.server_close()


@_needs_saknussemm
def test_a_stop_cuts_the_call_in_flight(
    silent: str, request: pytest.FixtureRequest
) -> None:
    """« Arrêter » → ``CorrectionAborted`` (l'annulation de ``saknussemm`` :
    ni rejouée ni prise pour une panne) en moins de 2 s, au lieu d'attendre la
    réponse — rouge avant S29a."""
    from saknussemm.errors import CorrectionAborted

    if sys.platform == "win32":  # ``shutdown`` d'un autre fil : mesuré sous Linux
        request.applymarker(pytest.mark.xfail(strict=False))
    control = RunControl()
    client = OllamaStructuredClient(host=silent, control=control)
    threading.Timer(0.5, control.trigger_cancel).start()
    started = time.monotonic()
    with pytest.raises(CorrectionAborted):
        asyncio.run(
            client.complete_structured("", "m", "corrige", {"lines": []}, _SCHEMA)
        )
    assert time.monotonic() - started < 2.0
