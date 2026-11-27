"""Ce que PyPI montrera du paquet pointe vers quelque chose qui existe (D-309).

La page d'un paquet sur PyPI est faite de deux choses : les métadonnées de
``pyproject.toml`` (adresses, classificateurs) et le README rendu. Aucune des
deux n'est relue par ``twine check``, qui ne vérifie que la syntaxe : une
adresse vers un fichier renommé, ou un lien relatif du README — que PyPI
résout contre sa propre page, donc vers rien —, y passent vert. Ces contrôles
lisent l'arbre : chaque adresse du dépôt nomme un fichier présent, chaque
ancre un titre présent, et les versions de Python annoncées sont celles que la
CI essaie.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/maribakulj/cinoc"
BLOB = f"{REPO}/blob/main/"
RAW = "https://raw.githubusercontent.com/maribakulj/cinoc/main/"

_PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
]


def _anchors(markdown: Path) -> set[str]:
    """Les ancres que GitHub fabrique pour les titres d'un fichier Markdown."""
    anchors: set[str] = set()
    in_fence = False
    for line in markdown.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        heading = re.match(r"#{1,6}\s+(.*)", line)
        if heading and not in_fence:
            slug = re.sub(r"[^\w\- ]", "", heading.group(1).strip().lower())
            anchors.add(slug.replace(" ", "-"))
    return anchors


def _check_repo_target(url: str) -> None:
    """Une adresse du dépôt nomme un fichier de l'arbre (et une ancre réelle)."""
    for base in (BLOB, RAW):
        if url.startswith(base):
            path, _, anchor = url[len(base) :].partition("#")
            target = ROOT / path
            assert target.is_file(), f"{url} : {path} n'existe pas dans l'arbre"
            if anchor:
                assert anchor in _anchors(target), f"{url} : ancre « {anchor} » absente"
            return
    assert url in (REPO, f"{REPO}/issues"), f"adresse du dépôt inattendue : {url}"


@pytest.mark.parametrize("name", sorted(_PROJECT["urls"]))
def test_each_project_url_points_into_the_repository(name: str) -> None:
    url = _PROJECT["urls"][name]
    assert url.startswith(REPO), (
        f"[project.urls] {name} = {url} : seules les adresses du dépôt sont "
        "écrites tant que PyPI, le Space et le DOI ne sont pas publiés"
    )
    _check_repo_target(url)


def _readme_targets() -> list[str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    markdown = re.findall(r"\]\(([^)\s]+)\)", readme)
    html = re.findall(r"""(?:href|src)=["']([^"']+)["']""", readme)
    return markdown + html


def test_the_readme_has_no_relative_link_pypi_would_break() -> None:
    relatifs = [t for t in _readme_targets() if not re.match(r"https?://|#|mailto:", t)]
    assert not relatifs, (
        f"liens relatifs dans le README : {relatifs}. PyPI les résout contre sa "
        f"propre page ; écrire {BLOB}<chemin> (fichier) ou {RAW}<chemin> (image)."
    )


def test_each_readme_link_into_the_repository_exists() -> None:
    cibles = [t for t in _readme_targets() if t.startswith((BLOB, RAW))]
    assert cibles, "le README ne pointe plus vers aucun fichier du dépôt ?"
    for url in cibles:
        _check_repo_target(url)


def test_the_python_classifiers_are_the_versions_the_ci_runs() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    matrice = re.search(r"python:\s*\[([^\]]*)\]", ci)
    assert matrice, "matrice Python du job `test` introuvable"
    essayees = re.findall(r"\d+\.\d+", matrice.group(1))
    annoncees = [
        c.rsplit(" :: ", 1)[1]
        for c in _PROJECT["classifiers"]
        if re.fullmatch(r"Programming Language :: Python :: \d+\.\d+", c)
    ]
    assert annoncees == essayees, (annoncees, essayees)
    assert _PROJECT["requires-python"] == f">={essayees[0]}"
