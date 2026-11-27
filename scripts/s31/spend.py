"""Dépense Mistral d'un ou plusieurs RunResult — outil de session.

Jetons et pages relus dans ``usage`` (unités **exécutées** par ce run : ``resumed``
false), au tarif de ``pricing.json`` ; et, à côté, le coût que l'analyse
``economics`` du RunResult écrit, quand elle en écrit un.

Usage : python spend.py <run_result.json> [...]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

PRICING = json.loads(
    (Path(__file__).resolve().parents[0] / "pricing.json").read_text(encoding="utf-8")
)
IN = PRICING["cloud_models"]["mistral/mistral-small-latest"]["input_eur_per_mtok"]
OUT = PRICING["cloud_models"]["mistral/mistral-small-latest"]["output_eur_per_mtok"]
PAGE = PRICING["cloud_page_kinds"]["mistral_ocr"]["eur_per_1k_pages"] / 1000


def spend(path: str, *, all_units: bool = False) -> tuple[dict, float]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for unit in data["usage"]:
        if unit.get("resumed") and not all_units:
            continue
        u = unit["usage"]
        r = rows[unit["pipeline"]]
        r["units"] += 1
        r["failed"] += unit["outcome"] == "failed"
        r["tin"] += u.get("tokens_in") or 0
        r["tout"] += u.get("tokens_out") or 0
        r["cache"] += u.get("tokens_cache_read") or 0
        r["pages"] += u.get("billed_pages") or 0
    total = 0.0
    for name, r in rows.items():
        pin, pout = IN, OUT
        for short in ("ministral-8b", "ministral-3b"):
            if f"({short})" in name:
                e = PRICING["cloud_models"][f"mistral/{short}-latest"]
                pin, pout = e["input_eur_per_mtok"], e["output_eur_per_mtok"]
        r["eur"] = r["tin"] * pin / 1e6 + r["tout"] * pout / 1e6 + r["pages"] * PAGE
        total += r["eur"]
    return rows, total


def economics(path: str) -> list[tuple[str, object, object]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for a in data.get("analyses", []):
        p = a["payload"]
        if p.get("kind") == "economics":
            for e in p.get("pipelines", []) or p.get("entries", []) or []:
                out.append((e.get("pipeline"), e.get("cost_eur"), e.get("basis")))
    return out


if __name__ == "__main__":
    all_units = "--all" in sys.argv
    grand = 0.0
    for path in [a for a in sys.argv[1:] if a != "--all"]:
        rows, total = spend(path, all_units=all_units)
        grand += total
        print(f"== {path}")
        for name, r in sorted(rows.items()):
            if not (r["tin"] or r["tout"] or r["pages"]):
                continue
            print(
                f"  {name:75s} u={int(r['units']):3d} ko={int(r['failed']):2d} "
                f"in={int(r['tin']):8d} out={int(r['tout']):7d} cache={int(r['cache']):5d} "
                f"pages={int(r['pages']):3d} -> {r['eur']:.4f} EUR"
            )
        print(f"  total {total:.4f} EUR")
    print(f"TOTAL {grand:.4f} EUR")
