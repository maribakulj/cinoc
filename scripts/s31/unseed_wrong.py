"""Retire des répétitions 2-5 ce que seed_keyless.py y a recopié à tort — outil de session.

Les unités Ministral de l'essai (« ministral » ne contient pas « mistral ») et
les échecs de l'essai 1 (Pillow absent, index sans étape).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

S = Path("/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad")

for corpus, s30 in (("bnl", "archive-bnl"), ("dresden", "archive-dresden")):
    old = {p.name for p in (S / "s30" / s30).iterdir()}
    for k in range(2, 6):
        dest = S / "s31" / f"arch-{corpus}" / f"repetition-{k}"
        removed = 0
        for unit in dest.iterdir():
            if unit.name in old or not (unit / "index.json").is_file():
                continue
            text = (unit / "index.json").read_text(encoding="utf-8")
            data = json.loads(text)
            if "ministral" in text or data["outcome"] != "ok":
                shutil.rmtree(unit)
                removed += 1
        print(corpus, k, "retirées", removed)
    # contrôle : dans la 1, ce qui reste hors S30 et sans « mistral »
    rep1 = S / "s31" / f"arch-{corpus}" / "repetition-1"
    n = 0
    for unit in rep1.iterdir():
        if unit.name in old or not (unit / "index.json").is_file():
            continue
        text = (unit / "index.json").read_text(encoding="utf-8")
        if "mistral" not in text and "ministral" not in text and json.loads(text)["outcome"] == "ok":
            n += 1
    print(corpus, "sans clé ré-exécutées dans la 1 :", n)
