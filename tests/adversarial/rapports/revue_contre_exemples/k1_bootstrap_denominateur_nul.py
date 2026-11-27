"""K1 §2.1a « Le bootstrap travaille sur les statistiques empilées : on somme les
lignes tirées, puis on finalise » ; §2.1b « une page à référence vide contribue
au micro » ; A3 « IC par bootstrap apparié ... égaux à scipy ».

Contre-exemple : le support micro D^μ_AB contient des pages à n_réf = 0. Un
rééchantillon qui ne tire que celles-là a Σ n_réf = 0 : finalize = None. Le
contrat ne dit pas ce que devient ce réplicat ; scipy rend un IC NaN.
"""
import warnings
import numpy as np
from scipy import stats

# 3 documents : (erreurs_A, erreurs_B, n_ref). Deux pages blanches (hallucinations).
E_A = np.array([4.0, 3.0, 1.0]); E_B = np.array([0.0, 0.0, 2.0]); N = np.array([0.0, 0.0, 10.0])
idx = np.arange(3)

def delta(i, axis=-1):
    i = np.asarray(i, dtype=int)
    den = N[i].sum(axis=axis)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (E_A[i].sum(axis=axis) - E_B[i].sum(axis=axis)) / den

print("Δ micro observé =", delta(idx))
print("P(rééchantillon sans page non vide) = (2/3)^3 =", (2 / 3) ** 3)
for method in ("percentile", "BCa"):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        res = stats.bootstrap((idx,), delta, method=method, n_resamples=999,
                              rng=np.random.default_rng(0), vectorized=True)
    print(f"{method:10s} IC =", res.confidence_interval, "| avertissements :",
          sorted({type(x.message).__name__ for x in w}))
    ci = res.confidence_interval
    assert not (np.isfinite(ci.low) and np.isfinite(ci.high)), "IC non fini"

# Même phénomène sur la fixture T1 reformulée (12 docs dont 6 blancs) : probabilité
# qu'au moins un réplicat sur 9 999 n'ait que des pages blanches
p_one = 0.5 ** 12
print("T1 : P(au moins un réplicat dégénéré sur 9999) =", 1 - (1 - p_one) ** 9999)
