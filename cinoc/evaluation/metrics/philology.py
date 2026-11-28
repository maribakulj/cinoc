"""Métrique philologique **MUFI** : taux d'erreur sur les caractères médiévaux
spéciaux (zone privée MUFI, abréviations latines, lettres médiévales).

Complète ``diacritic_err`` (signes combinants) sur un autre axe philologique :
les **lettres et signes médiévaux** standardisés par la MUFI (Medieval Unicode
Font Initiative) — soit dans la **zone d'usage privé** (PUA), soit des codepoints
Unicode dédiés (``ſ`` s long, ``þ`` thorn, ligatures, abréviations latines de
Latin Extended-D…). Un moteur OCR/HTR peut très bien rendre le texte courant mais
échouer précisément sur ces glyphes — c'est ce que cette métrique isole.

Même mécanique que ``diacritic_err`` : alignement caractère ``rapidfuzz``
(whitelist ``evaluation/``, C, déterministe). ``text.py`` reste sans dépendance.
"""

from __future__ import annotations

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation import statistics as st
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, document_metric
from cinoc.evaluation.preservation import preservation_counts
from cinoc.evaluation.statistics import Proportion

#: Plages Unicode où vivent les glyphes MUFI / médiévaux.
#: ⚠️ **Pas de signes combinants** ici (bloc U+1DC0–U+1DFF volontairement exclu) :
#: ils relèvent de ``diacritic_err`` (catégorie ``Mn``). ``mufi_err`` mesure des
#: **lettres/ligatures/abréviations** à codepoint propre → axe disjoint.
_MUFI_RANGES: tuple[tuple[int, int], ...] = (
    (0xE000, 0xF8FF),      # Private Use Area (zone MUFI principale)
    (0xF0000, 0xFFFFD),    # Supplementary PUA-A
    (0x100000, 0x10FFFD),  # Supplementary PUA-B
    (0xA720, 0xA7FF),      # Latin Extended-D (abréviations latines médiévales)
    (0xFB00, 0xFB06),      # Ligatures latines (ﬀ ﬁ ﬂ ﬃ ﬄ ﬅ ﬆ)
)

#: Lettres/signes médiévaux à codepoint dédié, hors plages ci-dessus.
_MUFI_EXPLICIT: frozenset[str] = frozenset("þÞðÐƿǷſæÆœŒøØƀŧđħȝȜ")


def _is_mufi(char: str) -> bool:
    """Vrai si ``char`` est un glyphe MUFI / médiéval (PUA ou codepoint dédié)."""
    cp = ord(char)
    if any(lo <= cp <= hi for lo, hi in _MUFI_RANGES):
        return True
    return char in _MUFI_EXPLICIT


@document_metric(
    name="mufi_err",
    finalize=st.proportion,
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.EXPLORATORY,
    unit=MetricUnit.CHARACTER,
    description="Taux d'erreur sur les caractères MUFI / médiévaux "
    "(PUA, abréviations latines, ſ/þ/ligatures…).",
    higher_is_better=False,
    tags=frozenset({"text", "philology", "alignment", "mufi"}),
)
def mufi_error(ctx: DocContext) -> Proportion:
    """Parmi les caractères MUFI de la **référence**, fraction mal reconnue
    (substituée ou supprimée dans l'alignement). Indéfini si la référence n'en
    contient aucun (``zero_denominator``)."""
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError(
            "mufi_err : reference et hypothesis doivent être du texte."
        )
    # Accept #17 : on compte les glyphes MUFI **de la référence** mal reconnus
    # (substitués/supprimés). Un MUFI *inséré* (présent en hyp, absent en réf)
    # n'est pas compté : le dénominateur est l'ensemble des MUFI attendus.
    counts = preservation_counts(ctx.reference, ctx.hypothesis, _is_mufi)
    return Proportion(count=counts.wrong, total=counts.total)


#: Métriques philologiques MUFI (dépendent de ``rapidfuzz``).
PHILOLOGY_METRICS: tuple[DocumentMetric, ...] = (mufi_error,)

__all__ = ["PHILOLOGY_METRICS", "mufi_error"]
