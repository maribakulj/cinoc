"""Révision 3, N1 et N2 : une seule procédure par Δ micro, p et IC cohérents,
et niveau aux petits n.

(a) Famille à dénominateur de référence (taux d'édition) : test exact de
    changement de signe sur r_d(δ) = e_d − δ·n_d ; p = p(0) ; IC = {δ : p(δ) > α}
    obtenu par inversion du même test. Vérifie : niveau ≤ α à n = 5 et 10 sous H0
    (échangeabilité), IC d'un seul tenant, et p(0) ≤ α ⇔ 0 ∉ IC (cohérence).
(b) Familles à dénominateur d'hypothèse (scénario F1 de la revue, R_A = R_B) :
    p et IC percentile tirés des mêmes réplicats du bootstrap apparié. Vérifie la
    cohérence et mesure le niveau pour n = 5 … 50 (choix de n_min).
(c) Pour information : permutation studentisée sur le même scénario à n = 5, 10.
"""
import numpy as np
rng = np.random.default_rng(31)
ALPHA = 0.05

# ---------- (a) changement de signe exact, inversion ----------
def signs(n):
    return 1 - 2 * ((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1)

def p_signflip(r, S):
    null = S @ r; obs = r.sum()
    return min(1.0, 2 * min(np.mean(null >= obs - 1e-9), np.mean(null <= obs + 1e-9)))

def ci_inversion(e, nref, S, grid):
    ok = np.array([p_signflip(e - d * nref, S) > ALPHA for d in grid])
    return ok

viol_interval = incoh = 0; rej = {5: 0, 10: 0}; sims = 400
for n in (5, 10):
    S = signs(n)
    for _ in range(sims):
        nref = rng.integers(20, 200, n).astype(float)
        base = rng.poisson(nref * 0.05)
        EA, EB = base + rng.poisson(2, n), base + rng.poisson(2, n)   # H0 : A et B échangeables
        e = (EA - EB).astype(float)
        p0 = p_signflip(e, S)
        rej[n] += p0 <= ALPHA
        R = e.sum() / nref.sum()
        grid = np.union1d(np.linspace(R - 0.2, R + 0.2, 401), [0.0])
        ok = ci_inversion(e, nref, S, grid)
        idx = np.flatnonzero(ok)
        if idx.size and (idx[-1] - idx[0] + 1) != idx.size:
            viol_interval += 1
        zero_in = bool(idx.size) and grid[idx[0]] <= 0 <= grid[idx[-1]]   # IC = [premier, dernier] δ acceptés
        incoh += (p0 <= ALPHA) == bool(zero_in)
print("(a) changement de signe exact + IC par inversion")
for n in (5, 10):
    print(f"   n = {n:2d} : taux de rejet sous H0 = {rej[n]/sims:.3f} (p minimale possible 2^(1-n) = {2**(1-n):.4f})")
print(f"   IC non d'un seul tenant : {viol_interval} ; incohérences p/IC : {incoh}")

# ---------- (b) bootstrap apparié, p et IC des mêmes réplicats ----------
def f1(S3):
    den = 2 * S3[..., 0] + S3[..., 1] + S3[..., 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, 2 * S3[..., 0] / den, np.nan)

def boot(A, B, n_boot=1999):
    n = len(A); idx = rng.integers(0, n, (n_boot, n))
    d = f1(A[idx].sum(1)) - f1(B[idx].sum(1)); d = np.sort(d[np.isfinite(d)])
    p = min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))
    lo, hi = np.quantile(d, [ALPHA / 2, 1 - ALPHA / 2], method="inverted_cdf")
    return p, lo, hi

print("(b) bootstrap apparié, scénario F1 (R_A = R_B), 1000 simulations ; borne α + 3 err. MC = 0,071")
incoh_b = 0
for n in (5, 10, 15, 20, 30, 50):
    r = 0
    for _ in range(1000):
        A = np.tile([2, 4, 0], (n, 1)); good = rng.random(n) < 1 / 3
        B = np.where(good[:, None], [2, 0, 0], [0, 0, 2])
        p, lo, hi = boot(A, B)
        r += p < ALPHA
        incoh_b += (p < ALPHA) == (lo <= 0 <= hi)
    print(f"   n = {n:2d} : taux de rejet {r/1000:.3f}")
print(f"   incohérences p/IC (même réplicats, quantile inverted_cdf) : {incoh_b}")

# ---------- (c) permutation studentisée (vectorisée) ----------
def Tvec(a, b):  # a, b : (P, n, 3)
    res = []
    for x in (a, b):
        s3 = x.sum(1); den = 2 * s3[:, 0] + s3[:, 1] + s3[:, 2]; R = 2 * s3[:, 0] / den
        n = x.shape[1]
        u = (2 * x[..., 0] - R[:, None] * (2 * x[..., 0] + x[..., 1] + x[..., 2])) / (den[:, None] / n)
        res.append((R, u))
    (Ra, ua), (Rb, ub) = res; d = ua - ub
    se = np.sqrt(((d - d.mean(1, keepdims=True)) ** 2).sum(1)) / d.shape[1]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(se > 0, (Ra - Rb) / se, 0.0)
print("(c) permutation studentisée (exacte si 2^n <= 1024, sinon 1999 échanges tirés), 1000 simulations")
for n in (5, 10, 15, 20, 30):
    M = (signs(n) < 0) if n <= 10 else (rng.random((1999, n)) < 0.5)
    r = 0
    for _ in range(1000):
        A = np.tile([2, 4, 0], (n, 1)); good = rng.random(n) < 1 / 3
        B = np.where(good[:, None], [2, 0, 0], [0, 0, 2])
        t0 = abs(Tvec(A[None], B[None])[0])
        a = np.where(M[..., None], B[None], A[None]); b = np.where(M[..., None], A[None], B[None])
        t = np.abs(Tvec(a, b))
        p = (np.sum(t >= t0 - 1e-12) + (0 if n <= 10 else 1)) / (len(M) + (0 if n <= 10 else 1))
        r += p <= ALPHA
    print(f"   n = {n:2d} : taux de rejet {r/1000:.3f}")
