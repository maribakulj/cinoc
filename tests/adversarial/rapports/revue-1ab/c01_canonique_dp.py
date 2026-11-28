"""C01 — S/D/I canoniques (P1) contre une DP lexicographique (min coût, max S).

Chaînes et listes de mots, alphabets petits (beaucoup d'ex æquo), longueurs 0..14,
plus le cas où le raccourci min(D_rf, I_rf) = 0 est pris. Vérifie aussi MER/cMER
(EditCounts) et la propriété I − D = |h| − |r|."""
import random, sys
from cinoc.evaluation._alignment import canonical_counts
from cinoc.evaluation.statistics import canonical_edit_counts, match_error_rate

def dp(r, h):
    n, m = len(r), len(h)
    INF = (10**9, 0)
    # (cost, -S) minimal lexicographiquement ; garde aussi D
    best = [[None]*(m+1) for _ in range(n+1)]
    best[0][0] = (0, 0, 0, 0)  # cost, negS, D, I
    for i in range(n+1):
        for j in range(m+1):
            if i == 0 and j == 0: continue
            cands = []
            if i and j:
                c, s, d, ii = best[i-1][j-1]
                sub = r[i-1] != h[j-1]
                cands.append((c+sub, s - sub, d, ii))
            if i:
                c, s, d, ii = best[i-1][j]; cands.append((c+1, s, d+1, ii))
            if j:
                c, s, d, ii = best[i][j-1]; cands.append((c+1, s, d, ii+1))
            best[i][j] = min(cands)
    c, s, d, ii = best[n][m]
    return (-s, d, ii)

rng = random.Random(20261128)
bad = 0; n_cases = 0
for trial in range(6000):
    alpha = rng.choice(["ab", "abc", "abcd"])
    r = "".join(rng.choice(alpha) for _ in range(rng.randint(0, 12)))
    h = "".join(rng.choice(alpha) for _ in range(rng.randint(0, 12)))
    for R, H in ((r, h), (list(r), list(h)), (r.split("a"), h.split("a"))):
        n_cases += 1
        got = canonical_counts(R, H)
        exp = dp(R, H)
        if got != exp:
            bad += 1
            if bad < 5: print("ECART", R, H, got, exp)
        s, d, i = got
        assert i - d == len(H) - len(R)
# unicode combinant / hors BMP
for R, H in (("é", "é"), ("𝔄b", "b𝔄"), ("ab", "ba")):
    print(repr(R), repr(H), canonical_counts(R, H), dp(R, H))
print(f"cas : {n_cases}, écarts : {bad}")
e = canonical_edit_counts("ab", "ba"); print("ab/ba", e, "MER", match_error_rate(e))
sys.exit(1 if bad else 0)
