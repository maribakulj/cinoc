"""Scalaires ``ner_f1`` et ``ner_f1_exact`` : F1 sur les entités nommées (couche 3).

Jonction ``(ENTITIES, ENTITIES)`` que le registre type-driven accepte sans
modification. Le calcul (appariement IoU + **reprojection R14** des spans
hypothèse en coordonnées GT) vit dans ``evaluation.ner`` ; ici on n'expose que
le F1 global comme ``Observation`` (poids = nombre d'entités GT → micro-agrégat
au niveau corpus). ``None`` si la GT du document ne porte aucune entité (non
applicable — jamais un faux zéro).

``ner_f1_exact`` (D-288) : même appariement, mais un apparié ne compte juste
que si sa forme écrite est celle de la GT ; sinon il est à la fois manqué et
ajouté (FN + FP). ``ner_f1`` ne lit pas la forme : « Montfort » lu « Montfert »
au même endroit y compte juste.
"""

from __future__ import annotations

from cinoc.domain.artifacts import ArtifactType
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation, document_metric
from cinoc.evaluation.ner import EntitySet, compute_ner, prf


def _entity_pair(ctx: DocContext) -> tuple[EntitySet, EntitySet]:
    if not isinstance(ctx.reference, EntitySet) or not isinstance(
        ctx.hypothesis, EntitySet
    ):
        raise EvaluationError(
            "ner_f1 : reference et hypothesis doivent être des EntitySet."
        )
    return ctx.reference, ctx.hypothesis


@document_metric(
    name="ner_f1",
    input_types=(ArtifactType.ENTITIES, ArtifactType.ENTITIES),
    description=(
        "F1 global sur entités nommées appariées par empan (IoU ≥ 0,5, labels "
        "casefold, spans reprojetés en coordonnées GT) ; forme écrite non lue."
    ),
    higher_is_better=True,
    tags=frozenset({"ner", "downstream", "entities"}),
)
def ner_f1(ctx: DocContext) -> Observation | None:
    reference, hypothesis = _entity_pair(ctx)
    if not reference.entities:
        return None  # GT sans entité → non applicable
    counts = compute_ner(reference, hypothesis)
    _precision, _recall, f1 = prf(counts.tp, counts.fp, counts.fn)
    return Observation(value=f1, weight=len(reference.entities))


@document_metric(
    name="ner_f1_exact",
    input_types=(ArtifactType.ENTITIES, ArtifactType.ENTITIES),
    description=(
        "F1 global sur entités nommées dont la forme écrite est exacte : "
        "appariement de ner_f1, puis forme identique à celle de la GT."
    ),
    higher_is_better=True,
    tags=frozenset({"ner", "downstream", "entities"}),
)
def ner_f1_exact(ctx: DocContext) -> Observation | None:
    reference, hypothesis = _entity_pair(ctx)
    if not reference.entities:
        return None
    counts = compute_ner(reference, hypothesis)
    wrong = counts.tp - counts.tp_exact
    _precision, _recall, f1 = prf(
        counts.tp_exact, counts.fp + wrong, counts.fn + wrong
    )
    return Observation(value=f1, weight=len(reference.entities))


#: Socle NER, collecté explicitement par le registre.
NER_METRICS: tuple[DocumentMetric, ...] = (ner_f1, ner_f1_exact)

__all__ = ["NER_METRICS", "ner_f1", "ner_f1_exact"]
