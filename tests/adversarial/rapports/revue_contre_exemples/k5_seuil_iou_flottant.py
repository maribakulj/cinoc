"""§2.4 « seuil d'admissibilité θ (IoU ≥ θ ou > θ) » ; §6 n° 4 « IoU > 0,5 strict ».

Les boîtes sont en pixels entiers (`domain/layout.py:37`), mais l'appariement
les rend RELATIVES à la page (`metrics/layout.py:157`, x/width) avant l'IoU.
Une paire mathématiquement à IoU = 1/2 tombe alors d'un côté ou de l'autre du
seuil selon l'arrondi : le choix « ≥ » ou « > » n'est pas tranché par la
règle, il l'est par la largeur de la page. Référence : Fraction.
"""
from fractions import Fraction as F
from cinoc.evaluation.metrics.layout import _iou   # l'IoU existant, réutilisé par K5

def rel(box, w, h): x0, y0, x1, y1 = box; return (x0 / w, y0 / h, x1 / w, y1 / h)
def exact(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy; union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return F(inter, union)

hits = {}
for W in range(3, 400):
    for a in range(1, W // 2 + 1):
        r, h = (0, 0, a, 7), (0, 0, 2 * a, 7)           # IoU exact 1/2
        assert exact(r, h) == F(1, 2)
        v = _iou(rel(r, W, 7), rel(h, W, 7))
        if v != 0.5:
            hits.setdefault(">" if v > 0.5 else "<", (W, a, v))
    if len(hits) == 2:
        break
for k, (W, a, v) in hits.items():
    print(f"page de largeur {W} px, r = [0,0,{a},7], h = [0,0,{2*a},7] : IoU exact 1/2, "
          f"flottant {v!r} ({k} 0,5)")
assert hits
print("=> admissibilité à décider en entiers : 2·|r∩h| > |r∪h| sur les pixels (ou Fraction).")
