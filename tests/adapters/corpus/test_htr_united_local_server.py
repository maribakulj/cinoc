"""Fetch HTR-United **réel** contre un serveur loopback (déterministe, CI)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml

from cinoc.adapters.corpus import _http
from cinoc.adapters.corpus.htr_united import fetch_catalogue

_YAML = b"""
- title: Loopback Corpus
  url: https://github.com/HTR-United/loopback
  description: servi en local
  language: [fr]
"""


@pytest.fixture
def server() -> Iterator[int]:
    holder: dict[str, int] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if not self.path.endswith(".yml"):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/yaml")
            self.send_header("Content-Length", str(len(_YAML)))
            self.end_headers()
            self.wfile.write(_YAML)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    holder["port"] = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield holder["port"]
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_fetch_real_catalogue(server: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http, "assert_public_url", lambda url: None)
    cat = fetch_catalogue(catalogue_url=f"http://127.0.0.1:{server}/htr-united.yml")
    assert not cat.is_demo and cat.source == "remote"
    assert [e.id for e in cat.entries] == ["loopback"]
    assert cat.entries[0].languages == ("fr",)


def test_an_index_with_aliases_falls_back_to_the_demo(
    server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'index est une source tierce lue par la page d'accueil : il passe par
    le chargeur **sans alias** (D-300). L'index réel n'en a aucun ; un index
    qui en porte est refusé (repli démo), comme un « billion laughs »."""
    from cinoc.adapters.corpus.htr_united import parse_catalogue

    alias = (
        "- &corpus {title: A, url: https://github.com/HTR-United/a}\n"
        "- *corpus\n"
    )
    with pytest.raises(yaml.YAMLError, match="alias"):
        parse_catalogue(alias)
    monkeypatch.setattr(_http, "assert_public_url", lambda url: None)
    monkeypatch.setattr(
        "cinoc.adapters.corpus.htr_united.fetch_text", lambda *_a, **_k: alias
    )
    assert fetch_catalogue(catalogue_url="http://127.0.0.1:1/x.yml").is_demo
