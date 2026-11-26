"""Routeur **segmentation** (couche 8) : lancer un run + visualiser un layout.

Sert l'**aperçu de mise en page** du composeur (Banc d'essai) : on lance un run de
segmentation sur un corpus, puis on affiche les régions détectées. Il n'y a **plus
de page `/segmentation` dédiée** — la segmentation se compose comme un concurrent
*hybride* du Banc d'essai (seg → reconnaissance par bloc → texte scoré), et la
visualisation des régions est un **panneau du lanceur** alimenté par ces endpoints.

- ``POST /api/segmentation/run`` (JSON, **CSRF**) lance un run via le **même**
  ``JobRunner`` que les runs OCR (le sink persiste le ``CanonicalLayout``) ; renvoie
  ``{job_id, run_id}``. Gate : segmenteur indisponible → ``409``. **Pas** de masquage
  mode public (local/délégué, ni clé ni SSRF).
- ``GET /api/segmentation/{id}/image`` restitue l'image de page persistée.
- ``GET /api/segmentation/{id}/view`` rend le **SVG des régions** (fragment serveur).
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from cinoc.app.corpus_upload import CorpusStore
from cinoc.app.engines import StatusProvider
from cinoc.app.jobs import JobRunner
from cinoc.app.segmentation import SegmentationStore
from cinoc.app.structure_planning import (
    SEGMENTER_KIND,
    RunPlanningError,
    plan_segmentation_run,
    segmenter_kinds,
)
from cinoc.formats.images import image_media_type
from cinoc.interfaces.web.security.csrf import csrf_protect
from cinoc.reports.layout_svg import layout_to_svg


class SegmentationRunRequest(BaseModel):
    """Corps d'``POST /api/segmentation/run`` : corpus + segmenteur choisi.

    ``segmenter`` sélectionne le module (``pp_doclayout`` local par défaut, ou
    ``remote_segmenter`` distant). Pour le distant, ``endpoint`` est requis (cible
    object-detection HF) et ``token`` optionnel (auth) — c'est ce qui rend un
    segmenteur tiers **sélectionnable avant le run** sans rien réinstaller.
    """

    model_config = ConfigDict(extra="forbid")

    corpus_id: str = Field(min_length=1, max_length=128)
    segmenter: str = Field(default=SEGMENTER_KIND, max_length=64)
    endpoint: str | None = Field(default=None, max_length=2048)
    token: str | None = Field(default=None, max_length=512)


def build_segmentation_router(
    store: SegmentationStore,
    *,
    runner: JobRunner,
    corpus_store: CorpusStore,
    segmenters: StatusProvider,
) -> APIRouter:
    """Construit le routeur segmentation (monté par ``create_app``)."""
    router = APIRouter()

    @router.post(
        "/api/segmentation/run",
        status_code=201,
        dependencies=[Depends(csrf_protect)],
    )
    def launch_segmentation(req: SegmentationRunRequest) -> dict[str, str]:
        if req.segmenter not in segmenter_kinds():
            raise HTTPException(
                status_code=422, detail=f"segmenteur inconnu : {req.segmenter}"
            )
        status = next(
            (s for s in segmenters() if s.kind == req.segmenter), None
        )
        if status is None or not status.available:
            detail = status.detail if status else "segmenteur inconnu"
            raise HTTPException(
                status_code=409, detail=f"segmenteur indisponible : {detail}"
            )
        corpus = corpus_store.get(req.corpus_id)
        if corpus is None:
            raise HTTPException(status_code=404, detail="corpus introuvable")
        run_id = f"seg-{uuid.uuid4().hex[:12]}"
        try:
            plan = plan_segmentation_run(
                corpus,
                run_id,
                segmenter=req.segmenter,
                endpoint=req.endpoint,
                token=req.token,
            )
        except RunPlanningError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"job_id": runner.launch(plan)}

    @router.get("/api/segmentation/{seg_id}/image")
    def segmentation_image(seg_id: str) -> FileResponse:
        path = store.image_path(seg_id)  # id validé en amont → None hors zone
        if path is None:
            raise HTTPException(status_code=404, detail="image introuvable")
        # Type de la table des imports ; hors table, binaire opaque.
        media = image_media_type(path.suffix) or "application/octet-stream"
        return FileResponse(path, media_type=media)

    @router.get("/api/segmentation/preview", response_class=HTMLResponse)
    def segmentation_preview() -> HTMLResponse:
        # Fragment SVG des régions du **dernier** layout persisté (rendu serveur,
        # déterministe) : l'aperçu du lanceur l'injecte une fois le run terminé.
        # Le sink clé le store par id propre (≠ run_id) → on lit le plus récent,
        # comme le faisait l'ancienne page /segmentation (mono-opérateur).
        seg_id = store.latest()
        layout = store.get_layout(seg_id) if seg_id is not None else None
        if seg_id is None or layout is None:
            raise HTTPException(status_code=404, detail="aucune segmentation")
        image_href = f"/api/segmentation/{quote(seg_id, safe='')}/image"
        return HTMLResponse(layout_to_svg(layout, image_href=image_href))

    return router


__all__ = ["SegmentationRunRequest", "build_segmentation_router"]
