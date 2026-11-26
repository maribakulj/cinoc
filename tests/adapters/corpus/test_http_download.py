"""`download` en flux disque (Lot B) : `.part` au fil de l'eau, `os.replace`
atomique, plafond, aucun fichier partiel ; auth transmise à l'hôte d'origine ;
**seule une image est écrite** (octets magiques, défaut 4 de l'audit de
substitution).

Serveur loopback réel (vrai chemin httpx) ; le garde-fou SSRF est neutralisé
*ici seulement* (`assert_public_url` → no-op) pour viser 127.0.0.1.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cinoc.adapters.corpus import _http
from cinoc.adapters.corpus._http import (
    HttpFetchError,
    NotAnImageError,
    download,
    image_format,
)

_seen_auth: dict[str, str | None] = {}

_PNG_HEAD = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
#: Chemin servi → (corps, Content-Type ou None).
_ROUTES: dict[str, tuple[bytes, str | None]] = {
    "/img": (_PNG_HEAD + b"DATA", None),
    "/big": (_PNG_HEAD + b"x" * 1000, "image/png"),
    "/json": (b'{"@context": "http://iiif.io/api/image/2/"}', "application/json"),
    "/error-as-jpeg": (b"<html><body>503</body></html>", "image/jpeg"),
    "/jpeg-as-text": (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00", "text/plain"),
    "/short-jpeg": (b"\xff\xd8\xff", "image/jpeg"),
    "/empty": (b"", "image/jpeg"),
}


@pytest.fixture
def server() -> Iterator[int]:
    """Sert ``_ROUTES``, journalise l'auth."""
    _seen_auth.clear()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def do_GET(self) -> None:
            _seen_auth[self.path] = self.headers.get("Authorization")
            body, content_type = _ROUTES[self.path]
            self.send_response(200)
            if content_type:
                self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _no_ssrf(monkeypatch: pytest.MonkeyPatch) -> None:
    # Vise le loopback : on lève le garde-fou SSRF pour CES tests seulement.
    monkeypatch.setattr(_http, "assert_public_url", lambda url: None)


def test_download_streams_atomic_no_partial(server: int, tmp_path: Path) -> None:
    dest = tmp_path / "out.bin"
    download(f"http://127.0.0.1:{server}/img", dest)
    assert dest.read_bytes() == _PNG_HEAD + b"DATA"
    # Renommage atomique : aucun `.part` ne subsiste.
    assert not dest.with_name(dest.name + ".part").exists()
    assert list(tmp_path.iterdir()) == [dest]


def test_download_over_cap_leaves_no_file(
    server: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_http, "IMAGE_MAX_BYTES", 10)
    dest = tmp_path / "out.bin"
    with pytest.raises(HttpFetchError, match="plafond"):
        download(f"http://127.0.0.1:{server}/big", dest)
    # Ni destination, ni fichier partiel : rien laissé derrière.
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()
    assert list(tmp_path.iterdir()) == []


def test_download_forwards_auth_to_origin(server: int, tmp_path: Path) -> None:
    download(
        f"http://127.0.0.1:{server}/img",
        tmp_path / "out.bin",
        headers={"Authorization": "Token SECRET"},
    )
    assert _seen_auth["/img"] == "Token SECRET"


@pytest.mark.parametrize(
    ("path", "declared"),
    [
        ("/json", "application/json"),  # info.json d'un service IIIF
        ("/error-as-jpeg", "image/jpeg"),  # le Content-Type ne suffit pas
        ("/empty", "image/jpeg"),
    ],
)
def test_download_refuses_non_image_without_writing(
    server: int, tmp_path: Path, path: str, declared: str
) -> None:
    dest = tmp_path / "page_0001.jpg"
    with pytest.raises(NotAnImageError, match=declared):
        download(f"http://127.0.0.1:{server}{path}", dest)
    assert list(tmp_path.iterdir()) == []  # ni faux .jpg, ni .part


@pytest.mark.parametrize("path", ["/jpeg-as-text", "/short-jpeg"])
def test_download_trusts_magic_bytes_over_content_type(
    server: int, tmp_path: Path, path: str
) -> None:
    # Une vraie image mal étiquetée, ou plus courte que la fenêtre de détection,
    # est écrite telle quelle.
    dest = tmp_path / "page.jpg"
    download(f"http://127.0.0.1:{server}{path}", dest)
    assert dest.read_bytes() == _ROUTES[path][0]


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b"\xff\xd8\xff\xdb", "JPEG"),
        (_PNG_HEAD, "PNG"),
        (b"II*\x00\x08\x00", "TIFF"),
        (b"MM\x00*\x00\x00", "TIFF"),
        (b"II+\x00\x08\x00", "BigTIFF"),
        (b"\x00\x00\x00\x0cjP  \r\n\x87\n", "JPEG 2000"),
        (b"\xff\x4f\xff\x51\x00\x2f", "JPEG 2000"),
        (b"GIF89a\x01\x00", "GIF"),
        (b"RIFF\x24\x00\x00\x00WEBPVP8 ", "WebP"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", None),  # RIFF non WebP
        (b"{\"@context\": ", None),
        (b"<!DOCTYPE html>", None),
        (b"", None),
    ],
)
def test_image_format_signatures(head: bytes, expected: str | None) -> None:
    assert image_format(head) == expected
