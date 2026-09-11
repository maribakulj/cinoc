"""Distance entre deux ordres de lecture — fonctions pures (couche 3).

Comparer deux ordres n'est pas comparer deux textes. Un texte projeté dans le
mauvais ordre a un CER catastrophique, mais ce CER ne dit pas **où** est la
faute : dans la reconnaissance ou dans l'ordonnancement ? La distance de Kendall
répond à la seconde question seule.

Convention : on compte les **paires discordantes** — deux blocs que la référence
range dans un sens et l'hypothèse dans l'autre — normalisées par le nombre total
de paires. 0 = ordres identiques, 1 = ordre exactement inversé. C'est un
désaccord *relatif*, donc comparable entre pages de tailles différentes.
"""

from __future__ import annotations

from collections.abc import Sequence


def kendall_distance(
    reference: Sequence[str], hypothesis: Sequence[str]
) -> float | None:
    """Distance de Kendall normalisée entre deux ordres, sur leurs blocs communs.

    Seuls les identifiants **présents des deux côtés** sont comparés : un bloc
    que l'hypothèse n'a pas trouvé relève de la détection, pas de l'ordre, et le
    compter ici mêlerait deux fautes que le rapport doit pouvoir distinguer.

    ``None`` s'il y a moins de deux blocs communs — une paire est le minimum
    pour qu'un « ordre » veuille dire quelque chose.
    """
    rang_ref = {bloc: i for i, bloc in enumerate(reference)}
    communs = [bloc for bloc in hypothesis if bloc in rang_ref]
    n = len(communs)
    if n < 2:
        return None
    discordantes = 0
    for i in range(n):
        for j in range(i + 1, n):
            # L'hypothèse place `i` avant `j` ; la référence est-elle d'accord ?
            if rang_ref[communs[i]] > rang_ref[communs[j]]:
                discordantes += 1
    return discordantes / (n * (n - 1) / 2)


def order_coverage(reference: Sequence[str], hypothesis: Sequence[str]) -> float | None:
    """Part des blocs de la référence que l'hypothèse a effectivement ordonnés.

    Le compagnon indispensable de la distance : un ordre parfait sur deux blocs
    trouvés sur trente n'est pas un bon résultat, et la distance seule le
    dirait excellent.
    """
    attendus = set(reference)
    if not attendus:
        return None
    return len(attendus & set(hypothesis)) / len(attendus)


__all__ = ["kendall_distance", "order_coverage"]
