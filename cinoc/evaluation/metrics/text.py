"""Métriques de l'axe texte : CER, WER, MER.

Implémentations **déterministes et sans dépendance** (journal D-007) :
- CER = distance d'édition au **caractère** / longueur de référence ;
- WER = distance d'édition au **mot** / nombre de mots de référence ;
- MER (Match Error Rate) = erreurs / (erreurs + correspondances), au mot.

``jiwer`` sert d'**oracle de parité** (tests, dépendance *dev*) — jamais importé
par le code de production. Cas dégénérés (référence vide) explicites.

Coût : le caractère reste en deux lignes (mémoire linéaire) ; seule la matrice
complète de ``_align`` (pour MER) tourne sur des **mots**, peu nombreux.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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
    """Distance de Levenshtein sur deux séquences — bit-parallèle (Myers, 1999).

    **Pourquoi pas la matrice.** La version à deux lignes est O(n×m) *itérations
    Python*. Sur une ligne de texte c'est instantané ; sur une page de presse
    entière — 25 000 caractères contre 30 000 — c'est 750 millions de tours de
    boucle, soit plus de deux minutes par appel et par métrique. Un banc de
    48 documents y passait la nuit sans jamais rendre la main.

    Myers encode une colonne entière de la matrice dans les bits d'un entier :
    les entiers Python étant de taille arbitraire, une page tient dans un seul,
    et le coût retombe à O(n) opérations sur grands entiers — mesuré ~60× plus
    rapide à 10 000 caractères, et l'écart croît avec la taille.

    Le résultat est **exactement** celui de la matrice ; le test de parité contre
    ``jiwer`` continue de le prouver.
    """
    n, m = len(reference), len(hypothesis)
    if n == 0 or m == 0:
        return max(n, m)
    # Le motif encodé est le plus court : c'est lui qui occupe les bits.
    if n > m:
        reference, hypothesis = hypothesis, reference
        n, m = m, n

    equivalences: dict[object, int] = {}
    for position, token in enumerate(reference):
        equivalences[token] = equivalences.get(token, 0) | (1 << position)

    masque = (1 << n) - 1
    dernier = 1 << (n - 1)
    positifs, negatifs = masque, 0
    score = n

    for token in hypothesis:
        egaux = equivalences.get(token, 0)
        xv = egaux | negatifs
        xh = (((egaux & positifs) + positifs) ^ positifs) | egaux
        porte_plus = negatifs | ~(xh | positifs)
        porte_moins = positifs & xh
        if porte_plus & dernier:
            score += 1
        elif porte_moins & dernier:
            score -= 1
        porte_plus = ((porte_plus << 1) | 1) & masque
        porte_moins = (porte_moins << 1) & masque
        positifs = (porte_moins | ~(xv | porte_plus)) & masque
        negatifs = porte_plus & xv
    return score


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
    """Alignement complet (matrice + backtrace) — pour MER, sur des **mots**."""
    n, m = len(reference), len(hypothesis)
    matrix = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        matrix[i][0] = i
    for j in range(m + 1):
        matrix[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j - 1] + cost,
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
            )
    hits = subs = dels = ins = 0
    i, j = n, m
    while i > 0 or j > 0:
        if (
            i > 0
            and j > 0
            and reference[i - 1] == hypothesis[j - 1]
            and matrix[i][j] == matrix[i - 1][j - 1]
        ):
            hits += 1
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and matrix[i][j] == matrix[i - 1][j - 1] + 1:
            subs += 1
            i, j = i - 1, j - 1
        elif i > 0 and matrix[i][j] == matrix[i - 1][j] + 1:
            dels += 1
            i -= 1
        else:
            ins += 1
            j -= 1
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
