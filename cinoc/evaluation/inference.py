"""Inférence statistique : test omnibus, correction de Holm, post-hoc, bootstrap.

Procédure (Demšar 2006, *Statistical Comparisons of Classifiers over Multiple
Data Sets*, JMLR 7:1-30 — k pipelines × n documents appariés), par
(vue × métrique), sur les **cas complets** :

1. **Test omnibus** : Wilcoxon signé-rangs à 2 pipelines, Friedman (χ², ex
   æquo corrigés) au-delà — par ``scipy.stats``, réglages par défaut
   (Wilcoxon : différences nulles écartées, ``zero_method="wilcox"`` ; p
   exacte jusqu'à 50 paires sans ex æquo ni zéro, sinon ce que la version de
   scipy, écrite au manifeste, prévoit). Non calculé, avec son **motif**, sous
   ``MIN_SUPPORT`` cas complets, à un seul pipeline ou sans aucune différence.
2. **Holm** (1979, *A simple sequentially rejective multiple test procedure*,
   Scand. J. Statist. 6:65-70) sur la **famille des tests calculés du run** —
   les lignes du tableau de significativité, que le lecteur lit comme autant de
   verdicts. Holm contrôle le risque de famille sous **toute** dépendance
   (ici forte : mêmes documents, vues voisines), sans l'hypothèse
   d'indépendance de Šidák ni la perte de puissance de Bonferroni.
3. **Post-hoc de Nemenyi**, seulement si le Friedman est rejeté **après**
   correction : distance critique CD = q_α·√(k(k+1)/6n), q_α quantile du
   range studentisé à df = ∞ divisé par √2 (``scipy.stats.studentized_range``
   — exact pour tout k et tout α, sans table) ; rangs moyens par
   ``scipy.stats.rankdata`` (ex æquo au rang moyen). Les **barres CD** sont les
   groupes maximaux de pipelines consécutifs en rang d'étendue ≤ CD : elles se
   chevauchent, et une paire diffère si et seulement si elle n'en partage
   aucune.

Bootstrap : **percentile** (Efron), graine fixe → déterministe (invariant §12) ;
volontairement pas BCa. Indice de quantile = statistique d'ordre
``round(q·(n_iter−1))``. Seul coût non négligeable de l'inférence : calculé en
mode détaillé seulement (analyse ``inference``).
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from cinoc.evaluation.analysis import (
    Analysis,
    InferencePayload,
    NotComputedReason,
    OmnibusTest,
    PairwiseDifference,
    PipelineInterval,
    PipelineRank,
)
from cinoc.evaluation.errors import EvaluationError

#: Plancher de **puissance**, partagé avec ``metrics.stats.significance`` :
#: sous 6 cas complets, un Wilcoxon bilatéral ne peut pas atteindre p < 0,05
#: (n = 5 → p_min exact = 0,0625) et un Friedman à 2-5 blocs est dégénéré — on
#: dit « non calculé » plutôt qu'un verdict artefact de petit n.
MIN_SUPPORT = 6

#: Seuil des verdicts (risque de famille après Holm, et du post-hoc).
ALPHA = 0.05

#: Séries par pipeline, **alignées** (même index = même document ; ``None`` =
#: non applicable).
PerPipeline = Mapping[str, Sequence[float | None]]


@dataclass(frozen=True)
class Omnibus:
    """Résultat d'un test omnibus : le test et sa p, ou le motif de son absence."""

    names: tuple[str, ...]
    complete: tuple[tuple[float, ...], ...]
    test: OmnibusTest | None
    p_value: float | None
    not_computed: NotComputedReason | None


