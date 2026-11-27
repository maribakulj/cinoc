"""§2.4 étape 1 « Filiation démontrée » : chaîne ayant consommé la VT ET « chaque
étape déclarée `preserves_region_ids` par son module ». « Alors les ids ...
SONT l'appariement. »

(a) La preuve repose sur une DÉCLARATION du module (tiers, in-process) : le
    défaut que K4 reproche à l'existant (« l'identité est déclarée, jamais
    vérifiée ») revient ici. Une brique qui garde les ids mais réécrit les
    boîtes (redressement, recadrage, re-segmentation partielle) donne tp = n à
    IoU nul.
(b) Même honnête, sous filiation la hypothèse hérite des régions de la VT :
    `region_detection` vaut 1 par construction pour un pipeline qui n'a rien
    segmenté. Le contrat ne dit pas que la détection est alors non applicable.
"""
def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy; union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union

gt = {"r1": (0, 0, 100, 40), "r2": (0, 60, 100, 100)}
# brique « deskew + recadrage » déclarée preserves_region_ids=True : mêmes ids, repère changé
hyp = {"r1": (0, 50, 100, 90), "r2": (0, 0, 100, 30)}
by_id = [(i, i) for i in gt if i in hyp]
tp_filiation = len(by_id)
tp_geometrie = sum(1 for i, j in by_id if iou(gt[i], hyp[j]) > 0.5)
print("IoU des paires par id :", {i: round(iou(gt[i], hyp[i]), 3) for i in gt})
print("tp sous filiation (ids = appariement) :", tp_filiation, "→ region_detection F1 =", 2 * tp_filiation / (2 * tp_filiation + 0 + 0))
print("tp si l'admissibilité restait exigée :", tp_geometrie)
assert tp_filiation == 2 and tp_geometrie == 0
print("=> exiger l'admissibilité géométrique AUSSI sous filiation (les ids ne servent "
      "qu'à départager), et déclarer `region_detection` non applicable quand les "
      "régions sont héritées de la VT.")
