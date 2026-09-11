"""Routeur du **lanceur** : lancer un run, suivre son état, l'annuler (couche 8).

``POST /api/runs`` choisit des **concurrents** (chacun = un pipeline : OCR seul,
OCR→LLM texte/image, ou VLM zero-shot) sur un **corpus** (``corpus_id``). N
concurrents → **un seul run** comparé (cross-engine). Sans concurrent → le run de
**démonstration** (``precomputed``, local).

Ordre de garde, par moteur référencé (``engine`` + ``llm``) :
1. moteur inconnu → ``422`` ;
2. **mode public** : moteur hors du socle gratuit (``PUBLIC_ENGINE_KINDS``) → ``403``
   (fail-closed) — les moteurs cloud (clé) et tout futur kind y tombent, même si une
   clé est posée ; seul ``tesseract`` (gratuit, local) reste exécutable publiquement ;
3. ``corpus_id`` fourni mais introuvable → ``404`` ;
4. moteur **indisponible** (binaire/SDK/clé absent) → ``409`` — hors mode public, un
   moteur cloud sans clé y tombe ; avec sa clé il est autorisé (clé posée → marche) ;
5. concurrent incohérent (mode⇄moteur) → ``422`` (``plan_benchmark_run``).

``GET`` restitue l'état ; ``cancel`` déclenche l'annulation coopérative. Écritures
protégées **CSRF**. Le ``RunResult`` produit atterrit dans le dossier vitrine.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from cinoc.adapters.storage import JobStore
from cinoc.app.corpus_upload import CorpusStore
from cinoc.app.correction_planning import (
    ground_truth_is_its_own_source,
    plan_correction_run,
)
from cinoc.app.demo import demo_spec_builder
from cinoc.app.engines import PUBLIC_ENGINE_KINDS, StatusProvider
from cinoc.app.jobs import JobRunner
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.recipes import (
    RecipeError,
    plan_recipe_run,
    recipe_catalog,
    referenced_kinds,
    spec_for_corpus,
)
from cinoc.app.run_planning import Competitor, RunPlanningError, plan_benchmark_run
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.run_spec import RunSpec
from cinoc.interfaces.web.security.csrf import csrf_protect


class LaunchRequest(BaseModel):
    """Corps (optionnel) : des concurrents + un corpus, ou rien (démonstration)."""

    model_config = ConfigDict(extra="forbid")

    competitors: tuple[Competitor, ...] = ()
    corpus_id: str | None = None
    normalization: str | None = None
    #: Caractères filtrés des deux côtés (GT/hyp) avant le calcul des métriques.
    char_exclude: str | None = Field(default=None, max_length=512)
    #: Nom d'un profil de métriques (``standard``/``essentiel``/``philologie``) :
    #: choisit les colonnes de classement de la vue ``text``. Inconnu → 422 (plan).
    metric_profile: str | None = Field(default=None, max_length=64)


class RecipeRequest(BaseModel):
    """Lancer une **recette** : une forme nommée, sur un corpus du dépôt.

    L'utilisateur choisit l'intention (« presse ancienne multi-colonnes ») et les
    briques ; la forme, elle, vient de la recette. C'est la voie ergonomique : le
    graphe admet des centaines de formes, elles ne rentrent pas dans un formulaire.
    """

    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    recipe: str = Field(min_length=1, max_length=64)
    #: Brique retenue par étape (``{"ocr": "tesseract"}``). Absente → le défaut
    #: de la recette.
    choices: dict[str, str] = Field(default_factory=dict)


class SpecRequest(BaseModel):
    """Lancer une **spec complète**, décrite en YAML ou en JSON.

    La porte qui donne au web l'intégralité du graphe sans une case de plus : on
    compose en YAML — ou on part d'une recette et on l'exporte pour la modifier —
    puis on dépose le fichier.

    **Le corpus n'est jamais celui de la spec.** Il vient du dépôt, par
    ``corpus_id`` : une spec porte des URI de fichiers, et les accepter d'un
    client ferait du lanceur un lecteur de disque à distance. La spec décrit donc
    les pipelines et l'évaluation ; le corpus, c'est le serveur qui le fournit.
    """

    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    #: Le document de spec, tel quel. YAML accepté (le JSON en est un sous-ensemble).
    spec: str = Field(min_length=1, max_length=200_000)


class CorrectionRequest(BaseModel):
    """Corps d'un run de **post-correction structurée** : un corpus, un producteur.

    Pas un ``Competitor`` : la correction n'est pas un moteur de plus dans la
    file du composeur, c'est une **autre forme de run** (ALTO déjà là → corrigé),
    planifiée par ``plan_correction_run``. Elle a donc sa route, comme la
    segmentation a la sienne.
    """

    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    #: ``rules`` (déterministe, hors ligne) ou ``ollama`` (serveur local).
    producer: str = Field(default="rules", max_length=32)
    #: Modèle ollama — **exigé** par le planificateur si ``producer == "ollama"``.
    model: str | None = Field(default=None, max_length=128)
    host: str = Field(default="http://localhost:11434", max_length=2048)


def _referenced_kinds(comp: Competitor) -> tuple[str, ...]:
    """Kinds qu'un concurrent met en jeu : moteur OCR/VLM + LLM éventuel."""
    return (comp.engine,) if comp.llm is None else (comp.engine, comp.llm)


