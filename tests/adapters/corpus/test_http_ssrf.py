"""Garde-fou anti-SSRF (sans réseau réel : IP littérales + résolveur mocké)."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpcore
import pytest

from cinoc.adapters.corpus import _http
from cinoc.adapters.corpus._http import SsrfError, assert_public_url, fetch_json


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.org/x",  # schéma non http(s)
        "file:///etc/passwd",  # schéma local
        "http://user:pw@93.184.216.34/x",  # userinfo
        "http://127.0.0.1/x",  # loopback v4
        "http://[::1]/x",  # loopback v6
        "http://10.0.0.5/x",  # privé
        "http://192.168.1.1/x",  # privé
        "http://169.254.169.254/latest",  # link-local (métadonnées cloud)
        "https://0.0.0.0/x",  # non spécifié
    ],
)
def test_rejects_non_public_targets(url: str) -> None:
    with pytest.raises(SsrfError):
        assert_public_url(url)


def test_accepts_public_ip_literal() -> None:
    # IP publique littérale : aucune résolution réseau, aucune exception
    assert_public_url("http://93.184.216.34/manifest.json")


def test_rejects_hostname_resolving_to_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simule un nom qui résout vers l'interne (forme classique de SSRF/rebinding).
    def fake_getaddrinfo(host: str, *a: object, **k: object) -> list:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))]

    monkeypatch.setattr(_http.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(SsrfError):
        assert_public_url("http://evil.test/x")


def test_assert_public_url_returns_validated_ips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Le validateur retourne les IP à épingler (résolues une seule fois).
    def fake_getaddrinfo(host: str, *a: object, **k: object) -> list:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 80))]

    monkeypatch.setattr(_http.socket, "getaddrinfo", fake_getaddrinfo)
    assert assert_public_url("http://example.test/x") == ("93.184.216.34",)


def test_fetch_json_guards_before_connecting() -> None:
    # La validation court-circuite tout I/O réseau pour une cible interdite.
    with pytest.raises(SsrfError):
        fetch_json("http://127.0.0.1/manifest.json")


@pytest.fixture
def json_server() -> Iterator[int]:
    """Serveur loopback qui répond ``{"ok": true}`` à tout GET."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def do_GET(self) -> None:
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
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


def test_connection_pins_validated_ip_not_rebind(
    json_server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anti-DNS-rebinding : la connexion vise l'IP **validée**, pas une 2ᵉ résolution.

    ``getaddrinfo`` est hostile : il renvoie une IP **publique** à la validation,
    puis du **loopback** ensuite (rebinding). Le fix résout une seule fois et
    épingle l'IP publique ; on prouve que le transport tente bien de se connecter
    à cette IP publique (et non à l'IP interne d'une seconde résolution).
    """
    public_ip = "93.184.216.34"
    resolves = {"n": 0}

    def hostile_getaddrinfo(host: str, *a: object, **k: object) -> list:
        resolves["n"] += 1
        # 1ʳᵉ résolution (validation) = publique ; rebind interne ensuite.
        addr = public_ip if resolves["n"] == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 80))]

    monkeypatch.setattr(_http.socket, "getaddrinfo", hostile_getaddrinfo)

    # Intercepte l'adresse réellement visée par le transport, puis redirige la
    # vraie connexion TCP vers le serveur loopback (connexion par IP littérale →
    # pas de résolution supplémentaire, donc le compteur reste à 1).
    targets: list[str] = []
    backend_socket = httpcore._backends.sync.socket  # type: ignore[attr-defined]

    def spy_create_connection(address: tuple[str, int], *a: object, **k: object):  # type: ignore[no-untyped-def]
        targets.append(address[0])
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", json_server))
        return sock

    monkeypatch.setattr(backend_socket, "create_connection", spy_create_connection)

    result = fetch_json("http://malicious.test/manifest.json")

    assert result == {"ok": True}
    # La connexion a visé l'IP publique validée, pas le loopback du rebind.
    assert targets == [public_ip]
    # Une seule résolution DNS : aucune fenêtre de rebinding.
    assert resolves["n"] == 1


def test_ip_literal_never_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une IP écrite dans l'URL ne passe pas par le résolveur.

    Sur un réseau IPv6-seul (DNS64), ``getaddrinfo`` répond à une IPv4 littérale
    par une adresse NAT64 synthétique. La résoudre revenait à refuser l'IP qu'on
    venait d'écrire noir sur blanc.
    """

    def boom(*a: object, **k: object) -> list:
        raise AssertionError("une IP littérale ne doit pas être résolue.")

    monkeypatch.setattr(_http.socket, "getaddrinfo", boom)
    assert assert_public_url("http://93.184.216.34/x") == ("93.184.216.34",)
    assert assert_public_url("http://[2600:9000::1]/x") == ("2600:9000::1",)
    with pytest.raises(SsrfError):
        assert_public_url("http://127.0.0.1/x")


@pytest.mark.parametrize(
    ("resolved", "accepted"),
    [
        ("64:ff9b::5db8:d822", True),  # NAT64 de 93.184.216.34 — publique
        ("64:ff9b::7f00:1", False),  # NAT64 de 127.0.0.1 — loopback traduit
        ("64:ff9b::a9fe:a9fe", False),  # NAT64 de 169.254.169.254 — métadonnées
        ("::ffff:93.184.216.34", True),  # IPv4-mapped publique
        ("::ffff:10.0.0.1", False),  # IPv4-mapped privée
    ],
)
def test_judges_embedded_ipv4_not_the_envelope(
    monkeypatch: pytest.MonkeyPatch, resolved: str, accepted: bool
) -> None:
    """NAT64 / IPv4-mapped : c'est l'IPv4 embarquée qui décide, pas l'enveloppe.

    Sans cela le filtre est faux dans les deux sens : il refuse tout un réseau
    IPv6-seul (``64:ff9b::`` tombe dans ``::/8``, « réservé »), et il laisserait
    passer une enveloppe qui traduit du loopback.
    """

    def fake_getaddrinfo(host: str, *a: object, **k: object) -> list:
        return [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", (resolved, 80, 0, 0))]

    monkeypatch.setattr(_http.socket, "getaddrinfo", fake_getaddrinfo)
    if accepted:
        assert assert_public_url("http://example.test/x") == (resolved,)
    else:
        with pytest.raises(SsrfError):
            assert_public_url("http://example.test/x")
