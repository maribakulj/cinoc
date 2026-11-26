"""Ollama en flux : un arrêt coupe l'appel en vol (D-300, reste de S27).

``httpx.Client.close()`` depuis un autre fil ne réveille pas une lecture
bloquante : sur Ollama CPU, ~115 s s'écoulaient entre « Arrêter » et
« Arrêté » (D-299). L'appel est désormais diffusé (``stream: true``), l'arrêt
sondé entre deux morceaux, et le socket coupé avant le premier (encodage de
l'image). Le corps reconstitué est celui du mode non diffusé.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from cinoc.adapters.llm.ollama import _invoke_ollama, _read_stream
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError, DeadlineExceeded, RunCancelledError
from cinoc.pipeline.run_control import RunControl

#: Forme réelle (serveur Ollama 0.x, ``qwen2.5vl:3b``) : morceaux ``done:
#: false`` puis un dernier morceau à message vide qui porte l'arrêt et les jetons.
_CHUNKS = [
    {"model": "m", "created_at": "t1",
     "message": {"role": "assistant", "content": "Le"}, "done": False},
    {"model": "m", "created_at": "t2",
     "message": {"role": "assistant", "content": " chat."}, "done": False},
    {"model": "m", "created_at": "t3", "message": {"role": "assistant", "content": ""},
     "done": True, "done_reason": "stop", "total_duration": 9, "load_duration": 1,
     "prompt_eval_count": 34, "prompt_eval_cached_count": 0,
     "prompt_eval_duration": 2, "eval_count": 3, "eval_duration": 5},
]
#: Ce que rend ``stream: false`` pour la même génération.
_BODY = {**_CHUNKS[-1], "message": {"role": "assistant", "content": "Le chat."}}


def _read(lines: list[str], control: RunControl | None = None) -> dict[str, Any]:
    return _read_stream(
        lines, control=control or RunControl(), deadline=Deadline.infinite(),
        model="m",
    )


def test_the_stream_rebuilds_the_non_streamed_body() -> None:
    """Même texte, mêmes jetons, mêmes clés : le sidecar natif ne change pas."""
    assert _read([json.dumps(c) for c in _CHUNKS] + [""]) == _BODY
    # Un serveur qui répond d'un bloc (cassettes) reste lu.
    assert _read([json.dumps(_BODY)]) == _BODY


def test_thinking_is_concatenated_like_content() -> None:
    chunks = [
        {"message": {"content": "", "thinking": "Je "}, "done": False},
        {"message": {"content": "", "thinking": "pense."}, "done": False},
        {"message": {"content": "Oui"}, "done": True, "done_reason": "stop"},
    ]
    body = _read([json.dumps(c) for c in chunks])
    assert body["message"] == {"content": "Oui", "thinking": "Je pense."}


def test_a_cut_stream_or_garbage_is_an_engine_fault() -> None:
    with pytest.raises(AdapterStepError, match="interrompue"):
        _read([json.dumps(c) for c in _CHUNKS[:2]])
    with pytest.raises(AdapterStepError, match="illisible"):
        _read(["{pas du json"])


def test_an_error_chunk_is_returned_for_the_caller_to_raise() -> None:
    assert _read([json.dumps({"error": "out of memory"})]) == {"error": "out of memory"}


def test_stop_is_polled_between_chunks() -> None:
    control = RunControl()

    def lines() -> Iterator[str]:
        yield json.dumps(_CHUNKS[0])
        control.trigger_cancel()
        yield json.dumps(_CHUNKS[1])
        pytest.fail("lu après l'arrêt")

    with pytest.raises(RunCancelledError):
        _read_stream(lines(), control=control, deadline=Deadline.infinite(), model="m")


def test_the_step_deadline_is_polled_between_chunks() -> None:
    with pytest.raises(DeadlineExceeded):
        _read_stream(
            [json.dumps(_CHUNKS[0])], control=RunControl(),
            deadline=Deadline.at_monotonic(0.0), model="m",
        )


class _Slow(BaseHTTPRequestHandler):
    """Serveur qui lit la requête puis se tait : un VLM qui encode l'image
    (~30 s par page sur CPU), ou une génération dont les morceaux tardent."""

    release = threading.Event()
    streamed = False

    def do_POST(self) -> None:  # noqa: N802 — API de BaseHTTPRequestHandler
        self.rfile.read(int(self.headers["Content-Length"]))
        try:
            if self.streamed:
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                for _ in range(100):  # 100 morceaux à 0,1 s : 10 s de génération
                    piece = {"message": {"content": "x"}, "done": False}
                    self.wfile.write(json.dumps(piece).encode() + b"\n")
                    self.wfile.flush()
                    time.sleep(0.1)
            else:
                self.release.wait(10)
            body = json.dumps(_BODY).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, *_: object) -> None: ...


@pytest.fixture(params=[False, True], ids=["avant-le-premier-morceau", "en-generation"])
def server(request: pytest.FixtureRequest) -> Iterator[str]:
    handler = type("Handler", (_Slow,), {"release": threading.Event(),
                                         "streamed": request.param})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    handler.release.set()
    httpd.shutdown()
    httpd.server_close()


def test_stop_cuts_the_call_in_flight(
    server: str, request: pytest.FixtureRequest
) -> None:
    """« Arrêter » → l'appel rend la main en moins de 2 s, au lieu d'attendre
    la réponse (10 s ici, ~115 s mesurées sur Ollama CPU)."""
    if sys.platform == "win32" and "avant" in request.node.name:
        # Que ``shutdown`` d'un autre fil réveille un ``recv`` bloqué n'est
        # vérifié que sous Linux (mesuré) ; le sondage entre morceaux, lui,
        # vaut partout (D-300, point ouvert).
        request.applymarker(pytest.mark.xfail(strict=False))
    control = RunControl()
    threading.Timer(0.5, control.trigger_cancel).start()
    started = time.monotonic()
    with pytest.raises(RunCancelledError):
        _invoke_ollama(
            model="m", prompt="p", host=server, deadline=Deadline.in_seconds(60),
            control=control, options={},
        )
    assert time.monotonic() - started < 2.0


def test_the_payload_asks_for_a_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        lines = "\n".join(json.dumps(c) for c in _CHUNKS) + "\n"
        return httpx.Response(200, content=lines.encode())

    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    completion = _invoke_ollama(
        model="m", prompt="p", host="http://127.0.0.1:9",
        deadline=Deadline.in_seconds(5), control=RunControl(), options={},
    )
    assert sent["stream"] is True
    assert completion.text == "Le chat."
    assert (completion.tokens_in, completion.tokens_out) == (34, 3)
    assert completion.native == _BODY
