"""Planification d'un run : (concurrents, corpus) → ``RunSpec`` (couche 6).

Construire une spec d'exécution est de l'**orchestration**, pas du transport :
les routeurs (couche 8) délèguent ici et ne fabriquent **aucun** ``RunSpec``
eux-mêmes. Le dispatch est **exhaustif** — un moteur/mode non câblé est refusé
explicitement (``RunPlanningError``), jamais redirigé en silence vers un autre
moteur (anti-régression du défaut « ``mistral`` → tesseract »).

Un **benchmark** compare N **concurrents** sur le **même corpus**, en **un seul
run** : ``plan_benchmark_run`` assemble N ``PipelineSpec`` dans **un**
``RunSpec`` (l'orchestrateur les exécute toutes et calcule le cross-engine). Un
concurrent porte un **mode** :

- ``None``           — OCR seul (ex. tesseract) → ``RAW_TEXT`` ;
- ``text_only``      — OCR → LLM (post-correction texte) → ``CORRECTED_TEXT`` ;
- ``text_and_image`` — OCR → VLM (image + texte) → ``CORRECTED_TEXT`` ;
- ``zero_shot``      — VLM seul (image → texte), sans OCR amont → ``RAW_TEXT``.

La segmentation (``IMAGE → LAYOUT``, sans score texte) reste un run **à part**
(``plan_segmentation_run``), pas un concurrent de benchmark.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cinoc.app.engines import EngineStatus, providers_for_mode
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import (
    INITIAL_STEP_ID,
    PipelineMode,
    PipelineSpec,
    PipelineStep,
)
from cinoc.domain.projection import ProjectionSpec
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.archaic import resolve_archaic_list
from cinoc.formats.text import NORMALIZATION_PROFILES
from cinoc.prompts import PromptError, load_prompt

#: Moteurs OCR câblés pour un run réel (amont d'une chaîne ou OCR seul).
_OCR_ENGINES = frozenset(
    {
        "tesseract", "kraken", "pero", "calamari",
        "mistral_ocr", "google_vision", "azure_di",
    }
)
#: Fournisseurs par mode — **dérivés des adapters**, jamais recopiés.
#:
#: Ces deux ensembles étaient des littéraux tenus à la main, et ils ont dérivé :
#: ollama a gagné ses modes vision en août 2026 sans que ``_VLM_ENGINES`` le
#: sache, si bien que le planificateur refusait deux modes que l'adapter savait
#: exécuter — le seul VLM local et gratuit, précisément (D-233). La capacité se
#: lit désormais là où elle est implémentée.
def _llm_engines() -> frozenset[str]:
    """Fournisseurs de post-correction texte (mode ``text_only``)."""
    return providers_for_mode("text_only")


def _vlm_engines() -> frozenset[str]:
    """Fournisseurs **vision** (modes ``text_and_image`` et ``zero_shot``)."""
    return providers_for_mode("zero_shot") & providers_for_mode("text_and_image")


class RunPlanningError(CinocError):
    """Moteur/mode non câblé pour un run, ou incohérence concurrent⇄corpus."""


class Competitor(BaseModel):
    """Un concurrent de benchmark = un pipeline à exécuter (couche 6).

    ``engine`` est le moteur OCR (modes ``None``/``text_*``) **ou** le
    fournisseur VLM (mode ``zero_shot``) **ou**, quand ``segmenter`` est posé, le
    **reconnaisseur par bloc** d'un pipeline **hybride** (segmenteur → bloc →
    texte). ``llm`` nomme le fournisseur de post-correction des modes ``text_*``.
    Validé exhaustivement à la planification (jamais de retombée muette).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    engine: str = Field(min_length=1, max_length=64)
    mode: PipelineMode | None = None
    #: Pipeline **hybride** : segmenteur de mise en page en tête (``pp_doclayout`` /
    #: ``remote_segmenter``). Posé ⇒ ``engine`` est le reconnaisseur **par bloc**
    #: (OCR réel ou VLM zero-shot), scoré comme du texte à la page. ``None`` ⇒
    #: pipeline à plat (OCR / chaîne / VLM), comportement historique.
    segmenter: str | None = Field(default=None, max_length=64)
    #: Endpoint object-detection HF (requis si ``segmenter == "remote_segmenter"``).
    segmenter_endpoint: str | None = Field(default=None, max_length=2048)
    #: Jeton d'auth de l'endpoint de segmentation distant (optionnel).
    segmenter_token: str | None = Field(default=None, max_length=512)
    llm: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    lang: str = Field(default="fra", max_length=64)
    #: Prompt de post-correction/transcription (modes LLM/VLM). ``None`` → prompt
    #: par défaut du rôle (``default_prompt_for_role``). Exposé à l'UI (texte libre).
    prompt: str | None = Field(default=None, max_length=8000)
    #: Nom d'un **prompt curé** (``cinoc.prompts``) à utiliser à la place du défaut.
    #: Mutuellement exclusif avec ``prompt`` (libre). Résolu au plan en son texte.
    prompt_name: str | None = Field(default=None, max_length=128)
    #: Active une **étape NER terminale** (``texte → ENTITIES``) après l'OCR/LLM —
    #: scorée par la vue *entités nommées* si le corpus porte une GT ``ENTITIES``.
    #: Brique optionnelle (extra ``[ner]``, spaCy) ; ``False`` par défaut.
    ner: bool = False
    #: Modèle spaCy de l'étape NER (défaut ``fr_core_news_sm``). Ignoré si
    #: ``ner`` est ``False``.
    ner_model: str | None = Field(default=None, max_length=128)
    #: Demande l'export **ALTO XML** (géométrie + texte par mot) de l'étape OCR —
    #: la forme ré-importable dans un outil de relecture (eScriptorium, Transkribus).
    #: Réservé à ``tesseract`` (seul moteur du socle à émettre de l'ALTO natif) ;
    #: demandé avec un autre moteur → ``RunPlanningError``. ``False`` par défaut.
    alto: bool = False


