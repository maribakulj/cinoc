"""Révision 3, N1 / A3 / B9 : procédure PS (permutation studentisée, « exacte si
2^n ≤ 1024 », statistique Δ/se linéarisé, sans IC) pour les familles à dénominateur
d'hypothèse quand n < n_min = 30. A3 : « pour chaque procédure et chaque n du jeu
de calibration, taux de rejet ≤ α + 3 erreurs Monte-Carlo ». B9 : jeu = scénario
F1 de la revue, Simpson, page à fort levier, dénominateurs très inégaux.

PS est implémentée comme dans `n1_n2_procedure_unique.py` (c) (linéarisation
u_d = (num_d − R·den_d)/(Σden/n) d'un ratio de sommes), et mesurée sous H0
R_A = R_B (même ratio d'espérances) sur des scénarios où l'auteur ne l'a pas
mesurée. Chaque document a r_d entités de référence (tp + fn = r_d des deux côtés).
  F1      : scénario de la revue (r_d = 2), A sur-prédit, B parfait 1/3, muet 2/3 ;
  levier  : même chose, mais le document 0 a r = 60 et les autres r = 2 ;
  inégaux : r_d = ceil(exp(N(1, 1,2))) (queue lourde) ;
  MER     : n_réf = 20 ; A : 5 substitutions ; B : 1/3 parfait, 2/3 10 insertions + 5 suppressions
            (MER_A = 5/20 = 0,25 ; E num_B / E den_B = (2/3·15)/(20 + 2/3·10) = 10/26.7 : on règle
            p pour égaliser, voir code).
"""
import numpy as np
rng = np.random.default_rng(77)
ALPHA = 0.05; SIMS = 1000
BOUND = ALPHA + 3 * np.sqrt(ALPHA * (1 - ALPHA) / SIMS)

def masks(n):
    if 2 ** n <= 1024:
        return (1 - 2 * ((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1)) < 0, True
    return rng.random((1999, n)) < 0.5, False

def T(numA, denA, numB, denB):
    """numX, denX : (P, n). Statistique studentisée du Δ de ratios de sommes."""
    n = numA.shape[1]; out = []
    for num, den in ((numA, denA), (numB, denB)):
        R = num.sum(1) / den.sum(1)
        u = (num - R[:, None] * den) / (den.sum(1)[:, None] / n)
        out.append((R, u))
    (Ra, ua), (Rb, ub) = out; d = ua - ub
    se = np.sqrt(((d - d.mean(1, keepdims=True)) ** 2).sum(1)) / n
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(se > 0, (Ra - Rb) / se, 0.0)

def ps_p(numA, denA, numB, denB):
    n = len(numA); M, exact = masks(n)
    t0 = abs(T(numA[None], denA[None], numB[None], denB[None])[0])
    nA = np.where(M, numB, numA); dA = np.where(M, denB, denA)
    nB = np.where(M, numA, numB); dB = np.where(M, denA, denB)
    t = np.abs(T(nA, dA, nB, dB))
    k = np.sum(t >= t0 - 1e-12)
    return k / len(M) if exact else (k + 1) / (len(M) + 1)

def f1_scenario(r):
    """A : (tp=r, fp=2r, fn=0) -> F1 0,5 ; B : 1/3 (r,0,0), 2/3 (0,0,r) -> 0,5 en espérance."""
    n = len(r); good = rng.random(n) < 1 / 3
    numA = 2.0 * r; denA = 4.0 * r
    numB = np.where(good, 2.0 * r, 0.0); denB = np.where(good, 2.0 * r, 1.0 * r)
    return numA, denA, numB, denB

def mer_scenario(n):
    # A : 5 S sur 20 -> num 5, den 20 (MER 0,25). B : parfait (0, 20) avec proba q, sinon (15, 30).
    # E num / E den = 15(1-q) / (20 + 10(1-q)) = 0,25  ->  q = 1 - 20/50 = 0,6 ... vérifié ci-dessous
    q = 0.6; good = rng.random(n) < q
    return np.full(n, 5.0), np.full(n, 20.0), np.where(good, 0.0, 15.0), np.where(good, 20.0, 30.0)
assert abs(15 * 0.4 / (20 + 10 * 0.4) - 0.25) < 1e-12

scen = {
    "F1 (revue)": lambda n: f1_scenario(np.full(n, 2.0)),
    "levier (r0 = 60)": lambda n: f1_scenario(np.r_[60.0, np.full(n - 1, 2.0)]),
    "inégaux (lognormal)": lambda n: f1_scenario(np.ceil(np.exp(rng.normal(1, 1.2, n)))),
    "MER": mer_scenario,
}
worst = {}
print(f"borne A3 = {BOUND:.3f} ; {SIMS} simulations par case")
print("scénario".ljust(22) + "".join(f"n={n:<6d}" for n in (5, 6, 8, 10, 15, 20, 25)))
for name, gen in scen.items():
    row = []
    for n in (5, 6, 8, 10, 15, 20, 25):
        rej = sum(ps_p(*gen(n)) <= ALPHA for _ in range(SIMS)) / SIMS
        row.append(rej); worst[(name, n)] = rej
    print(name.ljust(22) + "".join(f"{x:<8.3f}" for x in row))
bad = {k: v for k, v in worst.items() if v > BOUND}
print("cases au-delà de la borne :", bad)
assert bad, "PS tient partout"
