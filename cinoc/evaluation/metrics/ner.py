"""Scalaires ``ner_f1`` et ``ner_f1_exact`` : F1 sur les entités nommées (couche 3).

Jonction ``(ENTITIES, ENTITIES)`` que le registre type-driven accepte sans
modification. Le calcul (appariement IoU + **reprojection R14** des spans
hypothèse en coordonnées GT) vit dans ``evaluation.ner`` ; ici on n'expose que
les comptes ``(tp, fp, fn)`` du document (``MatchCounts``) : au corpus, le F1
est ``F1(Σtp, Σfp, Σfn)`` (M3). Un document dont la GT ne porte aucune entité
contribue ses faux positifs ; son F1 vaut 0 s'il en invente, il est indéfini
(dénominateur nul) s'il n'invente rien.

``ner_f1_exact`` (D-288) : même appariement, mais un apparié ne compte juste
que si sa forme écrite est celle de la GT ; sinon il est à la fois manqué et
ajouté (FN + FP). ``ner_f1`` ne lit pas la forme : « Montfort » lu « Montfert »
au même endroit y compte juste.
"""

from __future__ import annotations

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation import statistics as st
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, document_metric
from cinoc.evaluation.ner import EntitySet, compute_ner
from cinoc.evaluation.statistics import MatchCounts


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
    finalize=st.f1,
    input_types=(ArtifactType.ENTITIES, ArtifactType.ENTITIES),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.ENTITY,
    description=(
        "F1 global sur entités nommées appariées par empan (IoU ≥ 0,5, labels "
        "casefold, spans reprojetés en coordonnées GT) ; forme écrite non lue."
    ),
    higher_is_better=True,
    tags=frozenset({"ner", "downstream", "entities"}),
)
def ner_f1(ctx: DocContext) -> MatchCounts:
    reference, hypothesis = _entity_pair(ctx)
    counts = compute_ner(reference, hypothesis)
    return MatchCounts(tp=counts.tp, fp=counts.fp, fn=counts.fn)


@document_metric(
    name="ner_f1_exact",
    finalize=st.f1,
    input_types=(ArtifactType.ENTITIES, ArtifactType.ENTITIES),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.ENTITY,
    description=(
        "F1 global sur entités nommées dont la forme écrite est exacte : "
        "appariement de ner_f1, puis forme identique à celle de la GT."
    ),
    higher_is_better=True,
    tags=frozenset({"ner", "downstream", "entities"}),
)
def ner_f1_exact(ctx: DocContext) -> MatchCounts:
    reference, hypothesis = _entity_pair(ctx)
    counts = compute_ner(reference, hypothesis)
    wrong = counts.tp - counts.tp_exact
    return MatchCounts(tp=counts.tp_exact, fp=counts.fp + wrong, fn=counts.fn + wrong)


#: Socle NER, collecté explicitement par le registre.
NER_METRICS: tuple[DocumentMetric, ...] = (ner_f1, ner_f1_exact)

__all__ = ["NER_METRICS", "ner_f1", "ner_f1_exact"]