#: Types de candidat scorés par toute vue benchmark : ``RAW_TEXT`` (OCR/zero-shot)
#: **et** ``CORRECTED_TEXT`` (OCR→LLM) — la précédence du runner évalue la sortie
#: la plus aboutie de chaque pipeline (cf. evaluation).
_CANDIDATES = frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT})

#: **Profils de métriques** : bundles curés de colonnes scalaires pour la vue
#: ``text`` (classement par défaut du rapport). Chaque nom ne référence que des
#: métriques **enregistrées** pour la signature ``(RAW_TEXT, RAW_TEXT)`` — un nom
#: non enregistré ferait lever le runner (couche 3 ; verrouillé par test). Changer
#: de profil n'allège **que** les colonnes de classement : les *collecteurs*
#: (taxonomy, structured_data, NER…) restent indépendants de ``metric_names``, la
#: donnée n'est jamais perdue. ``standard`` est le défaut **historique**
#: (byte-identique à l'ancienne vue par défaut).
DEFAULT_METRIC_PROFILE = "standard"
METRIC_PROFILES: dict[str, tuple[str, ...]] = {
    # ``cmer`` = MER caractère **borné [0,1]** (robuste aux modèles génératifs qui
    # font dépasser le CER ; cf. metrics/conformity) — calculé sur RAW_TEXT comme
    # CER, donc exposé d'office au socle (≠ réservé HIPE). Groupé « caractère ».
    "standard": (
        "cer", "cmer", "char_accuracy", "word_accuracy", "fca", "wer", "mer",
        "bow_precision", "bow_recall", "bow_f1",
        "searchability", "hallucination", "air",
    ),
    "essentiel": ("cer", "wer", "mer"),
    "philologie": ("cer", "cer_diplo", "mer", "diacritic_err", "mufi_err", "air"),
}


