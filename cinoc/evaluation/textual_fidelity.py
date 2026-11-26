"""Fidélité textuelle : tokens rares + modernisation lexicale (couche 3).

Deux diagnostics que le CER global masque, sur **un seul** alignement mot-à-mot :

- **Rappel des tokens rares** — un CER de 5 % peut cacher des erreurs
  systématiques sur les noms propres / toponymes / termes techniques (≤ 2
  occurrences corpus-wide : hapax + dis legomena). Ce sont eux qui comptent en
  indexation prosopographique. Rappel **multiset** (`Σ min(occ. GT, occ. hyp)`).
- **Modernisation lexicale** — quelles formes historiques le moteur (LLM/VLM)
  réécrit (`maistre`→`maître`, `nostre`→`nostre`, mot supprimé → `∅`). Table de
  fréquences = diagnostic de prompt, pas un score agrégé.

Particularité d'architecture (≠ scalaires `air`/`mufi_err`) : la rareté est
**corpus-wide** — connue seulement après la passe complète. Le collecteur
accumule (pipeline × document) au fil du scoring (pattern ``TaxonomyCollector``,
zéro relecture), puis ``build`` calcule les fréquences sur les GT collectées et
en dérive le rappel — tout **après** la passe, sans mécanique nouvelle dans le
runner. L'alignement mot-à-mot est l'alignement optimal partagé
(``evaluation._alignment``, D-286) ; :func:`token_fates` le lit une fois pour
la modernisation et pour la carte des mots (``word_errors``).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from cinoc.evaluation._alignment import alignment
from cinoc.evaluation.analysis import (
    Analysis,
    ModernizedToken,
    ModernizedVariant,
    PipelineTextualFidelity,
    TextualFidelityPayload,
)

#: Token = séquence de caractères de mot Unicode, contractions (`l'an`, `d'une`)
#: et mots composés (`peut-être`) conservés comme **un** token ; ponctuation et
#: espaces = séparateurs. Une seule tokenisation pour les deux mesures.
_TOKEN_RE = re.compile(r"\w+(?:['’\-]\w+)*", re.UNICODE)

#: Mot supprimé par le moteur (variante de modernisation, forme produite de la
#: carte des mots).
_DELETED = "∅"

#: Rareté par défaut : ≤ 2 occurrences corpus-wide (hapax + dis legomena).
_DEFAULT_MAX_FREQ = 2

#: Plafonds d'échantillons embarqués (bornent le payload).
_MAX_MISSED = 20
_MAX_MODERNIZED_TOKENS = 20
_MAX_VARIANTS = 5


def tokenize(text: str) -> list[str]:
    """Tokens **minuscules** (casse non pertinente pour rareté/modernisation)."""
    return [match.lower() for match in _TOKEN_RE.findall(text)]


def corpus_frequencies(references: list[str]) -> Counter[str]:
    """``{token: occurrences}`` sur les GT du corpus (une GT par document)."""
    counter: Counter[str] = Counter()
    for reference in references:
        counter.update(tokenize(reference))
    return counter


def rare_tokens(frequencies: Counter[str], max_freq: int) -> frozenset[str]:
    """Tokens dont la fréquence corpus-wide est ``≤ max_freq``."""
    return frozenset(token for token, n in frequencies.items() if n <= max_freq)


def rare_recall_counts(
    reference: str, hypothesis: str, rare: frozenset[str]
) -> tuple[int, int, list[str]]:
    """``(n_reference, n_recalled, missed)`` des tokens rares de la GT.

    Multiset : un token rare présent 2× en GT et 1× en hyp → 1 rappelé, 1 manqué.
    ``missed`` porte la multiplicité (token répété autant que manqué), dans
    l'ordre d'apparition GT.
    """
    ref_rare = Counter(token for token in tokenize(reference) if token in rare)
    n_reference = sum(ref_rare.values())
    if n_reference == 0:
        return 0, 0, []
    hyp_rare = Counter(token for token in tokenize(hypothesis) if token in rare)
    n_recalled = 0
    missed: list[str] = []
    for token, ref_count in ref_rare.items():
        recalled = min(ref_count, hyp_rare.get(token, 0))
        n_recalled += recalled
        missed.extend([token] * (ref_count - recalled))
    return n_reference, n_recalled, missed


@dataclass
class _ModSlot:
    """Sommes de modernisation d'un token GT (corpus, micro)."""

    n_total: int = 0
    n_modernized: int = 0
    variants: Counter[str] = field(default_factory=Counter)


def token_fates(reference: str, hypothesis: str) -> list[tuple[str, str | None]]:
    """Sort de chaque token GT, dans l'ordre : ``(token, forme produite)``.

    ``None`` = restitué tel quel ; une forme hyp = réécrit (substitution) ;
    ``∅`` = supprimé. Les tokens hyp insérés n'y figurent pas (mesure centrée
    GT). Alignement :func:`_alignment.alignment`.
    Le nombre de ``∅`` est le D, celui des formes produites le S, de
    l'alignement optimal sur ces tokens.
    """
    ref_tokens = tokenize(reference)
    hyp_tokens = tokenize(hypothesis)
    fates: list[tuple[str, str | None]] = []
    for i, j in alignment(ref_tokens, hyp_tokens):
        if i is None:
            continue  # token hyp inséré
        if j is None:
            fates.append((ref_tokens[i], _DELETED))
        elif ref_tokens[i] == hyp_tokens[j]:
            fates.append((ref_tokens[i], None))
        else:
            fates.append((ref_tokens[i], hyp_tokens[j]))
    return fates


