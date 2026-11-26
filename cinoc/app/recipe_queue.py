"""La **file** de recettes : N entrées → un ``RunSpec`` (couche 6).

Le seul constructeur de pipeline du produit (D-298). La page empile des entrées
— une recette, ses briques, ses réglages, ses étapes facultatives —, la ligne de
commande les lit sur ``--recipe``/``--brick``/``--set``/``--with``, et les deux
appellent :func:`plan_recipe_run`. ``cinoc hybrid`` et ``cinoc correct`` aussi :
une transcription hybride et une correction d'ALTO sont des recettes
(``segmentation_puis_lecture``, ``alto_corrige``), pas des formes de run à part.

``recipes.py`` décrit le langage (rôles, YAML, une recette → un pipeline) ; ce
module en assemble plusieurs dans un run, et c'est ici que se règlent ce qui
dépend de la file entière : instances partagées ou distinguées, noms uniques,
notation commune, et le piège d'un corpus dont la vérité terrain est l'ALTO
même qu'on corrige.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from cinoc.app.alto_corpus import ground_truth_is_its_own_source
from cinoc.app.evaluation_views import EvaluationOptions, plan_evaluation
from cinoc.app.recipes import (
    Recipe,
    RecipeError,
    Settings,
    plan_from_recipe,
    recipe_by_name,
)
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec

_Nom = Annotated[str, StringConstraints(min_length=1, max_length=64)]
_Valeur = Annotated[str, StringConstraints(max_length=8000)] | int | float | bool


class RecipeEntry(BaseModel):
    """Une entrée de la file : une recette, ses briques choisies, ses réglages.

    Ce que la page empile et que ``plan_recipe_run`` assemble en **un** run :
    plusieurs entrées se comparent dans le même rapport. Les réglages ne sont
    pas filtrés ici — ``check_spec_settings`` les confronte à la déclaration de
    chaque brique, comme pour une spec déposée.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recipe: _Nom
    #: Brique retenue par étape (``{"ocr": "kraken"}``). Absente → le défaut.
    choices: dict[_Nom, _Nom] = Field(default_factory=dict, max_length=32)
    #: Réglages par étape (``{"ocr": {"model": "…"}}``), ajoutés à ceux de la
    #: recette. Un prompt libre y tient (8 000 caractères, comme au composeur).
    params: dict[_Nom, dict[_Nom, _Valeur]] = Field(
        default_factory=dict, max_length=32
    )
    #: Étapes **facultatives** retenues (``("ner",)``, ``("alto",)``).
    optional: tuple[_Nom, ...] = Field(default=(), max_length=16)


def plan_recipe_run(
    corpus: CorpusSpec,
    entries: Sequence[RecipeEntry],
    *,
    run_id: str | None,
    options: EvaluationOptions | None = None,
) -> RunSpec:
    """``RunSpec`` d'une **file** de recettes, sur un corpus donné : un run, un
    pipeline par entrée, comparés dans le même rapport.

    Assembler une spec est un acte de la couche ``app`` : les feuilles de
    transport (CLI, web) choisissent les recettes et le corpus, jamais la forme
    du résultat. Un garde-fou d'architecture le vérifie.

    Deux entrées qui emploient la **même** brique aux **mêmes** réglages la
    partagent (une lecture, pas deux) ; aux réglages différents — deux modèles
    sous ``vlm_seul`` —, la seconde prend un libellé à part, sinon ses réglages
    écraseraient ceux de la première. Deux pipelines au même nom (mêmes
    briques, mêmes modèles) se départagent en ``#n``. Notation :
    ``plan_evaluation`` (D-297).
    """
    if not entries:
        raise RecipeError("file de recettes : au moins une recette requise.")
    pipelines: list[PipelineSpec] = []
    kwargs: Settings = {}
    vus: dict[str, int] = {}
    for rang, entree in enumerate(entries, start=1):
        pipeline, reglages = plan_from_recipe(
            recipe_by_name(entree.recipe),
            choices=entree.choices,
            params=entree.params,
            optional=entree.optional,
        )
        _source_sans_reference(pipeline, reglages, corpus)
        pipeline = _sans_collision(pipeline, reglages, kwargs, rang)
        vus[pipeline.name] = vus.get(pipeline.name, 0) + 1
        if vus[pipeline.name] > 1:
            pipeline = pipeline.model_copy(
                update={"name": f"{pipeline.name} #{vus[pipeline.name]}"}
            )
        pipelines.append(pipeline)
    try:
        notation = plan_evaluation(pipelines, corpus, options)
    except CinocError as exc:
        raise RecipeError(str(exc)) from exc
    return RunSpec(
        corpus=corpus,
        pipelines=tuple(pipelines),
        evaluation=notation.evaluation,
        adapter_kwargs=kwargs,
        run_id=run_id,
        metadata=notation.metadata,
    )


def _source_sans_reference(
    pipeline: PipelineSpec, reglages: Settings, corpus: CorpusSpec
) -> None:
    """Refuse de corriger l'ALTO **dont la vérité terrain est extraite**.

    Un corpus déposé en images + ALTO, sans transcription à part, voit sa vérité
    terrain dérivée de cet ALTO : le correcteur partirait du texte auquel on le
    compare, et le CER vaudrait zéro par construction — un verdict inversé qui
    ressemble à un excellent résultat. Seule issue : lire l'OCR d'ailleurs
    (``ocr_sidecar``). La règle vit ici, pour toute entrée — la page, la CLI.
    """
    for etape in pipeline.steps:
        if etape.adapter_name.split(":", 1)[0] != "alto_source":
            continue
        if not reglages[etape.adapter_name].get("ocr_sidecar") and (
            ground_truth_is_its_own_source(corpus)
        ):
            raise RecipeError(
                "la vérité terrain de ce corpus est extraite de son propre "
                "ALTO : le correcteur partirait du texte auquel on le compare, "
                "et le CER vaudrait zéro par construction. Dépose une "
                "transcription à part (<nom>.gt.txt) à côté de chaque ALTO."
            )


