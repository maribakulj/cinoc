"""Recettes : des formes de pipeline **nommées**, choisies plutôt que composées.

Le graphe typé de Cinoc admet des centaines de formes de pipeline valides. Elles
ne rentrent pas dans un formulaire, et un éditeur de nœuds serait à la fois lourd
à construire et hostile à l'usage. Une **recette** est la troisième voie : une
forme éprouvée, nommée par son intention — « presse ancienne multi-colonnes » —
dont l'utilisateur ne remplit que les briques.

Une recette porte son intention en clair, ce que douze cases à cocher ne feront
jamais. Et une dizaine bien choisies couvre l'essentiel des usages réels, parce
que les formes possibles ne sont pas équiprobables.

**C'est de la donnée, pas de la surface exécutable** — au même titre que les
profils de normalisation et les prompts curés. Une recette se lit dans un YAML
versionné ; en ajouter une ne demande pas de toucher au code.

Les **rôles** ci-dessous sont ce qui empêche une recette de décrire une spec
incohérente : une recette nomme des rôles, et c'est le builder qui connaît leur
signature typée. Une recette ne peut donc pas se tromper de types — elle peut
seulement nommer un rôle qui n'existe pas, ce qui se voit au chargement.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.errors import CinocError
from cinoc.domain.pipeline import INITIAL_STEP_ID, PipelineSpec, PipelineStep

RECIPES_DIR = Path(__file__).resolve().parent.parent / "recipes"


class RecipeError(CinocError):
    """Recette illisible, incohérente, ou nommant un rôle inconnu."""


@dataclass(frozen=True)
class Role:
    """Signature typée d'un rôle. C'est elle qui rend une recette sûre."""

    entrees: tuple[ArtifactType, ...]
    sorties: tuple[ArtifactType, ...]
    #: Briques proposées pour ce rôle, la première étant le défaut.
    briques: tuple[str, ...] = ()
    #: Reconnaissance par région : l'exécuteur démultiplie l'étape par bloc.
    fanout: bool = False
    #: Entrées supplémentaires toujours disponibles (l'image initiale).
    aussi: tuple[ArtifactType, ...] = field(default_factory=tuple)


IMAGE = ArtifactType.IMAGE
RAW = ArtifactType.RAW_TEXT
CORR = ArtifactType.CORRECTED_TEXT
LAYOUT, ALTO, PAGE = ArtifactType.LAYOUT, ArtifactType.ALTO_XML, ArtifactType.PAGE_XML
ENTITIES = ArtifactType.ENTITIES

def roles() -> Mapping[str, Role]:
    """Rôles connus des recettes, avec les briques proposées pour chacun.

    **Fonction et non constante** : les fournisseurs LLM/VLM sont lus sur les
    adapters à chaque appel (``providers_for_mode``). Une table figée à l'import
    serait une liste parallèle de plus — le garde-fou des capacités l'a
    d'ailleurs attrapée ici même, en troisième récidive (D-239).

    Ajouter un rôle est un acte délibéré : c'est ce qui borne ce qu'une recette
    peut décrire.
    """
    from cinoc.app.engines import providers_for_mode  # noqa: PLC0415

    correcteurs = tuple(sorted(providers_for_mode("text_only")))
    affineurs = tuple(sorted(providers_for_mode("refine")))
    return {
        "preprocess": Role((IMAGE,), (IMAGE,), ("preprocess",)),
        "ocr": Role(
            (IMAGE,),
            (RAW,),
            ("tesseract", "kraken", "pero", "calamari", "precomputed"),
        ),
        "segmenter": Role((IMAGE,), (LAYOUT,), ("pp_doclayout", "remote_segmenter")),
        "alto_source": Role((IMAGE,), (LAYOUT,), ("alto_source",)),
        "region_recognizer": Role(
            (LAYOUT, IMAGE), (LAYOUT,), ("tesseract", "kraken"), fanout=True
        ),
        "reading_order": Role((LAYOUT,), (LAYOUT,), ("reading_order",)),
        "structured_correction": Role(
            (LAYOUT,), (LAYOUT, CORR, ArtifactType.DECISIONS), ("saknussemm",)
        ),
        "projection": Role((LAYOUT,), (RAW,), ("layout_to_text",)),
        "alto_export": Role((LAYOUT,), (ALTO,), ("alto_assembler",)),
        "page_export": Role((LAYOUT,), (PAGE,), ("page_assembler",)),
        "correction": Role((RAW,), (CORR,), correcteurs),
        "refine": Role((CORR,), (CORR,), affineurs),
        "ner": Role((RAW,), (ENTITIES,), ("ner",)),
        "vote": Role((RAW,), (RAW,), ("vote",)),
    }


class RecipeStep(BaseModel):
    """Une étape de recette : un rôle, et de quoi la régler."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)
    #: Brique par défaut. Absente → la première du rôle.
    brick: str | None = Field(default=None, max_length=64)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)
    #: Étape dont cette étape prend son entrée principale. Absente → la
    #: précédente, ce qui décrit une chaîne — le cas courant.
    after: str | None = Field(default=None, max_length=64)
    #: Étapes que cette étape **fusionne**. Une fusion ne se décrit pas par
    #: ``after`` : le pool étant indexé par type, une seule source y survivrait.
    merge: tuple[str, ...] = ()


