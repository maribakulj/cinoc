"""Tableaux du README : agrégat micro par pipeline et par vue, sur les répétitions — outil de session.

Une chaîne ré-exécutée (Mistral) : moyenne ± écart-type (échantillon) et [min ; max] sur
ses répétitions. Une chaîne déterministe recopiée : sa valeur, une fois, marquée.

Usage : python tables.py <corpus> <json rép. 1> ... <json rép. 5>
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

REPEATED = ("mistral", "ministral", "témoin")
COLUMNS = (
    ("texte", "cer"),
    ("texte", "cer_diplo"),
    ("texte (lignes)", "cer"),
    ("lecture", "cer"),
    ("sans césure", "cer"),
    ("texte", "wer"),
)


def fmt(values: list[float]) -> str:
    if len(values) == 1:
        return f"{values[0]:.4f}"
    mean = statistics.fmean(values)
    sd = statistics.stdev(values)
    return f"{mean:.4f} ± {sd:.4f}"


def main(corpus: str, *paths: str) -> None:
    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]
    names = [e["pipeline"] for e in runs[0]["pipelines"] if e["view"] == "texte"]
    head = " | ".join(f"`{v}` {m}" for v, m in COLUMNS)
    print(f"| {corpus} | n | {head} | notés | CER `texte` [min ; max] |")
    print("|---" * (len(COLUMNS) + 4) + "|")
    for name in names:
        repeated = any(k in name for k in REPEATED) and "local" not in name
        cells = []
        support = ""
        spread = ""
        n = 0
        for view, metric in COLUMNS:
            values = []
            for run in runs:
                for e in run["pipelines"]:
                    if e["pipeline"] == name and e["view"] == view:
                        s = next(s for s in e["aggregate"] if s["metric"] == metric)
                        if s["value"] is not None:
                            values.append(s["value"])
                        if view == "texte" and metric == "cer":
                            support = f"{s['support']}/{s['expected']}"
            if not repeated:
                values = values[:1]
            n = len(values)
            cells.append(fmt(values) if values else "—")
            if view == "texte" and metric == "cer" and len(values) > 1:
                spread = f"[{min(values):.4f} ; {max(values):.4f}]"
        if "local" in name:
            label, nlab = f"{name} ³", "1"
        elif not repeated:
            label, nlab = f"{name} ¹", "1"
        elif n == 1:
            label, nlab = f"{name} ²", "1"
        else:
            label, nlab = name, str(n)
        row = f"| {label} | {nlab} | " + " | ".join(cells) + f" | {support} | {spread or '—'} |"
        print(row.replace(".", ","))


if __name__ == "__main__":
    main(sys.argv[1], *sys.argv[2:])
