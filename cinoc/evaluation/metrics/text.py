"""Métriques de l'axe texte : CER, WER, MER.

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

``jiwer`` reste l'oracle de parité des tests, et les valeurs n'ont pas bougé :
les deux noyaux calculent la **même** distance de Levenshtein exacte.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from cinoc.domain.artifacts import ArtifactType
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation, document_metric
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


@dataclass(frozen=True)
class _Alignment:
    """Décompte d'un alignement optimal : correspondances + erreurs typées."""

    hits: int
    substitutions: int
    deletions: int
    insertions: int

    @property
    def edits(self) -> int:
        return self.substitutions + self.deletions + self.insertions


def _align(reference: Sequence[object], hypothesis: Sequence[object]) -> _Alignment:
    """Décompte d'un alignement optimal — correspondances et erreurs typées.

    **Pourquoi ce n'est plus une matrice.** La version précédente allouait
    ``(n+1)×(m+1)`` listes Python et les parcourait deux fois. Sur une page de
    presse — 7 246 mots de chaque côté — cela fait 53 millions de cases, soit
    ~420 Mo de pointeurs et 11 s **par appel**. Or ``mer``, ``del_rate`` et
    ``ins_rate`` l'appellent chacun : trois fois cela par document. Ces trois
    métriques étaient donc inutilisables sur le corpus même qu'elles visent, et
    le disaient par une lenteur, jamais par un message.

    ``rapidfuzz`` rend directement le script d'édition, d'où se comptent les
    quatre catégories. Même alignement optimal, mêmes nombres, mémoire linéaire.
    """
    ref, hyp = list(reference), list(hypothesis)
    hits = subs = dels = ins = 0
    for operation in Levenshtein.opcodes(ref, hyp):
        longueur_ref = operation.src_end - operation.src_start
        longueur_hyp = operation.dest_end - operation.dest_start
        if operation.tag == "equal":
            hits += longueur_ref
        elif operation.tag == "replace":
            subs += longueur_ref
        elif operation.tag == "delete":
            dels += longueur_ref
        else:  # "insert"
            ins += longueur_hyp
    return _Alignment(hits=hits, substitutions=subs, deletions=dels, insertions=ins)


def _error_rate(edits: int, reference_length: int) -> float:
    """``edits / reference_length`` ; référence vide → 0.0 si exact, sinon 1.0."""
    if reference_length == 0:
        return 0.0 if edits == 0 else 1.0
    return edits / reference_length


def _text_pair(ctx: DocContext) -> tuple[str, str]:
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError(
            "métrique texte : reference et hypothesis doivent être du texte."
        )
    return ctx.reference, ctx.hypothesis


@document_metric(
    name="cer",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description="Character Error Rate : distance d'édition / longueur de référence.",
    higher_is_better=False,
    tags=frozenset({"text", "edit_distance"}),
)
def cer(ctx: DocContext) -> Observation:
    reference, hypothesis = _text_pair(ctx)
    edits = _edit_distance(reference, hypothesis)
    return Observation(
        value=_error_rate(edits, len(reference)), weight=len(reference)
    )


@document_metric(
    name="cer_diplo",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description="CER diplomatique : CER après repli ſ long→s (NFC), des deux côtés.",
    higher_is_better=False,
    tags=frozenset({"text", "edit_distance", "philology"}),
)
def cer_diplomatic(ctx: DocContext) -> Observation:
    reference, hypothesis = _text_pair(ctx)
    ref = _DIPLOMATIC.normalize(reference)
    hyp = _DIPLOMATIC.normalize(hypothesis)
    edits = _edit_distance(ref, hyp)
    return Observation(value=_error_rate(edits, len(ref)), weight=len(ref))


@document_metric(
    name="wer",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description="Word Error Rate : distance d'édition au mot / nombre de mots de réf.",
    higher_is_better=False,
    tags=frozenset({"text", "edit_distance", "word"}),
)
def wer(ctx: DocContext) -> Observation:
    reference, hypothesis = _text_pair(ctx)
    ref_words, hyp_words = reference.split(), hypothesis.split()
    edits = _edit_distance(ref_words, hyp_words)
    return Observation(
        value=_error_rate(edits, len(ref_words)), weight=len(ref_words)
    )


@document_metric(
    name="mer",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description="Match Error Rate : erreurs / (erreurs + correspondances), au mot.",
    higher_is_better=False,
    tags=frozenset({"text", "edit_distance", "word"}),
)
def mer(ctx: DocContext) -> Observation:
    reference, hypothesis = _text_pair(ctx)
    alignment = _align(reference.split(), hypothesis.split())
    total = alignment.hits + alignment.edits
    return Observation(
        value=alignment.edits / total if total else 0.0, weight=total
    )


@document_metric(
    name="del_rate",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description="Taux de suppression au mot : mots de réf. omis / mots de réf.",
    higher_is_better=False,
    tags=frozenset({"text", "word", "error_profile"}),
)
def deletion_rate(ctx: DocContext) -> Observation:
    reference, hypothesis = _text_pair(ctx)
    ref_words = reference.split()
    alignment = _align(ref_words, hypothesis.split())
    return Observation(
        value=_error_rate(alignment.deletions, len(ref_words)),
        weight=len(ref_words),
    )


@document_metric(
    name="ins_rate",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description="Taux d'insertion au mot : mots parasites ajoutés / mots de réf.",
    higher_is_better=False,
    tags=frozenset({"text", "word", "error_profile"}),
)
def insertion_rate(ctx: DocContext) -> Observation:
    reference, hypothesis = _text_pair(ctx)
    ref_words = reference.split()
    alignment = _align(ref_words, hypothesis.split())
    return Observation(
        value=_error_rate(alignment.insertions, len(ref_words)),
        weight=len(ref_words),
    )


@document_metric(
    name="char_accuracy",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description="Exactitude caractère : 1 − CER, bornée [0, 1] (lecture ICDAR).",
    higher_is_better=True,
    tags=frozenset({"text", "edit_distance", "accuracy"}),
)
def char_accuracy(ctx: DocContext) -> Observation:
    """``max(0, 1 − CER)`` ; poids = longueur de réf. → l'agrégat micro vaut
    exactement ``1 − CER_micro`` (sauf plancher 0 quand un doc a CER > 1)."""
    reference, hypothesis = _text_pair(ctx)
    rate = _error_rate(_edit_distance(reference, hypothesis), len(reference))
    return Observation(value=max(0.0, 1.0 - rate), weight=len(reference))


@document_metric(
    name="word_accuracy",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description="Exactitude mot : 1 − WER, bornée [0, 1] (lecture ICDAR).",
    higher_is_better=True,
    tags=frozenset({"text", "edit_distance", "word", "accuracy"}),
)
def word_accuracy(ctx: DocContext) -> Observation:
    """``max(0, 1 − WER)`` ; poids = nb de mots de réf. (cf. ``char_accuracy``)."""
    reference, hypothesis = _text_pair(ctx)
    ref_words, hyp_words = reference.split(), hypothesis.split()
    rate = _error_rate(_edit_distance(ref_words, hyp_words), len(ref_words))
    return Observation(value=max(0.0, 1.0 - rate), weight=len(ref_words))


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
