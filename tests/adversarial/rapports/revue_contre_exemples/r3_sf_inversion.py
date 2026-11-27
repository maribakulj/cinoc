"""Révision 3, N2 / A3 : SF = changement de signe exact sur r_d(δ) = e_d − δ·n_d ;
p = p(0) ; IC = {δ : p(δ) > α} ; « si n ≤ 5, aucun rejet possible ; IC non borné ».

(1) Monotonie : pour une partie J de documents « échangés », T_J(δ) ≥ T_∅(δ)
    ⇔ Σ_J e_d ≤ δ·Σ_J n_d. Chaque indicatrice est monotone en δ, donc p_haut(δ)
    croît, p_bas(δ) décroît, et {p > α} est un intervalle. Vérifié sur une grille.
(2) Seuil « n ≤ 5 » : une page à référence vide (n_d = 0, au support micro par
    § 2.1 b) a r_d(δ) = e_d, indépendant de δ. Quand δ → ±∞, seules les parties J
    faites de pages vides restent extrêmes : p(±∞) = 2·2^(k−n) pour k pages vides.
    Avec n = 8 et k = 3, p(±∞) = 0,0625 > α : IC NON BORNÉ, alors que n > 5 ; et
    p(0) peut être < α. Le seuil doit porter sur n_eff = #{d : n_d > 0}.
(3) Couverture sous effets hétérogènes (Simpson : A pire sur 9 petites pages,
    meilleur sur une grande) du Δ micro vrai Σ E[e_d] / Σ n_d.
"""
import numpy as np
rng = np.random.default_rng(9); ALPHA = 0.05
def S(n): return 1 - 2 * ((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1)
def p_of(e, nref, d, Sg):
    r = e - d * nref; null = Sg @ r; obs = r.sum()
    return min(1.0, 2 * min(np.mean(null >= obs - 1e-9), np.mean(null <= obs + 1e-9)))

# (1) monotonie de p_haut / p_bas et IC d'un seul tenant, 300 jeux aléatoires à n = 8
Sg = S(8); bad = 0
for _ in range(300):
    nref = rng.integers(0, 300, 8).astype(float); e = rng.integers(-15, 16, 8).astype(float)
    grid = np.linspace(-1, 1, 801); acc = np.array([p_of(e, nref, d, Sg) > ALPHA for d in grid])
    i = np.flatnonzero(acc); bad += bool(i.size) and (i[-1] - i[0] + 1 != i.size)
print("(1) IC non d'un seul tenant sur 300 jeux :", bad)

# (2) n = 8 dont 3 pages vides (insertions inventées par A sur deux d'entre elles)
nref = np.array([0, 0, 0, 100, 100, 100, 100, 100.0])
e = np.array([4, 6, -1, 9, 7, 8, 10, 6.0])                       # A pire partout
print("(2) p(0) =", p_of(e, nref, 0.0, Sg), "| p(δ = 10) =", p_of(e, nref, 10.0, Sg),
      "| p(δ = 1e6) =", p_of(e, nref, 1e6, Sg), "| 2·2^(k−n) =", 2 * 2 ** (3 - 8))
assert p_of(e, nref, 0.0, Sg) < ALPHA and p_of(e, nref, 1e6, Sg) > ALPHA
print("    -> IC = [borne, +∞) avec n = 8 > 5 ; la règle « n ≤ 5 » ne le signale pas")

# (3) couverture, Simpson hétérogène, n = 10
n = 10; Sg = S(n); nref = np.r_[np.full(9, 20.0), 2000.0]
rateA = np.r_[np.full(9, 0.15), 0.02]; rateB = np.r_[np.full(9, 0.05), 0.03]
true = ((rateA - rateB) * nref).sum() / nref.sum(); cover = 0; sims = 1000
for _ in range(sims):
    e = (rng.poisson(rateA * nref) - rng.poisson(rateB * nref)).astype(float)
    cover += p_of(e, nref, true, Sg) > ALPHA
print(f"(3) Δ micro vrai = {true:+.4f} ; couverture de l'IC SF = {cover / sims:.3f} (nominal 0,95)")
