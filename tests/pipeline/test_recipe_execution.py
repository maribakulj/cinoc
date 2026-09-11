"""Les recettes s'exécutent, elles ne se contentent pas de se décrire.

Une recette qui se planifie mais ne tourne pas serait le pire des deux mondes :
elle promet une forme éprouvée et livre une erreur au premier run. Ces tests
passent par le **vrai exécuteur**, avec la brique de rejeu — donc sans binaire,
sans clé et sans réseau, ce qui est aussi la condition pour qu'ils tournent
partout.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.recipes import plan_from_recipe, recipe_by_name
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.pipeline.executor import PipelineExecutor

#: Trois lectures qui se trompent **chacune ailleurs**, et dont **aucune**
#: n'est la bonne réponse : sans cette précaution, le test passerait parce qu'un
#: votant avait déjà raison, ce qui ne prouverait rien du vote.
LECTURES = {
    "ocr": "le soleil luiſoit",
    "ocr_a": "le soleil luiſoit",  # faute sur le 3ᵉ mot
    "ocr_b": "le solcil luisoit",  # faute sur le 2ᵉ
    "ocr_c": "lc soleil luisoit",  # faute sur le 1ᵉʳ
}


def _scene(tmp_path: Path) -> Artifact:
    """Une image factice et les sorties pré-calculées, nommées par étape.

    Le nom du rejeu **est** son ``source_label`` : les fichiers suivent donc les
    identifiants d'étape de la recette, pas l'inverse.
    """
    (tmp_path / "p1.png").write_bytes(b"\x89PNG stub")
    for etape, texte in LECTURES.items():
        (tmp_path / f"p1.{etape}.txt").write_text(texte, encoding="utf-8")
    return Artifact(
        id="i",
        document_id="p1",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p1.png"),
    )


def _executer(nom: str, etapes: tuple[str, ...], tmp_path: Path, ws: str) -> str:
    recette = recipe_by_name(nom)
    spec, kwargs = plan_from_recipe(
        recette,
        choices={e: "precomputed" for e in etapes},
        params={e: {"source_label": e} for e in etapes},
    )
    registre = ModuleRegistry()
    register_default_modules(registre)
    modules = {n: registre.build(n, k) for n, k in kwargs.items()}
    execution = PipelineExecutor(code_version="test").execute_document(
        spec,
        modules,
        document_id="p1",
        initial_inputs={ArtifactType.IMAGE: _scene(tmp_path)},
        workspace_uri=str(tmp_path / ws),
    )
    produit = execution.artifacts[ArtifactType.RAW_TEXT]
    assert produit.uri is not None
    return Path(produit.uri).read_text(encoding="utf-8")


def test_the_baseline_recipe_runs(tmp_path: Path) -> None:
    assert _executer("ocr_simple", ("ocr",), tmp_path, "ws1") == "le soleil luiſoit"


def test_the_vote_recipe_runs_and_beats_its_voters(tmp_path: Path) -> None:
    """La recette tient sa promesse : chacun se trompe une fois, pas la fusion.

    C'est le test qui relie les deux moitiés du travail — la fusion à N entrées
    (le contrat) et les recettes (l'ergonomie) : une forme nommée, choisie en un
    mot, qui produit un résultat qu'aucun de ses votants ne produit seul.
    """
    fusionne = _executer(
        "vote_trois_moteurs", ("ocr_a", "ocr_b", "ocr_c"), tmp_path, "ws2"
    )
    assert fusionne == "le soleil luisoit"
    for etape in ("ocr_a", "ocr_b", "ocr_c"):
        assert LECTURES[etape] != fusionne, f"{etape} aurait déjà la bonne réponse"
