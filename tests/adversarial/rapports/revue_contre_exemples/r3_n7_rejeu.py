"""Révision 3, rejeu de N7 : membres d'un groupe non ordonné linéarisés par (y0, x0)
puis id, jamais par l'ordre de déclaration. Deux déclarations permutées d'une même
VT donnent la même projection, donc le même CER (contre 0,919 / 0,0 en révision 2)."""
from rapidfuzz.distance import Levenshtein as L
members = {"m1": ((50, 800), "Nota bene en marge"), "m2": ((50, 1200), "Renvoi au folio 12")}  # (x0, y0)
def project(decl): return "\n".join(members[m][1] for m in sorted(decl, key=lambda m: (members[m][0][1], members[m][0][0], m)))
hyp = "\n".join([members["m2"][1], members["m1"][1]])
a, b = project(["m1", "m2"]), project(["m2", "m1"])
cer = lambda r: L.distance(r, hyp) / len(r)
print("projection identique :", a == b, "| CER =", round(cer(a), 3), round(cer(b), 3))
assert a == b and cer(a) == cer(b)
