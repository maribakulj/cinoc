"""Historique : sparklines CER (tendances) rendues **serveur** depuis le store."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from cinoc.adapters.storage.history_store import HistoryRecord, HistoryStore
from cinoc.interfaces.web.app import _TEMPLATES_DIR
from cinoc.interfaces.web.routers.home import build_home_router


def _history_body(tmp_path: Path, store: HistoryStore) -> str:
    app = FastAPI()
    app.include_router(
        build_home_router(
            tmp_path / "reports",
            Jinja2Templates(directory=_TEMPLATES_DIR),
            statuses=lambda: (),
            segmenters=lambda: (),
            third_party=lambda: (),
            history_store=store,
        )
    )
    return TestClient(app).get("/history").text


def _rec(run_id: str, ts: str, value: float) -> HistoryRecord:
    return HistoryRecord(
        run_id=run_id,
        completed_at=ts,
        corpus_name="c",
        code_version="1.0",
        pipeline="tesseract",
        view="text",
        metric="cer",
        value=value,
    )


def test_history_renders_cer_sparkline(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("r1", "2026-01-01T00:00:00", 0.30),
            _rec("r2", "2026-02-01T00:00:00", 0.20),
        ]
    )
    body = _history_body(tmp_path, store)
    assert "Tendances" in body  # section des tendances
    assert 'class="spark"' in body  # sparkline SVG rendue serveur
    assert "<polyline" in body  # 2 points → courbe
    assert "tesseract" in body


def test_history_no_sparkline_when_empty(tmp_path: Path) -> None:
    body = _history_body(tmp_path, HistoryStore(tmp_path / "h.db"))
    assert 'class="spark"' not in body  # aucune tendance sans donnée


def test_history_renders_slope_without_rupture_on_short_series(
    tmp_path: Path,
) -> None:
    # 2 runs : pente OLS affichée ; Pettitt non significatif (p clampée à 1
    # sur n=2) → aucune ligne « rupture » (jamais une rupture inventée).
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("r1", "2026-01-01T00:00:00", 0.30),
            _rec("r2", "2026-02-01T00:00:00", 0.20),
        ]
    )
    body = _history_body(tmp_path, store)
    assert "pente/j" in body
    assert "rupture dès" not in body


def test_history_renders_significant_change_point(tmp_path: Path) -> None:
    # 6 runs à 0.30 puis 6 à 0.10 : Pettitt significatif (K=36, p≈0.031) —
    # la carte nomme le premier run du nouveau régime (r07) et la p-value.
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec(f"r{i + 1:02d}", f"2026-01-{i + 1:02d}T00:00:00", value)
            for i, value in enumerate([0.30] * 6 + [0.10] * 6)
        ]
    )
    body = _history_body(tmp_path, store)
    assert "pente/j" in body and "R²" in body
    assert "rupture dès r07" in body
    assert "(p=0.031)" in body
    assert "-0.2000" in body  # Δ signé (amélioration)
