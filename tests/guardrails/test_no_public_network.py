"""Le garde-fou réseau de ``tests/conftest.py`` mord (D-303).

Chaque cas est joué dans un pytest **séparé** qui charge ce même conftest :
c'est la seule façon de voir le démontage échouer sans faire échouer ce
fichier-ci.
"""

from __future__ import annotations

import shutil
import socket
from pathlib import Path

import pytest

pytest_plugins = ("pytester",)

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"


def _run(pytester: pytest.Pytester, body: str) -> pytest.RunResult:
    shutil.copy(CONFTEST, pytester.path / "conftest.py")
    pytester.makepyfile(test_inner=body)
    with pytest.MonkeyPatch.context() as mp:
        # pytester lit la sortie de l'enfant en UTF-8 : un PYTHONIOENCODING
        # hérité (cp1252, job Windows) la rendrait illisible.
        mp.setenv("PYTHONIOENCODING", "utf-8")
        return pytester.runpytest_subprocess("-p", "no:cacheprovider", "-q")


def test_a_public_api_is_refused_with_a_clear_message(
    pytester: pytest.Pytester,
) -> None:
    """Rouge : un appel à ``api.mistral.ai`` échoue, et dit quoi faire."""
    result = _run(
        pytester,
        """
import httpx

def test_calls_mistral():
    httpx.get("https://api.mistral.ai/v1/models", timeout=2)
""",
    )
    result.assert_outcomes(failed=1, errors=1)
    result.stdout.fnmatch_lines(
        [
            "*réseau public refusé dans un test : résolution de 'api.mistral.ai'*"
            "marquez le test network ou live*",
        ]
    )


def test_a_swallowed_refusal_still_fails_the_test(pytester: pytest.Pytester) -> None:
    """Un code qui avale l'``OSError`` (reprise, repli hors ligne) ne cache pas
    la tentative : le test échoue à son démontage."""
    result = _run(
        pytester,
        """
import socket

def test_swallows():
    try:
        socket.create_connection(("93.184.215.14", 443), timeout=1)
    except OSError:
        pass
""",
    )
    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(
        ["*réseau public tenté hors marqueur network/live*93.184.215.14*"]
    )


def test_loopback_unix_sockets_and_markers_pass(pytester: pytest.Pytester) -> None:
    """Boucle locale (IPv4, ``localhost``), socket Unix : permis. Un test marqué
    ``network``/``live`` ne voit pas le garde-fou ; un test ordinaire ne voit
    aucun mandataire (un mandataire local porterait une requête publique)."""
    result = _run(
        pytester,
        """
import os, socket
import pytest

def _serve(family, address):
    server = socket.socket(family, socket.SOCK_STREAM)
    server.bind(address)
    server.listen(1)
    return server

def test_loopback(monkeypatch):
    server = _serve(socket.AF_INET, ("127.0.0.1", 0))
    port = server.getsockname()[1]
    socket.create_connection(("127.0.0.1", port), timeout=1).close()
    socket.create_connection(("localhost", port), timeout=1).close()
    server.close()

@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="pas de socket Unix")
def test_unix():
    path = "s"  # relatif : un chemin absolu de tmp_path dépasse 108 octets
    server = _serve(socket.AF_UNIX, path)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(path)
    client.close()
    server.close()

def test_no_proxy():
    assert not any(
        os.environ.get(v) for v in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY")
    )

@pytest.mark.network
def test_network_marker_unguarded():
    assert "<locals>" not in socket.socket.connect.__qualname__

@pytest.mark.live
def test_live_marker_unguarded():
    assert "<locals>" not in socket.getaddrinfo.__qualname__
""",
    )
    outcomes = result.parseoutcomes()
    assert outcomes.get("passed", 0) + outcomes.get("skipped", 0) == 5, outcomes
    assert "failed" not in outcomes and "errors" not in outcomes, outcomes


def test_guard_is_active_in_this_suite() -> None:
    """Le conftest est bien chargé par la suite elle-même (sans rien tenter :
    une tentative ferait échouer ce test à son démontage)."""
    patched_all = (socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex)
    for patched in patched_all:
        assert patched.__qualname__.startswith("_no_public_network.<locals>.")
