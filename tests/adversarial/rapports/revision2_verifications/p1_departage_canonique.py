"""P1 : comptes (S, D, I) canoniques = alignement optimal qui maximise S.
Deux appels rapidfuzz (distance simple d, distance pondérée W avec (K, K, K-1),
K = |r|+|h|+1) donnent S = K*d - W, puis D et I par S+D+I = d et I-D = |h|-|r|.
Comparé à une programmation dynamique lexicographique (d, -S) écrite à la main."""
import random
from rapidfuzz.distance import Levenshtein as L
def canon(r, h):
    d = L.distance(r, h); K = len(r) + len(h) + 1
    W = L.distance(r, h, weights=(K, K, K - 1))
    S = K * d - W; D = (d - S - (len(h) - len(r))) // 2
    return S, D, d - S - D
def brute(r, h):
    n, m = len(r), len(h); dp = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(m + 1):
            if i == j == 0: dp[i][j] = (0, 0, 0, 0); continue
            c = []
            if i: a = dp[i-1][j]; c.append((a[0]+1, a[1], a[2]+1, a[3]))
            if j: a = dp[i][j-1]; c.append((a[0]+1, a[1], a[2], a[3]+1))
            if i and j:
                a = dp[i-1][j-1]; s = r[i-1] != h[j-1]; c.append((a[0]+s, a[1]-s, a[2], a[3]))
            dp[i][j] = min(c)
    _, ms, D, I = dp[n][m]; return -ms, D, I
assert canon("ab", "ba") == brute("ab", "ba") == (2, 0, 0)
random.seed(0)
for _ in range(3000):
    r = "".join(random.choice("abc") for _ in range(random.randint(0, 7)))
    h = "".join(random.choice("abc") for _ in range(random.randint(0, 7)))
    assert canon(r, h) == brute(r, h), (r, h)
print("ok : 3000 cas, comptes canoniques = DP lexicographique")
