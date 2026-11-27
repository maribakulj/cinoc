"""Génère les specs de la campagne locale (S31L) — outil de session, non commité.

Part de la spec sans clé de S30 (copiée telle quelle : mêmes pipelines, mêmes
réglages, mêmes vues → l'archive de S30 est relue) et ajoute les équivalents
locaux (Ollama) des expériences que S31 réservait à Mistral.

Usage : python gen_local.py <dossier campagne> [--subset ids,...] [--out f] [--corpus bnl|dresden]
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

import yaml

OLLAMA = "http://127.0.0.1:11434"
LLM = "qwen2.5:3b"
VLM = "qwen2.5vl:3b"


def step(id_, kind, adapter, inputs, outputs, sources, *, fanout=False, crop=False):
    return {
        "id": id_,
        "kind": kind,
        "adapter_name": adapter,
        "input_types": inputs,
        "output_types": outputs,
        "inputs_from": sources,
        **({"fanout": True} if fanout else {}),
        **({"crop": True} if crop else {}),
    }


def seg_reco(reco_adapter):
    return [
        step("seg", "segmenter", "tesseract_layout:seg", ["image"], ["layout"],
             {"image": "__initial__"}),
        step("reco", "region_recognizer", reco_adapter, ["layout", "image"], ["layout"],
             {"layout": "seg", "image": "__initial__"}, fanout=True, crop=True),
        step("lecture", "projection", "layout_to_text:lecture", ["layout"], ["raw_text"],
             {"layout": "reco"}),
    ]


def pipeline(name, description, steps):
    return {"name": name, "description": description, "initial_inputs": ["image"],
            "steps": steps}


def local_part(corpus: str):
    curated = corpus == "bnl"
    correction = {
        "label": "qwen_correction", "model": LLM, "host": OLLAMA, "role": "text_only",
        "max_tokens": 2048, "temperature": 0, "seed": 0, "timeout": 900,
    }
    if curated:
        correction["prompt_name"] = "correction_press_19c_european"
    kwargs = {
        "ollama:qwen_correction": correction,
        "ollama:qwen_reco": {
            "label": "qwen_reco", "model": VLM, "host": OLLAMA, "role": "zero_shot",
            "max_tokens": 1024, "temperature": 0, "seed": 0, "timeout": 900,
        },
        "saknussemm:qwen": {"label": "qwen", "producer": "ollama", "model": LLM,
                            "host": OLLAMA, "timeout": 1800},
    }
    tess = "tesseract:lecture"
    pipelines = [
        pipeline(
            f"E2 · tesseract → {LLM} (local)",
            "OCR Tesseract puis correction LLM locale (texte)"
            + (", prompt curé de correction presse XIXᵉ." if curated else ", prompt générique."),
            [
                step("lecture", "ocr", tess, ["image"], ["raw_text"], {"image": "__initial__"}),
                step("correction", "correction", "ollama:qwen_correction", ["raw_text"],
                     ["corrected_text"], {"raw_text": "lecture"}),
            ],
        ),
        pipeline(
            f"E1 · segmentation → {VLM} (VLM par région, local)",
            "Segmentation Tesseract, chaque région lue par le VLM local.",
            seg_reco("ollama:qwen_reco"),
        ),
        pipeline(
            f"E3 · segmentation → tesseract → saknussemm ({LLM}, local)",
            "Correction structurée intégrale par le LLM local.",
            [*seg_reco("tesseract:reco"),
             step("correction", "structured_correction", "saknussemm:qwen", ["layout"],
                  ["layout", "corrected_text", "decisions", "native_json"],
                  {"layout": "reco"})],
        ),
    ]
    if corpus == "bnl":
        kwargs["saknussemm:qwen_qe"] = {
            "label": "qwen_qe", "producer": "ollama", "model": LLM, "host": OLLAMA,
            "qe": "dalembert", "qe_skip": 0.5, "timeout": 1800,
        }
        pipelines.append(pipeline(
            f"E4 · segmentation → tesseract → saknussemm sélectif ({LLM}, QE dalembert, local)",
            "Correction structurée sélective : seules les lignes au-dessus du seuil QE "
            "partent au LLM local.",
            [*seg_reco("tesseract:reco"),
             step("correction", "structured_correction", "saknussemm:qwen_qe", ["layout"],
                  ["layout", "corrected_text", "decisions", "native_json"],
                  {"layout": "reco"})],
        ))
    return pipelines, kwargs


def build(campagne: Path, corpus: str) -> dict:
    base = yaml.safe_load((campagne / f"{corpus}-sans-cle.yaml").read_text(encoding="utf-8"))
    spec = copy.deepcopy(base)
    spec["run_id"] = f"reference-{corpus}-local"
    pipelines, kwargs = local_part(corpus)
    spec["pipelines"] = base["pipelines"] + pipelines
    spec["adapter_kwargs"] = {**base["adapter_kwargs"], **kwargs}
    return spec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("campagne", type=Path)
    ap.add_argument("--corpus", choices=["bnl", "dresden"], required=True)
    ap.add_argument("--subset", default="")
    ap.add_argument("--only-local", action="store_true",
                    help="ne garder que les pipelines locaux ajoutés (+ E5)")
    ap.add_argument("--pipeline", default="",
                    help="ne garder que les pipelines dont le nom commence par ce préfixe")
    ap.add_argument("--drop", action="append", default=[],
                    help="retirer les pipelines dont le nom commence par ce préfixe")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    spec = build(args.campagne, args.corpus)
    if args.subset:
        ids = args.subset.split(",")
        spec["corpus"]["documents"] = [d for d in spec["corpus"]["documents"] if d["id"] in ids]
        assert len(spec["corpus"]["documents"]) == len(ids), ids
    if args.only_local:
        spec["pipelines"] = [p for p in spec["pipelines"]
                             if "(local" in p["name"]]
    if args.run_id:
        spec["run_id"] = args.run_id
    for prefix in args.drop:
        before = len(spec["pipelines"])
        spec["pipelines"] = [p for p in spec["pipelines"] if not p["name"].startswith(prefix)]
        assert len(spec["pipelines"]) == before - 1, prefix
    if args.pipeline:
        spec["pipelines"] = [p for p in spec["pipelines"]
                             if p["name"].startswith(args.pipeline)]
        assert spec["pipelines"], args.pipeline
    used = {st["adapter_name"] for p in spec["pipelines"] for st in p["steps"]}
    spec["adapter_kwargs"] = {k: v for k, v in spec["adapter_kwargs"].items() if k in used}
    args.out.write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
