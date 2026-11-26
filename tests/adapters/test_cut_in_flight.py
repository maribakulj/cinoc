"""Un arrêt coupe l'appel **en vol**, chez les SDK cloud comme en HTTPS (S29a).

S28a coupait le socket d'Ollama (``cut_on_cancel``, D-300) ; les SDK cloud
restaient sous ``close()`` d'un autre fil, qui ne réveille pas une lecture
bloquante : contre un serveur muet de 10 s, OpenAI 3.x, Anthropic 2.x et
Mistral 3.x rendaient la main à 10 s. Leur client HTTP (``httpx2``) reçoit
désormais un crochet ``request`` qui pose la trace sur chaque requête
(``cut_on_cancel_hooks``). Et la trace gardait le socket **TCP**, que TLS
détache : contre un serveur HTTPS, rien n'était coupé — or toute API cloud est
en HTTPS.

Les tests des SDK ne tournent que là où ils sont installés (job CI ``sdks``) ;
ceux de la trace, partout (``httpx`` de base, ``cryptography`` pour TLS).
"""

from __future__ import annotations

import datetime
import functools
import ipaddress
import ssl
import sys
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest

from cinoc.adapters._resilience import cut_on_cancel, cut_on_cancel_hooks
from cinoc.adapters.llm._base import InferenceSettings
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import RunCancelledError
from cinoc.pipeline.run_control import RunControl

#: Le serveur se tait 10 s ; l'arrêt tombe à 0,5 s ; la main doit revenir en 2 s.
_MUTE = 10.0
_STOP_AT = 0.5
_BOUND = 2.0


class _Mute(BaseHTTPRequestHandler):
    """Lit la requête, se tait, puis répond 500 (jamais atteint si coupé)."""

    release: threading.Event

    def do_POST(self) -> None:  # noqa: N802 — API de http.server
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.release.wait(_MUTE)
        try:
            self.send_response(500)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
        except OSError:
            return

    def log_message(self, *_: object) -> None: ...


def _serve(wrap: Callable[[Any], Any] | None = None) -> Iterator[str]:
    handler = type("Handler", (_Mute,), {"release": threading.Event()})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    if wrap is not None:
        httpd.socket = wrap(httpd.socket)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    scheme = "https" if wrap is not None else "http"
    yield f"{scheme}://127.0.0.1:{httpd.server_address[1]}"
    handler.release.set()
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def mute() -> Iterator[str]:
    yield from _serve()


@pytest.fixture
def mute_tls(tmp_path: Path) -> Iterator[tuple[str, str]]:
    """Serveur HTTPS muet, certificat auto-signé pour ``127.0.0.1``."""
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    server_ctx.load_cert_chain(cert_path, key_path)
    for url in _serve(lambda sock: server_ctx.wrap_socket(sock, server_side=True)):
        yield url, str(cert_path)


def _linux_only(request: pytest.FixtureRequest) -> None:
    """Qu'un ``shutdown`` d'un autre fil réveille un ``recv`` bloqué n'est
    mesuré que sous Linux (D-300, point ouvert) : non strict ailleurs."""
    if sys.platform == "win32":
        request.applymarker(pytest.mark.xfail(strict=False))


def _stopped_within(
    call: Callable[[RunControl], object],
    raises: type[BaseException] = RunCancelledError,
) -> float:
    """Durée entre le lancement et l'échec de ``call``, arrêté à ``_STOP_AT``."""
    control = RunControl()
    threading.Timer(_STOP_AT, control.trigger_cancel).start()
    started = time.monotonic()
    with pytest.raises(raises):
        call(control)
    return time.monotonic() - started


def test_the_hooks_pose_the_trace_on_every_request(
    mute: str, request: pytest.FixtureRequest
) -> None:
    """Le crochet ``request`` d'un client qu'on ne sollicite pas soi-même."""
    _linux_only(request)

    def call(control: RunControl) -> None:
        with httpx.Client(event_hooks=cut_on_cancel_hooks(control)) as client:
            client.post(f"{mute}/x", content=b"x")

    assert _stopped_within(call, httpx.TransportError) < _BOUND


