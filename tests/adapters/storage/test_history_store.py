"""``HistoryStore`` sur **vrai SQLite** : round-trip, idempotence, régressions."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.storage.history_store import (
    HistoryRecord,
    HistorySchemaError,
    HistoryStore,
    SeriesKey,
)

KEY = SeriesKey("corpusA", "flat_text", "tesseract", "text")


def _rec(
    run_id: str,
    when: str,
    value: float,
    *,
    metric: str = "cer",
    corpus: str = "corpusA",
    profile: str | None = "flat_text",
) -> HistoryRecord:
    return HistoryRecord(
        run_id=run_id,
        completed_at=when,
        corpus_name=corpus,
        normalization_profile=profile,
        code_version="0.1.0",
        pipeline="tesseract",
        view="text",
        metric=metric,
        value=value,
    )


def test_round_trip_chronological(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    assert store.add([_rec("r2", "2026-02-01T00:00:00+00:00", 0.15)]) == 1
    store.add([_rec("r1", "2026-01-01T00:00:00+00:00", 0.10)])
    hist = store.history(KEY, "cer")
    assert [r.run_id for r in hist] == ["r1", "r2"]  # trié par completed_at
    assert hist[1].value == pytest.approx(0.15)


def test_re_record_is_idempotent(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add([_rec("r1", "2026-01-01T00:00:00+00:00", 0.10)])
    store.add([_rec("r1", "2026-01-01T00:00:00+00:00", 0.10)])  # même PK
    assert len(store.history(KEY, "cer")) == 1


def test_persists_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    HistoryStore(db).add([_rec("r1", "2026-01-01T00:00:00+00:00", 0.10)])
    assert len(HistoryStore(db).history(KEY, "cer")) == 1


def test_regression_detected_when_cer_worsens(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("r1", "2026-01-01T00:00:00+00:00", 0.10),
            _rec("r2", "2026-02-01T00:00:00+00:00", 0.15),
        ]
    )
    regs = store.regressions("text", "cer")
    assert len(regs) == 1
    reg = regs[0]
    assert reg.pipeline == "tesseract"
    assert (reg.previous, reg.latest) == (pytest.approx(0.10), pytest.approx(0.15))
    assert reg.delta == pytest.approx(0.05)
    assert (reg.previous_run_id, reg.latest_run_id) == ("r1", "r2")


def test_improvement_is_not_a_regression(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("r1", "2026-01-01T00:00:00+00:00", 0.20),
            _rec("r2", "2026-02-01T00:00:00+00:00", 0.10),
        ]
    )
    assert store.regressions("text", "cer") == ()


def test_threshold_filters_small_changes(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("r1", "2026-01-01T00:00:00+00:00", 0.10),
            _rec("r2", "2026-02-01T00:00:00+00:00", 0.13),
        ]
    )
    assert store.regressions("text", "cer", threshold=0.05) == ()
    assert len(store.regressions("text", "cer", threshold=0.01)) == 1


def test_higher_is_better_inverts_direction(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("r1", "2026-01-01T00:00:00+00:00", 0.90, metric="accuracy"),
            _rec("r2", "2026-02-01T00:00:00+00:00", 0.80, metric="accuracy"),
        ]
    )
    # accuracy qui baisse = régression seulement si higher_is_better
    assert store.regressions("text", "accuracy", higher_is_better=True)
    assert store.regressions("text", "accuracy") == ()


def test_single_run_has_no_regression(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add([_rec("r1", "2026-01-01T00:00:00+00:00", 0.10)])
    assert store.regressions("text", "cer") == ()


def test_series_never_mix_corpora_or_profiles(tmp_path: Path) -> None:
    """D-288 : une série était indexée par (pipeline, vue) seulement — un run
    sur un autre corpus, ou sous un autre profil, s'y glissait et faisait une
    « régression » (ou une tendance) qui ne mesurait que le changement de
    convention. Chaque (corpus, profil, pipeline, vue) est sa propre série."""
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _rec("r1", "2026-01-01T00:00:00+00:00", 0.10),
            # Même pipeline, même vue : autre corpus, puis autre profil, puis
            # comparaison brute (``None``) — trois séries de plus, pas trois
            # points de plus.
            _rec("r2", "2026-02-01T00:00:00+00:00", 0.40, corpus="corpusB"),
            _rec("r3", "2026-03-01T00:00:00+00:00", 0.30, profile="nfc"),
            _rec("r4", "2026-04-01T00:00:00+00:00", 0.50, profile=None),
        ]
    )
    assert [r.run_id for r in store.history(KEY, "cer")] == ["r1"]
    raw = SeriesKey("corpusA", None, "tesseract", "text")
    assert [r.run_id for r in store.history(raw, "cer")] == ["r4"]
    assert store.regressions("text", "cer") == ()
    keys = [key for key, _ in store.series("text", "cer")]
    assert keys == [
        raw,
        KEY,
        SeriesKey("corpusA", "nfc", "tesseract", "text"),
        SeriesKey("corpusB", "flat_text", "tesseract", "text"),
    ]
    store.add([_rec("r5", "2026-05-01T00:00:00+00:00", 0.20)])
    (reg,) = store.regressions("text", "cer")
    assert (reg.corpus_name, reg.normalization_profile) == ("corpusA", "flat_text")
    assert (reg.previous_run_id, reg.latest_run_id) == ("r1", "r5")


def test_legacy_database_without_profile_is_refused(tmp_path: Path) -> None:
    """Une base écrite avant la clé de série ne dit pas sous quel profil ses
    valeurs ont été calculées : refusée plutôt que relue en séries mêlées."""
    import sqlite3

    db = tmp_path / "h.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE run_metrics (run_id TEXT, completed_at TEXT, "
            "corpus_name TEXT, code_version TEXT, pipeline TEXT, view TEXT, "
            "metric TEXT, value REAL)"
        )
    with pytest.raises(HistorySchemaError, match="format antérieur"):
        HistoryStore(db).all_records()
