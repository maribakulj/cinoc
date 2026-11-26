"""``validated_path`` : confine sous base ; rejette traversal / absolu / nul.

``check_model_host`` : l'hôte d'un serveur de modèles reçu d'un client (ollama
``host``, endpoint OpenAI-compatible ``base_url``) est confronté à la liste
blanche de l'opérateur (P5d 4, D-269 ; étendue au ``base_url`` en P5f 6, D-293).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from cinoc.app.security import (
    HostNotAllowedError,
    PathSecurityError,
    check_model_host,
    validated_path,
)


def test_relative_resolves_under_base(tmp_path: Path) -> None:
    assert validated_path("images/doc1.png", tmp_path) == (
        tmp_path / "images/doc1.png"
    ).resolve()


def test_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathSecurityError):
        validated_path("../../etc/passwd", tmp_path)


def test_absolute_outside_base_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathSecurityError):
        validated_path("/etc/passwd", tmp_path)


def test_absolute_inside_base_accepted(tmp_path: Path) -> None:
    inside = tmp_path / "a" / "b.txt"
    assert validated_path(str(inside), tmp_path) == inside.resolve()


@pytest.mark.parametrize("bad", ["", "   ", "a\x00b"])
def test_empty_or_null_rejected(bad: str, tmp_path: Path) -> None:
    with pytest.raises(PathSecurityError):
        validated_path(bad, tmp_path)


def test_must_exist(tmp_path: Path) -> None:
    with pytest.raises(PathSecurityError):
        validated_path("absent.txt", tmp_path, must_exist=True)
    (tmp_path / "here.txt").write_text("x", encoding="utf-8")
    assert validated_path("here.txt", tmp_path, must_exist=True) == (
        tmp_path / "here.txt"
    ).resolve()


# --- Hôte d'un serveur de modèles : liste blanche de l'opérateur ----------


def _env(value: str | None) -> Callable[[str], str | None]:
    return lambda name: value if name == "CINOC_MODEL_HOSTS" else None


@pytest.mark.parametrize(
    "host",
    [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "https://LOCALHOST",  # la casse d'un nom d'hôte ne compte pas
        "http://localhost:8080/sous/chemin",  # port et chemin restent libres
    ],
)
def test_by_default_only_the_machine_itself_is_allowed(host: str) -> None:
    check_model_host(host, get_env=_env(None))


@pytest.mark.parametrize(
    "host",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.7:11434",
        "http://[::1]:11434",  # hors du défaut tant que l'opérateur ne l'ajoute pas
        "http://localhost.evil.example:11434",  # préfixe ≠ nom exact
        "http://evil.example#@localhost",  # le fragment ne déguise pas l'hôte
    ],
)
def test_any_other_host_is_refused_by_default(host: str) -> None:
    with pytest.raises(HostNotAllowedError, match="liste blanche"):
        check_model_host(host, get_env=_env(None))


@pytest.mark.parametrize(
    "host", ["localhost:11434", "ftp://localhost", "http://", "file:///etc/passwd"]
)
def test_an_unreadable_host_is_refused(host: str) -> None:
    with pytest.raises(HostNotAllowedError, match="illisible"):
        check_model_host(host, get_env=_env(None))


def test_credentials_in_the_url_are_refused() -> None:
    with pytest.raises(HostNotAllowedError, match="identifiants"):
        check_model_host("http://user:pw@localhost:11434", get_env=_env(None))


def test_the_operator_list_replaces_the_default() -> None:
    env = _env(" gpu.lan , 192.168.1.20 ")
    check_model_host("http://GPU.lan:11434", get_env=env)
    check_model_host("http://192.168.1.20", get_env=env)
    with pytest.raises(HostNotAllowedError):
        check_model_host("http://localhost:11434", get_env=env)


def test_an_empty_operator_list_allows_nothing() -> None:
    with pytest.raises(HostNotAllowedError, match="vide"):
        check_model_host("http://localhost:11434", get_env=_env(""))


def test_an_openai_compatible_endpoint_is_checked_like_an_ollama_host() -> None:
    """Une seule liste pour les deux cibles (D-293) : un ``base_url`` vLLM n'a
    pas de seconde porte."""
    check_model_host("http://127.0.0.1:8000/v1", get_env=_env(None))
    with pytest.raises(HostNotAllowedError, match="CINOC_MODEL_HOSTS"):
        check_model_host("http://169.254.169.254/v1", get_env=_env(None))
