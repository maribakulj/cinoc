"""Chaque score noté en ligne par une tranche = celui du RunResult final (relu hors ligne) — outil de session.

Usage : python -I compare_chunks.py <final.json> <tranche.json>...
"""
import json, sys

final = json.load(open(sys.argv[1], encoding="utf-8"))
index = {(d["view"], d["pipeline"], d["document_id"]): d for d in final["documents"]}
same = differ = absent = 0
for path in sys.argv[2:]:
    r = json.load(open(path, encoding="utf-8"))
    for d in r["documents"]:
        k = (d["view"], d["pipeline"], d["document_id"])
        if k not in index:
            absent += 1
        elif index[k] == d:
            same += 1
        else:
            differ += 1
            print(f"DIFFÈRE : {k} ({path})")
print(f"scores (vue × pipeline × document) des tranches : identiques {same}, différents {differ} (hors de cette spec : {absent})")
sys.exit(1 if differ or not same else 0)
