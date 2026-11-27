"""Révision 3, N8 : ce que fait réellement `scipy.stats.wilcoxon(method="auto")`
dans la version tracée (lu dans scipy/stats/_wilcoxon.py, l. 128-242 en 1.18.1) :
  n > 50 -> asymptotique ; n <= 50 sans zéro ni ex æquo -> loi exacte ;
  zéros ou ex æquo et n <= 13 -> PermutationMethod() (énumération des 2^n) ;
  zéros ou ex æquo et 13 < n <= 50 -> asymptotique avec correction de continuité.
Contrat retenu : method=PermutationMethod explicite, énumération exacte si 2^n <= 2^16,
sinon 99 999 échanges tirés avec une graine déclarée ; vérifié ici : égal à l'énumération
écrite à la main sur les rangs moyens, et à `auto` dans le seul cas où auto énumère."""
import itertools
import numpy as np, scipy
from scipy import stats
from scipy.stats import rankdata
def manual(d):  # wilcox : zéros retirés, rangs moyens des |d|, énumération des signes
    d = d[d != 0]; r = rankdata(np.abs(d)); obs = r[d > 0].sum(); tot = r.sum()
    null = [sum(ri for ri, s in zip(r, sg) if s) for sg in itertools.product((0, 1), repeat=len(d))]
    null = np.array(null); c = tot / 2
    return np.mean(np.abs(null - c) >= abs(obs - c) - 1e-12)
explicite = lambda d, n_res: stats.wilcoxon(d, zero_method="wilcox",
    method=stats.PermutationMethod(n_resamples=n_res, rng=np.random.default_rng(0))).pvalue
d7 = np.array([0.1, 0.1, -0.1, 0.1, -0.1, 0.2, 0.3])
print("scipy", scipy.__version__)
print("n = 7, ex æquo : auto", round(stats.wilcoxon(d7).pvalue, 4), "| explicite exact", round(explicite(d7, np.inf), 4),
      "| manuel", round(manual(d7), 4), "| method='exact'", round(stats.wilcoxon(d7, method="exact").pvalue, 4))
assert abs(explicite(d7, np.inf) - manual(d7)) < 1e-12
d20 = np.round(np.random.default_rng(1).choice([-0.2, -0.1, 0.0, 0.1, 0.2, 0.3], 20), 1)
print("n = 20, ex æquo et zéros : auto (asymptotique)", round(stats.wilcoxon(d20).pvalue, 4),
      "| explicite exact", round(explicite(d20, np.inf), 4), "| manuel", round(manual(d20), 4))
assert abs(explicite(d20, np.inf) - manual(d20)) < 1e-12
print("répétable (graine déclarée, tirage) :", explicite(np.r_[d20, d20], 99_999) == explicite(np.r_[d20, d20], 99_999))
