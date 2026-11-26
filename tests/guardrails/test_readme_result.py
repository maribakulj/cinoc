"""Chaque nombre du résultat montré au README se relit dans un ``RunResult`` commité.

Le README de P5i montre **un vrai résultat** (S33, D-305) : la partie sans clé
de la campagne de référence (S30). Un tableau recopié à la main dérive dès
qu'un run est refait — ou ment dès le premier jour si une décimale est mal
lue. Ce test relit chaque ligne du tableau dans le ``RunResult`` du dossier de
campagne : CER et WER de la vue ``texte`` (agrégat micro, quatre décimales) et
le support « notés / attendus ».
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / "campaigns" / "2026-11-26-reference"
RESULTS = {
    "BNL": CAMPAIGN / "bnl-sans-cle.run_result.json",
    "Dresden": CAMPAIGN / "dresden-sans-cle.run_result.json",
}
_ROW = re.compile(
    r"^\|\s*(?P<corpus>[^|]*?)\s*\|\s*(?P<pipeline>[^|]+?)\s*\|\s*(?P<cer>[\d.]+)"
    r"\s*\|\s*(?P<wer>[\d.]+)\s*\|\s*(?P<support>\d+)/(?P<expected>\d+)\s*\|$"
)


def _section() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    start = readme.index("## A real result")
    return readme[start : readme.index("\n## ", start + 1)]


def _scores(path: Path) -> dict[str, dict[str, dict[str, object]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        entry["pipeline"]: {score["metric"]: score for score in entry["aggregate"]}
        for entry in data["pipelines"]
        if entry["view"] == "texte"
    }


def test_every_number_of_the_readme_result_is_in_a_committed_run_result() -> None:
    rows = [m for line in _section().splitlines() if (m := _ROW.match(line))]
    assert len(rows) >= 4, "le tableau du résultat a disparu du README"
    corpus = ""
    for row in rows:
        corpus = row["corpus"].strip() or corpus
        source = next(path for key, path in RESULTS.items() if key in corpus)
        scores = _scores(source)[row["pipeline"]]
        cer, wer = scores["cer"], scores["wer"]
        assert row["cer"] == f"{cer['value']:.4f}", (row.group(0), cer)
        assert row["wer"] == f"{wer['value']:.4f}", (row.group(0), wer)
        assert (int(row["support"]), int(row["expected"])) == (
            cer["support"],
            cer["expected"],
        ), row.group(0)
