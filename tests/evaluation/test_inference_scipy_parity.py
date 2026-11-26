"""Verdicts de l'inférence = ceux de scipy, sur 5 000 tirages seedés.

Critère de sortie de S11 (P5e 3, 4, 6). La référence est recalculée ici **sans
le code de Cinoc** : cas complets, test omnibus (``scipy.stats.wilcoxon`` /
``friedmanchisquare``), Holm sous sa forme **descendante** (rejeter tant que
p₍ⱼ₎ ≤ α/(m − j + 1), arrêter au premier échec — Cinoc, lui, compare des p
ajustées), et Nemenyi sous sa forme **p-value** (``studentized_range.sf`` de
l'écart de rangs, comme scikit-posthocs — Cinoc, lui, compare l'écart à une
distance critique tirée de ``ppf``). Deux formulations, mêmes verdicts.

Tirages : k = 2 à 8 pipelines (et 30 à 50 pour un dixième, la zone où la table
d'avant S11 se trompait), n = 4 à 40 documents, ex æquo et valeurs absentes,
α ∈ {0,01 ; 0,05 ; 0,10} (la table servait 0,05 pour tout α ≠ 0,01), familles
de 1 à 8 tests par run.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pytest
from scipy import stats  # type: ignore[import-untyped]

from cinoc.evaluation.analysis import InferencePayload
from cinoc.evaluation.inference import MIN_SUPPORT, inference_analyses

_DRAWS = 5_000
_SEED = 20261126


def _draw(rng: np.random.Generator) -> dict[str, list[float | None]]:
    k = int(rng.integers(30, 51)) if rng.random() < 0.1 else int(rng.integers(2, 9))
    n = int(rng.integers(MIN_SUPPORT - 2, 41))
    effects = rng.normal(0.0, rng.choice([0.0, 0.02, 0.1]), size=k)
    noise = rng.normal(0.0, 0.05, size=(n, k)) + rng.normal(0.0, 0.05, size=(n, 1))
    values = np.abs(noise + effects + 0.2)
    if rng.random() < 0.4:  # ex æquo (et différences nulles) fréquents
        values = np.round(values, 1)
    data: dict[str, list[float | None]] = {}
    for j in range(k):
        column: list[float | None] = [float(v) for v in values[:, j]]
        for i in range(n):
            if rng.random() < 0.03:
                column[i] = None
        data[f"p{j:02d}"] = column
    return data


def _reference_test(
    data: dict[str, list[float | None]],
) -> tuple[str | None, float | None, np.ndarray]:
    names = sorted(data)
    rows = [
        [data[name][i] for name in names]
        for i in range(len(data[names[0]]))
        if all(data[name][i] is not None for name in names)
    ]
    matrix = np.array(rows, dtype=float).reshape(len(rows), len(names))
    if len(rows) < MIN_SUPPORT or all(len(set(row)) == 1 for row in rows):
        return None, None, matrix
    if len(names) == 2:
        p_value = stats.wilcoxon(matrix[:, 0], matrix[:, 1]).pvalue
        return "wilcoxon", float(p_value), matrix
    return "friedman", float(stats.friedmanchisquare(*matrix.T).pvalue), matrix


def _holm_step_down(p_values: Sequence[float], alpha: float) -> list[bool]:
    order = sorted(range(len(p_values)), key=lambda i: (p_values[i], i))
    rejected = [False] * len(p_values)
    for position, index in enumerate(order):
        if p_values[index] > alpha / (len(p_values) - position):
            break
        rejected[index] = True
    return rejected


def _nemenyi_pairs(
    matrix: np.ndarray, names: list[str], alpha: float
) -> dict[tuple[str, str], bool]:
    n, k = matrix.shape
    ranks = stats.rankdata(matrix, axis=1).mean(axis=0)
    scale = math.sqrt(k * (k + 1) / (6.0 * n))
    pairs = [(i, j) for i in range(k) for j in range(i + 1, k)]
    gaps = np.array([abs(ranks[i] - ranks[j]) for i, j in pairs])
    # Écarts en multiples de 1/(2n) : beaucoup de doublons, une intégrale par
    # valeur distincte suffit.
    unique, inverse = np.unique(np.round(gaps, 12), return_inverse=True)
    p = stats.studentized_range.sf(unique * math.sqrt(2.0) / scale, k, math.inf)[
        inverse
    ]
    return {
        (names[i], names[j]): bool(pv < alpha)
        for (i, j), pv in zip(pairs, p, strict=True)
    }


@pytest.mark.slow  # ~12 s ; tourne dans la suite (le marqueur n'exclut rien)
def test_verdicts_match_scipy_on_5000_seeded_draws() -> None:
    rng = np.random.default_rng(_SEED)
    checked = rejected_omnibus = rejected_holm = posthocs = significant_pairs = 0
    large_k_posthocs = 0
    while checked < _DRAWS:
        family = [_draw(rng) for _ in range(int(rng.integers(1, 9)))]
        alpha = float(rng.choice([0.01, 0.05, 0.10]))
        payloads = [
            analysis.payload
            for analysis in inference_analyses(
                [("v", f"m{i}", data) for i, data in enumerate(family)],
                alpha=alpha,
                with_intervals=False,
            )
        ]
        references = [_reference_test(data) for data in family]
        computed = [i for i, (test, _, _) in enumerate(references) if test is not None]
        holm = dict(
            zip(
                computed,
                _holm_step_down([references[i][1] or 0.0 for i in computed], alpha),
                strict=True,
            )
        )
        for i, payload in enumerate(payloads):
            assert isinstance(payload, InferencePayload)
            test, p_value, matrix = references[i]
            assert payload.test == test
            assert payload.n_documents == matrix.shape[0]
            if test is None:
                assert payload.p_value is None and payload.not_computed is not None
                checked += 1
                continue
            assert payload.p_value == p_value  # même appel scipy : identique
            assert payload.family_size == len(computed)
            assert payload.p_holm is not None
            verdict = payload.p_holm < alpha
            assert verdict == holm[i], (payload, p_value, alpha)
            rejected_omnibus += bool(p_value is not None and p_value < alpha)
            rejected_holm += verdict
            names = sorted(family[i])
            if test == "friedman" and verdict:
                posthocs += 1
                large_k_posthocs += len(names) >= 30
                expected = _nemenyi_pairs(matrix, names, alpha)
                got = {(pair.a, pair.b): pair.significant for pair in payload.pairwise}
                assert got == expected
                significant_pairs += sum(expected.values())
                # Barres CD ⇔ paires : indiscernables ⇔ une barre en commun.
                for (a, b), different in got.items():
                    shared = any(a in g and b in g for g in payload.cd_groups)
                    assert shared is not different
            else:
                assert payload.critical_distance is None and payload.pairwise == ()
            checked += 1
    # Le tirage exerce bien chaque branche (sans quoi la parité ne prouverait
    # rien) — à cette graine : 2 245 rejets bruts, 1 998 après Holm, 1 811
    # post-hoc (dont 181 à k ≥ 30), 19 727 paires significatives.
    assert rejected_holm < rejected_omnibus  # Holm retire des rejets bruts
    assert posthocs > 300 and significant_pairs > 1_000 and large_k_posthocs > 20
