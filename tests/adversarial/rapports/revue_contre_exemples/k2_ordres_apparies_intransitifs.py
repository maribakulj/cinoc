"""A6 « deux pipelines ne s'ordonnent que sur leur support apparié » ; §2.1c
« Global ... tri multi-pipelines du tableau » ; §6 n° 14.

Les ordres appariés, chacun sur son propre support, peuvent former un cycle
(A < B < C < A), et le tri sur le support global peut contredire un ordre
apparié publié à côté. CER micro, erreurs/caractères ; None = indisponible.
"""
n = {"d1": 100, "d2": 100, "d3": 100, "d4": 100}
E = {"A": {"d1": 1, "d2": 5, "d3": None, "d4": 3},
     "B": {"d1": None, "d2": 2, "d3": 6, "d4": 3},
     "C": {"d1": 4, "d2": None, "d3": 1, "d4": 3}}
def micro(p, docs): return sum(E[p][d] for d in docs) / sum(n[d] for d in docs)
def support(*ps): return [d for d in n if all(E[p][d] is not None for p in ps)]
winners = []
for a, b in (("A", "B"), ("B", "C"), ("C", "A")):
    s = support(a, b)
    winners.append(a if micro(a, s) < micro(b, s) else b)
    print(f"{a} vs {b} sur {s} : {micro(a, s):.3f} vs {micro(b, s):.3f} ->", a if micro(a, s) < micro(b, s) else b, "meilleur")
g = support("A", "B", "C")
print("support global", g, ":", {p: micro(p, g) for p in "ABC"}, "-> aucun ordre")
assert winners == ["B", "C", "A"], "cycle"
