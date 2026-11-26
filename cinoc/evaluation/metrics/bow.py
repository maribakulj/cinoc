"""Bag-of-Words : précision / rappel / F1 sur le **multiset de tokens** (mots),
indépendants de l'ordre — lecture « recherche / rappel d'information ».

Pour chaque token, le **vrai positif** est ``min(compte_réf, compte_hyp)`` :

- ``tp = Σ min(compte_réf, compte_hyp)`` sur tous les tokens distincts ;
- ``précision = tp / |hyp|`` (part des mots produits qui sont justes) ;
- ``rappel    = tp / |réf|`` (part des mots attendus retrouvés) ;
- ``F1 = 2·P·R / (P + R)``.

Insensible à l'ordre des mots (sac de mots), déterministe. Utile quand le
document sera **cherché en plein texte** : un mot juste compte, où qu'il soit.
"""

from __future__ import annotations

from collections import Counter

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation, document_metric


def _tokens(ctx: DocContext) -> tuple[list[str], list[str]]:
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError(
            "bag-of-words : reference et hypothesis doivent être du texte."
        )
    return ctx.reference.split(), ctx.hypothesis.split()


def _true_positives(ref: list[str], hyp: list[str]) -> int:
    """``Σ min(compte_réf, compte_hyp)`` — intersection des multisets de tokens."""
    return sum((Counter(ref) & Counter(hyp)).values())


@document_metric(
    name="bow_precision",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.WORD,
    description="Bag-of-Words — précision : mots justes produits / mots produits.",
    higher_is_better=True,
    tags=frozenset({"text", "word", "search", "bag_of_words"}),
)
def bow_precision(ctx: DocContext) -> Observation:
    """Poids = ``|hyp|`` → l'agrégat micro vaut ``Σtp / Σ|hyp|``."""
    ref, hyp = _tokens(ctx)
    tp = _true_positives(ref, hyp)
    value = tp / len(hyp) if hyp else (1.0 if not ref else 0.0)
    return Observation(value=value, weight=len(hyp))


@document_metric(
    name="bow_recall",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.WORD,
    description="Bag-of-Words — rappel : mots attendus retrouvés / mots attendus.",
    higher_is_better=True,
    tags=frozenset({"text", "word", "search", "bag_of_words"}),
)
def bow_recall(ctx: DocContext) -> Observation:
    """Poids = ``|réf|`` → l'agrégat micro vaut ``Σtp / Σ|réf|``."""
    ref, hyp = _tokens(ctx)
    tp = _true_positives(ref, hyp)
    value = tp / len(ref) if ref else 1.0
    return Observation(value=value, weight=len(ref))


@document_metric(
    name="bow_f1",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.WORD,
    description="Bag-of-Words — F1 : moyenne harmonique précision/rappel des mots.",
    higher_is_better=True,
    tags=frozenset({"text", "word", "search", "bag_of_words"}),
)
def bow_f1(ctx: DocContext) -> Observation:
    """F1 par document ; agrégat corpus = **moyenne pondérée par la taille**
    (poids ``|réf|``) — pas le F1 micro exact (non linéaire), choix documenté."""
    ref, hyp = _tokens(ctx)
    tp = _true_positives(ref, hyp)
    precision = tp / len(hyp) if hyp else (1.0 if not ref else 0.0)
    recall = tp / len(ref) if ref else 1.0
    denom = precision + recall
    f1 = 2 * precision * recall / denom if denom else 0.0
    return Observation(value=f1, weight=len(ref))


#: Socle « sac de mots » (recherche plein-texte), collecté par le registre.
BOW_METRICS: tuple[DocumentMetric, ...] = (bow_precision, bow_recall, bow_f1)

__all__ = ["BOW_METRICS", "bow_f1", "bow_precision", "bow_recall"]
