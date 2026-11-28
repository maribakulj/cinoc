"""Tranche 1b — observations partielles : conservées, jamais jetées (§ 2.1 f).

Révision n° 7 du ``CONTRATS.md`` (arbitrage du 28/11) :
- une observation partielle (axe 3 ``partial_output``) est **conservée** avec
  sa statistique (``stat_partielle``), jamais jetée ni imputée en silence ;
- deux qualités sont publiées pour chaque (pipeline × vue × métrique), avec la
  couverture : **conditionnelle** (observations complètes, par défaut) et
  **opérationnelle** (partielles notées telles que produites, échecs notés
  comme une sortie vide) ;
- l'évaluation **lit** l'état déclaré par l'étape et ne le reconstruit pas à
  partir des textes.

Les valeurs attendues sont calculées à la main (commentaires de chaque test).
Les formes d'API — ``stat_partielle``, ``PipelineResult.operational_aggregate``,
``StepOutput.partial`` — sont fixées dans ``tests/adversarial/_contrat.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.domain.pipeline import PipelineSpec
from cinoc.evaluation.result import RunResult
from tests.adversarial._contrat import (
    agregat_operationnel,
    axes,
    composante_partielle,
    couverture,
    statistique,
    statistique_partielle,
    support_micro,
)
from tests.adversarial.metriques_stats.ms_support import (
    Bench,
    observation,
    view,
)
from tests.adversarial.metriques_stats.ms_support import aggregate as bench_aggregate

from ._kit import (
    T,
    TextBrick,
    aggregate,
    corpus,
    execute,
    fixed,
    per_document,
    pipeline,
    registry_with,
    spec,
    step,
    text_view,
)

pytestmark = [pytest.mark.tranche("1b"), pytest.mark.valide]

#: Référence de cinq mots (14 caractères) : le CER et le sac de mots se
#: calculent à la main sur le même corpus.
REF = "ab cd ef gh ij"
ONE_ERROR = "ab cd ef gh iX"  # 1 substitution ; 4 mots justes sur 5
CUT = "ab cd ef"  # sortie partielle : " gh ij" (6 caractères, 2 mots) jamais produit


def _bench(tmp_path: Path) -> Bench:
    """``p`` : d1 parfait, d2 une substitution, d3 **partiel** (sortie ``CUT``),
    d4 en échec. Toutes les références valent ``REF``."""
    bench = Bench(tmp_path)
    for doc in ("d1", "d2", "d3", "d4"):
        bench.document(doc, REF)
    bench.output("p", "d1", REF)
    bench.output("p", "d2", ONE_ERROR)
    bench.partial("p", "d3", CUT)
    bench.fail("p", "d4")
    return bench


# (métrique, composantes de stat_partielle de d3, conditionnel, opérationnel)
# CER : d3 = 6 suppressions sur 14. Conditionnel = (0 + 1) / (14 + 14) = 1/28 ;
#       opérationnel = (0 + 1 + 6 + 14) / (4 × 14) = 21/56 (l'échec d4 est une
#       sortie vide : 14 suppressions).
# Rappel BoW : d3 retrouve 3 mots sur 5 (tp 3, fp 0, fn 2). Conditionnel =
#       (5 + 4) / (5 + 5) = 9/10 ; opérationnel = (5 + 4 + 3 + 0) / 20 = 3/5.
CAS = [
    pytest.param(
        "cer",
        {"substitutions": 0, "deletions": 6, "insertions": 0, "reference_length": 14},
        1 / 28,
        21 / 56,
        id="cer",
    ),
    pytest.param(
        "bow_recall",
        {"tp": 3, "fp": 0, "fn": 2},
        9 / 10,
        3 / 5,
        id="bow_recall",
    ),
]


@pytest.mark.parametrize(("metric", "partial_stat", "conditional", "operational"), CAS)
def test_f_observation_partielle__conservee_avec_sa_statistique(
    tmp_path: Path,
    metric: str,
    partial_stat: dict[str, int],
    conditional: float,
    operational: float,
) -> None:
    """§ 2.1 f : une observation partielle est **conservée**. d3 (étape déclarée
    partielle, sortie ``CUT``) porte l'axe 3 ``partial_output``, n'a ni ``stat``
    ni scalaire (elle n'est pas notée par défaut) mais garde sa statistique,
    calculée sur ce qui a été produit, dans ``stat_partielle``. d4 (échec) n'a
    rien produit : pas de ``stat_partielle``."""
    result = _bench(tmp_path).run(view([metric]))
    d3 = observation(result, "p", "d3", metric)
    assert axes(d3)[2] == "partial_output"
    assert statistique(d3) is None and d3.value is None
    for nom, attendu in partial_stat.items():
        assert composante_partielle(d3, nom) == attendu, (
            f"stat_partielle.{nom} de la sortie partielle"
        )
    d4 = observation(result, "p", "d4", metric)
    assert statistique_partielle(d4) is None
    d2 = observation(result, "p", "d2", metric)
    assert statistique_partielle(d2) is None, (
        "une observation complète n'a pas de partielle"
    )


@pytest.mark.parametrize(("metric", "partial_stat", "conditional", "operational"), CAS)
def test_f_deux_agregats__conditionnel_et_operationnel_avec_couverture(
    tmp_path: Path,
    metric: str,
    partial_stat: dict[str, int],
    conditional: float,
    operational: float,
) -> None:
    """§ 2.1 f : deux agrégats par (pipeline × vue × métrique). Le conditionnel
    (défaut) ne note que les 2 observations complètes ; l'opérationnel note la
    partielle telle que produite et l'échec comme une sortie vide. La couverture
    — 2 complètes, 1 partielle, 1 en échec, 4 attendues — est publiée à côté des
    deux : ni l'un ni l'autre ne l'améliore sans que la couverture le dise."""
    result = _bench(tmp_path).run(view([metric]))
    cond = bench_aggregate(result, "p", metric)
    assert cond.value == pytest.approx(conditional), "agrégat conditionnel (défaut)"
    assert (support_micro(cond), cond.expected) == (2, 4)
    assert couverture(cond) == {"partial_output": 1, "step_failed": 1}
    oper = agregat_operationnel(result, "p", metric, view="v")
    assert oper.value == pytest.approx(operational), "agrégat opérationnel"
    assert oper.expected == 4
    assert couverture(oper) == {"partial_output": 1, "step_failed": 1}
    assert oper.value != pytest.approx(cond.value), (
        "les deux qualités diffèrent dès qu'une observation est partielle ou en échec"
    )


def test_f_sans_partielle_ni_echec__les_deux_qualites_coincident(
    tmp_path: Path,
) -> None:
    """§ 2.1 f : sans observation partielle ni échec, la qualité opérationnelle
    est la qualité conditionnelle (d1, d2 seuls : CER 1/28), et la couverture
    est complète (2 attendues, 2 mesurées, aucun motif)."""
    bench = Bench(tmp_path)
    for doc in ("d1", "d2"):
        bench.document(doc, REF)
    bench.output("p", "d1", REF)
    bench.output("p", "d2", ONE_ERROR)
    result = bench.run(view(["cer"]))
    cond = bench_aggregate(result, "p", "cer")
    oper = agregat_operationnel(result, "p", "cer", view="v")
    assert cond.value == pytest.approx(1 / 28)
    assert oper.value == pytest.approx(cond.value)
    assert couverture(oper) == {} and oper.expected == 2


# --------------------------------------------------------------------------
# § 2.1 f : l'évaluation lit l'état déclaré par l'étape.
# --------------------------------------------------------------------------

DOC_REF = "abcdefghij"
OCR_TEXT = "abcdefghiX"  # 1 substitution


def _declared_state_run(tmp_path: Path) -> RunResult:
    """Deux pipelines ``ocr → correction`` sur un document.

    - ``identique`` : la correction rend **le texte de sa source** et déclare
      son étape **complète** ;
    - ``complet`` : la correction rend un texte **parfait** (= la référence) et
      déclare son étape **partielle**.
    """
    ocr = TextBrick("ce_ocr", fixed({"a": OCR_TEXT}))
    same = TextBrick(
        "ce_corr_same",
        fixed({"a": OCR_TEXT}),
        in_type=T.RAW_TEXT,
        out_type=T.CORRECTED_TEXT,
    )
    full = TextBrick(
        "ce_corr_full",
        fixed({"a": DOC_REF}),
        in_type=T.RAW_TEXT,
        out_type=T.CORRECTED_TEXT,
        partial=frozenset({"a"}),
    )

    def chain(name: str, corr: str) -> PipelineSpec:
        return pipeline(
            name,
            step("ocr", "ce_ocr"),
            step("corr", corr, in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT),
        )

    return execute(
        spec(
            corpus(tmp_path, {"a": DOC_REF}),
            [chain("identique", "ce_corr_same"), chain("complet", "ce_corr_full")],
            [text_view(candidates=(T.CORRECTED_TEXT,))],
        ),
        registry_with(ocr, same, full),
    )


def test_f_evaluation_lit_letat_declare__etape_complete_texte_identique(
    tmp_path: Path,
) -> None:
    """§ 2.1 f (« l'évaluation lit l'état déclaré, ne le reconstruit jamais ») :
    une correction qui déclare son étape **complète** avec un texte identique à
    sa source donne une observation **complète** (CER noté = 1/10), et non une
    partielle déduite de l'absence de changement."""
    result = _declared_state_run(tmp_path)
    same = per_document(result, "identique", "a")
    assert axes(same) == ("applicable", "available", "valid")
    assert same.value == pytest.approx(0.1)
    assert statistique(same) is not None
    assert aggregate(result, "identique").value == pytest.approx(0.1)


def test_f_evaluation_lit_letat_declare__etape_partielle_texte_complet(
    tmp_path: Path,
) -> None:
    """§ 2.1 f : une correction qui déclare son étape **partielle** avec un
    texte qui est pourtant la référence exacte donne une observation
    **partielle** (axe 3 ``partial_output``, non notée par défaut), et non une
    observation complète déduite du texte. Sa statistique est gardée
    (``stat_partielle`` : 0 édition sur 10 caractères) ; l'unité est
    ``partial`` ; la qualité opérationnelle note le texte produit (CER 0)."""
    result = _declared_state_run(tmp_path)
    partial = per_document(result, "complet", "a")
    assert axes(partial)[2] == "partial_output", (
        "état reconstruit du texte (complet) au lieu de l'état déclaré : "
        f"{axes(partial)}"
    )
    assert partial.value is None and statistique(partial) is None
    assert composante_partielle(partial, "reference_length") == 10
    assert (
        composante_partielle(partial, "substitutions")
        + composante_partielle(partial, "deletions")
        + composante_partielle(partial, "insertions")
    ) == 0
    outcomes = {(u.pipeline, u.document_id): str(u.outcome) for u in result.usage}
    assert outcomes[("complet", "a")] == "partial"
    assert outcomes[("identique", "a")] == "ok"
    assert agregat_operationnel(result, "complet", "cer").value == pytest.approx(0.0)
    cond = aggregate(result, "complet")
    assert cond.value is None and couverture(cond) == {"partial_output": 1}


# --------------------------------------------------------------------------
# § 2.1 f, persistance : l'aller-retour JSON conserve l'état.
# --------------------------------------------------------------------------


def test_f_persistance__aller_retour_json_conserve_partielle_agregats_couverture(
    tmp_path: Path,
) -> None:
    """§ 2.1 f : ``RunResult`` relu depuis son JSON porte toujours
    ``stat_partielle`` de d3, les deux agrégats (1/28 et 21/56) et la
    couverture (2 complètes, 1 partielle, 1 en échec, 4 attendues)."""
    result = _bench(tmp_path).run(view(["cer"]))
    reloaded = RunResult.model_validate_json(result.model_dump_json())
    assert reloaded == result
    d3 = observation(reloaded, "p", "d3", "cer")
    assert axes(d3)[2] == "partial_output"
    assert composante_partielle(d3, "deletions") == 6
    assert composante_partielle(d3, "reference_length") == 14
    cond = bench_aggregate(reloaded, "p", "cer")
    assert cond.value == pytest.approx(1 / 28)
    assert (support_micro(cond), cond.expected) == (2, 4)
    assert couverture(cond) == {"partial_output": 1, "step_failed": 1}
    oper = agregat_operationnel(reloaded, "p", "cer", view="v")
    assert oper.value == pytest.approx(21 / 56) and oper.expected == 4
    assert couverture(oper) == {"partial_output": 1, "step_failed": 1}
