"""Statistiques suffisantes par famille de métriques (K1, ``CONTRATS.md`` § 2.1 a).

Une observation n'est plus un ratio et un poids : c'est la **statistique
suffisante** de sa famille — des comptes entiers. Elle se **combine** par
addition exacte (associative, commutative, d'élément neutre nul) et se
**finalise** en un scalaire. La valeur d'un document et l'agrégat micro du
corpus passent par la **même** finalisation, appliquée à la statistique du
document ou à la somme des statistiques : le micro n'est plus Σv·w/Σw, il est
la métrique calculée sur les comptes cumulés (R1 : entiers, une seule
conversion flottante, à la finalisation).

Pas d'algèbre générique : une petite classe par famille, chacune avec ses
consommateurs. La finalisation est déclarée **par métrique** (``cer`` et
``ins_rate`` partagent ``EditCounts`` et ne se finalisent pas pareil).

- ``EditCounts`` (S, D, I, n_réf) **canoniques** — taux d'édition et MER :
  ``cer``, ``cer_diplo``, ``wer``, ``ins_rate``, ``del_rate``, ``mer``,
  ``cmer`` ;
- ``ErrorCounts`` (erreurs, n_réf) — exactitudes (``char_accuracy``,
  ``word_accuracy``, ``fca``) et texte par région (``region_cer``,
  ``line_identity_cer``) ;
- ``MatchCounts`` (tp, fp, fn) — appariement P/R/F : ``ner_f1``,
  ``ner_f1_exact``, ``region_detection``, ``bow_*`` ;
- ``Proportion`` (k, n) — proportions (``searchability``, ``diacritic_err``,
  ``mufi_err``, ``hcpr``, ``air``, ``numseq_*``, ``unanchored_trigrams``,
  couvertures) et désaccord d'ordre (``reading_order_tau`` : discordantes,
  paires).

Un scalaire **indéfini** (dénominateur nul : référence vide…) n'empêche pas
la statistique de contribuer au micro : une page blanche apporte ses
insertions au numérateur du CER du corpus (M1) ; son scalaire est ``None``,
motif ``zero_denominator``.

**Conversions (R1).** *Vers l'exact* : toutes les composantes de ces quatre
familles sont des **comptes** entiers, aucun flottant n'y entre. Le seul
flottant entrant qu'une statistique de la couche additionne est la confiance
d'un jeton (calibration, ``evaluation.calibration``) : il est lu comme la
valeur **exacte** de son binaire IEEE 754, ``Fraction(x)`` — sans arrondi
décimal, qui serait une convention de plus (combien de chiffres ?) et
changerait deux jetons distincts en un même nombre. Une IoU (régions, NER)
ne sert qu'à **décider** un appariement, jamais à être sommée ; son seuil
exact relève de la tranche 4 (P17). *Vers le flottant publié* : **une**
conversion par valeur, arrondie au plus proche (pair en cas d'égalité) —
``int / int`` et ``float(Fraction)`` le sont tous deux en Python ; aucun
résultat intermédiaire n'est un flottant.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from fractions import Fraction
from typing import Annotated, Literal, NamedTuple, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cinoc.evaluation._alignment import canonical_counts
from cinoc.evaluation.errors import EvaluationError

#: Pourquoi un scalaire est indéfini alors que la statistique existe (axe 4).
ScalarReason = Literal["zero_denominator"]


class _Counts(BaseModel):
    """Base des statistiques : comptes figés, sans champ libre."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EditCounts(_Counts):
    """(S, D, I, n_réf) **canoniques** : parmi les alignements de coût
    minimal, celui qui maximise S (P1). H + S + D = n_réf."""

    family: Literal["edit_counts"] = "edit_counts"
    substitutions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    insertions: int = Field(ge=0)
    reference_length: int = Field(ge=0)

    @model_validator(mode="after")
    def _within_reference(self) -> Self:
        if self.substitutions + self.deletions > self.reference_length:
            raise ValueError("S + D excède la longueur de la référence")
        return self

    @property
    def edits(self) -> int:
        """S + D + I : la distance d'édition."""
        return self.substitutions + self.deletions + self.insertions

    @property
    def alignment_path(self) -> Literal["canonical"]:
        """La convention d'alignement de ces comptes : ``canonical`` (P1, max S).

        Une **propriété**, pas un champ : cette classe n'a pas d'autre
        convention (``family: "edit_counts"`` la nomme dans le JSON), et un
        champ de plus est un octet de plus par statistique. Les analyses qui
        nomment les éditions, elles, portent la leur (``rapidfuzz``).
        """
        return "canonical"


