"""Vignettes du rapport — orchestration (couche 6).

Résout les **références** image du ``RunResult`` (``RunDocumentResult.image_ref``)
en intrants de rendu, via l'adapter (couche 5, Pillow). Deux **saveurs** partagent
la même sélection (pires-CER d'abord, déterministe) et ne diffèrent que par la
façon de produire le href :

- **embedded** (``build_thumbnails``/``build_facsimiles``) → data-URI inliné,
  **plafonné** (borne le poids du rapport autonome) ; les octets ne touchent
  jamais le résultat.
- **sidecar / dossier** (``build_sidecar_*`` + ``write_report_bundle``) → dérivés
  écrits dans ``report-assets/``, hrefs **relatifs** ; **caps relâchés** (les
  octets sont sur disque, plus dans le HTML).
- **servie** (``build_served_hrefs``) → hrefs vers une **route** de l'app web, qui
  produit la vignette à la demande. **Aucun plafond** : rien n'est ni encodé ni
  écrit à l'avance, le navigateur ne charge que ce qu'il affiche (les cartes
  portent déjà ``loading="lazy"``). C'est la saveur des runs de milliers de pages,
  où inliner plafonnerait à quelques centaines de documents **en silence**.

Dégradé gracieux partout : ``{}`` si rien n'est résoluble (pas d'image, pas de
Pillow) ; aucune exception large.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from cinoc.adapters.images import thumbnail_data_uri, thumbnail_to_file
from cinoc.app.security import safe_stem
from cinoc.evaluation.result import RunResult

#: Plafond par défaut de documents vignettés (borne le poids du rapport autonome).
_DEFAULT_MAX_DOCS = 300
#: Fac-similés medium (détail) : plus grands → plafond plus serré.
_FACSIMILE_MAX_PX = 1100
_FACSIMILE_MAX_DOCS = 60
#: Variante de stem des fac-similés (medium) : évite la collision avec la vignette
#: du même document dans le même ``report-assets/``.
_FACSIMILE_SUFFIX = "-fac"


class ReportHtmlRenderer(Protocol):
    """Forme du renderer HTML injecté dans ``write_report_bundle`` (couche 7).

    ``app`` (couche 6) **n'importe pas** ``reports`` (couche 7) : le renderer est
    fourni par l'appelant (couche 8). Correspond à ``ReportRenderer.render``."""

    def __call__(
        self,
        result: RunResult,
        *,
        title: str,
        lang: str,
        images: Mapping[str, str],
        facsimiles: Mapping[str, str],
    ) -> str: ...


def _worst_first_doc_ids(result: RunResult) -> list[str]:
    """``document_id`` ordonnés par CER décroissant (pires-d'abord), déterministe."""
    worst: dict[str, float] = {}
    for d in result.documents:
        cer = next((s.value for s in d.scores if s.metric == "cer"), None)
        if cer is not None:
            worst[d.document_id] = max(worst.get(d.document_id, 0.0), cer)
    ordered = sorted(worst, key=lambda doc: (-worst[doc], doc))
    # Documents sans CER : ajoutés en fin, ordre d'apparition stable.
    for d in result.documents:
        if d.document_id not in worst and d.document_id not in ordered:
            ordered.append(d.document_id)
    return ordered


def _ordered_refs(
    result: RunResult, *, max_docs: int | None
) -> list[tuple[str, str]]:
    """``[(document_id, image_ref)]`` pires-d'abord, plafonné (``None`` = sans cap).

    Partage la sélection entre saveurs : un document → sa première référence ; tri
    pires-CER d'abord (déterministe) ; troncature au plafond si demandé."""
    refs: dict[str, str] = {}
    for d in result.documents:
        if d.image_ref and d.document_id not in refs:
            refs[d.document_id] = d.image_ref
    if not refs:
        return []
    selected = [doc for doc in _worst_first_doc_ids(result) if doc in refs]
    if max_docs is not None:
        selected = selected[:max_docs]
    return [(doc_id, refs[doc_id]) for doc_id in selected]


def build_thumbnails(
    result: RunResult, *, max_px: int = 280, max_docs: int = _DEFAULT_MAX_DOCS
) -> dict[str, str]:
    """``{document_id: data-URI}`` des vignettes résolues (plafonné, pires-d'abord)."""
    out: dict[str, str] = {}
    for doc_id, ref in _ordered_refs(result, max_docs=max_docs):
        uri = thumbnail_data_uri(ref, max_px=max_px)
        if uri is not None:
            out[doc_id] = uri
    return out


def build_facsimiles(
    result: RunResult,
    *,
    max_px: int = _FACSIMILE_MAX_PX,
    max_docs: int = _FACSIMILE_MAX_DOCS,
) -> dict[str, str]:
    """``{document_id: data-URI}`` des **fac-similés medium** (détail document).

    Même résolution que ``build_thumbnails`` mais plus grands et plus plafonnés
    (le détail montre une image, pas une grille)."""
    return build_thumbnails(result, max_px=max_px, max_docs=max_docs)


def _build_sidecar(
    result: RunResult,
    assets_dir: Path,
    *,
    max_px: int,
    suffix: str,
    max_docs: int | None,
) -> dict[str, str]:
    """``{document_id: href relatif}`` ; écrit un dérivé JPEG par document image.

    Les deux saveurs (vignette / fac-similé) ne diffèrent que par ``max_px`` et
    ``suffix`` — la résolution (``thumbnail_to_file``) est la même, appelée
    directement (pas d'indirection ``resolve``)."""
    out: dict[str, str] = {}
    for doc_id, ref in _ordered_refs(result, max_docs=max_docs):
        stem = safe_stem(doc_id, suffix=suffix, fallback="doc")
        href = thumbnail_to_file(ref, assets_dir, stem, max_px=max_px)
        if href is not None:
            out[doc_id] = href
    return out


