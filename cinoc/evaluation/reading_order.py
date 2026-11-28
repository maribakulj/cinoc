"""Distance entre deux ordres de lecture — fonctions pures (couche 3).

Comparer deux ordres n'est pas comparer deux textes. Un texte projeté dans le
mauvais ordre a un CER catastrophique, mais ce CER ne dit pas **où** est la
faute : dans la reconnaissance ou dans l'ordonnancement ? La distance de Kendall
répond à la seconde question seule.

Convention : on compte les **paires discordantes** — deux blocs que la référence
range dans un sens et l'hypothèse dans l'autre — normalisées par le nombre total
de paires. 0 = ordres identiques, 1 = ordre exactement inversé. C'est un
désaccord *relatif*, donc comparable entre pages de tailles différentes. Les
fonctions rendent les **comptes** (``Proportion``) : au corpus, le désaccord est
Σ discordantes / Σ paires (K1), pas une moyenne de ratios par page.
"""

from __future__ import annotations

from collections.abc import Sequence

from cinoc.evaluation.statistics import Proportion


def kendall_counts(reference: Sequence[str], hypothesis: Sequence[str]) -> Proportion:
    """(paires discordantes, paires) entre deux ordres, sur leurs blocs communs.

    Seuls les identifiants **présents des deux côtés** sont comparés : un bloc
    que l'hypothèse n'a pas trouvé relève de la détection, pas de l'ordre, et le
    compter ici mêlerait deux fautes que le rapport doit pouvoir distinguer.

    Aucune paire (moins de deux blocs communs) : la distance est indéfinie —
    une paire est le minimum pour qu'un « ordre » veuille dire quelque chose.
    """
    rang_ref = {bloc: i for i, bloc in enumerate(reference)}
    communs = [bloc for bloc in hypothesis if bloc in rang_ref]
    n = len(communs)
    discordantes = 0
    for i in range(n):
        for j in range(i + 1, n):
            # L'hypothèse place `i` avant `j` ; la référence est-elle d'accord ?
            if rang_ref[communs[i]] > rang_ref[communs[j]]:
                discordantes += 1
    return Proportion(count=discordantes, total=n * (n - 1) // 2)


def order_counts(reference: Sequence[str], hypothesis: Sequence[str]) -> Proportion:
    """(blocs de la référence ordonnés par l'hypothèse, blocs de la référence).

    Le compagnon indispensable de la distance : un ordre parfait sur deux blocs
    trouvés sur trente n'est pas un bon résultat, et la distance seule le
    dirait excellent.
    """
    attendus = set(reference)
    return Proportion(count=len(attendus & set(hypothesis)), total=len(attendus))


__all__ = ["kendall_counts", "order_counts"]
