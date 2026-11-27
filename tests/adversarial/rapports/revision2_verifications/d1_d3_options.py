"""Révision 5, D3 et D1.

(1) D3 : diagnostic de levier calculé sur la RÉFÉRENCE (r_d = tp+fn, ou n_réf),
    commune à la paire, sur l'exemple `r4_levier_echappatoire.py` : B pire par
    invention massive reste jugé.
(2) D1 : niveau sous H0 sur le scénario lognormal (n = 60, 100) et le scénario de la
    revue (n = 25), 2 000 jeux par case, parmi les jeux retenus par Kish(réf) ≥ 20 :
    (a) BA percentile (contrat) ; (b) bootstrap-t apparié (statistique studentisée par
    l'écart-type linéarisé, p et IC des mêmes réplicats) ; (c) BA + diagnostic de queue
    (kurtosis des tailles de référence ≤ 10) ; (b)+(c) les deux.
"""
import sys, numpy as np
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "revue_contre_exemples"))
rng = np.random.default_rng(55)
ALPHA = 0.05; BOOT = 1499
kish = lambda x: x.sum() ** 2 / (x ** 2).sum()

def ba_p(nA, dA, nB, dB, idx):
    d = nA[idx].sum(1) / dA[idx].sum(1) - nB[idx].sum(1) / dB[idx].sum(1)
    d = d[np.isfinite(d)]; return min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))
def lin(num, den):  # num, den : (..., n) -> R, u
    n = num.shape[-1]; R = num.sum(-1) / den.sum(-1)
    return R, (num - R[..., None] * den) / (den.sum(-1)[..., None] / n)
def boot_t_p(nA, dA, nB, dB, idx):
    n = len(nA)
    def stat(a, b, c, e):
        Ra, ua = lin(a, b); Rb, ub = lin(c, e); d = ua - ub
        se = np.sqrt(((d - d.mean(-1, keepdims=True)) ** 2).sum(-1)) / n
        return Ra - Rb, se
    D, se = stat(nA, dA, nB, dB)
    Ds, ses = stat(nA[idx], dA[idx], nB[idx], dB[idx])
    with np.errstate(invalid="ignore", divide="ignore"):
        T0 = D / se; Ts = (Ds - D) / ses
    Ts = Ts[np.isfinite(Ts)]
    return float(np.mean(np.abs(Ts) >= abs(T0))) if np.isfinite(T0) else 1.0
def kurt(x):
    z = (x - x.mean()) / x.std() if x.std() > 0 else np.zeros_like(x); return float((z ** 4).mean() - 3)
def f1_docs(r, q=1/3):
    good = rng.random(len(r)) < q
    return 2.0 * r, 4.0 * r, np.where(good, 2.0 * r, 0.0), np.where(good, 2.0 * r, r)

print("(1) D3 : 40 documents de 5 entités ; A (4±1, 1, 1), B (3±1, 2, 2)")
n = 40
tpA = 4.0 + rng.integers(-1, 2, n); tpB = 3.0 + rng.integers(-1, 2, n)
ref = np.full(n, 5.0)
for label, extra in (("B", 0.0), ("B + 2 000 fp sur un document", 2000.0)):
    fpB = np.full(n, 2.0); fpB[0] += extra
    nA, dA = 2 * tpA, 2 * tpA + 1 + 1; nB, dB = 2 * tpB, 2 * tpB + fpB + 2
    idx = rng.integers(0, n, (4999, n))
    print(f"   {label:30s} F1 B = {nB.sum()/dB.sum():.3f} | Kish(den) = {min(kish(dA), kish(dB)):5.1f} | "
          f"Kish(réf) = {kish(ref):5.1f} -> p BA = {ba_p(nA, dA, nB, dB, idx):.4f}")

print("(2) D1 : niveau sous H0 parmi les jeux retenus par Kish(réf) ≥ 20, 2 000 jeux par case")
SCEN = {"revue n=25": (25, lambda n: np.full(n, 2.0)),
        "lognormal n=60": (60, lambda n: np.ceil(np.exp(rng.normal(1, 1.2, n)))),
        "lognormal n=100": (100, lambda n: np.ceil(np.exp(rng.normal(1, 1.2, n))))}
for name, (n, mk) in SCEN.items():
    rows = []
    for _ in range(2000):
        r = mk(n)
        if kish(r) < 20: rows.append(None); continue
        nA, dA, nB, dB = f1_docs(r); idx = rng.integers(0, n, (BOOT, n))
        rows.append((ba_p(nA, dA, nB, dB, idx) < ALPHA, boot_t_p(nA, dA, nB, dB, idx) < ALPHA, kurt(r) <= 10))
    kept = [x for x in rows if x is not None]; m = len(kept); se = np.sqrt(ALPHA * (1 - ALPHA) / max(m, 1))
    ba = np.mean([x[0] for x in kept]); bt = np.mean([x[1] for x in kept])
    tail = [x for x in kept if x[2]]
    print(f"   {name:16s} retenus {m:4d} (err. MC {se:.4f}) | (a) BA {ba:.3f} | (b) bootstrap-t {bt:.3f} | "
          f"(c) BA + kurtosis ≤ 10 : {np.mean([x[0] for x in tail]) if tail else float('nan'):.3f} sur {len(tail)} | "
          f"(b)+(c) bootstrap-t + kurtosis ≤ 10 : {np.mean([x[1] for x in tail]) if tail else float('nan'):.3f}")
