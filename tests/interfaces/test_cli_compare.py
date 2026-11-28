"""CLI ``compare`` : deux ``RunResult`` JSON → rapport de deltas."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cinoc.app.results import dump_run_result
from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.interfaces.cli import main

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _result(run_id: str, cer: float) -> RunResult:
    manifest = RunManifest(
        run_id=run_id,
        corpus_name="c",
        n_documents=1,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="eng",
                view="text",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=cer, support=1),
                ),
            ),
        ),
    )


def test_compare_command_end_to_end(tmp_path: Path) -> None:
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    dump_run_result(_result("A", 0.30), path_a)
    dump_run_result(_result("B", 0.25), path_b)
    output = tmp_path / "diff.html"

    code = main(["compare", str(path_a), str(path_b), "-o", str(output)])

    assert code == 0
    html = output.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "-0,0500" in html  # amélioration de 0.30 -> 0.25 (décimale FR)


def test_compare_names_each_file_and_speaks_english_on_request(
    tmp_path: Path,
) -> None:
    """Deux runs au même ``run_id`` (une spec relancée) : le rapport nomme le
    fichier de chaque côté — son nom, jamais le chemin de la machine (D5)."""
    (tmp_path / "x").mkdir()
    path_a = tmp_path / "x" / "lundi.json"
    path_b = tmp_path / "mardi.json"
    dump_run_result(_result("run", 0.30), path_a)
    dump_run_result(_result("run", 0.25), path_b)
    output = tmp_path / "diff.html"

    code = main(
        ["compare", str(path_a), str(path_b), "-o", str(output), "--lang", "en"]
    )

    assert code == 0
    html = output.read_text(encoding="utf-8")
    assert "lundi.json" in html and "mardi.json" in html
    assert str(tmp_path) not in html
    assert "-0.0500" in html and '<html lang="en">' in html
