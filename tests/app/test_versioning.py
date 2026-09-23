"""``code_version`` ne doit pas dépendre de l'endroit d'où on lance.

Elle entre dans la **clé de reprise** et dans le ``RunManifest`` : deux valeurs
pour un même code, c'est un cache manqué sans raison et un manifeste qui
contredit l'invariant de reproductibilité (``CLAUDE.md`` §12).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cinoc.app.versioning import _est_installee, resolve_code_version
from cinoc.domain._version_fallback import FALLBACK_VERSION


class _Fausse:
    """Tient lieu de ``Distribution`` : seuls ``version`` et ``RECORD`` comptent."""

    def __init__(self, version: str, *, record: str | None) -> None:
        self.version = version
        self._record = record

    def read_text(self, nom: str) -> str | None:
        return self._record if nom == "RECORD" else None


def test_un_egg_info_de_copie_de_travail_n_est_pas_une_installation() -> None:
    """C'est tout le discriminant : la PEP 376 impose ``RECORD`` à une
    installation, un artefact de build n'en a pas."""
    assert not _est_installee(_Fausse("9.9.9", record=None))
    assert _est_installee(_Fausse("1.0.0", record="cinoc/__init__.py,,"))


def test_l_installation_l_emporte_sur_l_artefact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L'ordre de ``sys.path`` ne doit plus décider de la version.

    Ici l'artefact est rendu **en premier** — le cas réel, puisque le script
    console pose le répertoire courant en tête de ``sys.path``.
    """
    monkeypatch.setattr(
        "cinoc.app.versioning.distributions",
        lambda **_: iter(
            (
                _Fausse("9.9.9-artefact", record=None),
                _Fausse("1.2.3-installee", record="cinoc/__init__.py,,"),
            )
        ),
    )
    assert resolve_code_version() == "1.2.3-installee"


def test_sans_installation_l_artefact_sert_de_repli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un installeur qui omettrait ``RECORD`` doit rester utilisable : mieux
    vaut une version imparfaite que le fallback, qui affirmerait à tort que le
    paquet n'est pas installé."""
    monkeypatch.setattr(
        "cinoc.app.versioning.distributions",
        lambda **_: iter((_Fausse("9.9.9-artefact", record=None),)),
    )
    assert resolve_code_version() == "9.9.9-artefact"


def test_la_version_ne_bouge_pas_selon_le_repertoire(tmp_path: Path) -> None:
    avant = Path.cwd()
    depuis_racine = resolve_code_version()
    try:
        os.chdir(tmp_path)
        depuis_ailleurs = resolve_code_version()
    finally:
        os.chdir(avant)
    assert depuis_racine == depuis_ailleurs


def test_metadonnee_locale_ignoree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une métadonnée de copie de travail ne doit rien changer, où qu'elle soit
    dans ``sys.path`` — y compris quand elle n'est **pas** le répertoire
    courant, ce que sait faire ``pytest`` en y ajoutant la racine du dépôt.
    """
    piege = tmp_path / "cinoc.egg-info"
    piege.mkdir()
    (piege / "PKG-INFO").write_text(
        "Metadata-Version: 2.1\nName: cinoc\nVersion: 9.9.9-piege\n",
        encoding="utf-8",
    )
    attendu = resolve_code_version()
    monkeypatch.syspath_prepend(str(tmp_path))
    obtenu = resolve_code_version()
    assert obtenu == attendu
    assert "piege" not in obtenu


def test_sans_paquet_installe_le_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucune métadonnée trouvable → ``FALLBACK_VERSION``, qui dit précisément
    « paquet non installé » — pas la version d'un artefact périmé."""
    monkeypatch.setattr(
        "cinoc.app.versioning.distributions", lambda **_: iter(())
    )
    assert resolve_code_version() == FALLBACK_VERSION

