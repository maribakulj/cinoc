"""Section cross_engine : clé parsée en colonnes + verdict, ``None`` si absent.

Étendue 4e.1 : blocs ``inter_engine`` (complémentarité oracle + divergence JS),
avec la borne bag-of-words **documentée dans la prose** (anti-surinterprétation).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    ComplementarityDocument,
    EngineTokenRecall,
    InferencePayload,
    InterEngineComplementarity,
    InterEngineDivergence,
    InterEnginePayload,
    PairwiseDifference,
    PipelineInterval,
    PipelineRank,
    TaxonomyDivergencePair,
)
from cinoc.evaluation.result import MetricScore, RunResult
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.cross_engine import CrossEngineSection
from tests.adversarial._contrat import etiquette_exploratoire, verdicts

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=2,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def _result(
    metric: str, value: float | None, payload: InferencePayload | None = None
) -> RunResult:
    analyses = (
        (Analysis(scope="corpus", view="text", payload=payload),)
        if payload is not None
        else ()
    )
    return RunResult(
        manifest=_manifest(),
        cross_engine=(MetricScore(metric=metric, value=value, support=10),),
        analyses=analyses,
    )


def _wilcoxon(p: float, p_holm: float, family: int) -> InferencePayload:
    return InferencePayload(
        metric="cer", alpha=0.05, n_documents=10, test="wilcoxon",
        p_value=p, p_holm=p_holm, family_size=family,
        mean_ranks=(
            PipelineRank(pipeline="alpha", mean_rank=1.2),
            PipelineRank(pipeline="beta", mean_rank=1.8),
        ),
    )


@pytest.mark.tranche("1b")
def test_significant_verdict_and_parsed_columns() -> None:
    html = CrossEngineSection().render(
        _result("text:cer:significance_p", 0.03, _wilcoxon(0.03, 0.03, 1)),
        SectionContext(),
    )
    assert html is not None
    # Question 7 (seconde revue) : plus de « Significativité » en titre.
    assert "Tests inter-moteurs (exploratoires)" in html
    assert "Significativité" not in html
    # clé éclatée en colonnes Vue / Métrique (vue affichée en libellé humain)
    assert ">Texte<" in html and ">cer<" in html
    assert "0,0300" in html
    assert "Wilcoxon signé-rangs" in html  # le test nommé, pas « Wilcoxon / Friedman »
    # Rév. 7 (inverse) : plus de verdict « significatif » ; la p reste un nombre
    # (0,0300 ci-dessus) et le test est étiqueté exploratoire.
    assert not verdicts(html)
    assert etiquette_exploratoire(html)



@pytest.mark.tranche("1b")
def test_verdict_reads_the_holm_corrected_p() -> None:
    """p brute 0,03 parmi 7 tests : corrigée 0,21 (D7). Rév. 7 : les deux p sont
    publiées comme nombres, sans verdict « non significatif »."""
    html = CrossEngineSection().render(
        _result("text:cer:significance_p", 0.03, _wilcoxon(0.03, 0.21, 7)),
        SectionContext(),
    )
    assert html is not None
    assert "0,0300" in html and "0,2100" in html
    assert not verdicts(html) and etiquette_exploratoire(html)
    assert "Holm sur les 7 test(s)" in html


def test_a_row_without_payload_says_uncorrected() -> None:
    """Résultat antérieur au schéma 5 : la p brute reste, sans verdict."""
    html = CrossEngineSection().render(
        _result("text:cer:significance_p", 0.03), SectionContext()
    )
    assert html is not None
    assert "0,0300" in html and "non corrigé" in html
    assert ">significatif<" not in html


def test_a_test_not_computed_gives_its_reason() -> None:
    payload = InferencePayload(
        metric="cer", alpha=0.05, n_documents=3, not_computed="insufficient_support"
    )
    html = CrossEngineSection().render(
        _result("text:cer:significance_p", None, payload), SectionContext()
    )
    assert html is not None
    assert "non calculé" in html and "3 cas complets, il en faut au moins 6" in html


def test_none_value_rendered_as_dash() -> None:
    html = CrossEngineSection().render(_result("x", None), SectionContext())
    assert html is not None
    assert "—" in html


def test_empty_cross_engine_returns_none() -> None:
    section = CrossEngineSection()
    assert section.render(RunResult(manifest=_manifest()), SectionContext()) is None


def _friedman(**update: object) -> InferencePayload:
    payload = InferencePayload(
        metric="cer",
        alpha=0.05,
        n_documents=10,
        test="friedman",
        p_value=0.0017,
        p_holm=0.0017,
        family_size=1,
        critical_distance=1.0482,
        q_alpha=2.3437,
        mean_ranks=(
            PipelineRank(pipeline="alpha", mean_rank=1.2),
            PipelineRank(pipeline="beta", mean_rank=2.0),
            PipelineRank(pipeline="gamma", mean_rank=2.8),
        ),
        cd_groups=(("alpha", "beta"), ("beta", "gamma")),
        pairwise=(
            PairwiseDifference(a="alpha", b="beta", rank_gap=0.8),
            PairwiseDifference(a="alpha", b="gamma", rank_gap=1.6),
            PairwiseDifference(a="beta", b="gamma", rank_gap=0.8),
        ),
        intervals=(
            PipelineInterval(
                pipeline="alpha", value=0.1062, lower=0.095, upper=0.1162,
                n_documents=10,
            ),
        ),
    )
    return payload.model_copy(update=update)


@pytest.mark.tranche("1b")
def test_inference_block_renders_ranks_posthoc_and_intervals() -> None:
    result = _result("text:cer:significance_p", 0.0017, _friedman())
    html = CrossEngineSection().render(result, SectionContext())
    assert html is not None
    assert ">Friedman<" in html
    assert "CD = 1,0482" in html and "q = 2,3437" in html
    assert "rang moyen" in html
    assert "[0,0950 ; 0,1162]" in html
    # L'IC est à côté du chiffre qu'il encadre : l'agrégat micro, pas une
    # moyenne des documents.
    assert "agrégat (micro)" in html and ">moyenne<" not in html
    assert "0,1062" in html
    # Les paires, pas des groupes disjoints : seule alpha – gamma diffère, et
    # les barres qui se chevauchent le montrent.
    # Rév. 7 : la paire que la distance critique sépare reste nommée (comme
    # paire), sans la dire « significative ».
    assert "alpha – gamma" in html and "paires significatives" not in html
    assert not verdicts(html)
    assert "{alpha, beta} · {beta, gamma}" in html
    assert "groupes indiscernables" not in html
    # Déterminisme bit-à-bit du rendu.
    assert html == CrossEngineSection().render(result, SectionContext())


def test_a_friedman_not_rejected_has_no_posthoc() -> None:
    payload = _friedman(
        p_value=0.0572, p_holm=0.343, family_size=7, critical_distance=None,
        q_alpha=None, cd_groups=(), pairwise=(), intervals=(),
    )
    html = CrossEngineSection().render(
        _result("text:cer:significance_p", 0.0572, payload), SectionContext()
    )
    assert html is not None
    assert "Post-hoc de Nemenyi non effectué" in html
    assert "IC 95" not in html  # mode rapide : rangs seuls


def test_two_pipeline_inference_block_points_to_wilcoxon() -> None:
    html = CrossEngineSection().render(
        _result("text:cer:significance_p", 0.02, _wilcoxon(0.02, 0.02, 1)),
        SectionContext(),
    )
    assert html is not None
    assert "pas de post-hoc" in html


def _inter_engine_result() -> RunResult:
    """Témoin : payload ``inter_engine`` seul (aucun scalaire cross_engine)."""
    payload = InterEnginePayload(
        complementarity=InterEngineComplementarity(
            n_documents=3,
            n_reference_tokens=120,
            oracle_recall=0.95,
            best_single_recall=0.9,
            best_engine="alpha",
            absolute_gap=0.05,
            relative_gap=0.5,
            per_engine_recall=(
                EngineTokenRecall(pipeline="alpha", recall=0.9),
                EngineTokenRecall(pipeline="beta", recall=0.85),
            ),
            per_document=(
                ComplementarityDocument(
                    document_id="d2",
                    oracle_recall=0.9,
                    best_single_recall=0.7,
                    absolute_gap=0.2,
                ),
            ),
        ),
        taxonomy_divergence=InterEngineDivergence(
            pairs=(
                TaxonomyDivergencePair(a="alpha", b="beta", divergence=0.1887),
            ),
            max_pair=TaxonomyDivergencePair(a="alpha", b="beta", divergence=0.1887),
        ),
    )
    return RunResult(
        manifest=_manifest(),
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )


def test_inter_engine_blocks_render_with_documented_bound() -> None:
    # Le payload seul suffit (pas de scalaire cross_engine requis) ; la borne
    # bag-of-words est documentée dans la prose (anti-surinterprétation).
    html = CrossEngineSection().render(_inter_engine_result(), SectionContext())
    assert html is not None
    assert "complémentarité" in html
    assert "oracle" in html
    assert "Borne supérieure" in html and "ordre est ignoré" in html
    assert "95,0%" in html and "90,0%" in html  # oracle + meilleur seul
    assert "alpha" in html and "beta" in html
    assert "d2" in html and "20,0%" in html  # document au plus fort écart
    assert "Jensen-Shannon" in html
    assert "0,1887" in html  # divergence de la paire (et de max_pair)
    # Déterminisme bit-à-bit du rendu.
    assert html == CrossEngineSection().render(_inter_engine_result(), SectionContext())


@pytest.mark.tranche("1b")
def test_renders_english_labels() -> None:
    # Mêmes fixtures, contexte EN : libellés anglais présents, FR absents.
    result = _result("text:cer:significance_p", 0.03, _wilcoxon(0.03, 0.03, 1))
    html = CrossEngineSection().render(result, SectionContext(lang="en"))
    assert html is not None
    assert "Inter-engine tests (exploratory)" in html
    assert "Inter-engine significance" not in html
    assert "Tests inter-moteurs" not in html
    assert etiquette_exploratoire(html, "en") and not etiquette_exploratoire(html)
    assert not verdicts(html) and "significatif" not in html
    assert "Wilcoxon signed-rank" in html and "raw p" in html
    posthoc = CrossEngineSection().render(
        _result("text:cer:significance_p", 0.0017, _friedman()),
        SectionContext(lang="en"),
    )
    assert posthoc is not None
    assert "alpha – gamma" in posthoc and "significant pairs" not in posthoc
    assert not verdicts(posthoc)
    assert "CD bars" in posthoc and "Barres CD" not in posthoc
    assert "aggregate (micro)" in posthoc and "agrégat" not in posthoc
    assert ">View<" in html and ">Vue<" not in html
    # Le bloc inter-moteurs (complémentarité + divergence) bascule aussi en EN.
    inter = CrossEngineSection().render(
        _inter_engine_result(), SectionContext(lang="en")
    )
    assert inter is not None
    assert "engine complementarity" in inter and "complémentarité" not in inter
    assert "Upper bound" in inter and "Borne supérieure" not in inter


def test_divergence_without_max_pair_says_identical_profiles() -> None:
    payload = InterEnginePayload(
        taxonomy_divergence=InterEngineDivergence(
            pairs=(TaxonomyDivergencePair(a="alpha", b="beta", divergence=0.0),),
            max_pair=None,
        ),
    )
    result = RunResult(
        manifest=_manifest(),
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )
    html = CrossEngineSection().render(result, SectionContext())
    assert html is not None
    assert "identiques" in html  # pas de « paire la plus divergente » inventée
    assert "0,0000" in html


def test_a_hypothesis_denominator_micro_says_not_estimable() -> None:
    """B9c (tranche 1a) : MER, cMER — le dénominateur du micro dépend de la
    sortie ; aucune procédure validée, le bloc le dit (FR/EN), sans IC."""
    payload = _friedman(metric="mer", intervals=(), micro_estimable=False)
    for lang, text in (
        ("fr", "<b>inférence non estimable</b>"),
        ("en", "<b>inference not estimable</b>"),
    ):
        html = CrossEngineSection().render(
            _result("text:mer:significance_p", 0.0017, payload),
            SectionContext(lang=lang),
        )
        assert html is not None and text in html
        assert "IC 95" not in html and "95% CI" not in html
