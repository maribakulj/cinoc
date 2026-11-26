"""Numéraux **romains** : parseur + restitution en 5 statuts (couche 3).

Transversal aux périodes (médiéval `mcclxxxij`, imprimé ancien `Tome IV`,
moderne `Louis XIV`). Pour chaque numéral de la GT, on classe sa restitution
dans l'hypothèse selon le **premier** statut applicable :

1. ``strict_preserved`` — forme exacte (``xiv`` → ``xiv``) ;
2. ``case_changed`` — valeur intacte, casse modifiée (``xiv`` → ``XIV``) ;
3. ``j_dropped`` — ``j`` médiéval final standardisé (``viij`` → ``viii``) ;
4. ``converted_to_arabic`` — système modernisé (``XIV`` → ``14``) ;
5. ``lost`` — aucune trace de la valeur.

Les 4 premiers préservent la valeur. C'est l'**unique** comptage des romains
(R1 : retiré de `structured_data`, qui n'en garde qu'un helper de **valeur**
régnale, ré-exporté ici) ; les scores strict/valeur s'en dérivent sans double
comptage. Détection greedy `\\b[IVXLCDMivxlcdmj]+\\b` + validation par la grammaire des
chiffres (canonique ou additif médiéval, D-287) ;
``min_length=2`` par défaut (R2 : filtre les ``I``/``M`` isolés ambigus).
Adaptatif : GT sans numéral → pas de payload.
"""

from __future__ import annotations

import re

from cinoc.evaluation.analysis import (
    Analysis,
    PipelineRomanNumerals,
    RomanNumeralsPayload,
)

ROMAN_VALUES: dict[str, int] = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

_ROMAN_CHARS = "IVXLCDMivxlcdmj"
_ROMAN_RE = re.compile(rf"\b[{_ROMAN_CHARS}]+\b")

#: Statuts dans l'ordre canonique (= ordre de priorité de classement).
STATUSES: tuple[str, ...] = (
    "strict_preserved",
    "case_changed",
    "j_dropped",
    "converted_to_arabic",
    "lost",
)
#: Statuts qui préservent la valeur (tous sauf ``lost``).
_VALUE_PRESERVING = STATUSES[:-1]

#: Plafond d'échantillons de formes perdues par pipeline.
_MAX_LOST_SAMPLES = 12


def _normalize_roman(text: str) -> str:
    """Majuscule + ``j`` médiéval final → ``I`` (``viij`` → ``VIII``)."""
    upper = text.upper()
    if upper.endswith("J"):
        return upper[:-1] + "I"
    return upper


#: Grammaire d'un numéral : milliers, centaines, dizaines, unités, chacun un
#: chiffre écrit soit en forme canonique (``IV``, ``IX``, ``VIII``…) soit en
#: forme **additive médiévale** (``IIII``, ``VIIII`` — D-121), jusqu'à
#: ``MMMM``. C'est la grammaire canonique (celle du paquet ``roman``) où chaque
#: ``{0,3}`` devient ``{0,4}``.
_ROMAN_GRAMMAR = re.compile(
    r"M{0,4}(?:CM|CD|D?C{0,4})(?:XC|XL|L?X{0,4})(?:IX|IV|V?I{0,4})"
)


def _is_plausible_roman(text: str) -> bool:
    """Validation **stricte** par la grammaire des chiffres : accepte les
    formes canoniques et l'additif médiéval (``IIII``, ``VIIII``, ``XXXX``),
    rejette tout le reste — répétitions (``IIIII``, ``VV``), paires
    soustractives illégales (``IL``, ``IC`` — faux positifs de mots comme
    « ici »), et les suites dont chaque paire est légale prise seule mais
    qu'aucune écriture romaine ne produit (``IIV``, ``IXI``, ``VIV``,
    ``XIIX`` — acceptées avant D-287, défaut 11 de l'audit D-264).
    """
    return _ROMAN_GRAMMAR.fullmatch(text) is not None


def _parse_normalized(text: str) -> int | None:
    """Valeur d'un numéral **normalisé** (soustraction standard), ou ``None``."""
    if not text or not all(c in ROMAN_VALUES for c in text):
        return None
    total = 0
    previous = 0
    for char in reversed(text):
        value = ROMAN_VALUES[char]
        if value < previous:
            total -= value
        else:
            total += value
        previous = value
    if total <= 0 or not _is_plausible_roman(text):
        return None
    return total


