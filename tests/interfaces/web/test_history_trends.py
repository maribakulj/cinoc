"""Historique : sparklines CER (tendances) rendues **serveur** depuis le store."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from cinoc.adapters.storage.history_store import HistoryRecord, HistoryStore
from cinoc.interfaces.web.app import _TEMPLATES_DIR
from cinoc.interfaces.web.routers.home import build_home_router
from tests.adversarial._contrat import etiquette_exploratoire, verdicts


def _history_body(tmp_path: Path, store: HistoryStore, lang: str = "fr") -> str:
    app = FastAPI()
    app.include_router(
        build_home_router(
            tmp_path / "reports",
            Jinja2Templates(directory=_TEMPLATES_DIR),
            statuses=lambda: (),
            third_party=lambda: (),
            history_store=store,
        )
    )
    return TestClient(app).get(f"/history?lang={lang}").text


def _rec(
    run_id: str,
    ts: str,
    value: float,
    *,
    corpus: str = "c",
    profile: str | None = "flat_text",
) -> HistoryRecord:
    return HistoryRecord(
        run_id=run_id,
        completed_at=ts,
        corpus_name=corpus,
        normalization_profile=profile,
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
    # 2 runs : pente OLS affichée ; Pettitt non calculable sous 3 runs (rév. 7,
    # 28/11 : à 2 points sa p vaut 1 par construction) → aucune ligne « rupture ».
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


@pytest.mark.tranche("1b")
def test_history_renders_significant_change_point(tmp_path: Path) -> None:
    # 6 runs à 0.30 puis 6 à 0.10 : Pettitt (K=36, p≈0.031) — la carte nomme le
    # premier run du nouveau régime (r07) et la p-value. Rév. 7 : l'étiquette est
    # « exploratoire », aucun verdict « significatif » n'est employé.
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
    assert etiquette_exploratoire(body) and not verdicts(body)
    assert etiquette_exploratoire(_history_body(tmp_path, store, lang="en"), "en")


@pytest.mark.tranche("1b")
def test_history_says_when_a_slope_is_not_significant(tmp_path: Path) -> None:
    """Défaut 10 de l'audit D-264 : la pente s'affichait sans test. Six runs
    qui fluctuent (p = 0,186) : la carte donne la p-value. Rév. 7 (inverse) : elle
    ne dit plus « non significative » mais étiquette la pente « exploratoire »
    (un test de l'ancienne inférence n'est jamais un verdict)."""
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec(f"r{i + 1}", f"2026-01-{i + 1:02d}T00:00:00", value)
            for i, value in enumerate([0.30, 0.28, 0.31, 0.26, 0.29, 0.25])
        ]
    )
    body = _history_body(tmp_path, store)
    assert "p=0.186" in body
    assert etiquette_exploratoire(body) and not verdicts(body)
    english = _history_body(tmp_path, store, lang="en")
    assert "p=0.186" in english and "p=0.186 · not significant" not in english
    assert etiquette_exploratoire(english, "en") and not verdicts(english)


@pytest.mark.tranche("1b")
def test_history_says_when_a_slope_is_significant(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec(f"r{i + 1}", f"2026-01-{i + 1:02d}T00:00:00", value)
            for i, value in enumerate([0.30, 0.27, 0.25, 0.22, 0.20, 0.17])
        ]
    )
    body = _history_body(tmp_path, store)
    # Rév. 7 (inverse) : la p (linregress : 3,4·10⁻⁶, affichée « 0.000 ») reste
    # publiée comme nombre ; plus de « significative (p ≤ 0,05) », la pente est
    # étiquetée exploratoire.
    assert "p=0.000" in body
    assert etiquette_exploratoire(body) and not verdicts(body)
    assert "significative (p ≤ 0,05)" not in body


def test_history_says_two_runs_cannot_be_tested(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("r1", "2026-01-01T00:00:00", 0.30),
            _rec("r2", "2026-02-01T00:00:00", 0.20),
        ]
    )
    body = _history_body(tmp_path, store)
    assert "aucun test à 2 runs" in body
    assert "significative" not in body.split("trend-grid", 1)[1].split("</section>")[0]


def test_a_trend_never_spans_two_corpora_or_two_profiles(tmp_path: Path) -> None:
    """D-288 : six runs sur deux corpus et deux profils faisaient une seule
    carte (une « pente » nette qui ne mesurait que le changement de corpus).
    Chaque (corpus, profil, pipeline, vue) a sa carte, qui le dit, FR et EN."""
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("a1", "2026-01-01T00:00:00", 0.30),
            _rec("a2", "2026-01-02T00:00:00", 0.31),
            _rec("b1", "2026-01-03T00:00:00", 0.10, corpus="autre"),
            _rec("b2", "2026-01-04T00:00:00", 0.11, corpus="autre"),
            _rec("n1", "2026-01-05T00:00:00", 0.05, profile=None),
            _rec("n2", "2026-01-06T00:00:00", 0.06, profile=None),
        ]
    )
    body = _history_body(tmp_path, store)
    assert body.count('class="panel trend-card"') == 3
    assert "Corpus autre" in body and "Profil brut" in body
    assert "Profil flat_text" in body
    # Chaque série monte de 0,01 à son dernier run : trois régressions de
    # +0,01, aucune de 0,30 → 0,10 tirée d'un corpus à l'autre.
    assert body.count("<td>autre</td>") == 3  # sa régression + 2 lignes du journal
    assert "+0.0100" in body and "0.3100 → 0.1000" not in body
    english = _history_body(tmp_path, store, lang="en")
    assert "Profile raw" in english


def test_legacy_database_is_refused_and_said(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "h.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE run_metrics (run_id TEXT, completed_at TEXT, "
            "corpus_name TEXT, code_version TEXT, pipeline TEXT, view TEXT, "
            "metric TEXT, value REAL)"
        )
    body = _history_body(tmp_path, HistoryStore(db))
    assert "format antérieur" in body
    english = _history_body(tmp_path, HistoryStore(db), lang="en")
    assert "earlier format" in english
