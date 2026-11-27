"""§2.1d « Analyses de rangs : Wilcoxon signé (paire, sur D^M_AB) ; Friedman +
Nemenyi (famille, sur D^M_F) — telles qu'aujourd'hui » ; A9 « des pipelines
aux sorties identiques ne sont jamais fusionnés » ; A5.

(1) Wilcoxon : les différences nulles (deux pages parfaites des deux côtés,
    fréquent en CER) sont écartées par défaut (`zero_method="wilcox"`) : le n
    effectif n'est pas |D^M_AB| ; avec des ex æquo, la p dépend de `method`.
(2) Deux pipelines identiques gardés : Wilcoxon et Friedman indéfinis.
(3) Friedman exige ≥ 3 pipelines : une famille de 2 n'a pas d'analyse globale.
"""
import warnings
import numpy as np
from scipy import stats

a = np.array([0.00, 0.00, 0.00, 0.10, 0.20, 0.10, 0.30, 0.05])
b = np.array([0.00, 0.00, 0.00, 0.20, 0.10, 0.20, 0.40, 0.15])
d = a - b
print("|D^M_AB| =", len(d), " différences nulles :", int(np.sum(d == 0)))
for zm in ("wilcox", "pratt", "zsplit"):
    for method in ("auto", "exact", "approx"):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                r = stats.wilcoxon(a, b, zero_method=zm, method=method)
                out = f"p = {r.pvalue:.4f}"
            except Exception as exc:
                out = f"{type(exc).__name__}: {exc}"
        print(f"  zero_method={zm:6s} method={method:6s} {out}" + (f"  [{w[0].category.__name__}]" if w else ""))

print("(2) pipelines identiques")
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    try:
        print("  wilcoxon(a, a) :", stats.wilcoxon(a, a).pvalue)
    except Exception as exc:
        print("  wilcoxon(a, a) :", type(exc).__name__, exc)
    print("  friedman(a, a, a) :", stats.friedmanchisquare(a, a, a).pvalue)
print("(3) friedman à 2 pipelines")
try:
    stats.friedmanchisquare(a, b)
except Exception as exc:
    print("  ", type(exc).__name__, exc)

print("(4) ex aequo mathématiques cassés par l'arrondi flottant")
from fractions import Fraction as F
# CER par document comme ratios exacts e/n, puis en flottants
ea, eb, n = [1, 2, 1, 3, 1], [2, 1, 2, 4, 3], [10, 10, 10, 10, 20]
fa = np.array([x / m for x, m in zip(ea, n)]); fb = np.array([x / m for x, m in zip(eb, n)])
df = fa - fb
dq = [F(x, m) - F(y, m) for x, y, m in zip(ea, eb, n)]
print("  |Δ| flottants :", [repr(abs(x)) for x in df])
print("  |Δ| exacts    :", [str(abs(x)) for x in dq])
print("  rangs flottants :", stats.rankdata(np.abs(df)), " rangs exacts :", stats.rankdata([abs(float(x)) for x in dq]))
# Signe : le seul Δ positif est le 2e. On le place sur la valeur « arrondie vers le haut ».
ea2, eb2 = [2, 3, 1, 4, 1], [1, 2, 2, 3, 3]   # Δ = +1/10, +1/10, -1/10, +1/10, -1/10
fa2 = np.array([x / m for x, m in zip(ea2, n)]); fb2 = np.array([x / m for x, m in zip(eb2, n)])
d_float = fa2 - fb2
d_exact = np.array([float(F(x, m) - F(y, m)) for x, y, m in zip(ea2, eb2, n)])
print("  Δ flottants :", [repr(x) for x in d_float]); print("  Δ exacts    :", [repr(x) for x in d_exact])
pf = stats.wilcoxon(d_float, method="approx").pvalue
pq = stats.wilcoxon(d_exact, method="approx").pvalue
print(f"  Wilcoxon (approx) sur Δ flottants p = {pf:.6f} ; sur Δ exacts p = {pq:.6f}")
assert pf != pq
