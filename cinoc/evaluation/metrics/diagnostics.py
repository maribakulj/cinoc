"""Métriques de diagnostic texte : cherchabilité, trigrammes non ancrés (couche 3).

Heuristiques **maison** (PLAN_PARITE §5.8b : spécification de départ relue,
valeurs de test dérivées à la main — jamais en exécutant la source).

- ``searchability`` — la question des bibliothèques numériques : quelle part
  des mots de la référence un lecteur retrouve-t-il par recherche plein-texte
  **tolérante** dans la transcription ? La tolérance **suit la longueur du
  mot** — l'échelle ``fuzziness: AUTO`` de Lucene/Elasticsearch : 0 édition
  jusqu'à 2 caractères, 1 de 3 à 5, 2 au-delà (``SPEC_HIPE.md`` §10, D-288).
  Le seuil absolu ``≤ 2`` d'avant laissait tout mot de deux lettres en
  « retrouver » n'importe quel autre : un bruit « xx yy zz… » faisait 0,6.
  Distance de Levenshtein (une transposition coûte 2, là où Lucene la compte
  1 par défaut). Appariement multi-ensemble : un mot produit ne « retrouve »
  qu'une seule occurrence de référence.
- ``unanchored_trigrams`` — part des trigrammes de caractères de l'hypothèse
  **absents** de la référence (1 − ancrage n-gramme). Un passage inventé en
  ancre peu ; plus haut = plus de texte sans appui dans la GT. Ce n'est **pas**
  un détecteur d'hallucination — nom retiré en D-288 : une page recopiée deux
  fois n'invente aucun trigramme et vaut 0,021 (CER 1,01), un texte réordonné
  vaut presque 0.
"""

from __future__ import annotations

from rapidfuzz.distance import Levenshtein

from cinoc.domain.artifacts import ArtifactType
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metric import DocumentMetric, Observation, document_metric

#: Échelle ``AUTO`` : ``(longueur minimale du mot, éditions tolérées)``, du
#: plus long au plus court. Sous 3 caractères, aucune édition.
_SEARCH_TOLERANCE: tuple[tuple[int, int], ...] = ((6, 2), (3, 1))
#: Taille des n-grammes d'ancrage de ``unanchored_trigrams``.
_NGRAM = 3


def _text_pair(ctx: DocContext) -> tuple[str, str]:
    return str(ctx.reference), str(ctx.hypothesis)


def _search_tolerance(word: str) -> int:
    """Éditions tolérées pour retrouver ``word`` (échelle ``AUTO``)."""
    for min_length, edits in _SEARCH_TOLERANCE:
        if len(word) >= min_length:
            return edits
    return 0


@document_metric(
    name="searchability",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description=(
        "Part des mots de la référence retrouvables dans l'hypothèse par "
        "recherche plein-texte tolérante, à une distance de Levenshtein "
        "qui suit la longueur du mot (échelle AUTO : 0, 1 puis 2 éditions)."
    ),
    higher_is_better=True,
    tags=frozenset({"text", "diagnostics"}),
)
def searchability(ctx: DocContext) -> Observation | None:
    reference, hypothesis = _text_pair(ctx)
    targets = reference.split()
    if not targets:
        return None
    pool = hypothesis.split()
    used = [False] * len(pool)
    found = 0
    for target in targets:
        tolerance = _search_tolerance(target)
        for index, word in enumerate(pool):
            if used[index]:
                continue
            if Levenshtein.distance(target, word, score_cutoff=tolerance) <= tolerance:
                used[index] = True
                found += 1
                break
    return Observation(value=found / len(targets), weight=len(targets))


def _ngrams(text: str) -> list[str]:
    return [text[i : i + _NGRAM] for i in range(len(text) - _NGRAM + 1)]


@document_metric(
    name="unanchored_trigrams",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description=(
        "Part des trigrammes de caractères de l'hypothèse absents de la "
        "référence (1 - ancrage) ; aveugle à un texte dupliqué ou réordonné."
    ),
    higher_is_better=False,
    tags=frozenset({"text", "diagnostics"}),
)
def unanchored_trigrams(ctx: DocContext) -> Observation | None:
    reference, hypothesis = _text_pair(ctx)
    produced = _ngrams(hypothesis)
    if not produced:
        return None  # hypothèse trop courte : rien à ancrer
    anchored = set(_ngrams(reference))
    unanchored = sum(1 for gram in produced if gram not in anchored)
    return Observation(value=unanchored / len(produced), weight=len(produced))


#: Socle diagnostic, collecté explicitement par le registre.
DIAGNOSTIC_METRICS: tuple[DocumentMetric, ...] = (searchability, unanchored_trigrams)

__all__ = [
    "DIAGNOSTIC_METRICS",
    "searchability",
    "unanchored_trigrams",
]
