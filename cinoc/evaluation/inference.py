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

IC : **bootstrap du chiffre affiché**. L'agrégat d'un pipeline est le ratio
**micro** Σ(v·w)/Σw (``micro_ratio`` — le runner l'écrit au tableau ; pour un
taux d'erreur, Σ erreurs / Σ longueurs de référence) : on rééchantillonne les
**documents** avec remise et on recalcule ce même ratio (Davison & Hinkley
1997, *Bootstrap Methods and their Application*, ch. 2 et 5 : bootstrap d'un
estimateur par quotient, unités = documents, pas caractères — les erreurs d'une
page ne sont pas indépendantes). Intervalle **percentile** (Efron & Tibshirani
1993, *An Introduction to the Bootstrap*, ch. 13), quantiles à interpolation
linéaire, ``N_RESAMPLES`` tirages, graine fixe → mêmes octets à chaque run
(invariant §12). Un document de poids nul ne pèse rien dans le point : il
n'entre pas non plus dans le rééchantillonnage. Vectorisé par numpy
(``default_rng``, par lots de mémoire bornée) ; seul coût non négligeable de
l'inférence, calculé en mode détaillé seulement (analyse ``inference``).
"""

from __future__ import annotations

import math
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

#: Poids de micro-agrégation (``MetricScore.support`` par document), alignés
#: sur ``PerPipeline`` — le dénominateur de la métrique.
PerWeights = Mapping[str, Sequence[int]]

#: (vue, métrique, valeurs, poids) — une ligne de la famille de Holm.
InferenceEntry = tuple[str, str, PerPipeline, PerWeights]

#: Rééchantillons du bootstrap. Un intervalle de quantiles à 95 % en demande
#: de l'ordre de 1 000 à 2 000 (Efron & Tibshirani 1993, contre 25 à 200 pour
#: une erreur type) : 2 000, que la vectorisation rend bon marché.
N_RESAMPLES = 2000

#: Graine fixe : mêmes tirages, mêmes octets, à chaque run.
BOOTSTRAP_SEED = 42

#: Indices tirés par lot (≈ 8 Mo en int64) : la mémoire reste bornée quelle
#: que soit la taille du corpus.
_BATCH_ELEMENTS = 1 << 20


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


def micro_ratio(values: Sequence[float], weights: Sequence[int]) -> float | None:
    """Σ(v·w)/Σw — l'agrégat **affiché** d'une métrique (``None`` sans poids).

    Une seule définition, lue par le runner (tableau) et par l'IC (son point).
    """
    total_weight = sum(weights)
    if total_weight <= 0:
        return None
    return sum(v * w for v, w in zip(values, weights, strict=True)) / total_weight


def bootstrap_batch(n_documents: int) -> int:
    """Rééchantillons tirés par lot : au plus ``_BATCH_ELEMENTS`` indices."""
    return max(1, _BATCH_ELEMENTS // max(1, n_documents))


def micro_ratio_ci(
    values: Sequence[float],
    weights: Sequence[int],
    *,
    n_resamples: int = N_RESAMPLES,
    ci: float = 0.95,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """IC percentile du ratio micro, documents rééchantillonnés avec remise.

    ``weights`` doivent être > 0 (un poids nul ne pèse pas dans le point, il
    n'est pas rééchantillonné : ``_intervals`` l'écarte). Tirages
    ``default_rng(seed).integers(0, n, (lot, n))`` lot après lot — la forme de
    ``scipy.stats.bootstrap(paired=True, batch=bootstrap_batch(n))``.
    """
    if not values or len(values) != len(weights) or min(weights) <= 0:
        raise EvaluationError("micro_ratio_ci : poids > 0 alignés sur les valeurs.")
    weight = np.asarray(weights, dtype=np.float64)
    errors = np.asarray(values, dtype=np.float64) * weight
    n = len(values)
    rng = np.random.default_rng(seed)
    batch = bootstrap_batch(n)
    ratios = np.concatenate(
        [
            errors[index].sum(axis=1) / weight[index].sum(axis=1)
            for index in (
                rng.integers(0, n, (min(batch, n_resamples - start), n))
                for start in range(0, n_resamples, batch)
            )
        ]
    )
    half_alpha = (1.0 - ci) / 2.0
    lower, upper = np.quantile(ratios, [half_alpha, 1.0 - half_alpha])
    return (float(lower), float(upper))


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
    names: Sequence[str], per_pipeline: PerPipeline, weights: PerWeights
) -> tuple[PipelineInterval, ...]:
    """IC **marginaux** du ratio micro : chaque pipeline sur ses documents notés
    de poids non nul — exactement ceux qui font son agrégat."""
    intervals: list[PipelineInterval] = []
    for name in names:
        pairs = [
            (float(value), int(weight))
            for value, weight in zip(per_pipeline[name], weights[name], strict=True)
            if value is not None and weight > 0
        ]
        if not pairs:
            continue
        values = [value for value, _ in pairs]
        positive = [weight for _, weight in pairs]
        point = micro_ratio(values, positive)
        if point is None:  # pragma: no cover -- poids > 0 par construction
            continue
        lower, upper = micro_ratio_ci(values, positive)
        intervals.append(
            PipelineInterval(
                pipeline=name,
                value=point,
                lower=lower,
                upper=upper,
                n_documents=len(pairs),
            )
        )
    return tuple(intervals)


def _payload(
    metric: str,
    per_pipeline: PerPipeline,
    weights: PerWeights,
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
            _intervals(names, per_pipeline, weights)
            if with_intervals and supported
            else ()
        ),
    )


def inference_analyses(
    entries: Sequence[InferenceEntry],
    *,
    alpha: float = ALPHA,
    with_intervals: bool = True,
) -> list[Analysis]:
    """Une ``Analysis`` par (vue, métrique, séries) — la famille de Holm est
    l'ensemble des tests **calculés** parmi ``entries`` (le run entier)."""
    tests = [omnibus_test(per_pipeline) for _, _, per_pipeline, _ in entries]
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
                weights,
                tests[i],
                adjusted.get(i),
                len(computed),
                alpha,
                with_intervals,
            ),
        )
        for i, (view, metric, per_pipeline, weights) in enumerate(entries)
    ]


__all__ = [
    "ALPHA",
    "BOOTSTRAP_SEED",
    "MIN_SUPPORT",
    "N_RESAMPLES",
    "InferenceEntry",
    "Omnibus",
    "bootstrap_batch",
    "holm_adjusted",
    "inference_analyses",
    "micro_ratio",
    "micro_ratio_ci",
    "nemenyi_critical_value",
    "omnibus_test",
]
