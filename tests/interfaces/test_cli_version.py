"""``cinoc --version`` : la version que le paquet installé estampille (P5d 5, D-270).

Sans elle, l'utilisateur qui rapporte un défaut ne pouvait dire quelle version
il lance qu'en ouvrant un ``RunManifest``. Elle lit la **même** fonction que la
provenance des runs : deux sources de version finiraient par se contredire.
"""

from __future__ import annotations

import pytest

from cinoc.app import resolve_code_version
from cinoc.interfaces.cli import main


def test_version_prints_the_code_version_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as sortie:
        main(["--version"])

    assert sortie.value.code == 0
    assert capsys.readouterr().out.strip() == f"cinoc {resolve_code_version()}"


def test_version_needs_no_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    """``--version`` répond seul : la sous-commande exigée ne le bloque pas."""
    with pytest.raises(SystemExit) as sortie:
        main(["--version", "demo"])

    assert sortie.value.code == 0
    assert capsys.readouterr().out.startswith("cinoc ")
