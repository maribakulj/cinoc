"""Catégorie et unité d'une métrique, à l'affichage (couche 7) — D-289.

La déclaration vit **au registre** (``MetricSpec.category`` / ``.unit``, couche
3) ; ce module ne fait que la lire et la nommer, en français et en anglais.
Un nom que le registre ne connaît pas (le score d'un ``RunResult`` antérieur,
relu sous son ancienne clé) n'a pas de catégorie : il n'est ni classé ni
marqué établi — on ne lui prête pas une validité qu'aucune fiche ne déclare.
"""

from __future__ import annotations

from collections.abc import Iterable

from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation.registry import metric_specs
from cinoc.reports.html import escape, localized

#: Libellés (FR, EN) des catégories.
CATEGORY_LABELS: dict[MetricCategory, tuple[str, str]] = {
    MetricCategory.ESTABLISHED: ("établie", "established"),
    MetricCategory.ADAPTED: ("adaptée", "adapted"),
    MetricCategory.EXPLORATORY: ("exploratoire", "exploratory"),
}

#: Libellés (FR, EN) des unités — ceux que la fiche du glossaire doit nommer.
UNIT_LABELS: dict[MetricUnit, tuple[str, str]] = {
    MetricUnit.CHARACTER: ("caractère", "character"),
    MetricUnit.WORD: ("mot", "word"),
    MetricUnit.CHARACTER_TRIGRAM: ("trigramme", "trigram"),
    MetricUnit.LINE: ("ligne", "line"),
    MetricUnit.REGION: ("région", "region"),
    MetricUnit.ENTITY: ("entité", "entity"),
    MetricUnit.NUMERIC_SEQUENCE: ("séquence numérique", "numeric sequence"),
}

#: Marque d'en-tête d'une métrique non établie (la même en FR et en EN).
_MARKS: dict[MetricCategory, str] = {
    MetricCategory.ADAPTED: "≈",
    MetricCategory.EXPLORATORY: "∗",
}

#: Ce que chaque catégorie implique, dit en une phrase (FR, EN).
_MEANING: dict[MetricCategory, tuple[str, str]] = {
    MetricCategory.ADAPTED: (
        "variante justifiée d'une référence nommée",
        "a justified variant of a named reference",
    ),
    MetricCategory.EXPLORATORY: (
        "sans référence nommée",
        "no named reference",
    ),
}


def category_of(metric: str) -> MetricCategory | None:
    """Catégorie déclarée au registre ; ``None`` pour un nom inconnu."""
    spec = metric_specs().get(metric)
    return spec.category if spec is not None else None


def unit_of(metric: str) -> MetricUnit | None:
    """Unité déclarée au registre ; ``None`` pour un nom inconnu."""
    spec = metric_specs().get(metric)
    return spec.unit if spec is not None else None


def higher_is_better(metric: str) -> bool:
    """Sens de lecture déclaré ; un nom inconnu se lit comme un taux d'erreur."""
    spec = metric_specs().get(metric)
    return spec.higher_is_better if spec is not None else False


def is_established(metric: str) -> bool:
    """Vrai pour une métrique **établie** — la seule qu'on classe et teste."""
    return category_of(metric) is MetricCategory.ESTABLISHED


def category_label(category: MetricCategory, lang: str) -> str:
    return localized(lang, *CATEGORY_LABELS[category])


def unit_label(unit: MetricUnit, lang: str) -> str:
    return localized(lang, *UNIT_LABELS[unit])


def category_mark(metric: str, lang: str) -> str:
    """``<sup>`` après le nom d'une métrique adaptée ou exploratoire ; ``""``
    pour une établie (ou un nom inconnu, qui n'a pas de fiche à citer)."""
    category = category_of(metric)
    if category is None or category not in _MARKS:
        return ""
    title = (
        f"{category_label(category, lang)} — {localized(lang, *_MEANING[category])}"
        + localized(
            lang,
            " ; hors classement et hors tests de significativité",
            "; outside the ranking and the significance tests",
        )
    )
    return (
        f'<sup class="cat-mark" title="{escape(title)}">{_MARKS[category]}</sup>'
    )


def category_legend(metrics: Iterable[str], lang: str) -> str:
    """Légende des marques présentes parmi ``metrics`` ; ``""`` s'il n'y en a pas."""
    present = {category_of(m) for m in metrics}
    colon = localized(lang, " : ", ": ")
    parts = [
        f"{_MARKS[category]} {category_label(category, lang)}{colon}"
        f"{localized(lang, *_MEANING[category])}"
        for category in (MetricCategory.ADAPTED, MetricCategory.EXPLORATORY)
        if category in present
    ]
    if not parts:
        return ""
    tail = localized(
        lang,
        " — au diagnostic, hors classement et hors tests de significativité "
        "(fiches au glossaire).",
        " — diagnostic only, outside the ranking and the significance tests "
        "(cards in the glossary).",
    )
    return f'<p class="muted cat-legend">{" · ".join(parts)}{tail}</p>\n'


__all__ = [
    "CATEGORY_LABELS",
    "UNIT_LABELS",
    "category_label",
    "category_legend",
    "category_mark",
    "category_of",
    "higher_is_better",
    "is_established",
    "unit_label",
    "unit_of",
]
