"""Révision 2, P16/P17 (§ 2.4 a 2) : « un poids ENTIER unique, où chaque critère est
multiplié par une borne strictement supérieure au maximum de tous les suivants :
[adm] ; IoU ramenée au DÉNOMINATEUR COMMUN DES UNIONS ; −Σ distance d'édition.
L'affectation hongroise se fait en entiers Python (O(n³) par page). »

Coût : le dénominateur commun (ppcm) de toutes les aires d'union d'une page
grandit à peu près comme le produit des unions distinctes. On mesure sa taille
et le coût d'une addition à cette taille, puis on extrapole un hongrois O(n³)
(n régions de chaque côté, régions de 100 à 2000 px de côté, page 3000×4000).
"""
import math, random, time
random.seed(0)
def boxes(n):
    out = []
    for _ in range(n):
        w, h = random.randint(100, 2000), random.randint(30, 600)
        x, y = random.randint(0, 3000 - w), random.randint(0, 4000 - h); out.append((x, y, x + w, y + h))
    return out
def union(a, b):
    i = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - i
for n in (10, 40, 100):
    R, Hy = boxes(n), [(x + 5, y + 3, x2 + 5, y2 + 3) for x, y, x2, y2 in boxes(n)]
    m = 1
    for a in R:
        for b in Hy: m = math.lcm(m, union(a, b))
    bits = m.bit_length()
    x = m * 7 + 3; t0 = time.perf_counter()
    for _ in range(2000): y = x + x; z = y > x
    op = (time.perf_counter() - t0) / 2000
    print(f"n = {n:3d} : ppcm des unions = {bits:7d} bits ; opération ≈ {op*1e6:7.2f} µs ; "
          f"hongrois n³ ≈ {n**3 * op:9.2f} s par page (hors facteur constant)")
print("=> décomposer en composantes connexes du graphe d'admissibilité, et départager les critères"
      " par passes successives (ou Fraction seulement entre ex æquo), au lieu d'un poids entier global.")
