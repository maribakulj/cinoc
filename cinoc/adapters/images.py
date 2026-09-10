"""Vignettes du rapport : image → dérivé JPEG redimensionné (couche 5, adapter).

Le redimensionnement utilise **Pillow** (interdit en ``reports`` — couche 7) ; il
vit donc ici. Deux saveurs partagent le **même cœur** ``_render_jpeg`` :

- ``thumbnail_data_uri`` → **data-URI** embarqué dans le HTML (saveur fichier
  unique) ; les octets ne touchent jamais le ``RunResult``.
- ``thumbnail_to_file`` → écrit le dérivé dans un dossier d'assets et renvoie un
  **href relatif** (saveur dossier : HTML léger à liens relatifs).

**Dégradé gracieux** : si Pillow n'est pas installé (extra ``[images]``), si le
fichier manque ou est illisible → ``None`` (le rapport retombe sur l'aperçu
synthétique). Aucune exception large.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def thumbnail_bytes(source: str | Path, *, max_px: int = 280) -> bytes | None:
    """Octets JPEG d'une image locale redimensionnée ; ``None`` si indisponible.

    Cœur partagé des **trois** saveurs — data-URI (fichier unique), fichier
    (dossier) et **servie** (le web renvoie ces octets tels quels) : redimensionne
    pour que le
    plus grand côté ≤ ``max_px`` (jamais agrandi), convertit en RGB, encode JPEG.
    ``None`` (avec ``logger.warning``) si Pillow absent, fichier introuvable, ou
    image illisible — le rendu reste fonctionnel (aperçu synthétique)."""
    path = Path(source)
    if not path.is_file():
        return None
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        logger.warning(
            "[images] Pillow indisponible (%s) — vignettes omises, aperçu "
            "synthétique. Installer l'extra ``[images]``.",
            exc,
        )
        return None
    try:
        with Image.open(path) as opened:
            rgb = opened.convert("RGB")
            rgb.thumbnail((max_px, max_px))
            buffer = io.BytesIO()
            rgb.save(buffer, format="JPEG", quality=82, optimize=True)
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("[images] image illisible %s : %s — vignette omise.", path, exc)
        return None
    return buffer.getvalue()


def thumbnail_data_uri(source: str | Path, *, max_px: int = 280) -> str | None:
    """Vignette JPEG **data-URI** d'une image locale ; ``None`` si indisponible.

    Saveur fichier unique : les octets sont inlinés dans le HTML. ``None`` si le
    dérivé n'a pu être produit (Pillow absent, fichier manquant/illisible)."""
    raw = thumbnail_bytes(source, max_px=max_px)
    if raw is None:
        return None
    payload = base64.b64encode(raw).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def thumbnail_to_file(
    source: str | Path, dest_dir: str | Path, stem: str, *, max_px: int = 280
) -> str | None:
    """Écrit la vignette JPEG dans ``dest_dir/<stem>.jpg`` ; renvoie un href relatif.

    Saveur dossier : le dérivé est **un fichier sur disque** (pas inliné), le HTML
    n'en porte qu'une **référence relative**. L'href renvoyé est relatif au
    **parent** de ``dest_dir`` (``f"{dest_dir.name}/{stem}.jpg"``, séparateur ``/``
    portable) : l'appelant garantit que le HTML est un voisin de ``dest_dir`` (cf.
    ``app.report_images.write_report_bundle``). ``None`` si le dérivé n'a pu être
    produit (dégradé gracieux, aucun fichier écrit, aucun dossier créé)."""
    raw = thumbnail_bytes(source, max_px=max_px)
    if raw is None:
        return None
    folder = Path(dest_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}.jpg").write_bytes(raw)
    return f"{folder.name}/{stem}.jpg"


def iiif_derivative(
    source: str | Path, dest_path: str | Path, *, width: int
) -> tuple[int, int] | None:
    """Écrit un dérivé JPEG de **largeur exacte** ``width`` (jamais agrandi) à
    ``dest_path`` ; renvoie ``(largeur, hauteur)`` réels, ou ``None`` (dégradé).

    Variante **largeur-fixe** de ``_render_jpeg`` (qui borne le plus grand côté) :
    une taille IIIF Image API ``full/{w},/`` exige une largeur exacte, pas un
    cadrage. Convertit en RGB, ré-échantillonne (Lanczos), crée les dossiers
    parents. ``None`` (avec ``logger.warning``) si Pillow absent, fichier
    introuvable ou image illisible — l'outil appelant décide d'échouer ou non."""
    path = Path(source)
    if not path.is_file():
        logger.warning("[images] image introuvable %s — dérivé IIIF omis.", path)
        return None
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        logger.warning(
            "[images] Pillow indisponible (%s) — dérivé IIIF omis. Extra ``[images]``.",
            exc,
        )
        return None
    try:
        with Image.open(path) as opened:
            rgb = opened.convert("RGB")
            orig_w, orig_h = rgb.size
            target_w = min(width, orig_w)  # jamais agrandi
            target_h = max(1, round(orig_h * target_w / orig_w))
            resized = rgb.resize((target_w, target_h), Image.Resampling.LANCZOS)
            dest = Path(dest_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            resized.save(dest, format="JPEG", quality=82, optimize=True)
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning(
            "[images] image illisible %s : %s — dérivé IIIF omis.", path, exc
        )
        return None
    return (target_w, target_h)


__all__ = [
    "iiif_derivative",
    "thumbnail_bytes",
    "thumbnail_data_uri",
    "thumbnail_to_file",
]
