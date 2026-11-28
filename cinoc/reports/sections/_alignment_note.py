"""Le chemin d'alignement des analyses qui nomment des éditions (couche 7).

Les comptes des métriques (CER, WER…) sont **canoniques** (parmi les alignements
de coût minimal, celui qui maximise les substitutions, P1) ; les analyses qui
**nomment** des éditions — confusions, taxonomie, cartes de mots, fidélité, suites
d'éditions de la correction, diff surligné — suivent l'alignement de RapidFuzz.
Les deux ne se décomposent pas l'un l'autre sur les ex æquo d'alignement
(« ab » → « ba » : canonique (2, 0, 0), RapidFuzz (0, 1, 1)).

Une seule lecture, partagée : le chemin du payload est écrit à côté des éditions
(D8, ``CONTRATS.md`` § 2.1 f), et quand ``matches_canonical_counts`` est faux,
aucune phrase ne présente ces éditions comme la décomposition des comptes
canoniques.
"""

from __future__ import annotations

from cinoc.reports.html import escape, localized


def alignment_note(path: str, lang: str, *, concordant: bool | None = None) -> str:
    """« Chemin d'alignement : rapidfuzz », et, si ``concordant`` est faux, que
    ces éditions ne décomposent pas exactement les comptes canoniques."""
    name = f"<code>{escape(path)}</code>"
    note = localized(
        lang,
        f"Chemin d'alignement : {name}. Les éditions nommées ici suivent cet "
        "alignement ; les comptes des métriques sont canoniques.",
        f"Alignment path: {name}. The edits named here follow this alignment; "
        "the metrics' counts are canonical.",
    )
    if concordant is False:
        note += localized(
            lang,
            " Sur au moins un document, les deux répartissent autrement les "
            "substitutions, suppressions et insertions (ex æquo d'alignement) : "
            "ces éditions ne décomposent pas les comptes canoniques.",
            " On at least one document the two split substitutions, deletions "
            "and insertions differently (alignment ties): these edits do not "
            "break down the canonical counts.",
        )
    return f'<p class="muted">{note}</p>\n'


__all__ = ["alignment_note"]
