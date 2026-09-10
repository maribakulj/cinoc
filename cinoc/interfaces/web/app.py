"""Factory de l'application web (couche 8) — ``create_app()``.

L'app FastAPI est construite **à la demande**, jamais à l'import : pas de
``app = FastAPI()`` au niveau module (interdit par ``no_side_effect_imports`` —
``FastAPI``/``APIRouter`` sont des fabriques à effet de bord). uvicorn et le
HF Space reçoivent la **factory** (``--factory`` / callable), jamais un singleton
de module. Conséquence d'archi : un routeur est une **fonction qui construit et
renvoie un ``APIRouter``** (l'appel ``APIRouter()`` vit dans la fonction), montée
par ``create_app`` — voir les sous-tranches T4b+.

T4a pose la coquille : la factory + une route de santé. La surface (routers
benchmark/corpus, package ``security/``, SSE, annulation) se remplit ensuite,
une sous-tranche à la fois.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cinoc.adapters.storage import JobStore
from cinoc.adapters.storage.history_store import HistoryStore
from cinoc.adapters.storage.publisher import resolve_publisher
from cinoc.app import resolve_code_version
from cinoc.app.alto_store import AltoStore
from cinoc.app.corpus_import import (
    HF_AUTHOR_ENV,
    HF_TOKEN_ENVS,
    SPACE_ID_ENV,
    resolve_curated_author,
)
from cinoc.app.corpus_upload import CorpusStore
from cinoc.app.data_dir import resolve_data_dir
from cinoc.app.engines import (
    EngineStatus,
    correction_status,
    engine_statuses,
    ner_status,
    segmenter_statuses,
)
from cinoc.app.jobs import JobRunner
from cinoc.app.modules import (
    ModuleRegistry,
    discover_plugins,
    register_default_modules,
)
from cinoc.app.segmentation import SegmentationStore, demo_layout, demo_page_image
from cinoc.interfaces.web.catalog import seed_reports
from cinoc.interfaces.web.metrics import MetricsMiddleware, RequestMetrics
from cinoc.interfaces.web.routers.corpus import build_corpus_router
from cinoc.interfaces.web.routers.engines import build_engines_router
from cinoc.interfaces.web.routers.home import build_home_router
from cinoc.interfaces.web.routers.reports import build_reports_router
from cinoc.interfaces.web.routers.runs import build_runs_router
from cinoc.interfaces.web.routers.segmentation import build_segmentation_router
from cinoc.interfaces.web.security import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)

#: Assets de la coquille (CSS + polices auto-hébergées) et gabarits Jinja2,
#: livrés **dans le paquet** (cf. ``[tool.setuptools.package-data]``) pour être
#: présents aussi bien en source qu'une fois ``pip install``é (Space/CI).
_WEB_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _WEB_DIR / "static"
_TEMPLATES_DIR = _WEB_DIR / "templates"

#: Version du **contrat de transport HTTP** (évolue indépendamment du code métier ;
#: le déterminisme produit (§12) vit dans ``RunResult``, pas dans l'API).
API_VERSION = "0"

#: Dossier des rapports (``RunResult`` JSON) servis par la vitrine, surchargé par
#: ce var d'env (utile au Space) si ``create_app(reports_dir=...)`` ne le fixe pas.
REPORTS_DIR_ENV = "CINOC_REPORTS_DIR"

#: Mode public (exposition sans secrets) : refuse les moteurs cloud porteurs de
#: clé. Activé par cet env (truthy) si ``create_app(public_mode=...)`` ne tranche pas.
PUBLIC_MODE_ENV = "CINOC_PUBLIC_MODE"

#: Observabilité Prometheus **opt-in** : expose ``/metrics`` si truthy (un Space
#: exposé ne publie pas ses stats par défaut). Surchargé par ``create_app(metrics=)``.
METRICS_ENV = "CINOC_METRICS"

#: Compte HF dont les **datasets curés** (tag ``cinoc-corpus``) sont listés
#: automatiquement dans la Bibliothèque (sans coller le ``repo_id``). Override
#: explicite ; à défaut le handle est résolu **tout seul** (jeton/Space, cf.
#: ``_resolve_curated_author``). Aucun signal → section masquée (import manuel OK).

#: Jetons HF reconnus (ordre de lecture) : présent → on résout le handle de
#: l'opérateur via ``whoami`` → ses datasets curés apparaissent sans config.

#: Identifiant du Space (``owner/name``, injecté par HuggingFace). Son ``owner``
#: EST le handle de l'opérateur → datasets curés automatiques sur un Space, sans
#: jeton ni appel réseau pour la résolution.


def _resolve_reports_dir(reports_dir: Path | str | None) -> Path:
    """Argument explicite > variable d'env > défaut ``./reports``."""
    if reports_dir is not None:
        return Path(reports_dir)
    env = os.environ.get(REPORTS_DIR_ENV)
    return Path(env) if env else Path("reports")


