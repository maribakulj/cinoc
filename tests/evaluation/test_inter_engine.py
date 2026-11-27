"""Inter-moteurs : JSD (valeurs main), oracle multiset (valeurs main), R10, caps.

Toutes les valeurs attendues sont **dérivées à la main** (règle D-068) :
- JSD : formule ``½·KL(P‖M) + ½·KL(Q‖M)`` en base 2 posée sur des
  distributions courtes (``log2(1.5) = 0.5849625007211562``) ;
- oracle : multisets min/max comptés à la main sur 2 moteurs courts.
"""

from __future__ import annotations

import pytest

from cinoc.evaluation.analysis import (
    Analysis,
    InterEnginePayload,
    PipelineTaxonomy,
    TaxonomyCount,
    TaxonomyPayload,
)
from cinoc.evaluation.inter_engine import (
    InterEngineCollector,
    jensen_shannon_divergence,
)

# JS({case: ¾, visual: ¼}, {case: ¼, visual: ¾}) — à la main :
# M = (½, ½) ; KL(P‖M) = ¾·log2(1.5) + ¼·log2(0.5)
#             = 0.75 × 0.5849625007211562 − 0.25 = 0.18872187554086715 ;
# KL(Q‖M) identique par symétrie → JS = 0.18872187554086715.
_JS_THREE_QUARTERS = 0.18872187554086715


def _taxonomy(rows: dict[str, dict[str, int]]) -> Analysis:
    """Analyse ``taxonomy`` témoin (mêmes formes que ``TaxonomyCollector``)."""
    pipelines = tuple(
        PipelineTaxonomy(
            pipeline=name,
            total_errors=sum(counts.values()),
            counts=tuple(
                TaxonomyCount(label=label, count=count)
                for label, count in counts.items()
            ),
        )
        for name, counts in sorted(rows.items())
    )
    payload = TaxonomyPayload(classes=("case", "visual"), pipelines=pipelines)
    return Analysis(scope="corpus", view="text", payload=payload)


class TestJensenShannonDivergence:
    def test_identical_distributions_yield_zero(self) -> None:
        p = {"case": 0.5, "visual": 0.5}
        assert jensen_shannon_divergence(p, dict(p)) == 0.0

    def test_disjoint_distributions_saturate_at_one_bit(self) -> None:
        js = jensen_shannon_divergence({"a": 1.0}, {"b": 1.0})
        assert js == pytest.approx(1.0, abs=1e-9)
        assert js <= 1.0  # clamp : jamais au-dessus de la borne théorique

    def test_hand_derived_three_quarters_split(self) -> None:
        js = jensen_shannon_divergence(
            {"case": 0.75, "visual": 0.25}, {"case": 0.25, "visual": 0.75}
        )
        assert js == pytest.approx(_JS_THREE_QUARTERS, abs=1e-12)

    def test_symmetric(self) -> None:
        p = {"case": 0.9, "visual": 0.1}
        q = {"case": 0.2, "lacuna": 0.8}
        assert jensen_shannon_divergence(p, q) == pytest.approx(
            jensen_shannon_divergence(q, p), abs=1e-15
        )

    def test_empty_distributions_yield_zero(self) -> None:
        assert jensen_shannon_divergence({}, {}) == 0.0


