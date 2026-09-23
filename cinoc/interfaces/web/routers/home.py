"""Routeur des **vues de la coquille** (couche 8) : accueil · Banc d'essai · Moteurs.

Rendu **serveur** (Jinja2 + tokens/polices du design) ; le Banc d'essai ajoute
un **JS léger auto-hébergé** (EventSource pour le SSE) — toujours pas de SPA. La
page « Moteurs » est, elle, **100 % rendue serveur** (aucun JS) : elle lit l'état
des moteurs (`app.engines`) côté serveur. Le rail réserve **tous** les
emplacements de nav ; les vivants sont liés, les autres restent « à venir ».
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from cinoc.adapters.corpus.htr_united import HTRUnitedCatalogue, fetch_catalogue
from cinoc.adapters.corpus.huggingface import (
    CuratedDatasetRef,
    HuggingFaceCatalogue,
    HuggingFaceDataset,
    discover_curated,
)
from cinoc.adapters.storage.history_store import HistoryRecord, HistoryStore
from cinoc.app import resolve_code_version
from cinoc.app.alto_store import AltoStore
from cinoc.app.corpus_upload import CorpusStore
from cinoc.app.engines import (
    EngineStatus,
    StatusProvider,
    curated_prompts,
    installed_mistral_models,
    installed_ollama_models,
)
from cinoc.app.history import series_insight
from cinoc.app.run_planning import benchmark_engine_catalog, metric_profile_catalog
from cinoc.app.structure_planning import hybrid_recognizer_catalog
from cinoc.formats.text import NORMALIZATION_PROFILES
from cinoc.interfaces.web._cache import TTLCache
from cinoc.interfaces.web.catalog import available_reports
from cinoc.interfaces.web.i18n import normalize_lang, strings_for
from cinoc.interfaces.web.sparkline import sparkline_svg

logger = logging.getLogger(__name__)

#: TTL des catalogues de découverte (F1) : la page Bibliothèque ne refetch plus
#: à chaque chargement. Fenêtre courte — la fraîcheur prime sur le cache.
_CATALOGUE_TTL_SECONDS = 300.0

#: Vues **vivantes** : id de nav → chemin. (La segmentation n'a plus de page
#: dédiée : elle se compose comme un concurrent *hybride* du Banc d'essai.)
_VIEW_PATHS = {
    "library": "/library",
    "reports": "/",
    "benchmark": "/benchmark",
    "history": "/history",
    "engines": "/engines",
}
_PRIMARY_NAV_IDS = ("library", "benchmark", "reports", "history")
_SECONDARY_NAV_IDS = ("engines",)


def _nav_items(
    ids: tuple[str, ...],
    t: dict[str, str],
    lang: str,
    active: str,
    metas: dict[str, str],
) -> list[dict[str, str]]:
    """Construit les entrées de navigation pour un groupe d'identifiants."""
    items: list[dict[str, str]] = []
    for nav_id in ids:
        items.append(
            {
                "id": nav_id,
                "label": t[f"nav_{nav_id}"],
                "state": "active" if nav_id == active else "link",
                "href": f"{_VIEW_PATHS[nav_id]}?lang={lang}",
                "meta": metas.get(nav_id, ""),
            }
        )
    return items


def _corpora_summaries(corpus_store: CorpusStore | None) -> list[dict[str, object]]:
    """Résumés des corpus enregistrés pour l'UI Bibliothèque/Benchmark."""
    if corpus_store is None:
        return []
    summaries: list[dict[str, object]] = []
    for cid, spec in corpus_store.list_corpora():
        docs = spec.documents
        summaries.append(
            {
                "id": cid,
                "name": spec.name,
                "n_documents": len(docs),
                "n_ground_truth": sum(1 for doc in docs if doc.ground_truths),
                "preview_ids": [doc.id for doc in docs[:3]],
                "source": spec.metadata.get("source", ""),
                "language": spec.metadata.get("language", ""),
            }
        )
    return summaries


def _cer_trends(
    history_store: HistoryStore, records: tuple[HistoryRecord, ...]
) -> list[dict[str, object]]:
    """Sparklines CER : une série chronologique par ``(pipeline, vue)``.

    Données réelles du store (``history``) — aucune ré-agrégation ici : la
    tendance OLS et la rupture (Pettitt) viennent d'``app.history`` (couche 6).
    Ordre stable (première apparition dans ``records``, plus récent d'abord).
    """
    seen: set[tuple[str, str]] = set()
    trends: list[dict[str, object]] = []
    for record in records:
        if record.metric != "cer":
            continue
        key = (record.pipeline, record.view)
        if key in seen:
            continue
        seen.add(key)
        series = history_store.history(record.pipeline, record.view, "cer")
        values = [s.value for s in series]
        insight = series_insight(series)
        trends.append(
            {
                "pipeline": record.pipeline,
                "view": record.view,
                "latest": values[-1] if values else None,
                "n": len(values),
                "svg": sparkline_svg(values),
                "slope": (
                    insight.trend.slope_per_day
                    if insight.trend is not None
                    else None
                ),
                "r_squared": (
                    insight.trend.r_squared if insight.trend is not None else None
                ),
                # Rupture affichée seulement si significative (p ≤ α) — le
                # test de Pettitt remplace le max-diff qui « trouvait » toujours.
                "rupture": (
                    {
                        "run_id": insight.rupture_run_id,
                        "delta": insight.rupture.delta,
                        "p_value": insight.rupture.p_value,
                    }
                    if insight.rupture is not None and insight.rupture.significant
                    else None
                ),
            }
        )
    return trends