def _resolve_uploads_dir(uploads_dir: Path | str | None) -> Path:
    """Dossier des corpus uploadés : argument explicite > dossier temporaire neuf.

    Éphémère par défaut (entrées de travail ; les résultats sont publiés à part).
    """
    if uploads_dir is not None:
        return Path(uploads_dir)
    return Path(tempfile.mkdtemp(prefix="cinoc-uploads-"))


def _resolve_public_mode(public_mode: bool | None) -> bool:
    """Mode public (verrou *fail-closed*) : arg explicite > env ``CINOC_PUBLIC_MODE``
    > ``False``.

    **Désactivé par défaut, partout — y compris sur un Space.** Une instance
    exécute ses moteurs (cloud compris) dès qu'une clé est présente, sans blocage :
    c'est l'opérateur qui maîtrise sa clé. Le verrou reste disponible **en option**
    via ``CINOC_PUBLIC_MODE=true`` (masque les moteurs cloud, refuse les imports
    distants, désactive la découverte de plugins tiers) — pour qui expose un Space
    **public** avec une clé qu'un visiteur ne doit pas pouvoir dépenser. ``false``
    ou absent ⇒ surface ouverte (l'opérateur assume l'exposition de sa clé ;
    cf. ``deploy/README_SPACE.md``).
    """
    if public_mode is not None:
        return public_mode
    return os.environ.get(PUBLIC_MODE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _resolve_metrics(metrics: bool | None) -> bool:
    """``/metrics`` : arg explicite > env ``CINOC_METRICS`` > ``False`` (off)."""
    if metrics is not None:
        return metrics
    return os.environ.get(METRICS_ENV, "").strip().lower() in {"1", "true", "yes"}


def create_app(
    *,
    reports_dir: Path | str | None = None,
    uploads_dir: Path | str | None = None,
    data_dir: Path | str | None = None,
    rate_limit: int = 60,
    public_mode: bool | None = None,
    metrics: bool | None = None,
) -> FastAPI:
    """Construit une **nouvelle** application web Cinoc.

    Appelée explicitement (CLI ``serve``, tests, Space) — jamais au chargement du
    module. Chaque appel renvoie une instance neuve (aucun état partagé global).
    Les routeurs sont des **fonctions builder** montées ici (jamais d'``APIRouter``
    au niveau module — gate ``no_side_effect_imports``). Toute réponse porte les
    en-têtes de sécurité (CSP stricte) ; le débit par IP est borné (``429``). Le
    **lanceur** (``/api/runs``) exécute les runs en arrière-plan via un
    ``JobRunner`` ; en ``public_mode`` les moteurs cloud sont refusés.
    """
    if rate_limit < 1:
        raise ValueError("create_app : rate_limit doit être >= 1.")
    catalog_dir = _resolve_reports_dir(reports_dir)
    # Dossier **inscriptible** (≠ rapports bakés, souvent root-only sur un Space) :
    # l'historique et le puits des rapports de run y vivent. On y recopie la graine
    # des rapports bakés → la vitrine sert depuis un seul dossier inscriptible.
    runtime_dir = resolve_data_dir(data_dir)
    seed_reports(catalog_dir, runtime_dir)
    is_public = _resolve_public_mode(public_mode)
    app = FastAPI(title="Cinoc", version=API_VERSION)
    # Ordre : le limiteur (ajouté en dernier) s'exécute en premier → il borne
    # avant tout traitement ; les en-têtes habillent la réponse qui remonte.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=rate_limit)

    # Observabilité opt-in : compte toutes les requêtes (middleware le plus
    # externe → voit même les 429) et expose `/metrics`. État par application.
    if _resolve_metrics(metrics):
        request_metrics = RequestMetrics()
        app.add_middleware(MetricsMiddleware, metrics=request_metrics)

        @app.get("/metrics")
        def metrics_endpoint() -> PlainTextResponse:
            """Exposition Prometheus (texte). Montée **seulement** si opt-in."""
            return PlainTextResponse(
                request_metrics.render(), media_type=request_metrics.content_type
            )

    @app.get("/health")
    def health() -> dict[str, str]:
        """Sonde de vivacité (orchestrateurs / Space). Aucune donnée sensible."""
        return {"status": "ok"}

    # Assets servis depuis notre origine (``font-src``/``style-src 'self'``) —
    # aucune dépendance CDN en prod (cf. CSP, ``security/headers.py``).
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=_TEMPLATES_DIR)

    # Lanceur : un registre + un store + un runner par application (état du
    # processus serveur, pas un singleton de module → factory respectée).
    registry = ModuleRegistry()
    register_default_modules(registry)
    # Découverte de modules tiers : DÉSACTIVÉE en mode public (fail-closed —
    # pas de chargement de code arbitraire in-process sur un serveur exposé).
    discover_plugins(registry, enabled=not is_public)
    # Historique longitudinal : un store SQLite par application ; le runner
    # y enregistre chaque run terminé, la page `/history` (rendu serveur) le lit.
    history_store = HistoryStore(runtime_dir / "history.db")
    # Segmentation : un store disque par application + une graine de **démo**
    # (layout + image de page). Le sink du runner y persiste les ``LAYOUT`` des
    # runs réels ; l'aperçu du lanceur (``/api/segmentation/preview``) rend le plus
    # récent (run réel > démo). Créé **avant** le runner pour le lui passer.
    seg_store = SegmentationStore(Path(tempfile.mkdtemp(prefix="cinoc-seg-")))
    # Graine de démo (layout + image) : l'aperçu du lanceur affiche ces régions
    # tant qu'aucun run réel n'a été lancé.
    seg_store.save(demo_layout(), image_ext=".png", image_bytes=demo_page_image())
    # Export ALTO : un store disque par application, indexé par run_id. Le sink du
    # runner y dépose les ``ALTO_XML`` produits ; le routeur des rapports les
    # rezippe à la demande (téléchargement par run).
    alto_store = AltoStore(Path(tempfile.mkdtemp(prefix="cinoc-alto-")))
    runner = JobRunner(
        store=JobStore(),
        registry=registry,
        reports_dir=runtime_dir,
        code_version=resolve_code_version(),
        # Persistance : actif uniquement si dépôt + jeton sont en secrets ;
        # sinon NoopPublisher → la vitrine read-only ne fait aucune sortie réseau.
        publisher=resolve_publisher(),
        history_store=history_store,
        segmentation_store=seg_store,
        alto_store=alto_store,
    )
    corpus_store = CorpusStore(_resolve_uploads_dir(uploads_dir))

    # Un seul fournisseur de statuts moteurs (même mode) partagé par le lanceur
    # et l'onglet Moteurs → pas de closures jumelles qui pourraient diverger.
    def engine_status_provider() -> tuple[EngineStatus, ...]:
        return engine_statuses()

    # Segmenteurs : catégorie distincte (pas dans le <select> moteur OCR), jamais
    # masquée en public (segmenteur local, pas de clé). Alimente le gate du run de
    # segmentation, le mode hybride du composeur et l'aperçu de mise en page.
    def segmenter_status_provider() -> tuple[EngineStatus, ...]:
        return segmenter_statuses()

    # Étape NER (extra [ner], spaCy) : catégorie distincte (post-traitement, pas
    # un moteur). Alimente le gate du lanceur et la case « NER » du composeur.
    def ner_status_provider() -> EngineStatus:
        return ner_status()

    # Post-correction structurée (extra [saknussemm]) : brique de
    # post-traitement, sondée comme la NER — refusée avant le lancement
    # plutôt qu'en plein run.
    def correction_status_provider() -> EngineStatus:
        return correction_status()

    app.include_router(
        build_home_router(
            runtime_dir,
            templates,
            statuses=engine_status_provider,
            segmenters=segmenter_status_provider,
            ner=ner_status_provider,
            history_store=history_store,
            corpus_store=corpus_store,
            curated_author=resolve_curated_author(),
            public_mode=is_public,
            alto_store=alto_store,
        )
    )
    app.include_router(build_reports_router(runtime_dir, alto_store=alto_store))
    app.include_router(
        build_segmentation_router(
            seg_store,
            runner=runner,
            corpus_store=corpus_store,
            segmenters=segmenter_status_provider,
        )
    )
    # Le lanceur exécute aussi les concurrents **hybrides** (segmenteur →
    # reconnaissance par bloc → texte scoré) : pas de second chemin d'exécution.
    # Les ALTO produits (option) se téléchargent via /reports/{run_id}/alto.zip.
    app.include_router(
        build_runs_router(
            runner,
            corpus_store,
            statuses=engine_status_provider,
            segmenters=segmenter_status_provider,
            ner_available=lambda: ner_status_provider().available,
            correction_available=lambda: correction_status_provider().available,
            public_mode=is_public,
        )
    )
    app.include_router(build_engines_router())
    app.include_router(build_corpus_router(corpus_store, public_mode=is_public))
    return app


__all__ = [
    "API_VERSION",
    "HF_AUTHOR_ENV",
    "HF_TOKEN_ENVS",
    "METRICS_ENV",
    "PUBLIC_MODE_ENV",
    "REPORTS_DIR_ENV",
    "SPACE_ID_ENV",
    "create_app",
]
