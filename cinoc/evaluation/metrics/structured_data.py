"""Données structurées : séquences numériques — détecteurs + scalaires (couche 3).

Ce que cite et cherche un historien : **années** (1000-2099), **foliotation**
(f./fol./p./pp./n° + recto/verso), **montants** (livres/sols/deniers/écus/
florins/francs + symboles), **années régnales** (« an III », « l'an de grâce
MCCCXV »). Le CER ne dit pas si « 1515 » a survécu — ces métriques le disent,
sous deux lentilles :

- **strict** : la forme exacte de la GT est restituée (« fol. 12r ») ;
- **value** : l'équivalent est restitué, forme libre (« f. 12r », « an 3 »
  pour « an III »).

Regex volontairement **conservatrices** (la précision prime sur le rappel pour
une métrique de restitution — les formes en toutes lettres ne sont pas
couvertes). La catégorie *romain* vit dans la famille philologie (un seul
comptage — réparation R1) ; le régnal n'utilise le parseur romain que comme
**helper** de valeur.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation, document_metric
from cinoc.evaluation.roman import roman_to_int

#: Ordre canonique des catégories (rendu + payload).
CATEGORIES: tuple[str, ...] = ("year", "foliation", "currency", "regnal")

#: Années plausibles en contexte patrimonial : 1000-2099, frontières de mot.
_RE_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")

#: Foliotation : marqueur + numéro(s) (plage acceptée) + recto/verso optionnel.
_RE_FOLIATION = re.compile(
    r"\b(?:fol\.?|f\.|pp\.|p\.|n\.°|n°)\s*"
    r"(\d+(?:\s*-\s*\d+)?)"
    r"\s*([rvRV])?"
)

#: Montants : nombre + unité d'Ancien Régime ou symbole.
_RE_CURRENCY = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*"
    r"(livres?|sols?|deniers?|écus?|florins?|francs?|l\.|s\.|d\.|£|€|₣)"
    r"(?=\b|[\s,;.!?:]|$)",
    re.IGNORECASE,
)

_CURRENCY_CANONICAL = {
    "livres": "livre",
    "livre": "livre",
    "l.": "livre",
    "sols": "sol",
    "sol": "sol",
    "s.": "sol",
    "deniers": "denier",
    "denier": "denier",
    "d.": "denier",
    "écus": "écu",
    "écu": "écu",
    "florins": "florin",
    "florin": "florin",
    "francs": "franc",
    "franc": "franc",
    "£": "£",
    "€": "€",
    "₣": "₣",
}

#: Années régnales : « an III », « l'an 1793 », « an de grâce MCCCXV ».
_RE_REGNAL = re.compile(
    r"\b(?:l['’]\s*)?an\s+(?:de\s+(?:grâce|la\s+R[eé]publique)\s+)?"
    r"([IVXLCDM]+|[ivxlcdm]+|\d{1,4})\b"
)


@dataclass(frozen=True)
class SequenceItem:
    """Une séquence détectée : sa catégorie, sa forme exacte, sa clé de valeur."""

    category: str
    form: str
    #: Identité de **valeur** : "1515" (année), "12r" (folio), "3|livre"
    #: (montant), "14" (régnal) — deux formes différentes de même clé sont
    #: équivalentes sous la lentille *value*.
    key: str


def detect_sequences(text: str) -> tuple[SequenceItem, ...]:
    """Toutes les séquences du texte, par ordre de catégorie puis d'apparition."""
    items: list[SequenceItem] = []
    for match in _RE_YEAR.finditer(text):
        items.append(SequenceItem("year", match.group(0), match.group(1)))
    for match in _RE_FOLIATION.finditer(text):
        numbers = re.sub(r"\s", "", match.group(1))
        side = (match.group(2) or "").lower()
        items.append(SequenceItem("foliation", match.group(0), f"{numbers}{side}"))
    for match in _RE_CURRENCY.finditer(text):
        amount = match.group(1).replace(",", ".")
        unit = _CURRENCY_CANONICAL[match.group(2).lower()]
        items.append(SequenceItem("currency", match.group(0), f"{amount}|{unit}"))
    for match in _RE_REGNAL.finditer(text):
        raw = match.group(1)
        value = int(raw) if raw.isdigit() else roman_to_int(raw)
        if value is None:
            continue
        items.append(SequenceItem("regnal", match.group(0), str(value)))
    return tuple(items)


