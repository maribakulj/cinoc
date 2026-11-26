"""Carte des mots — quels mots GT chaque moteur ne restitue pas (couche 3).

Le CER global dit *combien* d'erreurs, jamais *lesquelles*. Cette analyse pose la
**matière** sur la table : pour chaque mot de la vérité-terrain qu'un moteur ne
reproduit pas, on compte les échecs **par moteur** et on **croise** les pipelines
— quels mots *tous* ratent (difficulté de la matière) vs *un seul* (faiblesse
moteur). On juge à l'œil sur les mots eux-mêmes.

Réutilise la **tokenisation partagée** et le **même alignement** que la
modernisation lexicale (``textual_fidelity.token_fates`` — mots Unicode
minuscules, alignement optimal partagé, D-286) : un mot GT est « raté »
quand il est réécrit ou supprimé (pas reproduit verbatim). La **forme produite
dominante** est gardée (la matière de la confusion).

Honnêteté : l'appariement dépend de la **normalisation de la vue** (GT/hyp
préparés identiquement en amont par le runner) ; une **fusion/scission** de mots
est une limite de l'alignement (une substitution et une suppression : le second
mot devient ``∅``) ; mots et variantes sont **verbatim** (rien d'inventé —
anti-hallucination D-094).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from cinoc.evaluation.analysis import (
    Analysis,
    EngineWordError,
    WordError,
    WordErrorPayload,
)
from cinoc.evaluation.textual_fidelity import token_fates

#: Mots embarqués dans le payload : les plus durs (-total d'erreurs, puis mot).
#: Cap explicite — borne le payload comme les autres collecteurs (caps de
#: ``textual_fidelity``/``inter_engine``).
_MAX_WORDS = 50


def word_misses(reference: str, hypothesis: str) -> list[tuple[str, str]]:
    """``(mot_GT, forme_produite)`` des mots GT non restitués.

    Les mots réécrits (forme hyp alignée) et supprimés (``∅``) de
    :func:`textual_fidelity.token_fates` — leur nombre est S + D de
    l'alignement optimal. Les mots hyp insérés ne sont **pas** des ratés GT
    (mesure centrée GT).
    """
    return [
        (token, form)
        for token, form in token_fates(reference, hypothesis)
        if form is not None
    ]


@dataclass
class _WordSlot:
    """Échecs d'un (pipeline, mot GT) : compte + formes produites observées."""

    count: int = 0
    variants: Counter[str] = field(default_factory=Counter)


class WordErrorCollector:
    """Accumule les mots GT ratés (pipeline × mot) au scoring ; ``build`` croise.

    ``observe`` aligne GT↔hyp au mot et incrémente, par (pipeline, mot GT), le
    nombre d'échecs + la forme produite. ``build`` cross-tabule sur les pipelines
    **observés** (ceux qui ont produit du texte — comme ``inter_engine``) → matrice
    mot→{moteur:compte} + signature de regroupement. ``None`` si < 2 pipelines ou
    aucune erreur. ``document_id`` n'entre pas dans l'agrégat (les échecs se
    somment sur tout le corpus, indépendamment du document) — conservé dans la
    signature pour l'uniformité de câblage du runner.
    """

    def __init__(self) -> None:
        self._order: list[str] = []
        self._slots: dict[str, dict[str, _WordSlot]] = {}

    def observe(
        self, pipeline: str, document_id: str, reference: str, hypothesis: str
    ) -> None:
        if pipeline not in self._slots:
            self._slots[pipeline] = {}
            self._order.append(pipeline)
        per_word = self._slots[pipeline]
        for word, variant in word_misses(reference, hypothesis):
            slot = per_word.setdefault(word, _WordSlot())
            slot.count += 1
            slot.variants[variant] += 1

    def build(self, view: str) -> Analysis | None:
        """Payload ``word_errors`` de la vue, ``None`` si non applicable."""
        pipelines = sorted(self._slots)
        if len(pipelines) < 2:
            return None
        # Mot GT → {pipeline : slot}, sur les seuls moteurs qui le ratent (creux).
        by_word: dict[str, dict[str, _WordSlot]] = {}
        for pipeline in pipelines:
            for word, slot in self._slots[pipeline].items():
                by_word.setdefault(word, {})[pipeline] = slot
        if not by_word:
            return None
        words = [
            _word_error(word, per_pipeline, len(pipelines))
            for word, per_pipeline in by_word.items()
        ]
        # Tri déterministe : les mots les plus ratés d'abord, puis alpha ; capé.
        words.sort(key=lambda w: (-w.total_errors, w.word))
        return Analysis(
            scope="corpus",
            view=view,
            payload=WordErrorPayload(
                pipelines=tuple(pipelines),
                words=tuple(words[:_MAX_WORDS]),
            ),
        )


def _word_error(
    word: str, per_pipeline: dict[str, _WordSlot], n_pipelines: int
) -> WordError:
    """``WordError`` d'un mot : détail par moteur (creux), total, regroupement."""
    per_engine = tuple(
        EngineWordError(
            pipeline=pipeline,
            count=slot.count,
            variant=_dominant_variant(slot.variants),
        )
        for pipeline, slot in sorted(
            per_pipeline.items(), key=lambda item: (-item[1].count, item[0])
        )
    )
    n_engines = len(per_engine)
    group: Literal["universal", "engine_specific", "partial"]
    if n_engines == n_pipelines:
        group = "universal"
    elif n_engines == 1:
        group = "engine_specific"
    else:
        group = "partial"
    return WordError(
        word=word[:64],
        total_errors=sum(engine.count for engine in per_engine),
        per_engine=per_engine,
        group=group,
    )


def _dominant_variant(variants: Counter[str]) -> str:
    """Forme produite **dominante** (-compte, puis forme) — verbatim, capée 64 c."""
    form, _ = min(variants.items(), key=lambda item: (-item[1], item[0]))
    return form[:64]


__all__ = ["WordErrorCollector", "word_misses"]
