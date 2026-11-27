"""§2.1b « execution : ok | truncated | partial — étiquette ... sans effet sur les
supports » ; §2.1e « Rien n'est imputé par défaut » ; A7.

Un fan-out `partial` (une région en échec, `fanout.py:230-235` l'ignore) produit
un texte où la région manquante est absente : sa référence compte en
suppressions, c.-à-d. une imputation « page vide » LOCALE, par défaut.
Un fan-out dont TOUTES les régions échouent est `failed` : exclu, rien
d'imputé. Plus d'échecs ⇒ meilleur agrégat : non-monotonie.
"""
from rapidfuzz.distance import Levenshtein as L

pages = {  # (référence région 1, référence région 2)
    "p1": ("abcdefghij", "klmnopqrst"),
    "p2": ("uvwxyzabcd", "efghijklmn"),
}
def cer_micro(outputs):
    e = n = 0
    for p, out in outputs.items():
        if out is None:          # step_failed : hors support (pas d'imputation)
            continue
        ref = "\n".join(pages[p]); e += L.distance(ref, out); n += len(ref)
    return e / n

# P : sur p2, une région sur deux échoue  -> partial, la région est absente du texte
P = {"p1": "\n".join(pages["p1"]), "p2": pages["p2"][0]}
# Q : sur p2, les DEUX régions échouent   -> failed, exclu
Q = {"p1": "\n".join(pages["p1"]), "p2": None}
print("P (1 échec de région, partial) CER micro =", round(cer_micro(P), 4))
print("Q (2 échecs de région, failed) CER micro =", round(cer_micro(Q), 4))
assert cer_micro(Q) < cer_micro(P)
print("=> Q échoue davantage et note mieux : `partial` impute « page vide » à la "
      "région en échec, contrairement à A7. Il faut un axe/motif pour la part "
      "manquante, ou la même règle pour `partial` et `failed`.")
