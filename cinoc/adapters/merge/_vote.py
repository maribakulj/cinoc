"""Vote par jeton entre plusieurs transcriptions — fonctions pures.

Séparées de l'adapter pour se tester sans fichier ni workspace. La méthode est
celle qu'OCR-D applique avec ``cor-asv-ann-align`` : aligner les lectures, puis
choisir à chaque position ce que dit la majorité.

**Ce que le vote peut et ne peut pas.** Il corrige les erreurs qu'un seul moteur
commet ; il est impuissant — et c'est important de le dire — quand tous se
trompent pareil, ce qui arrive sur une écriture qu'aucun n'a apprise. Le banc
existe justement pour mesurer lequel des deux cas on est.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from difflib import SequenceMatcher


def align_tokens(
    reference: Sequence[str], autre: Sequence[str]
) -> list[tuple[str | None, str | None]]:
    """Aligne deux suites de jetons en paires ``(référence, autre)``.

    ``None`` d'un côté marque une absence — un jeton que l'une des lectures n'a
    pas. Alignement par ``SequenceMatcher`` avec ``autojunk`` désactivé : sur des
    textes courts, l'heuristique de « jetons populaires » écarte des mots
    fréquents et fausse l'appariement.
    """
    paires: list[tuple[str | None, str | None]] = []
    matcher = SequenceMatcher(None, list(reference), list(autre), autojunk=False)
    for balise, i1, i2, j1, j2 in matcher.get_opcodes():
        if balise == "equal":
            paires.extend(zip(reference[i1:i2], autre[j1:j2], strict=True))
        elif balise == "replace":
            gauche = list(reference[i1:i2])
            droite = list(autre[j1:j2])
            longueur = max(len(gauche), len(droite))
            gauche += [None] * (longueur - len(gauche))  # type: ignore[list-item]
            droite += [None] * (longueur - len(droite))  # type: ignore[list-item]
            paires.extend(zip(gauche, droite, strict=True))
        elif balise == "delete":
            paires.extend((jeton, None) for jeton in reference[i1:i2])
        else:  # insert
            paires.extend((None, jeton) for jeton in autre[j1:j2])
    return paires


def vote_tokens(lectures: dict[str, str]) -> str:
    """Fusionne plusieurs lectures par vote majoritaire, jeton par jeton.

    La première lecture, **par ordre alphabétique d'identifiant de source**, sert
    de squelette d'alignement : il faut un pivot, et le choisir par un ordre
    stable rend la fusion déterministe — deux exécutions du même run donnent le
    même texte, ce qui est un invariant du banc et pas un détail.

    Égalité de voix → le jeton du pivot l'emporte. Une majorité d'absences →
    le jeton disparaît : si la plupart des moteurs n'ont rien lu là, en garder
    un inventerait du texte.
    """
    if not lectures:
        return ""
    noms = sorted(lectures)
    pivot_nom = noms[0]
    pivot = lectures[pivot_nom].split()
    if len(noms) == 1:
        return " ".join(pivot)

    # Pour chaque position du pivot, les avis alignés des autres lectures.
    avis: list[list[str | None]] = [[jeton] for jeton in pivot]
    for nom in noms[1:]:
        position = 0
        supplementaires: list[tuple[int, str]] = []
        for attendu, propose in align_tokens(pivot, lectures[nom].split()):
            if attendu is None:
                # Jeton que seule cette lecture voit : noté à part, il ne peut
                # pas gagner un vote auquel le pivot ne participe pas.
                if propose is not None:
                    supplementaires.append((position, propose))
                continue
            if position < len(avis):
                avis[position].append(propose)
            position += 1
        del supplementaires

    sortie: list[str] = []
    for index, colonne in enumerate(avis):
        comptes = Counter(j for j in colonne if j is not None)
        absences = sum(1 for j in colonne if j is None)
        if not comptes or absences > len(colonne) / 2:
            continue
        meilleur = max(comptes.values())
        candidats = [j for j, n in comptes.items() if n == meilleur]
        # Égalité → le pivot tranche (il est toujours dans la colonne).
        sortie.append(pivot[index] if pivot[index] in candidats else candidats[0])
    return " ".join(sortie)


__all__ = ["align_tokens", "vote_tokens"]
