"""Noter un ALTO d'un autre outil, sans moteur — la voie du guide, exécutée (D-307).

Le README promettait « transcriptions from another tool (text or ALTO) →
``precomputed`` », qui ne lit que du texte. Le testeur extérieur a écrit la spec
``alto_source → layout_to_text`` en devinant (dix minutes, un ``label`` requis
non documenté). Le guide la donne désormais ; ce test exécute **le bloc du
guide**, tel quel, pour qu'il ne puisse pas se périmer en silence. Le même
parcours tourne sur la roue installée (``tests/installed``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.interfaces.cli import main
from tests.installed._score_alto import guide_spec, pages_zip


def _import_and_extend(tmp_path: Path, *, transcriptions: bool) -> Path:
    archive = pages_zip(tmp_path, transcriptions=transcriptions)
    dest = tmp_path / "corpus"
    assert main(["corpus", "import", "zip", str(archive), "--dest", str(dest)]) == 0
    fichier = dest / "corpus.yaml"
    fichier.write_text(
        fichier.read_text(encoding="utf-8") + guide_spec(), encoding="utf-8"
    )
    return fichier


def test_the_guide_scores_an_existing_alto_without_engine(tmp_path: Path) -> None:
    import json

    fichier = _import_and_extend(tmp_path, transcriptions=True)
    sortie = tmp_path / "run.json"
    assert main(["run", str(fichier), "-o", str(tmp_path / "r.html"),
                 "--json", str(sortie)]) == 0
    result = json.loads(sortie.read_text(encoding="utf-8"))
    (texte,) = [p for p in result["pipelines"] if p["view"] == "texte"]
    cer = next(
        s["value"] for s in texte["conditional_aggregate"] if s["metric"] == "cer"
    )
    # L'ALTO porte exactement la transcription : rien à reprocher.
    assert cer == 0.0


def test_without_a_transcription_the_run_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sans ``.gt.txt``, l'import dérive la référence de ce même ALTO : un zéro
    par construction. La spec écrite à la main est refusée, comme la recette."""
    fichier = _import_and_extend(tmp_path, transcriptions=False)
    assert main(["run", str(fichier), "-o", str(tmp_path / "r.html")]) == 1
    assert "propre ALTO" in capsys.readouterr().err
