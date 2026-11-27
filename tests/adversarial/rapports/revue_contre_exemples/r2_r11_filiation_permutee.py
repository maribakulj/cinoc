"""Révision 2, R11 (§ 2.4 a 1) : filiation vérifiée = chaîne d'empreintes jusqu'à la
VT + `preserves_region_ids` déclaré + « la paire (même id, même page) est
ADMISSIBLE ». « Une paire qui remplit les trois est retenue en priorité. »
O2 : admissibilité inclusive 2·|∩| ≥ |∪|.

Une brique déclarée `preserves_region_ids` qui ÉCHANGE les ids de deux
régions de VT qui se recouvrent (r1 = page entière, r2 = ses 60 % supérieurs ;
PAGE l'autorise) passe les trois conditions : chaque paire « par id » est
admissible (IoU 0,6). Les paires par id sont retenues en priorité, ce qui
croise les textes, alors que l'optimum géométrique (IoU 1 et 1) les apparie
correctement. Le contrôle d'admissibilité ne prouve pas l'homologie quand les
régions de VT se recouvrent. Il s'écarte aussi de M8 (« optimum égal à
l'énumération »).
"""
from fractions import Fraction as F
from rapidfuzz.distance import Levenshtein as L
def inter(a, b): return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
def area(a): return (a[2] - a[0]) * (a[3] - a[1])
def iou(a, b): i = inter(a, b); return F(i, area(a) + area(b) - i)
def admissible(a, b): i = inter(a, b); return 2 * i >= area(a) + area(b) - i
gt = {"r1": ((0, 0, 100, 100), "TITRE corps du texte"), "r2": ((0, 0, 100, 60), "TITRE")}
# la brique hérite de la géométrie de la VT mais permute les ids (bogue ou mensonge)
hyp = {"r1": ((0, 0, 100, 60), "TITRE"), "r2": ((0, 0, 100, 100), "TITRE corps du texte")}
by_id = [(i, i) for i in gt if i in hyp and admissible(gt[i][0], hyp[i][0])]
print("paires par id admissibles :", {i: str(iou(gt[i][0], hyp[i][0])) for i, _ in by_id})
assert len(by_id) == 2
cer = lambda pairs: sum(L.distance(gt[r][1], hyp[h][1]) for r, h in pairs) / sum(len(t) for _, t in gt.values())
geo = [("r1", "r2"), ("r2", "r1")]                    # optimum : IoU 1 + 1
print("region_cer sous filiation « vérifiée » :", round(cer(by_id), 3),
      "| sous l'optimum géométrique :", round(cer(geo), 3),
      "| Σ IoU :", str(sum(iou(gt[r][0], hyp[h][0]) for r, h in by_id)), "contre", str(sum(iou(gt[r][0], hyp[h][0]) for r, h in geo)))
assert cer(by_id) > cer(geo)
print("=> sous héritage, exiger la géométrie IDENTIQUE à celle de la VT (empreinte des coordonnées),"
      " ou ne retenir la paire par id que si elle appartient à un optimum lexicographique.")
