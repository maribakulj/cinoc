"""Le catalogue de recettes tel que la page le reçoit, et ce qu'il promet.

Une recette affichée doit **se construire** : une forme qu'on peut choisir puis
qui tombe dans le job sur un nom de module mal formé est un piège publié. Le
premier test le vérifie pour **toutes** les recettes livrées, réglages requis
remplis — c'est lui qui a montré que ``presse_ancienne`` et ``alto_corrige``
nommaient des briques sans libellé (``tesseract_layout:seg``,
``alto_source:source``) que le registre refusait.
"""

from __future__ import annotations

import pytest

from cinoc.app.engines import CLI_ONLY_KINDS, EngineStatus
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.modules.registry import check_spec_settings, socle_params
from cinoc.app.recipe_catalog import ROLE_LABELS, recipe_catalog
from cinoc.app.recipes import (
    RecipeEntry,
    RecipeError,
    load_recipes,
    plan_from_recipe,
    plan_recipe_run,
    recipe_by_name,
    roles,
)
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef

_CORPUS = CorpusSpec(
    name="c", documents=(DocumentRef(id="d", image_uri="d.png", ground_truths=()),)
)
_VALEURS: dict[str, str | int | float | bool] = {
    "str": "m",
    "int": 1,
    "float": 1.0,
    "bool": True,
}


def _requis(recette: str) -> dict[str, dict[str, str | int | float | bool]]:
    """Les réglages **requis** de chaque étape, remplis d'une valeur du bon
    type — ce que la page demande à l'utilisateur, et rien d'autre."""
    spec, _ = plan_from_recipe(recipe_by_name(recette))
    out: dict[str, dict[str, str | int | float | bool]] = {}
    for etape in spec.steps:
        declares = socle_params(etape.adapter_name.split(":", 1)[0]) or ()
        requis = {
            p.name: _VALEURS[p.type]
            for p in declares
            if p.required and p.name not in {"label", "role", "source_label"}
        }
        if requis:
            out[etape.id] = requis
    return out


@pytest.mark.parametrize("recette", [r.name for r in load_recipes()])
def test_every_shipped_recipe_builds_and_passes_the_settings_check(
    recette: str,
) -> None:
    """Chaque brique de chaque recette se construit, sans rien exécuter."""
    registre = ModuleRegistry()
    register_default_modules(registre)
    spec = plan_recipe_run(
        _CORPUS,
        (RecipeEntry(recipe=recette, params=_requis(recette)),),
        run_id="r",
    )
    check_spec_settings(spec, registre)


def test_two_steps_of_a_label_less_brick_are_two_instances() -> None:
    """``presse_ancienne`` segmente **et** reconnaît avec ``tesseract_layout`` :
    deux étapes, deux instances nommées — pas un nom que le module ne porte
    pas."""
    spec, kwargs = plan_from_recipe(recipe_by_name("presse_ancienne"))
    noms = {s.id: s.adapter_name for s in spec.steps}
    assert noms["seg"] == "tesseract_layout:seg"
    assert noms["reco"] == "tesseract_layout:reco"
    assert kwargs["tesseract_layout:seg"] == {"label": "seg"}


def test_a_fixed_brick_cannot_be_swapped_for_one_outside_the_role() -> None:
    """``vote_trois_moteurs`` fixe ses briques ; un choix les **remplace**, et
    ce choix-là doit rester dans le rôle — l'exemption valait pour la brique de
    l'auteur, pas pour celle du client."""
    with pytest.raises(RecipeError, match="n'est pas proposé"):
        plan_from_recipe(
            recipe_by_name("vote_trois_moteurs"), choices={"ocr_b": "openai"}
        )


def test_settings_for_an_unknown_step_are_refused() -> None:
    """Un réglage rangé sous une étape qui n'existe pas ne serait lu par
    personne : le dire, comme pour un choix."""
    with pytest.raises(RecipeError, match="étapes inconnues"):
        plan_from_recipe(
            recipe_by_name("ocr_simple"), params={"fantome": {"psm": 6}}
        )


def test_several_recipes_make_one_compared_run() -> None:
    """La file de la page : N recettes → **un** run, N pipelines comparés."""
    spec = plan_recipe_run(
        _CORPUS,
        (
            RecipeEntry(recipe="ocr_simple"),
            RecipeEntry(recipe="presse_ancienne"),
        ),
        run_id="r",
    )
    assert [p.name for p in spec.pipelines] == ["ocr_simple", "presse_ancienne"]
    noms = {v.name for v in spec.evaluation.views}
    assert {"texte", "structure"} <= noms


