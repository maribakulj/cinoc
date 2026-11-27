"""§2.1d / A3 : « p : permutation appariée (échange A/B par document) » pour le
Δ micro d'un ratio de sommes, quand les dénominateurs DIFFÈRENT entre pipelines
(F1 : 2tp+fp+fn = n_réf + n_préd dépend de l'hypothèse).

L'échange A/B par document teste l'échangeabilité (H0 forte : même loi de
(S_A,d , S_B,d)), pas H0 : R_A = R_B. Simulation réaliste : chaque document a
2 entités de référence (tp+fn = 2 des deux côtés).
  A : sur-prédit toujours  (tp=2, fp=4, fn=0)  F1 = 4/8 = 0,5
  B : 1/3 parfait (2,0,0), 2/3 muet (0,0,2)   F1 micro attendu = 4/12 / ... = 0,5
R_A = R_B = 0,5 en population. On mesure le taux de rejet à α = 0,05.
"""
import numpy as np
rng = np.random.default_rng(12345)

def f1(tp, fp, fn):
    return 2 * tp / (2 * tp + fp + fn)

def draw(n):
    A = np.tile([2, 4, 0], (n, 1))
    perfect = rng.random(n) < 1 / 3
    B = np.where(perfect[:, None], [2, 0, 0], [0, 0, 2])
    return A, B

def stat(A, B):
    return f1(*A.sum(0)) - f1(*B.sum(0))

def perm_p(A, B, R=999):
    obs = stat(A, B)
    n = len(A)
    swaps = rng.random((R, n)) < 0.5
    null = np.empty(R)
    for r in range(R):
        s = swaps[r][:, None]
        null[r] = stat(np.where(s, B, A), np.where(s, A, B))
    ge = (np.sum(null >= obs - 1e-12) + 1) / (R + 1)
    le = (np.sum(null <= obs + 1e-12) + 1) / (R + 1)
    return min(1.0, 2 * min(ge, le))

# Vérification de H0 en population (grand échantillon)
A, B = draw(200_000)
print("R_A =", f1(*A.sum(0)), " R_B ≈", round(f1(*B.sum(0)), 4))
for n in (10, 30, 100):
    sims = 600
    rej = sum(perm_p(*draw(n)) < 0.05 for _ in range(sims))
    print(f"n = {n:3d} docs : taux de rejet sous R_A = R_B : {rej / sims:.3f} (nominal 0,05)")
    last = rej / sims
print("=> la permutation appariée n'est pas un test de niveau α pour « Δ micro F1 = 0 » ;"
      " elle teste l'échangeabilité. À déclarer (H0 forte) ou remplacer (bootstrap"
      " studentisé / permutation studentisée).")

assert last > 0.15, "niveau non contrôlé"
