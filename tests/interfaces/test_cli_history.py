"""CLI ``history`` : série d'un pipeline et régressions, sortie stable."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.storage.history_store import HistoryRecord, HistoryStore
from cinoc.interfaces.cli import main


def _record(run_id: str, completed: str, value: float) -> HistoryRecord:
    return HistoryRecord(
        run_id=run_id,
        completed_at=completed,
        corpus_name="c",
        code_version="1.0",
        pipeline="tess",
        view="texte",
        metric="cer",
        value=value,
    )


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _record("r1", "2026-06-01T00:00:00+00:00", 0.10),
            _record("r2", "2026-06-02T00:00:00+00:00", 0.20),
        ]
    )
    return tmp_path / "h.db"


def test_series_lists_chronological_values(
    db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["history", str(db), "--pipeline", "tess"]) == 0
    out = capsys.readouterr().out
    assert "r1" in out and "r2" in out
    assert out.index("r1") < out.index("r2")
    assert "cer=0.100000" in out


def test_regressions_reported_with_delta(
    db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["history", str(db)]) == 0
    out = capsys.readouterr().out
    # CER 0.10 → 0.20 : dégradation signalée avec le delta signé.
    assert "tess: 0.100000 → 0.200000" in out
    assert "+0.100000" in out


def test_no_regression_prints_clean_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add([_record("r1", "2026-06-01T00:00:00+00:00", 0.10)])
    assert main(["history", str(tmp_path / "h.db")]) == 0
    assert "Aucune régression" in capsys.readouterr().out
