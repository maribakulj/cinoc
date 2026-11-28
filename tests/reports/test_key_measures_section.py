"""Section Mesures clés : scores standard triables + dot plot CER (IC) + test,
**sans verdict** (aucun gagnant déclaré)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    InferencePayload,
    PairwiseDifference,
    PipelineInterval,
    PipelineRank,
)
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.reports.section import Section, SectionContext
from cinoc.reports.sections.key_measures import KeyMeasuresSection
from tests.adversarial._contrat import etiquette_exploratoire, verdicts

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _pipe(name: str, cer: float) -> PipelineResult:
    return PipelineResult(
        pipeline=name, view="text",
        conditional_aggregate=(
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
    analyses: tuple[Analysis, ...] = ()
    if with_inference or p is not None:
        analyses = (Analysis(scope="corpus", view="text", payload=InferencePayload(
            metric="cer", alpha=0.05, n_documents=20, test="wilcoxon",
            p_value=p if p is not None else 0.5,
            p_holm=p if p is not None else 0.5,
            family_size=1,
            mean_ranks=(
                PipelineRank(pipeline="pero", mean_rank=1.1),
                PipelineRank(pipeline="tesseract", mean_rank=1.9),
            ),
            intervals=() if not with_inference else (
                PipelineInterval(pipeline="pero", value=0.045, lower=0.03,
                                 upper=0.06, n_documents=20),
                PipelineInterval(pipeline="tesseract", value=0.07, lower=0.05,
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
    assert html.count('class="dot-pt"') == 2  # un point (l'agrégat) par moteur
    assert "IC 95" in html  # légende honnête
    # Le point est le CER du tableau (micro), et la légende le dit.
    assert "point = CER du tableau (micro" in html and "moyenne" not in html
    english = KeyMeasuresSection().render(
        _result(with_inference=True), SectionContext(lang="en")
    )
    assert english is not None
    assert "dot = the table’s CER (micro" in english and "point =" not in english


@pytest.mark.tranche("1b")
def test_significance_as_neutral_fact_wilcoxon() -> None:
    # k=2 → Wilcoxon : le RÉSULTAT DU TEST est un fait, pas un gagnant.
    html = KeyMeasuresSection().render(_result(p=0.002), SectionContext())
    assert html is not None
    assert "Wilcoxon signé-rangs" in html and "p = 0,0020" in html
    assert "corrigée de Holm sur 1 test(s) : 0,0020" in html
    # Rév. 7 (inverse) : la phrase donne les p comme nombres, sans qualifier la
    # différence de « significative » ; le test est étiqueté exploratoire.
    assert not verdicts(html)
    assert etiquette_exploratoire(html)
    # Le support du test (observations complètes, apparié) est dit : ce n'est pas celui
    # d'un agrégat quand un moteur a perdu une unité.
    assert "(20 observations complètes)" in html


def test_incomplete_aggregate_shows_scored_over_expected() -> None:
    """A3 : un agrégat qui a perdu une unité en échec porte « n notés / n
    attendus » ; un agrégat complet ne porte rien."""
    result = _result()
    pero = result.pipelines[1].model_copy(
        update={
            "conditional_aggregate": (
                MetricScore(metric="cer", value=0.045, support=19, expected=20),
            )
        }
    )
    tess = result.pipelines[0].model_copy(
        update={
            "conditional_aggregate": (
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
            conditional_aggregate=(MetricScore(metric="wer", value=0.1, support=1),),
        ),),
    )
    assert KeyMeasuresSection().render(result, SectionContext()) is None


def _friedman_result(**update: object) -> RunResult:
    payload = InferencePayload(
        metric="cer", alpha=0.05, n_documents=10, test="friedman",
        p_value=0.0017, p_holm=0.0017, family_size=1,
        critical_distance=1.0482, q_alpha=2.3437,
        mean_ranks=(
            PipelineRank(pipeline="a", mean_rank=1.2),
            PipelineRank(pipeline="b", mean_rank=2.0),
            PipelineRank(pipeline="c", mean_rank=2.8),
        ),
        cd_groups=(("a", "b"), ("b", "c")),
        pairwise=(
            PairwiseDifference(a="a", b="b", rank_gap=0.8),
            PairwiseDifference(a="a", b="c", rank_gap=1.6),
            PairwiseDifference(a="b", b="c", rank_gap=0.8),
        ),
    ).model_copy(update=update)
    return RunResult(
        manifest=RunManifest(
            run_id="r", corpus_name="c", n_documents=10, code_version="1.0",
            started_at=FIXED, completed_at=FIXED,
        ),
        pipelines=(_pipe("a", 0.05), _pipe("b", 0.06), _pipe("c", 0.07)),
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )


@pytest.mark.tranche("1b")
def test_three_engines_are_a_friedman_with_its_pairs() -> None:
    """D7 : à 3 pipelines le test est un Friedman — jamais « Wilcoxon » — et
    le post-hoc nomme la seule paire qui diffère."""
    html = KeyMeasuresSection().render(_friedman_result(), SectionContext())
    assert html is not None
    assert "Friedman : p = 0,0017" in html and "Wilcoxon" not in html
    assert "entre les 3 moteurs" in html
    assert "a – c" in html and "paires significatives" not in html
    assert not verdicts(html)
    # La phrase qui tirait une significativité de groupes disjoints est retirée.
    assert "hors d'un même groupe" not in html
    en = KeyMeasuresSection().render(_friedman_result(), SectionContext(lang="en"))
    assert en is not None
    assert "Friedman: p = 0.0017" in en
    assert "a – c" in en and "significant pairs" not in en
    assert not verdicts(en)


@pytest.mark.tranche("1b")
def test_a_friedman_not_rejected_after_holm_says_so() -> None:
    html = KeyMeasuresSection().render(
        _friedman_result(
            p_value=0.0572, p_holm=0.343, family_size=7, critical_distance=None,
            q_alpha=None, cd_groups=(), pairwise=(),
        ),
        SectionContext(),
    )
    assert html is not None
    assert "p = 0,0572, corrigée de Holm sur 7 test(s) : 0,3430" in html
    assert not verdicts(html) and etiquette_exploratoire(html)
    assert "Post-hoc de Nemenyi non effectué" in html


def test_test_not_computed_says_why() -> None:
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=3, code_version="1.0",
        started_at=FIXED, completed_at=FIXED,
    )
    payload = InferencePayload(
        metric="cer", alpha=0.05, n_documents=3, not_computed="insufficient_support"
    )
    result = RunResult(
        manifest=manifest,
        pipelines=(_pipe("a", 0.05), _pipe("b", 0.06)),
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )
    html = KeyMeasuresSection().render(result, SectionContext())
    assert html is not None
    assert "test non calculé : 3 observations complètes, il en faut au moins 6." in html
    # Sans payload (résultat antérieur au schéma 5) : le dire, pas se taire.
    bare = KeyMeasuresSection().render(
        result.model_copy(update={"analyses": ()}), SectionContext(lang="en")
    )
    assert bare is not None and "test not computed." in bare


def _with_views(*views: object) -> RunResult:
    result = _result()
    manifest = result.manifest.model_copy(update={"view_specs": views})
    return result.model_copy(update={"manifest": manifest})


def test_the_convention_is_written_next_to_the_figure() -> None:
    """D-285 : un CER ne se lit pas sans sa normalisation. Nom du profil et
    définition, dérivée de ses leviers, sous le titre de la vue, FR et EN ;
    et ce qui rend le chiffre comparable aux outils de référence."""
    from cinoc.domain.artifacts import ArtifactType
    from cinoc.domain.evaluation import EvaluationView

    texts = frozenset({ArtifactType.RAW_TEXT})
    view = EvaluationView(name="text", candidate_types=texts)
    fr = KeyMeasuresSection().render(_with_views(view), SectionContext())
    en = KeyMeasuresSection().render(_with_views(view), SectionContext(lang="en"))
    assert fr is not None and en is not None
    assert "Normalisation <code>flat_text</code> : NFC, invisibles retirés" in fr
    assert "saut de ligne compris" in fr and "« texte (lignes) »" in fr
    assert "every whitespace run, line breaks included" in en
    assert "“text (lines)”" in en and "saut de ligne" not in en
    lines = view.model_copy(update={"normalization_profile": "keep_line_breaks"})
    html = KeyMeasuresSection().render(_with_views(lines), SectionContext())
    assert html is not None and "sauts de ligne comptés" in html
    raw = view.model_copy(update={"normalization_profile": None})
    html = KeyMeasuresSection().render(_with_views(raw), SectionContext())
    assert html is not None and "aucune normalisation (comparaison brute)" in html


def test_only_established_metrics_enter_the_headline() -> None:
    """D-289 : ``char_accuracy`` (adaptée, 1 − CER borné) n'est pas classée ;
    le classement ne porte que les établies (cer, wer ; mer masqué)."""
    html = KeyMeasuresSection().render(_result(), SectionContext())
    assert html is not None
    head = html.split("<tbody>")[0]
    assert "CER ↓" in head and "WER ↓" in head
    assert "Exact" not in head and "CHAR_ACCURACY" not in head
    assert "établies" in html and "au diagnostic" in html


def _with_usage(
    *, archive: str | None, resumed: tuple[tuple[str, str], ...] = ()
) -> RunResult:
    from cinoc.domain.usage import ResourceUsage
    from cinoc.evaluation.result import DocumentUsage

    base = _result()
    usage = (
        DocumentUsage(document_id="d1", pipeline="pero",
                      usage=ResourceUsage(duration_seconds=60.0)),
        DocumentUsage(document_id="d2", pipeline="pero",
                      usage=ResourceUsage(duration_seconds=67.0)),
        DocumentUsage(document_id="d1", pipeline="tesseract",
                      usage=ResourceUsage(duration_seconds=2.5)),
        # Une unité en échec n'a rien mesuré : elle ne fait pas une page rapide.
        DocumentUsage(document_id="d2", pipeline="tesseract",
                      usage=ResourceUsage(), outcome="failed", reason="engine"),
    )
    usage = tuple(
        u.model_copy(update={"resumed": (u.pipeline, u.document_id) in resumed})
        for u in usage
    )
    manifest = base.manifest.model_copy(update={"artifacts_dir": archive})
    return base.model_copy(update={"usage": usage, "manifest": manifest})


def test_duration_per_page_is_a_default_column() -> None:
    """Pilote D11 (D-281) : un VLM 25 fois plus lent ne se lisait qu'au mode
    détaillé. La durée par page est au tableau par défaut, triable."""
    html = KeyMeasuresSection().render(_with_usage(archive=None), SectionContext())
    assert html is not None
    assert "s/page ↓" in html and "durée par page" in html
    assert 'data-sort="63.500000">63,5<' in html  # (60 + 67) / 2
    assert 'data-sort="2.500000">2,5<' in html  # l'échec n'est pas compté
    assert "archive de reprise" not in html
    english = KeyMeasuresSection().render(
        _with_usage(archive=None), SectionContext(lang="en")
    )
    assert english is not None and ">63.5<" in english


def test_a_run_with_an_archive_but_nothing_resumed_has_no_inheritance_note() -> None:
    """Le ``RunResult`` dit maintenant quelles unités sont reprises (D10) : une
    archive sans reprise n'appelle plus de note générique."""
    html = KeyMeasuresSection().render(
        _with_usage(archive="archive"), SectionContext()
    )
    assert html is not None and "↺" not in html and "première exécution" not in html


