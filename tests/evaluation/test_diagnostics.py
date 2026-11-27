"""Diagnostic : métriques + assemblage — valeurs dérivées **à la main**.

Règle d'ancrage (D-068) : heuristiques maison — chaque valeur
attendue est calculée sur papier, jamais générée en exécutant la source.
"""

from __future__ import annotations

import time

import pytest

from cinoc.evaluation._alignment import char_counts
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.diagnostics import (
    DiagnosticsCollector,
    char_confusions,
    line_cers,
)
from cinoc.evaluation.metrics.diagnostics import searchability, unanchored_trigrams
from cinoc.evaluation.metrics.text import cer
from cinoc.evaluation.result import MetricScore


def _ctx(reference: str, hypothesis: str) -> DocContext:
    return DocContext(document_id="d1", reference=reference, hypothesis=hypothesis)


# --- searchability : rappel de mots, tolérance selon la longueur ----------


def test_searchability_tolerance_grows_with_word_length() -> None:
    # Échelle AUTO de Lucene/Elasticsearch : 0 édition jusqu'à 2 caractères,
    # 1 de 3 à 5, 2 au-delà. « chat »/« chot » (4 car., 1 éd.) retrouvé ;
    # « le »/« la » (2 car., 1 éd.) non ; « seigneur »/« seignuer » (8 car.,
    # 2 éd.) retrouvé ; « chat »/« chut » oui, « chat »/« cbut » (2 éd.) non.
    assert searchability.fn(_ctx("le chat noir", "le chot noir")).value == 1.0  # type: ignore[union-attr]
    obs = searchability.fn(_ctx("le chat", "la chat"))
    assert obs is not None and obs.value == pytest.approx(0.5)
    obs = searchability.fn(_ctx("seigneur", "seignuer"))
    assert obs is not None and obs.value == 1.0
    obs = searchability.fn(_ctx("chat", "cbut"))
    assert obs is not None and obs.value == 0.0


def test_searchability_noise_of_short_words_finds_nothing() -> None:
    """Constat de l'audit (D-264) : à seuil absolu ``≤ 2``, tout mot de deux
    lettres « retrouvait » n'importe quel mot de deux lettres — un bruit
    « xx yy zz… » faisait 0,6 de rappel sur « le roi et la reine… »."""
    gt = "le roi et la reine de la cour du roi"
    obs = searchability.fn(_ctx(gt, "xx yy zz aa bb cc dd ee ff gg"))
    assert obs is not None
    assert obs.value == 0.0
    assert obs.weight == 10


def test_searchability_counts_missing_words() -> None:
    obs = searchability.fn(_ctx("le chat noir", "le xxxxxxx noir"))
    assert obs is not None
    assert obs.value == pytest.approx(2 / 3)


def test_searchability_multiset_one_match_per_occurrence() -> None:
    # Réf : « aa aa » (2 occurrences) ; hyp : « aa » (1 seule) → recall 1/2.
    obs = searchability.fn(_ctx("aa aa", "aa"))
    assert obs is not None
    assert obs.value == pytest.approx(0.5)


def test_searchability_empty_reference_is_not_applicable() -> None:
    assert searchability.fn(_ctx("", "texte")) is None


# --- unanchored_trigrams : trigrammes non ancrés ----------------------------


def test_unanchored_trigrams_zero_when_verbatim() -> None:
    obs = unanchored_trigrams.fn(_ctx("bonjour", "bonjour"))
    assert obs is not None
    assert obs.value == 0.0
    assert obs.weight == 5  # « bonjour » : 7 chars → 5 trigrammes


def test_unanchored_trigrams_hand_computed_on_invented_suffix() -> None:
    # Réf « abcdef » ancre {abc,bcd,cde,def}. Hyp « abcxyz » produit
    # {abc,bcx,cxy,xyz} → 3 non ancrés sur 4 = 0.75.
    obs = unanchored_trigrams.fn(_ctx("abcdef", "abcxyz"))
    assert obs is not None
    assert obs.value == pytest.approx(0.75)
    assert obs.weight == 4


def test_unanchored_trigrams_short_hypothesis_not_applicable() -> None:
    assert unanchored_trigrams.fn(_ctx("abcdef", "ab")) is None


