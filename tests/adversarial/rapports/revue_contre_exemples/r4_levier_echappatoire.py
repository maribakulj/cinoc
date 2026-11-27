"""Révision 4, B9 : n_eff = min sur la paire de (Σ den)²/Σ den², avec den calculé
sur la SORTIE de chaque pipeline (F1 : 2tp+fp+fn ; MER : n_réf + I).

Un pipeline peut donc échapper au verdict en étant PIRE : une page où il invente
massivement (fp ou insertions) écrase son propre n_eff, et la comparaison devient
« non estimable ». 40 documents de 5 entités ; A : (4, 1, 1) partout (F1 0,8) ;
B : (3, 2, 2) partout (F1 0,6), puis B invente en plus 2 000 entités sur un document.
"""
import numpy as np
rng = np.random.default_rng(1)
kish = lambda den: den.sum() ** 2 / (den ** 2).sum()
def ba(nA, dA, nB, dB, B=4999):
    idx = rng.integers(0, len(nA), (B, len(nA)))
    d = nA[idx].sum(1) / dA[idx].sum(1) - nB[idx].sum(1) / dB[idx].sum(1)
    return min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))
n = 40
tpA, fpA, fnA = np.full(n, 4.0) + rng.integers(-1, 2, n), np.full(n, 1.0), np.full(n, 1.0)
tpB, fpB, fnB = np.full(n, 3.0) + rng.integers(-1, 2, n), np.full(n, 2.0), np.full(n, 2.0)
for label, extra in (("B sans invention massive", 0.0), ("B + 2 000 fp sur un document", 2000.0)):
    fpB2 = fpB.copy(); fpB2[0] += extra
    nA, dA, nB, dB = 2 * tpA, 2 * tpA + fpA + fnA, 2 * tpB, 2 * tpB + fpB2 + fnB
    ne = min(kish(dA), kish(dB)); Rb = nB.sum() / dB.sum()
    verdict = f"p = {ba(nA, dA, nB, dB):.4f}" if ne >= 20 else "« non estimable (levier) »"
    print(f"{label:30s} F1 micro B = {Rb:.3f} (A = {nA.sum()/dA.sum():.3f}) | n_eff = {ne:5.1f} | {verdict}")
print("=> calculer le diagnostic sur des quantités de RÉFÉRENCE (tp+fn, n_réf), ancillaires et identiques"
      " pour la paire, ou publier l'invention massive comme verdict au lieu de « non estimable ».")
