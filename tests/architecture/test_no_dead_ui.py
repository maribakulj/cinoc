"""Garde-fou **anti-vide** : chaque option du composeur a un backend réel.

Le composeur (Banc d'essai) est le catalogue de recettes (``recipe_catalog``,
D-298) : pour chaque étape, les briques que son rôle propose, et leurs réglages
requis. Ce test verrouille mécaniquement qu'on **ne peut pas afficher une option
sans backend** :

1. toute brique offerte est un **builder enregistré** (constructible au runtime) ;
2. toute brique offerte, à son étape, les réglages requis remplis comme la page
   le demande, **se construit** (``check_spec_settings`` : la règle de
   ``cinoc run --check`` et du lanceur web).

Si un jour le catalogue et le registre divergent (option ajoutée côté UI sans
brique, réglage requis que la page ne demande pas), ce test casse — pas l'UI en
prod.
"""

from __future__ import annotations

from cinoc.app.modules.registry import (
    ModuleRegistry,
    check_spec_settings,
    register_default_modules,
)
from cinoc.app.recipe_catalog import recipe_catalog
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def _corpus() -> CorpusSpec:
    return CorpusSpec(name="t", documents=(DocumentRef(id="d", image_uri="d.png"),))


#: Ce qu'un utilisateur saisit dans un champ requis, par nom de réglage.
_SAISIE = {"endpoint": "https://segmenteur.example"}


def test_catalog_bricks_are_registered_builders() -> None:
    offered = {
        brick["kind"]
        for recipe in recipe_catalog()
        for step in recipe["steps"]  # type: ignore[attr-defined]
        for brick in step["bricks"]
    }
    missing = offered - set(_registry().kinds())
    assert not missing, f"briques offertes au composeur sans builder : {missing}"


def _requis(brick: dict[str, object]) -> dict[str, str]:
    return {
        str(p["name"]): _SAISIE.get(str(p["name"]), "m")
        for p in brick["params"]  # type: ignore[attr-defined]
        if p["required"]
    }


def test_every_catalog_option_builds_with_what_the_page_asks() -> None:
    """Chaque brique de chaque étape, les autres étapes à leur défaut : les
    réglages requis remplis partout, comme la page les demande."""
    registry = _registry()
    refus: list[str] = []
    for recipe in recipe_catalog():
        steps = recipe["steps"]
        defauts = {
            s["step"]: next(b for b in s["bricks"] if b["kind"] == s["default"])
            for s in steps  # type: ignore[attr-defined]
        }
        for step in steps:  # type: ignore[attr-defined]
            for brick in step["bricks"]:
                choisies = {**defauts, step["step"]: brick}
                reglages = {k: _requis(b) for k, b in choisies.items() if _requis(b)}
                entree = RecipeEntry(
                    recipe=str(recipe["name"]),
                    choices={step["step"]: brick["kind"]},
                    params=reglages,
                    optional=tuple(s["step"] for s in steps if s["optional"]),
                )
                try:
                    spec = plan_recipe_run(_corpus(), (entree,), run_id="r")
                    check_spec_settings(spec, registry)
                except Exception as exc:  # noqa: BLE001 — on collecte pour nommer
                    refus.append(
                        f"{recipe['name']}/{step['step']}={brick['kind']}: {exc}"
                    )
    assert not refus, "options du composeur sans backend :\n  " + "\n  ".join(refus)
