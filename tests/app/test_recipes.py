"""Recettes : des formes nommées, et ce que le chargement refuse.

Une recette est de la **donnée**, au même titre que les profils de normalisation
et les prompts curés : en ajouter une ne demande pas de toucher au code. Ce qui
la rend sûre est ailleurs — elle nomme des **rôles**, et c'est le builder qui
connaît leur signature typée. Une recette ne peut donc pas décrire une spec mal
câblée ; elle peut seulement nommer un rôle qui n'existe pas, ce qui se voit au
chargement.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cinoc.app.recipes import (
    Recipe,
    RecipeError,
    describe,
    load_recipes,
    plan_from_recipe,
    recipe_by_name,
    roles,
)
from cinoc.domain.artifacts import ArtifactType


def _ecrire(tmp_path: Path, contenu: dict) -> Path:
    (tmp_path / f"{contenu['name']}.yaml").write_text(
        yaml.safe_dump(contenu, allow_unicode=True), encoding="utf-8"
    )
    return tmp_path


def _recette(**extra: object) -> dict:
    base = {
        "name": "essai",
        "title": {"fr": "Essai", "en": "Trial"},
        "description": {"fr": "…", "en": "…"},
        "steps": [{"id": "ocr", "role": "ocr"}],
    }
    base.update(extra)
    return base


# --------------------------------------------------------------------------- #
# Les recettes livrées
# --------------------------------------------------------------------------- #


def test_the_shipped_recipes_all_load_and_plan() -> None:
    """Une recette livrée qui ne se planifie pas serait un piège documenté."""
    recettes = load_recipes()
    assert recettes, "aucune recette livrée"
    for recette in recettes:
        spec, kwargs = plan_from_recipe(recette)
        assert spec.steps, f"{recette.name} : spec sans étape"
        assert set(kwargs) == {s.adapter_name for s in spec.steps}


def test_every_shipped_recipe_is_bilingual() -> None:
    """Le titre et la description existent en français et en anglais : une
    recette se choisit sur son intention, qui doit être lisible."""
    for recette in load_recipes():
        for champ in (recette.title, recette.description):
            assert {"fr", "en"} <= set(champ), f"{recette.name} : {champ}"


def test_the_baseline_recipe_is_a_single_step() -> None:
    """``ocr_simple`` est la référence contre laquelle les autres se mesurent :
    si elle se compliquait, il n'y aurait plus de ligne de base."""
    spec, _ = plan_from_recipe(recipe_by_name("ocr_simple"))
    assert len(spec.steps) == 1


def test_the_press_recipe_puts_the_order_before_the_projection() -> None:
    """L'ordre de lecture doit précéder la projection, sinon il ne sert à rien :
    c'est la projection qui le consomme."""
    spec, _ = plan_from_recipe(recipe_by_name("presse_ancienne"))
    kinds = [s.kind for s in spec.steps]
    assert kinds.index("reading_order") < kinds.index("projection")


def test_the_vote_recipe_actually_votes() -> None:
    """Une recette nommée « un vote » doit en contenir un.

    Écrite d'abord sans son étape de fusion, elle décrivait trois OCR dont
    seul le dernier aurait survécu au pool — le nom aurait menti.
    """
    spec, _ = plan_from_recipe(recipe_by_name("vote_trois_moteurs"))
    fusions = [s for s in spec.steps if s.merge_from]
    assert len(fusions) == 1
    assert len(fusions[0].merge_from) == 3


# --------------------------------------------------------------------------- #
# Ce que le rôle garantit
# --------------------------------------------------------------------------- #


def test_types_come_from_the_role_not_from_the_recipe() -> None:
    """Une recette ne déclare aucun type : c'est ce qui la rend incapable de
    décrire une spec mal typée."""
    spec, _ = plan_from_recipe(recipe_by_name("ocr_simple"))
    etape = spec.steps[0]
    assert etape.input_types == roles()["ocr"].entrees
    assert etape.output_types == roles()["ocr"].sorties


def test_a_region_recognizer_gets_fanout_without_saying_so() -> None:
    """Le fan-out vient du rôle : une recette ne peut pas l'oublier."""
    spec, _ = plan_from_recipe(recipe_by_name("presse_ancienne"))
    reco = next(s for s in spec.steps if s.kind == "region_recognizer")
    assert reco.fanout and reco.crop
    assert ArtifactType.IMAGE in reco.input_types


def test_a_chain_wires_each_step_to_the_previous_one() -> None:
    spec, _ = plan_from_recipe(recipe_by_name("ocr_puis_llm"))
    correction = spec.steps[1]
    assert correction.inputs_from[ArtifactType.RAW_TEXT] == "ocr"


# --------------------------------------------------------------------------- #
# Ce que le chargement refuse
# --------------------------------------------------------------------------- #


def test_an_unknown_role_is_refused(tmp_path: Path) -> None:
    dossier = _ecrire(tmp_path, _recette(steps=[{"id": "x", "role": "magie"}]))
    with pytest.raises(RecipeError, match="rôle 'magie' inconnu"):
        load_recipes(dossier)


def test_a_repeated_step_id_is_refused(tmp_path: Path) -> None:
    dossier = _ecrire(
        tmp_path,
        _recette(steps=[{"id": "a", "role": "ocr"}, {"id": "a", "role": "ocr"}]),
    )
    with pytest.raises(RecipeError, match="répété"):
        load_recipes(dossier)


def test_a_forward_reference_is_refused(tmp_path: Path) -> None:
    """Une étape ne peut pas venir après une étape qui n'existe pas encore."""
    dossier = _ecrire(
        tmp_path,
        _recette(
            steps=[
                {"id": "a", "role": "ocr"},
                {"id": "b", "role": "correction", "after": "plus_tard"},
            ]
        ),
    )
    with pytest.raises(RecipeError, match="n'est pas déclarée avant"):
        load_recipes(dossier)


def test_after_and_merge_together_are_refused(tmp_path: Path) -> None:
    """Une fusion nomme toutes ses sources : désigner en plus une entrée
    principale n'aurait pas de sens."""
    dossier = _ecrire(
        tmp_path,
        _recette(
            steps=[
                {"id": "a", "role": "ocr"},
                {"id": "b", "role": "ocr"},
                {"id": "f", "role": "vote", "after": "a", "merge": ["a", "b"]},
            ]
        ),
    )
    with pytest.raises(RecipeError, match="`after` et"):
        load_recipes(dossier)


def test_a_choice_for_an_unknown_step_is_refused() -> None:
    """Un choix qui ne s'applique à rien est silencieusement perdu : le dire."""
    with pytest.raises(RecipeError, match="étapes inconnues"):
        plan_from_recipe(recipe_by_name("ocr_simple"), choices={"fantome": "tesseract"})


def test_a_brick_outside_the_role_is_refused() -> None:
    """Choisir un correcteur comme moteur d'OCR produirait une spec absurde."""
    with pytest.raises(RecipeError, match="n'est pas proposé"):
        plan_from_recipe(recipe_by_name("ocr_simple"), choices={"ocr": "openai"})


def test_an_unknown_recipe_lists_the_known_ones() -> None:
    with pytest.raises(RecipeError, match="connues"):
        recipe_by_name("inexistante")


def test_the_title_falls_back_to_french() -> None:
    recette = Recipe.model_validate(_recette(title={"fr": "Essai"}))
    assert describe(recette, "en") == "Essai"
