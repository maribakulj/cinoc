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
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.pipeline import INITIAL_STEP_ID, PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.formats import safe_load_yaml

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
    #: Mode LLM/VLM que le rôle pose sur sa brique (réglage ``role``) : c'est
    #: lui qui fait qu'un même adapter lise l'image, ou le texte, ou les deux.
    mode: str | None = None


IMAGE = ArtifactType.IMAGE
RAW = ArtifactType.RAW_TEXT
CORR = ArtifactType.CORRECTED_TEXT
LAYOUT, ALTO, PAGE = ArtifactType.LAYOUT, ArtifactType.ALTO_XML, ArtifactType.PAGE_XML
ENTITIES = ArtifactType.ENTITIES

#: Reconnaisseurs par région qui ne lisent **aucun pixel** : le rejeu lit un
#: texte figé par identifiant de région. Le découper exigerait Pillow et une
#: vraie image — ce que la démo et la CI n'ont pas — pour n'en rien faire.
_SANS_PIXELS = frozenset({"precomputed_region"})


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
    from cinoc.app.modules.registry import socle_ocr_engines  # noqa: PLC0415

    # Les moteurs OCR, lus sur le socle dans son ordre (= préférence) : la
    # liste tenue ici à la main en était la quatrième copie (D-301).
    ocr = socle_ocr_engines()

    def fournisseurs(mode: str) -> tuple[str, ...]:
        return tuple(sorted(providers_for_mode(mode)))
    return {
        "preprocess": Role((IMAGE,), (IMAGE,), ("preprocess",)),
        "ocr": Role((IMAGE,), (RAW,), (*ocr, "precomputed")),
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
                # Le rejeu d'une mise en page figée (``<doc>.layout.json``) :
                # comme ``precomputed`` pour l'OCR, il sert la démo, la CI, et
                # « segmenter une fois, comparer plusieurs lectures dessus ».
                "precomputed_layout",
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
        # trois blocs y perd ses vingt lignes. Tout OCR convient au bloc
        # découpé, et tout VLM qui sait transcrire une image : le mode
        # ``zero_shot`` n'est posé que sur les briques qui le déclarent.
        "region_recognizer": Role(
            (LAYOUT, IMAGE),
            (LAYOUT,),
            (
                "tesseract_layout", *ocr, "precomputed_region",
                *fournisseurs("zero_shot"),
            ),
            fanout=True,
            mode="zero_shot",
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
        # Les entités se lisent sur le texte le plus abouti : brut après un OCR,
        # corrigé après un LLM. Deux rôles, une brique — le pool est indexé par
        # type, une étape doit dire lequel elle lit.
        "ner": Role((RAW,), (ENTITIES,), ("ner",)),
        "ner_corrige": Role((CORR,), (ENTITIES,), ("ner",)),
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
    #: Étape **facultative** : absente du pipeline tant que l'entrée ne la
    #: retient pas (les entités nommées, l'export ALTO). Toujours une feuille :
    #: aucune étape ne la suit ni ne la fusionne, et la chaîne implicite
    #: (``after`` absent) l'enjambe — l'ôter ne peut rien débrancher.
    optional: bool = False


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


#: Réglages par nom d'instance (``adapter_kwargs`` d'une spec).
Settings = dict[str, dict[str, str | int | float | bool]]


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
    facultatives: set[str] = set()
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
        suivies = {*step.merge, *((step.after,) if step.after else ())}
        if suivies & facultatives:
            raise RecipeError(
                f"recette {fichier} : l'étape {step.id!r} dépend d'une étape "
                f"facultative ({sorted(suivies & facultatives)}) — une étape "
                "facultative est une feuille, l'ôter ne doit rien débrancher."
            )
        vus.add(step.id)
        if step.optional:
            facultatives.add(step.id)


def plan_from_recipe(
    recipe: Recipe,
    *,
    choices: Mapping[str, str] | None = None,
    params: Mapping[str, Mapping[str, str | int | float | bool]] | None = None,
    optional: Sequence[str] = (),
) -> tuple[PipelineSpec, Settings]:
    """Construit la ``PipelineSpec`` d'une recette, briques choisies.

    ``choices`` remplace la brique d'une étape (par identifiant d'étape) ;
    ``params`` ajoute ou remplace ses paramètres ; ``optional`` retient des
    étapes facultatives. Tout le reste — types, câblage, fan-out — vient du
    **rôle**, pas de la recette : c'est ce qui garantit qu'une recette ne peut
    pas décrire une spec mal typée. Le **nom** du pipeline vient de ce qui a
    été construit (:func:`pipeline_name`), jamais du chemin qui l'a demandé.
    """
    choisies = dict(choices or {})
    reglages = {k: dict(v) for k, v in (params or {}).items()}
    retenues = set(optional)
    ids = [s.id for s in recipe.steps]
    facultatives = {s.id for s in recipe.steps if s.optional}
    for quoi, cles in (
        ("choix", choisies), ("réglages", reglages), ("étapes retenues", retenues)
    ):
        inconnues = sorted(set(cles) - set(ids))
        if inconnues:
            raise RecipeError(
                f"recette {recipe.name!r} : {quoi} pour des étapes inconnues "
                f"{inconnues} (étapes : {ids})."
            )
    if retenues - facultatives:
        raise RecipeError(
            f"recette {recipe.name!r} : {sorted(retenues - facultatives)} ne "
            f"sont pas facultatives (facultatives : {sorted(facultatives)})."
        )
    ecartees = sorted((set(choisies) | set(reglages)) & (facultatives - retenues))
    if ecartees:
        raise RecipeError(
            f"recette {recipe.name!r} : choix ou réglages pour des étapes "
            f"facultatives non retenues {ecartees} — ils seraient ignorés."
        )

    etapes: list[PipelineStep] = []
    kwargs: Settings = {}
    marques: list[tuple[RecipeStep, str, Mapping[str, object]]] = []
    precedente: str | None = None
    for step in recipe.steps:
        if step.optional and step.id not in retenues:
            continue
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
        reglage = {
            **_identite(brique, step.id, role.mode),
            **step.params,
            **reglages.get(step.id, {}),
        }
        nom = _nom_instance(brique, reglage)
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
                    crop=role.fanout and brique not in _SANS_PIXELS,
                )
            )
        kwargs[nom] = reglage
        marques.append((step, brique, reglage))
        if not step.optional:
            precedente = step.id

    spec = PipelineSpec(
        name=pipeline_name(recipe, marques),
        initial_inputs=(ArtifactType.IMAGE,),
        steps=tuple(etapes),
    )
    return spec, kwargs


