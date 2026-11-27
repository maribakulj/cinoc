"""Révision 4, rejeu de C4 (paires héritées FIXÉES avant l'optimisation, qui porte sur
le reste) et de C5 (invention hors référence sur le support APPARIÉ)."""
import r3_n6_heritage_hors_optimum as N6   # (exécute aussi ses propres assertions)
R = N6.R
H = [("r1", (0, 0, 100, 100), "TITRE corps du texte"), ("h2", (0, 40, 100, 100), "corps du texte")]
fixed = [(i, j) for i, r in enumerate(R) for j, h in enumerate(H) if r[0] == h[0] and r[1] == h[1]]
restR = [r for i, r in enumerate(R) if i not in {a for a, _ in fixed}]
restH = [h for j, h in enumerate(H) if j not in {b for _, b in fixed}]
_, rest = N6.optimum(restR, restH)
pairs = fixed + [(R.index(restR[i]), H.index(restH[j])) for i, j in rest]
print("C4 : paires =", [(R[i][0], H[j][0]) for i, j in pairs], "| region_cer =", round(N6.rcer(R, H, pairs), 3))
assert (0, 0) in pairs and round(N6.rcer(R, H, pairs), 2) == 0.76
import r3_invention_hors_reference as C5
print("C5 : sur le support apparié, A et B identiques :", C5.pair["A"] == C5.pair["B"])
