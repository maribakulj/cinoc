"""Génère les specs de la campagne de référence (S30) — outil de session, non commité.

Usage : python gen_specs.py <corpus.yaml BNL> <corpus.yaml Dresden> <dossier de sortie>
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

OLLAMA = "http://127.0.0.1:11434"
MISTRAL_CHAT = "mistral-small-latest"
MISTRAL_OCR = "mistral-ocr-latest"


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


def ocr(adapter):
    return step("lecture", "ocr", adapter, ["image"], ["raw_text"], {"image": "__initial__"})


def vlm(adapter):
    return step(
        "lecture", "zero_shot", adapter, ["image"], ["raw_text"], {"image": "__initial__"}
    )


def seg_reco(reco_adapter, reco_kind="region_recognizer"):
    return [
        step("seg", "segmenter", "tesseract_layout:seg", ["image"], ["layout"],
             {"image": "__initial__"}),
        step("reco", reco_kind, reco_adapter, ["layout", "image"], ["layout"],
             {"layout": "seg", "image": "__initial__"}, fanout=True, crop=True),
        step("lecture", "projection", "layout_to_text:lecture", ["layout"], ["raw_text"],
             {"layout": "reco"}),
    ]


def text_correction(adapter):
    return step("correction", "correction", adapter, ["raw_text"], ["corrected_text"],
                {"raw_text": "lecture"})


def structured(adapter, native: bool):
    outputs = ["layout", "corrected_text", "decisions"] + (["native_json"] if native else [])
    return step("correction", "structured_correction", adapter, ["layout"], outputs,
                {"layout": "reco"})


def pipeline(name, description, steps):
    return {"name": name, "description": description, "initial_inputs": ["image"],
            "steps": steps}


VIEWS = [
    {
        "name": "texte",
        "description": (
            "Défaut (flat_text) : la sortie la plus aval de chaque chaîne. "
            "cer_diplo = convention BNL ſ = s (repli des deux côtés)."
        ),
        "candidate_types": ["raw_text", "corrected_text"],
        "normalization_profile": "flat_text",
        "metric_names": ["cer", "wer", "cer_diplo", "cmer", "mer", "unanchored_trigrams"],
    },
    {
        "name": "texte (lignes)",
        "description": "Défaut (keep_line_breaks) : sauts de ligne comptés — le chiffre comparable à dinglehopper.",
        "candidate_types": ["raw_text", "corrected_text"],
        "normalization_profile": "keep_line_breaks",
        "metric_names": ["cer"],
    },
    {
        "name": "lecture",
        "description": "Ablation : l'étape « lecture » de chaque chaîne, avant toute correction (E0/E1 dans les chaînes E2/E3/E4).",
        "candidate_types": ["raw_text"],
        "normalization_profile": "flat_text",
        "target_step": "lecture",
        "metric_names": ["cer", "wer", "cer_diplo"],
    },
    {
        "name": "sans césure",
        "description": "Convention ⸗ : un mot coupé en fin de ligne (⸗, -, ‐, ‑, –, ¬ + saut) est recollé des deux côtés ; sauts de ligne comptés comme dans « texte (lignes) ».",
        "candidate_types": ["raw_text", "corrected_text"],
        "normalization_profile": "dehyphenated",
        "metric_names": ["cer"],
    },
]


def bnl(corpus, *, local_only: bool):
    lang = "Fraktur+fra"
    p = []
    kw = {
        "tesseract:lecture": {"label": "lecture", "lang": lang},
        "tesseract_layout:seg": {"label": "seg", "lang": lang},
        "tesseract:reco": {"label": "reco", "lang": lang},
        "layout_to_text:lecture": {"label": "lecture"},
        "saknussemm:regles": {"label": "regles", "producer": "rules"},
        "saknussemm:regles_qe": {"label": "regles_qe", "producer": "rules",
                                 "qe": "heuristic", "qe_skip": 0.5},
        "ollama:qwen_vlm": {"label": "qwen_vlm", "model": "qwen2.5vl:3b", "host": OLLAMA,
                            "role": "zero_shot", "max_tokens": 2048},
    }
    p += [
        pipeline("E0 · tesseract", "OCR seul (Tesseract Fraktur+fra).",
                 [ocr("tesseract:lecture")]),
        pipeline("E1 · segmentation → tesseract", "Segmentation Tesseract, OCR par région.",
                 seg_reco("tesseract:reco")),
        pipeline("E3 · segmentation → tesseract → saknussemm (règles)",
                 "Validation de chaîne sans clé : correction structurée par règles.",
                 [*seg_reco("tesseract:reco"), structured("saknussemm:regles", False)]),
        pipeline("E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique)",
                 "Validation de chaîne sans clé : routage QE (heuristique de saknussemm, AUC 0,5) puis règles.",
                 [*seg_reco("tesseract:reco"), structured("saknussemm:regles_qe", False)]),
        pipeline("E5 · qwen2.5vl:3b (local)", "VLM local zero-shot, prompt générique (déclaré au README).",
                 [vlm("ollama:qwen_vlm")]),
    ]
    if not local_only:
        kw.update({
            "mistral_ocr:lecture": {"label": "lecture", "model": MISTRAL_OCR},
            "mistral:correction": {"label": "correction", "model": MISTRAL_CHAT,
                                   "role": "text_only", "max_tokens": 2048,
                                   "prompt_name": "correction_press_19c_european"},
            "mistral:reco": {"label": "reco", "model": MISTRAL_CHAT, "role": "zero_shot",
                             "max_tokens": 1024},
            "mistral:vlm": {"label": "vlm", "model": MISTRAL_CHAT, "role": "zero_shot",
                            "max_tokens": 2048},
            "saknussemm:mistral": {"label": "mistral", "producer": "mistral",
                                   "model": MISTRAL_CHAT},
            "saknussemm:mistral_qe": {"label": "mistral_qe", "producer": "mistral",
                                      "model": MISTRAL_CHAT, "qe": "dalembert",
                                      "qe_skip": 0.5},
        })
        p += [
            pipeline("E0 · mistral-ocr", "OCR seul (Mistral OCR).",
                     [ocr("mistral_ocr:lecture")]),
            pipeline("E2 · tesseract → mistral", "OCR Tesseract puis correction LLM (texte).",
                     [ocr("tesseract:lecture"), text_correction("mistral:correction")]),
            pipeline("E2 · mistral-ocr → mistral", "OCR Mistral puis correction LLM (texte).",
                     [ocr("mistral_ocr:lecture"), text_correction("mistral:correction")]),
            pipeline("E1 · segmentation → mistral (VLM par région)",
                     "Segmentation Tesseract, chaque région lue par le VLM.",
                     seg_reco("mistral:reco")),
            pipeline("E3 · segmentation → tesseract → saknussemm (mistral)",
                     "Correction structurée intégrale, chaque ligne au modèle.",
                     [*seg_reco("tesseract:reco"), structured("saknussemm:mistral", True)]),
            pipeline("E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert)",
                     "Correction structurée sélective : seules les lignes au-dessus du seuil QE partent au modèle.",
                     [*seg_reco("tesseract:reco"), structured("saknussemm:mistral_qe", True)]),
            pipeline("E5 · mistral (VLM)", "VLM cloud zero-shot sur la page entière.",
                     [vlm("mistral:vlm")]),
        ]
    return p, kw


def dresden(corpus, *, local_only: bool):
    lang = "Fraktur"
    kw = {
        "tesseract:lecture": {"label": "lecture", "lang": lang},
        "tesseract_layout:seg": {"label": "seg", "lang": lang},
        "tesseract:reco": {"label": "reco", "lang": lang},
        "layout_to_text:lecture": {"label": "lecture"},
        "saknussemm:regles": {"label": "regles", "producer": "rules"},
        "ollama:qwen_vlm": {"label": "qwen_vlm", "model": "qwen2.5vl:3b", "host": OLLAMA,
                            "role": "zero_shot", "max_tokens": 2048},
    }
    p = [
        pipeline("E0 · tesseract", "OCR seul (Tesseract Fraktur ; aucun modèle Kurrent).",
                 [ocr("tesseract:lecture")]),
        pipeline("E1 · segmentation → tesseract", "Segmentation Tesseract, OCR par région.",
                 seg_reco("tesseract:reco")),
        pipeline("E3 · segmentation → tesseract → saknussemm (règles)",
                 "Validation de chaîne sans clé : correction structurée par règles.",
                 [*seg_reco("tesseract:reco"), structured("saknussemm:regles", False)]),
        pipeline("E5 · qwen2.5vl:3b (local)", "VLM local zero-shot, prompt générique (déclaré au README).",
                 [vlm("ollama:qwen_vlm")]),
    ]
    if not local_only:
        kw.update({
            "mistral_ocr:lecture": {"label": "lecture", "model": MISTRAL_OCR},
            "mistral:correction": {"label": "correction", "model": MISTRAL_CHAT,
                                   "role": "text_only", "max_tokens": 2048},
            "mistral:reco": {"label": "reco", "model": MISTRAL_CHAT, "role": "zero_shot",
                             "max_tokens": 1024},
            "mistral:vlm": {"label": "vlm", "model": MISTRAL_CHAT, "role": "zero_shot",
                            "max_tokens": 2048},
            "saknussemm:mistral": {"label": "mistral", "producer": "mistral",
                                   "model": MISTRAL_CHAT},
        })
        p += [
            pipeline("E0 · mistral-ocr", "OCR seul (Mistral OCR).",
                     [ocr("mistral_ocr:lecture")]),
            pipeline("E2 · tesseract → mistral", "OCR Tesseract puis correction LLM (texte).",
                     [ocr("tesseract:lecture"), text_correction("mistral:correction")]),
            pipeline("E2 · mistral-ocr → mistral", "OCR Mistral puis correction LLM (texte).",
                     [ocr("mistral_ocr:lecture"), text_correction("mistral:correction")]),
            pipeline("E1 · segmentation → mistral (VLM par région)",
                     "Segmentation Tesseract, chaque région lue par le VLM.",
                     seg_reco("mistral:reco")),
            pipeline("E3 · segmentation → tesseract → saknussemm (mistral)",
                     "Correction structurée intégrale, chaque ligne au modèle.",
                     [*seg_reco("tesseract:reco"), structured("saknussemm:mistral", True)]),
            pipeline("E5 · mistral (VLM)", "VLM cloud zero-shot sur la page entière.",
                     [vlm("mistral:vlm")]),
        ]
    return p, kw


def write(build, corpus_path: Path, out: Path, run_id: str, local_only: bool) -> None:
    corpus = yaml.safe_load(corpus_path.read_text(encoding="utf-8"))["corpus"]
    pipelines, kwargs = build(corpus, local_only=local_only)
    used = {s["adapter_name"] for p in pipelines for s in p["steps"]}
    spec = {
        "run_id": run_id,
        "corpus": corpus,
        "pipelines": pipelines,
        "evaluation": {"views": VIEWS},
        "adapter_kwargs": {k: v for k, v in kwargs.items() if k in used},
    }
    out.write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )


if __name__ == "__main__":
    bnl_corpus, dresden_corpus, dest = map(Path, sys.argv[1:4])
    dest.mkdir(parents=True, exist_ok=True)
    write(bnl, bnl_corpus, dest / "bnl.yaml", "reference-bnl", False)
    write(bnl, bnl_corpus, dest / "bnl-sans-cle.yaml", "reference-bnl-sans-cle", True)
    write(dresden, dresden_corpus, dest / "dresden.yaml", "reference-dresden", False)
    write(dresden, dresden_corpus, dest / "dresden-sans-cle.yaml",
          "reference-dresden-sans-cle", True)
