"""R4 : niveau de l'inversion percentile du bootstrap apparié (et de la permutation
studentisée) sur le scénario de la revue (F1 NER, R_A = R_B en population)."""
import numpy as np
rng = np.random.default_rng(12345)
def f1(tp, fp, fn):
    den = 2*tp + fp + fn
    return np.where(den > 0, 2*tp/np.where(den > 0, den, 1), np.nan)
def sim(n, B=2000, sims=1000):
    rej_boot = rej_stud = 0
    for _ in range(sims):
        A = np.tile([2, 4, 0], (n, 1))
        good = rng.random(n) < 1/3
        Bs = np.where(good[:, None], [2, 0, 0], [0, 0, 2])
        # bootstrap apparié
        idx = rng.integers(0, n, (B, n))
        sa = A[idx].sum(1); sb = Bs[idx].sum(1)
        d = f1(*sa.T) - f1(*sb.T)
        d = d[np.isfinite(d)]
        p = min(1.0, 2*min((d <= 0).mean(), (d >= 0).mean()))
        rej_boot += p < 0.05
        # permutation studentisée (linéarisation de F1 = 2tp/(2tp+fp+fn))
        def T(a, b):
            out = []
            for x in (a, b):
                S = x.sum(0); den = 2*S[0]+S[1]+S[2]; R = 2*S[0]/den
                u = (2*x[:, 0] - R*(2*x[:, 0]+x[:, 1]+x[:, 2])) / (den/len(x))
                out.append((R, u))
            (Ra, ua), (Rb, ub) = out
            diff = ua - ub
            se = np.sqrt(((diff - diff.mean())**2).sum())/len(diff)
            return (Ra - Rb)/se if se > 0 else 0.0
        t0 = T(A, Bs)
        cnt = 0; P = 500
        for _ in range(P):
            s = rng.random(n) < 0.5
            a2 = np.where(s[:, None], Bs, A); b2 = np.where(s[:, None], A, Bs)
            cnt += abs(T(a2, b2)) >= abs(t0) - 1e-12
        rej_stud += (cnt + 1)/(P + 1) < 0.05
    return rej_boot/sims, rej_stud/sims
for n in (30, 100):
    print(n, *sim(n, sims=300))
