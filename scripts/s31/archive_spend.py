"""Dépense lue dans une archive (unités absentes de l'archive S30) — outil de session.

Usage : python archive_spend.py <archive> <archive S30>
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

PRICING = json.loads((Path(__file__).parent / "pricing.json").read_text(encoding="utf-8"))
PAGE = PRICING["cloud_page_kinds"]["mistral_ocr"]["eur_per_1k_pages"] / 1000


ALIASES = {
    "mistral-small-2603": "mistral-small-latest",
    "ministral-8b-2512": "ministral-8b-latest",
    "ministral-3b-2512": "ministral-3b-latest",
}


def price(model: str) -> tuple[float, float]:
    entry = PRICING["cloud_models"].get(f"mistral/{ALIASES.get(model, model)}")
    if entry is None:
        raise SystemExit(f"tarif absent : {model}")
    return entry["input_eur_per_mtok"], entry["output_eur_per_mtok"]


def main(archive: str, s30: str) -> None:
    base, old = Path(archive), {p.name for p in Path(s30).iterdir()}
    rows: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    total = 0.0
    for unit in sorted(base.iterdir()):
        if unit.name in old or not (unit / "index.json").is_file():
            continue
        data = json.loads((unit / "index.json").read_text(encoding="utf-8"))
        adapters, doc, key = [], "?", "(échec, sans étape)"
        cost = 0.0
        for step in data["steps"]:
            for art in step["artifacts"].values():
                doc = art["document_id"]
                parts = art["id"].split(":")
                if step["step"] != "__initial__" and len(parts) >= 4:
                    name = ":".join(parts[1:3])
                    if name not in adapters:
                        adapters.append(name)
            u = step.get("usage") or {}
            served = next(
                (
                    a["provenance"]["served_models"][0]
                    for a in step["artifacts"].values()
                    if a.get("provenance") and a["provenance"].get("served_models")
                ),
                "mistral-small-latest",
            )
            if u.get("tokens_in") or u.get("tokens_out"):
                pin, pout = price(served)
                cost += (u.get("tokens_in") or 0) * pin / 1e6
                cost += (u.get("tokens_out") or 0) * pout / 1e6
            cost += (u.get("billed_pages") or 0) * PAGE
            key = " → ".join(adapters)
        billed = data.get("billed") or {}
        if billed:
            pass
        r = rows[key]
        r["units"] += 1
        r["failed"] += data["outcome"] != "ok"
        r["eur"] += cost
        total += cost
        _ = doc
    for key, r in sorted(rows.items()):
        print(f"  {key:90s} u={int(r['units']):3d} ko={int(r['failed']):2d} {r['eur']:.4f} EUR")
    print(f"TOTAL {total:.4f} EUR")


if __name__ == "__main__":
    main(*sys.argv[1:3])
