"""Témoin de k1_permutation_ratio_niveau.py : famille « taux d'édition ».
Même document ⇒ même n_réf pour A et B ⇒ Δ micro = Σ(E_A − E_B)/Σn, linéaire :
l'échange de signe est asymptotiquement de niveau α même pour des lois
différentes (A constant, B asymétrique, même moyenne)."""
import numpy as np
rng = np.random.default_rng(7)
def perm_p(d, R=999):
    obs = d.sum(); flips = rng.choice([-1, 1], size=(R, len(d)))
    null = (flips * d).sum(1)
    ge = (np.sum(null >= obs - 1e-12) + 1) / (R + 1); le = (np.sum(null <= obs + 1e-12) + 1) / (R + 1)
    return min(1.0, 2 * min(ge, le))
for n in (10, 30, 100):
    rej = 0
    for _ in range(1000):
        EA = np.full(n, 3.0); EB = np.where(rng.random(n) < 1 / 3, 9.0, 0.0)
        rej += perm_p(EA - EB) < 0.05
    print(f"CER, n = {n:3d} : taux de rejet {rej / 1000:.3f} (nominal 0,05)")