def _ocr_view(
    normalization: str | None,
    char_exclude: str | None,
    *,
    with_hcpr: bool = False,
    base_metrics: tuple[str, ...] = METRIC_PROFILES[DEFAULT_METRIC_PROFILE],
) -> EvaluationView:
    # ``base_metrics`` vient du **profil de métriques** choisi (défaut
    # ``standard``). ``air`` (apport net d'archaïsmes) y est d'office (Q4) ;
    # ``hcpr`` (préservation) n'est **ajouté** que sur une liste **explicitement**
    # configurée — sinon il doublonnerait ``mufi_err`` sur tout corpus médiéval.
    # ``numseq_strict``/``numseq_value`` restent **hors** des profils (D-130) :
    # adaptatifs (``None`` sans séquences) → colonnes vides « — » sur tout corpus
    # sans dates/folios/montants. Ils restent **enregistrés** (utilisables par une
    # vue custom qui voudrait classer dessus), et la **section `structured_data`
    # reste affichée** quand des séquences existent (le collecteur l'observe
    # indépendamment de ``metric_names``) — la donnée n'est pas perdue, seul le
    # classement scalaire par défaut s'allège.
    metric_names = base_metrics
    if with_hcpr:
        metric_names = (*metric_names, "hcpr")
    return EvaluationView(
        name="text",
        candidate_types=_CANDIDATES,
        metric_names=metric_names,
        normalization_profile=normalization,
        char_exclude=char_exclude,
    )


def _layout_view() -> EvaluationView:
    """Vue **structure / mise en page** : note les sorties ``LAYOUT``
    (segmentation) par **Region-F1** (`region_detection`) + **CER par région**
    (`region_cer`), sans projection — les métriques prennent le
    ``CanonicalLayout`` directement. Normalisation/`char_exclude` N/A (géométrie
    + texte par région). N'est ajoutée que si le corpus porte une GT ``LAYOUT``."""
    return EvaluationView(
        name="structure (mise en page)",
        candidate_types=frozenset({ArtifactType.LAYOUT}),
        metric_names=(
            "region_detection",
            "region_cer",
            # Appariement par IDENTITÉ, quand les deux côtés portent des
            # identifiants de ligne : exact là où l'alignement de lignes
            # devine. Mesuré sur corpus/37-GT-BNL : la devinette diverge sur
            # 57 lignes de 522 et gonfle le CER par ligne de 58 %.
            "line_identity_cer",
            "line_identity_coverage",
        ),
    )


def _ner_view() -> EvaluationView:
    """Vue **entités nommées (NER)** : note les sorties ``ENTITIES`` (étape NER)
    par ``ner_f1`` contre la GT ``ENTITIES``, sans projection (jonction
    ``(ENTITIES, ENTITIES)``). Normalisation/`char_exclude` N/A (comparaison
    d'entités, pas de texte). N'est ajoutée que si le corpus porte une GT
    ``ENTITIES`` (sinon la section NER resterait orpheline)."""
    return EvaluationView(
        name="entités nommées (NER)",
        candidate_types=frozenset({ArtifactType.ENTITIES}),
        metric_names=("ner_f1",),
    )


def _reference_view(
    normalization: str | None, char_exclude: str | None
) -> EvaluationView:
    """Vue **référence OCR** (opt-in) : compare le candidat à une référence
    ``REFERENCE_TEXT`` (ex. OCR Gallica) via une projection identité. Le **nom de
    la vue porte l'avertissement** : ce n'est PAS une vérité-terrain manuelle, le
    score mesure l'accord avec un autre OCR."""
    return EvaluationView(
        name="référence OCR (pas une vérité-terrain manuelle)",
        candidate_types=_CANDIDATES,
        projections_by_source_type={
            ArtifactType.REFERENCE_TEXT: ProjectionSpec(
                source_type=ArtifactType.REFERENCE_TEXT,
                target_type=ArtifactType.RAW_TEXT,
                projector_name="identity_text",
            )
        },
        metric_names=("cer", "wer", "mer"),
        ignored_dimensions=("exactitude (la référence est elle-même un OCR)",),
        normalization_profile=normalization,
        char_exclude=char_exclude,
    )


