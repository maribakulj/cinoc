"""Tire d'une spec sans clé ses seuls pipelines à fan-out — outil de session.

Usage : python fanout_keyless.py <spec sans clé> <sortie>
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml


def main(src: str, dest: str) -> None:
    spec = yaml.safe_load(Path(src).read_text(encoding="utf-8"))
    keep = [p for p in spec["pipelines"] if any(s.get("fanout") for s in p["steps"])]
    used = {s["adapter_name"] for p in keep for s in p["steps"]}
    spec["pipelines"] = keep
    spec["run_id"] = spec["run_id"] + "-fanout"
    spec["adapter_kwargs"] = {k: v for k, v in spec["adapter_kwargs"].items() if k in used}
    Path(dest).write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )
    print([p["name"] for p in keep])


if __name__ == "__main__":
    main(*sys.argv[1:3])
