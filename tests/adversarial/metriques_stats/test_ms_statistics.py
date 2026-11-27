"""Affirmation 3 — statistiques : micro vs effets par document, IC, manquants.

Les contre-exemples passent par ``evaluate_run`` (le payload ``inference`` et
les agrégats que le rapport consomme) ; les références sont recalculées sans
Cinoc (numpy, scipy, calcul à la main).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from cinoc.app.resume import repetition_dir
from cinoc.domain.documents import DocumentRef
from cinoc.evaluation.inference import micro_ratio_ci
from tests.adversarial.metriques_stats.ms_support import (
    Bench,
    aggregate,
    inference,
    letters,
    substitute,
    view,
)


def _simpson_bench(tmp_path: Path) -> Bench:
    """A parfait sur 12 petites pages (20 car.) et 400 erreurs sur une grosse (2 000 car.) ; B : 2 erreurs par petite page, grosse parfaite."""
    bench = Bench(tmp_path)
    for i in range(12):
        ref = letters(20, seed=i)
        bench.document(f"s{i:02d}", ref)
        bench.output("A", f"s{i:02d}", ref)
        bench.output("B", f"s{i:02d}", substitute(ref, 2))
    big = letters(2000, seed=99)
    bench.document("big", big)
    bench.output("A", "big", substitute(big, 400))
    bench.output("B", "big", big)
    return bench


def test_test_omnibus__meme_sens_que_le_cer_micro_affiche(tmp_path: Path) -> None:
    """Contre-exemple de Simpson : le test « inter-moteurs (CER) » déclaré significatif doit départager dans le sens du CER micro du tableau."""
    result = _simpson_bench(tmp_path).run(view(["cer"]))
    micro = {p: aggregate(result, p, "cer").value for p in ("A", "B")}
    # Référence à la main : A = 400/2240 ≈ 0,179 ; B = 24/2240 ≈ 0,011.
    assert micro["A"] == pytest.approx(400 / 2240)
    assert micro["B"] == pytest.approx(24 / 2240)
    payload = inference(result, "cer")
    assert payload.test == "wilcoxon" and payload.p_holm is not None
    assert payload.p_holm < payload.alpha  # « différence significative »
    best_by_test = payload.mean_ranks[0].pipeline  # rang moyen le plus bas
    best_by_micro = min(micro, key=lambda p: micro[p] or 0.0)
    assert best_by_test == best_by_micro


def test_test_omnibus__p_du_ratio_micro_par_permutation_appariee(tmp_path: Path) -> None:
    """Même corpus : la p d'un test de permutation appariée (échange A/B par document) de ΔCER micro diffère du Wilcoxon affiché — le test ne teste pas le chiffre."""
    result = _simpson_bench(tmp_path).run(view(["cer"]))
    weights = np.array([20.0] * 12 + [2000.0])
    err_a = np.array([0.0] * 12 + [400.0])
    err_b = np.array([2.0] * 12 + [0.0])
    observed = (err_a - err_b).sum() / weights.sum()
    # Permutation exacte : 2^13 échanges de signe des différences par document.
    diffs = err_a - err_b
    signs = np.array(np.meshgrid(*[[1, -1]] * len(diffs))).reshape(len(diffs), -1).T
    null = (signs * diffs).sum(axis=1) / weights.sum()
    p_micro = float(np.mean(np.abs(null) >= abs(observed) - 1e-12))
    payload = inference(result, "cer")
    assert payload.p_value is not None
    # Référence scipy du test affiché (sur les CER par document, non pondérés).
    rates_a, rates_b = err_a / weights, err_b / weights
    assert payload.p_value == pytest.approx(stats.wilcoxon(rates_a, rates_b).pvalue)
    # Le chiffre affiché (Δ micro ≈ +0,168) repose sur une seule page : sa p
    # de permutation appariée vaut 1. Le rapport affiche « significative ».
    assert p_micro == pytest.approx(1.0)
    assert (payload.p_holm or 0.0) >= payload.alpha


def _correlated_bench(tmp_path: Path) -> Bench:
    """30 pages de difficulté très variable ; B fait toujours exactement 1 erreur de plus que A (sur 100 car.)."""
    bench = Bench(tmp_path)
    for i in range(30):
        ref = letters(100, seed=i)
        e = (i * 37) % 60
        bench.document(f"d{i:02d}", ref)
        bench.output("A", f"d{i:02d}", substitute(ref, e))
        bench.output("B", f"d{i:02d}", substitute(ref, e + 1))
    return bench


def _find_difference_interval(payload: object) -> dict[str, object] | None:
    """Cherche dans le payload un intervalle (lower, upper) portant sur une paire (a, b)."""
    stack: list[object] = [payload.model_dump()]  # type: ignore[attr-defined]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if {"a", "b", "lower", "upper"} <= set(item):
                return item
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    return None