def roman_to_int(text: str | None) -> int | None:
    """Valeur d'une chaîne romaine (tolère casse + ``j`` médiéval), ou ``None``.

    Source unique de parsing romain (R1) : `structured_data` l'importe pour la
    valeur régnale.
    """
    if not text:
        return None
    return _parse_normalized(_normalize_roman(text))


def detect_roman_numerals(
    text: str, *, min_length: int = 2
) -> list[tuple[int, str, int]]:
    """Numéraux valides de ``text`` : ``[(index, forme, valeur), ...]``."""
    found: list[tuple[int, str, int]] = []
    for match in _ROMAN_RE.finditer(text):
        form = match.group(0)
        if len(form) < min_length:
            continue
        value = roman_to_int(form)
        if value is not None:
            found.append((match.start(), form, value))
    return found


def _present(needle: str, hypothesis: str) -> bool:
    """``needle`` présent dans ``hypothesis`` hors d'un mot alphabétique."""
    pattern = r"(?<![A-Za-z])" + re.escape(needle) + r"(?![A-Za-z])"
    return re.search(pattern, hypothesis) is not None


def classify(numeral: str, value: int, hypothesis: str) -> str:
    """Statut de restitution de ``numeral`` (de valeur ``value``) dans l'hyp."""
    if _present(numeral, hypothesis):
        return "strict_preserved"
    swapped = numeral.swapcase()
    if swapped != numeral and _present(swapped, hypothesis):
        return "case_changed"
    lowered = numeral.lower()
    if lowered.endswith("j"):
        flipped = numeral[:-1] + ("I" if numeral[-1] == "J" else "i")
    elif lowered.endswith("i"):
        flipped = numeral[:-1] + ("J" if numeral[-1] == "I" else "j")
    else:
        flipped = numeral
    if flipped != numeral and (
        _present(flipped, hypothesis) or _present(flipped.swapcase(), hypothesis)
    ):
        return "j_dropped"
    if re.search(r"(?<!\d)" + str(value) + r"(?!\d)", hypothesis):
        return "converted_to_arabic"
    return "lost"


class RomanNumeralsCollector:
    """Accumule la restitution des numéraux au fil du scoring (micro).

    ``observe`` par document scoré (mêmes textes normalisés, zéro relecture),
    ``build`` agrège par (pipeline × statut). Pipelines sans numéral → absents.
    """

    def __init__(self, *, min_length: int = 2) -> None:
        self._min_length = min_length
        self._counts: dict[str, dict[str, int]] = {}
        self._lost: dict[str, list[str]] = {}
        self._order: list[str] = []

    def observe(self, pipeline: str, reference: str, hypothesis: str) -> None:
        detected = detect_roman_numerals(reference, min_length=self._min_length)
        if not detected:
            return
        if pipeline not in self._counts:
            self._counts[pipeline] = {status: 0 for status in STATUSES}
            self._lost[pipeline] = []
            self._order.append(pipeline)
        for _index, numeral, value in detected:
            status = classify(numeral, value, hypothesis)
            self._counts[pipeline][status] += 1
            if status == "lost" and len(self._lost[pipeline]) < _MAX_LOST_SAMPLES:
                self._lost[pipeline].append(numeral)

    def build(self, view: str) -> Analysis | None:
        """Payload de la vue, ``None`` si aucun numéral dans la GT du corpus."""
        rows: list[PipelineRomanNumerals] = []
        for pipeline in self._order:
            counts = self._counts[pipeline]
            n_total = sum(counts.values())
            rows.append(
                PipelineRomanNumerals(
                    pipeline=pipeline,
                    n_total=n_total,
                    strict_preserved=counts["strict_preserved"],
                    case_changed=counts["case_changed"],
                    j_dropped=counts["j_dropped"],
                    converted_to_arabic=counts["converted_to_arabic"],
                    lost=counts["lost"],
                    lost_samples=tuple(self._lost[pipeline]),
                )
            )
        if not rows:
            return None
        return Analysis(
            scope="corpus",
            view=view,
            payload=RomanNumeralsPayload(pipelines=tuple(rows)),
        )


__all__ = [
    "ROMAN_VALUES",
    "STATUSES",
    "RomanNumeralsCollector",
    "classify",
    "detect_roman_numerals",
    "roman_to_int",
]
