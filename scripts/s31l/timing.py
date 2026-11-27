"""Durées par pipeline d'un RunResult (unités exécutées, pas relues) — outil de session.

Usage : python -I timing.py <run.json> [...]
"""

from __future__ import annotations

import json
import sys

for path in sys.argv[1:]:
    r = json.load(open(path, encoding="utf-8"))
    print(path)
    by: dict[str, list[tuple[str, float, object, object, str]]] = {}
    for u in r["usage"]:
        if u.get("resumed"):
            continue
        us = u["usage"] or {}
        by.setdefault(u["pipeline"], []).append(
            (u["document_id"], us.get("duration_seconds") or 0.0, us.get("tokens_in"),
             us.get("tokens_out"), u["outcome"])
        )
    for name, rows in by.items():
        total = sum(x[1] for x in rows)
        detail = ", ".join(f"{d} {t:.0f} s ({i}→{o}, {oc})" for d, t, i, o, oc in rows)
        print(f"  {name} : {total:.0f} s — {detail}")
