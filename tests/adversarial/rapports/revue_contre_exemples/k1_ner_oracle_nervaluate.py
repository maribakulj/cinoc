"""M3 « Vérif. : O nervaluate (NER) » pour `ner_f1` / `ner_f1_exact`.

`ner_f1` apparie par IoU d'empan ≥ 0,5 (`metrics/ner.py:41`, `ner.py:229`).
nervaluate apparie par CHEVAUCHEMENT (ent_type/partial) ou par bornes exactes
(strict/exact) : aucun de ses schémas n'est « IoU ≥ 0,5 ». Une prédiction qui
couvre l'entité mais déborde (IoU = 1/3) est juste pour nervaluate
(ent_type) et fausse (fp + fn) pour ner_f1. L'oracle désigné ne calcule pas la
même grandeur.
"""
from nervaluate import Evaluator

true = [[{"label": "PER", "start": 0, "end": 9}]]
pred = [[{"label": "PER", "start": 0, "end": 29}]]       # couvre l'entité, 3× trop long
iou = 10 / 30
res = Evaluator(true, pred, tags=["PER"]).evaluate()
overall = res[0] if isinstance(res, tuple) else res["overall"]
for scheme in ("ent_type", "partial", "strict", "exact"):
    s = overall[scheme]
    get = (lambda k: s[k]) if isinstance(s, dict) else (lambda k: getattr(s, k))
    print(f"nervaluate {scheme:8s} : correct={get('correct')} partial={get('partial')} f1={get('f1'):.3f}")
print(f"ner_f1 (IoU ≥ 0,5) : IoU = {iou:.3f} -> tp=0, fp=1, fn=1, F1 = 0")
print("=> oracle à reconstruire (énumération sur l'IoU d'empan), nervaluate seulement pour strict ⇔ bornes exactes, ce que ner_f1_exact n'est pas non plus.")

# Confirmation par le code de Cinoc (copie figée)
from cinoc.evaluation.ner import Entity, EntitySet, compute_ner
text = "Jean Valjean marche dans Paris ce matin de juin"
ref = EntitySet(text, (Entity("PER", 0, 10),))
hyp = EntitySet(text, (Entity("PER", 0, 30),))
c = compute_ner(ref, hyp)
print("Cinoc compute_ner :", (c.tp, c.fp, c.fn))
assert (c.tp, c.fp, c.fn) == (0, 1, 1)
