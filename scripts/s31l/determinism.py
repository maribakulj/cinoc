"""Preuve de déterminisme : une seconde exécution d'un sous-ensemble contre la
campagne — outil de session.

Pour chaque unité de l'archive de rejeu (mêmes clés que la campagne, l'image et
les réglages étant identiques) : les ``content_hash`` de chaque artefact produit,
étape par étape, comparés à ceux de l'archive de la campagne ; puis, pour les
unités qui diffèrent, l'écart de CER (vue ``texte``) entre les deux RunResult.

Usage : python -I determinism.py <archive campagne> <archive rejeu> <campagne.json> <rejeu.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def hashes(index: Path) -> dict[tuple[str, str], str | None]:
    data = json.loads(index.read_text(encoding="utf-8"))
    out = {}
    for entry in data["steps"]:
        if entry["step"] == "__initial__":
            continue
        for kind, art in entry["artifacts"].items():
            out[(entry["step"], kind)] = art.get("content_hash")
    out[("__outcome__", "")] = data["outcome"]
    return out


def cer_by_unit(path: str) -> dict[tuple[str, str], float]:
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        (d["pipeline"], d["document_id"]): next(
            s["value"] for s in d["scores"] if s["metric"] == "cer"
        )
        for d in r["documents"]
        if d["view"] == "texte"
    }


def unit_names(path: str) -> list[tuple[str, str]]:
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    return [(u["pipeline"], u["document_id"]) for u in r["usage"]]


def main(main_arch: str, replay_arch: str, main_json: str, replay_json: str) -> None:
    base, replay = Path(main_arch), Path(replay_arch)
    same = differ = missing = 0
    differing_steps: dict[str, int] = {}
    for index in sorted(replay.glob("*/index.json")):
        other = base / index.parent.name / "index.json"
        if not other.is_file():
            missing += 1
            print(f"absente de la campagne : {index.parent.name}")
            continue
        a, b = hashes(other), hashes(index)
        if a == b:
            same += 1
        else:
            differ += 1
            for k in sorted(set(a) | set(b)):
                if a.get(k) != b.get(k):
                    differing_steps[f"{k[0]}.{k[1]}"] = differing_steps.get(f"{k[0]}.{k[1]}", 0) + 1
    print(f"unités rejouées : {same + differ + missing} ; hashes identiques : {same} ; "
          f"différentes : {differ} ; absentes de la campagne : {missing}")
    if differing_steps:
        print(f"artefacts qui diffèrent (étape.type : unités) : {differing_steps}")
    ca, cb = cer_by_unit(main_json), cer_by_unit(replay_json)
    by_pipeline: dict[str, list[float]] = {}
    for unit in unit_names(replay_json):
        if unit in ca and unit in cb:
            by_pipeline.setdefault(unit[0], []).append(abs(ca[unit] - cb[unit]))
    for name, deltas in by_pipeline.items():
        print(f"  {name} : |ΔCER texte| max {max(deltas):.4f}, moyen "
              f"{sum(deltas) / len(deltas):.4f} sur {len(deltas)} page(s)")


if __name__ == "__main__":
    main(*sys.argv[1:5])
