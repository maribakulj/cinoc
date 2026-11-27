"""``docs/PLUGINS.md`` : un module écrivable depuis la seule page (S34b, n° 11).

Le testeur extérieur a suivi la page : l'exemple finissait sur
``StepOutput(artifacts={ArtifactType.RAW_TEXT: ...})`` — la construction de
l'``Artifact`` non dite —, aucune voie sans paquet pip, et la page était en
français, renvoyant à ``CLAUDE.md`` et à des numéros de décision. Ici, les trois
blocs marqués de la page (module, script, spec) sont **extraits et exécutés**
tels quels sur une page de corpus : s'ils cessent de marcher, la suite échoue.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "PLUGINS.md"
FIRST_CORPUS = ROOT / "tests" / "fixtures" / "first_corpus"


def _blocks() -> dict[str, str]:
    texte = PAGE.read_text(encoding="utf-8")
    motif = r"<!-- example: ([\w-]+) -->\n```\w+\n(.*?)```"
    return dict(re.findall(motif, texte, re.S))


def test_the_page_carries_a_module_a_script_and_a_spec() -> None:
    assert {"plugin-module", "plugin-script", "plugin-spec"} <= set(_blocks())


def test_the_module_of_the_page_runs_without_a_package(tmp_path: Path) -> None:
    """Le module, le script et la spec de la page, sans rien installer."""
    blocs = _blocks()
    (tmp_path / "my_ocr.py").write_text(blocs["plugin-module"], encoding="utf-8")
    (tmp_path / "run_my_ocr.py").write_text(blocs["plugin-script"], encoding="utf-8")
    (tmp_path / "run.yaml").write_text(blocs["plugin-spec"], encoding="utf-8")
    for nom in ("page_001.png", "page_001.gt.txt"):
        shutil.copy(FIRST_CORPUS / nom, tmp_path / nom)

    fini = subprocess.run(
        [sys.executable, "run_my_ocr.py", "run.yaml", "report.html"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )

    assert fini.returncode == 0, fini.stderr[-2000:]
    assert (tmp_path / "report.html").read_text(encoding="utf-8").startswith(
        "<!DOCTYPE html>"
    )
    cer = re.search(r"^my_ocr texte cer (\S+)$", fini.stdout, re.M)
    assert cer and float(cer.group(1)) > 0.0, fini.stdout  # une vraie mesure


def test_the_page_is_in_english_and_self_contained() -> None:
    """Comme le README et le guide ; aucun renvoi au contrat interne."""
    texte = PAGE.read_text(encoding="utf-8")
    assert "CLAUDE.md" not in texte
    assert not re.search(r"\bD-\d{3}\b", texte)
    prose = re.sub(r"```.*?```", "", texte, flags=re.S)
    francais = re.findall(r"\b(les|des|une|pour|avec|dans)\b", prose)
    assert not francais, francais[:5]