def _views_for_corpus(
    corpus: CorpusSpec,
    normalization: str | None = None,
    char_exclude: str | None = None,
    *,
    with_hcpr: bool = False,
    base_metrics: tuple[str, ...] = METRIC_PROFILES[DEFAULT_METRIC_PROFILE],
) -> tuple[EvaluationView, ...]:
    """Vues à évaluer selon les **types de GT présents**, sous ``normalization``.

    GT manuelle ``RAW_TEXT`` → vue ``text`` ; référence ``REFERENCE_TEXT`` (OCR
    Gallica) → vue *référence* distincte. Un corpus sans GT → vue ``text`` par
    défaut (le run reste exécutable, simplement non scoré). ``char_exclude``
    filtre des caractères des deux côtés (GT/hyp) avant le calcul (runner couche 3).
    ``with_hcpr`` ajoute la colonne ``hcpr`` à la vue ``text`` (liste archaïque
    configurée). ``base_metrics`` = colonnes scalaires du **profil de métriques**
    choisi (n'affecte que la vue ``text``, pas la vue *référence* fixe).
    """
    gt_types = {gt.type for doc in corpus.documents for gt in doc.ground_truths}
    views: list[EvaluationView] = []
    if ArtifactType.RAW_TEXT in gt_types:
        views.append(
            _ocr_view(
                normalization, char_exclude,
                with_hcpr=with_hcpr, base_metrics=base_metrics,
            )
        )
    if ArtifactType.REFERENCE_TEXT in gt_types:
        views.append(_reference_view(normalization, char_exclude))
    if ArtifactType.LAYOUT in gt_types:
        views.append(_layout_view())
    if ArtifactType.ENTITIES in gt_types:
        views.append(_ner_view())
    if not views:
        views.append(
            _ocr_view(
                normalization, char_exclude,
                with_hcpr=with_hcpr, base_metrics=base_metrics,
            )
        )
    return tuple(views)


def _resolve_metric_profile(name: str | None) -> tuple[str, ...]:
    """Colonnes scalaires d'un profil nommé (défaut : ``standard``).

    Un nom inconnu → ``RunPlanningError`` (jamais un défaut muet ; le routeur le
    remonte en 422), comme pour un profil de normalisation inconnu.
    """
    if name is None:
        return METRIC_PROFILES[DEFAULT_METRIC_PROFILE]
    try:
        return METRIC_PROFILES[name]
    except KeyError:
        raise RunPlanningError(
            f"profil de métriques inconnu : {name!r}."
        ) from None


def _resolve_prompt(comp: Competitor) -> str | None:
    """Texte du prompt : libre (prioritaire) > curé (par nom) > défaut du rôle.

    ``prompt`` (texte libre saisi) et ``prompt_name`` (prompt curé) sont
    **mutuellement exclusifs** : les fournir tous deux est une erreur de plan
    (jamais un choix silencieux). Un nom curé inconnu → ``RunPlanningError`` (422).
    """
    if comp.prompt and comp.prompt_name:
        raise RunPlanningError(
            "prompt : choisir un prompt libre OU un prompt curé, pas les deux."
        )
    if comp.prompt:
        return comp.prompt
    if comp.prompt_name:
        try:
            return load_prompt(comp.prompt_name)
        except PromptError as exc:
            raise RunPlanningError(str(exc)) from exc
    return None


def _llm_kwargs(
    label: str, comp: Competitor, role: PipelineMode
) -> dict[str, str | int | float | bool]:
    kwargs: dict[str, str | int | float | bool] = {"label": label, "role": role}
    if comp.model:
        kwargs["model"] = comp.model
    prompt = _resolve_prompt(comp)
    if prompt:
        kwargs["prompt"] = prompt
    return kwargs


#: Modèle spaCy par défaut de l'étape NER (français — cohérent avec le défaut
#: historique du builder ``ner``). Surchargé par ``Competitor.ner_model``.
_NER_DEFAULT_MODEL = "fr_core_news_sm"


def _ner_step(suffix: str, text_type: ArtifactType, from_id: str) -> PipelineStep:
    """Étape NER **terminale** : ``text → ENTITIES`` (branchée sur la sortie texte
    la plus aboutie du pipeline — ``RAW_TEXT`` en OCR/zero-shot, ``CORRECTED_TEXT``
    en chaîne LLM/VLM)."""
    return PipelineStep(
        id="ner",
        kind="ner",
        adapter_name=f"ner:{suffix}",
        input_types=(text_type,),
        output_types=(ArtifactType.ENTITIES,),
        inputs_from={text_type: from_id},
    )


def _ner_kwargs(
    suffix: str, comp: Competitor
) -> dict[str, str | int | float | bool]:
    return {"label": suffix, "model": comp.ner_model or _NER_DEFAULT_MODEL}


