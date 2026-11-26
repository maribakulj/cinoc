"""Métriques inter-moteurs **statistiques** (scipy) : significativité.

Le scalaire ``significance_p`` est la p **brute** du test omnibus — **Wilcoxon**
signé-rangs (2 pipelines) ou **Friedman** (≥ 3) — sur les **cas complets**
(documents où *tous* les pipelines ont une valeur). ``None`` si le test n'est
pas calculé (support insuffisant, un seul pipeline, aucune différence). Le
calcul est celui de ``evaluation.inference.omnibus_test`` : un seul calcul,
deux lectures — ce scalaire, et le payload ``inference`` qui y ajoute le nom
du test, la p corrigée de Holm, le post-hoc et le motif d'absence.
"""

from __future__ import annotations

from cinoc.evaluation.context import CrossEngineContext
from cinoc.evaluation.inference import omnibus_test
from cinoc.evaluation.metric import CrossEngineMetric, cross_engine_metric


@cross_engine_metric(
    name="significance_p",
    description="p-value brute d'une différence entre pipelines (Wilcoxon/Friedman).",
)
def significance(ctx: CrossEngineContext) -> tuple[float | None, int]:
    result = omnibus_test(ctx.per_pipeline)
    return result.p_value, len(result.complete)


#: Socle de métriques inter-moteurs, collecté explicitement par le registre.
CROSS_ENGINE_METRICS: tuple[CrossEngineMetric, ...] = (significance,)

__all__ = ["CROSS_ENGINE_METRICS", "significance"]
