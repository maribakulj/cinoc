"""Le dossier de données de ``cinoc serve`` survit au redémarrage (D-307).

Le défaut était un dossier temporaire **neuf à chaque lancement** : un testeur a
déposé un corpus, lancé un run depuis la page, arrêté puis relancé le serveur —
« Aucun corpus local », rapport disparu, sans qu'aucun message l'ait dit. Le
défaut est maintenant le dossier par utilisateur de la plate-forme ; le mode
public garde l'éphémère (un serveur exposé ne garde pas ce que des visiteurs y
déposent).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from cinoc.app import data_dir as module
from cinoc.app.data_dir import DATA_DIR_ENV, resolve_data_dir, user_data_dir


def test_the_default_survives_a_restart() -> None:
    premier = resolve_data_dir()
    second = resolve_data_dir()
    assert premier.path == second.path == user_data_dir()
    assert not premier.ephemeral


def test_tests_never_reach_the_real_user_folder(tmp_path: Path) -> None:
    # Le conftest isole chaque test : le vrai ``~/.local/share/cinoc`` n'est
    # jamais celui que la suite lit ou écrit.
    base = tmp_path.parent.parent
    assert base in user_data_dir().parents


def test_the_variable_still_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "ailleurs"))
    choisi = resolve_data_dir()
    assert choisi.path == tmp_path / "ailleurs"
    assert choisi.path.is_dir()
    assert not choisi.ephemeral


def test_the_argument_wins_over_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "env"))
    assert resolve_data_dir(tmp_path / "arg").path == tmp_path / "arg"


def test_public_mode_stays_ephemeral() -> None:
    choisi = resolve_data_dir(public=True)
    assert choisi.ephemeral
    assert choisi.path != user_data_dir()
    assert not user_data_dir().exists()


def test_an_unwritable_user_folder_falls_back_to_a_temporary_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    bloque = tmp_path / "fichier"
    bloque.write_text("pas un dossier", encoding="utf-8")
    monkeypatch.setattr(module, "user_data_dir", lambda: bloque / "cinoc")
    choisi = resolve_data_dir()
    assert choisi.ephemeral and choisi.path.is_dir()
    assert "dégradé" in caplog.text


#: Absolu sur l'OS qui exécute le test (``/x/data`` ne l'est pas sous Windows).
_ABS = os.path.abspath("/x/data")


@pytest.mark.parametrize(
    ("platform", "env", "attendu"),
    [
        ("linux", {"XDG_DATA_HOME": _ABS}, Path(_ABS) / "cinoc"),
        ("linux", {"XDG_DATA_HOME": ""}, Path("/h/.local/share/cinoc")),
        # Relatif : ignoré, comme le veut la spécification XDG.
        ("linux", {"XDG_DATA_HOME": "rel"}, Path("/h/.local/share/cinoc")),
        ("darwin", {}, Path("/h/Library/Application Support/cinoc")),
        ("win32", {"LOCALAPPDATA": "C:/Users/u/AppData/Local"},
         Path("C:/Users/u/AppData/Local/cinoc")),
        ("win32", {"LOCALAPPDATA": ""}, Path("/h/AppData/Local/cinoc")),
    ],
)
def test_each_platform_has_its_convention(
    platform: str,
    env: dict[str, str],
    attendu: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/h")))
    for nom, valeur in env.items():
        monkeypatch.setenv(nom, valeur)
    assert user_data_dir() == attendu