def _hybrid_reco_kwargs(
    comp: Competitor, suffix: str
) -> tuple[str, dict[str, str | int | float | bool]]:
    """``(adapter_name, kwargs)`` du reconnaisseur **par bloc** d'un hybride.

    OCR réel → ``IMAGE → RAW_TEXT`` (``lang``/``model``) ; VLM → même contrat en
    rôle ``zero_shot`` (transcription par bloc, prompt curé/libre optionnel).
    """
    name = f"{comp.engine}:{suffix}"
    if comp.engine in _vlm_engines():
        kwargs: dict[str, str | int | float | bool] = {
            "label": suffix,
            "role": "zero_shot",
        }
        prompt = _resolve_prompt(comp)
        if prompt:
            kwargs["prompt"] = prompt
    else:
        kwargs = {"label": suffix, "lang": comp.lang}
    if comp.model:
        kwargs["model"] = comp.model
    return name, kwargs


def _hybrid_competitor(
    comp: Competitor, suffix: str
) -> tuple[PipelineSpec, dict[str, dict[str, str | int | float | bool]]]:
    """Pipeline **hybride** d'un concurrent : segmenteur → reconnaissance par bloc
    (fan-out, image découpée) → aplatissement texte (scoré CER/WER à la page) — et,
    si ``alto``, assemblage ALTO XML téléchargeable. C'est « segmentation puis OCR/
    VLM » jugé **côte à côte** avec un pipeline à plat, dans le même run."""
    from cinoc.app.structure_planning import (  # cycle → import local
        PIPELINE_SEGMENTERS,
        pipeline_recognizers,
    )

    # Même ensemble que la transcription autonome : la même intention ne peut
    # pas recevoir deux réponses selon le mode d'entrée (D-233).
    if comp.segmenter not in PIPELINE_SEGMENTERS:
        raise RunPlanningError(
            f"hybride : segmenteur non câblé : {comp.segmenter!r} "
            f"(attendu l'un de {sorted(PIPELINE_SEGMENTERS)})."
        )
    if comp.engine not in pipeline_recognizers():
        raise RunPlanningError(
            f"hybride : reconnaisseur par bloc non câblé : {comp.engine!r} "
            f"(attendu l'un de {sorted(pipeline_recognizers())})."
        )
    if comp.mode is not None:
        raise RunPlanningError("hybride : aucun mode (le pipeline est seg → bloc).")
    if comp.llm:
        raise RunPlanningError("hybride : pas de LLM séparé (reconnaissance par bloc).")
    recognizer, reco_kwargs = _hybrid_reco_kwargs(comp, suffix)
    text_name = f"layout_to_text:{suffix}"
    kwargs: dict[str, dict[str, str | int | float | bool]] = {
        recognizer: reco_kwargs,
        text_name: {"label": suffix},
    }
    steps: list[PipelineStep] = [
        PipelineStep(
            id="segment",
            kind="segmentation",
            adapter_name=comp.segmenter,
            input_types=(ArtifactType.IMAGE,),
            output_types=(ArtifactType.LAYOUT,),
        ),
        PipelineStep(
            id="recognize",
            kind="recognition",
            adapter_name=recognizer,
            input_types=(ArtifactType.LAYOUT, ArtifactType.IMAGE),
            output_types=(ArtifactType.LAYOUT,),
            inputs_from={ArtifactType.LAYOUT: "segment"},
            fanout=True,
            crop=True,
        ),
        PipelineStep(
            id="text",
            kind="extraction",
            adapter_name=text_name,
            input_types=(ArtifactType.LAYOUT,),
            output_types=(ArtifactType.RAW_TEXT,),
            inputs_from={ArtifactType.LAYOUT: "recognize"},
        ),
    ]
    if comp.segmenter == "remote_segmenter":
        if not comp.segmenter_endpoint:
            raise RunPlanningError(
                "hybride : 'segmenter_endpoint' requis pour remote_segmenter."
            )
        seg_kwargs: dict[str, str | int | float | bool] = {
            "endpoint": comp.segmenter_endpoint
        }
        if comp.segmenter_token:
            seg_kwargs["token"] = comp.segmenter_token
        kwargs[comp.segmenter] = seg_kwargs
    if comp.alto:
        steps.append(
            PipelineStep(
                id="assemble",
                kind="assembly",
                adapter_name="alto_assembler",
                input_types=(ArtifactType.LAYOUT,),
                output_types=(ArtifactType.ALTO_XML,),
                inputs_from={ArtifactType.LAYOUT: "recognize"},
            )
        )
    if comp.ner:
        steps.append(_ner_step(suffix, ArtifactType.RAW_TEXT, "text"))
        kwargs[f"ner:{suffix}"] = _ner_kwargs(suffix, comp)
    pipeline = PipelineSpec(
        name=f"{comp.segmenter}→{comp.engine}",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=tuple(steps),
    )
    return pipeline, kwargs


