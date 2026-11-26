"""Section Mesures clés : scores standard triables + dot plot CER (IC) + test,
**sans verdict** (aucun gagnant déclaré)."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    InferencePayload,
    PipelineInterval,
)
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.reports.section import Section, SectionContext
from cinoc.reports.sections.key_measures import KeyMeasuresSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _pipe(name: str, cer: float) -> PipelineResult:
    return PipelineResult(
        pipeline=name, view="text",
        aggregate=(
            MetricScore(metric="cer", value=cer, support=900),
            MetricScore(metric="wer", value=round(cer * 2, 4), support=160),
            MetricScore(metric="char_accuracy", value=round(1 - cer, 4), support=900),
            MetricScore(metric="mer", value=round(cer * 1.9, 4), support=160),
        ),
    )


def _result(*, with_inference: bool = False, p: float | None = None) -> RunResult:
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=20, code_version="1.0",
        started_at=FIXED, completed_at=FIXED,
    )
    pipes = (_pipe("tesseract", 0.07), _pipe("pero", 0.045))
    cross = (
        (MetricScore(metric="text:cer", value=p, support=20),)
        if p is not None
        else ()
    )
    analyses = ()
    if with_inference:
        analyses = (Analysis(scope="corpus", view="text", payload=InferencePayload(
            metric="cer", alpha=0.05, n_documents=20,
            intervals=(
                PipelineInterval(pipeline="pero", mean=0.045, lower=0.03,
                                 upper=0.06, n_documents=20),
                PipelineInterval(pipeline="tesseract", mean=0.07, lower=0.05,
                                 upper=0.09, n_documents=20),
            ),
        )),)
    return RunResult(
        manifest=manifest, pipelines=pipes, cross_engine=cross, analyses=analyses
    )


def test_satisfies_protocol_and_gated_on_cer() -> None:
    section = KeyMeasuresSection()
    assert isinstance(section, Section) and section.name == "key_measures"
    assert section.requires == ("cer",)


def test_neutral_standard_scores_table_sortable_with_direction() -> None:
    html = KeyMeasuresSection().render(_result(), SectionContext())
    assert html is not None
    assert "Mesures clés" in html
    assert 'class="data sortable"' in html  # triable par colonne
    assert "CER ↓" in html and "WER ↓" in html  # plus bas = meilleur
    assert "↑" in html  # exactitude : plus haut = meilleur
    # AUCUN verdict : ni colonne « Meilleur pipeline », ni badge verdict (les
    # artefacts de l'ex-« Synthèse »). La caption affirme « aucun gagnant déclaré ».
    assert "Meilleur pipeline" not in html and "Best pipeline" not in html
    assert "sig-badge" not in html
    assert "Aucun gagnant" in html  # neutralité affirmée
    # mer masqué de l'affichage (pas d'en-tête « MER » ; redondant avec WER).
    assert ">MER " not in html and ">MER<" not in html


def test_dot_plot_with_ci_when_inference_present() -> None:
    html = KeyMeasuresSection().render(_result(with_inference=True), SectionContext())
    assert html is not None
    assert 'class="dot-svg"' in html  # dot plot rendu
    assert html.count('class="dot-ci"') == 2  # une moustache d'IC par moteur
    assert html.count('class="dot-pt"') == 2  # un point (moyenne) par moteur
    assert "IC 95" in html  # légende honnête


def test_significance_as_neutral_fact_wilcoxon() -> None:
    # k=2 → Wilcoxon : le RÉSULTAT DU TEST est un fait, pas un gagnant.
    html = KeyMeasuresSection().render(_result(p=0.002), SectionContext())
    assert html is not None
    assert "Wilcoxon" in html and "p = 0,0020" in html
    assert "significative" in html  # qualifie la DIFFÉRENCE, pas un moteur
    # Le support du test (cas complets, apparié) est dit : ce n'est pas celui
    # d'un agrégat quand un moteur a perdu une unité.
    assert "(20 cas complets)" in html


def test_incomplete_aggregate_shows_scored_over_expected() -> None:
    """A3 : un agrégat qui a perdu une unité en échec porte « n notés / n
    attendus » ; un agrégat complet ne porte rien."""
    result = _result()
    pero = result.pipelines[1].model_copy(
        update={
            "aggregate": (
                MetricScore(metric="cer", value=0.045, support=19, expected=20),
            )
        }
    )
    tess = result.pipelines[0].model_copy(
        update={
            "aggregate": (
                MetricScore(metric="cer", value=0.07, support=20, expected=20),
            )
        }
    )
    result = result.model_copy(update={"pipelines": (tess, pero)})
    html = KeyMeasuresSection().render(result, SectionContext())
    assert html is not None
    assert ">19/20</span>" in html
    assert "20/20" not in html
    en = KeyMeasuresSection().render(result, SectionContext(lang="en"))
    assert en is not None and "19 documents scored out of 20 expected" in en


def test_dot_plot_says_when_engines_have_different_n() -> None:
    """L'IC est marginal : un moteur qui a perdu une unité a un n plus petit."""
    result = _result(with_inference=True)
    (analysis,) = result.analyses
    payload = analysis.payload
    assert isinstance(payload, InferencePayload)
    shrunk = payload.model_copy(
        update={
            "intervals": (
                payload.intervals[0].model_copy(update={"n_documents": 19}),
                payload.intervals[1],
            )
        }
    )
    result = result.model_copy(
        update={"analyses": (analysis.model_copy(update={"payload": shrunk}),)}
    )
    html = KeyMeasuresSection().render(result, SectionContext())
    assert html is not None and "n=19–20" in html


def test_none_without_cer() -> None:
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=1, code_version="1.0",
        started_at=FIXED, completed_at=FIXED,
    )
    result = RunResult(
        manifest=manifest,
        pipelines=(PipelineResult(
            pipeline="p", view="text",
            aggregate=(MetricScore(metric="wer", value=0.1, support=1),),
        ),),
    )
    assert KeyMeasuresSection().render(result, SectionContext()) is None