def test_the_same_step_shared_by_two_recipes_stays_one_instance() -> None:
    """``tesseract:ocr`` aux mêmes réglages dans deux recettes : une brique,
    pas deux — c'est la même lecture, elle n'a pas à être refaite."""
    spec = plan_recipe_run(
        _CORPUS,
        (RecipeEntry(recipe="ocr_simple"), RecipeEntry(recipe="ocr_simple")),
        run_id="r",
    )
    assert [p.name for p in spec.pipelines] == ["ocr_simple", "ocr_simple #2"]
    assert list(spec.adapter_kwargs) == ["tesseract:ocr"]


def test_the_same_recipe_twice_with_two_models_gives_two_instances() -> None:
    """Deux modèles sous la même recette : deux instances, chacune ses
    réglages. Sans cela, le second écraserait le premier et le rapport
    comparerait un modèle à lui-même."""
    spec = plan_recipe_run(
        _CORPUS,
        (
            RecipeEntry(
                recipe="vlm_seul", choices={"vlm": "openai"},
                params={"vlm": {"model": "a"}},
            ),
            RecipeEntry(
                recipe="vlm_seul", choices={"vlm": "openai"},
                params={"vlm": {"model": "b"}},
            ),
        ),
        run_id="r",
    )
    noms = [p.steps[0].adapter_name for p in spec.pipelines]
    assert noms[0] != noms[1]
    assert {spec.adapter_kwargs[n]["model"] for n in noms} == {"a", "b"}
    assert spec.adapter_kwargs[noms[1]]["label"] == noms[1].split(":", 1)[1]


def test_a_run_needs_at_least_one_recipe() -> None:
    with pytest.raises(RecipeError, match="au moins une recette"):
        plan_recipe_run(_CORPUS, (), run_id="r")


# --------------------------------------------------------------------------- #
# Le catalogue servi à la page
# --------------------------------------------------------------------------- #


def _statut(kind: str, ok: bool) -> EngineStatus:
    return EngineStatus(kind=kind, label=kind, available=ok, detail=f"{kind} ?")


def test_every_role_has_a_bilingual_name() -> None:
    """La page nomme l'étape par son rôle, en clair : un rôle sans libellé
    s'afficherait par son identifiant technique."""
    assert set(ROLE_LABELS) == set(roles())
    for fr, en in ROLE_LABELS.values():
        assert fr and en


def test_the_catalogue_describes_each_step_and_its_bricks() -> None:
    catalogue = recipe_catalog("fr", statuses=(_statut("kraken", False),))
    presse = next(c for c in catalogue if c["name"] == "presse_ancienne")
    etapes = presse["steps"]
    assert isinstance(etapes, list)
    reco = next(e for e in etapes if e["step"] == "reco")
    assert reco["role_label"] == ROLE_LABELS["region_recognizer"][0]
    assert reco["fanout"] is True
    assert reco["default"] == "tesseract_layout"
    kraken = next(b for b in reco["bricks"] if b["kind"] == "kraken")
    assert kraken["available"] is False
    assert kraken["detail"] == "kraken ?"
    assert any(p["name"] == "model" for p in kraken["required"])


def test_a_brick_reserved_to_the_cli_is_never_offered() -> None:
    catalogue = recipe_catalog("fr")
    offertes = {
        b["kind"]
        for c in catalogue
        for e in c["steps"]  # type: ignore[attr-defined]
        for b in e["bricks"]
    }
    assert not offertes & CLI_ONLY_KINDS


def test_public_mode_greys_out_what_it_would_refuse() -> None:
    """Le catalogue ne propose pas ce que le lanceur refuserait en 403."""
    catalogue = recipe_catalog("en", public_mode=True)
    simple = next(c for c in catalogue if c["name"] == "ocr_simple")
    briques = {b["kind"]: b for b in simple["steps"][0]["bricks"]}  # type: ignore[index]
    assert briques["kraken"]["available"] is False
    assert "public" in str(briques["kraken"]["detail"])
    presse = next(c for c in catalogue if c["name"] == "presse_ancienne")
    prep = presse["steps"][0]  # type: ignore[index]
    assert prep["role_label"] == ROLE_LABELS["preprocess"][1]
    assert all(not b["available"] for b in prep["bricks"])


def test_the_role_and_the_mode_are_never_asked_of_the_user() -> None:
    """``label``, ``role`` : la recette les pose — la page ne les demande pas."""
    catalogue = recipe_catalog("fr")
    demandes = {
        p["name"]
        for c in catalogue
        for e in c["steps"]  # type: ignore[attr-defined]
        for b in e["bricks"]
        for p in b["required"]
    }
    assert not demandes & {"label", "role", "source_label"}
    assert "model" in demandes
