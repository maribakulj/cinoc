"""CLI ``history`` : série d'un pipeline et régressions, sortie stable."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.storage.history_store import HistoryRecord, HistoryStore
from cinoc.interfaces.cli import main


def _record(
    run_id: str,
    completed: str,
    value: float,
    *,
    corpus: str = "c",
    profile: str | None = "flat_text",
) -> HistoryRecord:
    return HistoryRecord(
        run_id=run_id,
        completed_at=completed,
        corpus_name=corpus,
        normalization_profile=profile,
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
    assert "tess: 0.100000 -> 0.200000" in out
    assert "+0.100000" in out
    assert "[corpus c, profil flat_text]" in out


def test_no_regression_prints_clean_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = HistoryStore(tmp_path / "h.db")
    store.add([_record("r1", "2026-06-01T00:00:00+00:00", 0.10)])
    assert main(["history", str(tmp_path / "h.db")]) == 0
    assert "Aucune régression" in capsys.readouterr().out


def test_series_are_printed_apart_by_corpus_and_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-288 : ``--pipeline`` imprimait une seule suite mêlant corpus et
    profils ; chaque série a désormais son en-tête, et aucune régression
    n'est tirée d'un changement de corpus ou de profil."""
    store = HistoryStore(tmp_path / "h.db")
    store.add(
        [
            _record("r1", "2026-06-01T00:00:00+00:00", 0.10),
            _record("r2", "2026-06-02T00:00:00+00:00", 0.40, corpus="autre"),
            _record("r3", "2026-06-03T00:00:00+00:00", 0.30, profile=None),
        ]
    )
    db = str(tmp_path / "h.db")
    assert main(["history", db, "--pipeline", "tess"]) == 0
    out = capsys.readouterr().out
    assert "[corpus autre | profil flat_text | tess | texte]" in out
    assert "[corpus c | profil brut | tess | texte]" in out
    assert "[corpus c | profil flat_text | tess | texte]" in out
    assert main(["history", db]) == 0
    assert "Aucune régression" in capsys.readouterr().out


def test_regressions_print_under_a_cp1252_console(db: Path) -> None:
    """La CI Windows écrit en cp1252 : « → » et « Δ » y levaient
    ``UnicodeEncodeError`` dès qu'une régression était imprimée."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    done = subprocess.run(
        [sys.executable, "-m", "cinoc.interfaces.cli", "history", str(db)],
        capture_output=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("cp1252", "replace")
    assert b"tess: 0.100000 -> 0.200000" in done.stdout
