"""Tranche 1a — statistiques suffisantes et agrégation (K1 ; M1, M2, M3, M6).

Tests écrits pour la refonte (``CONTRATS.md`` § 4.1, « 1a · À écrire ») : les
contre-exemples de la revue (``rapports/revue_contre_exemples/`` de la
contre-expertise) portés en tests, et les propriétés « P » de M1, M2, M3 et M6
(Hypothesis, profil déterministe). Tous passent par ``evaluate_run`` (agrégat et
observations réels d'un ``RunResult``) ; les champs que la tranche ajoute sont
lus par ``tests/adversarial/_contrat.py``.

Oracles indépendants, écrits ici sans Cinoc :
- DP lexicographique pour les comptes (S, D, I) canoniques (P1 : parmi les
  alignements de coût minimal, celui qui maximise S) ;
- ``jiwer`` pour S+D+I au niveau du corpus quand Σ n_réf > 0 ;
- énumération exhaustive des appariements d'entités (IoU d'empan ≥ 1/2, même
  catégorie : la règle de Cinoc), et non nervaluate (k1_ner_oracle_nervaluate) ;
- ``fractions.Fraction`` pour l'ECE (R1 : une seule conversion en flottant).
"""

from __future__ import annotations

import itertools
import json
import tempfile
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

import jiwer
import pytest
from hypothesis import given
from hypothesis import strategies as st

from cinoc.domain.artifacts import ArtifactType
from cinoc.evaluation.analysis import CalibrationPayload, NerPayload
from cinoc.evaluation.result import RunResult
from tests.adversarial._contrat import (
    axes,
    composante,
    composantes,
    exige,
    motif_scalaire,
    taux_non_tronque,
)
from tests.adversarial._hypothese import DETERMINISTE
from tests.adversarial.metriques_stats.ms_support import (
    Bench,
    aggregate,
    entities_json,
    observation,
    prf_f1,
    view,
)

pytestmark = pytest.mark.tranche("1a")

EDITS = ("substitutions", "deletions", "insertions", "reference_length")


# --- Oracles ---------------------------------------------------------------


def canonical_sdi(ref: Sequence[object], hyp: Sequence[object]) -> tuple[int, int, int]:
    """(S, D, I) de l'alignement de coût minimal qui maximise S (DP lexicographique)."""
    n, m = len(ref), len(hyp)
    # dp[i][j] = (coût, −S, D, I), minimisé dans cet ordre.
    dp: list[list[tuple[int, int, int, int]]] = [
        [(0, 0, 0, 0)] * (m + 1) for _ in range(n + 1)
    ]
    for i in range(n + 1):
        for j in range(m + 1):
            if i == j == 0:
                continue
            options = []
            if i:
                c, s, d, k = dp[i - 1][j]
                options.append((c + 1, s, d + 1, k))
            if j:
                c, s, d, k = dp[i][j - 1]
                options.append((c + 1, s, d, k + 1))
            if i and j:
                c, s, d, k = dp[i - 1][j - 1]
                sub = int(ref[i - 1] != hyp[j - 1])
                options.append((c + sub, s - sub, d, k))
            dp[i][j] = min(options)
    _, minus_s, d, k = dp[n][m]
    return -minus_s, d, k


def f1_or_none(tp: int, fp: int, fn: int) -> float | None:
    return 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None


Span = tuple[str, int, int]


def matched_by_enumeration(refs: Sequence[Span], hyps: Sequence[Span]) -> int:
    """Taille maximale d'un appariement injectif admissible, par énumération.

    Admissible : même catégorie et IoU d'empan ≥ 1/2, en arithmétique exacte
    (2·|∩| ≥ |∪|). C'est la règle de Cinoc (``ner.py``) ; nervaluate n'en a
    aucune équivalente (son ``ent_type`` accepte tout chevauchement).
    """

    def admissible(r: Span, h: Span) -> bool:
        inter = max(0, min(r[2], h[2]) - max(r[1], h[1]))
        union = (r[2] - r[1]) + (h[2] - h[1]) - inter
        return r[0] == h[0] and union > 0 and 2 * inter >= union

    best = 0
    for k in range(min(len(refs), len(hyps)), 0, -1):
        for chosen in itertools.combinations(range(len(refs)), k):
            for image in itertools.permutations(range(len(hyps)), k):
                if all(
                    admissible(refs[r], hyps[h])
                    for r, h in zip(chosen, image, strict=True)
                ):
                    return k
    return best