def test_a_resumed_unit_s_duration_is_not_presented_as_measured() -> None:
    """D10 (pilote D-281) : une unité reprise garde la durée de sa première
    exécution. La cellule est marquée, et la note sépare, par pipeline, ce que
    ce run a mesuré de ce qu'il a relu."""
    html = KeyMeasuresSection().render(
        _with_usage(archive="archive", resumed=(("pero", "d1"),)),
        SectionContext(),
    )
    assert html is not None
    assert ">63,5 ↺<" in html  # la valeur reste, marquée
    assert ">2,5<" in html  # tesseract : rien de repris, rien de marqué
    assert "1 mesurée(s) par ce run (67,0 s/page)" in html
    assert "1 reprise(s) de l'archive (60,0 s/page" in html
    assert "première exécution" in html
    english = KeyMeasuresSection().render(
        _with_usage(archive="archive", resumed=(("pero", "d1"),)),
        SectionContext(lang="en"),
    )
    assert english is not None and "1 resumed from the archive" in english


def test_an_offline_rescore_measures_no_duration() -> None:
    """Re-notation ``--offline`` : tout est repris, rien n'est mesuré — le
    rapport le dit au lieu d'afficher des durées comme celles de ce run."""
    every = (("pero", "d1"), ("pero", "d2"), ("tesseract", "d1"), ("tesseract", "d2"))
    html = KeyMeasuresSection().render(
        _with_usage(archive="archive", resumed=every), SectionContext()
    )
    assert html is not None
    assert "aucune durée n'est mesurée par ce run" in html
    assert ">63,5 ↺<" in html and ">2,5 ↺<" in html


