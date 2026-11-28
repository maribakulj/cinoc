"""Tranche 1b — verdicts exploratoires et chemins d'alignement (révision n° 7).

**Verdicts de l'ancienne inférence** (§ 2.1 d). Jusqu'à la tranche I, aucun
verdict n'est confirmatoire : tout résultat de test produit par l'ancienne
inférence est étiqueté **exploratoire** dans le rapport et dans le ``RunResult``,
et le mot « significatif » n'est plus employé comme verdict. Les p brutes et
corrigées restent publiées **comme nombres**. Périmètre (inventaire du 28/11) :
tests inter-moteurs (sections ``cross_engine`` et ``key_measures``,
``_inference_text``) ; scalaire ``significance_p`` ; tendances de l'historique
web (couvertes par ``tests/interfaces/web/test_history_trends.py``).

**Chemins d'alignement** (§ 2.1 a, § 6.2). Les confusions et la taxonomie
gardent *temporairement* le chemin RapidFuzz ; la convention est inscrite dans
chaque résultat (``alignment_path: "rapidfuzz"``, contre ``"canonical"`` pour les
comptes), et le résultat ne prétend pas décomposer les comptes canoniques quand
leur ventilation S/D/I diverge (« ab » → « ba » : canonique (2, 0, 0),
RapidFuzz (0, 1, 1)).

Formes d'API fixées dans ``tests/adversarial/_contrat.py`` : ``status``,
``alignment_path``, ``matches_canonical_counts``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    DiagnosticsPayload,
    InferencePayload,
    PairwiseDifference,
    PipelineRank,
    TaxonomyPayload,
)
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.reports.section import SectionContext
from cinoc.reports.sections import _inference_text as inference_text
from cinoc.reports.sections.cross_engine import CrossEngineSection
from cinoc.reports.sections.key_measures import KeyMeasuresSection
from tests.adversarial._contrat import (
    chemin_alignement,
    concordance_canonique,
    etiquette_exploratoire,
    statistique,
    statut_inference,
    verdicts,
)
from tests.adversarial.metriques_stats.ms_support import (
    Bench,
    inference,
    letters,
    observation,
    substitute,
    view,
)
from tests.adversarial.metriques_stats.ms_support import aggregate as bench_aggregate

pytestmark = [pytest.mark.tranche("1b"), pytest.mark.valide]

FIXED = datetime(2026, 1, 1, tzinfo=UTC)

# --------------------------------------------------------------------------
# Le payload d'inférence porte le statut ``exploratory`` (RunResult).
# --------------------------------------------------------------------------


def _inference_bench(tmp_path: Path, errors: dict[str, list[int]]) -> Bench:
    """Huit documents de 100 caractères ; ``errors[nom][i]`` substitutions."""
    bench = Bench(tmp_path)
    for i in range(8):
        reference = letters(100, seed=i + 1)
        bench.document(f"d{i + 1}", reference)
        for name, counts in errors.items():
            bench.output(name, f"d{i + 1}", substitute(reference, counts[i]))
    return bench


A = [1, 2, 1, 3, 2, 1, 2, 3]
B = [0, 1, 0, 2, 1, 0, 1, 2]  # B fait une erreur de moins que A, partout
C = [2, 3, 2, 4, 3, 2, 3, 4]


@pytest.mark.parametrize(
    ("errors", "test"),
    [
        pytest.param({"A": A, "B": B}, "wilcoxon", id="wilcoxon"),
        pytest.param({"A": A, "B": B, "C": C}, "friedman", id="friedman"),
    ],
)
def test_exploratoire__le_payload_dinference_porte_son_statut(
    tmp_path: Path, errors: dict[str, list[int]], test: str
) -> None:
    """Rév. 7, § 2.1 d : tout résultat de test de l'ancienne inférence est
    étiqueté ``exploratory`` dans le ``RunResult`` (payload ``inference``). Les
    p brute et corrigée restent publiées comme **nombres** (ici A et B diffèrent
    du même signe sur les 8 documents : Wilcoxon exact p = 2/2⁸ = 0,0078125), et
    le statut survit à l'aller-retour JSON."""
    result = _inference_bench(tmp_path, errors).run(view(["cer"]))
    payload = inference(result, "cer")
    assert payload.test == test, "le contre-exemple doit produire un test calculé"
    assert payload.p_value is not None and payload.p_holm is not None
    if test == "wilcoxon":
        assert payload.p_value == pytest.approx(2 / 2**8)
    assert statut_inference(payload) == "exploratory"
    reloaded = RunResult.model_validate_json(result.model_dump_json())
    assert statut_inference(inference(reloaded, "cer")) == "exploratory"