def ner_counts(refs: Sequence[Span], hyps: Sequence[Span]) -> tuple[int, int, int]:
    tp = matched_by_enumeration(refs, hyps)
    return tp, len(hyps) - tp, len(refs) - tp


# --- M1 : taux d'édition ---------------------------------------------------


def test_k1_editops_egalites__comptes_canoniques_maximisent_s(tmp_path: Path) -> None:
    """``k1_editops_egalites.py`` : « ab » contre « ba » a deux alignements de
    coût 2, (S, D, I) = (2, 0, 0) et (0, 1, 1) ; rapidfuzz retient le second.
    M1 (P1) : les comptes publiés sont les canoniques, (2, 0, 0), ceux de la DP
    lexicographique. Au mot, « a b » contre « b a » : ``ins_rate`` et
    ``del_rate`` valent donc 0, pas 0,5 ; le CER reste 1 (S+D+I inchangé)."""
    bench = Bench(tmp_path)
    bench.document("car", "ab")
    bench.output("p", "car", "ba")
    bench.document("mots", "a b")
    bench.output("p", "mots", "b a")
    result = bench.run(view(["cer", "ins_rate", "del_rate"]))
    assert observation(result, "p", "mots", "ins_rate").value == 0.0
    assert observation(result, "p", "mots", "del_rate").value == 0.0
    assert canonical_sdi("ab", "ba") == (2, 0, 0)
    assert composantes(observation(result, "p", "car", "cer"), *EDITS) == (2, 0, 0, 2)
    mots = observation(result, "p", "mots", "ins_rate")
    assert composantes(mots, *EDITS) == (2, 0, 0, 2)


def jiwer_cmer(ref: str, hyp: str) -> float:
    """cMER de jiwer au caractère : (S+D+I) / (H+S+D+I), comptes de jiwer."""
    o = jiwer.process_characters(ref, hyp)
    edits = o.substitutions + o.deletions + o.insertions
    return float(edits / (o.hits + edits))


@pytest.mark.parametrize(
    ("metric", "ref", "hyp"),
    [
        # mots : canonique (2, 0, 0) → 2 / (2 + 0) ; jiwer (0, 1, 1) → 2/3
        pytest.param("mer", "a b", "b a", id="mer-mots"),
        # caractères : idem sur « ab » / « ba »
        pytest.param("cmer", "ab", "ba", id="cmer-caracteres"),
    ],
)
def test_r2_p1_mer_parite_jiwer__ecart_volontaire_sur_les_ex_aequo(
    tmp_path: Path, metric: str, ref: str, hyp: str
) -> None:
    """``r2_p1_mer_parite_jiwer.py`` : avec les comptes canoniques, MER = (S+D+I)
    / (n_réf + I) s'écarte de jiwer dès qu'il existe des alignements ex æquo —
    écart **volontaire**, écrit dans M1. Sur « a b » / « b a » : 1,0 (jiwer
    0,667)."""
    bench = Bench(tmp_path)
    bench.document("d", ref)
    bench.output("p", "d", hyp)
    result = bench.run(view([metric]))
    value = aggregate(result, "p", metric).value
    oracle = jiwer.mer(ref, hyp) if metric == "mer" else jiwer_cmer(ref, hyp)
    assert oracle == pytest.approx(2 / 3)
    assert value == pytest.approx(1.0), f"{metric} = {value}, comptes de rapidfuzz"


