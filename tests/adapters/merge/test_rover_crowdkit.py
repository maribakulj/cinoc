"""Parité du ROVER de Cinoc avec celui de **crowd-kit** — reste de S15
(D-287), livré en S18 (P5e 10, D-290).

**Pourquoi une transcription et pas le paquet.** ``crowdkit.aggregation.ROVER``
ne s'importe pas seul : ``crowdkit/aggregation/__init__.py`` importe tous les
agrégateurs, donc pandas, scikit-learn, scipy, nltk et tqdm (et le paquet
déclare en plus ``transformers`` et ``pyarrow``). C'est l'écosystème entier
pour une programmation dynamique de 80 lignes. D'où, comme pour kraken en S15,
une **transcription littérale** de ``crowdkit/aggregation/texts/rover.py``
(crowd-kit 1.4.2, Apache-2.0 : ``ROVER.fit``, ``_build_word_transition_network``,
``_align``, ``_get_result``), où seuls ``numpy.zeros``/``arange`` deviennent des
listes et ``attr.s`` une ``dataclass``. Sa fidélité a été vérifiée une fois
contre le paquet **exécuté** (crowd-kit 1.4.2 dans un environnement séparé,
pandas et scikit-learn compris) : mêmes sorties sur les 300 fusions de
``bnl_mini`` ci-dessous et sur 5 000 jeux de lectures courtes tirés (D-290).

**Même entrée, même sortie.** Deux écarts, documentés à ``_vote.py`` :

1. l'**ordre d'alignement** — crowd-kit aligne dans l'ordre reçu, Cinoc dans un
   ordre tiré du contenu (D-287). Donnée à crowd-kit dans l'ordre de Cinoc, la
   même entrée donne la même sortie ; dans l'ordre des noms de moteurs, elle
   diffère sur 74 des 300 fusions de ``bnl_mini`` (c'est le défaut que D-287
   corrigeait : la fusion dépendait du nom des sources) ;
2. le **bord de la table** — crowd-kit y compte toute absence 1
   (``distance[0, :] = arange``), Cinoc comme à l'intérieur (0 dans une case qui
   a déjà une absence). C'est la seule ligne que ``bord_comme_interieur``
   change ; avec elle, la transcription égale Cinoc partout (bnl_mini et
   5 000 jeux tirés). Sur ``bnl_mini`` le bord ne joue sur aucune fusion ; sur
   des lectures courtes tirées, il en change un peu plus d'une sur dix (559).
"""

from __future__ import annotations

import itertools
import random
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pytest

from cinoc.adapters.merge._vote import _ordre_d_alignement, vote_tokens

_BNL_MINI = Path(__file__).parents[2] / "fixtures" / "reference_corpus" / "bnl_mini"
_MOTEURS = ("deu", "deu_latf", "easyocr", "fra", "frk")


# --- Transcription littérale de crowd-kit 1.4.2 ----------------------------


class AlignmentAction(Enum):
    DELETION = "DELETION"
    SUBSTITUTION = "SUBSTITUTION"
    INSERTION = "INSERTION"
    CORRECT = "CORRECT"


@dataclass
class AlignmentEdge:
    value: str
    sources_count: int


Edges = dict[str, AlignmentEdge]


def _align(
    ref_edges_sets: list[Edges],
    hyp_edges: list[AlignmentEdge],
    sources_count: int,
    bord_comme_interieur: bool,
) -> list[Edges]:
    distance = [[0.0] * (len(ref_edges_sets) + 1) for _ in range(len(hyp_edges) + 1)]
    for i in range(len(hyp_edges) + 1):
        distance[i][0] = float(i)
    for j in range(len(ref_edges_sets) + 1):
        distance[0][j] = float(j)
    if bord_comme_interieur:  # le seul écart de Cinoc, hors de crowd-kit
        for j, ref_edges in enumerate(ref_edges_sets, start=1):
            distance[0][j] = distance[0][j - 1] + ("" not in ref_edges)

    memoization: list[list[tuple[AlignmentAction, Edges, AlignmentEdge] | None]] = [
        [None] * (len(ref_edges_sets) + 1) for _ in range(len(hyp_edges) + 1)
    ]
    for i, hyp_edge in enumerate(hyp_edges, start=1):
        memoization[i][0] = (
            AlignmentAction.INSERTION,
            {"": AlignmentEdge("", sources_count)},
            hyp_edge,
        )
    for i, ref_edges in enumerate(ref_edges_sets, start=1):
        memoization[0][i] = (AlignmentAction.DELETION, ref_edges, AlignmentEdge("", 1))

    for i, hyp_edge in enumerate(hyp_edges, start=1):
        hyp_word = hyp_edge and hyp_edge.value
        for j, ref_edges in enumerate(ref_edges_sets, start=1):
            ref_words_set = ref_edges.keys()
            is_hyp_word_in_ref = hyp_word in ref_words_set
            options: list[tuple[float, tuple[AlignmentAction, Edges, AlignmentEdge]]]
            if is_hyp_word_in_ref:
                options = [
                    (
                        distance[i - 1][j - 1],
                        (AlignmentAction.CORRECT, ref_edges, hyp_edge),
                    )
                ]
            else:
                options = [
                    (
                        distance[i - 1][j - 1] + 1,
                        (AlignmentAction.SUBSTITUTION, ref_edges, hyp_edge),
                    )
                ]
            options.append(
                (
                    distance[i][j - 1] + ("" not in ref_edges),
                    (AlignmentAction.DELETION, ref_edges, AlignmentEdge("", 1)),
                )
            )
            options.append(
                (
                    distance[i - 1][j] + 1,
                    (
                        AlignmentAction.INSERTION,
                        {"": AlignmentEdge("", sources_count)},
                        hyp_edge,
                    ),
                )
            )
            distance[i][j], memoization[i][j] = min(options, key=lambda t: t[0])

    alignment = []
    i = len(hyp_edges)
    j = len(ref_edges_sets)
    while i != 0 or j != 0:
        step = memoization[i][j]
        assert step is not None
        action, ref_edges, hyp_edge = step
        joined_edges = deepcopy(ref_edges)
        hyp_edge_word = hyp_edge.value
        if hyp_edge_word not in joined_edges:
            joined_edges[hyp_edge_word] = hyp_edge
        else:
            joined_edges[hyp_edge_word].sources_count += 1
        alignment.append(joined_edges)
        if action in (AlignmentAction.CORRECT, AlignmentAction.SUBSTITUTION):
            i -= 1
            j -= 1
        elif action == AlignmentAction.INSERTION:
            i -= 1
        else:
            j -= 1
    return alignment[::-1]


