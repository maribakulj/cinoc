"""Deux RunResult : identiques hors horodatages et ``resumed`` ? — outil de session.

Usage : python same.py <exécution.json> <re-notation.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def strip_usage(units: list[dict]) -> list[dict]:
    return [{k: v for k, v in u.items() if k != "resumed"} for u in units]


def manifest_diff(a: dict, b: dict, path: str = "manifest") -> list[str]:
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            out += manifest_diff(a.get(k), b.get(k), f"{path}.{k}")
    elif a != b:
        out.append(path)
    return out


def main(left: str, right: str) -> int:
    a = json.loads(Path(left).read_text(encoding="utf-8"))
    b = json.loads(Path(right).read_text(encoding="utf-8"))
    ok = True
    for key in ("pipelines", "documents", "cross_engine", "analyses"):
        same = a[key] == b[key]
        ok &= same
        print(f"  {key:12s} {'identiques' if same else 'DIFFÉRENTS'}")
    same = strip_usage(a["usage"]) == strip_usage(b["usage"])
    ok &= same
    resumed = sum(1 for u in b["usage"] if u.get("resumed"))
    print(f"  usage        {'identique' if same else 'DIFFÉRENT'} hors resumed "
          f"({resumed}/{len(b['usage'])} relues)")
    diffs = manifest_diff(a["manifest"], b["manifest"])
    print(f"  manifeste    écarts : {diffs}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