def test_m1_page_blanche__scalaire_indefini_zero_denominator(tmp_path: Path) -> None:
    """M1 : une page à référence vide est applicable, disponible et valide ;
    son scalaire est indéfini (``zero_denominator``) — pas 1,0 — et sa
    statistique porte ses |h| = 3 insertions, qui entrent au micro."""
    bench = Bench(tmp_path)
    bench.document("blank", "")
    bench.output("p", "blank", "xyz")
    bench.document("a", "abcd")
    bench.output("p", "a", "abcd")
    result = bench.run(view(["cer"]))
    blank = observation(result, "p", "blank", "cer")
    assert blank.value is None, f"CER d'une page blanche = {blank.value}"
    assert motif_scalaire(blank) == "zero_denominator"
    assert axes(blank) == ("applicable", "available", "valid")
    assert composantes(blank, *EDITS) == (0, 0, 3, 0)
    assert aggregate(result, "p", "cer").value == pytest.approx(3 / 4)


def test_m1_corpus_entierement_vide__micro_indefini_insertions_publiees(
    tmp_path: Path,
) -> None:
    """M1 : sur un corpus dont toutes les références sont vides, le micro est
    indéfini pour CER et WER — écart volontaire à jiwer, qui rend 3 et 1 — et
    la somme des insertions (3 caractères, 1 mot) est publiée."""
    bench = Bench(tmp_path)
    bench.document("v1", "")
    bench.output("p", "v1", "xyz")
    bench.document("v2", "")
    bench.output("p", "v2", "")
    result = bench.run(view(["cer", "wer"]))
    assert (jiwer.cer(["", ""], ["xyz", ""]), jiwer.wer(["", ""], ["xyz", ""])) == (
        3,
        1,
    )
    cer, wer = aggregate(result, "p", "cer"), aggregate(result, "p", "wer")
    assert (cer.value, wer.value) == (None, None)
    assert composante(cer, "insertions") == 3
    assert composante(wer, "insertions") == 1


words = st.lists(st.sampled_from(["a", "b", "ab", "ba"]), max_size=4)


@DETERMINISTE
@given(st.lists(st.tuples(words, words), min_size=1, max_size=4))
def test_propriete_m1__comptes_canoniques_et_micro_jiwer(
    pairs: list[tuple[list[str], list[str]]],
) -> None:
    """P (M1) : pour tout corpus, (a) le CER et le WER micro égalent jiwer quand
    Σ n_réf > 0 (pages blanches comprises) et sont indéfinis sinon ; (b) chaque
    observation porte les (S, D, I, n_réf) canoniques de la DP ; (c) l'agrégat
    porte leur somme exacte."""
    refs = [" ".join(r) for r, _ in pairs]
    hyps = [" ".join(h) for _, h in pairs]
    with tempfile.TemporaryDirectory() as tmp:
        bench = Bench(Path(tmp))
        for i, (ref, hyp) in enumerate(zip(refs, hyps, strict=True)):
            bench.document(f"d{i}", ref)
            bench.output("p", f"d{i}", hyp)
        result = bench.run(view(["cer", "wer"]))
    for metric, unit in (("cer", list), ("wer", str.split)):
        units = [(unit(r), unit(h)) for r, h in zip(refs, hyps, strict=True)]  # type: ignore[operator]
        n_ref = sum(len(r) for r, _ in units)
        oracle = None
        if n_ref:
            oracle = jiwer.cer(refs, hyps) if metric == "cer" else jiwer.wer(refs, hyps)
        value = aggregate(result, "p", metric).value
        assert value == (pytest.approx(oracle) if oracle is not None else None), (
            f"{metric} micro = {value}, jiwer = {oracle}"
        )
        totals = [0, 0, 0, 0]
        for i, (r, h) in enumerate(units):
            expected = (*canonical_sdi(r, h), len(r))
            assert (
                composantes(observation(result, "p", f"d{i}", metric), *EDITS)
                == expected
            )
            totals = [t + e for t, e in zip(totals, expected, strict=True)]
        assert composantes(aggregate(result, "p", metric), *EDITS) == tuple(totals)


