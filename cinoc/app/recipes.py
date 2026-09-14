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
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
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


def default_evaluation(pipeline: PipelineSpec) -> EvaluationSpec:
    """Vues d'évaluation déduites de ce que le pipeline **produit réellement**.

    Une recette décrit une forme, pas une façon de la noter. Plutôt que d'imposer
    une vue fixe — qui serait vide sur la moitié des recettes — on regarde les
    types de sortie : du texte se note en texte, une mise en page en structure,
    des entités en entités. Un type qu'aucune étape ne produit ne donne pas de
    vue : une vue vide vaut moins que pas de vue.
    """
    produits = {
        t for etape in pipeline.steps for t in etape.output_types
    }
    vues: list[EvaluationView] = []
    candidats_texte = produits & {RAW, CORR}
    if candidats_texte:
        vues.append(
            EvaluationView(
                name="texte",
                candidate_types=frozenset(candidats_texte),
                metric_names=("cer", "wer"),
            )
        )
    if LAYOUT in produits:
        vues.append(
            EvaluationView(
                name="structure",
                candidate_types=frozenset({LAYOUT}),
                metric_names=("region_cer", "reading_order_tau"),
            )
        )
    if ENTITIES in produits:
        vues.append(
            EvaluationView(
                name="entites",
                candidate_types=frozenset({ENTITIES}),
                metric_names=("ner_f1",),
            )
        )
    return EvaluationSpec(views=tuple(vues))


def plan_recipe_run(
    corpus: CorpusSpec,
    recipe_name: str,
    *,
    run_id: str,
    choices: Mapping[str, str] | None = None,
    params: Mapping[str, Mapping[str, str | int | float | bool]] | None = None,
) -> RunSpec:
    """``RunSpec`` complet d'une recette, sur un corpus donné.

    Assembler une spec est un acte de la couche ``app`` : les feuilles de
    transport (CLI, web) choisissent la recette et le corpus, jamais la forme du
    résultat. Un garde-fou d'architecture le vérifie.
    """
    recette = recipe_by_name(recipe_name)
    pipeline, kwargs = plan_from_recipe(recette, choices=choices, params=params)
    return RunSpec(
        corpus=corpus,
        pipelines=(pipeline,),
        evaluation=default_evaluation(pipeline),
        adapter_kwargs=kwargs,
        run_id=run_id,
    )


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


def recipe_catalog(lang: str = "fr") -> list[dict[str, object]]:
    """Catalogue des recettes, prêt à afficher : forme, intention, choix restants.

    Vit en couche ``app`` et non dans le routeur : c'est la **même** donnée que
    montre ``cinoc list recipes``, et deux transports d'un même catalogue ne
    doivent pas le décrire différemment.
    """
    table = roles()
    langue = "en" if lang == "en" else "fr"
    sorties: list[dict[str, object]] = []
    for recette in load_recipes():
        pipeline, _ = plan_from_recipe(recette)
        sorties.append(
            {
                "name": recette.name,
                "title": describe(recette, langue),
                "description": recette.description.get(langue, ""),
                "shape": [etape.kind for etape in pipeline.steps],
                "choices": [
                    {"step": e.id, "bricks": list(table[e.role].briques)}
                    for e in recette.steps
                    if len(table[e.role].briques) > 1
                ],
            }
        )
    return sorties


__all__ = [
    "RECIPES_DIR",
    "Recipe",
    "RecipeError",
    "RecipeStep",
    "Role",
    "default_evaluation",
    "describe",
    "load_recipes",
    "plan_from_recipe",
    "recipe_catalog",
    "plan_recipe_run",
    "referenced_kinds",
    "spec_for_corpus",
    "recipe_by_name",
    "roles",
]
