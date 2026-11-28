"""Agrégats d'un pipeline : deux qualités, couverture, macro (couche 3).

Pour chaque (pipeline × vue × métrique), à partir des observations de chaque
document (``evaluation.scoring``) :

- la qualité **conditionnelle** — la somme des statistiques des observations
  **complètes** (axes 1 à 3 au vert), finalisée : le micro, la métrique
  calculée sur les comptes cumulés (K1) ;
- la qualité **opérationnelle** — la somme de ce que l'utilisateur reçoit :
  partielles et tronquées telles que produites, échecs comme une sortie vide ;
- le **macro** — la moyenne des scalaires sur D^M_P (documents dont la
  *référence* définit le scalaire, R5), par document ou par grappe selon la
  pondération déclarée par le corpus (B3) ;
- la **couverture** — ``expected`` (les applicables) et ``coverage`` (les
  attendus non entrés, par motif), la même pour les deux qualités.

Aucune statistique inférentielle ici : ce sont des agrégats **métrologiques**
(``CONTRATS.md`` § 2.1 a, c, f), corrects pour toute observation.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations
from math import fsum
from typing import Literal

from cinoc.evaluation.comparison import (
    ComparisonPayload,
    GlobalSupport,
    InventionPair,
    InventionPayload,
    PairSupport,
)
from cinoc.evaluation.metric import DocumentMetric
from cinoc.evaluation.result import MetricScore
from cinoc.evaluation.statistics import (
    Counts,
    combine,
    invented_units,
    reference_defines,
)


def is_complete(score: MetricScore) -> bool:
    """Observation **complète** : applicable, disponible, valide, et mesurée."""
    return (
        score.applicability == "applicable"
        and score.availability == "available"
        and score.validity == "valid"
        and score.stat is not None
    )


def complete_statistic(score: MetricScore) -> Counts | None:
    """La statistique d'une observation complète (``None`` sinon)."""
    return score.stat if is_complete(score) else None


def coverage_of(scores: Sequence[MetricScore]) -> dict[str, int]:
    """``{motif : nombre d'attendus non entrés}`` — le motif est la valeur de
    l'axe 2 ou 3 qui a écarté l'observation (``step_failed``,
    ``partial_output``…). Les attendus sont les ``applicable`` (axe 1)."""
    motifs: Counter[str] = Counter()
    for score in scores:
        if score.applicability != "applicable" or is_complete(score):
            continue
        if score.availability not in (None, "available"):
            motifs[score.availability] += 1
        elif score.validity not in (None, "valid"):
            motifs[score.validity] += 1
    return dict(sorted(motifs.items()))


def expected_of(scores: Sequence[MetricScore]) -> int:
    """Nombre d'observations attendues : les applicables (axe 1)."""
    return sum(score.applicability == "applicable" for score in scores)


def macro_of(
    metric: DocumentMetric,
    items: Sequence[tuple[int, Counts]],
    clusters: Sequence[str],
    weighting: str,
) -> tuple[float | None, int | None]:
    """``(macro, |D^M_P|)`` des observations ``items`` (index de document,
    statistique) : la moyenne des scalaires des documents dont la **référence**
    définit le scalaire.

    ``weighting == "cluster"`` : moyenne des moyennes par grappe (un document
    sans grappe est la sienne). Somme exacte (``fsum``), une division. ``None``
    pour une métrique sans macro (dénominateur d'hypothèse) ; ``(None, 0)`` si
    D^M_P est vide.
    """
    if not metric.macro:
        return None, None
    values: dict[str, list[float]] = {}
    count = 0
    for index, stat in items:
        if not reference_defines(stat):
            continue
        scalar = metric.finalize(stat).value
        if scalar is None:
            continue
        count += 1
        key = clusters[index] if weighting == "cluster" else str(index)
        values.setdefault(key, []).append(scalar)
    if not count:
        return None, 0
    if weighting == "cluster":
        means = [fsum(group) / len(group) for group in values.values()]
        return fsum(means) / len(means), count
    return fsum(v for group in values.values() for v in group) / count, count


def publish(
    metric: DocumentMetric,
    items: Sequence[tuple[int, Counts]],
    scores: Sequence[MetricScore],
    clusters: Sequence[str],
    weighting: str,
) -> MetricScore:
    """L'agrégat d'une qualité : la finalisation de la somme de ``items``.

    ``support`` = |D^μ_P| : le nombre d'observations dont la statistique entre
    dans **cet** agrégat ; ``expected`` et ``coverage`` décrivent les attendus
    de ``scores`` et sont les mêmes pour les deux qualités.
    """
    macro, macro_support = macro_of(metric, items, clusters, weighting)
    combined = combine([stat for _, stat in items])
    base = MetricScore(
        metric=metric.name,
        support=len(items),
        expected=expected_of(scores),
        coverage=coverage_of(scores),
        macro=macro,
        macro_support=macro_support,
    )
    if combined is None:
        return base
    scalar = metric.finalize(combined)
    return base.model_copy(
        update={
            "value": scalar.value,
            "stat": combined,
            "scalar_reason": scalar.reason,
            "untruncated_error_rate": scalar.untruncated_error_rate,
        }
    )


#: Statistiques par document d'un pipeline, alignées sur le corpus : ``None``
#: = non entrée (axes 1 à 3 non au vert).
Series = Mapping[str, Sequence[Counts | None]]


#: ``(D^μ, D^M, micro par pipeline, macro par pipeline)`` d'un support.
_Support = tuple[
    tuple[str, ...], tuple[str, ...], dict[str, float | None], dict[str, float | None]
]


def _micro(metric: DocumentMetric, stats: Sequence[Counts]) -> float | None:
    combined = combine(stats)
    return None if combined is None else metric.finalize(combined).value


