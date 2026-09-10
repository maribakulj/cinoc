"""Routeur vitrine : rendu d'un ``RunResult`` sauvé, en saveur **servie**.

Trois saveurs d'images coexistent, et cette route sert la troisième. Le rapport
**autonome** inline ses vignettes en data-URI, ce qui le plafonne à quelques
centaines de documents — au-delà, les suivants perdent leur aperçu **en
silence**. La saveur **dossier** (``bundle.zip``) écrit les dérivés à côté du
HTML. La saveur **servie** ne fait ni l'un ni l'autre : le HTML ne porte que des
**URL**, et les vignettes sont produites à la demande par
``/reports/{name}/image/{doc}``. Le navigateur ne charge que ce qu'il affiche
(les cartes portent déjà ``loading="lazy"``, et la galerie est paginée), donc un
run de milliers de pages se consulte sans plafond et sans HTML de plusieurs
dizaines de mégaoctets.

Le rapport lui-même n'a **rien** à savoir de tout ça : il reçoit un
``Mapping[document_id, href]``. C'est le seam qui rend les trois saveurs
possibles sans trois renderers.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from cinoc.adapters.images import thumbnail_bytes
from cinoc.app.alto_store import AltoStore
from cinoc.app.report_images import (
    build_report_zip,
    build_served_hrefs,
    image_ref_for,
)
from cinoc.app.results import RunResultError, load_run_result
from cinoc.app.security import PathSecurityError
from cinoc.interfaces.web.catalog import resolve_report
from cinoc.reports import default_report_renderer

#: Tailles servies : la vignette de galerie et le fac-similé de détail. Mêmes
#: valeurs que les saveurs inline/dossier — une même image doit avoir la même
#: définition quelle que soit la façon dont elle arrive au rapport.
_THUMBNAIL_PX = 280
_FACSIMILE_PX = 1100


def build_reports_router(
    reports_dir: Path, *, alto_store: AltoStore | None = None
) -> APIRouter:
    """Construit le routeur des rapports (monté par ``create_app``).

    ``alto_store`` (optionnel) sert les exports ALTO persistés d'un run via
    ``/reports/{name}/alto.zip`` ; absent → l'endpoint répond ``404``.
    """
    router = APIRouter()

    @router.get("/reports/{name}", response_class=HTMLResponse)
    def get_report(name: str, lang: str = "fr") -> str:
        try:
            path = resolve_report(reports_dir, name)
        except PathSecurityError as exc:
            # introuvable OU hors zone → même réponse (pas de fuite).
            raise HTTPException(status_code=404, detail="rapport introuvable") from exc
        try:
            result = load_run_result(path)
        except RunResultError as exc:
            raise HTTPException(status_code=500, detail="rapport illisible") from exc
        # Langue du glossaire pédagogique (fr par défaut ; en seul autre porté).
        report_lang = "en" if lang == "en" else "fr"
        quoted = quote(name, safe="")
        return default_report_renderer().render(
            result,
            title=f"Cinoc — {result.manifest.run_id}",
            lang=report_lang,
            images=build_served_hrefs(
                result,
                lambda doc: f"/reports/{quoted}/image/{quote(doc, safe='')}",
            ),
            facsimiles=build_served_hrefs(
                result,
                lambda doc: f"/reports/{quoted}/facsimile/{quote(doc, safe='')}",
            ),
        )


    def _document_image(name: str, document_id: str, max_px: int) -> Response:
        """Vignette JPEG d'un document, produite à la demande.

        ``document_id`` sert de **clé de recherche** dans le ``RunResult``, jamais
        de chemin : un identifiant inventé ne désigne rien, il ne peut pas
        désigner autre chose. Une image distante ou illisible donne ``404``,
        comme les autres saveurs donnent « pas de vignette » — le rapport
        retombe sur son aperçu synthétique.
        """
        try:
            path = resolve_report(reports_dir, name)
            result = load_run_result(path)
        except (PathSecurityError, RunResultError) as exc:
            raise HTTPException(status_code=404, detail="rapport introuvable") from exc
        ref = image_ref_for(result, document_id)
        if ref is None:
            raise HTTPException(status_code=404, detail="document sans image")
        raw = thumbnail_bytes(ref, max_px=max_px)
        if raw is None:
            raise HTTPException(status_code=404, detail="image indisponible")
        return Response(
            content=raw,
            media_type="image/jpeg",
            # Un run est **immuable** : ses vignettes le sont aussi. Le cache
            # évite de ré-encoder la même image à chaque défilement d'une
            # galerie de milliers de cartes.
            headers={"Cache-Control": "public, max-age=86400, immutable"},
        )

    @router.get("/reports/{name}/image/{document_id}")
    def get_document_image(name: str, document_id: str) -> Response:
        """Vignette de galerie (petite)."""
        return _document_image(name, document_id, _THUMBNAIL_PX)

    @router.get("/reports/{name}/facsimile/{document_id}")
    def get_document_facsimile(name: str, document_id: str) -> Response:
        """Fac-similé de détail (plus grand) — le drill-in d'un document."""
        return _document_image(name, document_id, _FACSIMILE_PX)

    @router.get("/reports/{name}/bundle.zip")
    def get_report_bundle(name: str, lang: str = "fr") -> Response:
        """Télécharge le rapport en **bundle dossier zippé** (saveur dossier) :
        ``report.html`` + ``report-assets/`` (images réelles, hors-ligne). Rendu
        à la demande depuis le ``RunResult`` sauvé — rien de pré-écrit."""
        try:
            path = resolve_report(reports_dir, name)
        except PathSecurityError as exc:
            raise HTTPException(status_code=404, detail="rapport introuvable") from exc
        try:
            result = load_run_result(path)
        except RunResultError as exc:
            raise HTTPException(status_code=500, detail="rapport illisible") from exc
        report_lang = "en" if lang == "en" else "fr"
        data = build_report_zip(
            result,
            render=default_report_renderer().render,
            title=f"Cinoc — {result.manifest.run_id}",
            lang=report_lang,
        )
        # ``name`` est déjà validé (resolve_report) → sûr en nom de fichier.
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{name}.zip"'
            },
        )

    @router.get("/reports/{name}/alto.zip")
    def get_alto_archive(name: str) -> Response:
        """Télécharge les **exports ALTO XML** du run (un fichier par document),
        empaquetés en ZIP — la forme ré-importable dans un outil de relecture
        (eScriptorium, Transkribus). ``404`` si le run n'a produit aucun ALTO
        (concurrent sans l'option *Exporter l'ALTO*)."""
        try:
            resolve_report(reports_dir, name)
        except PathSecurityError as exc:
            raise HTTPException(status_code=404, detail="rapport introuvable") from exc
        data = alto_store.archive(name) if alto_store is not None else None
        if data is None:
            raise HTTPException(
                status_code=404, detail="aucun export ALTO pour ce run"
            )
        # ``name`` est validé (resolve_report) → sûr en nom de fichier.
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{name}-alto.zip"'
            },
        )

    return router


__all__ = ["build_reports_router"]
