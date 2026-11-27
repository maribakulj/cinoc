"""Une spec réduite à des pipelines nommés (préfixe) et, au besoin, à des documents — outil de session.

Usage : python only.py <spec> <sortie> <run_id> <préfixe de nom> [doc_id,...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml


def main(src: str, dest: str, run_id: str, prefix: str, docs: str | None = None) -> None:
    spec = yaml.safe_load(Path(src).read_text(encoding="utf-8"))
    keep = [p for p in spec["pipelines"] if p["name"].startswith(prefix)]
    used = {s["adapter_name"] for p in keep for s in p["steps"]}
    spec["run_id"] = run_id
    spec["pipelines"] = keep
    spec["adapter_kwargs"] = {k: v for k, v in spec["adapter_kwargs"].items() if k in used}
    if docs:
        wanted = docs.split(",")
        spec["corpus"]["documents"] = [
            d for d in spec["corpus"]["documents"] if d["id"] in wanted
        ]
    Path(dest).write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )
    print([p["name"] for p in keep], len(spec["corpus"]["documents"]))


if __name__ == "__main__":
    main(*sys.argv[1:])
