"""Révision 4, B9 : confirmation et puissance perdue.
(1) Cases hors borne de `r4_ba_kish_calibration.py` rejouées à 2 000 jeux.
(2) Niveau de BA parmi les jeux JUSTE au-dessus du seuil (20 ≤ n_eff < 25), scénarios
    lourds (lognormal, bimodal, corrélé, grappes) à n = 30, 40, 60 confondus.
(3) Puissance perdue : alternative B pire (q = 0,2, R_B = 1/3 contre R_A = 1/2) ; part des
    jeux où BA rejette à tort ou à raison… ici à raison, mais où « non estimable » est publié.
"""
import numpy as np
import r4_ba_kish_calibration as C
A = C.ALPHA
def run(gen, n, sims):
    kept, allr, ne = [], [], []
    for _ in range(sims):
        nA, dA, nB, dB = gen(n); k = min(C.kish(dA), C.kish(dB)); r = C.ba_p(nA, dA, nB, dB) < A
        allr.append(r); ne.append(k)
        if k >= C.THR: kept.append(r)
    return np.array(allr), np.array(ne), kept
print("(1) confirmation, 2 000 jeux")
for name, n in (("revue", 25), ("lognormal", 60)):
    allr, ne, kept = run(C.SCEN[name], n, 2000); m = len(kept)
    print(f"   {name} n = {n} : retenus {m}, BA|retenu = {np.mean(kept):.3f}, borne = {A + 3*np.sqrt(A*(1-A)/m):.3f}")
print("(2) jeux juste au-dessus du seuil, 20 ≤ n_eff < 25")
rej = []
for name in ("lognormal", "bimodal*", "corrélé*", "grappes*"):
    for n in (30, 40, 60):
        allr, ne, _ = run(C.SCEN[name], n, 500)
        sel = (ne >= 20) & (ne < 25); rej += list(allr[sel])
m = len(rej); print(f"   {m} jeux : BA rejette {np.mean(rej):.3f} (borne {A + 3*np.sqrt(A*(1-A)/m):.3f})")
print("(3) puissance perdue sous l'alternative (q_B = 0,2)")
alt = {"levier60": lambda n: C.f1_docs(np.r_[60.0, np.full(n - 1, 2.0)], 0.2),
       "bimodal*": lambda n: C.f1_docs(np.where(C.rng.random(n) < 0.2, 40.0, 2.0), 0.2),
       "corrélé*": lambda n: (lambda big: C.f1_docs(np.where(big, 20.0, 2.0), np.where(big, 0.15, 0.4)))(C.rng.random(n) < 0.5),
       "MER": lambda n: (np.full(n, 5.0), np.full(n, 20.0), *(lambda g: (np.where(g, 0.0, 15.0), np.where(g, 20.0, 30.0)))(C.rng.random(n) < 0.4))}
for name, n, h0 in (("levier60", 100, 0.057), ("bimodal*", 60, 0.070), ("corrélé*", 30, 0.053), ("MER", 20, 0.030)):
    allr, ne, kept = run(alt[name], n, 400)
    print(f"   {name:9s} n = {n:3d} (niveau sous H0 sans diagnostic {h0:.3f}) : puissance BA {allr.mean():.2f} ; "
          f"publiée {np.sum(allr & (ne >= C.THR)) / len(allr):.2f} ; non estimable {np.mean(ne < C.THR):.2f}")
