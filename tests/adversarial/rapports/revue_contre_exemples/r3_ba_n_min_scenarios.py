"""Révision 3, B9 : « n_min = le plus petit n à partir duquel BA tient α + 3 erreurs
Monte-Carlo sur TOUS les scénarios (F1 de la revue, Simpson, page à fort levier,
dénominateurs très inégaux) et pour tous les n supérieurs mesurés ».

On mesure BA (bootstrap apparié, p par inversion des mêmes réplicats) sur les
scénarios « levier » et « inégaux » de `r3_ps_niveau_scenarios.py` à n = 30, 50,
100. Si aucun n mesuré ne tient la borne, la définition de B9 n'a pas de
solution et le contrat ne dit pas ce qui est publié.
"""
import numpy as np
rng = np.random.default_rng(5)
ALPHA = 0.05; SIMS = 600
BOUND = ALPHA + 3 * np.sqrt(ALPHA * (1 - ALPHA) / SIMS)
def gen(r):
    n = len(r); good = rng.random(n) < 1 / 3
    return 2.0 * r, 4.0 * r, np.where(good, 2.0 * r, 0.0), np.where(good, 2.0 * r, r)
def ba_p(nA, dA, nB, dB, B=1999):
    n = len(nA); idx = rng.integers(0, n, (B, n))
    d = nA[idx].sum(1) / dA[idx].sum(1) - nB[idx].sum(1) / dB[idx].sum(1)
    return min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))
res = {}
for name, mk in {"levier (r0 = 60)": lambda n: np.r_[60.0, np.full(n - 1, 2.0)],
                 "inégaux (lognormal)": lambda n: np.ceil(np.exp(rng.normal(1, 1.2, n)))}.items():
    for n in (30, 50, 100):
        res[(name, n)] = sum(ba_p(*gen(mk(n))) < ALPHA for _ in range(SIMS)) / SIMS
        print(f"{name:22s} n = {n:3d} : BA rejette {res[(name, n)]:.3f} (borne {BOUND:.3f})")
assert any(v > BOUND for v in res.values())