class ErrorCounts(_Counts):
    """(erreurs, n_réf) : exactitudes (plancher au corpus, B1) et texte par
    région (ratio non borné)."""

    family: Literal["error_counts"] = "error_counts"
    errors: int = Field(ge=0)
    reference_length: int = Field(ge=0)



class MatchCounts(_Counts):
    """(tp, fp, fn) d'un appariement : F1, précision, rappel."""

    family: Literal["match_counts"] = "match_counts"
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)



class Proportion(_Counts):
    """(k, n) : ``count`` unités sur ``total`` (k ≤ n)."""

    family: Literal["proportion"] = "proportion"
    count: int = Field(ge=0)
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        if self.count > self.total:
            raise ValueError("une proportion compte au plus son total")
        return self



#: Une statistique, quelle que soit sa famille.
Counts = EditCounts | ErrorCounts | MatchCounts | Proportion

#: La statistique d'une observation, telle qu'écrite dans ``RunResult``.
Statistic = Annotated[Counts, Field(discriminator="family")]


def combine(stats: Sequence[Counts]) -> Counts | None:
    """Somme exacte, composante par composante, des statistiques d'**une**
    famille (toutes leurs composantes sont des comptes) ; ``None`` si vide.
    Associative et commutative : l'ordre des documents n'y change rien."""
    if not stats:
        return None
    family = type(stats[0])
    if any(type(stat) is not family for stat in stats):
        raise EvaluationError("combine : statistiques de familles différentes.")
    names = [name for name in family.model_fields if name != "family"]
    return family(
        **{name: sum(getattr(stat, name) for stat in stats) for name in names}
    )


def reference_defines(stat: Counts) -> bool:
    """La **référence** définit le scalaire de ``stat`` : n_réf > 0, ou
    tp + fn > 0 (R5). Ce critère — pas la valeur d'un pipeline — fait D^M :
    le même support pour tous les pipelines."""
    if isinstance(stat, EditCounts | ErrorCounts):
        return stat.reference_length > 0
    if isinstance(stat, MatchCounts):
        return stat.tp + stat.fn > 0
    return stat.total > 0


def invented_units(stat: Counts) -> tuple[str, int] | None:
    """``(unité, nombre)`` **inventé** par l'hypothèse (``CONTRATS.md`` § 2.1 c,
    N3) : les insertions d'un taux d'édition ou d'une exactitude (sur une page
    sans référence, S = D = 0 : les erreurs sont les insertions), les faux
    positifs d'un appariement. ``None`` pour une proportion : sa statistique
    ne compte aucune unité de l'hypothèse (« non définie »)."""
    if isinstance(stat, EditCounts):
        return "insertions", stat.insertions
    if isinstance(stat, ErrorCounts):
        return "insertions", stat.errors
    if isinstance(stat, MatchCounts):
        return "false_positives", stat.fp
    return None


class Scalar(NamedTuple):
    """Finalisation d'une statistique : le scalaire, ou le motif de son absence.

    ``exact`` est le **rationnel** dont ``value`` est l'unique conversion
    flottante (arrondi au plus proche) : le macro moyenne ces rationnels, jamais
    des flottants déjà arrondis (D5, R1). ``untruncated_error_rate`` n'est
    rempli que par les exactitudes : le taux d'erreur e/n **avant** le plancher
    max(0, ·), publié à côté (B1).
    """

    value: float | None
    reason: ScalarReason | None = None
    untruncated_error_rate: float | None = None
    exact: Fraction | None = None