def test_no_duration_column_without_measured_durations() -> None:
    html = KeyMeasuresSection().render(_result(), SectionContext())
    assert html is not None and "s/page" not in html and "durée" not in html


def test_each_test_names_the_view_it_judges() -> None:
    """S34b, n° 14 : « différence significative » dans « texte (lignes) », CER
    à 0 dans « texte » — deux tests, deux vues, et rien ne le disait à côté du
    verdict. Plusieurs vues : chaque test nomme la sienne, et le chapeau dit
    qu'un verdict ne vaut que pour sa vue."""
    base = _result(p=0.03)
    lignes = tuple(
        p.model_copy(update={"view": "texte (lignes)"}) for p in base.pipelines
    )
    deux = base.model_copy(update={"pipelines": base.pipelines + lignes})
    fr = KeyMeasuresSection().render(deux, SectionContext())
    en = KeyMeasuresSection().render(deux, SectionContext(lang="en"))
    assert fr is not None and en is not None
    assert "Test inter-moteurs (CER, vue « Texte (lignes) »)" in fr
    assert "ne vaut que pour sa vue" in fr
    assert "Inter-engine test (CER, “Text (lines)” view)" in en
    seule = KeyMeasuresSection().render(base, SectionContext())
    assert seule is not None and "Test inter-moteurs (CER)" in seule
