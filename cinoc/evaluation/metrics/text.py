"""Métriques de l'axe texte : CER, WER, MER, taux d'insertion et de suppression,
exactitudes.

Chaque métrique rend sa **statistique suffisante** (``evaluation.statistics``) :
les comptes (S, D, I, n_réf) **canoniques** — parmi les alignements de coût
minimal, celui qui maximise S (P1) — pour les taux d'édition et le MER,
(erreurs, n_réf) pour les exactitudes. La valeur d'un document et celle du
corpus sont la même finalisation de ces comptes (K1).

Implémentations **déterministes** (journal D-007), déléguées à ``rapidfuzz``
pour les deux noyaux coûteux — distance et alignement. Ce n'est pas une nouvelle
dépendance : ``rapidfuzz`` est dans la liste blanche de la couche 3 et déjà
importé par ``evaluation.diagnostics``. Garder ici deux implémentations écrites
à la main coûtait un facteur 13 sur la distance, et rendait l'alignement
inutilisable sur une page entière (11 s et ~420 Mo de matrice Python).
- CER = distance d'édition au **caractère** / longueur de référence ;
- WER = distance d'édition au **mot** / nombre de mots de référence ;
- MER (Match Error Rate) = erreurs / (erreurs + correspondances), au mot.

``jiwer`` sert d'**oracle de parité** (tests, dépendance *dev*) — jamais importé
par le code de production. Cas dégénérés (référence vide) explicites.

S + D + I est la distance de Levenshtein exacte : CER et WER restent ceux de
jiwer (au corpus, dès que Σ n_réf > 0). Le départage canonique des ex æquo
écarte en revanche D et I (donc ``ins_rate``, ``del_rate`` et le MER) de
jiwer et de ``rapidfuzz.editops`` — écart **voulu** (M1).
"""

from __future__ import annotations

from collections.abc import Sequence

from rapidfuzz.distance import Levenshtein

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation import statistics as st
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, document_metric
from cinoc.evaluation.statistics import EditCounts, ErrorCounts, canonical_edit_counts
from cinoc.formats.text import get_builtin_profile

#: Repli diplomatique minimal (NFC + ſ long → s), appliqué symétriquement par
#: ``cer_diplo``. L'écart ``cer − cer_diplo`` = part d'erreur **purement
#: typographique** (un ſ long mal lu cesse de compter comme une erreur).
_DIPLOMATIC = get_builtin_profile("minimal")


def _edit_distance(
    reference: Sequence[object], hypothesis: Sequence[object]
) -> int:
    """Distance de Levenshtein exacte sur deux séquences.

    **Pourquoi ce n'est plus écrit ici.** Ce module a d'abord porté une version
    à deux lignes (mémoire linéaire, O(n×m) *itérations Python*), puis une
    version bit-parallèle (Myers, 1999) parce que la première mettait plus de
    deux minutes sur une page de presse. Myers a réglé ce cas — 1,0 s au lieu de
    130 — mais restait du Python : ``rapidfuzz`` fait le même calcul en C, et
    rend le **même entier**, en 0,076 s. Soit un facteur 13 pour rien.

    La raison de l'avoir écrit à la main était la règle « sans dépendance » du
    journal D-007. Elle ne tient plus : ``rapidfuzz`` figure dans la liste
    blanche de la couche 3 (``CLAUDE.md`` §3) et ``evaluation.diagnostics``
    l'importe déjà. Maintenir une seconde implémentation de la même chose, plus
    lente, n'était plus un choix d'architecture mais un oubli.

    Parité vérifiée sur une page réelle, sur des séquences de mots, et sur
    300 couples aléatoires : aucun écart.
    """
    if isinstance(reference, str) and isinstance(hypothesis, str):
        return int(Levenshtein.distance(reference, hypothesis))
    # ``rapidfuzz`` accepte toute séquence d'éléments hachables — c'est le cas
    # du WER, qui compare des listes de mots.
    return int(Levenshtein.distance(list(reference), list(hypothesis)))


def _text_pair(ctx: DocContext) -> tuple[str, str]:
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError(
            "métrique texte : reference et hypothesis doivent être du texte."
        )
    return ctx.reference, ctx.hypothesis


def _word_counts(ctx: DocContext) -> EditCounts:
    """(S, D, I, n_réf) canoniques au mot — WER, MER, ``ins_rate``, ``del_rate``."""
    reference, hypothesis = _text_pair(ctx)
    return canonical_edit_counts(reference.split(), hypothesis.split())