def crowdkit_rover(texts: list[str], *, bord_comme_interieur: bool = False) -> str:
    """``ROVER(str.split, " ".join).fit_predict`` pour une tâche, lectures dans
    l'ordre reçu."""
    hypotheses = [text.split() for text in texts]
    edges = [{word: AlignmentEdge(word, 1)} for word in hypotheses[0]]
    for sources_count, hyp in enumerate(hypotheses[1:], start=1):
        edges = _align(
            edges,
            [AlignmentEdge(word, 1) for word in hyp],
            sources_count,
            bord_comme_interieur,
        )
    result = []
    for edges_set in edges:
        _, _, value = max(
            (x.sources_count, len(x.value), x.value) for x in edges_set.values()
        )
        result.append(value)
    return " ".join(value for value in result if value != "")


# --- Parité -----------------------------------------------------------------


def _cinoc_order(lectures: dict[str, str]) -> list[str]:
    return [
        " ".join(m) for m in _ordre_d_alignement([t.split() for t in lectures.values()])
    ]


#: Fusions de ``bnl_mini`` (sur 30) où crowd-kit, dans l'ordre des noms de
#: moteurs, ne rend pas la fusion de Cinoc — l'écart 1, mesuré.
_ECARTS_ORDRE_DES_NOMS = {
    ("deu", "deu_latf", "easyocr"): 3,
    ("deu", "deu_latf", "fra"): 5,
    ("deu", "deu_latf", "frk"): 3,
    ("deu", "easyocr", "fra"): 15,
    ("deu", "easyocr", "frk"): 14,
    ("deu", "fra", "frk"): 4,
    ("deu_latf", "easyocr", "fra"): 15,
    ("deu_latf", "easyocr", "frk"): 5,
    ("deu_latf", "fra", "frk"): 5,
    ("easyocr", "fra", "frk"): 5,
}


@pytest.mark.parametrize("triplet", list(itertools.combinations(_MOTEURS, 3)))
def test_same_input_same_output_on_bnl_mini(triplet: tuple[str, str, str]) -> None:
    """Chaque page de chaque triplet : crowd-kit, lectures dans l'ordre de
    Cinoc, rend la fusion de Cinoc — bord compris (il ne joue pas ici)."""
    pages = sorted(p.name.removesuffix(".gt.txt") for p in _BNL_MINI.glob("*.gt.txt"))
    assert len(pages) == 30
    ecarts = 0
    for page in pages:
        lectures = {
            moteur: (_BNL_MINI / f"{page}.{moteur}.txt").read_text(encoding="utf-8")
            for moteur in triplet
        }
        fusion = vote_tokens(lectures)
        assert crowdkit_rover(_cinoc_order(lectures)) == fusion, page
        ecarts += crowdkit_rover(list(lectures.values())) != fusion
    assert sum(_ECARTS_ORDRE_DES_NOMS.values()) == 74
    assert ecarts == _ECARTS_ORDRE_DES_NOMS[triplet]


def test_the_border_is_the_only_other_gap() -> None:
    """5 000 jeux de 2 à 5 lectures courtes (graine fixe) : avec le bord de
    Cinoc, la transcription égale Cinoc partout ; sans, elle en diffère sur
    559 — le bord de crowd-kit est le seul écart restant."""
    rng = random.Random(1)
    mots = ("le", "la", "un", "soleil", "lune")
    ecarts = 0
    for _ in range(5_000):
        lectures = {
            f"s{k}": " ".join(rng.choice(mots) for _ in range(rng.randint(0, 4)))
            for k in range(rng.randint(2, 5))
        }
        ordre = _cinoc_order(lectures)
        fusion = vote_tokens(lectures)
        assert crowdkit_rover(ordre, bord_comme_interieur=True) == fusion, lectures
        ecarts += crowdkit_rover(ordre) != fusion
    assert ecarts == 559


def test_a_border_case_spelled_out() -> None:
    """« la » · « le la lune » · « lune soleil » (ordre de Cinoc) : la case
    nouvelle de « lune » et l'absence de « le » coûtent au bord chez crowd-kit
    ce qu'elles ne coûtent pas à l'intérieur — deux réseaux, deux fusions."""
    lectures = {"a": "la", "b": "le la lune", "c": "lune soleil"}
    assert _cinoc_order(lectures) == ["la", "le la lune", "lune soleil"]
    assert vote_tokens(lectures) == "la soleil"
    assert crowdkit_rover(_cinoc_order(lectures)) == "lune la"
