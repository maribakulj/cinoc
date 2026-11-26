"""Deux runs de la même spec → le même JSON, hors horloge (§12, D-282).

Le pilote (D-281, D4) a montré deux ``RunResult`` de la même spec qui ne
différaient que par l'ordre de ``candidate_types`` : un ``frozenset`` s'itère
selon le hachage des chaînes, randomisé **par processus**. Un test dans un seul
processus ne le voit donc pas ; celui-ci lance deux processus sous deux graines
de hachage différentes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

#: Champs d'horloge : ils varient par nature (wall-clock), le reste ne le doit pas.
_CLOCK = ("started_at", "completed_at", "duration_seconds")


def _without_clock(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _without_clock(v) for k, v in node.items() if k not in _CLOCK}
    if isinstance(node, list):
        return [_without_clock(v) for v in node]
    return node


def _run(config: Path, out: Path, seed: int) -> str:
    subprocess.run(
        [
            sys.executable, "-m", "cinoc.interfaces.cli", "run", str(config),
            "-o", str(out.with_suffix(".html")), "--json", str(out),
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PYTHONHASHSEED": str(seed)},
    )
    return out.read_text(encoding="utf-8")


def test_two_runs_of_the_same_spec_give_the_same_json(tmp_path: Path) -> None:
    shutil.copytree(EXAMPLES, tmp_path / "ex")
    config = tmp_path / "ex" / "config.yaml"
    # Trois types candidats : l'ordre d'un ensemble de trois chaînes change
    # avec la graine — les graines 0 et 3 en donnaient deux ordres différents.
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "    candidate_types:\n    - raw_text\n",
            "    candidate_types:\n    - raw_text\n    - corrected_text\n"
            "    - alto_xml\n",
            1,
        ),
        encoding="utf-8",
    )
    first = _run(config, tmp_path / "a.json", seed=0)
    second = _run(config, tmp_path / "b.json", seed=3)
    assert '"corrected_text"' in first
    assert _without_clock(json.loads(first)) == _without_clock(json.loads(second))
    # Octet pour octet, une fois l'horloge retirée du texte lui-même.
    horloge = re.compile(r'"(?:started_at|completed_at|duration_seconds)": [^,\n]*')
    assert horloge.sub("", first) == horloge.sub("", second)