# --- M2 : exactitudes ------------------------------------------------------


def test_m2_word_accuracy__plancher_au_corpus_comptes_publies(tmp_path: Path) -> None:
    """M2 (B1) : ``word_accuracy`` corpus = max(0, 1 − Σe/Σn), jamais la moyenne
    des planchers par page. d1 : 1 mot de réf., 4 erreurs (plancher 0 à la
    page) ; d2 : 4 mots parfaits. Corpus : max(0, 1 − 4/5) = 0,2 (la moyenne des
    planchers donne 0,8) ; comptes (4, 5) et taux non tronqué 0,8 publiés."""
    bench = Bench(tmp_path)
    bench.document("d1", "alpha")
    bench.output("p", "d1", "x y z w")
    bench.document("d2", "un deux trois quatre")
    bench.output("p", "d2", "un deux trois quatre")
    result = bench.run(view(["word_accuracy"]))
    score = aggregate(result, "p", "word_accuracy")
    assert score.value == pytest.approx(0.2), f"word_accuracy = {score.value}"
    assert composantes(score, "errors", "reference_length") == (4, 5)
    assert taux_non_tronque(score) == pytest.approx(0.8)


@DETERMINISTE
@given(st.lists(st.tuples(words, words), min_size=1, max_size=4))
def test_propriete_m2__exactitude_au_corpus_et_comptes(
    pairs: list[tuple[list[str], list[str]]],
) -> None:
    """P (M2) : pour tout corpus, ``char_accuracy`` et ``word_accuracy`` valent
    max(0, 1 − Σe/Σn) (indéfinies si Σn = 0), où e est la distance d'édition ;
    (Σe, Σn) et Σe/Σn sont publiés à côté."""
    refs = [" ".join(r) for r, _ in pairs]
    hyps = [" ".join(h) for _, h in pairs]
    with tempfile.TemporaryDirectory() as tmp:
        bench = Bench(Path(tmp))
        for i, (ref, hyp) in enumerate(zip(refs, hyps, strict=True)):
            bench.document(f"d{i}", ref)
            bench.output("p", f"d{i}", hyp)
        result = bench.run(view(["char_accuracy", "word_accuracy"]))
    for metric, unit in (("char_accuracy", list), ("word_accuracy", str.split)):
        units = [(unit(r), unit(h)) for r, h in zip(refs, hyps, strict=True)]  # type: ignore[operator]
        errors = sum(sum(canonical_sdi(r, h)) for r, h in units)
        n_ref = sum(len(r) for r, _ in units)
        score = aggregate(result, "p", metric)
        expected = max(0.0, 1 - errors / n_ref) if n_ref else None
        assert score.value == (
            pytest.approx(expected) if expected is not None else None
        ), f"{metric} = {score.value}, attendu max(0, 1 − {errors}/{n_ref})"
        assert composantes(score, "errors", "reference_length") == (errors, n_ref)
        if n_ref:
            assert taux_non_tronque(score) == pytest.approx(errors / n_ref)


# --- M3 : appariement P/R/F, agrégation ------------------------------------


