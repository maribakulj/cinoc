"""Révision 4, C1-C2 / B9 : diagnostic de levier déclaré et calibration.

Diagnostic : taille effective de Kish n_eff = (Σ_d den_d)² / Σ_d den_d², calculée
pour CHAQUE pipeline de la paire sur ses dénominateurs, et n_eff(A, B) = le minimum
des deux. (n_eff = n quand les dénominateurs sont égaux ; n_eff ≈ 1/part maximale
quand une unité domine.) Règle candidate : p (et IC) publiés seulement si
n_eff ≥ seuil, sinon « non estimable (levier) », à tout n.

Mesure, sous H0 R_A = R_B, sur les scénarios de la revue (`r3_ps_niveau_scenarios.py`)
plus un levier modéré : taux de rejet de PS et de BA PARMI les jeux qui passent le
seuil, pour plusieurs seuils ; borne α + 3 erreurs MC calculée sur le nombre de
jeux retenus dans la case ; cases avec moins de 100 jeux retenus ignorées.
"""
import numpy as np
rng = np.random.default_rng(404)
ALPHA = 0.05; SIMS = 600; NS = (6, 8, 10, 15, 20, 30, 50, 100); THRESH = (8, 10, 12, 15, 20, 25, 30)

def T(numA, denA, numB, denB):
    n = numA.shape[1]; out = []
    for num, den in ((numA, denA), (numB, denB)):
        R = num.sum(1) / den.sum(1); u = (num - R[:, None] * den) / (den.sum(1)[:, None] / n); out.append((R, u))
    (Ra, ua), (Rb, ub) = out; d = ua - ub
    se = np.sqrt(((d - d.mean(1, keepdims=True)) ** 2).sum(1)) / n
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(se > 0, (Ra - Rb) / se, 0.0)
def ps_p(nA, dA, nB, dB):
    n = len(nA)
    if 2 ** n <= 1024: M = (1 - 2 * ((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1)) < 0; ex = True
    else: M = rng.random((1999, n)) < 0.5; ex = False
    t0 = abs(T(nA[None], dA[None], nB[None], dB[None])[0])
    t = np.abs(T(np.where(M, nB, nA), np.where(M, dB, dA), np.where(M, nA, nB), np.where(M, dA, dB)))
    k = np.sum(t >= t0 - 1e-12); return k / len(M) if ex else (k + 1) / (len(M) + 1)
def ba_p(nA, dA, nB, dB, B=1999):
    n = len(nA); idx = rng.integers(0, n, (B, n))
    with np.errstate(invalid="ignore", divide="ignore"):
        d = nA[idx].sum(1) / dA[idx].sum(1) - nB[idx].sum(1) / dB[idx].sum(1)
    d = d[np.isfinite(d)]; return min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))
def kish(den): return den.sum() ** 2 / (den ** 2).sum()
def f1(r):
    good = rng.random(len(r)) < 1 / 3
    return 2.0 * r, 4.0 * r, np.where(good, 2.0 * r, 0.0), np.where(good, 2.0 * r, r)
def mer(n):
    good = rng.random(n) < 0.6
    return np.full(n, 5.0), np.full(n, 20.0), np.where(good, 0.0, 15.0), np.where(good, 20.0, 30.0)
SCEN = {"F1": lambda n: f1(np.full(n, 2.0)),
        "levier r0=60": lambda n: f1(np.r_[60.0, np.full(n - 1, 2.0)]),
        "levier r0=10": lambda n: f1(np.r_[10.0, np.full(n - 1, 2.0)]),
        "lognormal": lambda n: f1(np.ceil(np.exp(rng.normal(1, 1.2, n)))),
        "MER": mer}
rows = []
for name, g in SCEN.items():
    for n in NS:
        for _ in range(SIMS):
            nA, dA, nB, dB = g(n)
            rows.append((name, n, min(kish(dA), kish(dB)), ps_p(nA, dA, nB, dB) <= ALPHA, ba_p(nA, dA, nB, dB) < ALPHA))
rows = np.array(rows, dtype=object)
def check(proc_col, lo, hi=np.inf):
    """Cases (scénario, n) où le taux de rejet parmi les jeux de n_eff ∈ [lo, hi) dépasse la borne."""
    bad, worst = [], 0.0
    for name in SCEN:
        for n in NS:
            sel = [(r[proc_col]) for r in rows if r[0] == name and r[1] == n and lo <= r[2] < hi]
            if len(sel) < 100: continue
            rate = float(np.mean(sel)); bound = ALPHA + 3 * np.sqrt(ALPHA * (1 - ALPHA) / len(sel))
            worst = max(worst, rate - bound)
            if rate > bound: bad.append((name, n, round(rate, 3), len(sel)))
    return bad, worst
print("n_eff médian par scénario et n :")
for name in SCEN:
    print("  ", name.ljust(14), {n: round(float(np.median([r[2] for r in rows if r[0] == name and r[1] == n])), 1) for n in NS})
print("Sans diagnostic : PS hors borne :", check(3, 0)[0]); print("                 BA hors borne :", check(4, 0)[0])
for t in THRESH:
    bps, _ = check(3, t); bba, _ = check(4, t)
    print(f"seuil n_eff >= {t:2d} : PS hors borne {bps} | BA hors borne {bba}")
print("PS seule entre 8 et 30, BA au-delà de 30 :", check(3, 8, 30)[0], check(4, 30)[0])
print("Détail au seuil retenu n_eff >= 20 (cases avec au moins 100 jeux retenus) : scénario, n, jeux retenus, rejet PS, rejet BA, borne")
for name in SCEN:
    for n in NS:
        sel = [r for r in rows if r[0] == name and r[1] == n and r[2] >= 20]
        if len(sel) < 100: continue
        m = len(sel); bound = ALPHA + 3 * np.sqrt(ALPHA * (1 - ALPHA) / m)
        print(f"   {name:14s} n={n:3d} retenus={m:3d}  PS={np.mean([r[3] for r in sel]):.3f}  BA={np.mean([r[4] for r in sel]):.3f}  borne={bound:.3f}")
print("Part des jeux déclarés « non estimable (levier) » au seuil 20, par scénario et n :")
for name in SCEN:
    print("  ", name.ljust(14), {n: round(float(np.mean([r[2] < 20 for r in rows if r[0] == name and r[1] == n])), 2) for n in NS})
