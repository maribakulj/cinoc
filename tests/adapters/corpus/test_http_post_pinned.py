"""``post_json`` se connecte à l'IP **validée**, sans résoudre l'hôte une 2ᵉ fois.

Défaut réel (D-263) : le segmenteur distant validait son endpoint avec
``assert_public_url`` puis jetait les IP épinglées et laissait ``httpx``
résoudre le nom à nouveau — la fenêtre exacte d'un DNS rebinding. L'endpoint
vient d'un formulaire web.

La preuve est comportementale : l'hôte ``rebind.invalid`` ne résout nulle part
(TLD réservé, RFC 6761). La validation est simulée pour le « résoudre » vers le
serveur local ; si la connexion repassait par le DNS, elle échouerait.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cinoc.adapters.corpus import _http
from cinoc.adapters.corpus._http import HttpFetchError, post_json


@pytest.fixture
def server() -> Iterator[int]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 — API http.server
            n = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(n)
            if self.path == "/redirect":
                self.send_response(307)
                self.send_header("Location", "http://rebind.invalid/ailleurs")
                self.end_headers()
                return
            payload = json.dumps(
                {"recu": len(body), "auth": self.headers.get("Authorization")}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: object) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()


@pytest.fixture
def pinned_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http, "assert_public_url", lambda url: ("127.0.0.1",))


@pytest.mark.usefixtures("pinned_to_loopback")
def test_post_connects_to_the_validated_ip_not_a_fresh_dns_answer(
    server: int,
) -> None:
    result = post_json(
        f"http://rebind.invalid:{server}/detect",
        content=b"octets",
        headers={"Authorization": "Bearer t"},
    )
    assert result == {"recu": 6, "auth": "Bearer t"}


@pytest.mark.usefixtures("pinned_to_loopback")
def test_post_follows_no_redirect(server: int) -> None:
    with pytest.raises(HttpFetchError, match="redirection refusée"):
        post_json(f"http://rebind.invalid:{server}/redirect", content=b"x")


def test_post_refuses_a_private_endpoint() -> None:
    with pytest.raises(_http.SsrfError):
        post_json("http://127.0.0.1:9/detect", content=b"x")