def _ratio(numerator: int, denominator: int) -> Scalar:
    # ``int / int`` est arrondi correctement : une seule conversion.
    if denominator == 0:
        return Scalar(None, "zero_denominator")
    return Scalar(numerator / denominator, exact=Fraction(numerator, denominator))


def edit_rate(stat: EditCounts) -> Scalar:
    """(S + D + I) / n_réf — CER, WER."""
    return _ratio(stat.edits, stat.reference_length)


def insertion_rate(stat: EditCounts) -> Scalar:
    """I / n_réf."""
    return _ratio(stat.insertions, stat.reference_length)


def deletion_rate(stat: EditCounts) -> Scalar:
    """D / n_réf."""
    return _ratio(stat.deletions, stat.reference_length)


def match_error_rate(stat: EditCounts) -> Scalar:
    """(S + D + I) / (H + S + D + I) = (S + D + I) / (n_réf + I) — MER, cMER."""
    return _ratio(stat.edits, stat.reference_length + stat.insertions)


def edit_terms(stat: EditCounts) -> tuple[int, int]:
    """(S + D + I, n_réf) : les termes du ratio d'un taux d'édition, dont le
    dénominateur est fixé par la référence (§ 2.1 d)."""
    return stat.edits, stat.reference_length


def accuracy(stat: ErrorCounts) -> Scalar:
    """max(0, 1 − e/n), plancher appliqué **à cette statistique** — celle du
    document ou celle du corpus, jamais une moyenne de planchers (B1) ; le
    taux non tronqué e/n est rendu à côté."""
    if stat.reference_length == 0:
        return Scalar(None, "zero_denominator")
    rate = Fraction(stat.errors, stat.reference_length)
    exact = max(Fraction(0), 1 - rate)
    return Scalar(
        float(exact),
        untruncated_error_rate=stat.errors / stat.reference_length,
        exact=exact,
    )


def error_ratio(stat: ErrorCounts) -> Scalar:
    """e / n_réf, non borné — texte par région."""
    return _ratio(stat.errors, stat.reference_length)


def f1(stat: MatchCounts) -> Scalar:
    """2tp / (2tp + fp + fn)."""
    return _ratio(2 * stat.tp, 2 * stat.tp + stat.fp + stat.fn)


def precision(stat: MatchCounts) -> Scalar:
    """tp / (tp + fp)."""
    return _ratio(stat.tp, stat.tp + stat.fp)


def recall(stat: MatchCounts) -> Scalar:
    """tp / (tp + fn)."""
    return _ratio(stat.tp, stat.tp + stat.fn)


def proportion(stat: Proportion) -> Scalar:
    """k / n."""
    return _ratio(stat.count, stat.total)


def canonical_edit_counts(
    reference: Sequence[Hashable], hypothesis: Sequence[Hashable]
) -> EditCounts:
    """(S, D, I, n_réf) **canoniques** (P1) : parmi les alignements de coût
    minimal, celui qui maximise S.

    Les comptes viennent de ``_alignment.canonical_counts`` (la primitive
    que partage le cMER de l'analyse de correction). Ils diffèrent de jiwer et
    de ``rapidfuzz.editops`` sur D et I (« ab »/« ba » : (2, 0, 0) contre
    (0, 1, 1)), jamais sur S + D + I.
    """
    s, d, i = canonical_counts(reference, hypothesis)
    return EditCounts(
        substitutions=s, deletions=d, insertions=i, reference_length=len(reference)
    )


__all__ = [
    "EditCounts",
    "ErrorCounts",
    "Counts",
    "MatchCounts",
    "Proportion",
    "Scalar",
    "ScalarReason",
    "Statistic",
    "accuracy",
    "canonical_edit_counts",
    "combine",
    "deletion_rate",
    "edit_rate",
    "edit_terms",
    "error_ratio",
    "f1",
    "insertion_rate",
    "invented_units",
    "match_error_rate",
    "precision",
    "proportion",
    "recall",
    "reference_defines",
]
