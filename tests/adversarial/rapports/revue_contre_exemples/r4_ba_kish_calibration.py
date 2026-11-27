"""Révision 4, B9 / A3 / C2 — calibration INDÉPENDANTE du diagnostic de Kish.

Règle : BA (bootstrap apparié, p = 2·min(F̂*(0), 1 − F̂*(0⁻)) sur les réplicats)
publié ssi n_eff = min_{A,B} (Σ den)² / Σ den² ≥ 20, sinon « non estimable ».
Code écrit indépendamment de `c1_c2_levier_calibration.py` (graine, B, scénarios).

Scénarios (H0 : R_A = R_B = 0,5 en ratio d'espérances ; F1 = 2tp/(2tp+fp+fn)) :
  revue      : r_d = 2, B parfait 1/3 sinon muet (C1/C2) ;
  levier60   : r_0 = 60, autres 2 (C1/C2) ;
  lognormal  : r_d = ceil(exp(N(1; 1,2))) (C1/C2) ;
  MER        : (C1/C2) ;
  NOUVEAUX (non vus par l'auteur) :
  bimodal    : r_d = 40 avec proba 0,2, sinon 2 ;
  corrélé    : r_d ∈ {2, 20} (moitié-moitié), B bon avec proba 2/3 sur les petits,
               0,3 sur les grands (moyenne pondérée par r = 1/3 : H0 exacte),
               dénominateur et effet corrélés ;
  grappes    : grappes de 1 + Géom(0,25) documents (r = 2), q de B tiré par grappe
               (Bêta de moyenne 1/3, corrélation intra-grappe), unité = la grappe.
Mesures, 600 jeux par case : rejet sous H0 PARMI les jeux retenus (n_eff ≥ 20) contre
la borne α + 3 erreurs MC sur ce nombre de jeux ; rejet de BA SANS diagnostic ; part
des jeux non estimables.
"""
import numpy as np
rng = np.random.default_rng(20261127)
ALPHA = 0.05; SIMS = 600; BOOT = 1499; THR = 20

def ba_p(nA, dA, nB, dB):
    n = len(nA); idx = rng.integers(0, n, (BOOT, n))
    with np.errstate(invalid="ignore", divide="ignore"):
        d = nA[idx].sum(1) / dA[idx].sum(1) - nB[idx].sum(1) / dB[idx].sum(1)
    d = d[np.isfinite(d)]
    return min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))
kish = lambda den: den.sum() ** 2 / (den ** 2).sum()

def f1_docs(r, q):
    good = rng.random(len(r)) < q
    return 2.0 * r, 4.0 * r, np.where(good, 2.0 * r, 0.0), np.where(good, 2.0 * r, r)
def mer(n):
    good = rng.random(n) < 0.6
    return np.full(n, 5.0), np.full(n, 20.0), np.where(good, 0.0, 15.0), np.where(good, 20.0, 30.0)
def correle(n):
    big = rng.random(n) < 0.5; r = np.where(big, 20.0, 2.0)
    return f1_docs(r, np.where(big, 0.3, 2 / 3))
def grappes(n, qmean=1 / 3):
    out = [np.zeros(n) for _ in range(4)]
    for c in range(n):
        s = 1 + rng.geometric(0.25) - 1 + 0; s = max(1, s)
        q = rng.beta(2 * qmean / (1 - qmean) * 1.0, 2.0) if qmean != 1 / 3 else rng.beta(1.0, 2.0)
        nA, dA, nB, dB = f1_docs(np.full(s, 2.0), q)
        for k, v in enumerate((nA, dA, nB, dB)): out[k][c] = v.sum()
    return tuple(out)
SCEN = {"revue": lambda n: f1_docs(np.full(n, 2.0), 1 / 3),
        "levier60": lambda n: f1_docs(np.r_[60.0, np.full(n - 1, 2.0)], 1 / 3),
        "lognormal": lambda n: f1_docs(np.ceil(np.exp(rng.normal(1, 1.2, n))), 1 / 3),
        "MER": mer,
        "bimodal*": lambda n: f1_docs(np.where(rng.random(n) < 0.2, 40.0, 2.0), 1 / 3),
        "corrélé*": correle,
        "grappes*": grappes}
if __name__ == "__main__":
    NS = (10, 20, 25, 30, 40, 60, 100)
    over = []
    print(f"{'scénario':11s} {'n':>4s} {'retenus':>8s} {'BA|retenu':>10s} {'borne':>6s} {'BA sans diag':>13s} {'non estim.':>10s}")
    for name, g in SCEN.items():
        for n in NS:
            kept = []; allp = []
            for _ in range(SIMS):
                nA, dA, nB, dB = g(n)
                rej = ba_p(nA, dA, nB, dB) < ALPHA; allp.append(rej)
                if min(kish(dA), kish(dB)) >= THR: kept.append(rej)
            m = len(kept); bound = ALPHA + 3 * np.sqrt(ALPHA * (1 - ALPHA) / m) if m else np.nan
            rate = np.mean(kept) if m else np.nan
            flag = "  <-- HORS BORNE" if m >= 100 and rate > bound else ""
            if flag: over.append((name, n, round(rate, 3), m))
            print(f"{name:11s} {n:4d} {m:8d} {rate:10.3f} {bound:6.3f} {np.mean(allp):13.3f} {1 - m / SIMS:10.2f}{flag}")
    print("cases retenues (≥ 100 jeux) hors borne :", over)
    assert over, "aucune case hors borne"
