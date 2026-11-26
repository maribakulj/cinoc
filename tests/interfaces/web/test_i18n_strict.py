"""Gabarits web : une clé absente lève, et chaque clé existe en FR et en EN.

**Le défaut fermé** (audit D-264, défaut 19) : ``{{ t.cle_mal_orthographiee }}``
rendait ``''`` en silence — un libellé manquant ne se voyait qu'à l'œil, et
dans une seule des deux langues. Les gabarits sont désormais rendus sous
``StrictUndefined`` (D-301), et ce fichier prouve la parité des dictionnaires.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jinja2 import UndefinedError

from cinoc.adapters.corpus.htr_united import HTRUnitedCatalogue
from cinoc.interfaces.web import i18n
from cinoc.interfaces.web.app import create_app

WEB = Path(i18n.__file__).resolve().parent
PAGES = ("/", "/benchmark", "/library", "/history", "/engines")


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            reports_dir=tmp_path / "reports",
            uploads_dir=tmp_path / "uploads",
            data_dir=tmp_path / "data",
        )
    )


class _NoHub:
    def search(self, *_: object, **__: object) -> tuple[()]:
        return ()


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_under_strict_undefined(
    tmp_path: Path, page: str, lang: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """StrictUndefined lève aussi sur un ``{% if absent %}`` : chaque page, dans
    chaque langue, doit donc rendre sans une variable manquante. Les catalogues
    de ``/library`` sont servis hors ligne : la page interrogeait HTR-United et
    Hugging Face en direct (relevé par le garde-fou réseau, D-303)."""
    monkeypatch.setattr(
        "cinoc.interfaces.web.routers.home.fetch_catalogue",
        HTRUnitedCatalogue.from_demo,
    )
    monkeypatch.setattr(
        "cinoc.interfaces.web.routers.home.HuggingFaceCatalogue", _NoHub
    )
    response = _client(tmp_path).get(page, params={"lang": lang})
    assert response.status_code == 200, response.text[:300]


def test_a_missing_key_raises_instead_of_rendering_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    amputee = {k: v for k, v in i18n._STRINGS["fr"].items() if k != "reports_title"}
    monkeypatch.setitem(i18n._STRINGS, "fr", amputee)
    with pytest.raises(UndefinedError, match="reports_title"):
        _client(tmp_path).get("/")


def test_fr_and_en_have_the_same_keys() -> None:
    fr, en = set(i18n._STRINGS["fr"]), set(i18n._STRINGS["en"])
    assert fr == en, f"FR seul : {sorted(fr - en)} ; EN seul : {sorted(en - fr)}"
    vides = [
        f"{lang}:{k}" for lang, table in i18n._STRINGS.items()
        for k, v in table.items() if not v.strip()
    ]
    assert not vides, f"libellés vides : {vides}"


def _sources() -> str:
    return "".join(
        p.read_text(encoding="utf-8")
        for pattern in ("templates/*.html", "**/*.py", "static/js/*.js")
        for p in WEB.glob(pattern)
        if p.name != "i18n.py"
    )


def test_every_key_used_by_a_template_exists() -> None:
    gabarits = "".join(
        p.read_text(encoding="utf-8") for p in (WEB / "templates").glob("*.html")
    )
    utilisees = set(re.findall(r"\bt\.([a-z_0-9]+)", gabarits))
    assert utilisees, "aucune clé lue : le motif ne voit plus les gabarits"
    absentes = sorted(utilisees - set(i18n._STRINGS["fr"]))
    assert not absentes, f"clés lues, absentes du dictionnaire : {absentes}"


def test_no_key_is_orphaned() -> None:
    """Une clé que rien ne lit est un libellé mort (``library_open``, relevé
    par l'audit). Les clés composées (``t[f"nav_{id}"]``) comptent par préfixe."""
    sources = _sources()
    prefixes = tuple(re.findall(r"""t\[f["']([a-z_0-9]+)\{""", sources))
    assert prefixes, "le préfixe de navigation n'est plus vu"
    orphelines = sorted(
        k
        for k in i18n._STRINGS["fr"]
        if not re.search(rf"\b{re.escape(k)}\b", sources) and not k.startswith(prefixes)
    )
    assert not orphelines, f"clés que rien ne lit : {orphelines}"
