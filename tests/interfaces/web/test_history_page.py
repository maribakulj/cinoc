"""Page « Historique » (S6) : rendu serveur, aucun JS — entièrement testable."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from cinoc.adapters.storage.history_store import HistoryRecord, HistoryStore
from cinoc.interfaces.web.app import _TEMPLATES_DIR, create_app
from cinoc.interfaces.web.routers.home import build_home_router


def _rec(run_id: str, when: str, value: float) -> HistoryRecord:
    return HistoryRecord(
        run_id=run_id,
        completed_at=when,
        corpus_name="corpusA",
        code_version="0.1.0",
        pipeline="tesseract",
        view="text",
        metric="cer",
        value=value,
    )


def _seeded_client(tmp_path: Path) -> TestClient:
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("run-old", "2026-01-01T00:00:00+00:00", 0.10),
            _rec("run-new", "2026-02-01T00:00:00+00:00", 0.15),
        ]
    )
    templates = Jinja2Templates(directory=_TEMPLATES_DIR)
    app = FastAPI()
    app.include_router(
        build_home_router(
            tmp_path / "reports",
            templates,
            statuses=lambda: (),
            segmenters=lambda: (),
            third_party=lambda: (),
            history_store=store,
        )
    )
    return TestClient(app)


def test_history_page_lists_log_newest_first(tmp_path: Path) -> None:
    body = _seeded_client(tmp_path).get("/history").text
    assert "run-new" in body and "run-old" in body
    assert "0.1500" in body and "0.1000" in body
    # le plus récent apparaît avant l'ancien (tri DESC)
    assert body.index("run-new") < body.index("run-old")


def test_history_page_reports_regression(tmp_path: Path) -> None:
    body = _seeded_client(tmp_path).get("/history").text
    assert "Régressions" in body
    # 0.10 → 0.15 dégradation (delta +0.05) affichée
    assert "0.1000 → 0.1500" in body
    assert "+0.0500" in body


def test_history_page_server_rendered_active_nav(tmp_path: Path) -> None:
    body = _seeded_client(tmp_path).get("/history").text
    assert "<script" not in body  # 100 % rendu serveur
    assert 'aria-current="page"' in body  # onglet Historique actif


def test_history_page_english(tmp_path: Path) -> None:
    body = _seeded_client(tmp_path).get("/history?lang=en").text
    assert "History" in body and "Regressions" in body


def test_history_empty_via_create_app(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            reports_dir=tmp_path / "r",
            uploads_dir=tmp_path / "u",
            rate_limit=1000,
        )
    )
    resp = client.get("/history")
    assert resp.status_code == 200
    assert "Aucun run" in resp.text  # état vide


def test_history_is_live_nav_link_from_home(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            reports_dir=tmp_path / "r",
            uploads_dir=tmp_path / "u",
            rate_limit=1000,
        )
    )
    assert 'href="/history?lang=fr"' in client.get("/").text
