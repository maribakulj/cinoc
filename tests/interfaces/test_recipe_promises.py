"""Ce qu'une recette promet, le rapport le montre (S34b, divergence relevée).

``ocr_puis_llm`` annonçait « le rapport dit ce qui a été amélioré, dégradé,
réécrit sans raison », ``alto_corrige`` « ce qui a été changé et ce que le
correcteur a refusé » : le testeur n'a vu ni l'un ni l'autre. Ces bilans sont
des **analyses**, que le mode rapide (le défaut) ne calcule pas ; la promesse
était vraie en mode détaillé seulement — la description le dit désormais.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from cinoc.app.recipes import recipe_by_name
from cinoc.interfaces.cli import main
from tests.installed._score_alto import pages_zip


@pytest.mark.parametrize("name", ["ocr_puis_llm", "alto_corrige"])
def test_a_correction_recipe_says_its_balance_needs_the_detailed_mode(
    name: str,
) -> None:
    recette = recipe_by_name(name)
    assert "mode détaillé" in recette.description["fr"]
    assert "detailed mode" in recette.description["en"]


@pytest.mark.skipif(
    importlib.util.find_spec("saknussemm") is None,
    reason="saknussemm absent — la correction structurée passe par lui.",
)
def test_the_correction_balance_appears_in_detailed_mode_only(tmp_path: Path) -> None:
    archive = pages_zip(tmp_path, transcriptions=True)
    corpus = tmp_path / "c" / "corpus.yaml"
    dest = str(corpus.parent)
    assert main(["corpus", "import", "zip", str(archive), "--dest", dest]) == 0
    rapide, detaille = tmp_path / "rapide.html", tmp_path / "detaille.html"
    recette = ["run", str(corpus), "--recipe", "alto_corrige"]
    assert main([*recette, "-o", str(rapide)]) == 0
    assert main([
        "run", str(corpus), "--recipe", "alto_corrige", "--analyses", "toutes",
        "-o", str(detaille),
    ]) == 0
    assert "Bilan de correction" not in rapide.read_text(encoding="utf-8")
    html = detaille.read_text(encoding="utf-8")
    assert "Bilan de correction" in html and "Décisions du correcteur" in html


def test_the_detailed_mode_is_reachable_from_the_page(tmp_path: Path) -> None:
    """``POST /api/runs`` acceptait ``detailed_analyses`` ; la page n'avait pas
    la case que le CHANGELOG annonçait — la promesse de la recette y était donc
    hors d'atteinte."""
    from fastapi.testclient import TestClient

    from cinoc.interfaces.web.app import create_app

    page = TestClient(create_app(reports_dir=tmp_path)).get("/benchmark").text
    assert 'id="detailed-analyses"' in page
    js = (
        Path(__file__).resolve().parents[2]
        / "cinoc/interfaces/web/static/js/benchmark.js"
    ).read_text(encoding="utf-8")
    assert "cfg.detailed_analyses" in js