def _pipeline_for_competitor(
    comp: Competitor, index: int,
) -> tuple[PipelineSpec, dict[str, dict[str, str | int | float | bool]]]:
    """Construit le ``PipelineSpec`` + ``adapter_kwargs`` d'**un** concurrent.

    Labels d'adapter suffixés par l'index (``c0``, ``c1``…) : chaque concurrent a
    ses propres instances de modules — pas de collision entre concurrents.
    """
    suffix = f"c{index}"
    # Pipeline **hybride** (segmenteur posé) : branche dédiée AVANT le dispatch à
    # plat — ALTO y est produit par l'assembleur (pas réservé à tesseract).
    if comp.segmenter is not None:
        return _hybrid_competitor(comp, suffix)
    # ALTO natif : réservé à tesseract (seul moteur du socle qui l'émet). Refusé
    # AVANT le dispatch de mode → message clair, jamais un export muet ignoré.
    if comp.alto and comp.engine != "tesseract":
        raise RunPlanningError(
            f"export ALTO : réservé à tesseract, pas à {comp.engine!r}."
        )
    # Types de sortie de l'étape OCR tesseract : ``RAW_TEXT`` + ``ALTO_XML`` si export.
    ocr_outputs: tuple[ArtifactType, ...] = (
        (ArtifactType.RAW_TEXT, ArtifactType.ALTO_XML)
        if comp.alto
        else (ArtifactType.RAW_TEXT,)
    )
    if comp.mode is None:
        if comp.engine not in _OCR_ENGINES:
            raise RunPlanningError(f"OCR seul : moteur non câblé : {comp.engine!r}.")
        if comp.llm:
            raise RunPlanningError("OCR seul : aucun LLM attendu.")
        name = f"{comp.engine}:{suffix}"
        step = PipelineStep(
            id="ocr",
            kind="ocr",
            adapter_name=name,
            input_types=(ArtifactType.IMAGE,),
            output_types=ocr_outputs,
        )
        steps: list[PipelineStep] = [step]
        ocr_kwargs: dict[str, dict[str, str | int | float | bool]] = {
            name: {"label": suffix, "lang": comp.lang}
        }
        if comp.alto:
            ocr_kwargs[name]["alto"] = True
        # En OCR seul, ``model`` est le **modèle du moteur** (chemin .mlmodel
        # kraken, config PERO, checkpoint Calamari, nom Mistral OCR) — requis par
        # ces moteurs. Tesseract/Google/Azure ignorent ce kwarg. (En chaîne,
        # ``model`` désigne le LLM aval, cf. ``_llm_kwargs``.)
        if comp.model:
            ocr_kwargs[name]["model"] = comp.model
        if comp.ner:
            steps.append(_ner_step(suffix, ArtifactType.RAW_TEXT, "ocr"))
            ocr_kwargs[f"ner:{suffix}"] = _ner_kwargs(suffix, comp)
        pipeline = PipelineSpec(
            name=comp.engine,
            initial_inputs=(ArtifactType.IMAGE,),
            steps=tuple(steps),
        )
        return pipeline, ocr_kwargs

    if comp.mode == "zero_shot":
        if comp.engine not in _vlm_engines():
            raise RunPlanningError(
                f"zero_shot : {comp.engine!r} n'a pas de VLM (vision)."
            )
        if comp.llm:
            raise RunPlanningError(
                "zero_shot : pas de LLM séparé (le moteur EST le VLM)."
            )
        name = f"{comp.engine}:{suffix}"
        step = PipelineStep(
            id="vlm",
            kind="transcription",
            adapter_name=name,
            input_types=(ArtifactType.IMAGE,),
            output_types=(ArtifactType.RAW_TEXT,),
        )
        vlm_steps: list[PipelineStep] = [step]
        vlm_kwargs: dict[str, dict[str, str | int | float | bool]] = {
            name: _llm_kwargs(suffix, comp, "zero_shot")
        }
        if comp.ner:
            vlm_steps.append(_ner_step(suffix, ArtifactType.RAW_TEXT, "vlm"))
            vlm_kwargs[f"ner:{suffix}"] = _ner_kwargs(suffix, comp)
        pipeline = PipelineSpec(
            name=f"{comp.engine} (zero-shot)",
            initial_inputs=(ArtifactType.IMAGE,),
            steps=tuple(vlm_steps),
        )
        return pipeline, vlm_kwargs

    # text_only / text_and_image : OCR amont → LLM/VLM.
    if comp.engine not in _OCR_ENGINES:
        raise RunPlanningError(
            f"{comp.mode} : moteur OCR amont non câblé : {comp.engine!r}."
        )
    if not comp.llm:
        raise RunPlanningError(f"{comp.mode} : un fournisseur LLM est requis.")
    allowed = _llm_engines() if comp.mode == "text_only" else _vlm_engines()
    if comp.llm not in allowed:
        raise RunPlanningError(
            f"{comp.mode} : fournisseur {comp.llm!r} indisponible pour ce mode."
        )
    ocr_name = f"{comp.engine}:{suffix}"
    llm_name = f"{comp.llm}:{suffix}"
    ocr_step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name=ocr_name,
        input_types=(ArtifactType.IMAGE,),
        output_types=ocr_outputs,
    )
    llm_inputs: tuple[ArtifactType, ...]
    inputs_from: dict[ArtifactType, str]
    if comp.mode == "text_only":
        llm_inputs = (ArtifactType.RAW_TEXT,)
        inputs_from = {ArtifactType.RAW_TEXT: "ocr"}
    else:  # text_and_image — le VLM reçoit l'image initiale ET le texte OCR.
        llm_inputs = (ArtifactType.RAW_TEXT, ArtifactType.IMAGE)
        inputs_from = {
            ArtifactType.RAW_TEXT: "ocr",
            ArtifactType.IMAGE: INITIAL_STEP_ID,
        }
    llm_step = PipelineStep(
        id="llm",
        kind="post_correction",
        adapter_name=llm_name,
        input_types=llm_inputs,
        output_types=(ArtifactType.CORRECTED_TEXT,),
        inputs_from=inputs_from,
    )
    chain_steps: list[PipelineStep] = [ocr_step, llm_step]
    kwargs: dict[str, dict[str, str | int | float | bool]] = {
        ocr_name: {"label": suffix, "lang": comp.lang},
        llm_name: _llm_kwargs(suffix, comp, comp.mode),
    }
    if comp.alto:
        kwargs[ocr_name]["alto"] = True
    if comp.ner:
        chain_steps.append(_ner_step(suffix, ArtifactType.CORRECTED_TEXT, "llm"))
        kwargs[f"ner:{suffix}"] = _ner_kwargs(suffix, comp)
    pipeline = PipelineSpec(
        name=f"{comp.engine}→{comp.llm}",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=tuple(chain_steps),
    )
    return pipeline, kwargs


