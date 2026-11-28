"""Affirmation 1 — contrat mathématique des métriques et de leur agrégation.

Importé de la contre-expertise (``metriques_stats/test_ms_aggregation.py``,
commit ``04a1c17b``) : seuls les tests que ``CONTRATS.md`` § 4.1 range en
tranches 1a et 1b. Les valides sont tels quels ; les trois discutables
« plancher des exactitudes » (C02) sont reformulés selon B1 : plancher au
niveau du corpus, comptes et taux d'erreur non tronqué publiés à côté.

Chaque test construit un corpus minimal, passe par ``evaluate_run`` (agrégat
réel du ``RunResult``) et compare à un calcul indépendant fait à la main sur
les statistiques suffisantes (numérateur, dénominateur ; ou TP/FP/FN).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.evaluation.analysis import NerPayload
from tests.adversarial._contrat import composantes, taux_non_tronque
from tests.adversarial.metriques_stats.ms_support import (
    Bench,
    aggregate,
    entities_json,
    layout_json,
    prf_f1,
    view,
)

HALLUCINATION = "Lorem ipsum dolor sit amet hallucinated page"  # 44 car., 7 mots

B1 = pytest.mark.discutable("C02-plancher-exactitudes")
VALIDE_1A = (pytest.mark.valide, pytest.mark.tranche("1a"))


def _blank_page_bench(tmp_path: Path) -> Bench:
    bench = Bench(tmp_path)
    bench.document("a", "abcdefghij")  # 10 car., 1 mot
    bench.document("blank", "")  # page blanche : vérité terrain vide
    bench.output("p", "a", "abcdefghij")  # parfait
    bench.output("p", "blank", HALLUCINATION)  # page entière inventée
    return bench


# --- Références vides ------------------------------------------------------


@pytest.mark.parametrize(
    ("metric", "expected", "comptes"),
    [
        # Σ éditions / Σ longueurs de référence = (0 + 44) / (10 + 0)
        pytest.param("cer", 44 / 10, None, marks=VALIDE_1A, id="cer-4.4"),
        # Σ éditions mot / Σ mots de référence = (0 + 7) / (1 + 0)
        pytest.param("wer", 7 / 1, None, marks=VALIDE_1A, id="wer-7.0"),
        # Σ insertions mot / Σ mots de référence = (0 + 7) / 1
        pytest.param("ins_rate", 7 / 1, None, marks=VALIDE_1A, id="ins_rate-7.0"),
        # B1 : max(0, 1 − 44/10) au niveau du corpus ; (44, 10) et 4,4 publiés
        pytest.param(
            "char_accuracy",
            0.0,
            (44, 10),
            marks=(B1, pytest.mark.tranche("1a")),
            id="char_accuracy-0.0",
        ),
        # B1 : max(0, 1 − Σ erreurs / Σ car. de réf.) = max(0, 1 − 44/10)
        pytest.param(
            "fca", 0.0, (44, 10), marks=(B1, pytest.mark.tranche("1a")), id="fca-0.0"
        ),
    ],
)
def test_reference_vide__hallucination_comptee_au_numerateur(
    tmp_path: Path, metric: str, expected: float, comptes: tuple[int, int] | None
) -> None:
    """Page blanche (GT vide) + 44 car. inventés : les erreurs doivent entrer
    dans Σ erreurs du corpus. Pour une exactitude (B1), le plancher s'applique
    au corpus, et ses comptes (Σe, Σn) et son taux non tronqué Σe/Σn sont
    publiés à côté de la valeur."""
    result = _blank_page_bench(tmp_path).run(view([metric]))
    score = aggregate(result, "p", metric)
    assert score.value == pytest.approx(expected)
    if comptes is not None:
        assert composantes(score, "errors", "reference_length") == comptes
        assert taux_non_tronque(score) == pytest.approx(comptes[0] / comptes[1])


@pytest.mark.valide
@pytest.mark.tranche("1a")
def test_reference_vide__pipeline_qui_hallucine_est_classe_apres(
    tmp_path: Path,
) -> None:
    """H invente 44 car. sur la page blanche et lit « a » parfaitement ; S se tait sur
    la blanche et fait 1 erreur sur « a » : H doit avoir le pire CER."""
    bench = Bench(tmp_path)
    bench.document("a", "abcdefghij")
    bench.document("blank", "")
    bench.output("H", "a", "abcdefghij")
    bench.output("H", "blank", HALLUCINATION)
    bench.output("S", "a", "0bcdefghij")
    bench.output("S", "blank", "")
    result = bench.run(view(["cer"]))
    h, s = aggregate(result, "H", "cer").value, aggregate(result, "S", "cer").value
    # Référence : H = 44/10 = 4,4 ; S = 1/10 = 0,1.
    assert (h, s) == pytest.approx((4.4, 0.1))


# --- F1 et ratios non linéaires -------------------------------------------
#
# Agrégation NER et régions (tranche 1a, M3) sur des appariements sans
# ambiguïté ; l'appariement (M8) est jugé en tranche 4.


def _ner_bench(tmp_path: Path) -> Bench:
    """d1 : 1 entité GT trouvée + 9 faux positifs ; d2 : 10 entités GT, toutes
    trouvées."""
    bench = Bench(tmp_path, gt_type=ArtifactType.ENTITIES)
    t1 = "Marie a b c d e f g h i"
    bench.document("d1", entities_json(t1, [("PER", 0, 5)]))
    fps = [("PER", 6 + 2 * i, 7 + 2 * i) for i in range(9)]
    bench.output("p", "d1", entities_json(t1, [("PER", 0, 5), *fps]))
    t2 = " ".join(f"N{i}" for i in range(10))
    spans2 = [("PER", 3 * i, 3 * i + 2) for i in range(10)]
    bench.document("d2", entities_json(t2, spans2))
    bench.output("p", "d2", entities_json(t2, spans2))
    return bench


@pytest.mark.valide
@pytest.mark.tranche("1a")
@pytest.mark.parametrize("metric", ["ner_f1", "ner_f1_exact"])
def test_ner_f1__micro_sur_tp_fp_fn(tmp_path: Path, metric: str) -> None:
    """Comptes déséquilibrés (d1 : TP1 FP9 ; d2 : TP10) : le F1 corpus est F1(ΣTP=11,
    ΣFP=9, ΣFN=0)."""
    result = _ner_bench(tmp_path).run(view([metric], ArtifactType.ENTITIES))
    expected = prf_f1(tp=11, fp=9, fn=0)  # 22/31 ≈ 0,7097
    assert aggregate(result, "p", metric).value == pytest.approx(expected)


@pytest.mark.valide
@pytest.mark.tranche("1a")
def test_ner_f1__faux_positifs_sur_document_sans_entite_gt(tmp_path: Path) -> None:
    """d1 : 2 entités GT trouvées ; d2 : GT sans entité, 8 entités inventées : F1 corpus
    = F1(2, 8, 0) = 1/3."""
    bench = Bench(tmp_path, gt_type=ArtifactType.ENTITIES)
    t1 = "Jean Paul"
    spans = [("PER", 0, 4), ("PER", 5, 9)]
    bench.document("d1", entities_json(t1, spans))
    bench.output("p", "d1", entities_json(t1, spans))
    t2 = "a b c d e f g h"
    bench.document("d2", entities_json(t2, []))
    bench.output(
        "p", "d2", entities_json(t2, [("PER", 2 * i, 2 * i + 1) for i in range(8)])
    )
    result = bench.run(view(["ner_f1"], ArtifactType.ENTITIES))
    assert aggregate(result, "p", "ner_f1").value == pytest.approx(prf_f1(2, 8, 0))


@pytest.mark.valide
@pytest.mark.tranche("1b")
def test_ner_payload__label_absent_de_la_gt__ne_plante_pas(tmp_path: Path) -> None:
    """Un extracteur qui émet un label (LOC) absent de la GT : le mode détaillé doit
    compter un FP, pas lever."""
    bench = Bench(tmp_path, gt_type=ArtifactType.ENTITIES)
    text = "Marie a Paris"
    bench.document("d1", entities_json(text, [("PER", 0, 5)]))
    bench.output("p", "d1", entities_json(text, [("PER", 0, 5), ("LOC", 8, 13)]))
    result = bench.run(view(["ner_f1"], ArtifactType.ENTITIES), analyses="toutes")
    (payload,) = [
        a.payload for a in result.analyses if isinstance(a.payload, NerPayload)
    ]
    (row,) = payload.pipelines
    assert (row.true_positives, row.false_positives) == (1, 1)


def _box(i: int) -> tuple[int, int, int, int]:
    return (10 + 90 * (i % 10), 10 + 90 * (i // 10), 80, 80)


@pytest.mark.valide
@pytest.mark.tranche("1a")
def test_region_detection__micro_sur_tp_fp_fn(tmp_path: Path) -> None:
    """d1 : 1 région GT trouvée + 9 fantômes ; d2 : 10 régions GT trouvées : F1 corpus =
    F1(11, 9, 0)."""
    bench = Bench(tmp_path, gt_type=ArtifactType.LAYOUT)
    bench.document("d1", layout_json([("g0", _box(0), [])]))
    bench.output(
        "p",
        "d1",
        layout_json(
            [("h0", _box(0), [])] + [(f"h{i}", _box(10 + i), []) for i in range(1, 10)]
        ),
    )
    regions: list[tuple[str, tuple[int, int, int, int], list[tuple[str, str]]]]
    regions = [(f"g{i}", _box(i), []) for i in range(10)]
    bench.document("d2", layout_json(regions))
    bench.output("p", "d2", layout_json([(f"h{i}", _box(i), []) for i in range(10)]))
    result = bench.run(view(["region_detection"], ArtifactType.LAYOUT))
    assert aggregate(result, "p", "region_detection").value == pytest.approx(
        prf_f1(11, 9, 0)
    )


@pytest.mark.valide
@pytest.mark.tranche("1a")
def test_bow_f1__micro_sur_tp_hyp_ref(tmp_path: Path) -> None:
    """d1 : 1 mot GT retrouvé + 9 mots parasites ; d2 : 10 mots GT retrouvés : F1 =
    F1(Σtp=11, Σ|hyp|−tp=9, Σ|réf|−tp=0)."""
    bench = Bench(tmp_path)
    bench.document("d1", "alpha")
    bench.output("p", "d1", "alpha " + " ".join(f"x{i}" for i in range(9)))
    words = " ".join(f"w{i}" for i in range(10))
    bench.document("d2", words)
    bench.output("p", "d2", words)
    result = bench.run(view(["bow_f1", "bow_precision", "bow_recall"]))
    assert aggregate(result, "p", "bow_f1").value == pytest.approx(prf_f1(11, 9, 0))


# --- Bornes ---------------------------------------------------------------


@B1
@pytest.mark.tranche("1a")
def test_char_accuracy__vaut_un_moins_cer_corpus(tmp_path: Path) -> None:
    """d1 : réf « ab », hyp de 6 car. faux (CER 3) ; d2 : 10 car. parfaits.
    B1 : le plancher s'applique au corpus, où il n'est pas atteint :
    ``char_accuracy`` = max(0, 1 − 6/12) = 0,5, et non la moyenne des planchers
    par page (0,833). Les comptes (6, 12) et le taux 0,5 sont publiés."""
    bench = Bench(tmp_path)
    bench.document("d1", "ab")
    bench.output("p", "d1", "000000")
    bench.document("d2", "abcdefghij")
    bench.output("p", "d2", "abcdefghij")
    result = bench.run(view(["cer", "char_accuracy"]))
    cer = aggregate(result, "p", "cer").value
    assert cer == pytest.approx(0.5)
    assert cer is not None
    accuracy = aggregate(result, "p", "char_accuracy")
    assert accuracy.value == pytest.approx(1 - cer)
    assert composantes(accuracy, "errors", "reference_length") == (6, 12)
    assert taux_non_tronque(accuracy) == pytest.approx(0.5)
