"""Métriques co-localisées (fiche + statistique + finalisation) + décorateurs **purs**.

- ``DocumentMetric`` (par-document) : calcule, sur un ``DocContext``, la
  **statistique suffisante** de sa famille (``evaluation.statistics``) et
  déclare sa **finalisation** ; la valeur du document et l'agrégat micro du
  corpus passent par cette même finalisation (K1, ``CONTRATS.md`` § 2.1 a).
- ``CrossEngineMetric`` (inter-moteurs) : opère sur un ``CrossEngineContext`` et
  renvoie ``(valeur, support)``.

Les décorateurs **construisent** l'objet sans muter de registre global (→ import
sans effet de bord, CLAUDE.md §7) ; la collecte est explicite.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricSpec, MetricUnit
from cinoc.evaluation.context import CrossEngineContext, DocContext
from cinoc.evaluation.statistics import Counts, Scalar, ScalarReason


@dataclass(frozen=True)
class Observation:
    """Mesure par-document : la statistique, et son scalaire finalisé.

    ``value`` est ``finalize(stat)`` ; ``None`` quand la finalisation est
    indéfinie (``scalar_reason`` dit pourquoi) — la statistique, elle,
    contribue toujours au micro.
    """

    stat: Counts
    value: float | None
    scalar_reason: ScalarReason | None = None
    untruncated_error_rate: float | None = None


def observe(stat: Counts, finalize: Callable[[Any], Scalar]) -> Observation:
    """L'observation d'une statistique sous sa finalisation."""
    scalar = finalize(stat)
    return Observation(
        stat=stat,
        value=scalar.value,
        scalar_reason=scalar.reason,
        untruncated_error_rate=scalar.untruncated_error_rate,
    )


#: Une métrique par-document rend sa statistique (``None`` si non applicable).
StatisticFn = Callable[[DocContext], Counts | None]

#: Une métrique inter-moteurs renvoie ``(valeur, support)`` (``None`` si N/A).
CrossEngineFn = Callable[[CrossEngineContext], tuple[float | None, int]]


@dataclass(frozen=True)
class DocumentMetric:
    """Métrique par-document : fiche, statistique et finalisation co-localisées.

    ``terms`` : (numérateur, dénominateur) du ratio micro quand le
    dénominateur est fixé par la **référence** (taux d'édition) — l'entrée de
    l'intervalle du micro. ``None`` : dénominateur d'hypothèse ou finalisation
    non linéaire ; l'inférence du micro est alors « non estimable » (B9c).
    """

    spec: MetricSpec
    statistic: StatisticFn
    #: Prend la statistique de **sa** famille (``EditCounts`` pour ``cer``…).
    finalize: Callable[[Any], Scalar]
    terms: Callable[[Any], tuple[int, int]] | None = None

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def input_types(self) -> tuple[ArtifactType, ArtifactType]:
        return self.spec.input_types

    def fn(self, ctx: DocContext) -> Observation | None:
        """Observation du document, ou ``None`` si la métrique ne s'y applique pas."""
        stat = self.statistic(ctx)
        return None if stat is None else observe(stat, self.finalize)


@dataclass(frozen=True)
class CrossEngineMetric:
    """Métrique inter-moteurs : compare les pipelines entre eux sur une métrique."""

    name: str
    description: str
    fn: CrossEngineFn


def document_metric(
    *,
    name: str,
    input_types: tuple[ArtifactType, ArtifactType],
    category: MetricCategory,
    unit: MetricUnit,
    finalize: Callable[[Any], Scalar],
    terms: Callable[[Any], tuple[int, int]] | None = None,
    description: str = "",
    higher_is_better: bool = False,
    tags: frozenset[str] = frozenset(),
) -> Callable[[StatisticFn], DocumentMetric]:
    """Construit une ``DocumentMetric`` depuis sa fonction de statistique (pur).

    ``category`` et ``unit`` sont **requises** (D-289) : la déclaration unique
    de ce que vaut la métrique et de ce que compte sa statistique ;
    ``finalize``, aussi : la valeur d'un document et celle du corpus en
    sortent toutes deux.
    """

    def decorate(fn: StatisticFn) -> DocumentMetric:
        return DocumentMetric(
            spec=MetricSpec(
                name=name,
                input_types=input_types,
                description=description,
                higher_is_better=higher_is_better,
                tags=tags,
                category=category,
                unit=unit,
            ),
            statistic=fn,
            finalize=finalize,
            terms=terms,
        )

    return decorate


def cross_engine_metric(
    *, name: str, description: str = ""
) -> Callable[[CrossEngineFn], CrossEngineMetric]:
    """Construit une ``CrossEngineMetric`` depuis une fonction (pur, sans effet)."""

    def decorate(fn: CrossEngineFn) -> CrossEngineMetric:
        return CrossEngineMetric(name=name, description=description, fn=fn)

    return decorate


__all__ = [
    "CrossEngineFn",
    "CrossEngineMetric",
    "DocumentMetric",
    "Observation",
    "StatisticFn",
    "cross_engine_metric",
    "document_metric",
    "observe",
]
