"""Métrique de conformité HIPE : ``cmer`` — MER au **caractère** (couche 3).

Le scorer HIPE-OCRepair classe sur le Match Error Rate caractère
``(S+D+I)/(H+S+D+I)`` — **borné [0, 1]**, contrairement au CER classique qu'un
modèle génératif fait dépasser 100 % (SPEC_HIPE §1.1). ``mer`` (mot) existe déjà
au socle ; ``cmer`` est son pendant caractère. Comptes S/D/I **canoniques**
(``statistics.canonical_edit_counts`` : parmi les alignements de coût minimal,
celui qui maximise S, P1).

Même formule que le scorer ; mêmes comptes que lui (``jiwer.process_characters``)
sauf sur les alignements ex æquo, où jiwer garde une suppression et une
insertion là où le départage canonique voit une substitution (« ab »/« ba » :
1,0 contre 0,667). Écart voulu et écrit (M1) : sans départage canonique, les
comptes dépendraient de l'ordre de calcul de la bibliothèque.
"""

from __future__ import annotations

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation import statistics as st
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, document_metric
from cinoc.evaluation.statistics import EditCounts, canonical_edit_counts


@document_metric(
    name="cmer",
    finalize=st.match_error_rate,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ESTABLISHED,
    unit=MetricUnit.CHARACTER,
    description=(
        "Match Error Rate caractère : (S+D+I)/(H+S+D+I), borné [0,1] — "
        "la métrique de classement du scorer HIPE-OCRepair."
    ),
    higher_is_better=False,
    tags=frozenset({"text", "conformity"}),
)
def cmer(ctx: DocContext) -> EditCounts:
    """``edits / (longueur_référence + insertions)`` sur les comptes (S, D, I)
    **canoniques** ; deux textes vides → indéfini (``zero_denominator``).

    Au corpus, la même finalisation des comptes cumulés : somme des comptes
    puis ratio, comme le ``cmer_micro`` du scorer (SPEC_HIPE §4.1). Le
    départage canonique des ex æquo (max S, P1) peut écarter I — donc le
    dénominateur — de celui du scorer (jiwer) : écart voulu (M1).
    """
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError("cmer : reference et hypothesis doivent être du texte.")
    return canonical_edit_counts(ctx.reference, ctx.hypothesis)


#: Métriques de conformité, collectées explicitement par le registre.
CONFORMITY_METRICS: tuple[DocumentMetric, ...] = (cmer,)

__all__ = ["CONFORMITY_METRICS", "cmer"]
