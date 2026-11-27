"""Tire de la spec complète sa partie Mistral (pipelines à l'identique) — outil de session.

Usage : python split_specs.py <spec complète> <sortie> <run_id> [doc_id,...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

FACTUREES = {"mistral", "mistral_ocr"}


def billed(pipeline, kwargs):
    for step in pipeline["steps"]:
        name = step["adapter_name"]
        if name.split(":", 1)[0] in FACTUREES:
            return True
        if kwargs.get(name, {}).get("producer") in {"mistral", "mistral_vision"}:
            return True
    return False


def main(src: str, dest: str, run_id: str, docs: str | None = None) -> None:
    spec = yaml.safe_load(Path(src).read_text(encoding="utf-8"))
    kwargs = spec["adapter_kwargs"]
    pipelines = [p for p in spec["pipelines"] if billed(p, kwargs)]
    used = {s["adapter_name"] for p in pipelines for s in p["steps"]}
    out = dict(spec)
    out["run_id"] = run_id
    out["pipelines"] = pipelines
    out["adapter_kwargs"] = {k: v for k, v in kwargs.items() if k in used}
    if docs:
        wanted = docs.split(",")
        out["corpus"] = dict(spec["corpus"])
        out["corpus"]["documents"] = [
            d for d in spec["corpus"]["documents"] if d["id"] in wanted
        ]
    Path(dest).write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