def test_intervalles__ic_apparie_sur_la_difference_micro(tmp_path: Path) -> None:
    """B = A + 1 erreur sur chaque page : IC marginaux qui se chevauchent, IC apparié de ΔCER micro = [0,01 ; 0,01] ; le payload doit porter ce dernier."""
    result = _correlated_bench(tmp_path).run(view(["cer"]))
    payload = inference(result, "cer")
    by_name = {iv.pipeline: iv for iv in payload.intervals}
    a, b = by_name["A"], by_name["B"]
    assert a.upper > b.lower and b.upper > a.lower  # marginaux : chevauchement
    # Référence indépendante : bootstrap apparié (mêmes documents tirés pour
    # A et B) du ratio micro — Δ constant par page, donc IC dégénéré en 0,01.
    rng = np.random.default_rng(0)
    idx = rng.integers(0, 30, (2000, 30))
    e = np.array([(i * 37) % 60 for i in range(30)], dtype=float)
    delta = ((e + 1)[idx].sum(1) - e[idx].sum(1)) / (100.0 * 30)
    assert np.quantile(delta, 0.025) > 0  # la différence est certaine
    assert payload.test == "wilcoxon" and (payload.p_holm or 1.0) < payload.alpha
    assert _find_difference_interval(payload) is not None


def _failure_bench(tmp_path: Path) -> Bench:
    """7 pages faciles (100 car.) : A 5 erreurs, B 4 ; 1 page difficile (1 000 car.) : A échoue, B 500 erreurs."""
    bench = Bench(tmp_path)
    for i in range(7):
        ref = letters(100, seed=i)
        bench.document(f"e{i}", ref)
        bench.output("A", f"e{i}", substitute(ref, 5))
        bench.output("B", f"e{i}", substitute(ref, 4))
    hard = letters(1000, seed=50)
    bench.document("hard", hard)
    bench.fail("A", "hard")
    bench.output("B", "hard", substitute(hard, 500))
    return bench


def test_echec_non_aleatoire__classement_sur_documents_communs(tmp_path: Path) -> None:
    """A échoue sur la page difficile (politique par défaut) et B est meilleur sur chaque page commune : les agrégats comparés ne doivent pas classer A devant B."""
    result = _failure_bench(tmp_path).run(view(["cer"]))
    cer_a = aggregate(result, "A", "cer")
    cer_b = aggregate(result, "B", "cer")
    assert (cer_a.support, cer_a.expected) == (7, 8)  # l'échec est bien affiché
    payload = inference(result, "cer")
    assert payload.n_documents == 7 and payload.mean_ranks[0].pipeline == "B"
    # Référence : sur les 7 pages communes, A = 35/700 = 0,05 > B = 28/700 = 0,04.
    assert (cer_a.value or 0.0) >= (cer_b.value or 0.0)


def test_echec_non_aleatoire__politique_max_error_penalise(tmp_path: Path) -> None:
    """Contrôle : sous ``failure_policy=max_error``, l'échec compte 1 000 erreurs : A = 1 035/1 700, pire que B = 528/1 700."""
    result = _failure_bench(tmp_path).run(view(["cer"]), failure_policy="max_error")
    assert aggregate(result, "A", "cer").value == pytest.approx(1035 / 1700)
    assert aggregate(result, "B", "cer").value == pytest.approx(528 / 1700)


def test_intervalles__meme_documents_que_le_test(tmp_path: Path) -> None:
    """Même corpus : le test porte sur 7 cas complets ; les IC qui l'accompagnent doivent porter sur les mêmes documents."""
    result = _failure_bench(tmp_path).run(view(["cer"]))
    payload = inference(result, "cer")
    sizes = {iv.pipeline: iv.n_documents for iv in payload.intervals}
    assert sizes == {"A": payload.n_documents, "B": payload.n_documents}


def test_bootstrap__unite_de_reechantillonnage_le_document() -> None:
    """Contrôle : à 2 documents (0,1 sur 100 car. ; 0,5 sur 300), un bootstrap par document a pour IC 95 % [0,1 ; 0,5] (atomes des tirages {d1,d1} et {d2,d2}), là où un bootstrap par caractère serait étroit."""
    lower, upper = micro_ratio_ci([0.1, 0.5], [100, 300])
    assert (lower, upper) == (pytest.approx(0.1), pytest.approx(0.5))


def test_bootstrap__grappes_documentaires_declarables() -> None:
    """Pages d'un même manuscrit : le contrat doit permettre de déclarer la grappe (corpus et IC), sans quoi l'IC suppose des pages indépendantes."""
    params = set(inspect.signature(micro_ratio_ci).parameters)
    fields = set(DocumentRef.model_fields)
    assert params & {"groups", "clusters", "group"} or fields & {"group", "cluster"}


def test_repetitions__archives_disjointes() -> None:
    """Contrôle : ``--repeat`` donne à chaque répétition sa propre archive (aucune ne relit le cache d'une autre)."""
    base = Path("archive")
    dirs = {repetition_dir(base, i, 5) for i in range(5)}
    assert len(dirs) == 5 and base not in dirs
