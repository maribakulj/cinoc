"""Bag-of-Words : précision / rappel / F1 sur le **multiset de tokens** (mots),
indépendants de l'ordre — lecture « recherche / rappel d'information ».

Pour chaque token, le **vrai positif** est ``min(compte_réf, compte_hyp)`` :

- ``tp = Σ min(compte_réf, compte_hyp)`` sur tous les tokens distincts ;
- ``précision = tp / |hyp|`` (part des mots produits qui sont justes) ;
- ``rappel    = tp / |réf|`` (part des mots attendus retrouvés) ;
- ``F1 = 2·tp / (2·tp + fp + fn)``, avec ``fp = |hyp| − tp`` et ``fn = |réf| − tp``.

La statistique d'un document est ``(tp, fp, fn)`` (``MatchCounts``) : au
corpus, F1, précision et rappel se calculent sur les comptes cumulés (M3), et
non comme une moyenne de F1 par document.

Insensible à l'ordre des mots (sac de mots), déterministe. Utile quand le
document sera **cherché en plein texte** : un mot juste compte, où qu'il soit.
"""

from __future__ import annotations

from collections import Counter

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation import statistics as st
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, document_metric
from cinoc.evaluation.statistics import MatchCounts


def _tokens(ctx: DocContext) -> tuple[list[str], list[str]]:
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError(
            "bag-of-words : reference et hypothesis doivent être du texte."
        )
    return ctx.reference.split(), ctx.hypothesis.split()


def _counts(ctx: DocContext) -> MatchCounts:
    """(tp, fp, fn) : ``tp = Σ min(compte_réf, compte_hyp)`` — intersection des
    multisets de tokens."""
    ref, hyp = _tokens(ctx)
    tp = sum((Counter(ref) & Counter(hyp)).values())
    return MatchCounts(tp=tp, fp=len(hyp) - tp, fn=len(ref) - tp)


@document_metric(
    name="bow_precision",
    finalize=st.precision,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.WORD,
    description="Bag-of-Words — précision : mots justes produits / mots produits.",
    higher_is_better=True,
    tags=frozenset({"text", "word", "search", "bag_of_words"}),
)
def bow_precision(ctx: DocContext) -> MatchCounts:
    """``tp / |hyp|`` ; indéfinie sans mot produit. Corpus : ``Σtp / Σ|hyp|``."""
    return _counts(ctx)


@document_metric(
    name="bow_recall",
    finalize=st.recall,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.WORD,
    description="Bag-of-Words — rappel : mots attendus retrouvés / mots attendus.",
    higher_is_better=True,
    tags=frozenset({"text", "word", "search", "bag_of_words"}),
)
def bow_recall(ctx: DocContext) -> MatchCounts:
    """``tp / |réf|`` ; indéfini sans mot attendu. Corpus : ``Σtp / Σ|réf|``."""
    return _counts(ctx)


@document_metric(
    name="bow_f1",
    finalize=st.f1,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.WORD,
    description="Bag-of-Words — F1 : moyenne harmonique précision/rappel des mots.",
    higher_is_better=True,
    tags=frozenset({"text", "word", "search", "bag_of_words"}),
)
def bow_f1(ctx: DocContext) -> MatchCounts:
    """F1 ; corpus : ``F1(Σtp, Σfp, Σfn)`` (M3) — et non une moyenne de F1
    par document. Indéfini quand ni la référence ni la sortie n'ont de mot."""
    return _counts(ctx)


#: Socle « sac de mots » (recherche plein-texte), collecté par le registre.
BOW_METRICS: tuple[DocumentMetric, ...] = (bow_precision, bow_recall, bow_f1)

__all__ = ["BOW_METRICS", "bow_f1", "bow_precision", "bow_recall"]
