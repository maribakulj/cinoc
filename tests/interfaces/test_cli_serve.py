"""CLI ``serve`` : câblage uvicorn (factory) + garde-fous, sans lancer le serveur."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from cinoc.interfaces.cli import main


class _FakeUvicorn(ModuleType):
    """Faux module ``uvicorn`` capturant l'appel ``run`` (jamais de vrai serveur)."""

    def __init__(self) -> None:
        super().__init__("uvicorn")
        self.calls: list[dict[str, Any]] = []

    def run(self, app: str, **kwargs: Any) -> None:
        self.calls.append({"app": app, **kwargs})


@pytest.fixture
def fake_uvicorn(monkeypatch: pytest.MonkeyPatch) -> _FakeUvicorn:
    fake = _FakeUvicorn()
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    return fake


def test_serve_passes_factory_to_uvicorn(fake_uvicorn: _FakeUvicorn) -> None:
    code = main(["serve", "--host", "127.0.0.1", "--port", "9123"])
    assert code == 0
    (call,) = fake_uvicorn.calls
    # On passe la FACTORY (chemin importable + factory=True), jamais un app de module.
    assert call["app"] == "cinoc.interfaces.web.app:create_app"
    assert call["factory"] is True
    assert call["host"] == "127.0.0.1"
    assert call["port"] == 9123


def test_serve_warns_on_public_host(
    fake_uvicorn: _FakeUvicorn, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["serve", "--host", "0.0.0.0"])
    assert code == 0
    assert "exposé au réseau" in capsys.readouterr().err


def test_serve_local_host_does_not_warn(
    fake_uvicorn: _FakeUvicorn, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["serve"])  # défaut 127.0.0.1
    assert "exposé au réseau" not in capsys.readouterr().err


def test_serve_sets_reports_dir_env(
    fake_uvicorn: _FakeUvicorn, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CINOC_REPORTS_DIR", raising=False)
    main(["serve", "--reports-dir", "/data/reports"])
    import os

    assert os.environ["CINOC_REPORTS_DIR"] == "/data/reports"


def test_serve_without_extra_reports_cleanly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # uvicorn absent → message clair + code 1, pas de trace.
    monkeypatch.setitem(sys.modules, "uvicorn", None)  # force ImportError
    code = main(["serve"])
    assert code == 1
    assert "cinoc[serve]" in capsys.readouterr().err


def test_serve_says_where_its_data_lives(
    fake_uvicorn: _FakeUvicorn, capsys: pytest.CaptureFixture[str]
) -> None:
    # Le testeur a perdu son corpus au redémarrage sans qu'aucun message ne
    # dise où vivaient les données (D-307) : le démarrage le dit.
    from cinoc.app.data_dir import user_data_dir

    main(["serve"])
    sortie = capsys.readouterr().out
    assert str(user_data_dir()) in sortie
    assert "CINOC_DATA_DIR" in sortie


def test_serve_in_public_mode_says_its_data_is_temporary(
    fake_uvicorn: _FakeUvicorn,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CINOC_PUBLIC_MODE", "true")
    main(["serve"])
    assert "temporaire" in capsys.readouterr().out
