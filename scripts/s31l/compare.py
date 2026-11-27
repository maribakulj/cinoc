"""Re-notation hors ligne : le RunResult relu doit égaler celui du run — outil de session.

Usage : python -I compare.py <run.json> <offline.json>
Sortie : une ligne par section ; code 1 si une section notée diffère.
"""

from __future__ import annotations

import json
import sys


def main(a_path: str, b_path: str) -> int:
    a = json.load(open(a_path, encoding="utf-8"))
    b = json.load(open(b_path, encoding="utf-8"))
    bad = 0
    for key in ("pipelines", "documents", "cross_engine", "analyses"):
        same = a.get(key) == b.get(key)
        bad += not same
        print(f"{key}: {'identique' if same else 'DIFFÈRE'}")

    def strip(rows):
        return [{k: v for k, v in r.items() if k != "resumed"} for r in rows]

    same_usage = strip(a["usage"]) == strip(b["usage"])
    bad += not same_usage
    resumed = sum(1 for r in b["usage"] if r.get("resumed"))
    print(f"usage (hors resumed): {'identique' if same_usage else 'DIFFÈRE'} ; "
          f"relues hors ligne {resumed}/{len(b['usage'])}")
    ma, mb = a["manifest"], b["manifest"]
    diff = sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k))
    print(f"manifeste, champs qui diffèrent : {diff}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
