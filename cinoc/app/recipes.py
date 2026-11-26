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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from cinoc.app.evaluation_views import EvaluationOptions, plan_evaluation
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.pipeline import INITIAL_STEP_ID, PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec

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
    #: Mode LLM/VLM que le rôle pose sur sa brique (réglage ``role``) : c'est
    #: lui qui fait qu'un même adapter lise l'image, ou le texte, ou les deux.
    mode: str | None = None


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

    def fournisseurs(mode: str) -> tuple[str, ...]:
        return tuple(sorted(providers_for_mode(mode)))
    return {
        "preprocess": Role((IMAGE,), (IMAGE,), ("preprocess",)),
        "ocr": Role(
            (IMAGE,),
            (RAW,),
            ("tesseract", "kraken", "pero", "calamari", "precomputed"),
        ),
        # Ordre = préférence : le premier est le défaut d'une recette qui ne
        # choisit pas. ``tesseract_layout`` ouvre la marche parce qu'il est le
        # seul à ne rien exiger — ni poids, ni SDK, ni adresse — et parce que
        # c'est le segmenteur de la chaîne NDNP de référence.
        #
        # La liste reste **écrite à la main** pour garder cet ordre, et elle est
        # confrontée au registre par ``tests/guardrails/test_recipe_roles.py`` :
        # deux segmenteurs enregistrés cette semaine n'y étaient jamais arrivés,
        # et le catalogue ne proposait que des briques inexécutables sur une
        # machine nue.
        "segmenter": Role(
            (IMAGE,),
            (LAYOUT,),
            (
                "tesseract_layout",
                "doclayout_yolo",
                "pp_doclayout",
                "remote_segmenter",
                # Dernier : il ne segmente rien lui-même, il *branche* ce qu'on
                # lui nomme. Utile partout, défaut nulle part — et réservé à la
                # CLI (``CLI_ONLY_KINDS``), donc jamais proposé par le web.
                "cli_layout",
                "ocrd",
            ),
        ),
        "alto_source": Role((IMAGE,), (LAYOUT,), ("alto_source",)),
        # ``tesseract_layout`` d'abord : il rend un **sous-layout**, donc le
        # fan-out greffe de vraies lignes. Les reconnaisseurs qui ne rendent que
        # du texte plat donnent une ligne par bloc — correct, mais une page de
        # trois blocs y perd ses vingt lignes.
        "region_recognizer": Role(
            (LAYOUT, IMAGE),
            (LAYOUT,),
            ("tesseract_layout", "tesseract", "kraken"),
            fanout=True,
        ),
        "reading_order": Role((LAYOUT,), (LAYOUT,), ("reading_order",)),
        "structured_correction": Role(
            (LAYOUT,), (LAYOUT, CORR, ArtifactType.DECISIONS), ("saknussemm",)
        ),
        "projection": Role((LAYOUT,), (RAW,), ("layout_to_text",)),
        "alto_export": Role((LAYOUT,), (ALTO,), ("alto_assembler",)),
        "page_export": Role((LAYOUT,), (PAGE,), ("page_assembler",)),
        # Les quatre modes que déclarent les adapters LLM/VLM (``llm_modes``),
        # chacun un rôle : sans ``zero_shot`` ni ``text_and_image``, une recette
        # ne pouvait pas décrire ce que le composeur décrit déjà (D-258).
        "correction": Role(
            (RAW,), (CORR,), fournisseurs("text_only"), mode="text_only"
        ),
        "refine": Role((CORR,), (CORR,), fournisseurs("refine"), mode="refine"),
        # Le VLM lit la page : transcription directe, sans OCR amont.
        "zero_shot": Role(
            (IMAGE,), (RAW,), fournisseurs("zero_shot"), mode="zero_shot"
        ),
        # Le VLM corrige le texte de l'OCR **en voyant l'image** : le texte vient
        # de l'étape précédente, l'image de l'entrée initiale.
        "text_and_image": Role(
            (RAW, IMAGE),
            (CORR,),
            fournisseurs("text_and_image"),
            mode="text_and_image",
        ),
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


_Nom = Annotated[str, StringConstraints(min_length=1, max_length=64)]
_Valeur = Annotated[str, StringConstraints(max_length=4096)] | int | float | bool
Settings = dict[str, dict[str, str | int | float | bool]]


class RecipeEntry(BaseModel):
    """Une entrée de la file : une recette, ses briques choisies, ses réglages.

    Ce que la page empile et que ``plan_recipe_run`` assemble en **un** run :
    plusieurs entrées se comparent comme les concurrents du composeur. Les
    réglages ne sont pas filtrés ici — ``check_spec_settings`` les confronte à la
    déclaration de chaque brique, comme pour une spec déposée.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recipe: _Nom
    #: Brique retenue par étape (``{"ocr": "kraken"}``). Absente → le défaut.
    choices: dict[_Nom, _Nom] = Field(default_factory=dict, max_length=32)
    #: Réglages par étape (``{"ocr": {"model": "…"}}``), ajoutés à ceux de la
    #: recette.
    params: dict[_Nom, dict[_Nom, _Valeur]] = Field(
        default_factory=dict, max_length=32
    )


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
    for quoi, cles in (("choix", choisies), ("réglages", reglages)):
        inconnues = sorted(set(cles) - {s.id for s in recipe.steps})
        if inconnues:
            raise RecipeError(
                f"recette {recipe.name!r} : {quoi} pour des étapes inconnues "
                f"{inconnues} (étapes : {[s.id for s in recipe.steps]})."
            )

    etapes: list[PipelineStep] = []
    kwargs: dict[str, dict[str, str | int | float | bool]] = {}
    precedente: str | None = None
    for step in recipe.steps:
        role = roles()[step.role]
        brique = choisies.get(step.id) or recipe.brique_de(step)
        # La brique fixée par l'auteur peut sortir du rôle ; celle d'un choix,
        # jamais — sinon un client remplacerait un OCR fixé par un correcteur.
        if role.briques and brique not in role.briques and brique != step.brick:
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
        reglage = {
            **_identite(brique, step.id, role.mode),
            **step.params,
            **reglages.get(step.id, {}),
        }
        kwargs[nom] = reglage
        precedente = step.id

    spec = PipelineSpec(
        name=recipe.name,
        initial_inputs=(ArtifactType.IMAGE,),
        steps=tuple(etapes),
    )
    return spec, kwargs


def _identite(
    brique: str, step_id: str, mode: str | None
) -> dict[str, str | int | float | bool]:
    """Le libellé d'instance et le mode LLM que la recette pose — **si la brique
    les déclare** : un réglage posé sur une brique qui ne le lit pas est refusé
    (D14), pas ignoré. ``precomputed`` se nomme par ``source_label`` : il rejoue
    donc ``<doc>.<étape>.txt``. Une brique sans déclaration (module tiers)
    reçoit le libellé, par convention."""
    from cinoc.app.modules.registry import socle_params  # noqa: PLC0415

    declares = socle_params(brique)
    noms = None if declares is None else {p.name for p in declares}
    identite: dict[str, str | int | float | bool] = {}
    if noms is None or "label" in noms:
        identite["label"] = step_id
    elif "source_label" in noms:
        identite["source_label"] = step_id
    if mode is not None and (noms is None or "role" in noms):
        identite["role"] = mode
    return identite


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
    écraseraient ceux de la première. Notation : ``plan_evaluation`` (D-297).
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
        )
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


def recipe_entries(
    names: Sequence[str],
    *,
    bricks: Sequence[str] = (),
    settings: Sequence[str] = (),
) -> tuple[RecipeEntry, ...]:
    """La file d'une ligne de commande (``--recipe``, ``--brick``, ``--set``).

    ``[N:]étape=brique`` et ``[N:]étape.réglage=valeur`` (valeur lue comme en
    YAML : ``300`` est un entier). Sans ``N:``, chaque recette qui a l'étape ;
    ``N:`` vise la N-ième. Une étape qu'aucune recette visée ne porte est
    refusée — un réglage lu par personne serait ignoré en silence. Le reste est
    vérifié comme pour la page (``plan_recipe_run``, ``check_spec_settings``).
    """
    if not names:
        raise RecipeError("file de recettes : au moins une recette requise.")
    recettes = [recipe_by_name(nom) for nom in names]
    choix: list[dict[str, str]] = [{} for _ in recettes]
    reglages: list[Settings] = [{} for _ in recettes]
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
    return tuple(
        RecipeEntry(recipe=nom, choices=choix[i], params=reglages[i])
        for i, nom in enumerate(names)
    )


def _affectation(texte: str, quoi: str, n: int) -> tuple[list[int], str, str]:
    """``[N:]clé=valeur`` → (rangs, clé, valeur) ; rang lu avant le ``=``."""
    tete, egal, valeur = texte.partition("=")
    rang, deux_points, cle = tete.rpartition(":")
    if not egal or not cle:
        raise RecipeError(f"{quoi} {texte!r} : forme attendue [N:]clé=valeur.")
    if not deux_points:
        return list(range(n)), cle, valeur
    if not rang.isdigit() or not 1 <= int(rang) <= n:
        raise RecipeError(
            f"{quoi} {texte!r} : rang {rang!r} hors de la file (1 à {n})."
        )
    return [int(rang) - 1], cle, valeur


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


def spec_for_corpus(document: str, corpus: CorpusSpec, *, run_id: str) -> RunSpec:
    """Lit une spec **déposée** et la lie au corpus fourni par l'appelant.

    **Le corpus de la spec est écarté avant même la validation.** Une spec porte
    des URI de fichiers ; les accepter d'un client ferait d'un lanceur web un
    lecteur de disque à distance. La spec décrit donc les pipelines et
    l'évaluation ; le corpus, c'est l'appelant qui le fournit — et le résolveur
    de chemins ne voit jamais une URI choisie par le client.

    C'est ici, en couche ``app``, que cette décision doit vivre : un transport
    qui l'oublierait rouvrirait la porte sans qu'aucun test ne le voie.
    """
    try:
        brut = yaml.safe_load(document)
    except yaml.YAMLError as exc:
        raise RecipeError(f"spec illisible : {exc}") from exc
    if not isinstance(brut, dict):
        raise RecipeError("spec : un objet est attendu à la racine.")
    brut.pop("corpus", None)
    brut["corpus"] = corpus.model_dump(mode="json")
    brut["run_id"] = run_id
    try:
        return RunSpec.model_validate(brut)
    except ValidationError as exc:
        raise RecipeError(f"spec invalide : {exc}") from exc


def referenced_kinds(spec: RunSpec) -> set[str]:
    """Les ``kind`` de briques qu'une spec met en jeu.

    Le nom d'adapter suit la convention ``<kind>:<label>`` : c'est ce qui permet
    d'appliquer à une spec **arbitraire** les mêmes gardes qu'à un concurrent du
    composeur, sans avoir à comprendre la spec.
    """
    return {
        etape.adapter_name.split(":", 1)[0]
        for pipeline in spec.pipelines
        for etape in pipeline.steps
    }


__all__ = [
    "RECIPES_DIR",
    "Recipe",
    "RecipeEntry",
    "RecipeError",
    "RecipeStep",
    "Role",
    "describe",
    "load_recipes",
    "plan_from_recipe",
    "plan_recipe_run",
    "referenced_kinds",
    "spec_for_corpus",
    "recipe_by_name",
    "recipe_entries",
    "roles",
]
