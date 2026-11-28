"""Coût de l'alignement canonique (S, D, I) sur des textes longs et dégradés.

Déterministe (graine fixe). Compare canonical_counts à la seule distance
de Levenshtein de rapidfuzz, et vérifie S+D+I = d et I-D = |h|-|r|."""
import random, string, time, statistics
from rapidfuzz.distance import Levenshtein
from cinoc.evaluation._alignment import canonical_counts

ALPHA = string.ascii_letters + "àéèêôûçſ ,.;:'-" * 2

def degrade(ref, rate, rng):
    out = []
    for ch in ref:
        r = rng.random()
        if r < rate / 3:            # suppression
            continue
        if r < 2 * rate / 3:        # substitution
            out.append(rng.choice(ALPHA)); continue
        out.append(ch)
        if r < rate:                # insertion après
            out.append(rng.choice(ALPHA))
    return "".join(out)

def timeit(fn, *a, rep=3):
    ts = []
    for _ in range(rep):
        t = time.perf_counter(); res = fn(*a); ts.append(time.perf_counter() - t)
    return res, statistics.median(ts)

rng = random.Random(20261128)
print(f"{'n_réf':>7} {'taux':>5} {'CER':>6} {'d (s)':>9} {'canon (s)':>10} {'×':>7}  vérif")
for n in (2_000, 10_000, 30_000, 60_000):
    ref = "".join(rng.choice(ALPHA) for _ in range(n))
    for rate in (0.05, 0.30, 0.80):
        hyp = degrade(ref, rate, rng)
        d, td = timeit(Levenshtein.distance, ref, hyp)
        (s, dl, i), tc = timeit(canonical_counts, ref, hyp, rep=1)
        ok = (s + dl + i == d) and (i - dl == len(hyp) - len(ref))
        print(f"{n:>7} {rate:>5.2f} {d/n:>6.3f} {td:>9.4f} {tc:>10.4f} {tc/max(td,1e-9):>7.0f}  {'ok' if ok else 'ÉCHEC'}")