def _parse_last_event_id(raw: str | None) -> int:
    """``Last-Event-ID`` (en-tête de reprise SSE) → entier ≥ 0, tolérant."""
    if raw is None:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _sse_stream(
    store: JobStore,
    job_id: str,
    last_event_id: int,
    *,
    poll: float = 0.1,
    idle_timeout: float = 30.0,
) -> Iterator[str]:
    """Diffuse le journal du job en SSE depuis ``last_event_id`` jusqu'au terminal.

    Boucle de *polling* (les transitions sont rares) ; rejoue d'abord les
    événements manqués (reprise ``Last-Event-ID``), puis suit les nouveaux. Un
    job déjà terminé renvoie tout l'historique puis ferme. Le ``idle_timeout``
    borne un job qui ne se terminerait jamais (pas de flux pendu en prod).
    """
    sent = last_event_id
    deadline = time.monotonic() + idle_timeout
    while True:
        for event_id, job in store.history_since(job_id, sent):
            sent = event_id
            payload = json.dumps(job.model_dump(mode="json"), ensure_ascii=False)
            yield f"id: {event_id}\nevent: {job.state.value}\ndata: {payload}\n\n"
            deadline = time.monotonic() + idle_timeout
        current = store.get(job_id)
        if current is not None and current.state.is_terminal:
            if not store.history_since(job_id, sent):
                return
        elif time.monotonic() > deadline:
            return
        time.sleep(poll)


