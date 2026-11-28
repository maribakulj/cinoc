"""C18 — S/D/I canoniques sur textes plus longs (150-400 car., alphabets 2-4,
mutations) contre la DP lexicographique (min coût puis max S)."""
import random
from cinoc.evaluation._alignment import canonical_counts
def dp(r, h):
    n, m = len(r), len(h)
    prev = [(j, 0, 0) for j in range(m + 1)]  # (cost, -S, D) ; I déduit
    for i in range(1, n + 1):
        cur = [(i, 0, i)]
        for j in range(1, m + 1):
            c1, s1, d1 = prev[j - 1]; sub = r[i-1] != h[j-1]
            a = (c1 + sub, s1 - sub, d1)
            c2, s2, d2 = prev[j]; b = (c2 + 1, s2, d2 + 1)
            c3, s3, d3 = cur[j - 1]; c = (c3 + 1, s3, d3)
            cur.append(min(a, b, c))
        prev = cur
    c, s, d = prev[m]
    return (-s, d, c - (-s) - d)
rng = random.Random(11); bad = 0
for t in range(120):
    al = rng.choice(["ab", "abc", "abcd"])
    r = "".join(rng.choice(al) for _ in range(rng.randint(150, 400)))
    h = list(r)
    for _ in range(rng.randint(1, 120)):
        op = rng.random(); p = rng.randrange(len(h) + 1)
        if op < .33 and h: h.pop(min(p, len(h) - 1))
        elif op < .66: h.insert(p, rng.choice(al))
        elif h: h[min(p, len(h)-1)] = rng.choice(al)
    h = "".join(h)
    if canonical_counts(r, h) != dp(r, h):
        bad += 1; print("ECART", len(r), len(h), canonical_counts(r, h), dp(r, h))
print("cas : 120, écarts :", bad)
