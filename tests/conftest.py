"""Aucun test ne joint le réseau public, sauf s'il le déclare (D-303).

Un test sous vrai SDK Mistral a joint ``api.mistral.ai`` avec une fausse clé
(réponse 401) : rien ne l'empêchait. Ce garde-fou, appliqué à **chaque** test,
refuse toute connexion qui ne vise pas la boucle locale (``127.0.0.0/8``,
``::1``, ``localhost``) ou un socket Unix, et toute résolution de nom public —
sauf pour un test marqué ``network`` ou ``live``, qui déclare ce qu'il fait.

Trois choses le rendent sûr plutôt qu'indicatif :

* les variables de mandataire (``HTTPS_PROXY``…) sont retirées : un mandataire
  local porterait sinon une requête publique par une connexion à
  ``127.0.0.1``, que la règle laisse passer ;
* le refus est noté avant d'être levé, et le test **échoue à son démontage**
  s'il y en a eu un : un code qui avale l'``OSError`` (une reprise, un repli
  « hors ligne ») ne le cache pas ;
* la résolution est refusée avant d'interroger le DNS : un nom public ne part
  même pas en requête.

Un sous-processus lancé par un test n'hérite que de l'environnement sans
mandataire, pas des correctifs de ``socket``.

Second garde-fou, même esprit (D-307) : ``cinoc serve`` garde ses données dans
un dossier **par utilisateur** (``~/.local/share/cinoc``…). Aucun test n'y
écrit — chaque test reçoit son propre dossier de plate-forme, vide, et
``CINOC_DATA_DIR`` hérité du shell est retiré.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
import sys
from collections.abc import Iterator
from typing import Any

import pytest

#: Marqueurs qui autorisent le réseau public (``pyproject.toml``, ``markers``).
NETWORK_MARKERS = ("network", "live")

_PROXY_VARIABLES = (
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
)

_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


class PublicNetworkRefused(ConnectionRefusedError):
    """Connexion ou résolution vers le réseau public, refusée hors marqueur."""


def _is_local_host(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    name = host.strip("[]").split("%", 1)[0].rstrip(".").lower()
    if not name or name in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _is_local_address(family: int, address: object) -> bool:
    if family == getattr(socket, "AF_UNIX", None):
        return True
    if isinstance(address, tuple) and address:
        return _is_local_host(address[0])
    return False


@pytest.fixture(autouse=True)
def _isolated_user_data(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Un dossier de données de plate-forme **par test**, jamais le vrai.

    Créé paresseusement (le chemin seulement : ``resolve_data_dir`` le crée s'il
    sert) — 3 700 tests ne paient pas 3 700 dossiers. ``setenv`` avant
    ``delenv`` : la valeur d'origine est notée et restaurée, même quand le test
    a lui-même écrit ``os.environ`` (``cinoc serve`` le fait).
    """
    racine = tmp_path_factory.getbasetemp() / "user-data" / hashlib.sha256(
        request.node.nodeid.encode("utf-8")
    ).hexdigest()[:16]
    for variable in ("XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.setenv(variable, str(racine))
    if sys.platform == "darwin":
        monkeypatch.setenv("HOME", str(racine))
    monkeypatch.setenv("CINOC_DATA_DIR", "")
    monkeypatch.delenv("CINOC_DATA_DIR")


@pytest.fixture(autouse=True)
def _no_public_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if any(request.node.get_closest_marker(m) for m in NETWORK_MARKERS):
        yield
        return
    for variable in _PROXY_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    refused: list[str] = []

    def refuse(target: str) -> PublicNetworkRefused:
        refused.append(target)
        return PublicNetworkRefused(
            f"réseau public refusé dans un test : {target} — "
            f"marquez le test {' ou '.join(NETWORK_MARKERS)} "
            "s'il doit le joindre, sinon servez-le en local (tests/conftest.py)"
        )

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def connect(self: socket.socket, address: Any) -> None:
        if not _is_local_address(self.family, address):
            raise refuse(f"connexion à {address!r}")
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        if not _is_local_address(self.family, address):
            raise refuse(f"connexion à {address!r}")
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host is not None and not _is_local_host(host):
            raise refuse(f"résolution de {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield
    if refused:
        pytest.fail(
            "réseau public tenté hors marqueur "
            f"{'/'.join(NETWORK_MARKERS)} : " + " ; ".join(dict.fromkeys(refused)),
            pytrace=False,
        )
