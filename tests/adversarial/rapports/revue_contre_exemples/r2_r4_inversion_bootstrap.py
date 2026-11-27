"""Révision 2, R4 / A3 : « Sinon, la p est obtenue par inversion du bootstrap
apparié : p = min(1, 2·min(F̂*(0), 1 − F̂*(0⁻))) » ; A3 « taux de rejet ≤ α + 3
erreurs Monte-Carlo pour chaque famille » ; P2 (réplicats dégénérés écartés).

(1) Niveau sur le scénario de la revue (F1 NER, R_A = R_B = 0,5) à n = 5, 10, 30
    (5 = nombre de grappes BNL, B3 ; l'auteur n'a mesuré que n = 30 et 100).
(2) Famille « taux d'édition » : p par changement de signe et IC par bootstrap
    (table § 2.1 d) : taux de publications contradictoires (p < α avec 0 dans
    l'IC, ou l'inverse).
"""
import numpy as np
rng = np.random.default_rng(2026)
ALPHA = 0.05

def f1(S):  # S : (..., 3)
    den = 2 * S[..., 0] + S[..., 1] + S[..., 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, 2 * S[..., 0] / den, np.nan)

def inversion_p(A, B, n_boot=1999):
    n = len(A); idx = rng.integers(0, n, (n_boot, n))
    d = f1(A[idx].sum(1)) - f1(B[idx].sum(1))
    d = d[np.isfinite(d)]
    return min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))

print("(1) inversion du bootstrap, scénario F1 de la revue, 1000 simulations (erreur MC ≈ 0,007)")
res = {}
for n in (5, 10, 30):
    rej = 0
    for _ in range(1000):
        A = np.tile([2, 4, 0], (n, 1))
        good = rng.random(n) < 1 / 3
        B = np.where(good[:, None], [2, 0, 0], [0, 0, 2])
        rej += inversion_p(A, B) < ALPHA
    res[n] = rej / 1000
    print(f"   n = {n:3d} : taux de rejet {res[n]:.3f} (borne A3 : {ALPHA + 3*np.sqrt(ALPHA*(1-ALPHA)/1000):.3f})")

print("(2) taux d'édition : p (changement de signe exact) contre IC percentile (bootstrap apparié)")
def signflip_p(d):
    n = len(d); signs = 1 - 2 * ((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1)
    null = (signs * d).sum(1); obs = d.sum()
    return min(1.0, 2 * min(np.mean(null >= obs - 1e-12), np.mean(null <= obs + 1e-12)))
disc = 0; sims = 1000; n = 10; nref = 100.0
for _ in range(sims):
    EA = rng.poisson(5, n).astype(float); EB = EA + rng.choice([0, 0, 1, 3], n)   # B un peu pire
    d = EA - EB
    p = signflip_p(d)
    idx = rng.integers(0, n, (1999, n)); reps = d[idx].sum(1) / (nref * n)
    lo, hi = np.percentile(reps, [2.5, 97.5])
    disc += (p < ALPHA) != (not (lo <= 0 <= hi))
print(f"   n = {n} : publications où p et IC se contredisent : {disc / sims:.3f}")
assert res[5] > ALPHA + 3 * np.sqrt(ALPHA * (1 - ALPHA) / 1000) and disc > 0