@document_metric(
    name="cer",
    finalize=st.edit_rate,
    terms=st.edit_terms,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ESTABLISHED,
    unit=MetricUnit.CHARACTER,
    description="Character Error Rate : distance d'édition / longueur de référence.",
    higher_is_better=False,
    tags=frozenset({"text", "edit_distance"}),
)
def cer(ctx: DocContext) -> EditCounts:
    reference, hypothesis = _text_pair(ctx)
    return canonical_edit_counts(reference, hypothesis)


@document_metric(
    name="cer_diplo",
    finalize=st.edit_rate,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.CHARACTER,
    description="CER diplomatique : CER après repli ſ long→s (NFC), des deux côtés.",
    higher_is_better=False,
    tags=frozenset({"text", "edit_distance", "philology"}),
)
def cer_diplomatic(ctx: DocContext) -> EditCounts:
    reference, hypothesis = _text_pair(ctx)
    return canonical_edit_counts(
        _DIPLOMATIC.normalize(reference), _DIPLOMATIC.normalize(hypothesis)
    )


@document_metric(
    name="wer",
    finalize=st.edit_rate,
    terms=st.edit_terms,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ESTABLISHED,
    unit=MetricUnit.WORD,
    description="Word Error Rate : distance d'édition au mot / nombre de mots de réf.",
    higher_is_better=False,
    tags=frozenset({"text", "edit_distance", "word"}),
)
def wer(ctx: DocContext) -> EditCounts:
    return _word_counts(ctx)


@document_metric(
    name="mer",
    finalize=st.match_error_rate,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ESTABLISHED,
    unit=MetricUnit.WORD,
    description="Match Error Rate : erreurs / (erreurs + correspondances), au mot.",
    higher_is_better=False,
    tags=frozenset({"text", "edit_distance", "word"}),
)
def mer(ctx: DocContext) -> EditCounts:
    return _word_counts(ctx)


@document_metric(
    name="del_rate",
    finalize=st.deletion_rate,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.WORD,
    description="Taux de suppression au mot : mots de réf. omis / mots de réf.",
    higher_is_better=False,
    tags=frozenset({"text", "word", "error_profile"}),
)
def deletion_rate(ctx: DocContext) -> EditCounts:
    return _word_counts(ctx)


@document_metric(
    name="ins_rate",
    finalize=st.insertion_rate,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.WORD,
    description="Taux d'insertion au mot : mots parasites ajoutés / mots de réf.",
    higher_is_better=False,
    tags=frozenset({"text", "word", "error_profile"}),
)
def insertion_rate(ctx: DocContext) -> EditCounts:
    return _word_counts(ctx)


@document_metric(
    name="char_accuracy",
    finalize=st.accuracy,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.CHARACTER,
    description="Exactitude caractère : 1 − CER, bornée [0, 1] (lecture ICDAR).",
    higher_is_better=True,
    tags=frozenset({"text", "edit_distance", "accuracy"}),
)
def char_accuracy(ctx: DocContext) -> ErrorCounts:
    """``max(0, 1 − e/n)`` sur (distance, longueur de réf.) : au corpus, le
    plancher s'applique aux comptes cumulés — ``1 − CER_micro`` tant que le
    CER du corpus ne dépasse pas 1 (B1)."""
    reference, hypothesis = _text_pair(ctx)
    return ErrorCounts(
        errors=_edit_distance(reference, hypothesis), reference_length=len(reference)
    )


@document_metric(
    name="word_accuracy",
    finalize=st.accuracy,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.ADAPTED,
    unit=MetricUnit.WORD,
    description="Exactitude mot : 1 − WER, bornée [0, 1] (lecture ICDAR).",
    higher_is_better=True,
    tags=frozenset({"text", "edit_distance", "word", "accuracy"}),
)
def word_accuracy(ctx: DocContext) -> ErrorCounts:
    """``max(0, 1 − e/n)`` au mot (cf. ``char_accuracy``)."""
    reference, hypothesis = _text_pair(ctx)
    ref_words, hyp_words = reference.split(), hypothesis.split()
    return ErrorCounts(
        errors=_edit_distance(ref_words, hyp_words), reference_length=len(ref_words)
    )


#: Socle de métriques texte, collecté explicitement par le registre.
TEXT_METRICS: tuple[DocumentMetric, ...] = (
    cer,
    cer_diplomatic,
    char_accuracy,
    word_accuracy,
    wer,
    mer,
    deletion_rate,
    insertion_rate,
)

__all__ = [
    "TEXT_METRICS",
    "cer",
    "cer_diplomatic",
    "char_accuracy",
    "deletion_rate",
    "insertion_rate",
    "mer",
    "wer",
    "word_accuracy",
]