def test_k1_ner_oracle__f1_micro_par_enumeration(tmp_path: Path) -> None:
    """``k1_ner_oracle_nervaluate.py`` : une prédiction qui couvre l'entité mais
    déborde (IoU 10/30) est juste pour nervaluate (``ent_type``) et fausse pour
    la règle de Cinoc (IoU ≥ 1/2) : nervaluate ne peut pas servir d'oracle.
    Oracle retenu (M3) : énumération des appariements sous la règle de Cinoc.
    d1 : l'empan qui déborde, plus deux lieux inventés, (tp, fp, fn) =
    (0, 3, 1) ; d2 : trois entités exactes, (3, 0, 0). F1 corpus =
    F1(3, 3, 1) = 0,6 ; chaque observation porte ses comptes."""
    bench = Bench(tmp_path, gt_type=ArtifactType.ENTITIES)
    t1 = "Jean Valjean marche dans Paris ce matin de juin"
    r1 = [("PER", 0, 10)]
    h1 = [("PER", 0, 30), ("LOC", 25, 30), ("LOC", 43, 47)]
    bench.document("d1", entities_json(t1, r1))
    bench.output("p", "d1", entities_json(t1, h1))
    t2 = "Hugo Paris Lyon"
    r2 = [("PER", 0, 4), ("LOC", 5, 10), ("LOC", 11, 15)]
    bench.document("d2", entities_json(t2, r2))
    bench.output("p", "d2", entities_json(t2, r2))
    result = bench.run(view(["ner_f1"], ArtifactType.ENTITIES))
    oracle = {"d1": ner_counts(r1, h1), "d2": ner_counts(r2, r2)}
    assert oracle == {"d1": (0, 3, 1), "d2": (3, 0, 0)}
    value = aggregate(result, "p", "ner_f1").value
    assert value == pytest.approx(prf_f1(3, 3, 1)), f"ner_f1 corpus = {value}"
    for document, counts in oracle.items():
        assert (
            composantes(observation(result, "p", document, "ner_f1"), "tp", "fp", "fn")
            == counts
        )


def test_m3_tout_vide__f1_indefini(tmp_path: Path) -> None:
    """M3 : ni entité de référence ni entité prédite, sur tout le corpus : le
    F1 corpus est indéfini (dénominateur nul), pas 0 ni 1."""
    bench = Bench(tmp_path, gt_type=ArtifactType.ENTITIES)
    for document in ("d1", "d2"):
        bench.document(document, entities_json("rien a signaler", []))
        bench.output("p", document, entities_json("rien a signaler", []))
    result = bench.run(view(["ner_f1"], ArtifactType.ENTITIES))
    score = aggregate(result, "p", "ner_f1")
    assert score.value is None, f"F1 d'un corpus sans entité = {score.value}"
    assert composantes(score, "tp", "fp", "fn") == (0, 0, 0)


def test_m3_categorie_seulement_predite__precision_nulle_rappel_indefini(
    tmp_path: Path,
) -> None:
    """M3 : une catégorie présente seulement en prédiction (LOC, absente de la
    GT) a P = 0 et R indéfini dans le détail par catégorie — sans erreur ; la
    catégorie présente des deux côtés (PER) garde P = R = 1."""
    bench = Bench(tmp_path, gt_type=ArtifactType.ENTITIES)
    text = "Marie a Paris"
    bench.document("d1", entities_json(text, [("PER", 0, 5)]))
    bench.output("p", "d1", entities_json(text, [("PER", 0, 5), ("LOC", 8, 13)]))
    result = bench.run(view(["ner_f1"], ArtifactType.ENTITIES), analyses="toutes")
    (payload,) = [
        a.payload for a in result.analyses if isinstance(a.payload, NerPayload)
    ]
    (row,) = payload.pipelines
    categories = {c.label: (c.precision, c.recall) for c in row.per_category}
    assert categories == {"PER": (1.0, 1.0), "LOC": (0.0, None)}


SLOTS = 6


@st.composite
def entity_documents(draw: st.DrawFn) -> list[tuple[list[Span], list[Span]]]:
    """Documents d'entités sur des cases disjointes [4k, 4k+3) : chaque entité
    de référence est copiée, ré-étiquetée, ou omise ; des faux positifs occupent
    des cases libres. L'appariement y est sans ambiguïté (M8 n'est pas en jeu)."""
    documents = []
    for _ in range(draw(st.integers(1, 3))):
        refs: list[Span] = []
        hyps: list[Span] = []
        for k in range(SLOTS):
            span = (4 * k, 4 * k + 3)
            kind = draw(st.sampled_from(["vide", "exact", "etiquette", "omise", "fp"]))
            label = draw(st.sampled_from(["PER", "LOC"]))
            other = "LOC" if label == "PER" else "PER"
            if kind in {"exact", "etiquette", "omise"}:
                refs.append((label, *span))
            if kind == "exact":
                hyps.append((label, *span))
            elif kind == "etiquette":
                hyps.append((other, *span))
            elif kind == "fp":
                hyps.append((label, *span))
        documents.append((refs, hyps))
    return documents