class TestComplementarity:
    def test_oracle_and_gaps_hand_derived(self) -> None:
        # GT = 4 tokens. alpha en rattrape 3 (0.75), beta 2 (0.5) ; chaque
        # token est rattrapé par au moins un moteur → oracle = 1.0 ;
        # absolute_gap = 0.25 ; relative_gap = 0.25 / (1 − 0.75) = 1.0.
        collector = InterEngineCollector()
        collector.observe("alpha", "d1", "le chat noir dort", "le chat noir")
        collector.observe("beta", "d1", "le chat noir dort", "le dort dort")
        analysis = collector.build("text", None)
        assert analysis is not None
        assert analysis.scope == "corpus" and analysis.view == "text"
        payload = analysis.payload
        assert isinstance(payload, InterEnginePayload)
        assert payload.taxonomy_divergence is None
        comp = payload.complementarity
        assert comp is not None
        assert comp.n_documents == 1 and comp.n_reference_tokens == 4
        assert comp.oracle_recall == 1.0
        assert comp.best_engine == "alpha"
        assert comp.best_single_recall == 0.75
        assert comp.absolute_gap == 0.25
        assert comp.relative_gap == pytest.approx(1.0)
        recalls = {r.pipeline: r.recall for r in comp.per_engine_recall}
        assert recalls == {"alpha": 0.75, "beta": 0.5}
        (document,) = comp.per_document
        assert document.document_id == "d1"
        assert document.oracle_recall == 1.0
        assert document.best_single_recall == 0.75
        assert document.absolute_gap == 0.25

    def test_multiset_multiplicity_and_lexicographic_tie_break(self) -> None:
        # GT {a:2, b:1} (3 occ.). alpha « a b b » → min(2,1)+min(1,2) = 2 ;
        # beta « a a » → min(2,2) = 2 — égalité 2/3 : le nom le plus petit
        # gagne. Oracle : a → max(1,2)=2 ; b → max(1,0)=1 → 3/3 = 1.0.
        collector = InterEngineCollector()
        collector.observe("beta", "d1", "a a b", "a a")
        collector.observe("alpha", "d1", "a a b", "a b b")
        analysis = collector.build("text", None)
        assert analysis is not None
        comp = analysis.payload.complementarity
        assert comp is not None
        assert comp.best_engine == "alpha"
        assert comp.best_single_recall == pytest.approx(2 / 3)
        assert comp.oracle_recall == 1.0
        assert comp.absolute_gap == pytest.approx(1 / 3)
        assert comp.relative_gap == pytest.approx(1.0)

    def test_r10_empty_ground_truth_yields_none_not_one(self) -> None:
        # R10 : GT sans token (vide ou ponctuation seule) → analyse absente —
        # jamais un rappel 1.0 (la convention de la source est réparée).
        collector = InterEngineCollector()
        collector.observe("alpha", "d1", "", "du texte produit")
        collector.observe("beta", "d1", "…!!!", "autre texte")
        assert collector.build("text", None) is None

    def test_r10_empty_gt_document_excluded_from_denominator(self) -> None:
        collector = InterEngineCollector()
        for name, hyp in (("alpha", "roi"), ("beta", "loi")):
            collector.observe(name, "d_vide", "", hyp)
            collector.observe(name, "d_plein", "roi", hyp)
        analysis = collector.build("text", None)
        assert analysis is not None
        comp = analysis.payload.complementarity
        assert comp is not None
        # Seul d_plein compte : 1 token GT, alpha le rattrape, beta non.
        assert comp.n_documents == 1 and comp.n_reference_tokens == 1
        assert {d.document_id for d in comp.per_document} == {"d_plein"}
        assert comp.best_engine == "alpha" and comp.oracle_recall == 1.0

    def test_single_pipeline_yields_no_analysis(self) -> None:
        collector = InterEngineCollector()
        collector.observe("alpha", "d1", "le roi", "le roi")
        assert collector.build("text", None) is None

    def test_per_document_sample_is_capped_and_sorted(self) -> None:
        # 25 documents au même écart (0.5) → 20 embarqués (cap explicite),
        # tri (−gap, document_id) → d00…d19.
        collector = InterEngineCollector()
        for i in range(25):
            doc = f"d{i:02d}"
            collector.observe("alpha", doc, "x y", "x")
            collector.observe("beta", doc, "x y", "y")
        analysis = collector.build("text", None)
        assert analysis is not None
        comp = analysis.payload.complementarity
        assert comp is not None
        assert comp.n_documents == 25
        assert len(comp.per_document) == 20
        assert [d.document_id for d in comp.per_document] == [
            f"d{i:02d}" for i in range(20)
        ]
        assert comp.per_document[0].absolute_gap == 0.5
        assert comp.oracle_recall == 1.0 and comp.best_single_recall == 0.5

    def test_pipeline_without_output_on_a_document_costs_recall(self) -> None:
        # beta n'a de sortie que sur d1 : sur d2 il ne préserve rien (l'échec
        # n'est pas neutralisé), le dénominateur reste le corpus entier.
        collector = InterEngineCollector()
        collector.observe("alpha", "d1", "un roi", "un roi")
        collector.observe("beta", "d1", "un roi", "un roi")
        collector.observe("alpha", "d2", "deux lois", "deux lois")
        analysis = collector.build("text", None)
        assert analysis is not None
        comp = analysis.payload.complementarity
        assert comp is not None
        recalls = {r.pipeline: r.recall for r in comp.per_engine_recall}
        assert recalls == {"alpha": 1.0, "beta": 0.5}


