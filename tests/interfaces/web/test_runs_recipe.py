"""Le catalogue de recettes branché à la file : de la page au rapport.

La page lit ``GET /api/recipes``, empile des recettes dans la file et les lance
par ``POST /api/runs`` en **un** run comparé. Ce fichier tient le chemin
côté serveur de bout en bout : une file de deux recettes sur un corpus déposé
produit un rapport servable. Le navigateur, lui, n'est pas testé en CI (le dépôt
n'en a pas) ; il a été vérifié à la main, capture à l'appui (D-296).
"""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER

_CSRF = {CSRF_HEADER: "1"}
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _client(tmp_path: Path, *, public_mode: bool = False) -> TestClient:
    return TestClient(
        create_app(reports_dir=tmp_path, rate_limit=1000, public_mode=public_mode)
    )


def _corpus(client: TestClient) -> str:
    """Deux pages, leur vérité terrain, et les lectures « pré-calculées » que la
    brique ``precomputed`` rejoue sous le nom de l'étape (``<doc>.<étape>.txt``)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        pages = (("p1", "le soleil", "le so1eil"), ("p2", "la lune", "la lune"))
        for doc, gt, lu in pages:
            zf.writestr(f"{doc}.png", _PNG)
            zf.writestr(f"{doc}.gt.txt", gt)
            for etape in ("ocr", "ocr_a", "ocr_b", "ocr_c"):
                zf.writestr(f"{doc}.{etape}.txt", lu)
    reponse = client.post(
        "/api/corpus",
        files={"file": ("c.zip", buf.getvalue(), "application/zip")},
        headers=_CSRF,
    )
    assert reponse.status_code == 201, reponse.json()
    return str(reponse.json()["corpus_id"])


def _attendre(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    limite = time.time() + timeout
    while time.time() < limite:
        corps = client.get(f"/api/runs/{job_id}").json()
        if corps["state"] in {"done", "failed", "cancelled"}:
            return dict(corps)
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} non terminé dans le délai")


def _tout_disponible(monkeypatch: pytest.MonkeyPatch) -> None:
    from cinoc.app import engines

    monkeypatch.setattr(
        "cinoc.interfaces.web.app.engine_statuses",
        lambda: engines.engine_statuses(
            has_binary=lambda _: "/bin/x", has_module=lambda _: True
        ),
    )


def test_a_queue_of_recipes_runs_to_a_report(tmp_path: Path) -> None:
    """Le chemin de la page, côté serveur : deux recettes dans la file, un run,
    deux pipelines dans le même rapport."""
    client = _client(tmp_path)
    corpus_id = _corpus(client)
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={
            "corpus_id": corpus_id,
            "entries": [
                {"recipe": "ocr_simple", "choices": {"ocr": "precomputed"}},
                {
                    "recipe": "vote_trois_moteurs",
                    "choices": {
                        "ocr_a": "precomputed",
                        "ocr_b": "precomputed",
                        "ocr_c": "precomputed",
                    },
                },
            ],
        },
    )
    assert reponse.status_code == 201, reponse.json()
    job = _attendre(client, reponse.json()["job_id"])
    assert job["state"] == "done", job.get("error")
    page = client.get(f"/reports/{job['report_name']}")
    assert page.status_code == 200
    assert "ocr_simple" in page.text and "vote_trois_moteurs" in page.text


def test_the_page_loads_the_recipe_script(tmp_path: Path) -> None:
    """La troisième clause (``FRONT``) déclare que la page appelle les routes de
    recettes : la page doit au moins charger le script qui le fait."""
    page = _client(tmp_path).get("/benchmark")
    assert '<script src="/static/js/recipes.js"></script>' in page.text
    assert 'id="recipe-picker"' in page.text
    script = _client(tmp_path).get("/static/js/recipes.js")
    assert script.status_code == 200
    assert "/api/recipes" in script.text


def test_the_catalogue_says_which_bricks_can_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La page grise une brique indisponible : c'est le serveur qui le sait."""
    from cinoc.app import engines

    monkeypatch.setattr(
        "cinoc.interfaces.web.app.engine_statuses",
        lambda: engines.engine_statuses(
            has_binary=lambda _: "/bin/x",
            has_module=lambda nom: nom != "kraken",
        ),
    )
    recettes = _client(tmp_path).get("/api/recipes?lang=en").json()["recipes"]
    simple = next(r for r in recettes if r["name"] == "ocr_simple")
    briques = {b["kind"]: b for b in simple["steps"][0]["bricks"]}
    assert briques["tesseract"]["available"] is True
    assert briques["kraken"]["available"] is False


def test_a_recipe_whose_brick_misses_a_required_setting_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kraken sans modèle : refusé avant le lancement, le réglage nommé."""
    _tout_disponible(monkeypatch)
    client = _client(tmp_path)
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={
            "corpus_id": _corpus(client),
            "entries": [{"recipe": "ocr_simple", "choices": {"ocr": "kraken"}}],
        },
    )
    assert reponse.status_code == 422
    assert "model" in reponse.json()["detail"]


def test_an_empty_queue_is_refused(tmp_path: Path) -> None:
    client = _client(tmp_path)
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={"corpus_id": _corpus(client), "entries": []},
    )
    assert reponse.status_code == 422


def test_the_composer_names_a_setting_its_brick_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``POST /api/runs`` : une entrée dont la brique ne se construit pas
    (Kraken sans modèle) était **lancée**, et le job échouait (D-296). Refusée
    avant le lancement, en 422, le réglage nommé — la règle de
    ``cinoc run --check`` et de la spec déposée."""
    _tout_disponible(monkeypatch)
    client = _client(tmp_path)
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={
            "corpus_id": _corpus(client),
            "entries": [{"recipe": "ocr_simple", "choices": {"ocr": "kraken"}}],
        },
    )
    assert reponse.status_code == 422, reponse.json()
    assert "model" in reponse.json()["detail"]