def build_runs_router(
    runner: JobRunner,
    corpus_store: CorpusStore,
    *,
    statuses: StatusProvider,
    segmenters: StatusProvider | None = None,
    ner_available: Callable[[], bool] = lambda: True,
    correction_available: Callable[[], bool] = lambda: True,
    public_mode: bool = False,
) -> APIRouter:
    """Construit le routeur du lanceur (monté par ``create_app``).

    ``public_mode`` (Space exposé) **verrouille** l'exécution au seul socle
    first-party gratuit (``PUBLIC_ENGINE_KINDS``) : tout moteur cloud ou autre kind
    est refusé en ``403`` (fail-closed), sans jamais lancer un appel facturé.

    ``ner_available`` sonde la dispo de l'étape NER (extra ``[ner]``, spaCy) : un
    concurrent NER demandé sans la lib tombe en ``409`` **avant** le lancement
    (plutôt qu'un échec d'étape en cours de run). spaCy étant local first-party,
    la NER reste autorisée en mode public.

    ``correction_available`` fait de même pour la **post-correction structurée**
    (extra ``[saknussemm]``). Elle est en revanche **refusée en mode public** :
    son producteur utile parle à un serveur LLM local, qu'un Space exposé n'a
    pas, et le producteur ``rules`` seul ne justifie pas d'ouvrir la surface.
    """
    router = APIRouter()

    @router.post(
        "/api/runs", status_code=201, dependencies=[Depends(csrf_protect)]
    )
    def launch_run(payload: LaunchRequest | None = None) -> dict[str, str]:
        req = payload or LaunchRequest()
        run_id = f"web-{uuid.uuid4().hex[:12]}"
        # Démonstration : aucun concurrent → precomputed (local, jamais cloud).
        if not req.competitors:
            if req.corpus_id is not None:
                raise HTTPException(
                    status_code=422,
                    detail="démonstration : ne s'exécute pas sur un corpus "
                    "(sélectionne au moins un concurrent).",
                )
            return {"job_id": runner.launch(demo_spec_builder(run_id))}

        sts = statuses()
        known = {s.kind for s in sts}
        available = {s.kind for s in sts if s.available}
        # 1 : moteur connu (la disponibilité runtime — binaire/SDK/clé — est
        # vérifiée à l'étape 4 : un moteur cloud sans clé y tombe en 409).
        for comp in req.competitors:
            for kind in _referenced_kinds(comp):
                if kind not in known:
                    raise HTTPException(
                        status_code=422, detail=f"moteur inconnu : {kind!r}"
                    )
        # 2 : mode public → fail-closed sur le socle gratuit. Refusé AVANT toute
        # vérification de clé/dispo : un moteur cloud ne doit pas même être tenté
        # sur une instance publique (aucun appel facturé), clé présente ou non.
        if public_mode:
            for comp in req.competitors:
                for kind in _referenced_kinds(comp):
                    if kind not in PUBLIC_ENGINE_KINDS:
                        raise HTTPException(
                            status_code=403,
                            detail=f"moteur indisponible en mode public : {kind!r} "
                            "(seul le socle gratuit est exécuté).",
                        )
        # 3 : corpus.
        corpus: CorpusSpec | None = None
        if req.corpus_id is not None:
            corpus = corpus_store.get(req.corpus_id)
            if corpus is None:
                raise HTTPException(status_code=404, detail="corpus introuvable")
        # 4 : disponibilité runtime (binaire/SDK/clé).
        for comp in req.competitors:
            for kind in _referenced_kinds(comp):
                if kind not in available:
                    raise HTTPException(
                        status_code=409, detail=f"moteur indisponible : {kind!r}"
                    )
        # 4ter : concurrent hybride → le **segmenteur** doit être disponible (extra
        # [segment] / endpoint). Catégorie distincte des moteurs OCR (provider
        # dédié) ; jamais masqué en mode public (local/délégué, pas de clé exposée).
        seg_available = (
            {s.kind for s in segmenters() if s.available}
            if segmenters is not None
            else set()
        )
        for comp in req.competitors:
            if comp.segmenter and comp.segmenter not in seg_available:
                raise HTTPException(
                    status_code=409,
                    detail=f"segmenteur indisponible : {comp.segmenter!r}",
                )
        # 4bis : étape NER demandée → exiger spaCy (extra [ner]) AVANT le lancement.
        if any(comp.ner for comp in req.competitors) and not ner_available():
            raise HTTPException(
                status_code=409,
                detail="étape NER indisponible : installer 'cinoc[ner]' (spaCy).",
            )
        # 5 : cohérence mode⇄moteur (dispatch exhaustif).
        try:
            build = plan_benchmark_run(
                req.competitors,
                corpus,
                run_id,
                normalization=req.normalization,
                char_exclude=req.char_exclude,
                metric_profile=req.metric_profile,
            )
        except RunPlanningError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"job_id": runner.launch(build)}



    def _garder(spec: RunSpec) -> None:
        """Applique à une spec les gardes du lanceur, dans le même ordre.

        Une spec composée à la main ne doit pas ouvrir une porte que le
        formulaire ferme : ce serait un contournement, pas une fonctionnalité.
        """
        sts = statuses()
        registre = ModuleRegistry()
        register_default_modules(registre)
        connus = {s.kind for s in sts} | set(registre.kinds())
        disponibles = {s.kind for s in sts if s.available}
        for kind in sorted(referenced_kinds(spec)):
            if kind not in connus:
                raise HTTPException(
                    status_code=422, detail=f"brique inconnue : {kind!r}"
                )
            if public_mode and kind not in PUBLIC_ENGINE_KINDS:
                raise HTTPException(
                    status_code=403,
                    detail=f"brique indisponible en mode public : {kind!r} "
                    "(seul le socle gratuit est exécuté).",
                )
            # Une brique hors catalogue moteur (projection, assembleur, vote…)
            # n'a pas de sonde de disponibilité : elle est intégrée, donc prête.
            if kind in {s.kind for s in sts} and kind not in disponibles:
                raise HTTPException(
                    status_code=409, detail=f"brique indisponible : {kind!r}"
                )

    def _corpus_du_depot(corpus_id: str) -> CorpusSpec:
        corpus = corpus_store.get(corpus_id)
        if corpus is None:
            raise HTTPException(status_code=404, detail="corpus introuvable")
        return corpus

    @router.get("/api/recipes")
    def list_recipes(lang: str = "fr") -> dict[str, object]:
        """Recettes livrées : forme, intention, et ce qu'il reste à choisir."""
        return {"recipes": recipe_catalog(lang)}

    @router.post(
        "/api/runs/recipe", status_code=201, dependencies=[Depends(csrf_protect)]
    )
    def launch_recipe(payload: RecipeRequest) -> dict[str, str]:
        """Lance une recette sur un corpus du dépôt."""
        corpus = _corpus_du_depot(payload.corpus_id)
        try:
            spec = plan_recipe_run(
                corpus,
                payload.recipe,
                run_id=f"web-rec-{uuid.uuid4().hex[:12]}",
                choices=payload.choices,
            )
        except RecipeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _garder(spec)
        return {"job_id": runner.launch(lambda _ws: spec)}

    @router.post(
        "/api/runs/spec", status_code=201, dependencies=[Depends(csrf_protect)]
    )
    def launch_spec(payload: SpecRequest) -> dict[str, str]:
        """Lance une **spec complète** déposée par l'utilisateur.

        Le corpus vient du dépôt, jamais de la spec — la règle et sa raison
        vivent en couche ``app`` (``spec_for_corpus``), pour qu'un transport qui
        l'oublierait ne puisse pas rouvrir la porte en silence.
        """
        corpus = _corpus_du_depot(payload.corpus_id)
        try:
            spec = spec_for_corpus(
                payload.spec, corpus, run_id=f"web-spec-{uuid.uuid4().hex[:12]}"
            )
        except RecipeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _garder(spec)
        return {"job_id": runner.launch(lambda _ws: spec)}

    @router.post(
        "/api/runs/correction",
        status_code=201,
        dependencies=[Depends(csrf_protect)],
    )
    def launch_correction(payload: CorrectionRequest) -> dict[str, str]:
        """Lance une **post-correction structurée** sur un corpus d'ALTO.

        Ordre de garde, du plus général au plus spécifique — chaque refus nomme
        sa cause, aucun ne retombe sur un défaut muet :

        1. mode public → ``403`` (le producteur utile exige un LLM local) ;
        2. bibliothèque absente → ``409`` (avant le lancement, pas en plein run) ;
        3. corpus introuvable → ``404`` ;
        4. **vérité terrain dérivée de l'ALTO** → ``422``. C'est le refus qui
           compte : sans lui, le banc compare le texte à lui-même et publie un
           verdict inversé. Voir ``ground_truth_is_its_own_source``.
        5. producteur incohérent (``ollama`` sans modèle) → ``422`` (plan).
        """
        if public_mode:
            raise HTTPException(
                status_code=403,
                detail="post-correction refusée en mode public (elle suppose un "
                "serveur LLM local).",
            )
        if not correction_available():
            raise HTTPException(
                status_code=409,
                detail="post-correction indisponible : extra [saknussemm] non "
                "installé (le paquet n'est pas publié sur PyPI, il s'installe "
                "depuis son dépôt).",
            )
        corpus = corpus_store.get(payload.corpus_id)
        if corpus is None:
            raise HTTPException(status_code=404, detail="corpus introuvable.")
        if ground_truth_is_its_own_source(corpus):
            raise HTTPException(
                status_code=422,
                detail="la vérité terrain de ce corpus est extraite de son "
                "propre ALTO : le correcteur partirait du texte auquel on le "
                "compare, et le CER vaudrait zéro par construction. Dépose une "
                "transcription à part (<nom>.gt.txt) à côté de chaque ALTO.",
            )
        run_id = f"web-corr-{uuid.uuid4().hex[:12]}"
        try:
            spec = plan_correction_run(
                corpus,
                run_id,
                producer=payload.producer,
                model=payload.model or "",
                host=payload.host,
            )
        except CinocError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"job_id": runner.launch(lambda _ws: spec)}

    @router.post(
        "/api/runs/config", dependencies=[Depends(csrf_protect)]
    )
    def validate_config(payload: LaunchRequest) -> dict[str, object]:
        """Valide une **config de lanceur** (= un ``LaunchRequest``) et la renvoie
        sous forme **canonique**.

        Stateless : aucune persistance (Cinoc reste déterministe). Consommé par
        l'**import** côté client, qui valide ici le fichier déposé avant de
        repeupler le formulaire — un champ inconnu ou une borne dépassée tombe en
        ``422`` (Pydantic, ``extra="forbid"``), jamais un repeuplement muet.
        """
        return {"config": payload.model_dump(mode="json", exclude_none=True)}

    @router.get("/api/runs/{job_id}")
    def get_run(job_id: str) -> dict[str, object]:
        job = runner.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job introuvable")
        return job.model_dump(mode="json")

    @router.get("/api/runs/{job_id}/events")
    def run_events(job_id: str, request: Request) -> StreamingResponse:
        if runner.store.get(job_id) is None:
            raise HTTPException(status_code=404, detail="job introuvable")
        last = _parse_last_event_id(request.headers.get("last-event-id"))
        return StreamingResponse(
            _sse_stream(runner.store, job_id, last),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post(
        "/api/runs/{job_id}/cancel", dependencies=[Depends(csrf_protect)]
    )
    def cancel_run(job_id: str) -> dict[str, bool]:
        if runner.store.get(job_id) is None:
            raise HTTPException(status_code=404, detail="job introuvable")
        return {"cancelled": runner.cancel(job_id)}

    return router


__all__ = ["Competitor", "LaunchRequest", "build_runs_router"]
