"""Métrique philologique **diacritiques** : taux d'erreur sur les caractères
porteurs de signes (umlauts ä/ö/ü, accents é/è/ê…), mesuré par **alignement
caractère** position-aware.

Contrairement à CER/WER/MER — implémentations pures (journal D-007) — cette
métrique exige un alignement caractère sur des documents entiers (plusieurs
milliers de caractères) : une plein-matrice en Python pur serait trop coûteuse
en CI. Elle s'appuie donc sur ``rapidfuzz`` (whitelist ``evaluation/``, C,
déterministe) — **c'est la tranche qui introduit cette dépendance** (cf.
``MIGRATION_COUCHE_3.md``). ``text.py`` reste, lui, sans dépendance externe.
"""

from __future__ import annotations

import unicodedata

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import MetricCategory, MetricUnit
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation, document_metric
from cinoc.evaluation.preservation import preservation_counts


def _is_diacritic(char: str) -> bool:
    """Vrai si ``char`` porte un signe combinant (décomposition NFD → catégorie
    ``Mn``). Capte les lettres accentuées précomposées (ä, é, ñ…) ; exclut les
    bases sans accent (``ß`` ; ``æ`` est une ligature, pas un diacritique)."""
    return any(
        unicodedata.category(part) == "Mn"
        for part in unicodedata.normalize("NFD", char)
    )


@document_metric(
    name="diacritic_err",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    category=MetricCategory.EXPLORATORY,
    unit=MetricUnit.CHARACTER,
    description="Taux d'erreur sur les caractères à diacritique (umlauts, accents).",
    higher_is_better=False,
    tags=frozenset({"text", "philology", "alignment"}),
)
def diacritic_error(ctx: DocContext) -> Observation | None:
    """Parmi les caractères à diacritique de la **référence**, fraction mal
    reconnue (substituée ou supprimée dans l'alignement). ``None`` si la référence
    n'en contient aucun (non applicable) — le runner exclut ce cas de l'agrégat."""
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError(
            "diacritic_err : reference et hypothesis doivent être du texte."
        )
    counts = preservation_counts(ctx.reference, ctx.hypothesis, _is_diacritic)
    if counts is None:
        return None
    n_total, n_wrong = counts
    return Observation(value=n_wrong / n_total, weight=n_total)


#: Métriques philologiques par alignement caractère (dépendent de ``rapidfuzz``).
DIACRITIC_METRICS: tuple[DocumentMetric, ...] = (diacritic_error,)

__all__ = ["DIACRITIC_METRICS", "diacritic_error"]