# --------------------------------------------------------------------------
# Aucun libellé de verdict dans les sections et dans le texte d'inférence.
# --------------------------------------------------------------------------


def _wilcoxon(p: float, p_holm: float, family: int) -> InferencePayload:
    return InferencePayload(
        metric="cer",
        alpha=0.05,
        n_documents=10,
        test="wilcoxon",
        p_value=p,
        p_holm=p_holm,
        family_size=family,
        mean_ranks=(
            PipelineRank(pipeline="alpha", mean_rank=1.2),
            PipelineRank(pipeline="beta", mean_rank=1.8),
        ),
    )


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
            PairwiseDifference(a="alpha", b="beta", rank_gap=0.8, significant=False),
            PairwiseDifference(a="alpha", b="gamma", rank_gap=1.6, significant=True),
            PairwiseDifference(a="beta", b="gamma", rank_gap=0.8, significant=False),
        ),
    )
    return payload.model_copy(update=update)


#: nom → (payload, p brute, p corrigée, test calculé ?). Un test non calculé
#: n'a jamais porté de verdict : il n'entre pas dans ces contre-exemples.
CASES: dict[str, tuple[InferencePayload, float, float, bool]] = {
    "wilcoxon_corrigee_sous_alpha": (_wilcoxon(0.03, 0.03, 1), 0.03, 0.03, True),
    "wilcoxon_corrigee_au_dessus": (_wilcoxon(0.03, 0.21, 7), 0.03, 0.21, True),
    "friedman_rejete_avec_paires": (_friedman(), 0.0017, 0.0017, True),
    "friedman_non_rejete": (
        _friedman(
            p_value=0.0572,
            p_holm=0.343,
            family_size=7,
            critical_distance=None,
            q_alpha=None,
            cd_groups=(),
            pairwise=(),
        ),
        0.0572,
        0.343,
        True,
    ),
}


def _pipe(name: str, cer: float) -> PipelineResult:
    return PipelineResult(
        pipeline=name,
        view="text",
        aggregate=(
            MetricScore(metric="cer", value=cer, support=900),
            MetricScore(metric="wer", value=round(cer * 2, 4), support=160),
        ),
    )


def _run_result(payload: InferencePayload) -> RunResult:
    """Un run dont l'inférence est ``payload`` : les deux sections la lisent."""
    names = [r.pipeline for r in payload.mean_ranks] or ["alpha", "beta"]
    cross = (
        (
            MetricScore(
                metric="text:cer:significance_p", value=payload.p_value, support=10
            ),
        )
        if payload.p_value is not None
        else (MetricScore(metric="text:cer:significance_p", value=None, support=3),)
    )
    return RunResult(
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=10,
            code_version="1.0",
            started_at=FIXED,
            completed_at=FIXED,
        ),
        pipelines=tuple(_pipe(n, 0.05 + 0.01 * i) for i, n in enumerate(names)),
        cross_engine=cross,
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )


def _decimal(value: float, lang: str) -> str:
    text = f"{value:.4f}"
    return text.replace(".", ",") if lang == "fr" else text


@pytest.mark.parametrize("lang", ["fr", "en"])
@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("section", [CrossEngineSection, KeyMeasuresSection])
def test_exploratoire__aucun_libelle_de_verdict_dans_les_sections(
    section: type, case: str, lang: str
) -> None:
    """Rév. 7, § 2.1 d : ni « significatif / significative(s) » (FR), ni
    « significant » (EN) — ni « non sig. » — n'est employé comme verdict dans
    ``cross_engine`` et ``key_measures``, quel que soit le résultat du test ; les
    p brute et corrigée y restent écrites comme nombres, et un test calculé
    porte l'étiquette « exploratoire » (FR) / « exploratory » (EN)."""
    payload, p, p_holm, computed = CASES[case]
    html = section().render(_run_result(payload), SectionContext(lang=lang))
    assert html is not None
    employes = verdicts(html)
    assert not employes, f"libellé de verdict employé : {employes}"
    if computed:
        assert _decimal(p, lang) in html and _decimal(p_holm, lang) in html
        assert etiquette_exploratoire(html, lang)


@pytest.mark.parametrize("lang", ["fr", "en"])
@pytest.mark.parametrize("case", ["friedman_rejete_avec_paires", "friedman_non_rejete"])
def test_exploratoire__le_texte_dinference_n_emploie_aucun_verdict(
    case: str, lang: str
) -> None:
    """Rév. 7 : le texte partagé (``_inference_text``) — étiquette du test, motif
    d'absence, phrase du post-hoc (propre au Friedman) — n'emploie aucun libellé
    de verdict, FR et EN.
    Le post-hoc de Nemenyi nomme toujours la paire que la distance critique
    sépare (alpha – gamma), comme paire, sans la dire « significative »."""
    payload, _, _, _ = CASES[case]
    texts = [
        inference_text.omnibus_label(payload, lang),
        inference_text.reason_text(payload, lang),
        inference_text.posthoc_text(payload, lang),
    ]
    for text in texts:
        assert not verdicts(text), text
    if case == "friedman_rejete_avec_paires":
        assert "alpha – gamma" in texts[2]
    if case == "friedman_non_rejete":
        # Le motif de l'absence de post-hoc reste dit, sans verdict.
        assert texts[2] != ""
        assert ("Nemenyi" in texts[2]) is True


