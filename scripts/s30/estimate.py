"""Estimation du coût Mistral de la campagne (S30) — outil de session.

Sources :
- tarifs : cinoc/evaluation/pricing.json (2026-11-25) — mistral-small-latest
  0,14 €/Mtok entrée, 0,55 €/Mtok sortie ; mistral_ocr 3,66 €/1 000 pages ;
- jetons d'image : docs.mistral.ai, Vision, FAQ (lue le 2026-11-26) — Mistral
  Small 3.2 : image ramenée à 1540×1540 au plus, ≈ W·H/784 jetons (≈ 3 025 max) ;
- jetons de texte : 3,0 caractères par jeton (prudent : qwen2.5vl en a donné
  3,8 sur le pilote, D-281) ;
- saknussemm : jetons mesurés (producteur ollama, même chaîne) sur 3 pages BNL,
  extrapolés au prorata des caractères de GT.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import yaml
from PIL import Image

IN, OUT = 0.14 / 1e6, 0.55 / 1e6
OCR_PAGE = 3.66 / 1000
CHARS_PER_TOKEN = 3.0


def img_tokens(w: int, h: int, maxs: int = 1540) -> int:
    s = min(1.0, maxs / max(w, h))
    return math.ceil((w * s) * (h * s) / 784)


def text_tokens(chars: float) -> float:
    return chars / CHARS_PER_TOKEN


def main(params_path: str) -> None:
    params = json.loads(Path(params_path).read_text())
    table = []
    for corpus in params["corpora"]:
        name = corpus["name"]
        pages = corpus["pages"]  # [{w,h,chars,regions:[(w,h)...]}]
        n = len(pages)
        chars = sum(p["chars"] for p in pages)
        img = sum(img_tokens(p["w"], p["h"]) for p in pages)
        transcription_prompt = text_tokens(params["transcription_prompt_chars"])
        correction_prompt = text_tokens(corpus["correction_prompt_chars"])
        out_text = text_tokens(chars) * 1.2  # sortie ≈ GT + 20 %
        rows = {}
        rows["E0 · mistral-ocr"] = (0, 0, n)
        # correction : prompt + texte OCR (≈ GT × 1,1) en entrée
        corr_in = n * correction_prompt + text_tokens(chars) * 1.1
        rows["E2 · tesseract → mistral"] = (corr_in, out_text, 0)
        rows["E2 · mistral-ocr → mistral"] = (corr_in, out_text, n)
        regions = [r for p in pages for r in p["regions"]]
        reg_img = sum(img_tokens(w, h) for w, h in regions)
        rows["E1 · segmentation → mistral (VLM par région)"] = (
            reg_img + len(regions) * transcription_prompt,
            out_text,
            0,
        )
        sak_in = corpus["saknussemm_in_per_char"] * chars
        sak_out = corpus["saknussemm_out_per_char"] * chars
        rows["E3 · … → saknussemm (mistral)"] = (sak_in, sak_out, 0)
        if corpus.get("e4", True):
            rows["E4 · … → saknussemm sélectif (mistral, QE)"] = (sak_in, sak_out, 0)
        rows["E5 · mistral (VLM)"] = (img + n * transcription_prompt, out_text, 0)
        # Plafond : chaque appel rend son max_tokens (spec), entrée × 1,5 ;
        # saknussemm (aucun plafond réglable) : sortie × 3.
        caps = {
            "E2 · tesseract → mistral": n * 2048,
            "E2 · mistral-ocr → mistral": n * 2048,
            "E1 · segmentation → mistral (VLM par région)": len(regions) * 1024,
            "E5 · mistral (VLM)": n * 2048,
        }
        for exp, (tin, tout, ocr_pages) in rows.items():
            cost = tin * IN + tout * OUT + ocr_pages * OCR_PAGE
            cap_out = caps.get(exp, tout * 3)
            ceiling = tin * 1.5 * IN + cap_out * OUT + ocr_pages * OCR_PAGE
            table.append((name, exp, tin, tout, ocr_pages, cost, ceiling))
        print(f"{name}: {n} pages, {chars} car., {img} jetons d'image, "
              f"{len(regions)} régions ({reg_img} jetons)")
    reps = params["repetitions"]
    margin = params["margin"]
    total = ceil = 0.0
    print("| corpus | expérience | jetons entrée | jetons sortie | pages OCR | € / passage "
          f"| € × {reps} | plafond × {reps} |")
    print("|---|---|---|---|---|---|---|---|")
    for name, exp, tin, tout, pages, cost, ceiling in table:
        total += cost * reps
        ceil += ceiling * reps
        print(f"| {name} | {exp} | {tin:,.0f} | {tout:,.0f} | {pages} | {cost:.4f} "
              f"| {cost * reps:.3f} | {ceiling * reps:.3f} |".replace(",", " "))
    print(f"total central × {reps} : {total:.2f} € ; avec marge × {margin} : "
          f"{total * margin:.2f} € ; plafond : {ceil:.2f} €")


if __name__ == "__main__":
    main(sys.argv[1])
    _ = yaml, Image
