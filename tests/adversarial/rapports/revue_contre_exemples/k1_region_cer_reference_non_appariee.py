"""K1 table « Texte par région » : S = (éditions sur paires bijectives + texte non
apparié de l'HYPOTHÈSE, car. réf.) ; M4 idem. Le texte des régions de
RÉFÉRENCE non appariées n'est ni au numérateur ni (selon lecture) exclu du
dénominateur. Le code actuel (`metrics/layout.py:103-108`) le compte en
suppressions intégrales ; la formulation révisée le perd.
"""
from rapidfuzz.distance import Levenshtein as L

ref = {"r1": "abcdefghij", "r2": "klmnopqrst"}       # deux régions de référence
hyp_one = {"h1": "abcdefghij"}                          # P : ne trouve que r1, parfaitement
pairs = {"r1": "h1"}
hyp_both = {"h1": "abcdefghij", "h2": "klmnopqrsX"}     # Q : trouve tout, une faute
pairs_q = {"r1": "h1", "r2": "h2"}

def doc_formula(ref, hyp, pairs, denom="all"):
    e = sum(L.distance(ref[r], hyp[h]) for r, h in pairs.items())
    e += sum(len(t) for h, t in hyp.items() if h not in pairs.values())
    n = sum(len(t) for r, t in ref.items() if denom == "all" or r in pairs)
    return e / n

def current_code(ref, hyp, pairs):
    e = sum(L.distance(t, hyp.get(pairs.get(r, ""), "")) for r, t in ref.items())
    e += sum(len(t) for h, t in hyp.items() if h not in pairs.values())
    return e / sum(len(t) for t in ref.values())

for name, (h, p) in {"P (moitié manquante)": (hyp_one, pairs), "Q (tout, 1 faute)": (hyp_both, pairs_q)}.items():
    print(f"{name:22s} formule CONTRATS (dén. total) = {doc_formula(ref, h, p):.3f} | "
          f"(dén. apparié) = {doc_formula(ref, h, p, 'paired'):.3f} | code actuel = {current_code(ref, h, p):.3f}")
assert doc_formula(ref, hyp_one, pairs) < doc_formula(ref, hyp_both, pairs_q)
print("=> sous la formule révisée, perdre une région entière note mieux qu'une faute de frappe.")
