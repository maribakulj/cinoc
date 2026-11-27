"""Révision 3, N6 (§ 2.4 a) : filiation = géométrie identique ; id en 4ᵉ critère.
« Pourquoi la géométrie identique suffit. Une paire héritée a IoU = 1. Elle
appartient donc TOUJOURS à un optimum des critères 1 et 2 ».

(a) Rejeu de r2_r11 (échange d'ids entre régions qui se recouvrent) sous la règle
    révisée : levé (region_cer 0).
(b) La phrase citée est fausse dès que la VT a des régions qui se recouvrent
    (PAGE l'autorise ; § 2.4 c ne les marque `ref_overlap` que pour les fusions).
    Le critère 1 (nombre de paires) prime sur l'IoU : une paire héritée à IoU 1
    peut être exclue de TOUT optimum. VT r1 (page), r2 (60 % du haut) ; la
    brique garde r1 à l'identique (id r1) et remplace r2 par une région h2
    (40 %-100 %). Optimum (énumération) : r1↔h2, r2↔h1 — la copie conforme de
    r1 est appariée à r2.
"""
import itertools
from fractions import Fraction as F
from rapidfuzz.distance import Levenshtein as L
def inter(a, b): return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
def area(a): return (a[2]-a[0]) * (a[3]-a[1])
def iou(a, b): i = inter(a, b); return F(i, area(a) + area(b) - i)
def adm(a, b): return 2 * inter(a, b) >= area(a) + area(b) - inter(a, b)        # O2 inclusif
def optimum(R, H, inherited=()):
    best = None
    for perm in itertools.permutations(range(len(H)), len(R)):
        ps = [(i, j) for i, j in enumerate(perm) if adm(R[i][1], H[j][1])]
        key = (len(ps), sum(iou(R[i][1], H[j][1]) for i, j in ps),
               -sum(L.distance(R[i][2], H[j][2]) for i, j in ps),
               sum((R[i][0], H[j][0]) in inherited for i, j in ps))
        if best is None or key > best[0]: best = (key, ps)
    return best
def rcer(R, H, ps):
    e = sum(L.distance(R[i][2], H[j][2]) for i, j in ps)
    e += sum(len(R[i][2]) for i in range(len(R)) if i not in {a for a, _ in ps})
    e += sum(len(H[j][2]) for j in range(len(H)) if j not in {b for _, b in ps})
    return e / sum(len(r[2]) for r in R)

R = [("r1", (0, 0, 100, 100), "TITRE corps du texte"), ("r2", (0, 0, 100, 60), "TITRE")]
# (a) ids échangés : géométries plus identiques -> aucune filiation
H = [("r1", (0, 0, 100, 60), "TITRE"), ("r2", (0, 0, 100, 100), "TITRE corps du texte")]
inh = {(r[0], h[0]) for r in R for h in H if r[0] == h[0] and r[1] == h[1]}
k, ps = optimum(R, H, inh); print("(a) filiation :", inh or "aucune", "| region_cer =", rcer(R, H, ps))
assert not inh and rcer(R, H, ps) == 0
# (b) r1 hérité à l'identique, r2 remplacé par h2
H = [("r1", (0, 0, 100, 100), "TITRE corps du texte"), ("h2", (0, 40, 100, 100), "corps du texte")]
inh = {(r[0], h[0]) for r in R for h in H if r[0] == h[0] and r[1] == h[1]}
k, ps = optimum(R, H, inh)
print("(b) paire héritée :", inh, "| optimum :", [(R[i][0], H[j][0]) for i, j in ps], "| clé", k[:2])
assert ("r1", "r1") in inh and (0, 0) not in ps
print("    region_cer à l'optimum =", round(rcer(R, H, ps), 3), "| avec la paire héritée gardée =",
      round(rcer(R, H, [(0, 0)]), 3))
print("=> soit la paire héritée est FIXÉE avant l'optimisation (et l'optimum porte sur le reste),"
      " soit la phrase « appartient toujours à un optimum » est retirée et M8 le dit.")