@DETERMINISTE
@given(entity_documents())
def test_propriete_m3__f1_sur_les_comptes_sommes(
    documents: list[tuple[list[Span], list[Span]]],
) -> None:
    """P (M3) : pour tout corpus, ``ner_f1`` = F1(Σtp, Σfp, Σfn), indéfini si le
    dénominateur est nul ; un document sans référence contribue ses fp ; chaque
    observation porte les comptes de l'énumération."""
    text = "x" * (4 * SLOTS)
    with tempfile.TemporaryDirectory() as tmp:
        bench = Bench(Path(tmp), gt_type=ArtifactType.ENTITIES)
        for i, (refs, hyps) in enumerate(documents):
            bench.document(f"d{i}", entities_json(text, refs))
            bench.output("p", f"d{i}", entities_json(text, hyps))
        result = bench.run(view(["ner_f1"], ArtifactType.ENTITIES))
    counts = [ner_counts(refs, hyps) for refs, hyps in documents]
    tp, fp, fn = (sum(c[k] for c in counts) for k in range(3))
    expected = f1_or_none(tp, fp, fn)
    value = aggregate(result, "p", "ner_f1").value
    assert value == (pytest.approx(expected) if expected is not None else None), (
        f"ner_f1 = {value}, F1({tp}, {fp}, {fn}) = {expected}"
    )
    for i, c in enumerate(counts):
        assert (
            composantes(observation(result, "p", f"d{i}", "ner_f1"), "tp", "fp", "fn")
            == c
        )


# --- M6 : calibration -------------------------------------------------------


Token = tuple[float, bool]


def exact_calibration(
    tokens: Sequence[Token],
) -> tuple[float, float, dict[int, tuple[int, int, Fraction]]]:
    """ECE, MCE et histogramme exacts (R1) : (n_b, justes_b) entiers, Σconf_b en
    ``Fraction`` ; ECE = (1/N) Σ_b |justes_b − Σconf_b|, une conversion."""
    bins: dict[int, tuple[int, int, Fraction]] = {}
    for confidence, correct in tokens:
        b = min(int(confidence * 10), 9)
        n, j, s = bins.get(b, (0, 0, Fraction(0)))
        bins[b] = (n + 1, j + int(correct), s + Fraction(confidence))
    total = sum(n for n, _, _ in bins.values())
    ece = sum((abs(j - s) for _, j, s in bins.values()), Fraction(0)) / total
    mce = max(abs(j - s) / n for n, j, s in bins.values())
    return float(ece), float(mce), bins


def calibration_run(
    tmp: Path, partition: Sequence[Sequence[tuple[str, Token]]]
) -> RunResult:
    """Un document par part : sa GT contient les mots des jetons justes ; la
    sortie, tous les mots ; le sidecar, leurs confiances."""
    tmp.mkdir(parents=True, exist_ok=True)
    bench = Bench(tmp)
    for i, part in enumerate(partition):
        bench.document(f"d{i}", " ".join(w for w, (_, ok) in part if ok) or "vide")
        bench.output(
            "p",
            f"d{i}",
            " ".join(w for w, _ in part),
            extra={
                ArtifactType.CONFIDENCES: json.dumps(
                    [{"text": w, "confidence": c} for w, (c, _) in part]
                )
            },
        )
    return bench.run(view(["cer"]))


