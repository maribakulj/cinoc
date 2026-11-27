"""Affirmation 1 — contrat mathématique des métriques et de leur agrégation.

Chaque test construit un corpus minimal, passe par ``evaluate_run`` (agrégat
réel du ``RunResult``) et compare à un calcul indépendant fait à la main sur
les statistiques suffisantes (numérateur, dénominateur ; ou TP/FP/FN).
"""

from __future__ import annotations

from pathlib import Path

import jiwer
import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.evaluation.analysis import CalibrationPayload, NerPayload
from cinoc.evaluation.registry import metric_specs
from tests.adversarial.metriques_stats.ms_support import (
    Bench,
    aggregate,
    entities_json,
    layout_json,
    letters,
    prf_f1,
    substitute,
    view,
)

HALLUCINATION = "Lorem ipsum dolor sit amet hallucinated page"  # 44 car., 7 mots


def _blank_page_bench(tmp_path: Path) -> Bench:
    bench = Bench(tmp_path)
    bench.document("a", "abcdefghij")  # 10 car., 1 mot
    bench.document("blank", "")  # page blanche : vérité terrain vide
    bench.output("p", "a", "abcdefghij")  # parfait
    bench.output("p", "blank", HALLUCINATION)  # page entière inventée
    return bench


# --- Références vides ------------------------------------------------------


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        # Σ éditions / Σ longueurs de référence = (0 + 44) / (10 + 0)
        pytest.param("cer", 44 / 10, marks=pytest.mark.valide),
        # Σ éditions mot / Σ mots de référence = (0 + 7) / (1 + 0)
        pytest.param("wer", 7 / 1, marks=pytest.mark.valide),
        # Σ insertions mot / Σ mots de référence = (0 + 7) / 1
        pytest.param("ins_rate", 7 / 1, marks=pytest.mark.valide),
        # max(0, 1 − CER corpus) — la définition déclarée par la métrique
        pytest.param("char_accuracy", 0.0, marks=pytest.mark.discutable("C02-plancher-exactitudes")),
        # max(0, 1 − Σ erreurs / Σ car. de réf.) = max(0, 1 − 44/10)
        pytest.param("fca", 0.0, marks=pytest.mark.discutable("C02-plancher-exactitudes")),
    ],
)
def test_reference_vide__hallucination_comptee_au_numerateur(
    tmp_path: Path, metric: str, expected: float
) -> None:
    """Page blanche (GT vide) + 44 car. inventés : les erreurs doivent entrer dans Σ erreurs du corpus."""
    result = _blank_page_bench(tmp_path).run(view([metric]))
    score = aggregate(result, "p", metric)
    assert score.value == pytest.approx(expected)


@pytest.mark.parametrize("metric", ["cmer", "mer", "bow_precision", "unanchored_trigrams"])
def test_reference_vide__metriques_a_denominateur_hypothese_penalisent(
    tmp_path: Path, metric: str
) -> None:
    """Contrôle : une métrique dont le dénominateur inclut l'hypothèse voit la page inventée."""
    result = _blank_page_bench(tmp_path).run(view([metric]))
    value = aggregate(result, "p", metric).value
    assert value is not None
    worse = value > 0 if metric != "bow_precision" else value < 1
    assert worse


@pytest.mark.valide
def test_reference_vide__pipeline_qui_hallucine_est_classe_apres(tmp_path: Path) -> None:
    """H invente 44 car. sur la page blanche et lit « a » parfaitement ; S se tait sur la blanche et fait 1 erreur sur « a » : H doit avoir le pire CER."""
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
    assert (h, s) == (pytest.approx(4.4), pytest.approx(0.1))


# --- F1 et ratios non linéaires -------------------------------------------


def _ner_bench(tmp_path: Path) -> Bench:
    """d1 : 1 entité GT trouvée + 9 faux positifs ; d2 : 10 entités GT toutes trouvées."""
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
@pytest.mark.parametrize("metric", ["ner_f1", "ner_f1_exact"])
def test_ner_f1__micro_sur_tp_fp_fn(tmp_path: Path, metric: str) -> None:
    """Comptes déséquilibrés (d1 : TP1 FP9 ; d2 : TP10) : le F1 corpus est F1(ΣTP=11, ΣFP=9, ΣFN=0)."""
    result = _ner_bench(tmp_path).run(view([metric], ArtifactType.ENTITIES))
    expected = prf_f1(tp=11, fp=9, fn=0)  # 22/31 ≈ 0,7097
    assert aggregate(result, "p", metric).value == pytest.approx(expected)


