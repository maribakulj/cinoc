"""Ajoute le témoin « segmentation → tesseract → mistral (correction libre) » — outil de session.

Même préfixe qu'E3 (seg, reco fan-out Tesseract, lecture = projection du layout),
puis la correction LLM libre (brique ``mistral``, rôle text_only) au lieu de
saknussemm : même modèle (mistral-small-latest), température 0 (la première
tentative de saknussemm), ``max_tokens`` au défaut de la brique (8192 —
saknussemm n'en envoie aucun), prompt de correction d'E2 sur le corpus.
Inséré juste avant E3 · saknussemm (mistral). Usage : python add_temoin.py <spec>
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import yaml

E3 = "E3 · segmentation → tesseract → saknussemm (mistral)"
NAME = "E3 témoin · segmentation → tesseract → mistral (correction libre)"
ADAPTER = "mistral:correction_seg"


def main(path: str) -> None:
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    names = [p["name"] for p in spec["pipelines"]]
    if NAME in names:
        return
    at = names.index(E3)
    p = copy.deepcopy(spec["pipelines"][at])
    p["name"] = NAME
    p["description"] = (
        "Témoin d'E3 : même lecture segmentée, corrigée par le LLM sans saknussemm "
        "(même modèle, température 0) — la seule comparaison qui isole saknussemm."
    )
    p["steps"] = [s for s in p["steps"] if s["id"] != "correction"] + [
        {
            "id": "correction",
            "kind": "correction",
            "adapter_name": ADAPTER,
            "input_types": ["raw_text"],
            "output_types": ["corrected_text"],
            "inputs_from": {"raw_text": "lecture"},
        }
    ]
    spec["pipelines"].insert(at, p)
    kwargs = {
        k: v
        for k, v in spec["adapter_kwargs"]["mistral:correction"].items()
        if k not in {"label", "max_tokens"}
    }
    spec["adapter_kwargs"][ADAPTER] = {
        "label": "correction_seg",
        **kwargs,
        "temperature": 0.0,
    }
    Path(path).write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )


if __name__ == "__main__":
    main(sys.argv[1])
