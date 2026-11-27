"""K2 §2.1c « D^M_P = {d : scalaire défini} », « D^M_AB = D^M_A ∩ D^M_B »,
A4 (Δ macro apparié) et A6 (classement sur le support apparié).

Pour les familles dont le dénominateur du scalaire dépend de l'HYPOTHÈSE
(F1 = 2tp/(2tp+fp+fn) ; P ; MER ; unanchored_trigrams), le support macro
dépend du pipeline : un document sans entité de référence est « défini »
(F1 = 0) pour qui hallucine et « indéfini » pour qui se tait. L'intersection
retire donc exactement le document où B est parfait et A faux.
"""
def f1(tp, fp, fn):
    den = 2 * tp + fp + fn
    return None if den == 0 else 2 * tp / den

# (tp, fp, fn) par document
A = {"d1": (5, 0, 0), "d2": (0, 5, 0)}   # d2 : aucune entité de référence, A en invente 5
B = {"d1": (5, 0, 0), "d2": (0, 0, 0)}   # B : parfait partout

def micro(S):
    tp, fp, fn = map(sum, zip(*S.values()))
    return f1(tp, fp, fn)

DM = {p: {d for d, s in S.items() if f1(*s) is not None} for p, S in {"A": A, "B": B}.items()}
DM_AB = DM["A"] & DM["B"]
macro_cond = {p: sum(f1(*S[d]) for d in DM[p]) / len(DM[p]) for p, S in {"A": A, "B": B}.items()}
delta_macro = sum(f1(*A[d]) - f1(*B[d]) for d in DM_AB) / len(DM_AB)
print("D^M_A =", sorted(DM["A"]), " D^M_B =", sorted(DM["B"]), " D^M_AB =", sorted(DM_AB))
print("macro conditionnel :", macro_cond)
print("Δ macro apparié (A-B) =", delta_macro, " -> A et B ex aequo sur le support apparié")
print("micro :", {"A": micro(A), "B": micro(B)})
assert delta_macro == 0.0 and micro(B) > micro(A)
# B domine A document par document (fp de A sur d2, rien d'autre)
print("B domine A sur chaque document, mais A6 interdit tout ordre hors D^M_AB : "
      "le Δ macro apparié est aveugle à l'hallucination.")

# Même phénomène, MER : ref vide, A hallucine (MER=1), B vide (MER indéfini)
def mer(h, s, d, i):
    den = h + s + d + i
    return None if den == 0 else (s + d + i) / den
print("MER d2 : A =", mer(0, 0, 0, 7), " B =", mer(0, 0, 0, 0))
