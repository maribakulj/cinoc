"""Taxonomie d'erreurs : classification par règles pures (couche 3).

Transforme « combien d'erreurs » en « quelles erreurs » : chaque mot erroné
est classé par des règles **déterministes et auditables** (aucun ML, aucun
lexique). Heuristique maison (règle D-068 : spécification source relue
et **élaguée** — les classes à lexique ``hapax``/``oov_character`` et
l'``abbreviation_error`` à table MUFI ne sont pas portées, cf. D-071).

Classes (ordre de test = priorité) :

- ``segmentation`` — fusion/fragmentation : la concaténation d'un côté égale
  l'autre (« bonjour » ↔ « bon jour ») ;
- ``case`` — casse seule (« Chat » ↔ « chat ») ;
- ``diacritic`` — diacritiques seuls (« été » ↔ « ete ») ;
- ``ligature`` — ligature non résolue (« cœur » ↔ « coeur ») ;
- ``visual`` — confusion morphologique connue (rn↔m, l/1/I, O/0, u↔n, ſ↔s) ;
- ``lacuna`` — mot de la référence absent de l'hypothèse ;
- ``insertion`` — mot de l'hypothèse absent de la référence ;
- ``other`` — substitution résiduelle inclassée.

**Les éditions sont celles du WER** (D-286) : mots découpés par ``str.split``
comme le WER, alignés par le même alignement optimal
(``evaluation._alignment``). Chaque édition reçoit une classe et une seule :
``lacuna`` = les D du WER, ``insertion`` = ses I, hors des blocs de
fusion/scission (rangés en ``segmentation``, comptés ``max(n, m)`` — le coût
du bloc) ; le total vaut S + D + I. Dans un bloc d'éditions aux côtés
inégaux, les mots appariés sont ceux qui se ressemblent le plus
(``_alignment.alignment``) : la classe d'un mot substitué en dépend, jamais
les comptes ``lacuna``/``insertion``.
"""

from __future__ import annotations

from collections import Counter

from cinoc.evaluation._alignment import Pair, alignment
from cinoc.evaluation.analysis import (
    Analysis,
    PipelineTaxonomy,
    TaxonomyCount,
    TaxonomyPayload,
)
from cinoc.formats.text.normalization import strip_diacritics

#: Ordre de rendu canonique des classes (déterminisme du payload).
CLASSES: tuple[str, ...] = (
    "segmentation",
    "case",
    "diacritic",
    "ligature",
    "visual",
    "lacuna",
    "insertion",
    "other",
)

#: Ligatures → développement (test dans les deux sens).
_LIGATURES = {
    "œ": "oe", "æ": "ae", "Œ": "OE", "Æ": "AE",
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff",
}

#: Groupes de confusions visuelles → représentant canonique. Appliqué aux
#: **deux** côtés d'une paire déjà fautive (pas de faux positif sur un mot juste),
#: une fois sur la casse d'origine (``I`` majuscule lu ``l``) et une fois en
#: minuscules (``RN`` lu ``M``). ``O`` lu ``o`` n'y figure pas : c'est la
#: classe ``case``, testée avant.
_VISUAL_CANON = (
    ("rn", "m"),
    ("1", "l"),
    ("I", "l"),
    ("|", "l"),
    ("0", "o"),
    ("ſ", "s"),
    ("u", "n"),
)


def _expand_ligatures(text: str) -> str:
    for ligature, expansion in _LIGATURES.items():
        text = text.replace(ligature, expansion)
    return text


def _visual_canonical(text: str) -> str:
    for variant, canon in _VISUAL_CANON:
        text = text.replace(variant, canon)
    return text


def _visually_equal(reference: str, hypothesis: str) -> bool:
    """Égaux à une confusion visuelle près, sur la casse d'origine ou en minuscules.

    La table appliquée après ``lower()`` seulement ne voyait jamais ``I`` :
    ``Il`` lu ``ll`` sortait en ``other``.
    """
    if _visual_canonical(reference).lower() == _visual_canonical(hypothesis).lower():
        return True
    return _visual_canonical(reference.lower()) == _visual_canonical(hypothesis.lower())


def classify_word_pair(reference: str, hypothesis: str) -> str:
    """Classe d'une substitution mot → mot (règles pures, ordre = priorité)."""
    if reference.lower() == hypothesis.lower():
        return "case"
    if strip_diacritics(reference) == strip_diacritics(hypothesis):
        return "diacritic"
    if _expand_ligatures(reference) == _expand_ligatures(hypothesis):
        return "ligature"
    if _visually_equal(reference, hypothesis):
        return "visual"
    return "other"


def _edit_blocks(
    ref_words: list[str], hyp_words: list[str], pairs: list[Pair]
) -> list[list[Pair]]:
    """Blocs d'éditions contiguës (entre deux mots égaux) de l'alignement."""
    blocks: list[list[Pair]] = []
    current: list[Pair] = []
    for i, j in pairs:
        if i is not None and j is not None and ref_words[i] == hyp_words[j]:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append((i, j))
    if current:
        blocks.append(current)
    return blocks


def classify_texts(reference: str, hypothesis: str) -> Counter[str]:
    """Comptage des classes d'erreurs entre deux textes (éditions du WER)."""
    counts: Counter[str] = Counter()
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    pairs = alignment(ref_words, hyp_words)
    for block in _edit_blocks(ref_words, hyp_words, pairs):
        ref_seg = [ref_words[i] for i, _ in block if i is not None]
        hyp_seg = [hyp_words[j] for _, j in block if j is not None]
        # Fusion/fragmentation d'abord (au niveau du bloc).
        if "".join(ref_seg) == "".join(hyp_seg):
            counts["segmentation"] += max(len(ref_seg), len(hyp_seg))
            continue
        for i, j in block:
            if j is None:
                counts["lacuna"] += 1
            elif i is None:
                counts["insertion"] += 1
            else:
                counts[classify_word_pair(ref_words[i], hyp_words[j])] += 1
    return counts


class TaxonomyCollector:
    """Accumule les classes d'erreurs au fil du scoring d'une vue."""

    def __init__(self) -> None:
        self._counts: dict[str, Counter[str]] = {}

    def observe(self, pipeline: str, reference: str, hypothesis: str) -> None:
        bucket = self._counts.setdefault(pipeline, Counter())
        bucket.update(classify_texts(reference, hypothesis))

    def build(self, view: str) -> Analysis | None:
        rows = tuple(
            PipelineTaxonomy(
                pipeline=pipeline,
                total_errors=sum(bucket.values()),
                counts=tuple(
                    TaxonomyCount(label=label, count=bucket[label])
                    for label in CLASSES
                    if bucket[label] > 0
                ),
            )
            for pipeline, bucket in sorted(self._counts.items())
            if bucket
        )
        if not rows:
            return None
        payload = TaxonomyPayload(classes=CLASSES, pipelines=rows)
        return Analysis(scope="corpus", view=view, payload=payload)


__all__ = ["CLASSES", "TaxonomyCollector", "classify_texts", "classify_word_pair"]