def plan_benchmark_run(
    competitors: tuple[Competitor, ...],
    corpus: CorpusSpec | None,
    run_id: str,
    *,
    normalization: str | None = None,
    char_exclude: str | None = None,
    archaic_list: str | None = None,
    metric_profile: str | None = None,
    detailed_analyses: bool = False,
) -> Callable[[Path], RunSpec]:
    """Builder de spec d'un **benchmark** : N concurrents → un ``RunSpec``.

    Exhaustif : tout moteur/mode non câblé est refusé (``RunPlanningError``).
    Les noms de pipeline sont rendus **uniques** (suffixe ``#n`` en cas de
    doublon) pour ne pas se piétiner dans les sorties indexées par nom.

    ``archaic_list`` (nom d'une liste curée, cf. ``ARCHAIC_LISTS``) **active
    ``hcpr``** (préservation des archaïsmes) et **relie ``air``/``hcpr`` à cette
    liste** ; sans lui, seul ``air`` reste actif sur la liste par défaut. Le nom
    et l'empreinte de la liste effective entrent au ``RunManifest.metadata``
    (reproductibilité) ; un nom inconnu est refusé (``RunPlanningError``).

    ``metric_profile`` (nom d'un :data:`METRIC_PROFILES`) choisit le **bundle de
    colonnes scalaires** de la vue ``text`` (défaut ``standard``, byte-identique à
    l'historique) ; un nom inconnu est refusé (``RunPlanningError`` → 422). Il
    n'affecte **que** le classement par défaut — les collecteurs restent intacts.
    """
    if not competitors:
        raise RunPlanningError("benchmark : au moins un concurrent requis.")
    if corpus is None:
        raise RunPlanningError("benchmark : corpus requis.")
    if normalization is not None and normalization not in NORMALIZATION_PROFILES:
        raise RunPlanningError(
            f"profil de normalisation inconnu : {normalization!r}."
        )
    base_metrics = _resolve_metric_profile(metric_profile)
    try:
        resolved = resolve_archaic_list(archaic_list)
    except CinocError as exc:
        raise RunPlanningError(str(exc)) from exc
    pipelines: list[PipelineSpec] = []
    adapter_kwargs: dict[str, dict[str, str | int | float | bool]] = {}
    seen: dict[str, int] = {}
    for index, comp in enumerate(competitors):
        pipeline, kwargs = _pipeline_for_competitor(comp, index)
        if pipeline.name in seen:
            seen[pipeline.name] += 1
            pipeline = pipeline.model_copy(
                update={"name": f"{pipeline.name} #{seen[pipeline.name]}"}
            )
        else:
            seen[pipeline.name] = 1
        pipelines.append(pipeline)
        adapter_kwargs.update(kwargs)
    spec = RunSpec(
        corpus=corpus,
        pipelines=tuple(pipelines),
        evaluation=EvaluationSpec(
            views=_views_for_corpus(
                corpus, normalization, char_exclude,
                with_hcpr=archaic_list is not None,
                base_metrics=base_metrics,
            ),
            # Mode rapide par défaut, ici comme en ligne de commande : le
            # lanceur web ne doit pas offrir un défaut différent (D-224).
            analyses="toutes" if detailed_analyses else None,
        ),
        adapter_kwargs=adapter_kwargs,
        run_id=run_id,
        metadata={
            "archaic_list": resolved.name,
            "archaic_list_hash": resolved.list_hash,
        },
    )
    return lambda _ws: spec


