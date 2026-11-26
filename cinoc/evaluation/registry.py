"""Registre de métriques **par-document** (type-driven) + **inter-moteurs**.

Unique et **instanciable** : il ne s'auto-peuple pas à l'import —
``register_default_metrics`` est appelé **explicitement** par l'app (CLAUDE.md §7).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import cache

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricSpec
from cinoc.evaluation.metric import CrossEngineMetric, DocumentMetric


class MetricRegistry:
    """Associe des noms (par-doc et inter-moteurs) à leurs fiches + fonctions."""

    def __init__(self) -> None:
        self._document: dict[str, DocumentMetric] = {}
        self._cross_engine: dict[str, CrossEngineMetric] = {}

    def register_document_metric(self, metric: DocumentMetric) -> None:
        """Enregistre (ou remplace) une métrique par-document. Idempotent."""
        self._document[metric.name] = metric

    def register_cross_engine_metric(self, metric: CrossEngineMetric) -> None:
        """Enregistre (ou remplace) une métrique inter-moteurs. Idempotent."""
        self._cross_engine[metric.name] = metric

    def document_metric(self, name: str) -> DocumentMetric | None:
        return self._document.get(name)

    def for_input_types(
        self, reference: ArtifactType, hypothesis: ArtifactType
    ) -> tuple[DocumentMetric, ...]:
        """Métriques par-document applicables à la signature ``(ref, hyp)``."""
        return tuple(
            metric
            for metric in self._document.values()
            if metric.input_types == (reference, hypothesis)
        )

    def cross_engine_metrics(self) -> tuple[CrossEngineMetric, ...]:
        """Métriques inter-moteurs enregistrées, triées par nom (déterministe)."""
        return tuple(self._cross_engine[name] for name in sorted(self._cross_engine))

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._document))

    def established(self, names: Iterable[str]) -> tuple[str, ...]:
        """Ceux de ``names`` dont la métrique est **établie**, dans leur ordre.

        Seules celles-là entrent dans les tests de significativité et donc
        dans la famille de Holm (D-289) : une métrique adaptée ou exploratoire
        reste au diagnostic. Un nom inconnu du registre n'est pas établi.
        """
        return tuple(
            name
            for name in names
            if (metric := self._document.get(name)) is not None
            and metric.spec.category is MetricCategory.ESTABLISHED
        )


def register_default_metrics(registry: MetricRegistry) -> None:
    """Collecte explicite du socle de métriques (aucun effet de bord à l'import)."""
    from cinoc.evaluation.metrics.archaic import ARCHAIC_METRICS
    from cinoc.evaluation.metrics.bow import BOW_METRICS
    from cinoc.evaluation.metrics.conformity import CONFORMITY_METRICS
    from cinoc.evaluation.metrics.diacritics import DIACRITIC_METRICS
    from cinoc.evaluation.metrics.diagnostics import DIAGNOSTIC_METRICS
    from cinoc.evaluation.metrics.flexible import FLEXIBLE_METRICS
    from cinoc.evaluation.metrics.layout import LAYOUT_METRICS
    from cinoc.evaluation.metrics.ner import NER_METRICS
    from cinoc.evaluation.metrics.philology import PHILOLOGY_METRICS
    from cinoc.evaluation.metrics.stats import CROSS_ENGINE_METRICS
    from cinoc.evaluation.metrics.structured_data import STRUCTURED_DATA_METRICS
    from cinoc.evaluation.metrics.text import TEXT_METRICS

    for document in (
        *TEXT_METRICS,
        *FLEXIBLE_METRICS,
        *BOW_METRICS,
        *DIACRITIC_METRICS,
        *PHILOLOGY_METRICS,
        *ARCHAIC_METRICS,
        *LAYOUT_METRICS,
        *DIAGNOSTIC_METRICS,
        *CONFORMITY_METRICS,
        *STRUCTURED_DATA_METRICS,
        *NER_METRICS,
    ):
        registry.register_document_metric(document)
    for cross in CROSS_ENGINE_METRICS:
        registry.register_cross_engine_metric(cross)


@cache
def metric_specs() -> Mapping[str, MetricSpec]:
    """Fiche (``MetricSpec``) de **chaque** métrique du socle, par nom.

    La lecture des déclarations pour qui n'exécute rien — le rapport, qui
    affiche catégorie et unité à côté du chiffre. ``hcpr``, que l'app ne
    relie que sur une liste archaïque configurée, y figure sur la liste par
    défaut : la liste change les caractères comptés, ni la catégorie ni
    l'unité. Les métriques ne sont pas un point d'extension (§3) : ce
    catalogue est complet.
    """
    from cinoc.evaluation.archaic import DEFAULT_ARCHAIC_LIST, resolve_archaic_list
    from cinoc.evaluation.metrics.archaic import make_hcpr_metric

    registry = MetricRegistry()
    register_default_metrics(registry)
    registry.register_document_metric(
        make_hcpr_metric(resolve_archaic_list(DEFAULT_ARCHAIC_LIST).chars)
    )
    return {
        name: metric.spec
        for name in registry.names()
        if (metric := registry.document_metric(name)) is not None
    }


__all__ = ["MetricRegistry", "metric_specs", "register_default_metrics"]