def recipe_entries(
    names: Sequence[str],
    *,
    bricks: Sequence[str] = (),
    settings: Sequence[str] = (),
    optional: Sequence[str] = (),
) -> tuple[RecipeEntry, ...]:
    """La file d'une ligne de commande (``--recipe``, ``--brick``, ``--set``,
    ``--with``).

    ``[N:]étape=brique``, ``[N:]étape.réglage=valeur`` (valeur lue comme en
    YAML : ``300`` est un entier) et ``[N:]étape`` (une étape facultative
    retenue). Sans ``N:``, chaque recette qui a l'étape ; ``N:`` vise la N-ième.
    Une étape qu'aucune recette visée ne porte est refusée — un réglage lu par
    personne serait ignoré en silence. Le reste est vérifié comme pour la page
    (``plan_recipe_run``, ``check_spec_settings``).
    """
    if not names:
        raise RecipeError("file de recettes : au moins une recette requise.")
    recettes = [recipe_by_name(nom) for nom in names]
    choix: list[dict[str, str]] = [{} for _ in recettes]
    reglages: list[Settings] = [{} for _ in recettes]
    retenues: list[list[str]] = [[] for _ in recettes]
    for texte in bricks:
        rangs, etape, brique = _affectation(texte, "--brick", len(recettes))
        for i in _portees(recettes, rangs, etape, f"--brick {texte!r}"):
            choix[i][etape] = brique
    for texte in settings:
        rangs, cle, brut = _affectation(texte, "--set", len(recettes))
        etape, point, reglage = cle.partition(".")
        if not point or not reglage:
            raise RecipeError(
                f"--set {texte!r} : forme attendue [N:]étape.réglage=valeur."
            )
        valeur = yaml.safe_load(brut) if brut.strip() else ""
        if not isinstance(valeur, (str, int, float, bool)):
            raise RecipeError(f"--set {texte!r} : une valeur simple est attendue.")
        for i in _portees(recettes, rangs, etape, f"--set {texte!r}"):
            reglages[i].setdefault(etape, {})[reglage] = valeur
    for texte in optional:
        rangs, etape = _rang(texte, "--with", len(recettes))
        for i in _portees(recettes, rangs, etape, f"--with {texte!r}"):
            retenues[i].append(etape)
    return tuple(
        RecipeEntry(
            recipe=nom,
            choices=choix[i],
            params=reglages[i],
            optional=tuple(retenues[i]),
        )
        for i, nom in enumerate(names)
    )


def _affectation(texte: str, quoi: str, n: int) -> tuple[list[int], str, str]:
    """``[N:]clé=valeur`` → (rangs, clé, valeur) ; rang lu avant le ``=``."""
    tete, egal, valeur = texte.partition("=")
    if not egal:
        raise RecipeError(f"{quoi} {texte!r} : forme attendue [N:]clé=valeur.")
    rangs, cle = _rang(tete, quoi, n)
    return rangs, cle, valeur


def _rang(texte: str, quoi: str, n: int) -> tuple[list[int], str]:
    """``[N:]clé`` → (rangs visés, clé) ; sans rang, toute la file."""
    rang, deux_points, cle = texte.rpartition(":")
    if not cle:
        raise RecipeError(f"{quoi} {texte!r} : forme attendue [N:]clé.")
    if not deux_points:
        return list(range(n)), cle
    if not rang.isdigit() or not 1 <= int(rang) <= n:
        raise RecipeError(
            f"{quoi} {texte!r} : rang {rang!r} hors de la file (1 à {n})."
        )
    return [int(rang) - 1], cle


def _portees(
    recettes: Sequence[Recipe], rangs: list[int], etape: str, ou: str
) -> list[int]:
    """Les recettes visées qui ont l'étape ; aucune → refus nommé."""
    portees = [i for i in rangs if etape in {s.id for s in recettes[i].steps}]
    if not portees:
        connues = sorted({s.id for i in rangs for s in recettes[i].steps})
        raise RecipeError(
            f"{ou} : aucune recette visée n'a d'étape {etape!r} "
            f"(étapes : {connues})."
        )
    return portees


def _sans_collision(
    pipeline: PipelineSpec, reglages: Settings, pris: Settings, rang: int
) -> PipelineSpec:
    """Range les réglages d'un pipeline dans ``pris`` ; une brique déjà prise
    sous d'**autres** réglages est renommée ``<kind>:<libellé>-<rang>``."""
    etapes: list[PipelineStep] = []
    for etape in pipeline.steps:
        nom, reglage = etape.adapter_name, reglages[etape.adapter_name]
        if nom in pris and pris[nom] != reglage:
            libelle = reglage.get("label")
            if not isinstance(libelle, str):
                raise RecipeError(
                    f"file de recettes : la brique {nom!r} revient avec "
                    "d'autres réglages, et ne porte pas de libellé qui "
                    "permettrait de la distinguer."
                )
            reglage = {**reglage, "label": f"{libelle}-{rang}"}
            nom = f"{nom.split(':', 1)[0]}:{reglage['label']}"
            etape = etape.model_copy(update={"adapter_name": nom})
        pris[nom] = reglage
        etapes.append(etape)
    return pipeline.model_copy(update={"steps": tuple(etapes)})


__all__ = ["RecipeEntry", "plan_recipe_run", "recipe_entries"]
