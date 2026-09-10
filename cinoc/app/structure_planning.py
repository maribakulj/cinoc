"""Planification d'un run de **structure** : segmentation + hybride (couche 6).

Sœur de ``run_planning`` (qui planifie les **benchmarks** texte). On isole ici
la planification *structure* — segmentation seule (``IMAGE → LAYOUT``) et pipeline
**hybride** (seg → reconnaissance par région → assemblage ALTO) — extraite de
``run_planning`` quand son seuil de découpe a été atteint (surface T5). Même
couche, même contrat : (choix UI/CLI) → ``RunSpec``. Les routeurs (couche 8) y
délèguent et ne fabriquent **aucun** ``RunSpec`` eux-mêmes.

Le slot de reconnaissance **par région** accepte tout moteur ``IMAGE → RAW_TEXT``
(le bloc découpé est OCRisé/transcrit puis réinjecté dans le ``LAYOUT``) : tout
OCR réel **ou** un VLM en transcription ``zero_shot`` — c'est exactement « un VLM
derrière une segmentation ».
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cinoc.app.engines import EngineStatus, providers_for_mode
from cinoc.app.run_planning import (
    _OCR_ENGINES,
    RunPlanningError,
)
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.evaluation import EvaluationSpec
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec

#: Segmenteur de mise en page du socle **par défaut** — **source unique** du
#: *kind* (consommé par la planification du run de segmentation ET par le gate
#: du routeur).
SEGMENTER_KIND = "pp_doclayout"

#: Segmenteurs du socle proposables au lanceur. ``pp_doclayout`` tourne en local
#: (poids) ; ``remote_segmenter`` **délègue** à un endpoint object-detection HF
#: (le modèle tourne à distance — on change de modèle en changeant l'endpoint).
SEGMENTER_KINDS = ("pp_doclayout", "remote_segmenter")

#: Segmenteurs acceptés **en tête d'un pipeline**, benchmark ou transcription
#: autonome : les réels, plus la brique de rejeu. **Source unique** — les deux
#: planificateurs lisaient jusqu'ici deux ensembles différents, si bien que la
#: même intention exprimée en mode benchmark ou en mode transcription donnait
#: deux réponses (D-233). Le rejeu appartient à la liste : il sert la démo et la
#: CI, où il n'y a ni PaddleX ni endpoint distant.
PIPELINE_SEGMENTERS = frozenset(SEGMENTER_KINDS) | {"precomputed_layout"}


def _segmentation_spec(
    corpus: CorpusSpec,
    run_id: str,
    *,
    segmenter: str,
    adapter_kwargs: dict[str, dict[str, str | int | float | bool]],
) -> RunSpec:
    """Pipeline de segmentation à 1 étape : ``segmenter`` (IMAGE→LAYOUT).

    Aucune vue d'évaluation : un run de segmentation produit de la **géométrie**
    (captée par le sink), pas une métrique scalaire. Le ``RunResult`` reste
    l'output formel du run ; les régions se visualisent via l'aperçu du lanceur
    (``GET /api/segmentation/preview``).

    ``adapter_kwargs`` porte les paramètres de construction du module choisi
    (ex. ``endpoint``/``token`` du segmenteur distant) → factory + ``RunManifest``.
    """
    step = PipelineStep(
        id="seg",
        kind="layout",
        adapter_name=segmenter,
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.LAYOUT,),
    )
    return RunSpec(
        corpus=corpus,
        pipelines=(
            PipelineSpec(
                name=segmenter,
                initial_inputs=(ArtifactType.IMAGE,),
                steps=(step,),
            ),
        ),
        evaluation=EvaluationSpec(views=()),
        adapter_kwargs=adapter_kwargs,
        run_id=run_id,
    )


def plan_segmentation_run(
    corpus: CorpusSpec,
    run_id: str,
    *,
    segmenter: str = SEGMENTER_KIND,
    endpoint: str | None = None,
    token: str | None = None,
) -> Callable[[Path], RunSpec]:
    """Builder de spec d'un run de **segmentation**.

    ``segmenter`` choisit le module (``pp_doclayout`` local ou ``remote_segmenter``
    distant). Pour ``remote_segmenter``, ``endpoint`` est **requis** (la cible
    object-detection) ; ``token`` est optionnel (auth de l'endpoint).
    """
    if segmenter not in SEGMENTER_KINDS:
        raise RunPlanningError(f"segmenteur inconnu : {segmenter!r}.")
    adapter_kwargs: dict[str, dict[str, str | int | float | bool]] = {}
    if segmenter == "remote_segmenter":
        if not endpoint:
            raise RunPlanningError(
                "remote_segmenter : 'endpoint' requis (cible object-detection)."
            )
        kwargs: dict[str, str | int | float | bool] = {"endpoint": endpoint}
        if token:
            kwargs["token"] = token
        adapter_kwargs[segmenter] = kwargs
    return lambda _ws: _segmentation_spec(
        corpus, run_id, segmenter=segmenter, adapter_kwargs=adapter_kwargs
    )


#: Segmenteurs valides en tête d'un run hybride (réels + précalculé pour la démo).
_HYBRID_SEGMENTERS = PIPELINE_SEGMENTERS
#: Reconnaisseurs **par région** câblés : tout moteur ``IMAGE → RAW_TEXT`` convient
#: au slot de fan-out (le bloc découpé est OCRisé/transcrit puis réinjecté). Donc
#: l'ensemble des OCR réels (dont ``mistral_ocr``, ``google_vision``, ``azure_di``)
#: **et** les VLM en transcription **zero-shot** par bloc — c'est exactement « un
#: VLM derrière une segmentation ». ``precomputed_region`` reste le mode démo/CI.
_HYBRID_OCR = _OCR_ENGINES | {"precomputed_region"}


def _hybrid_vlm() -> frozenset[str]:
    """VLM utilisables **par bloc** : ceux qui savent transcrire une image.

    Le mode par région est du ``zero_shot`` appliqué à un découpage — la
    capacité pertinente est donc celle-là, et elle est lue sur les adapters
    (aucune liste tenue à la main ne peut plus diverger, cf. D-233).
    """
    return providers_for_mode("zero_shot")


def pipeline_recognizers() -> frozenset[str]:
    """Reconnaisseurs valides **par bloc**, benchmark ou transcription autonome.

    Source unique, pour la même raison que ``PIPELINE_SEGMENTERS`` : les deux
    planificateurs en tenaient deux versions, et le rejeu manquait à celle du
    benchmark (D-233).
    """
    return frozenset(_HYBRID_OCR) | _hybrid_vlm()

_HybridKwargs = dict[str, dict[str, str | int | float | bool]]


def _hybrid_recognizer(
    ocr: str,
    *,
    label: str,
    source_label: str | None,
    lang: str = "fra",
    model: str | None = None,
    prompt: str | None = None,
) -> tuple[str, dict[str, str | int | float | bool]]:
    """``(adapter_name, kwargs)`` du reconnaisseur **par région** selon le moteur.

    OCR réel → ``IMAGE → RAW_TEXT`` (``lang``/``model`` selon le moteur) ; VLM →
    même contrat en rôle ``zero_shot`` (transcription par bloc, prompt optionnel).
    """
    if ocr == "precomputed_region":
        if not source_label:
            raise RunPlanningError(
                "plan_hybrid_run : 'source_label' requis pour precomputed_region."
            )
        return f"precomputed_region:{source_label}", {"source_label": source_label}
    if ocr in _hybrid_vlm():
        kwargs: dict[str, str | int | float | bool] = {
            "label": label,
            "role": "zero_shot",
        }
        if model:
            kwargs["model"] = model
        if prompt:
            kwargs["prompt"] = prompt
        return f"{ocr}:{label}", kwargs
    if ocr in _OCR_ENGINES:
        ocr_kwargs: dict[str, str | int | float | bool] = {
            "label": label,
            "lang": lang,
        }
        if model:
            ocr_kwargs["model"] = model
        return f"{ocr}:{label}", ocr_kwargs
    raise RunPlanningError(
        f"plan_hybrid_run : reconnaisseur par région inconnu {ocr!r} "
        f"(attendu l'un de {sorted(pipeline_recognizers())})."
    )


def hybrid_recognizer_catalog(
    statuses: tuple[EngineStatus, ...],
) -> list[dict[str, object]]:
    """Reconnaisseurs proposables au panneau hybride (OCR réels + VLM zero-shot).

    Source **unique** de ce qu'offre l'UI et de ce que ``plan_hybrid_run`` accepte
    (anti-vide). Un moteur indisponible reste listé (grisé) ; ``vlm`` marque la
    transcription par bloc. ``precomputed_region`` (démo) n'y figure pas.
    """
    by_kind = {s.kind: s for s in statuses}
    out: list[dict[str, object]] = []
    for vlm, kinds in ((False, sorted(_OCR_ENGINES)), (True, sorted(_hybrid_vlm()))):
        for kind in kinds:
            status = by_kind.get(kind)
            if status is not None:
                out.append(
                    {
                        "kind": kind,
                        "label": status.label,
                        "available": status.available,
                        "vlm": vlm,
                    }
                )
    return out


def _hybrid_spec(
    corpus: CorpusSpec,
    run_id: str,
    *,
    segmenter: str,
    recognizer: str,
    crop: bool,
    adapter_kwargs: _HybridKwargs,
) -> RunSpec:
    """Pipeline **hybride** à 3 étages en **une** ``PipelineSpec`` :

    1. ``segmenter`` : ``IMAGE → LAYOUT`` (régions seules — ``pp_doclayout`` réel,
       ``remote_segmenter`` distant, ou ``precomputed_layout`` pour la démo) ;
    2. ``recognizer`` : reconnaissance **par région** (``fanout=True`` → l'exécuteur
       boucle sur les régions, **découpe** chaque bloc via le cropper de couche 5
       et l'OCR par bloc, couche 4) → ``LAYOUT`` rempli ;
    3. ``alto_assembler`` : ``LAYOUT`` rempli → ``ALTO_XML`` (déterministe).
    """
    steps = (
        PipelineStep(
            id="segment",
            kind="segmentation",
            adapter_name=segmenter,
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
            crop=crop,
        ),
        PipelineStep(
            id="assemble",
            kind="assembly",
            adapter_name="alto_assembler",
            input_types=(ArtifactType.LAYOUT,),
            output_types=(ArtifactType.ALTO_XML,),
            inputs_from={ArtifactType.LAYOUT: "recognize"},
        ),
    )
    return RunSpec(
        corpus=corpus,
        pipelines=(
            PipelineSpec(
                name="hybrid", initial_inputs=(ArtifactType.IMAGE,), steps=steps
            ),
        ),
        # Pas de vue : un run hybride **produit** l'ALTO (géométrie + texte) ;
        # le scoring d'une métrique de structure est un épaississement (F-3b),
        # soumis à la preuve d'informativité (réflexe T7) avant câblage.
        evaluation=EvaluationSpec(views=()),
        adapter_kwargs=adapter_kwargs,
        run_id=run_id,
    )


def plan_hybrid_run(
    corpus: CorpusSpec,
    run_id: str,
    *,
    segmenter: str = "pp_doclayout",
    ocr: str = "tesseract",
    label: str = "hybrid",
    source_label: str | None = None,
    endpoint: str | None = None,
    token: str | None = None,
    lang: str = "fra",
    model: str | None = None,
    prompt: str | None = None,
) -> Callable[[Path], RunSpec]:
    """Builder de spec d'un run **hybride** seg → reconnaissance par région → ALTO.

    Compose un segmenteur (``pp_doclayout`` réel par défaut, ``remote_segmenter``,
    ou ``precomputed_layout`` démo) + un reconnaisseur **par région** (tout OCR réel
    — ``tesseract`` par défaut, ``mistral_ocr``… — **ou** un VLM en ``zero_shot``)
    + ``alto_assembler`` en une ``PipelineSpec`` à fan-out. L'exécuteur découpe
    chaque bloc (cropper couche 5) et le reconnaît. ``remote_segmenter`` exige
    ``endpoint`` ; ``precomputed_region`` exige ``source_label`` (démo). ``model``/
    ``prompt`` ciblent le reconnaisseur (modèle du moteur, prompt VLM).
    """
    if segmenter not in _HYBRID_SEGMENTERS:
        raise RunPlanningError(
            f"plan_hybrid_run : segmenteur inconnu {segmenter!r} "
            f"(attendu l'un de {sorted(_HYBRID_SEGMENTERS)})."
        )
    recognizer, reco_kwargs = _hybrid_recognizer(
        ocr,
        label=label,
        source_label=source_label,
        lang=lang,
        model=model,
        prompt=prompt,
    )
    # OCR réel par bloc → découpe l'image ; ``precomputed_region`` lit un texte
    # figé par ``region_id`` (page entière, aucun pixel) → pas de crop.
    crop = ocr != "precomputed_region"
    adapter_kwargs: _HybridKwargs = {recognizer: reco_kwargs}
    if segmenter == "remote_segmenter":
        if not endpoint:
            raise RunPlanningError(
                "remote_segmenter : 'endpoint' requis (cible object-detection)."
            )
        seg_kwargs: dict[str, str | int | float | bool] = {"endpoint": endpoint}
        if token:
            seg_kwargs["token"] = token
        adapter_kwargs[segmenter] = seg_kwargs
    return lambda _ws: _hybrid_spec(
        corpus,
        run_id,
        segmenter=segmenter,
        recognizer=recognizer,
        crop=crop,
        adapter_kwargs=adapter_kwargs,
    )


__all__ = [
    "SEGMENTER_KIND",
    "SEGMENTER_KINDS",
    "hybrid_recognizer_catalog",
    "plan_hybrid_run",
    "plan_segmentation_run",
]
