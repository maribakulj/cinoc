"""§2.4 étape 2 (objectif lexicographique, tri canonique « page, y0, x0, y1, x1,
puis texte », « départage les ex æquo résiduels ») et « Les mêmes paires
bijectives servent region_detection, region_cer, ... ». §6 n° 4 (justification
« IoU > 0,5 strict : unicité de l'appariement plan, Kirillov et al. 2019 »).

Implémentation littérale de l'objectif, oracle par énumération exhaustive.
"""
import itertools
import numpy as np
from scipy.optimize import linear_sum_assignment
from rapidfuzz.distance import Levenshtein as L

def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy; union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union

def key(reg):  # (y0, x0, y1, x1, texte)
    (x0, y0, x1, y1), t = reg; return (y0, x0, y1, x1, t)

def match(R, H, theta=0.5):
    R = sorted(R, key=key); H = sorted(H, key=key); n = min(len(R), len(H))
    W = np.zeros((len(R), len(H)))
    for i, (rb, _) in enumerate(R):
        for j, (hb, _) in enumerate(H):
            v = iou(rb, hb)
            if v > theta: W[i, j] = (n + 1) + v
    ri, hj = linear_sum_assignment(W, maximize=True)
    return R, H, [(i, j) for i, j in zip(ri, hj) if W[i, j] > 0]

def region_cer(R, H, pairs):
    e = sum(L.distance(R[i][1], H[j][1]) for i, j in pairs)
    e += sum(len(t) for i, (_, t) in enumerate(R) if i not in {p[0] for p in pairs})
    e += sum(len(t) for j, (_, t) in enumerate(H) if j not in {p[1] for p in pairs})
    return e / sum(len(t) for _, t in R)

print("1) Ex æquo géométrique départagé par l'ordre ALPHABÉTIQUE du texte hypothèse")
B = (0, 0, 100, 20)
R = [(B, "Zurich")]
H = [(B, "Aaaaaa"), (B, "Zurich")]       # boîte dupliquée (VLM qui répète une région)
Rs, Hs, pairs = match(R, H)
print("   paire retenue :", [(Rs[i][1], Hs[j][1]) for i, j in pairs], " region_cer =", round(region_cer(Rs, Hs, pairs), 3))
alt = [(0, 1)]
print("   paire alternative de même objectif :", [(Rs[0][1], Hs[1][1])], " region_cer =", round(region_cer(Rs, Hs, alt), 3))
assert region_cer(Rs, Hs, pairs) != region_cer(Rs, Hs, alt)
H2 = [(B, "Zzzzzz"), (B, "Zurich")]
Rs2, Hs2, p2 = match(R, H2)
print("   en remplaçant le texte fautif par « Zzzzzz » (trié APRÈS « Zurich ») :",
      [(Rs2[i][1], Hs2[j][1]) for i, j in p2])

print("2) VT emboîtée : plusieurs hypothèses à IoU > 0,5 avec une même région (Kirillov ne s'applique pas)")
r1, r2 = (0, 0, 100, 100), (0, 0, 100, 60)      # r2 imbriquée dans r1 (PAGE autorise l'imbrication)
h1, h2 = (0, 0, 100, 95), (0, 40, 100, 100)
for a, an in ((r1, "r1"), (r2, "r2")):
    print("   ", an, {hn: round(iou(a, b), 3) for b, hn in ((h1, "h1"), (h2, "h2"))})
R = [(r1, "AAAA BBBB"), (r2, "AAAA")]; H = [(h1, "AAAA BBBB"), (h2, "BBBB")]
Rs, Hs, pairs = match(R, H)
print("   bijection lexicographique :", [(Rs[i][1], Hs[j][1]) for i, j in pairs])
# oracle : énumération
best = None
for perm in itertools.permutations(range(2)):
    ps = [(i, perm[i]) for i in range(2) if iou(Rs[i][0], Hs[perm[i]][0]) > 0.5]
    score = (len(ps), sum(iou(Rs[i][0], Hs[j][0]) for i, j in ps))
    best = max(best or (score, ps), (score, ps))
print("   oracle exhaustif :", best[0], [(Rs[i][1], Hs[j][1]) for i, j in best[1]])
print("   region_cer =", round(region_cer(Rs, Hs, pairs), 3), "alors que h1 ≡ r1 au texte près ; tp = 2 (F1 = 1)")
# Fusion « détectée » : h1 couvre r1 et r2 à IoGT ≥ 0,5
iogt = lambda r, h: (max(0, min(r[2], h[2]) - max(r[0], h[0])) * max(0, min(r[3], h[3]) - max(r[1], h[1]))) / ((r[2]-r[0])*(r[3]-r[1]))
print("   IoGT(r1,h1) =", round(iogt(r1, h1), 3), " IoGT(r2,h1) =", round(iogt(r2, h1), 3),
      "=> h1 publié comme FUSION de r1 et r2, alors que r2 ⊂ r1 dans la VT")