def test_the_cut_reaches_a_tls_socket(
    mute_tls: tuple[str, str], request: pytest.FixtureRequest
) -> None:
    """Rouge avant S29a : la trace gardait le socket TCP, que l'enveloppe TLS
    détache — rendu à 10 s au lieu de 0,5."""
    _linux_only(request)
    url, cafile = mute_tls

    def call(control: RunControl) -> None:
        verify = ssl.create_default_context(cafile=cafile)
        with httpx.Client(verify=verify, timeout=30) as client:
            client.post(f"{url}/x", content=b"x",
                        extensions={"trace": cut_on_cancel(control)})

    assert _stopped_within(call, httpx.TransportError) < _BOUND


# -- les trois SDK, vrais ---------------------------------------------------

_SETTINGS = InferenceSettings.build(
    temperature=0.0, top_p=None, seed=0, max_tokens=16
)


def _openai(server: str, control: RunControl, _: Path) -> object:
    from cinoc.adapters.llm.openai import _invoke_openai

    return _invoke_openai(
        model="m", prompt="p", deadline=Deadline.in_seconds(60),
        settings=_SETTINGS, base_url=f"{server}/v1", control=control,
        api_key_env=None,
    )


def _anthropic(server: str, control: RunControl, _: Path) -> object:
    from cinoc.adapters.llm.anthropic import _invoke_anthropic

    return _invoke_anthropic(
        model="m", prompt="p", deadline=Deadline.in_seconds(60),
        settings=_SETTINGS, base_url=server, control=control,
    )


def _mistral(server: str, control: RunControl, _: Path) -> object:
    from cinoc.adapters.llm.mistral import _invoke_mistral

    return _invoke_mistral(
        model="m", prompt="p", deadline=Deadline.in_seconds(60),
        settings=_SETTINGS, control=control,
    )


def _mistral_ocr(server: str, control: RunControl, tmp: Path) -> object:
    from cinoc.adapters.ocr.mistral_ocr import _invoke_mistral_ocr

    image = tmp / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    return _invoke_mistral_ocr(
        model="m", image_path=str(image), deadline=Deadline.in_seconds(60),
        control=control,
    )


def _azure_di(server: str, control: RunControl, tmp: Path) -> object:
    from cinoc.adapters.ocr.azure_di import _invoke_azure_di

    image = tmp / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    return _invoke_azure_di(
        endpoint=server, image_path=str(image), deadline=Deadline.in_seconds(60),
        key="k", control=control,
    )


def _google_vision(server: str, control: RunControl, tmp: Path) -> object:
    from cinoc.adapters.ocr.google_vision import _invoke_google_vision

    image = tmp / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    return _invoke_google_vision(
        image_path=str(image), deadline=Deadline.in_seconds(60), api_key="k",
        control=control,
    )


@pytest.mark.parametrize("invoke", [_azure_di, _google_vision],
                         ids=["azure_di", "google_vision"])
def test_a_stop_cuts_the_http_ocr_call_in_flight(
    invoke: Callable[[str, RunControl, Path], object],
    mute: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Azure et Google parlent ``httpx`` sans SDK : même crochet, même borne
    (avant S29a : ``close()`` d'un autre fil, rendu à la réponse)."""
    from cinoc.adapters.ocr import google_vision

    _linux_only(request)
    monkeypatch.setattr(google_vision, "_ENDPOINT", f"{mute}/v1/images:annotate")
    assert _stopped_within(lambda control: invoke(mute, control, tmp_path)) < _BOUND


@pytest.mark.parametrize(
    ("sdk", "invoke"),
    [
        ("openai", _openai),
        ("anthropic", _anthropic),
        ("mistralai.client", _mistral),
        ("mistralai.client", _mistral_ocr),
    ],
    ids=["openai", "anthropic", "mistral", "mistral_ocr"],
)
def test_a_stop_cuts_the_sdk_call_in_flight(
    sdk: str,
    invoke: Callable[[str, RunControl, Path], object],
    mute: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """« Arrêter » pendant l'appel → ``RunCancelledError`` en < 2 s ; rouge
    avant S29a (rendu à 10 s, à la réponse du serveur)."""
    module = pytest.importorskip(sdk)
    _linux_only(request)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    if sdk == "mistralai.client":  # l'endpoint de Mistral est fixe : redirigé ici
        monkeypatch.setattr(
            module, "Mistral", functools.partial(module.Mistral, server_url=mute)
        )
    assert _stopped_within(lambda control: invoke(mute, control, tmp_path)) < _BOUND
