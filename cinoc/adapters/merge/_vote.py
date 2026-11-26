"""Vote entre plusieurs transcriptions : un ROVER — fonctions pures.

Séparées de l'adapter pour se tester sans fichier ni workspace. La méthode est
**ROVER** (Fiscus, « A post-processing system to yield reduced word error
rates: Recognizer Output Voting Error Reduction », IEEE ASRU 1997, §2) : les
lectures sont alignées **une à une sur un réseau de confusion** de mots — chaque
case y garde le mot de chaque lecture déjà alignée, ou son absence — puis chaque
case élit son mot à la majorité.

**Indépendant du nom et de l'ordre des sources.** Le réseau d'un ROVER dépend de
l'ordre dans lequel on y aligne les lectures. Cet ordre est tiré du seul
**contenu** : la lecture la plus proche de toutes les autres d'abord (somme des
écarts entre sacs de mots, la plus petite), à écart égal la suite de mots la
plus petite dans l'ordre lexicographique. Renommer ou permuter les sources ne
change donc rien (D-287). L'ancien vote alignait en étoile sur la première
source par ordre alphabétique de **nom** : le WER fusionné en dépendait sur
chacun des dix triplets de moteurs de ``bnl_mini``.

**Coûts et départages** — ceux de crowd-kit (``crowdkit.aggregation.ROVER``,
référence citée par l'audit D-264) : un mot qui figure déjà dans la case coûte
0, un autre 1 ; une absence coûte 0 dans une case qui en a déjà une, 1 sinon ;
une case nouvelle (un mot que les lectures précédentes n'ont pas) coûte 1. À
coût égal : appariement, puis absence, puis case nouvelle. Une case élit le mot
du plus grand nombre de lectures ; à voix égales le plus long, puis le plus
grand dans l'ordre lexicographique ; l'absence ne l'emporte qu'avec strictement
plus de voix que chaque mot. Seule divergence voulue : le bord de la table
compte une absence comme son intérieur (0 dans une case qui en a déjà une),
quand crowd-kit la compte toujours 1.

**Ce que le vote peut et ne peut pas.** Il corrige les erreurs qu'un seul moteur
commet ; il est impuissant — et c'est important de le dire — quand tous se
trompent pareil, ce qui arrive sur une écriture qu'aucun n'a apprise. Le banc
existe justement pour mesurer lequel des deux cas on est.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

#: Une case du réseau : nombre de lectures par mot, ``None`` = absence.
Case = dict[str | None, int]

_APPARIE, _ABSENT, _NOUVELLE = 1, 2, 3


def _ordre_d_alignement(lectures: Sequence[Sequence[str]]) -> list[list[str]]:
    """Les lectures dans l'ordre où le ROVER les aligne — fonction du contenu seul.

    Clé : somme des écarts de sac de mots aux autres lectures (nombre de mots
    qu'il faut ajouter ou retirer pour passer de l'une à l'autre), puis la suite
    de mots. Deux lectures de même clé sont identiques, donc interchangeables.
    """
    sacs = [Counter(lecture) for lecture in lectures]

    def ecart(a: Counter[str], b: Counter[str]) -> int:
        return sum(((a - b) + (b - a)).values())

    cles = [
        (sum(ecart(sac, autre) for autre in sacs), list(lecture))
        for sac, lecture in zip(sacs, lectures, strict=True)
    ]
    return [lecture for _total, lecture in sorted(cles)]


def _aligner(reseau: list[Case], lecture: Sequence[str], deja: int) -> list[Case]:
    """Aligne ``lecture`` sur ``reseau`` (``deja`` lectures) ; le réseau élargi.

    Programmation dynamique de coût minimal (coûts du module). Chaque case du
    résultat compte une lecture de plus : le mot aligné, ou une absence ; une
    case nouvelle compte ``deja`` absences.
    """
    n, m = len(reseau), len(lecture)
    absence = [0 if None in case else 1 for case in reseau]
    precedente = [0] * (n + 1)
    for j in range(1, n + 1):
        precedente[j] = precedente[j - 1] + absence[j - 1]
    choix = [bytearray([_ABSENT]) * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        mot = lecture[i - 1]
        courante = [precedente[0] + 1] + [0] * n
        ligne = choix[i]
        ligne[0] = _NOUVELLE
        for j in range(1, n + 1):
            apparie = precedente[j - 1] + (mot not in reseau[j - 1])
            absent = courante[j - 1] + absence[j - 1]
            nouvelle = precedente[j] + 1
            if apparie <= absent and apparie <= nouvelle:
                courante[j], ligne[j] = apparie, _APPARIE
            elif absent <= nouvelle:
                courante[j] = absent
            else:
                courante[j], ligne[j] = nouvelle, _NOUVELLE
        precedente = courante

    elargi: list[Case] = []
    i, j = m, n
    while i or j:
        etape = choix[i][j]
        if etape == _NOUVELLE:
            case: Case = {None: deja}
            mot_aligne: str | None = lecture[i - 1]
            i -= 1
        else:
            case = dict(reseau[j - 1])
            mot_aligne = lecture[i - 1] if etape == _APPARIE else None
            i, j = (i - 1, j - 1) if etape == _APPARIE else (i, j - 1)
        case[mot_aligne] = case.get(mot_aligne, 0) + 1
        elargi.append(case)
    elargi.reverse()
    return elargi


def _elire(case: Case) -> str | None:
    """Le mot élu d'une case (``None`` : l'absence l'emporte)."""
    return max(case.items(), key=lambda kv: (kv[1], len(kv[0] or ""), kv[0] or ""))[0]


def vote_tokens(lectures: Mapping[str, str]) -> str:
    """Fusionne plusieurs lectures par ROVER (vote majoritaire au mot).

    Les noms des sources ne servent pas : le résultat ne dépend que des textes.
    """
    ordonnees = _ordre_d_alignement([texte.split() for texte in lectures.values()])
    if not ordonnees:
        return ""
    reseau: list[Case] = [{mot: 1} for mot in ordonnees[0]]
    for deja, lecture in enumerate(ordonnees[1:], start=1):
        reseau = _aligner(reseau, lecture, deja)
    return " ".join(mot for mot in map(_elire, reseau) if mot is not None)


__all__ = ["vote_tokens"]