class Recipe(BaseModel):
    """Une forme de pipeline nommée par son intention."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    title: dict[str, str]
    description: dict[str, str]
    steps: tuple[RecipeStep, ...] = Field(min_length=1)

    def brique_de(self, step: RecipeStep) -> str:
        role = roles()[step.role]
        if step.brick:
            return step.brick
        if not role.briques:
            raise RecipeError(
                f"recette {self.name!r}, étape {step.id!r} : le rôle "
                f"{step.role!r} ne propose aucune brique par défaut."
            )
        return role.briques[0]


def load_recipes(directory: Path | None = None) -> tuple[Recipe, ...]:
    """Charge les recettes livrées, triées par nom (ordre stable)."""
    dossier = directory or RECIPES_DIR
    recettes: list[Recipe] = []
    for chemin in sorted(dossier.glob("*.yaml")):
        try:
            brut = yaml.safe_load(chemin.read_text(encoding="utf-8"))
            recette = Recipe.model_validate(brut)
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise RecipeError(f"recette illisible ({chemin.name}) : {exc}") from exc
        _valider(recette, chemin.name)
        recettes.append(recette)
    return tuple(recettes)


def _valider(recette: Recipe, fichier: str) -> None:
    """Refuse au chargement ce qui ne pourrait pas s'exécuter."""
    vus: set[str] = set()
    for step in recette.steps:
        if step.role not in roles():
            raise RecipeError(
                f"recette {fichier} : rôle {step.role!r} inconnu "
                f"(connus : {sorted(roles())})."
            )
        if step.id in vus:
            raise RecipeError(
                f"recette {fichier} : identifiant d'étape {step.id!r} répété."
            )
        for source in step.merge:
            if source not in vus:
                raise RecipeError(
                    f"recette {fichier} : l'étape {step.id!r} fusionne "
                    f"{source!r}, qui n'est pas déclarée avant elle."
                )
        if step.merge and step.after is not None:
            raise RecipeError(
                f"recette {fichier} : l'étape {step.id!r} déclare `after` et "
                "`merge` — une fusion nomme toutes ses sources, il n'y a pas "
                "d'entrée principale à désigner en plus."
            )
        if step.after is not None and step.after not in vus:
            raise RecipeError(
                f"recette {fichier} : l'étape {step.id!r} vient après "
                f"{step.after!r}, qui n'est pas déclarée avant elle."
            )
        vus.add(step.id)


def plan_from_recipe(
    recipe: Recipe,
    *,
    choices: Mapping[str, str] | None = None,
    params: Mapping[str, Mapping[str, str | int | float | bool]] | None = None,
) -> tuple[PipelineSpec, dict[str, dict[str, str | int | float | bool]]]:
    """Construit la ``PipelineSpec`` d'une recette, briques choisies.

    ``choices`` remplace la brique d'une étape (par identifiant d'étape) ;
    ``params`` ajoute ou remplace ses paramètres. Tout le reste — types, câblage,
    fan-out — vient du **rôle**, pas de la recette : c'est ce qui garantit qu'une
    recette ne peut pas décrire une spec mal typée.
    """
    choisies = dict(choices or {})
    reglages = {k: dict(v) for k, v in (params or {}).items()}
    inconnues = sorted(set(choisies) - {s.id for s in recipe.steps})
    if inconnues:
        raise RecipeError(
            f"recette {recipe.name!r} : choix pour des étapes inconnues "
            f"{inconnues} (étapes : {[s.id for s in recipe.steps]})."
        )

    etapes: list[PipelineStep] = []
    kwargs: dict[str, dict[str, str | int | float | bool]] = {}
    precedente: str | None = None
    for step in recipe.steps:
        role = roles()[step.role]
        brique = choisies.get(step.id) or recipe.brique_de(step)
        if role.briques and brique not in role.briques and not step.brick:
            raise RecipeError(
                f"recette {recipe.name!r}, étape {step.id!r} : {brique!r} n'est "
                f"pas proposé pour le rôle {step.role!r} "
                f"(attendu parmi {list(role.briques)})."
            )
        nom = f"{brique}:{step.id}"
        if step.merge:
            etapes.append(
                PipelineStep(
                    id=step.id,
                    kind=step.role,
                    adapter_name=nom,
                    input_types=role.entrees,
                    output_types=role.sorties,
                    merge_from=tuple(step.merge),
                )
            )
        else:
            source = step.after or precedente
            inputs_from = {
                t: (source if source and t is not IMAGE else INITIAL_STEP_ID)
                for t in role.entrees
            }
            etapes.append(
                PipelineStep(
                    id=step.id,
                    kind=step.role,
                    adapter_name=nom,
                    input_types=role.entrees,
                    output_types=role.sorties,
                    inputs_from=inputs_from,
                    fanout=role.fanout,
                    crop=role.fanout,
                )
            )
        reglage = {"label": step.id, **step.params, **reglages.get(step.id, {})}
        if step.role == "refine":
            reglage["role"] = "refine"
        kwargs[nom] = reglage
        precedente = step.id

    spec = PipelineSpec(
        name=recipe.name,
        initial_inputs=(ArtifactType.IMAGE,),
        steps=tuple(etapes),
    )
    return spec, kwargs


def recipe_by_name(nom: str, directory: Path | None = None) -> Recipe:
    """La recette portant ``nom``, ou une erreur qui liste les existantes."""
    recettes = load_recipes(directory)
    for recette in recettes:
        if recette.name == nom:
            return recette
    raise RecipeError(
        f"recette {nom!r} inconnue (connues : {[r.name for r in recettes]})."
    )


def describe(recipe: Recipe, lang: str = "fr") -> str:
    """Titre lisible d'une recette, dans la langue demandée (repli français)."""
    return recipe.title.get(lang) or recipe.title.get("fr") or recipe.name


__all__ = [
    "RECIPES_DIR",
    "Recipe",
    "RecipeError",
    "RecipeStep",
    "Role",
    "describe",
    "load_recipes",
    "plan_from_recipe",
    "recipe_by_name",
    "roles",
]