def pipeline_name(
    recipe: Recipe, steps: Sequence[tuple[RecipeStep, str, Mapping[str, object]]]
) -> str:
    """Le nom d'un pipeline : **la recette, puis ce qui la distingue**.

    ``ocr_simple · tesseract``, ``ocr_puis_llm · tesseract → ollama
    (qwen2.5:3b)``, ``segmentation_puis_lecture · tesseract_layout → tesseract
    + alto``. Une étape y figure si sa brique est un **choix** (son rôle en
    propose plusieurs) ou si elle reçoit un **modèle** ; une étape facultative
    retenue s'ajoute en ``+ <étape>``. La brique est écrite même quand c'est le
    défaut : un nom qui la tairait changerait de sens le jour où le défaut
    change, et ``cinoc compare`` apparierait deux pipelines différents.

    C'est la **seule** règle de nommage (D-298) : la CLI, la page et la
    correction passent toutes par ici, donc un même pipeline porte le même nom
    par toute entrée. Ce qui reste identique (mêmes briques, mêmes modèles,
    d'autres réglages) se départage en ``#n`` dans le run.
    """
    marques: list[str] = []
    retenues: list[str] = []
    for step, brique, reglage in steps:
        if step.optional:
            retenues.append(f" + {step.id}")
            continue
        modele = reglage.get("model")
        if len(roles()[step.role].briques) > 1 or modele:
            marques.append(f"{brique} ({modele})" if modele else brique)
    nom = recipe.name + (f" · {' → '.join(marques)}" if marques else "")
    return (nom + "".join(retenues))[:120]


def _nom_instance(brique: str, reglage: Mapping[str, object]) -> str:
    """``<brique>:<libellé>`` — le libellé, ou la source rejouée, que la brique
    portera ; ``<brique>`` nu pour une brique qui ne se nomme pas (le registre
    vérifie que le module construit porte bien ce nom)."""
    libelle = reglage.get("label") or reglage.get("source_label")
    return f"{brique}:{libelle}" if isinstance(libelle, str) and libelle else brique


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
        brut = safe_load_yaml(document)
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
    except CinocError as exc:  # étape sans types de sortie, cible de vue inconnue…
        raise RecipeError(f"spec invalide : {exc}") from exc


def referenced_kinds(spec: RunSpec) -> set[str]:
    """Les ``kind`` de briques qu'une spec met en jeu.

    Le nom d'adapter suit la convention ``<kind>:<label>`` : c'est ce qui permet
    d'appliquer à une spec **arbitraire** les mêmes gardes qu'à une file de
    recettes, sans avoir à comprendre la spec.
    """
    return {
        etape.adapter_name.split(":", 1)[0]
        for pipeline in spec.pipelines
        for etape in pipeline.steps
    }


__all__ = [
    "RECIPES_DIR",
    "Recipe",
    "RecipeError",
    "RecipeStep",
    "Role",
    "describe",
    "load_recipes",
    "pipeline_name",
    "plan_from_recipe",
    "referenced_kinds",
    "spec_for_corpus",
    "recipe_by_name",
    "roles",
]