def benchmark_engine_catalog(
    statuses: tuple[EngineStatus, ...],
) -> dict[str, list[dict[str, object]]]:
    """Moteurs proposables au composeur, **par rôle** (``ocr``/``llm``/``vlm``).

    Source unique des rôles : les mêmes ensembles que ``plan_benchmark_run``
    accepte (anti-vide — on n'offre jamais une option sans branche serveur). Un
    moteur indisponible **reste listé** (grisé côté UI) : son backend existe, il
    manque seulement une clé/un binaire.
    """
    by_kind = {status.kind: status for status in statuses}

    def role(kinds: frozenset[str]) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for kind in sorted(kinds):
            status = by_kind.get(kind)
            if status is not None:
                entries.append(
                    {
                        "kind": kind,
                        "label": status.label,
                        "available": status.available,
                    }
                )
        return entries

    return {
        "ocr": role(_OCR_ENGINES),
        "llm": role(_llm_engines()),
        "vlm": role(_vlm_engines()),
    }


def metric_profile_catalog() -> tuple[dict[str, object], ...]:
    """Profils de métriques proposables au lanceur — **source unique** de l'UI.

    ``standard`` (défaut) d'abord, puis les autres triés (ordre déterministe).
    Chaque entrée porte la liste **ordonnée** de ses métriques : le formulaire
    s'en sert pour un libellé self-documenté (les noms de métriques sont neutres
    en langue, pas d'i18n par profil). Anti-vide : on n'offre jamais une option
    sans branche serveur — chaque nom est résolu par ``_resolve_metric_profile``.
    """
    others = sorted(name for name in METRIC_PROFILES if name != DEFAULT_METRIC_PROFILE)
    return tuple(
        {"name": name, "metrics": list(METRIC_PROFILES[name])}
        for name in (DEFAULT_METRIC_PROFILE, *others)
    )


__all__ = [
    "DEFAULT_METRIC_PROFILE",
    "METRIC_PROFILES",
    "Competitor",
    "RunPlanningError",
    "benchmark_engine_catalog",
    "metric_profile_catalog",
    "plan_benchmark_run",
]
