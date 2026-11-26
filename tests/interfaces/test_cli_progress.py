"""``cinoc run`` dit où il en est : une ligne par unité terminée (D-307).

Le testeur extérieur : ``cinoc run … --recipe vlm_seul --brick vlm=ollama`` —
rien pendant 422 s, puis « Rapport écrit » et le bilan. Une ligne par unité
(document × pipeline), sur la sortie d'erreur : la sortie standard reste celle
qu'un script lit, et le compte est celui que la vitrine diffuse en SSE (le même
rappel de l'orchestrateur).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from cinoc.interfaces.cli import main

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
_LIGNE = re.compile(r"^\[(\d+)/(\d+)\] (\S+) · (\S+) — (.+)$")


def test_each_finished_unit_prints_one_line_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copytree(EXAMPLES, tmp_path / "examples")
    assert main(["run", str(tmp_path / "examples" / "config.yaml"),
                 "-o", str(tmp_path / "r.html")]) == 0
    sortie = capsys.readouterr()
    lignes = [m for ligne in sortie.err.splitlines() if (m := _LIGNE.match(ligne))]
    # 2 pipelines × 5 documents de l'exemple.
    assert len(lignes) == 10
    assert sorted(int(m.group(1)) for m in lignes) == list(range(1, 11))
    assert {m.group(2) for m in lignes} == {"10"}
    assert {m.group(3) for m in lignes} == {"tesseract", "pero"}
    assert {m.group(5) for m in lignes} == {"fait"}
    assert "[1/" not in sortie.out
