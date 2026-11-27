"""Révision 2, R5 : « D^M = {d : la référence définit le scalaire}, n_réf > 0 ou
tp + fn > 0 » ; A4 : « Δ macro sur D^M_AB avec D^M fixé par la référence : IL VOIT
L'HALLUCINATION D'UN DOCUMENT SANS RÉFÉRENCE ».

Le contre-exemple de la revue rejoué sous la nouvelle définition : le document
sans entité de référence (tp + fn = 0) est HORS de D^M, par définition. Le
support est bien symétrique (R5 levé sur ce point), mais le Δ macro reste
aveugle à l'hallucination : la phrase de A4 est fausse. Seul le micro la voit.
"""
def f1(tp, fp, fn):
    den = 2 * tp + fp + fn
    return None if den == 0 else 2 * tp / den
A = {"d1": (5, 0, 0), "d2": (0, 5, 0)}
B = {"d1": (5, 0, 0), "d2": (0, 0, 0)}
DM = {d for d, (tp, fp, fn) in A.items() if tp + fn > 0}          # fixé par la référence (tp+fn identique pour A et B)
assert DM == {d for d, (tp, fp, fn) in B.items() if tp + fn > 0}
delta_macro = sum(f1(*A[d]) - f1(*B[d]) for d in DM) / len(DM)
micro = {p: f1(*map(sum, zip(*S.values()))) for p, S in {"A": A, "B": B}.items()}
print("D^M =", sorted(DM), "| Δ macro =", delta_macro, "| micro =", micro)
assert delta_macro == 0.0 and micro["B"] > micro["A"]
print("=> A4 doit dire : le macro ne voit pas l'hallucination d'un document sans référence ; le micro la voit.")