def modernization_counts(reference: str, hypothesis: str) -> dict[str, _ModSlot]:
    """Réécriture par token GT (:func:`token_fates`).

    Restitué → token compté (non modernisé) ; réécrit → modernisé (variante =
    forme hyp) ; supprimé → modernisé en ``∅``.
    """
    slots: dict[str, _ModSlot] = {}
    for token, variant in token_fates(reference, hypothesis):
        slot = slots.setdefault(token, _ModSlot())
        slot.n_total += 1
        if variant is not None:
            slot.n_modernized += 1
            slot.variants[variant] += 1
    return slots


@dataclass
class _PipelineSlot:
    """Accumulateur d'un pipeline : rappel rare + table de modernisation."""

    pairs: list[tuple[str, str]] = field(default_factory=list)
    modernization: dict[str, _ModSlot] = field(default_factory=dict)


class TextualFidelityCollector:
    """Accumule (pipeline × document) au scoring ; ``build`` calcule corpus-wide.

    La rareté exige les fréquences de **toutes** les GT → le rappel se calcule à
    ``build`` ; la modernisation, elle, s'agrège au fil de l'eau (indépendante du
    corpus). Les GT sont dédupliquées par document (mêmes GT pour tous les
    pipelines) pour la distribution de fréquence.
    """

    def __init__(self, max_freq: int = _DEFAULT_MAX_FREQ) -> None:
        self._max_freq = max_freq
        self._gt_by_document: dict[str, str] = {}
        self._pipelines: dict[str, _PipelineSlot] = {}
        self._order: list[str] = []

    def observe(
        self, pipeline: str, document_id: str, reference: str, hypothesis: str
    ) -> None:
        self._gt_by_document.setdefault(document_id, reference)
        if pipeline not in self._pipelines:
            self._pipelines[pipeline] = _PipelineSlot()
            self._order.append(pipeline)
        slot = self._pipelines[pipeline]
        slot.pairs.append((reference, hypothesis))
        for token, mod in modernization_counts(reference, hypothesis).items():
            agg = slot.modernization.setdefault(token, _ModSlot())
            agg.n_total += mod.n_total
            agg.n_modernized += mod.n_modernized
            agg.variants.update(mod.variants)

    def build(self, view: str) -> Analysis | None:
        """Payload de la vue, ``None`` si aucun pipeline n'a produit de texte."""
        if not self._order:
            return None
        frequencies = corpus_frequencies(list(self._gt_by_document.values()))
        rare = rare_tokens(frequencies, self._max_freq)
        rows = [
            self._pipeline_row(pipeline, rare) for pipeline in self._order
        ]
        return Analysis(
            scope="corpus",
            view=view,
            payload=TextualFidelityPayload(
                max_freq=self._max_freq, pipelines=tuple(rows)
            ),
        )

    def _pipeline_row(
        self, pipeline: str, rare: frozenset[str]
    ) -> PipelineTextualFidelity:
        slot = self._pipelines[pipeline]
        n_reference = n_recalled = 0
        missed: list[str] = []
        for reference, hypothesis in slot.pairs:
            doc_ref, doc_rec, doc_missed = rare_recall_counts(
                reference, hypothesis, rare
            )
            n_reference += doc_ref
            n_recalled += doc_rec
            missed.extend(doc_missed[: _MAX_MISSED - len(missed)])
        recall = n_recalled / n_reference if n_reference > 0 else None
        return PipelineTextualFidelity(
            pipeline=pipeline,
            n_rare_reference=n_reference,
            n_rare_recalled=n_recalled,
            rare_recall=recall,
            missed=tuple(missed),
            modernization=_top_modernized(slot.modernization),
        )


def _top_modernized(slots: dict[str, _ModSlot]) -> tuple[ModernizedToken, ...]:
    """Tokens réécrits, triés (-taux, -total, token), capés ; variantes capées."""
    modernized = [
        (token, slot)
        for token, slot in slots.items()
        if slot.n_modernized > 0
    ]
    modernized.sort(
        key=lambda pair: (
            -pair[1].n_modernized / pair[1].n_total,
            -pair[1].n_total,
            pair[0],
        )
    )
    return tuple(
        ModernizedToken(
            token=token[:64],
            n_total=slot.n_total,
            n_modernized=slot.n_modernized,
            rate=slot.n_modernized / slot.n_total,
            variants=tuple(
                ModernizedVariant(form=form[:64], count=count)
                for form, count in sorted(
                    slot.variants.items(), key=lambda v: (-v[1], v[0])
                )[:_MAX_VARIANTS]
            ),
        )
        for token, slot in modernized[:_MAX_MODERNIZED_TOKENS]
    )


__all__ = [
    "TextualFidelityCollector",
    "corpus_frequencies",
    "modernization_counts",
    "rare_recall_counts",
    "rare_tokens",
    "token_fates",
    "tokenize",
]
