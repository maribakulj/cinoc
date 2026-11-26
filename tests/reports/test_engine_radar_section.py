"""Section radar : profil multi-métrique par moteur, superposé."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import (
    MetricScore,
    PipelineResult,
    RunResult,
)
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.engine_radar import EngineRadarSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)

_AXIS_METRICS = (
    "char_accuracy",
    "word_accuracy",
    "fca",
    "bow_f1",
    "searchability",
    "unanchored_trigrams",
)


def _pipe(name: str, values: dict[str, float]) -> PipelineResult:
    return PipelineResult(
        pipeline=name,
        view="text",
        aggregate=tuple(
            MetricScore(metric=m, value=v, support=2) for m, v in values.items()
        ),
    )


def _result(pipelines: tuple[PipelineResult, ...]) -> RunResult:
    manifest = RunManifest(
        run_id="r", corpus_name="demo", n_documents=2,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    return RunResult(manifest=manifest, pipelines=pipelines, documents=())


def test_radar_renders_one_polygon_per_engine() -> None:
    full = {m: 0.8 for m in _AXIS_METRICS}
    result = _result((_pipe("tesseract", full), _pipe("pero", dict(full, fca=0.6))))
    html = EngineRadarSection().render(result, SectionContext())
    assert html is not None
    assert "radar-svg" in html
    assert html.count('class="radar-area"') == 2  # un polygone par moteur
    assert "Profil radar" in html
    assert "tesseract" in html and "pero" in html


def test_radar_tooltips_absolute_scale_and_accessible() -> None:
    full = {m: 0.8 for m in _AXIS_METRICS}
    result = _result((_pipe("tesseract", full), _pipe("pero", dict(full, fca=0.6))))
    html = EngineRadarSection().render(result, SectionContext())
    assert html is not None
    # Sommets cliquables + infobulle valeur brute ET normalisée (auditables).
    assert "radar-vertex" in html
    assert "norm." in html and "%" in html
    # Échelle absolue explicitée (≠ min-max relatif trompeur).
    assert "absolue" in html
    assert 'role="img"' in html  # accessible


def test_radar_signals_dropped_non_comparable_dimensions() -> None:
    # ≥3 axes communs (radar rendu) ; ``unanchored_trigrams`` présent pour un seul
    # moteur → non comparable → masqué MAIS signalé (jamais comblé par un zéro).
    shared = {m: 0.8 for m in _AXIS_METRICS if m != "unanchored_trigrams"}
    result = _result(
        (
            _pipe("tesseract", dict(shared, unanchored_trigrams=0.1)),
            _pipe("pero", shared),
        )
    )
    html = EngineRadarSection().render(result, SectionContext())
    assert html is not None
    assert "non comparables masquées" in html


def test_radar_none_when_too_few_axes() -> None:
    # un seul axe partagé (< 3) → pas de radar.
    result = _result((_pipe("tesseract", {"char_accuracy": 0.8}),))
    assert EngineRadarSection().render(result, SectionContext()) is None


def test_radar_axes_require_metric_for_all_engines() -> None:
    # pero n'a que 2 axes en commun avec tesseract (< 3) → None.
    result = _result(
        (
            _pipe("tesseract", {m: 0.8 for m in _AXIS_METRICS}),
            _pipe("pero", {"char_accuracy": 0.7, "word_accuracy": 0.6}),
        )
    )
    assert EngineRadarSection().render(result, SectionContext()) is None


def test_radar_none_without_pipelines() -> None:
    assert EngineRadarSection().render(_result(()), SectionContext()) is None
