"""Section overview : tableau, valeurs, ``None`` → tiret, résultat vide."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.overview import OverviewSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _result(value: float | None) -> RunResult:
    manifest = RunManifest(
        run_id="r",
        corpus_name="demo",
        n_documents=2,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="tesseract",
                view="text",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=value, support=2),
                ),
            ),
        ),
    )


def test_renders_table_with_values() -> None:
    html = OverviewSection().render(_result(0.25), SectionContext())
    assert html is not None
    assert "tesseract" in html
    assert "0,2500" in html
    assert "demo" in html
    assert "cer" in html


def test_none_value_rendered_as_dash() -> None:
    html = OverviewSection().render(_result(None), SectionContext())
    assert html is not None
    assert "—" in html


def test_empty_result_returns_none() -> None:
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=0,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    section = OverviewSection()
    assert section.render(RunResult(manifest=manifest), SectionContext()) is None


def _pipe(name: str, value: float) -> PipelineResult:
    return PipelineResult(
        pipeline=name,
        view="text",
        conditional_aggregate=(MetricScore(metric="cer", value=value, support=2),),
    )


def _two(cer_a: float, cer_b: float) -> RunResult:
    manifest = RunManifest(
        run_id="r",
        corpus_name="demo",
        n_documents=2,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest, pipelines=(_pipe("tesseract", cer_a), _pipe("pero", cer_b))
    )


def test_scope_moved_to_hero_not_readouts() -> None:
    # La portée (docs/moteurs) vit désormais dans le héros (rendu par le renderer) ;
    # la section overview porte les métriques par vue, plus de bande de readouts.
    html = OverviewSection().render(_two(0.1, 0.2), SectionContext())
    assert html is not None
    assert "Métriques par vue" in html
    assert 'class="readouts"' not in html


def test_cell_tint_is_relative_to_column_max() -> None:
    html = OverviewSection().render(_two(0.1, 0.2), SectionContext())
    assert html is not None
    # cer 0.1 vs max 0.2 → teinte 0.5 ; 0.2 → 1.0 (échelle relative à la colonne)
    assert 'style="--t:0.5"' in html
    assert 'style="--t:1.0"' in html


def test_renders_english_labels() -> None:
    html = OverviewSection().render(_result(0.25), SectionContext(lang="en"))
    assert html is not None
    assert "Metrics per view" in html  # titre de section EN
    assert "Métriques par vue" not in html  # bascule de langue effective
    assert "Vue :" not in html  # vue unique → pas de sous-titre de vue ressassé