def build_sidecar_thumbnails(
    result: RunResult,
    assets_dir: str | Path,
    *,
    max_px: int = 280,
    max_docs: int | None = None,
) -> dict[str, str]:
    """``{document_id: href relatif}`` ; écrit les vignettes dans ``assets_dir``.

    Saveur dossier : **caps relâchés** par défaut (``max_docs=None`` → tous les
    documents avec image) puisque les octets vivent sur disque, pas dans le HTML."""
    return _build_sidecar(
        result,
        Path(assets_dir),
        max_px=max_px,
        suffix="",
        max_docs=max_docs,
    )


def build_sidecar_facsimiles(
    result: RunResult,
    assets_dir: str | Path,
    *,
    max_px: int = _FACSIMILE_MAX_PX,
    max_docs: int | None = None,
) -> dict[str, str]:
    """``{document_id: href}`` des **fac-similés** écrits dans ``assets_dir``."""
    return _build_sidecar(
        result,
        Path(assets_dir),
        max_px=max_px,
        suffix=_FACSIMILE_SUFFIX,
        max_docs=max_docs,
    )


def write_report_bundle(
    result: RunResult,
    out_dir: str | Path,
    *,
    render: ReportHtmlRenderer,
    title: str = "Cinoc — rapport",
    lang: str = "fr",
) -> Path:
    """Écrit un **bundle dossier** : ``out_dir/report.html`` + ``report-assets/``.

    Saveur dossier : les images réelles sont des dérivés JPEG dans
    ``out_dir/report-assets/`` ; ``report.html`` ne porte que des **hrefs
    relatifs** (HTML léger, hors-ligne). Le ``render`` (couche 7) est **injecté**
    par l'appelant — ``app`` n'importe pas ``reports``. Renvoie le chemin du
    ``report.html`` écrit. Sans Pillow : aucun asset, le HTML retombe sur l'aperçu
    synthétique (dégradé gracieux, pas de crash)."""
    out = Path(out_dir)
    assets = out / "report-assets"
    images = build_sidecar_thumbnails(result, assets)
    facsimiles = build_sidecar_facsimiles(result, assets)
    html = render(result, title=title, lang=lang, images=images, facsimiles=facsimiles)
    out.mkdir(parents=True, exist_ok=True)
    report = out / "report.html"
    report.write_text(html, encoding="utf-8")
    return report


def build_report_zip(
    result: RunResult,
    *,
    render: ReportHtmlRenderer,
    title: str = "Cinoc — rapport",
    lang: str = "fr",
) -> bytes:
    """Bundle dossier **en mémoire** : un ZIP de ``report.html`` + ``report-assets/``.

    Même saveur dossier que :func:`write_report_bundle` (images réelles, hrefs
    relatifs, hors-ligne) mais empaquetée en octets ZIP — la forme téléchargeable
    depuis le web (le navigateur reçoit *un* fichier, l'utilisateur déballe un
    dossier). Le ``render`` (couche 7) est **injecté** (``app`` n'importe pas
    ``reports``). Déterministe : entrées triées. Dégradé gracieux sans Pillow
    (HTML + aperçu synthétique, aucun asset)."""
    with tempfile.TemporaryDirectory() as tmp:
        write_report_bundle(result, tmp, render=render, title=title, lang=lang)
        buffer = io.BytesIO()
        root = Path(tmp)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
        return buffer.getvalue()


def build_served_hrefs(
    result: RunResult, url_for: Callable[[str], str]
) -> dict[str, str]:
    """``{document_id: href}`` — saveur **servie**, sans plafond ni octets.

    ``url_for`` fabrique l'URL d'un document : la couche ``app`` ne connaît pas
    les routes de l'app web (couche 8), elle reçoit de quoi les nommer. Même
    sélection que les autres saveurs (``_ordered_refs``), mais **sans cap** —
    l'intérêt de cette saveur est précisément de ne plus en avoir : un href ne
    coûte rien tant que le navigateur ne le suit pas.

    Un document **sans** référence d'image reste absent du résultat, comme
    ailleurs : le rapport retombe alors sur l'aperçu synthétique plutôt que de
    pointer une route qui répondrait 404.
    """
    return {
        doc_id: url_for(doc_id)
        for doc_id, _ in _ordered_refs(result, max_docs=None)
    }


def image_ref_for(result: RunResult, document_id: str) -> str | None:
    """Référence d'image d'un document, ou ``None``.

    Résolue **depuis le ``RunResult``**, jamais depuis l'URL : l'identifiant reçu
    par la route sert de clé de recherche, pas de chemin. Un identifiant inventé
    ne désigne donc rien — il ne peut pas désigner autre chose.
    """
    for document in result.documents:
        if document.document_id == document_id and document.image_ref:
            return document.image_ref
    return None


__all__ = [
    "ReportHtmlRenderer",
    "build_facsimiles",
    "build_served_hrefs",
    "build_report_zip",
    "build_sidecar_facsimiles",
    "build_sidecar_thumbnails",
    "build_thumbnails",
    "image_ref_for",
    "write_report_bundle",
]
