"""Révision 2, R1 / M6 : Σ conf en `Fraction`, addition exacte, une conversion à la
finalisation. Rejoue le contre-exemple de la revue et mesure le coût sur 200 000
jetons (ordre de grandeur d'une campagne)."""
import math, random, time
from fractions import Fraction as F
doc1, doc2 = [0.1, 0.2], [0.3]
pooled = sum(map(F, doc1 + doc2)); per_doc = sum(map(F, doc1)) + sum(map(F, doc2))
print("contre-exemple de la revue : poolé == par document :", pooled == per_doc, "->", float(abs(0 - pooled) / 3))
assert pooled == per_doc
random.seed(1); confs = [random.random() for _ in range(200_000)]
t = time.perf_counter(); s = sum(map(F, confs), F(0)); tf = time.perf_counter() - t
t = time.perf_counter(); math.fsum(confs); tm = time.perf_counter() - t
print(f"200 000 jetons : Fraction {tf:.2f} s (dénominateur {s.denominator.bit_length()} bits), fsum {tm*1e3:.1f} ms")
# partition et ordre quelconques
parts = [confs[i::7] for i in range(7)]; random.shuffle(parts)
assert sum((sum(map(F, p), F(0)) for p in parts), F(0)) == s
print("partition en 7 et ordre mélangé : égalité exacte (==) vérifiée")