class TestTaxonomyDivergence:
    def test_pair_from_taxonomy_counts_hand_derived(self) -> None:
        # alpha {case:3, visual:1} → (¾, ¼) ; beta {case:1, visual:3} →
        # (¼, ¾) — divergence dérivée à la main (cf. _JS_THREE_QUARTERS).
        # Collecteur mono-pipeline : payload à divergence seule.
        collector = InterEngineCollector()
        collector.observe("alpha", "d1", "le roi", "le roy")
        taxonomy = _taxonomy(
            {"alpha": {"case": 3, "visual": 1}, "beta": {"case": 1, "visual": 3}}
        )
        analysis = collector.build("text", taxonomy)
        assert analysis is not None
        payload = analysis.payload
        assert isinstance(payload, InterEnginePayload)
        assert payload.complementarity is None  # < 2 pipelines observés
        divergence = payload.taxonomy_divergence
        assert divergence is not None
        (pair,) = divergence.pairs
        assert (pair.a, pair.b) == ("alpha", "beta")
        assert pair.divergence == pytest.approx(_JS_THREE_QUARTERS, abs=1e-9)
        assert divergence.max_pair == pair

    def test_identical_profiles_have_no_max_pair(self) -> None:
        collector = InterEngineCollector()
        taxonomy = _taxonomy({"alpha": {"case": 2}, "beta": {"case": 5}})
        analysis = collector.build("text", taxonomy)
        assert analysis is not None
        divergence = analysis.payload.taxonomy_divergence
        assert divergence is not None
        (pair,) = divergence.pairs
        assert pair.divergence == 0.0
        assert divergence.max_pair is None  # profils identiques : rien à nommer

    def test_three_engines_yield_sorted_upper_triangle(self) -> None:
        taxonomy = _taxonomy(
            {
                "alpha": {"case": 4},
                "beta": {"visual": 4},
                "gamma": {"case": 2, "visual": 2},
            }
        )
        analysis = InterEngineCollector().build("text", taxonomy)
        assert analysis is not None
        divergence = analysis.payload.taxonomy_divergence
        assert divergence is not None
        assert [(p.a, p.b) for p in divergence.pairs] == [
            ("alpha", "beta"),
            ("alpha", "gamma"),
            ("beta", "gamma"),
        ]
        # alpha/beta disjoints → la paire la plus divergente (≈ 1 bit).
        assert divergence.max_pair is not None
        assert (divergence.max_pair.a, divergence.max_pair.b) == ("alpha", "beta")
        assert divergence.max_pair.divergence == pytest.approx(1.0, abs=1e-9)

    def test_single_taxonomy_pipeline_yields_no_divergence(self) -> None:
        collector = InterEngineCollector()
        collector.observe("alpha", "d1", "le roi", "le roi")
        collector.observe("beta", "d1", "le roi", "le roy")
        taxonomy = _taxonomy({"beta": {"case": 1}})
        analysis = collector.build("text", taxonomy)
        assert analysis is not None
        assert analysis.payload.taxonomy_divergence is None
        assert analysis.payload.complementarity is not None

    def test_no_signal_at_all_yields_none(self) -> None:
        assert InterEngineCollector().build("text", None) is None