def test_unanchored_trigrams_is_blind_to_a_duplicated_page() -> None:
    """La limite qui a fait retirer le nom ``hallucination`` (D-288) : une page
    recopiée deux fois n'invente aucun trigramme. Le CER le voit (> 1), la
    part non ancrée ne voit que les 3 trigrammes de la jointure sur 141."""
    gt = "Le seigneur Jehan de Montfort donna la terre au prieuré de Saint Martin"
    doubled = gt + " " + gt
    obs = unanchored_trigrams.fn(_ctx(gt, doubled))
    assert obs is not None
    assert obs.weight == len(doubled) - 2
    assert obs.value == pytest.approx(3 / 141)
    assert round(obs.value, 3) == 0.021
    cer_obs = cer.fn(_ctx(gt, doubled))
    assert cer_obs is not None and cer_obs.value > 1.0


# --- confusions de caractères ------------------------------------------------


def test_char_confusions_pairs_replaced_segment_positionally() -> None:
    # « rn » lu « m » n'est pas positionnel ; ici cas simple : e→o deux fois.
    pairs = char_confusions("le chevre", "lo chovre")
    assert pairs[("e", "o")] == 2


def test_char_confusions_counts_what_the_cer_counts_on_unrelated_spans() -> None:
    # Deux textes sans mot commun : le CER y compte des substitutions, les
    # confusions aussi (D-286). L'ancien alignement ``difflib`` écartait les
    # empans de plus de 2 000 caractères — des erreurs comptées, mais tues.
    gauche = " ".join(f"alpha{i}" for i in range(400))
    droite = " ".join(f"zeta{i}" for i in range(400))
    pairs = char_confusions(gauche, droite)
    assert sum(pairs.values()) == char_counts(gauche, droite)[0]
    assert pairs[("a", "z")] == 400


def test_char_confusions_tient_sur_une_page_entiere() -> None:
    """Garde-fou de complexité : l'alignement est fait sur les mots, pas sur
    les caractères. À granularité caractère, une page de presse (~40 000
    caractères, <100 symboles distincts) prenait ~30 s ; ce test la borne.
    """
    mots = [f"mot{i:05d}" for i in range(6000)]
    reference = " ".join(mots)
    # Une césure typographique mal rendue, une fois sur dix.
    hypothese = " ".join(m.replace("0", "O") if i % 10 == 0 else m
                         for i, m in enumerate(mots))
    assert len(reference) > 40_000
    depart = time.perf_counter()
    pairs = char_confusions(reference, hypothese)
    assert time.perf_counter() - depart < 5.0
    assert pairs[("0", "O")] > 0


def test_line_cers_hand_computed() -> None:
    lines = line_cers("abcd\nefgh", "abxd\nefgh")
    # Ligne 0 : 1 édition / 4 chars = 0.25 ; ligne 1 : 0.
    assert lines == [(0, 0.25, "abcd", "abxd"), (1, 0.0, "efgh", "efgh")]


def test_line_cers_missing_hypothesis_line_is_full_error() -> None:
    lines = line_cers("abcd\nefgh", "abcd")
    assert lines[1] == (1, 1.0, "efgh", "")


# --- assemblage --------------------------------------------------------------


def test_collector_builds_sorted_payload() -> None:
    collector = DiagnosticsCollector()
    collector.observe("alpha", "d1", "abcd\nefgh", "abxd\nefgh")
    collector.observe("beta", "d1", "abcd\nefgh", "xxxx\nefgh")
    analysis = collector.build(
        "text",
        "cer",
        ["d1"],
        {
            "alpha": [MetricScore(metric="cer", value=0.125, support=8)],
            "beta": [MetricScore(metric="cer", value=0.5, support=8)],
        },
    )
    assert analysis is not None
    payload = analysis.payload
    assert payload.kind == "diagnostics"
    # Pire ligne d'abord : beta ligne 0 (CER 1.0) avant alpha ligne 0 (0.25).
    assert payload.worst_lines[0].pipeline == "beta"
    assert payload.worst_lines[0].cer == pytest.approx(1.0)
    assert payload.worst_lines[1].pipeline == "alpha"
    # Confusions triées par pipeline ; alpha : c→x une fois.
    assert payload.confusions[0].pipeline == "alpha"
    assert payload.confusions[0].pairs[0].count == 1
    # Difficulté : moyenne des CER des pipelines scorés.
    assert payload.hardest_documents[0].mean_cer == pytest.approx(0.3125)
    assert payload.hardest_documents[0].n_pipelines == 2


def test_collector_without_observation_yields_none() -> None:
    assert DiagnosticsCollector().build("text", "cer", [], {}) is None


def test_payload_is_deterministic() -> None:
    def build() -> str:
        collector = DiagnosticsCollector()
        collector.observe("alpha", "d1", "abcd", "abxd")
        analysis = collector.build(
            "text", "cer", ["d1"],
            {"alpha": [MetricScore(metric="cer", value=0.25, support=4)]},
        )
        assert analysis is not None
        return analysis.model_dump_json()

    assert build() == build()
