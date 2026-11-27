"""Ajoute E3 · saknussemm (ministral-8b, ministral-3b) à une spec complète — outil de session.

Mêmes étapes que « E3 · … → saknussemm (mistral) », seul le modèle du producteur
change ; insérés juste après elle. Usage : python add_ministral.py <spec.yaml>
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import yaml

SOURCE = "E3 · segmentation → tesseract → saknussemm (mistral)"
MODELS = (("ministral-8b", "ministral-8b-latest"), ("ministral-3b", "ministral-3b-latest"))


def main(path: str) -> None:
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    names = [p["name"] for p in spec["pipelines"]]
    at = names.index(SOURCE)
    base = spec["pipelines"][at]
    new = []
    for short, model in MODELS:
        label = short.replace("-", "_")
        name = f"E3 · segmentation → tesseract → saknussemm ({short})"
        if name in names:
            continue
        p = copy.deepcopy(base)
        p["name"] = name
        p["description"] = (
            f"Correction structurée intégrale, chaque ligne au modèle {model} "
            "(texte seul, comme E3 mistral-small)."
        )
        for step in p["steps"]:
            if step["id"] == "correction":
                step["adapter_name"] = f"saknussemm:{label}"
        new.append(p)
        spec["adapter_kwargs"][f"saknussemm:{label}"] = {
            "label": label,
            "producer": "mistral",
            "model": model,
        }
    spec["pipelines"][at + 1 : at + 1] = new
    Path(path).write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )


if __name__ == "__main__":
    main(sys.argv[1])
