"""Scalaires ``air``/``hcpr`` : préservation & apport net d'archaïsmes (couche 3).

Deux scalaires par-document, jumeaux de ``mufi_err``/``diacritic_err`` au registre
(colonnes ``by_engine``), mais bâtis sur une **liste configurable** de caractères
archaïques (cf. :mod:`cinoc.evaluation.archaic`). La liste n'est pas une entrée du
``DocContext`` (qui n'est qu'une paire de textes) : elle est **liée à la métrique
à l'enregistrement** par une fabrique (fermeture). Le registre enregistre ``air``
sur la liste par défaut (``archaic_core``) ; l'app **relie** ``air`` et enregistre
``hcpr`` sur la liste réellement configurée d'un run (cf.
:mod:`cinoc.app.orchestrator`).

- ``air`` (apport net) — *plus bas = mieux*, **actif par défaut** (Q4).
- ``hcpr`` (préservation) — *plus haut = mieux*, **visible seulement sur liste
  configurée** (anti-colonne-jumelle de ``mufi_err`` sur corpus médiéval).
"""

from __future__ import annotations

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation.archaic import (
    DEFAULT_ARCHAIC_LIST,
    air_observation,
    hcpr_observation,
    resolve_archaic_list,
)
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation, document_metric


def _text_pair(ctx: DocContext, name: str) -> tuple[str, str]:
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError(
            f"{name} : reference et hypothesis doivent être du texte."
        )
    return ctx.reference, ctx.hypothesis


def make_air_metric(chars: frozenset[str]) -> DocumentMetric:
    """Métrique ``air`` liée à une liste de caractères archaïques."""

    @document_metric(
        name="air",
        input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
        category=MetricCategory.EXPLORATORY,
        unit=MetricUnit.CHARACTER,
        description=(
            "Apport net d'archaïsmes : part des caractères archaïques de la "
            "sortie qui sont insérés (absents à leur place dans la GT) — "
            "sur-historicisation."
        ),
        higher_is_better=False,
        tags=frozenset({"text", "philology", "alignment", "archaic"}),
    )
    def air(ctx: DocContext) -> Observation | None:
        reference, hypothesis = _text_pair(ctx, "air")
        return air_observation(reference, hypothesis, chars)

    return air


def make_hcpr_metric(chars: frozenset[str]) -> DocumentMetric:
    """Métrique ``hcpr`` liée à une liste de caractères archaïques."""

    @document_metric(
        name="hcpr",
        input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
        category=MetricCategory.EXPLORATORY,
        unit=MetricUnit.CHARACTER,
        description=(
            "Taux de préservation des caractères archaïques de la GT (liste "
            "configurée) dans la sortie."
        ),
        higher_is_better=True,
        tags=frozenset({"text", "philology", "alignment", "archaic"}),
    )
    def hcpr(ctx: DocContext) -> Observation | None:
        reference, hypothesis = _text_pair(ctx, "hcpr")
        return hcpr_observation(reference, hypothesis, chars)

    return hcpr


#: ``air`` sur la liste par défaut — socle du registre (``hcpr`` est opt-in,
#: relié par l'app sur la liste configurée d'un run).
ARCHAIC_METRICS: tuple[DocumentMetric, ...] = (
    make_air_metric(resolve_archaic_list(DEFAULT_ARCHAIC_LIST).chars),
)

__all__ = ["ARCHAIC_METRICS", "make_air_metric", "make_hcpr_metric"]
