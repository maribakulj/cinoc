"""Le ``JobRunner`` enregistre chaque run terminé dans l'historique (S6, D-046)."""

from __future__ import annotations

from pathlib import Path

from cinoc.adapters.storage import JobState, JobStore
from cinoc.adapters.storage.history_store import HistoryStore
from cinoc.app.demo import demo_run_spec, write_demo_corpus
from cinoc.app.jobs import JobRunner
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.results import load_run_result


def _runner(tmp_path: Path, history: HistoryStore | None) -> JobRunner:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return JobRunner(
        store=JobStore(),
        registry=registry,
        reports_dir=tmp_path,
        code_version="1.0",
        history_store=history,
    )


def test_completed_run_is_recorded(tmp_path: Path) -> None:
    history = HistoryStore(tmp_path / "h.db")
    runner = _runner(tmp_path, history)
    job_id = runner.launch(
        lambda ws: demo_run_spec(write_demo_corpus(ws), run_id="rec-1")
    )
    assert runner.join(job_id, timeout=30)
    assert runner.store.get(job_id).state is JobState.DONE  # type: ignore[union-attr]

    # On découvre une (pipeline, vue, métrique) réelle depuis le RunResult écrit,
    # puis on vérifie qu'elle est dans l'historique (robuste aux détails de la démo).
    result = load_run_result(tmp_path / "rec-1.json")
    sample = next(
        (p, s)
        for p in result.pipelines
        for s in p.aggregate
        if s.value is not None
    )
    pipeline, score = sample
    (series,) = [
        records
        for key, records in history.series(pipeline.view, score.metric)
        if key.pipeline == pipeline.pipeline
    ]
    assert len(series) == 1
    # La démo nomme son corpus ; sa vue texte reçoit le profil par défaut.
    assert series[0].corpus_name == result.manifest.corpus_name
    assert series[0].normalization_profile == "flat_text"
    assert series[0].run_id == "rec-1"
    assert series[0].value == score.value


def test_history_is_optional(tmp_path: Path) -> None:
    # Sans store d'historique, le run aboutit quand même (rétro-compatible).
    runner = _runner(tmp_path, None)
    job_id = runner.launch(
        lambda ws: demo_run_spec(write_demo_corpus(ws), run_id="rec-2")
    )
    assert runner.join(job_id, timeout=30)
    assert runner.store.get(job_id).state is JobState.DONE  # type: ignore[union-attr]