def test_ner_payload__micro_sur_tp_fp_fn(tmp_path: Path) -> None:
    """Contrôle : le payload ``ner`` du même RunResult cumule TP/FP/FN avant le ratio."""
    result = _ner_bench(tmp_path).run(view(["ner_f1"], ArtifactType.ENTITIES))
    (payload,) = [a.payload for a in result.analyses if isinstance(a.payload, NerPayload)]
    (row,) = payload.pipelines
    assert (row.true_positives, row.false_positives, row.false_negatives) == (11, 9, 0)
    assert row.f1 == pytest.approx(prf_f1(11, 9, 0))


@pytest.mark.valide
def test_ner_f1__faux_positifs_sur_document_sans_entite_gt(tmp_path: Path) -> None:
    """d1 : 2 entités GT trouvées ; d2 : GT sans entité, 8 entités inventées : F1 corpus = F1(2, 8, 0) = 1/3."""
    bench = Bench(tmp_path, gt_type=ArtifactType.ENTITIES)
    t1 = "Jean Paul"
    spans = [("PER", 0, 4), ("PER", 5, 9)]
    bench.document("d1", entities_json(t1, spans))
    bench.output("p", "d1", entities_json(t1, spans))
    t2 = "a b c d e f g h"
    bench.document("d2", entities_json(t2, []))
    bench.output("p", "d2", entities_json(t2, [("PER", 2 * i, 2 * i + 1) for i in range(8)]))
    result = bench.run(view(["ner_f1"], ArtifactType.ENTITIES))
    assert aggregate(result, "p", "ner_f1").value == pytest.approx(prf_f1(2, 8, 0))


@pytest.mark.valide
def test_ner_payload__label_absent_de_la_gt__ne_plante_pas(tmp_path: Path) -> None:
    """Un extracteur qui émet un label (LOC) absent de la GT : le mode détaillé doit compter un FP, pas lever."""
    bench = Bench(tmp_path, gt_type=ArtifactType.ENTITIES)
    text = "Marie a Paris"
    bench.document("d1", entities_json(text, [("PER", 0, 5)]))
    bench.output("p", "d1", entities_json(text, [("PER", 0, 5), ("LOC", 8, 13)]))
    result = bench.run(view(["ner_f1"], ArtifactType.ENTITIES), analyses="toutes")
    (payload,) = [a.payload for a in result.analyses if isinstance(a.payload, NerPayload)]
    (row,) = payload.pipelines
    assert (row.true_positives, row.false_positives) == (1, 1)


