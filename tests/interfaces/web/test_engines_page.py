"""Page « Moteurs » (S2.2a) : rendu serveur, aucun JS — entièrement testable."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app


def _client(tmp_path: Path, *, public_mode: bool = False) -> TestClient:
    return TestClient(
        create_app(reports_dir=tmp_path, rate_limit=1000, public_mode=public_mode)
    )


def test_engines_page_lists_socle(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/engines")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    for label in ("Pré-calculé", "Tesseract", "OpenAI", "Ollama"):
        assert label in body


def test_engines_page_nav_active_and_no_script(tmp_path: Path) -> None:
    body = _client(tmp_path).get("/engines").text
    assert "<script" not in body  # 100 % rendu serveur, aucun JS


def test_engines_reachable_via_system_details_not_nav(tmp_path: Path) -> None:
    home = _client(tmp_path).get("/").text
    # Comme Picarones : « Moteurs » n'est pas une pastille de nav, mais est
    # accessible via le bouton « Système · détails → » du rail.
    assert 'class="system-trigger" href="/engines?lang=fr"' in home
    assert 'nav-item" href="/engines' not in home
    assert 'nav-item active" href="/engines' not in home


def test_cloud_engine_unavailable_without_key(tmp_path: Path) -> None:
    body = _client(tmp_path, public_mode=True).get("/engines").text
    # openai (cloud) apparaît indisponible faute de clé — plus de motif « mode
    # public » : la disponibilité ne dépend que du SDK + clé.
    assert "indisponible" in body


def test_engines_page_english(tmp_path: Path) -> None:
    body = _client(tmp_path).get("/engines?lang=en").text
    assert "Engines" in body
    assert "available" in body or "unavailable" in body


def test_engines_page_montre_les_modules_tiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parité avec ``cinoc list engines`` (D-224).

    Un module tiers installé était visible en ligne de commande et **invisible**
    dans le web : la même capacité, rendue par un seul des deux transports.
    """
    import cinoc.interfaces.web.app as web_app
    from cinoc.app.engines import EngineStatus

    faux = (
        EngineStatus(
            kind="mon_seg",
            label="paquet.module:build",
            available=True,
            detail="module tiers, prêt",
        ),
        EngineStatus(
            kind="casse",
            label="paquet.autre:build",
            available=False,
            detail="module tiers inutilisable : No module named 'torch'",
        ),
    )
    # Patcher **là où le nom est lu** : ``app.py`` l'importe directement, donc
    # remplacer l'attribut du module d'origine n'aurait aucun effet.
    monkeypatch.setattr(web_app, "third_party_statuses", lambda **_: faux)
    body = _client(tmp_path).get("/engines").text
    assert "mon_seg" in body
    assert "paquet.module:build" in body
    # La cause d'un module cassé se lit dans la page, pas seulement au journal.
    assert "No module named" in body and "torch" in body


def test_mode_public_ne_revele_aucun_module_tiers(tmp_path: Path) -> None:
    """Même règle fail-closed que la découverte : on ne dit pas à un visiteur
    quel code tourne sur le serveur."""
    body = _client(tmp_path, public_mode=True).get("/engines").text
    assert "Modules tiers" not in body
