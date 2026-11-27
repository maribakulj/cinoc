"""Recopie dans les répétitions 2-5 les unités sans clé produites dans la 1 — outil de session.

Une unité sans clé (Tesseract, règles) est déterministe : elle est calculée une
fois (répétition 1) et recopiée telle quelle, octet pour octet.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

S = Path("/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad")

for corpus, s30 in (("bnl", "archive-bnl"), ("dresden", "archive-dresden")):
    rep1 = S / "s31" / f"arch-{corpus}" / "repetition-1"
    old = {p.name for p in (S / "s30" / s30).iterdir()}
    keyless = []
    for unit in rep1.iterdir():
        if unit.name in old or not (unit / "index.json").is_file():
            continue
        if "mistral" not in (unit / "index.json").read_text(encoding="utf-8"):
            keyless.append(unit)
    print(corpus, len(keyless))
    b1 = json.loads((rep1 / "binaries.json").read_text(encoding="utf-8"))
    for k in range(2, 6):
        dest = S / "s31" / f"arch-{corpus}" / f"repetition-{k}"
        for unit in keyless:
            if not (dest / unit.name).exists():
                shutil.copytree(unit, dest / unit.name)
        bk = json.loads((dest / "binaries.json").read_text(encoding="utf-8"))
        bk.update({n: v for n, v in b1.items() if "mistral" not in n})
        (dest / "binaries.json").write_text(
            json.dumps(bk, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