@dataclass(frozen=True)
class CategoryCounts:
    """Restitution d'une catégorie : totaux + formes perdues (lentille value)."""

    n_total: int
    n_strict: int
    n_value: int
    lost: tuple[str, ...]


def sequence_counts(reference: str, hypothesis: str) -> dict[str, CategoryCounts]:
    """Comptes par catégorie **présente dans la GT** (multiset des deux côtés).

    *strict* apparie les **formes** exactes, *value* les **clés** — deux
    consommations indépendantes (une forme appariée a toujours sa clé
    appariable : ``value ≥ strict`` structurellement).
    """
    reference_items = detect_sequences(reference)
    hypothesis_items = detect_sequences(hypothesis)
    out: dict[str, CategoryCounts] = {}
    for category in CATEGORIES:
        gt = [item for item in reference_items if item.category == category]
        if not gt:
            continue
        hyp = [item for item in hypothesis_items if item.category == category]
        forms = Counter(item.form for item in hyp)
        keys = Counter(item.key for item in hyp)
        n_strict = n_value = 0
        lost: list[str] = []
        for item in gt:
            if forms[item.form] > 0:
                forms[item.form] -= 1
                n_strict += 1
            if keys[item.key] > 0:
                keys[item.key] -= 1
                n_value += 1
            else:
                lost.append(item.form)
        out[category] = CategoryCounts(
            n_total=len(gt), n_strict=n_strict, n_value=n_value, lost=tuple(lost)
        )
    return out


def _text_pair(ctx: DocContext) -> tuple[str, str]:
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError(
            "séquences numériques : reference et hypothesis doivent être du texte."
        )
    return ctx.reference, ctx.hypothesis


def _global_score(ctx: DocContext, *, strict: bool) -> Observation | None:
    reference, hypothesis = _text_pair(ctx)
    counts = sequence_counts(reference, hypothesis)
    total = sum(c.n_total for c in counts.values())
    if total == 0:
        return None  # GT sans séquence : non applicable, jamais un zéro.
    preserved = sum((c.n_strict if strict else c.n_value) for c in counts.values())
    return Observation(value=preserved / total, weight=total)


@document_metric(
    name="numseq_strict",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.EXPLORATORY,
    unit=MetricUnit.NUMERIC_SEQUENCE,
    description=(
        "Part des séquences numériques de la GT (années, folios, montants, "
        "régnal) restituées sous leur forme exacte."
    ),
    higher_is_better=True,
    tags=frozenset({"text", "structured_data"}),
)
def numseq_strict(ctx: DocContext) -> Observation | None:
    return _global_score(ctx, strict=True)


@document_metric(
    name="numseq_value",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.EXPLORATORY,
    unit=MetricUnit.NUMERIC_SEQUENCE,
    description=(
        "Part des séquences numériques de la GT dont l'équivalent est restitué "
        "(forme libre : « f. 12r » vaut « fol. 12r »)."
    ),
    higher_is_better=True,
    tags=frozenset({"text", "structured_data"}),
)
def numseq_value(ctx: DocContext) -> Observation | None:
    return _global_score(ctx, strict=False)


#: Métriques de données structurées, collectées explicitement par le registre.
STRUCTURED_DATA_METRICS: tuple[DocumentMetric, ...] = (numseq_strict, numseq_value)

__all__ = [
    "CATEGORIES",
    "CategoryCounts",
    "STRUCTURED_DATA_METRICS",
    "SequenceItem",
    "detect_sequences",
    "numseq_strict",
    "numseq_value",
    "sequence_counts",
]