def _box(i: int) -> tuple[int, int, int, int]:
    return (10 + 90 * (i % 10), 10 + 90 * (i // 10), 80, 80)


@pytest.mark.valide
def test_region_detection__micro_sur_tp_fp_fn(tmp_path: Path) -> None:
    """d1 : 1 région GT trouvée + 9 fantômes ; d2 : 10 régions GT trouvées : F1 corpus = F1(11, 9, 0)."""
    bench = Bench(tmp_path, gt_type=ArtifactType.LAYOUT)
    bench.document("d1", layout_json([("g0", _box(0), [])]))
    bench.output(
        "p",
        "d1",
        layout_json([("h0", _box(0), [])] + [(f"h{i}", _box(10 + i), []) for i in range(1, 10)]),
    )
    regions = [(f"g{i}", _box(i), []) for i in range(10)]
    bench.document("d2", layout_json(regions))
    bench.output("p", "d2", layout_json([(f"h{i}", _box(i), []) for i in range(10)]))
    result = bench.run(view(["region_detection"], ArtifactType.LAYOUT))
    assert aggregate(result, "p", "region_detection").value == pytest.approx(
        prf_f1(11, 9, 0)
    )


@pytest.mark.discutable("C03-poids-reading-order-tau")
def test_reading_order_tau__micro_sur_paires(tmp_path: Path) -> None:
    """d1 : 2 blocs inversés (1 paire discordante sur 1) ; d2 : 10 blocs en ordre (0 sur 45) : τ corpus = 1/46."""
    bench = Bench(tmp_path, gt_type=ArtifactType.LAYOUT)
    bench.document("d1", layout_json([("a", None, []), ("b", None, [])], ["a", "b"]))
    bench.output("p", "d1", layout_json([("a", None, []), ("b", None, [])], ["b", "a"]))
    ids = [f"r{i}" for i in range(10)]
    regions = [(i, None, []) for i in ids]
    bench.document("d2", layout_json(regions, ids))
    bench.output("p", "d2", layout_json(regions, ids))
    result = bench.run(view(["reading_order_tau"], ArtifactType.LAYOUT))
    # Statistique suffisante d'une distance de Kendall : (discordantes, paires).
    assert aggregate(result, "p", "reading_order_tau").value == pytest.approx(1 / 46)


@pytest.mark.valide
def test_bow_f1__micro_sur_tp_hyp_ref(tmp_path: Path) -> None:
    """d1 : 1 mot GT retrouvé + 9 mots parasites ; d2 : 10 mots GT retrouvés : F1 = F1(Σtp=11, Σ|hyp|−tp=9, Σ|réf|−tp=0)."""
    bench = Bench(tmp_path)
    bench.document("d1", "alpha")
    bench.output("p", "d1", "alpha " + " ".join(f"x{i}" for i in range(9)))
    words = " ".join(f"w{i}" for i in range(10))
    bench.document("d2", words)
    bench.output("p", "d2", words)
    result = bench.run(view(["bow_f1", "bow_precision", "bow_recall"]))
    assert aggregate(result, "p", "bow_f1").value == pytest.approx(prf_f1(11, 9, 0))


def test_bow_precision_recall__micro_sur_comptes(tmp_path: Path) -> None:
    """Contrôle : précision et rappel BoW, ratios de comptes pondérés par leur dénominateur, sont exacts (11/20, 11/11)."""
    bench = Bench(tmp_path)
    bench.document("d1", "alpha")
    bench.output("p", "d1", "alpha " + " ".join(f"x{i}" for i in range(9)))
    words = " ".join(f"w{i}" for i in range(10))
    bench.document("d2", words)
    bench.output("p", "d2", words)
    result = bench.run(view(["bow_precision", "bow_recall"]))
    assert aggregate(result, "p", "bow_precision").value == pytest.approx(11 / 20)
    assert aggregate(result, "p", "bow_recall").value == pytest.approx(1.0)


# --- Bornes ---------------------------------------------------------------


@pytest.mark.discutable("C02-plancher-exactitudes")
def test_char_accuracy__vaut_un_moins_cer_corpus(tmp_path: Path) -> None:
    """d1 : réf « ab », hyp de 6 car. faux (CER 3) ; d2 : 10 car. parfaits : CER corpus 6/12 = 0,5, donc exactitude 0,5."""
    bench = Bench(tmp_path)
    bench.document("d1", "ab")
    bench.output("p", "d1", "000000")
    bench.document("d2", "abcdefghij")
    bench.output("p", "d2", "abcdefghij")
    result = bench.run(view(["cer", "char_accuracy"]))
    cer = aggregate(result, "p", "cer").value
    assert cer == pytest.approx(0.5)
    assert aggregate(result, "p", "char_accuracy").value == pytest.approx(1 - cer)


def test_cer_borne__peut_depasser_un_et_cmer_borne(tmp_path: Path) -> None:
    """Contrôle : CER non borné (réf « ab », hyp 6 car. → 3,0, agrégat compris) ; cMER borné dans [0, 1]."""
    bench = Bench(tmp_path)
    bench.document("d1", "ab")
    bench.output("p", "d1", "000000")
    result = bench.run(view(["cer", "cmer"]))
    assert aggregate(result, "p", "cer").value == pytest.approx(3.0)
    cmer = aggregate(result, "p", "cmer").value
    assert cmer is not None and 0.0 <= cmer <= 1.0
    assert cmer == pytest.approx(6 / 6)  # (S2 + I4) / (H0 + S2 + D0 + I4)


# --- Parité corpus avec un oracle indépendant -----------------------------


def test_taux_additifs__parite_corpus_jiwer(tmp_path: Path) -> None:
    """Contrôle : CER, WER, MER, cMER micro = jiwer au niveau corpus (comptes sommés) sur 3 documents de tailles inégales."""
    pairs = [
        ("le chat dort sur le tapis", "le chot dort sur tapis rouge"),
        ("un", "un deux trois"),
        ("abc def ghi jkl mno pqr stu vwx", "abc dxf ghi jkl mno pqr stu"),
    ]
    bench = Bench(tmp_path)
    for i, (ref, hyp) in enumerate(pairs):
        bench.document(f"d{i}", ref)
        bench.output("p", f"d{i}", hyp)
    result = bench.run(view(["cer", "wer", "mer", "cmer"]))
    refs, hyps = [r for r, _ in pairs], [h for _, h in pairs]
    words = jiwer.process_words(refs, hyps)
    chars = jiwer.process_characters(refs, hyps)
    c_edits = chars.substitutions + chars.deletions + chars.insertions
    assert aggregate(result, "p", "wer").value == pytest.approx(words.wer)
    assert aggregate(result, "p", "mer").value == pytest.approx(words.mer)
    assert aggregate(result, "p", "cer").value == pytest.approx(chars.cer)
    assert aggregate(result, "p", "cmer").value == pytest.approx(
        c_edits / (chars.hits + c_edits)
    )


def test_preservation__micro_sur_comptes(tmp_path: Path) -> None:
    """Contrôle : diacritic_err (k/n pondéré par n) = Σ mal lus / Σ attendus (d1 : 1/1 ; d2 : 0/4 → 1/5)."""
    bench = Bench(tmp_path)
    bench.document("d1", "é")
    bench.output("p", "d1", "e")
    bench.document("d2", "éèêë")
    bench.output("p", "d2", "éèêë")
    result = bench.run(view(["diacritic_err"]))
    assert aggregate(result, "p", "diacritic_err").value == pytest.approx(1 / 5)


@pytest.mark.discutable("C04-lignes-fantomes")
def test_line_identity_cer__ligne_fantome_comptee_en_insertion(tmp_path: Path) -> None:
    """Réf : l1 (10 car.) ; hyp : l1 identique + l2 fantôme de 10 car. : comme region_cer (D-288), CER = 10/10."""
    bench = Bench(tmp_path, gt_type=ArtifactType.LAYOUT)
    bench.document("d1", layout_json([("r", None, [("l1", "abcdefghij")])]))
    bench.output(
        "p", "d1", layout_json([("r", None, [("l1", "abcdefghij"), ("l2", "zzzzzzzzzz")])])
    )
    result = bench.run(view(["line_identity_cer", "region_cer"], ArtifactType.LAYOUT))
    assert aggregate(result, "p", "line_identity_cer").value == pytest.approx(1.0)


# --- Calibration ----------------------------------------------------------


def test_calibration__ece_sur_jetons_poolés(tmp_path: Path) -> None:
    """Contrôle : d1 10 jetons à 0,95 justes, d2 2 jetons à 0,95 faux : ECE = |10/12 − 0,95| (pool), pas une moyenne d'ECE par page."""
    import json

    bench = Bench(tmp_path)
    w1 = [f"m{i}" for i in range(10)]
    bench.document("d1", " ".join(w1))
    bench.output(
        "p",
        "d1",
        " ".join(w1),
        extra={
            ArtifactType.CONFIDENCES: json.dumps(
                [{"text": w, "confidence": 0.95} for w in w1]
            )
        },
    )
    bench.document("d2", "vrai mot")
    bench.output(
        "p",
        "d2",
        "faux mat",
        extra={
            ArtifactType.CONFIDENCES: json.dumps(
                [{"text": w, "confidence": 0.95} for w in ("faux", "mat")]
            )
        },
    )
    result = bench.run(view(["cer"]))
    (payload,) = [
        a.payload for a in result.analyses if isinstance(a.payload, CalibrationPayload)
    ]
    (row,) = payload.pipelines
    assert row.n_tokens == 12
    assert row.ece == pytest.approx(abs(10 / 12 - 0.95))
    assert row.mce == pytest.approx(abs(10 / 12 - 0.95))


# --- Exhaustivité de l'audit ----------------------------------------------


AUDITED = {
    "air", "bow_f1", "bow_precision", "bow_recall", "cer", "cer_diplo",
    "char_accuracy", "cmer", "del_rate", "diacritic_err", "fca", "hcpr",
    "ins_rate", "line_identity_cer", "line_identity_coverage", "mer",
    "mufi_err", "ner_f1", "ner_f1_exact", "numseq_strict", "numseq_value",
    "reading_order_coverage", "reading_order_tau", "region_cer",
    "region_detection", "searchability", "unanchored_trigrams", "wer",
    "word_accuracy",
}


def test_registre__toutes_les_metriques_sont_auditees() -> None:
    """Le tableau du rapport couvre exactement les métriques par-document du registre réel."""
    assert set(metric_specs()) == AUDITED


def test_ratio_de_comptes__substitutions_controlees() -> None:
    """Garde-fou du banc d'essai : ``substitute``/``letters`` produisent exactement k éditions."""
    from rapidfuzz.distance import Levenshtein

    text = letters(50)
    assert Levenshtein.distance(text, substitute(text, 7)) == 7
