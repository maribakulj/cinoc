"""Fuite de credentials sur redirection : l'``Authorization`` ne doit pas suivre
vers un **hôte différent** (régression de sécurité D-050)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cinoc.adapters.corpus import _http
from cinoc.adapters.corpus._http import fetch_json

_AUTH = {"Authorization": "Token SECRET"}
_seen: dict[str, str | None] = {}


@pytest.fixture
def server() -> Iterator[int]:
    _seen.clear()
    holder: dict[str, int] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def _redirect(self, location: str) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            _seen[self.path] = self.headers.get("Authorization")
            port = holder["port"]
            if self.path == "/cross":
                self._redirect(f"http://localhost:{port}/cross-target")
            elif self.path == "/same":
                self._redirect(f"http://127.0.0.1:{port}/same-target")
            else:
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    holder["port"] = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield holder["port"]
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_auth_not_forwarded_cross_host(
    server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_http, "assert_public_url", lambda url: None)
    fetch_json(f"http://127.0.0.1:{server}/cross", headers=_AUTH)
    assert _seen["/cross"] == "Token SECRET"  # origine : auth envoyée
    assert _seen["/cross-target"] is None  # autre hôte (localhost) : auth retirée


def test_auth_kept_same_host(server: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http, "assert_public_url", lambda url: None)
    fetch_json(f"http://127.0.0.1:{server}/same", headers=_AUTH)
    assert _seen["/same-target"] == "Token SECRET"  # même hôte : auth conservée


def test_auth_not_forwarded_to_another_port_of_the_same_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L'origine est (schéma, hôte, port), pas le seul nom d'hôte (D-263).

    Comparer le nom d'hôte seul renvoyait le jeton sur une redirection vers un
    autre port — ou, par le même chemin, sur une rétrogradation https → http.
    """
    monkeypatch.setattr(_http, "assert_public_url", lambda url: None)
    seen: dict[str, str | None] = {}

    class Target(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def do_GET(self) -> None:
            seen["target"] = self.headers.get("Authorization")
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
    target_port = target.server_address[1]

    class Origin(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def do_GET(self) -> None:
            seen["origin"] = self.headers.get("Authorization")
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target_port}/x")
            self.send_header("Content-Length", "0")
            self.end_headers()

    origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
    threads = [
        threading.Thread(target=s.serve_forever, daemon=True) for s in (target, origin)
    ]
    for t in threads:
        t.start()
    try:
        fetch_json(f"http://127.0.0.1:{origin.server_address[1]}/", headers=_AUTH)
    finally:
        origin.shutdown()
        target.shutdown()
    assert seen["origin"] == "Token SECRET"
    assert seen["target"] is None
