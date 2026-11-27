"""Tranche d'une spec commitée (pipelines par préfixe de nom, documents par id) — outil de session.

Les pipelines et réglages sont recopiés tels quels : la clé d'unité ne dépend que
du pipeline, de ses briques et du document, donc une tranche archive exactement
les unités que la spec entière relira.

Usage : python -I chunk.py <spec> <sortie> [--pipeline préfixe]... [--docs id,id]
"""
import argparse
from pathlib import Path

import yaml

ap = argparse.ArgumentParser()
ap.add_argument("spec", type=Path)
ap.add_argument("out", type=Path)
ap.add_argument("--pipeline", action="append", default=[])
ap.add_argument("--docs", default="")
a = ap.parse_args()
s = yaml.safe_load(a.spec.read_text(encoding="utf-8"))
if a.pipeline:
    s["pipelines"] = [p for p in s["pipelines"] if any(p["name"].startswith(x) for x in a.pipeline)]
    assert len(s["pipelines"]) == len(a.pipeline), [p["name"] for p in s["pipelines"]]
if a.docs:
    ids = a.docs.split(",")
    s["corpus"]["documents"] = [d for d in s["corpus"]["documents"] if d["id"] in ids]
    assert len(s["corpus"]["documents"]) == len(ids), ids
used = {st["adapter_name"] for p in s["pipelines"] for st in p["steps"]}
s["adapter_kwargs"] = {k: v for k, v in s["adapter_kwargs"].items() if k in used}
s["run_id"] = s["run_id"] + "-" + a.out.stem
a.out.write_text(yaml.safe_dump(s, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