# --------------------------------------------------------------------------
# Chemins d'alignement : ``alignment_path`` et concordance avec les comptes.
# --------------------------------------------------------------------------


def _payload(result: RunResult, kind: type) -> object:
    (found,) = [a.payload for a in result.analyses if isinstance(a.payload, kind)]
    return found


def _single(tmp_path: Path, reference: str, hypothesis: str) -> RunResult:
    bench = Bench(tmp_path)
    bench.document("d", reference)
    bench.output("p", "d", hypothesis)
    return bench.run(view(["cer", "wer"]))


def test_alignement__confusions_et_taxonomie_portent_leur_chemin(
    tmp_path: Path,
) -> None:
    """Rév. 7 : les analyses qualitatives qui nomment des éditions gardent le
    chemin RapidFuzz *et le disent* : ``alignment_path == "rapidfuzz"`` dans les
    résultats « confusions » (``diagnostics``) et « taxonomie »."""
    result = _single(tmp_path, "abc def", "abd dex")
    assert chemin_alignement(_payload(result, DiagnosticsPayload)) == "rapidfuzz"
    assert chemin_alignement(_payload(result, TaxonomyPayload)) == "rapidfuzz"


def test_alignement__les_comptes_portent_la_convention_canonique(
    tmp_path: Path,
) -> None:
    """Rév. 7 : les comptes S/D/I (statistique d'édition du CER et du WER, et leur
    agrégat) portent la convention ``alignment_path == "canonical"``."""
    result = _single(tmp_path, "abc def", "abd dex")
    for metric in ("cer", "wer"):
        assert chemin_alignement(
            statistique(observation(result, "p", "d", metric))
        ) == ("canonical")
        assert chemin_alignement(statistique(bench_aggregate(result, "p", metric))) == (
            "canonical"
        )


def test_alignement__confusions_sans_concordance_quand_les_comptes_divergent(
    tmp_path: Path,
) -> None:
    """Rév. 7, contre-exemple « ab » → « ba » : les comptes canoniques sont
    (S, D, I) = (2, 0, 0) (distance 2, S maximal) ; l'alignement RapidFuzz est
    (0, 1, 1) et ne nomme **aucune** substitution. L'analyse « confusions » ne
    prétend donc pas décomposer les S du CER : l'indicateur de concordance vaut
    faux."""
    result = _single(tmp_path, "ab", "ba")
    cer = statistique(observation(result, "p", "d", "cer"))
    assert (cer.substitutions, cer.deletions, cer.insertions) == (2, 0, 0)
    diagnostics = _payload(result, DiagnosticsPayload)
    assert concordance_canonique(diagnostics) is False


def test_alignement__taxonomie_sans_concordance_quand_les_comptes_divergent(
    tmp_path: Path,
) -> None:
    """Rév. 7, même contre-exemple sur les mots : « a b » → « b a ». Le WER
    canonique est (2, 0, 0) ; l'alignement RapidFuzz sépare une suppression et
    une insertion (« lacuna » 1, « insertion » 1). La taxonomie, qui range les D
    et I du WER en « lacuna » et « insertion », ne les décompose donc pas : sa
    concordance vaut faux."""
    result = _single(tmp_path, "a b", "b a")
    wer = statistique(observation(result, "p", "d", "wer"))
    assert (wer.substitutions, wer.deletions, wer.insertions) == (2, 0, 0)
    assert concordance_canonique(_payload(result, TaxonomyPayload)) is False


def test_alignement__concordance_vraie_quand_la_ventilation_est_la_meme(
    tmp_path: Path,
) -> None:
    """Rév. 7 (lecture directe de « concordance ») : sans ex æquo d'alignement
    — « abc » → « abd », « abc def » → « abc dex », une substitution —, la
    ventilation de l'analyse est celle des comptes canoniques, et l'indicateur
    vaut vrai (il n'est pas faux par défaut)."""
    result = _single(tmp_path, "abc def", "abc dex")
    assert concordance_canonique(_payload(result, DiagnosticsPayload)) is True
    assert concordance_canonique(_payload(result, TaxonomyPayload)) is True
