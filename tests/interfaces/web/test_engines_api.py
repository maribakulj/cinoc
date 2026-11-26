"""Aide au composeur côté HTTP : aperçu de normalisation + modèles (live).

Les listes de lecture (état des moteurs, profils de métriques/normalisation) sont
rendues côté serveur et leur logique est couverte par ``tests/app/test_engines``
+ ``test_run_planning`` — pas d'API JSON dédiée.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app


def _client(tmp_path: Path, *, public_mode: bool = False) -> TestClient:
    return TestClient(
        create_app(reports_dir=tmp_path, rate_limit=1000, public_mode=public_mode)
    )


def test_models_endpoint_asks_the_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La route sert ``available_models`` — la fonction de ``cinoc list models``,
    en direct —, sans cible réglable par le client."""
    from cinoc.app.models import ModelInfo, ModelListing

    asked: list[tuple[str, object]] = []

    def fake(provider: str, settings: object = None, **_: object) -> ModelListing:
        asked.append((provider, settings))
        return ModelListing(
            provider=provider,
            models=(ModelInfo(name="qwen-test:3b", vision=True, digest="ab" * 32),),
        )

    monkeypatch.setattr("cinoc.interfaces.web.routers.engines.available_models", fake)
    body = _client(tmp_path).get("/api/models/ollama?host=http://evil").json()
    assert asked == [("ollama", None)]
    assert body["unavailable"] is None
    (model,) = body["models"]
    assert (model["name"], model["vision"]) == ("qwen-test:3b", True)


def test_a_public_instance_asks_no_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un visiteur anonyme ne fait pas interroger la clé ni le serveur Ollama de
    l'opérateur : aucun de ces moteurs n'est exécutable en mode public."""

    def interdit(*_a: object, **_k: object) -> object:
        raise AssertionError("fournisseur interrogé en mode public")

    monkeypatch.setattr(
        "cinoc.interfaces.web.routers.engines.available_models", interdit
    )
    body = _client(tmp_path, public_mode=True).get("/api/models/ollama").json()
    assert body["models"] == [] and "mode public" in body["unavailable"]


def test_models_endpoint_unknown_provider_says_why(tmp_path: Path) -> None:
    body = _client(tmp_path).get("/api/models/bogus").json()
    assert body["provider"] == "bogus" and body["models"] == []
    assert "fournisseur sans liste" in body["unavailable"]  # champ libre, pas 500


def test_normalization_preview_named_and_custom(tmp_path: Path) -> None:
    from cinoc.interfaces.web.security.csrf import CSRF_HEADER

    client = _client(tmp_path)
    headers = {CSRF_HEADER: "1"}
    # profil nommé : caseless → minuscules.
    r = client.post(
        "/api/normalization/preview",
        headers=headers,
        json={"sample": "NOSTRE", "profile": "caseless"},
    )
    assert r.status_code == 200 and r.json()["normalized"] == "nostre"
    # config YAML custom (sans persistance) : exclut « X ».
    r = client.post(
        "/api/normalization/preview",
        headers=headers,
        json={"sample": "aXb", "config": 'exclude_chars: "X"'},
    )
    assert r.json()["normalized"] == "ab"


def test_normalization_preview_invalid_config_is_422(tmp_path: Path) -> None:
    from cinoc.interfaces.web.security.csrf import CSRF_HEADER

    r = _client(tmp_path).post(
        "/api/normalization/preview",
        headers={CSRF_HEADER: "1"},
        json={"sample": "x", "config": "bogus_key: 1"},
    )
    assert r.status_code == 422


def test_normalization_preview_requires_csrf(tmp_path: Path) -> None:
    r = _client(tmp_path).post(
        "/api/normalization/preview", json={"sample": "x", "profile": "nfc"}
    )
    assert r.status_code == 403
