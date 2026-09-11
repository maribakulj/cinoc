"""Vote par jeton : ce qu'il rattrape, et ce qu'il ne peut pas rattraper.

Le banc savait comparer des moteurs ; il ne savait pas en **combiner**. Ce que
ces tests fixent, ce sont les deux moitiés de la promesse — le vote corrige les
erreurs qu'**un** moteur commet là où les autres ont juste, et il est impuissant
quand tous se trompent pareil. Taire la seconde moitié ferait croire à une
méthode qui répare tout.
"""

from __future__ import annotations

from cinoc.adapters.merge._vote import align_tokens, vote_tokens


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


def test_a_tie_is_broken_by_the_pivot_not_by_chance() -> None:
    """Deux voix contre deux : le pivot tranche, et le pivot est choisi par un
    ordre stable — sans quoi deux exécutions du même run divergeraient."""
    lectures = {"a": "le soleil", "b": "le soleil", "c": "la lune", "d": "la lune"}
    assert vote_tokens(lectures) == "le soleil"


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


def test_alignment_marks_absences_on_both_sides() -> None:
    paires = align_tokens(["le", "grand", "soleil"], ["le", "soleil"])
    assert ("grand", None) in paires
    assert ("le", "le") in paires


def test_alignment_handles_a_pure_insertion() -> None:
    paires = align_tokens(["le", "soleil"], ["le", "beau", "soleil"])
    assert (None, "beau") in paires