def omnibus_test(per_pipeline: PerPipeline) -> Omnibus:
    """Wilcoxon (k = 2) ou Friedman (k ≥ 3) sur les cas complets, ou motif."""
    names = tuple(sorted(per_pipeline))
    k = len(names)
    if k < 2:
        return Omnibus(names, (), None, None, "single_pipeline")
    series = [per_pipeline[name] for name in names]
    n_aligned = min(len(column) for column in series)
    complete = tuple(
        tuple(float(value) for value in row if value is not None)
        for row in zip(*(column[:n_aligned] for column in series), strict=True)
        if all(value is not None for value in row)
    )
    if len(complete) < MIN_SUPPORT:
        return Omnibus(names, complete, None, None, "insufficient_support")
    if all(len(set(row)) == 1 for row in complete):
        return Omnibus(names, complete, None, None, "no_difference")
    columns = [list(column) for column in zip(*complete, strict=True)]
    test: OmnibusTest = "wilcoxon" if k == 2 else "friedman"
    try:
        if test == "wilcoxon":
            result = stats.wilcoxon(columns[0], columns[1])
        else:
            result = stats.friedmanchisquare(*columns)
    except ValueError:  # pragma: no cover -- filet : entrée dégénérée résiduelle
        # scipy refuse un échantillon que nos gardes n'ont pas écarté.
        return Omnibus(names, complete, None, None, "no_difference")
    p_value = float(result.pvalue)
    if not math.isfinite(p_value):  # pragma: no cover -- même filet
        return Omnibus(names, complete, None, None, "no_difference")
    return Omnibus(names, complete, test, min(1.0, max(0.0, p_value)), None)


def holm_adjusted(p_values: Sequence[float]) -> tuple[float, ...]:
    """p corrigées de Holm, dans l'ordre d'entrée (monotones, plafonnées à 1).

    p̃₍ᵢ₎ = max_{j ≤ i} min(1, (m − j + 1)·p₍ⱼ₎) sur les p triées croissantes ;
    rejeter H₍ᵢ₎ quand p̃₍ᵢ₎ < α équivaut à la procédure descendante de Holm.
    """
    m = len(p_values)
    order = sorted(range(m), key=lambda i: (p_values[i], i))
    adjusted = [0.0] * m
    running = 0.0
    for position, index in enumerate(order):
        running = max(running, min(1.0, (m - position) * p_values[index]))
        adjusted[index] = running
    return tuple(adjusted)


@lru_cache(maxsize=256)
def nemenyi_critical_value(k: int, alpha: float = ALPHA) -> float:
    """q_α de Nemenyi : quantile 1 − α du range studentisé (k, df = ∞) ÷ √2."""
    if k < 2:
        raise EvaluationError("nemenyi_critical_value : k >= 2 requis.")
    quantile = stats.studentized_range.ppf(1.0 - alpha, k, math.inf)
    return float(quantile) / math.sqrt(2.0)


