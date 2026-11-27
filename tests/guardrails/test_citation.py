"""``CITATION.cff`` dit la même chose que le paquet, et pas plus que le dépôt (D-309).

Le fichier est lu par GitHub (« Cite this repository ») et par Zenodo à la
publication. Trois dérives sont mécanisables : une structure que le format
refuse (le schéma CFF 1.2.0 exige ``cff-version``, ``message``, ``title``,
``authors``), des métadonnées qui divergent de ``pyproject.toml`` (licence,
mots-clés, dépôt), et une ``version`` écrite avant le tag — la version du paquet
vient du tag git (``setuptools_scm``), une version qu'aucun tag ne porte la
contredit. Le schéma complet est vérifié hors suite par ``cffconvert
--validate`` (D-309) : aucune dépendance de plus pour la CI.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/maribakulj/cinoc"


def _cff() -> dict[str, Any]:
    data = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _project() -> dict[str, Any]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project: dict[str, Any] = tomllib.loads(text)["project"]
    return project


def test_citation_has_the_keys_the_format_requires() -> None:
    cff = _cff()
    for key in ("cff-version", "message", "title", "authors"):
        assert cff.get(key), f"CITATION.cff : « {key} » requis par CFF 1.2.0"
    assert cff["cff-version"] == "1.2.0"
    assert cff["type"] == "software"
    for author in cff["authors"]:
        assert isinstance(author, dict) and (
            {"family-names", "name", "alias"} & author.keys()
        ), f"auteur sans nom ni alias : {author}"


def test_citation_says_what_the_package_says() -> None:
    cff, project = _cff(), _project()
    assert cff["title"].lower() == project["name"]
    assert cff["license"] == project["license"]
    assert cff["keywords"] == project["keywords"]
    assert cff["repository-code"] == REPO == project["urls"]["Source"]


def test_citation_carries_no_version_that_no_tag_carries() -> None:
    cff = _cff()
    if "version" not in cff:
        assert "date-released" not in cff, "une date de sortie sans version"
        return
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("pas de dépôt git : le tag ne peut pas être lu")
    tag = f"v{cff['version']}"
    if tag in _git("tag", "--list", tag).split():
        return
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        # Un clone superficiel (CI par défaut) ne porte pas les tags : leur
        # absence n'y prouve rien.
        pytest.skip(f"clone superficiel : le tag {tag} ne peut pas être lu")
    pytest.fail(
        f"CITATION.cff annonce la version {cff['version']} mais le tag {tag} "
        "n'existe pas : setuptools_scm calcule la version depuis le tag, "
        "l'écrire avant lui la contredit"
    )


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
