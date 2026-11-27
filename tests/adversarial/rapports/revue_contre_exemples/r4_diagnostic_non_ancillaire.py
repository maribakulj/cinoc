"""Révision 4, B9 : le diagnostic de Kish porte sur les dénominateurs des DEUX
pipelines, donc sur des quantités qui dépendent des sorties (F1 : 2tp+fp+fn). Sous H0,
la sélection « n_eff ≥ 20 » dépend des résultats ; le niveau conditionnel peut être PIRE
que sans diagnostic. Scénario lognormal (celui de l'auteur), n = 60 et 100, 1 500 jeux.
On compare trois règles : Kish sur les dénominateurs (contrat), Kish sur la seule
RÉFÉRENCE (r_d = tp+fn, ancillaire sous H0), Kish sur les dénominateurs ≥ 30."""
import numpy as np
import r4_ba_kish_calibration as C
A = C.ALPHA
for n in (60, 100):
    res = {"sans diagnostic": [], "Kish(den) ≥ 20 (contrat)": [], "Kish(réf) ≥ 20": [], "Kish(den) ≥ 30": []}
    for _ in range(1500):
        r = np.ceil(np.exp(C.rng.normal(1, 1.2, n))); nA, dA, nB, dB = C.f1_docs(r, 1 / 3)
        rej = C.ba_p(nA, dA, nB, dB) < A; kd = min(C.kish(dA), C.kish(dB)); kr = C.kish(r)
        res["sans diagnostic"].append(rej)
        if kd >= 20: res["Kish(den) ≥ 20 (contrat)"].append(rej)
        if kr >= 20: res["Kish(réf) ≥ 20"].append(rej)
        if kd >= 30: res["Kish(den) ≥ 30"].append(rej)
    for k, v in res.items():
        m = len(v); b = A + 3 * np.sqrt(A * (1 - A) / m) if m else float("nan")
        print(f"n = {n:3d}  {k:26s} retenus {m:5d}  rejet {np.mean(v) if m else float('nan'):.3f}  borne {b:.3f}")
