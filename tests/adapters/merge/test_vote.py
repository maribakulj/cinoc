"""Vote ROVER : ce qu'il rattrape, ce qu'il ne peut pas rattraper, et ce dont
il ne dépend pas — le nom des sources.

Le banc savait comparer des moteurs ; il ne savait pas en **combiner**. Ce que
ces tests fixent, ce sont les deux moitiés de la promesse — le vote corrige les
erreurs qu'**un** moteur commet là où les autres ont juste, et il est impuissant
quand tous se trompent pareil. Taire la seconde moitié ferait croire à une
méthode qui répare tout.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import jiwer

from cinoc.adapters.merge._vote import vote_tokens

_BNL_MINI = Path(__file__).parents[2] / "fixtures" / "reference_corpus" / "bnl_mini"
_MOTEURS = ("deu", "deu_latf", "easyocr", "fra", "frk")


def test_a_lone_error_is_outvoted() -> None:
    """Deux moteurs contre un : la faute isolée tombe."""
    fusion = vote_tokens(
        {
            "a": "le soleil luisoit",
            "b": "le soleil luiſoit",
            "c": "le soleil luisoit",
        }
    )
    assert fusion == "le soleil luisoit"


def test_two_separate_errors_are_both_corrected() -> None:
    """Chaque position vote pour elle-même : deux fautes à deux endroits
    différents tombent toutes les deux, même si aucune lecture n'est parfaite."""
    fusion = vote_tokens(
        {
            "a": "le soleil luisoit sur la ville",
            "b": "le soleil luiſoit sur la ville",
            "c": "le soleil luisoit sur la villc",
        }
    )
    assert fusion == "le soleil luisoit sur la ville"


def test_a_shared_error_survives_the_vote() -> None:
    """La limite, énoncée plutôt que tue.

    Quand tous les moteurs se trompent pareil — ce qui arrive sur une écriture
    qu'aucun n'a apprise — le vote entérine l'erreur. Une méthode de fusion qui
    prétendrait le contraire tromperait sur ce qu'elle mesure.
    """
    fusion = vote_tokens({"a": "le ſoleil", "b": "le ſoleil", "c": "le ſoleil"})
    assert fusion == "le ſoleil"


def test_a_majority_of_absences_drops_the_token() -> None:
    """Si la plupart n'ont rien lu là, en garder un inventerait du texte."""
    fusion = vote_tokens({"a": "le grand soleil", "b": "le soleil", "c": "le soleil"})
    assert fusion == "le soleil"


def test_a_tie_is_broken_by_content_not_by_source_names() -> None:
    """Deux voix contre deux : le départage lit les mots (le plus long, puis le
    plus grand dans l'ordre lexicographique), jamais le nom des sources — sans
    quoi renommer un moteur changerait la fusion."""
    lectures = {"a": "le soleil", "b": "le soleil", "c": "la lune", "d": "la lune"}
    renommees = {"d": "le soleil", "c": "le soleil", "b": "la lune", "a": "la lune"}
    assert vote_tokens(lectures) == vote_tokens(renommees) == "le soleil"


def test_an_insertion_read_by_the_majority_survives() -> None:
    """Un mot que la première source (par nom) n'a pas lu mais que les deux
    autres lisent reste : l'ancien vote en étoile le perdait, la fusion
    dépendait alors du nom des sources (« le soleil » ou « le grand soleil »)."""
    textes = ("le soleil", "le grand soleil", "le grand soleil")
    for noms in itertools.permutations("abc"):
        lectures = dict(zip(noms, textes, strict=True))
        assert vote_tokens(lectures) == "le grand soleil"


def test_an_insertion_read_by_a_minority_is_dropped() -> None:
    textes = ("le grand soleil", "le soleil", "le soleil")
    for noms in itertools.permutations("abc"):
        assert vote_tokens(dict(zip(noms, textes, strict=True))) == "le soleil"


def _pages() -> list[str]:
    return sorted(p.name.removesuffix(".gt.txt") for p in _BNL_MINI.glob("*.gt.txt"))


def test_renaming_the_sources_changes_nothing_on_bnl_mini() -> None:
    """Critère S15 : sur de l'OCR réel (``bnl_mini``, chaque triplet des cinq
    moteurs, 30 pages), renommer les sources — ici en inversant l'ordre de
    leurs noms — laisse chaque page fusionnée, donc le WER fusionné, identique.
    L'ancien vote en étoile changeait de résultat sur les dix triplets (WER
    fusionné de 0,2756 à 0,4002 pour ``deu``/``easyocr``/``fra``)."""
    pages = _pages()
    assert len(pages) == 30
    verites = [
        " ".join((_BNL_MINI / f"{p}.gt.txt").read_text(encoding="utf-8").split())
        for p in pages
    ]
    for triplet in itertools.combinations(_MOTEURS, 3):
        fusions = []
        for noms in (("a", "b", "c"), ("c", "b", "a")):
            fusions.append(
                [
                    vote_tokens(
                        {
                            nom: (_BNL_MINI / f"{p}.{moteur}.txt").read_text(
                                encoding="utf-8"
                            )
                            for nom, moteur in zip(noms, triplet, strict=True)
                        }
                    )
                    for p in pages
                ]
            )
        assert fusions[0] == fusions[1], triplet
        assert jiwer.wer(verites, fusions[0]) == jiwer.wer(verites, fusions[1])


def test_the_result_does_not_depend_on_insertion_order() -> None:
    """Déterminisme : c'est un invariant du banc, pas un détail de cette brique."""
    lectures = {
        "a": "le soleil luisoit",
        "b": "le soleil luiſoit",
        "c": "le solcil luisoit",
    }
    a = vote_tokens(lectures)
    b = vote_tokens(dict(reversed(list(lectures.items()))))
    assert a == b


def test_a_single_reading_passes_through() -> None:
    """Rien à fusionner : on rend ce qu'on a, sans rien inventer."""
    assert vote_tokens({"a": "le ſoleil"}) == "le ſoleil"


def test_no_reading_gives_nothing() -> None:
    assert vote_tokens({}) == ""