def _macro(
    metric: DocumentMetric,
    items: Sequence[tuple[int, Counts]],
    clusters: Sequence[str],
    weighting: str,
) -> float | None:
    return macro_of(metric, items, clusters, weighting)[0]


def _support(
    metric: DocumentMetric,
    pipelines: Sequence[str],
    series: Series,
    document_ids: Sequence[str],
    clusters: Sequence[str],
    weighting: str,
) -> _Support:
    """``(D^μ, D^M, micro, macro)`` de ``pipelines`` sur leur intersection."""
    common = [
        index
        for index in range(len(document_ids))
        if all(series[p][index] is not None for p in pipelines)
    ]
    first = pipelines[0]
    macro_documents = [
        index
        for index in common
        if reference_defines(series[first][index])  # type: ignore[arg-type]
    ]
    micro: dict[str, float | None] = {}
    macro: dict[str, float | None] = {}
    for pipeline in pipelines:
        stats = [series[pipeline][i] for i in common]
        micro[pipeline] = _micro(metric, [s for s in stats if s is not None])
        items = [
            (i, series[pipeline][i])
            for i in macro_documents
            if series[pipeline][i] is not None
        ]
        macro[pipeline] = _macro(
            metric, [(i, s) for i, s in items if s is not None], clusters, weighting
        )
    return (
        tuple(document_ids[i] for i in common),
        tuple(document_ids[i] for i in macro_documents),
        micro,
        macro,
    )


def comparison_payload(
    metric: DocumentMetric,
    pipelines: Sequence[str],
    series: Series,
    document_ids: Sequence[str],
    clusters: Sequence[str],
    weighting: str,
) -> ComparisonPayload | None:
    """Supports apparié (par paire) et global d'une (vue × métrique).

    ``pipelines`` : ceux que la vue voit (aucun ``not_in_view``). ``None`` sous
    deux pipelines : il n'y a rien à apparier.
    """
    if len(pipelines) < 2:
        return None

    def build_pair(a: str, b: str) -> PairSupport:
        micro_docs, macro_docs, micro, macro = _support(
            metric, [a, b], series, document_ids, clusters, weighting
        )
        return PairSupport(
            a=a,
            b=b,
            micro_documents=micro_docs,
            macro_documents=macro_docs,
            micro=micro,
            macro=macro,
        )

    pairs = tuple(build_pair(a, b) for a, b in combinations(pipelines, 2))
    micro_docs, macro_docs, micro, macro = _support(
        metric, list(pipelines), series, document_ids, clusters, weighting
    )
    sign = -1.0 if metric.spec.higher_is_better else 1.0
    defined = [p for p in pipelines if micro[p] is not None]
    ranking = tuple(
        sorted(defined, key=lambda p: (sign * micro[p], p))  # type: ignore[operator]
    )
    payload = ComparisonPayload(
        metric=metric.name,
        pairs=pairs,
        global_support=GlobalSupport(
            micro_documents=micro_docs,
            macro_documents=macro_docs,
            micro=micro,
            macro=macro,
            ranking=ranking,
        ),
    )
    return payload


def invention_payload(
    metric: DocumentMetric,
    pipelines: Sequence[str],
    series: Series,
    document_ids: Sequence[str],
    without_reference: Sequence[bool],
    applicable: Mapping[str, Sequence[bool]],
) -> InventionPayload | None:
    """L'invention hors référence d'une (vue × métrique), ou ``None``.

    ``without_reference[i]`` : la **référence** du document ``i`` ne définit pas
    le scalaire (fixé par la référence, jamais par une sortie) ; ``applicable``
    : par pipeline, les attendus. ``None`` : métrique sans macro (la famille n'a
    pas de macro qui puisse ne pas voir l'invention), moins de deux pipelines,
    ou aucune page sans référence.
    """
    pages = [i for i, empty in enumerate(without_reference) if empty]
    if len(pipelines) < 2 or not pages or not metric.macro:
        return None
    unit = _unit(series, pipelines, pages)

    def count(stat: Counts | None) -> int:
        found = None if stat is None else invented_units(stat)
        return 0 if found is None else found[1]

    pair_rows = []
    for a, b in combinations(pipelines, 2):
        shared = [
            i for i in pages if series[a][i] is not None and series[b][i] is not None
        ]
        pair_rows.append(
            InventionPair(
                a=a,
                b=b,
                documents=tuple(document_ids[i] for i in shared),
                invented=(
                    {}
                    if unit is None
                    else {
                        a: sum(count(series[a][i]) for i in shared),
                        b: sum(count(series[b][i]) for i in shared),
                    }
                ),
            )
        )
    coverage = {
        p: (
            sum(series[p][i] is not None for i in pages if applicable[p][i]),
            sum(1 for i in pages if applicable[p][i]),
        )
        for p in pipelines
    }
    payload = InventionPayload(
        metric=metric.name, unit=unit, pairs=tuple(pair_rows), coverage=coverage
    )
    return payload


def _unit(
    series: Series, pipelines: Sequence[str], pages: Sequence[int]
) -> Literal["insertions", "false_positives"] | None:
    """L'unité inventée de la famille (la statistique d'une page quelconque)."""
    for pipeline in pipelines:
        for index in pages:
            stat = series[pipeline][index]
            if stat is not None:
                found = invented_units(stat)
                return None if found is None else found[0]  # type: ignore[return-value]
    return None


__all__ = [
    "Series",
    "comparison_payload",
    "complete_statistic",
    "coverage_of",
    "expected_of",
    "invention_payload",
    "is_complete",
    "macro_of",
    "publish",
]