def calibration_row(result: RunResult) -> object:
    (payload,) = [
        a.payload for a in result.analyses if isinstance(a.payload, CalibrationPayload)
    ]
    (row,) = payload.pipelines
    return row


def assert_exact_calibration(row: object, tokens: Sequence[Token]) -> None:
    ece, mce, bins = exact_calibration(tokens)
    assert (exige(row, "ece", "M6"), exige(row, "mce", "M6")) == (ece, mce), (
        f"ECE/MCE publiés {(row.ece, row.mce)} ≠ exacts {(ece, mce)}"  # type: ignore[attr-defined]
    )
    published = {
        min(int(b.lower * 10 + 0.5), 9): (
            b.count,
            exige(b, "correct", "§ 2.1 a, calibration (n_b, justes_b, Σconf_b)"),
            exige(b, "confidence_sum", "§ 2.1 a, calibration (n_b, justes_b, Σconf_b)"),
        )
        for b in row.bins  # type: ignore[attr-defined]
    }
    assert published == bins


def test_k1_fsum_r2_r1_fraction__ece_exacte_quelle_que_soit_la_partition(
    tmp_path: Path,
) -> None:
    """``k1_fsum_non_associatif.py`` et ``r2_r1_fraction.py`` (M6, R1) : trois
    jetons faux de confiances 0,32, 0,40 et 0,38, répartis de deux façons entre
    deux documents. L'histogramme combiné est l'histogramme poolé (Σconf en
    ``Fraction``), et l'ECE est la conversion unique de la valeur exacte —
    0,3666666666666667, et non 0,36666666666666664 (moyenne flottante par
    classe, puis pondération flottante) — identique bit à bit sous les deux
    partitions."""
    tokens = {"faux": (0.32, False), "mot": (0.40, False), "zut": (0.38, False)}
    one = calibration_run(
        tmp_path / "p1",
        [[("faux", tokens["faux"]), ("mot", tokens["mot"])], [("zut", tokens["zut"])]],
    )
    two = calibration_run(
        tmp_path / "p2",
        [[("zut", tokens["zut"])], [("faux", tokens["faux"]), ("mot", tokens["mot"])]],
    )
    ece, _, _ = exact_calibration(list(tokens.values()))
    assert ece == 0.3666666666666667
    row_one, row_two = calibration_row(one), calibration_row(two)
    assert (row_one.ece, row_two.ece) == (ece, ece)  # type: ignore[attr-defined]
    assert_exact_calibration(row_one, list(tokens.values()))
    assert_exact_calibration(row_two, list(tokens.values()))


@st.composite
def token_partitions(draw: st.DrawFn) -> list[list[tuple[str, Token]]]:
    """Jetons à mots uniques (le jugement par multi-ensemble est alors sans
    ambiguïté), confiances loin des bornes de classe, répartis en 1 à 3 parts."""
    n = draw(st.integers(1, 8))
    parts: list[list[tuple[str, Token]]] = [[] for _ in range(draw(st.integers(1, 3)))]
    for i in range(n):
        b = draw(st.integers(0, 9))
        confidence = (b + draw(st.floats(0.05, 0.95))) / 10
        token = (f"w{i}", (confidence, draw(st.booleans())))
        parts[draw(st.integers(0, len(parts) - 1))].append(token)
    return [p for p in parts if p]


@DETERMINISTE
@given(token_partitions())
def test_propriete_m6__histogramme_combine_egal_au_poole(
    partition: list[list[tuple[str, Token]]],
) -> None:
    """P (M6) : pour toute partition et tout ordre des documents, l'histogramme
    combiné est égal (``==``) à celui des jetons poolés, et l'ECE et la MCE sont
    la conversion unique de leur valeur exacte (identiques bit à bit)."""
    tokens = [t for part in partition for _, t in part]
    with tempfile.TemporaryDirectory() as tmp:
        result = calibration_run(Path(tmp), partition)
    assert_exact_calibration(calibration_row(result), tokens)