def bootstrap_ci(
    values: Sequence[float],
    n_iter: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """IC percentile de la moyenne par bootstrap — déterministe (graine fixe)."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = sorted(
        sum(values[rng.randint(0, n - 1)] for _ in range(n)) / n
        for _ in range(n_iter)
    )
    half_alpha = (1.0 - ci) / 2.0

    def order_stat(q: float) -> float:
        return means[max(0, min(n_iter - 1, round(q * (n_iter - 1))))]

    return (order_stat(half_alpha), order_stat(1.0 - half_alpha))


def _cd_groups(
    names: Sequence[str], ranks: Sequence[float], critical_distance: float
) -> tuple[tuple[str, ...], ...]:
    """Barres CD : groupes maximaux consécutifs en rang, d'étendue ≤ CD.

    Un groupe contenu dans le précédent n'est pas répété ; un pipeline qui ne
    partage de groupe avec personne forme le sien (il diffère de tous).
    """
    order = sorted(range(len(names)), key=lambda i: (ranks[i], names[i]))
    groups: list[tuple[str, ...]] = []
    last_end = -1
    for start in range(len(order)):
        end = start
        while (
            end + 1 < len(order)
            and ranks[order[end + 1]] - ranks[order[start]] <= critical_distance
        ):
            end += 1
        if end > last_end:
            groups.append(tuple(names[order[i]] for i in range(start, end + 1)))
            last_end = end
    return tuple(groups)


def _intervals(
    names: Sequence[str], per_pipeline: PerPipeline
) -> tuple[PipelineInterval, ...]:
    """IC bootstrap **marginaux** : chaque pipeline sur ses valeurs valides."""
    intervals: list[PipelineInterval] = []
    for name in names:
        valid = [float(v) for v in per_pipeline[name] if v is not None]
        if not valid:
            continue
        lower, upper = bootstrap_ci(valid)
        intervals.append(
            PipelineInterval(
                pipeline=name,
                mean=sum(valid) / len(valid),
                lower=lower,
                upper=upper,
                n_documents=len(valid),
            )
        )
    return tuple(intervals)


def _payload(
    metric: str,
    per_pipeline: PerPipeline,
    omnibus: Omnibus,
    p_holm: float | None,
    family_size: int,
    alpha: float,
    with_intervals: bool,
) -> InferencePayload:
    names = omnibus.names
    k = len(names)
    supported = k >= 2 and len(omnibus.complete) >= MIN_SUPPORT
    means: list[float] = []
    mean_ranks: tuple[PipelineRank, ...] = ()
    if supported:
        ranks = stats.rankdata(np.asarray(omnibus.complete), axis=1)
        means = [float(value) for value in ranks.mean(axis=0)]
        mean_ranks = tuple(
            PipelineRank(pipeline=name, mean_rank=rank)
            for rank, name in sorted(zip(means, names, strict=True))
        )
    critical_distance: float | None = None
    q_alpha: float | None = None
    groups: tuple[tuple[str, ...], ...] = ()
    pairwise: tuple[PairwiseDifference, ...] = ()
    if omnibus.test == "friedman" and p_holm is not None and p_holm < alpha:
        n_blocks = len(omnibus.complete)
        q_alpha = nemenyi_critical_value(k, alpha)
        critical_distance = q_alpha * math.sqrt(k * (k + 1) / (6.0 * n_blocks))
        groups = _cd_groups(names, means, critical_distance)
        pairwise = tuple(
            PairwiseDifference(
                a=names[i],
                b=names[j],
                rank_gap=abs(means[i] - means[j]),
                significant=abs(means[i] - means[j]) > critical_distance,
            )
            for i in range(k)
            for j in range(i + 1, k)
        )
    return InferencePayload(
        metric=metric,
        alpha=alpha,
        n_documents=len(omnibus.complete),
        test=omnibus.test,
        not_computed=omnibus.not_computed,
        p_value=omnibus.p_value,
        p_holm=p_holm,
        family_size=family_size if omnibus.test is not None else 0,
        critical_distance=critical_distance,
        q_alpha=q_alpha,
        mean_ranks=mean_ranks,
        cd_groups=groups,
        pairwise=pairwise,
        intervals=(
            _intervals(names, per_pipeline) if with_intervals and supported else ()
        ),
    )


def inference_analyses(
    entries: Sequence[tuple[str, str, PerPipeline]],
    *,
    alpha: float = ALPHA,
    with_intervals: bool = True,
) -> list[Analysis]:
    """Une ``Analysis`` par (vue, métrique, séries) — la famille de Holm est
    l'ensemble des tests **calculés** parmi ``entries`` (le run entier)."""
    tests = [omnibus_test(per_pipeline) for _, _, per_pipeline in entries]
    computed = [i for i, test in enumerate(tests) if test.p_value is not None]
    adjusted = dict(
        zip(
            computed,
            holm_adjusted([tests[i].p_value or 0.0 for i in computed]),
            strict=True,
        )
    )
    return [
        Analysis(
            scope="corpus",
            view=view,
            payload=_payload(
                metric,
                per_pipeline,
                tests[i],
                adjusted.get(i),
                len(computed),
                alpha,
                with_intervals,
            ),
        )
        for i, (view, metric, per_pipeline) in enumerate(entries)
    ]


__all__ = [
    "ALPHA",
    "MIN_SUPPORT",
    "Omnibus",
    "bootstrap_ci",
    "holm_adjusted",
    "inference_analyses",
    "nemenyi_critical_value",
    "omnibus_test",
]
