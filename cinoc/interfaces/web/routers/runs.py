"""Routeur du **lanceur** : lancer un run, suivre son état, l'annuler (couche 8).

``POST /api/runs`` lance une **file de recettes** (``entries``) sur un corpus du
dépôt (``corpus_id``) : N entrées → **un seul run** comparé. Une entrée est une
recette, ses briques, ses réglages et ses étapes facultatives ; OCR seul, OCR →
LLM, VLM, segmentation puis lecture, correction d'un ALTO — tout ce que la page
sait lancer passe par là, et par la fonction de ``cinoc run --recipe``
(``plan_recipe_run``, D-298). Sans entrée → le run de **démonstration**
(``precomputed``, local).

Ordre de garde (``_garder``, le même pour une spec déposée) : brique réservée à
la CLI → ``403`` ; montage incohérent → ``422`` ; cible hors liste blanche →
``403`` ; brique inconnue → ``422`` ; **mode public** hors du socle local et
gratuit (``PUBLIC_BRICK_KINDS``) → ``403``, avant toute sonde de clé ; modèle ou
réglage refusé, brique de rejeu sans aucun de ses fichiers → ``422`` ; brique
**indisponible** (binaire, SDK, clé, extra) → ``409``. Avant elles : corpus
introuvable → ``404``, recette mal formée (dont la vérité terrain extraite de
l'ALTO à corriger, ou un secret retiré et non ressaisi) → ``422``.

``GET`` restitue l'état ; ``cancel`` (le bouton « Arrêter ») déclenche l'annulation
coopérative. La spec complète est fermée en mode public. Un export de
configuration (``/api/runs/config``) ne porte jamais un secret. Écritures
protégées **CSRF**. Le ``RunResult`` produit atterrit dans le dossier vitrine.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from cinoc.adapters.storage import JobStore
from cinoc.app.corpus_upload import CorpusStore
from cinoc.app.demo import demo_spec_builder
from cinoc.app.engines import (
    CLI_ONLY_KINDS,
    PUBLIC_BRICK_KINDS,
    StatusProvider,
    instance_status,
)
from cinoc.app.evaluation_views import EvaluationOptions
from cinoc.app.jobs import JobRunner
from cinoc.app.models import ModelChoiceError, check_spec_models
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.modules.registry import (
    check_replay_sources,
    check_spec_settings,
)
from cinoc.app.recipe_catalog import recipe_catalog
from cinoc.app.recipe_queue import (
    RecipeEntry,
    exportable_entries,
    plan_recipe_run,
)
from cinoc.app.recipes import RecipeError, referenced_kinds, spec_for_corpus
from cinoc.app.security import HostNotAllowedError, check_endpoint_settings
from cinoc.app.spec_coherence import SpecCoherenceError
from cinoc.app.spec_coherence import check as coherence_check
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.run_spec import RunSpec
from cinoc.interfaces.web.security.csrf import csrf_protect


class ScoringFields(BaseModel):
    """Les options de notation de la page — **les mêmes** pour toute entrée
    (une seule politique de vues, D-297)."""

    normalization: str | None = Field(default=None, max_length=128)
    #: Caractères filtrés des deux côtés (GT/hyp) avant le calcul.
    char_exclude: str | None = Field(default=None, max_length=512)
    #: Colonnes de classement de la vue ``texte`` ; inconnu → 422 (plan).
    metric_profile: str | None = Field(default=None, max_length=64)
    #: Mode **détaillé** (analyses) ; rapide par défaut, comme en CLI.
    detailed_analyses: bool = False

    def options(self) -> EvaluationOptions:
        return EvaluationOptions(
            normalization=self.normalization,
            char_exclude=self.char_exclude,
            metric_profile=self.metric_profile,
            detailed_analyses=self.detailed_analyses,
        )


class LaunchRequest(ScoringFields):
    """Corps (optionnel) : une file de recettes + un corpus, ou rien (démo).

    L'utilisateur choisit l'intention (« segmenter, puis lire chaque bloc ») et
    les briques ; la forme, elle, vient de la recette. C'est aussi le format de
    l'export de configuration : il porte la file entière.
    """

    model_config = ConfigDict(extra="forbid")

    corpus_id: str | None = None
    entries: tuple[RecipeEntry, ...] = Field(default=(), max_length=16)


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
    public_mode: bool = False,
) -> APIRouter:
    """Construit le routeur du lanceur (monté par ``create_app``).

    ``statuses`` sonde **toutes** les briques (``recipe_catalog.brick_statuses``
    : moteurs, segmenteurs, prétraitement, NER, correction) : le catalogue grise
    ce qu'elle dit indisponible, le lanceur le refuse en ``409`` — une sonde,
    deux usages.

    ``public_mode`` (Space exposé) **verrouille** l'exécution au socle local et
    gratuit (``PUBLIC_BRICK_KINDS``) : tout moteur cloud, la correction (elle
    suppose un serveur LLM) ou tout autre kind est refusé en ``403``
    (fail-closed), sans jamais lancer un appel facturé.
    """
    router = APIRouter()

    @router.post(
        "/api/runs", status_code=201, dependencies=[Depends(csrf_protect)]
    )
    def launch_run(payload: LaunchRequest | None = None) -> dict[str, str]:
        req = payload or LaunchRequest()
        run_id = f"web-{uuid.uuid4().hex[:12]}"
        # Démonstration : aucune entrée → precomputed (local, jamais cloud).
        if not req.entries:
            if req.corpus_id is not None:
                raise HTTPException(
                    status_code=422,
                    detail="démonstration : ne s'exécute pas sur un corpus "
                    "(ajoute au moins une recette à la file).",
                )
            return {"job_id": runner.launch(demo_spec_builder(run_id))}
        if req.corpus_id is None:
            raise HTTPException(
                status_code=422,
                detail="une file de recettes s'exécute sur un corpus : "
                "choisis-en un.",
            )
        corpus = _corpus_du_depot(req.corpus_id)
        try:
            spec = plan_recipe_run(
                corpus, req.entries, run_id=run_id, options=req.options()
            )
        except RecipeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _garder(spec)
        return {"job_id": runner.launch(lambda _ws: spec)}

    def _refuser_cli(kinds: set[str]) -> None:
        """Refuse toute brique de ``CLI_ONLY_KINDS``, **quel que soit le mode**.

        Ces briques exécutent une commande décrite par la spec. Les laisser
        atteignables par HTTP reviendrait à offrir un shell — et « instance
        privée » veut dire « les gens que je connais », pas « les gens à qui je
        confie un shell ». D'où un refus inconditionnel, et une seule fonction :
        un second chemin de lancement qui oublierait la règle rouvrirait la
        porte en silence.
        """
        interdites = sorted(kinds & CLI_ONLY_KINDS)
        if interdites:
            raise HTTPException(
                status_code=403,
                detail="brique réservée à la ligne de commande : "
                f"{', '.join(interdites)} (elle exécute une commande décrite "
                "par la spec).",
            )

    def _garder(spec: RunSpec) -> None:
        """Applique à une spec les gardes du lanceur, dans le même ordre.

        Une spec composée à la main ne doit pas ouvrir une porte que le
        formulaire ferme : ce serait un contournement, pas une fonctionnalité.
        """
        # **Avant tout le reste.** Une brique qui exécute une commande lue dans
        # la spec ne doit jamais être atteignable par HTTP — sur une instance
        # publique comme privée. C'est un refus inconditionnel, pas un réglage,
        # et il passe avant les contrôles de cohérence : refuser un montage
        # incohérent serait déjà en avoir accepté l'exécution comme principe.
        _refuser_cli(referenced_kinds(spec))
        # Puis la cohérence du montage : une spec peut être typée juste et
        # décrire un assemblage qui ne fera pas ce qu'il annonce. Refusée en
        # 422, comme une brique inconnue — c'est la même famille d'erreur, et
        # elle se constate au même moment.
        try:
            coherence_check(spec)
        except SpecCoherenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # ``adapter_kwargs`` est libre : un ``host`` (ollama) ou un ``base_url``
        # (instance OpenAI-compatible) y ferait poster le serveur vers l'adresse
        # du choix du client, comme par la route de correction.
        for reglages in spec.adapter_kwargs.values():
            try:
                check_endpoint_settings(reglages, public_mode=public_mode)
            except HostNotAllowedError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
        sts = statuses()
        registre = ModuleRegistry()
        register_default_modules(registre)
        connus = {s.kind for s in sts} | set(registre.kinds())
        par_kind = {s.kind: s for s in sts}
        for kind in sorted(referenced_kinds(spec)):
            if kind not in connus:
                raise HTTPException(
                    status_code=422, detail=f"brique inconnue : {kind!r}"
                )
            if public_mode and kind not in PUBLIC_BRICK_KINDS:
                raise HTTPException(
                    status_code=403,
                    detail=f"brique indisponible en mode public : {kind!r} "
                    "(seul le socle local et gratuit est exécuté).",
                )
        # Aucun modèle par défaut : une instance sans modèle est refusée (422),
        # le message liste les disponibles — après les gardes d'accès (403),
        # pour qu'une spec refusée n'apprenne rien des fournisseurs.
        try:
            check_spec_models(spec, live=False)
        except ModelChoiceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # Chaque brique se construit avec ses réglages (sans rien exécuter) : un
        # réglage qu'elle ne déclare pas est refusé ici, nommé (422) — la règle
        # de ``cinoc run --check``, en couche ``app`` (D14 du pilote).
        try:
            check_spec_settings(spec, registre)
            # Une brique de rejeu sans aucun de ses fichiers : refusée ici,
            # plutôt qu'un job qui échoue page après page (D-299).
            check_replay_sources(spec, registre)
        except CinocError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # La disponibilité se juge **par instance** : une instance ``openai``
        # auto-hébergée (``base_url``) n'a pas besoin d'``OPENAI_API_KEY``. Une
        # brique hors catalogue moteur (projection, assembleur, vote…) n'a pas
        # de sonde : elle est intégrée, donc prête.
        for pipeline in spec.pipelines:
            for etape in pipeline.steps:
                statut = par_kind.get(etape.adapter_name.split(":", 1)[0])
                if statut is None:
                    continue
                try:
                    statut = instance_status(
                        statut, spec.adapter_kwargs.get(etape.adapter_name, {})
                    )
                except CinocError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                if not statut.available:
                    raise HTTPException(
                        status_code=409,
                        detail=f"brique indisponible : {statut.kind!r} "
                        f"({statut.detail})",
                    )

    def _corpus_du_depot(corpus_id: str) -> CorpusSpec:
        corpus = corpus_store.get(corpus_id)
        if corpus is None:
            raise HTTPException(status_code=404, detail="corpus introuvable")
        return corpus

    @router.get("/api/recipes")
    def list_recipes(lang: str = "fr") -> dict[str, object]:
        """Recettes livrées : forme, intention, et ce qu'il reste à choisir."""
        return {
            "recipes": recipe_catalog(
                lang, statuses=statuses(), public_mode=public_mode
            )
        }

    @router.post(
        "/api/runs/spec", status_code=201, dependencies=[Depends(csrf_protect)]
    )
    def launch_spec(payload: SpecRequest) -> dict[str, str]:
        """Lance une **spec complète** déposée par l'utilisateur.

        Le corpus vient du dépôt, jamais de la spec — la règle et sa raison
        vivent en couche ``app`` (``spec_for_corpus``), pour qu'un transport qui
        l'oublierait ne puisse pas rouvrir la porte en silence.

        **Fermée en mode public** (D-299) : une file de recettes est bornée (16
        entrées), une spec ne l'est pas — un visiteur anonyme y décrirait mille
        pipelines du socle gratuit. Une instance privée la garde ; la page y
        dépose un fichier.
        """
        if public_mode:
            raise HTTPException(
                status_code=403,
                detail="spec complète refusée en mode public : seule une file "
                "de recettes (bornée) s'exécute ici.",
            )
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
        "/api/runs/config", dependencies=[Depends(csrf_protect)]
    )
    def validate_config(payload: LaunchRequest) -> dict[str, object]:
        """Valide une **config de lanceur** (= un ``LaunchRequest``) et la renvoie
        sous forme **canonique**.

        Stateless : aucune persistance (Cinoc reste déterministe). Consommé par
        l'**import** côté client, qui valide ici le fichier déposé avant de
        repeupler le formulaire — un champ inconnu ou une borne dépassée tombe en
        ``422`` (Pydantic, ``extra="forbid"``), jamais un repeuplement muet.

        C'est aussi **l'export** : la page y fait passer sa file avant de la
        télécharger, et la forme canonique est **sans secret** — un réglage
        déclaré secret (le jeton du segmenteur distant) en est retiré et nommé
        (``withheld_secrets``), pour que l'import le redemande (D-299).
        """
        try:
            entries = exportable_entries(payload.entries)
        except RecipeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        canonique = payload.model_copy(update={"entries": entries})
        return {"config": canonique.model_dump(mode="json", exclude_none=True)}

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


__all__ = ["LaunchRequest", "build_runs_router"]