def build_home_router(
    reports_dir: Path,
    templates: Jinja2Templates,
    *,
    statuses: StatusProvider,
    segmenters: StatusProvider,
    third_party: StatusProvider,
    ner: Callable[[], EngineStatus] | None = None,
    history_store: HistoryStore,
    corpus_store: CorpusStore | None = None,
    curated_author: str | None = None,
    public_mode: bool = False,
    alto_store: AltoStore | None = None,
) -> APIRouter:
    """Construit le routeur des vues de la coquille (monté par ``create_app``)."""
    router = APIRouter()
    app_version = resolve_code_version()
    # Caches TTL partagés par toutes les requêtes /library (F1) : fin du fetch
    # réseau à chaque chargement. HTR-United (index, indépendant de la requête)
    # et HuggingFace (par requête ``q``).
    htr_cache: TTLCache[str, HTRUnitedCatalogue] = TTLCache(_CATALOGUE_TTL_SECONDS)
    hf_cache: TTLCache[str, tuple[HuggingFaceDataset, ...]] = TTLCache(
        _CATALOGUE_TTL_SECONDS
    )
    # Datasets curés du compte HF configuré (``CINOC_HF_AUTHOR``) : découverts par
    # tag de convention, mis en cache TTL comme les autres catalogues distants.
    curated_cache: TTLCache[str, tuple[CuratedDatasetRef, ...]] = TTLCache(
        _CATALOGUE_TTL_SECONDS
    )

    def _base_context(
        lang: str, active: str, metas: dict[str, str]
    ) -> dict[str, object]:
        t = strings_for(lang)
        engine_list = tuple(statuses())
        n_ready = sum(1 for status in engine_list if status.available)
        engine_labels = [status.label for status in engine_list if status.available][:3]
        return {
            "lang": lang,
            "t": t,
            "primary_nav": _nav_items(_PRIMARY_NAV_IDS, t, lang, active, metas),
            "secondary_nav": _nav_items(_SECONDARY_NAV_IDS, t, lang, active, metas),
            "version": app_version,
            "view_path": _VIEW_PATHS[active],
            "system_pipeline": {
                "ready": n_ready,
                "total": len(engine_list),
                "labels": engine_labels,
            },
            # Les imports distants fetchent côté serveur → masqués en mode public
            # (l'endpoint les refuse de toute façon : 403).
            "public_mode": public_mode,
        }

    @router.get("/", response_class=HTMLResponse)
    def home(request: Request, lang: str = "fr") -> HTMLResponse:
        lang = normalize_lang(lang)
        names = available_reports(reports_dir)
        context = _base_context(lang, "reports", {"reports": str(len(names))})
        context["reports"] = [
            {
                "name": name,
                "href": f"/reports/{quote(name, safe='')}",
                "zip_href": f"/reports/{quote(name, safe='')}/bundle.zip",
                # Lien ALTO présent seulement si le run a produit un export (sinon
                # l'endpoint répondrait 404) → pas de bouton mort dans la liste.
                "alto_href": (
                    f"/reports/{quote(name, safe='')}/alto.zip"
                    if alto_store is not None and alto_store.has(name)
                    else None
                ),
            }
            for name in names
        ]
        context["n_reports"] = len(names)
        return templates.TemplateResponse(request, "home.html", context)

    @router.get("/benchmark", response_class=HTMLResponse)
    def benchmark(request: Request, lang: str = "fr") -> HTMLResponse:
        lang = normalize_lang(lang)
        context = _base_context(lang, "benchmark", {})
        # Catalogue moteurs par rôle (ocr/llm/vlm) : options rendues **serveur**
        # (testables) ; le composeur JS ne fait qu'assembler les concurrents.
        context["catalog"] = benchmark_engine_catalog(statuses())
        # Mode **hybride** du composeur : segmenteurs du socle + reconnaisseurs
        # par bloc (OCR réels + VLM zero-shot) — mêmes ensembles que le planner
        # accepte (anti-vide). Le « segmenteur → bloc → texte » devient un
        # concurrent scoré côte à côte avec les pipelines à plat.
        context["segmenters"] = list(segmenters())
        context["recognizers"] = hybrid_recognizer_catalog(statuses())
        # Modèles ollama installés → menu déroulant (au lieu d'une saisie à
        # l'aveugle). Best-effort : serveur éteint → liste vide, saisie libre.
        context["ollama_models"] = installed_ollama_models()
        # Modèles Mistral disponibles pour la clé → menu déroulant dynamique.
        context["mistral_models"] = installed_mistral_models()
        # Le corpus est préparé dans la Bibliothèque ; ici on le sélectionne.
        context["corpora"] = _corpora_summaries(corpus_store)
        # Profils de normalisation lus **dynamiquement** depuis formats/text
        # (jamais figés en dur) ; le profil choisi alimente la vue d'évaluation.
        context["profiles"] = [
            {"name": p.name, "description": p.description}
            for p in NORMALIZATION_PROFILES.values()
        ]
        # Profils de métriques (colonnes de classement de la vue ``text``) :
        # même source que le plan (anti-vide) ; libellé self-documenté côté form.
        context["metric_profiles"] = metric_profile_catalog()
        # Prompts curés par période (lus dynamiquement) → menu déroulant ; le
        # texte libre du formulaire reste prioritaire (résolu au plan).
        context["curated_prompts"] = list(curated_prompts())
        # Étape NER (extra [ner]) : son statut active/désactive la case « NER » du
        # composeur (désactivée + motif si spaCy absent).
        context["ner"] = ner() if ner is not None else None
        return templates.TemplateResponse(request, "benchmark.html", context)

    @router.get("/library", response_class=HTMLResponse)
    def library(request: Request, lang: str = "fr", q: str = "") -> HTMLResponse:
        lang = normalize_lang(lang)
        # Découverte best-effort : HTR-United (réseau → repli démo `is_demo`),
        # HuggingFace (socle de référence + API best-effort). Aucun blocage si
        # hors-ligne. Catalogues mis en cache TTL (F1) → pas de refetch par
        # chargement ; ``.search(q)`` de HTR-United reste en mémoire (gratuit).
        catalogue = htr_cache.get_or_compute("htr_united", fetch_catalogue)
        htr = catalogue.search(q) if q else catalogue.entries
        hf = hf_cache.get_or_compute(q, lambda: HuggingFaceCatalogue().search(q))
        # Datasets curés du compte configuré (apparaissent sans coller le repo_id).
        # Best-effort + TTL : compte absent → tuple vide (l'import manuel reste).
        curated: tuple[CuratedDatasetRef, ...] = ()
        if curated_author:
            author = curated_author
            curated = curated_cache.get_or_compute(
                author, lambda: discover_curated(author)
            )
        corpora = _corpora_summaries(corpus_store)
        context = _base_context(lang, "library", {"library": str(len(htr) + len(hf))})
        context["query"] = q
        context["corpora"] = corpora
        context["htr_entries"] = htr
        context["htr_is_demo"] = catalogue.is_demo
        context["hf_datasets"] = hf
        context["curated_datasets"] = curated
        context["n_corpora"] = len(corpora)
        context["n_htr"] = len(htr)
        context["n_hf"] = len(hf)
        context["n_pages"] = sum(int(c["n_documents"]) for c in corpora)  # type: ignore[call-overload]
        return templates.TemplateResponse(request, "library.html", context)

    @router.get("/history", response_class=HTMLResponse)
    def history(request: Request, lang: str = "fr") -> HTMLResponse:
        lang = normalize_lang(lang)
        try:
            records = history_store.all_records()
            # Régressions pour chaque (vue, métrique) enregistrée : lecture du
            # store, pas de ré-agrégation (cf. CLAUDE §8.3).
            pairs = sorted({(r.view, r.metric) for r in records})
            regressions = [
                reg
                for view, metric in pairs
                for reg in history_store.regressions(view, metric)
            ]
            trends = _cer_trends(history_store, records)
        except sqlite3.Error as exc:
            # Stockage indisponible (ex. dossier non inscriptible sur un Space) :
            # la page se dégrade au lieu de renvoyer une 500.
            logger.warning("[history] historique indisponible : %s", exc)
            records, regressions, trends = (), [], []
        context = _base_context(lang, "history", {"history": str(len(records))})
        context["records"] = records
        context["regressions"] = regressions
        context["trends"] = trends
        return templates.TemplateResponse(request, "history.html", context)

    @router.get("/engines", response_class=HTMLResponse)
    def engines(request: Request, lang: str = "fr") -> HTMLResponse:
        lang = normalize_lang(lang)
        engine_list = statuses()
        n_ready = sum(1 for s in engine_list if s.available)
        context = _base_context(lang, "engines", {"engines": str(n_ready)})
        context["engines"] = engine_list
        context["n_ready"] = n_ready
        context["n_engines"] = len(engine_list)
        # Les modules tiers ne sont pas dans le catalogue écrit à la main : ils
        # sont **découverts**. Les taire ici rompait la parité avec
        # ``cinoc list engines``, qui les montre (D-224).
        context["third_party"] = list(third_party())
        return templates.TemplateResponse(request, "engines.html", context)

    return router


__all__ = ["build_home_router"]
