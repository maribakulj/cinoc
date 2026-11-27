"""Révision 2, P4 / § 6 B5 : « zero_method="wilcox", method="auto" (exact si n ≤ 50
sans zéro ni ex æquo, sinon approximation) » ; invariant de déterminisme (CLAUDE.md §12).

Sur scipy 1.18.1 (la version de la copie), `method="auto"` avec des ex æquo
(n ≤ 50) ne rend ni l'exact ni l'approximation normale annoncés par B5 : il
calcule une loi de permutation des rangs moyens. Les ex æquo exacts sont
justement ce que P4 préserve (rangs sur Fraction) : la description de B5 ne
correspond pas à la p publiée. (Vérifié : cette p reste déterministe.)
"""
import numpy as np, scipy
from scipy import stats
d7 = np.array([0.1, 0.1, -0.1, 0.1, -0.1, 0.2, 0.3])
p = {m: stats.wilcoxon(d7, method=m).pvalue for m in ("auto", "exact", "approx")}
print("scipy", scipy.__version__, "| n = 7 avec ex æquo :", {k: round(v, 4) for k, v in p.items()})
assert p["auto"] not in (p["exact"], p["approx"])
d30 = np.round(np.random.default_rng(0).choice([-0.2, -0.1, 0.1, 0.2, 0.3], 30), 1)
q = {m: stats.wilcoxon(d30, method=m).pvalue for m in ("auto", "approx")}
print("n = 30 avec ex æquo :", {k: round(v, 5) for k, v in q.items()}, "| répétable :", stats.wilcoxon(d30, method="auto").pvalue == q["auto"])
print("=> B5 : décrire le comportement réel de la version tracée, passer `method` explicite"
      " et écrire la méthode réellement appliquée en présence d'ex æquo.")
