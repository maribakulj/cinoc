"""Formats d'image d'une page — **la** table des extensions qu'un import accepte.

Cinq copies vivaient en couches 5 et 6 (import distant, ZIP web, dossier à
transcrire, corpus ALTO, Hugging Face) et divergeaient : ``.jp2`` accepté par
quatre, ``.webp`` par une seule — un même fichier entrait par une porte et
était refusé par l'autre (S29a). Une seule source, ici, en couche 2 : le format
d'un fichier de page est du vocabulaire de format, comme ALTO ou PAGE.

**L'ensemble** — PNG, JPEG, TIFF, JPEG 2000 (``.jp2``), WebP : ce que les
moteurs qui lisent les pixels ici lisent **réellement**. Pillow (extra
``[images]``, image du Space) décode les cinq, JPEG 2000 et WebP compris
(``PIL.features.check("jpg_2000")`` et ``("webp")`` vrais sur ses roues) ;
Tesseract les lit par Leptonica (``libopenjp2``, ``libwebp`` sur sa bannière
``--version``). GIF, BMP et le flux JPEG 2000 nu (``.j2k``) n'en sont pas : un
fac-similé patrimonial n'y est pas publié, et chaque format admis est une
surface de décodage de plus pour une entrée non fiable.

``looks_like_image`` vérifie la **signature** des octets (un ZIP déposé dit
l'extension qu'il veut) : rien n'est décodé. ``image_media_type`` donne le type
MIME d'une extension acceptée — celui que les moteurs annoncent en envoyant la
page (VLM, Mistral OCR, OCR-D) et que l'app web sert : quatre tables le
recopiaient sans ``.jp2``, et un JPEG 2000 partait annoncé ``image/png`` (D-303).
"""

from __future__ import annotations

from types import MappingProxyType

#: Extensions d'image acceptées à l'import (minuscules, point compris). Un
#: tuple, pas un ensemble : son ordre est la **préférence** quand deux images
#: d'un même nom se côtoient (``a.png`` et ``a.jpg`` à côté de ``a.xml``) — un
#: ensemble l'aurait tirée de l'aléa de hachage.
IMAGE_SUFFIXES: tuple[str, ...] = (
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".jp2", ".webp",
)

#: Type MIME de chaque extension acceptée (IANA : ``image/jp2``, RFC 3745).
_MEDIA_TYPES = MappingProxyType({
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".jp2": "image/jp2",
    ".webp": "image/webp",
})

#: Signatures en tête de fichier : PNG, JPEG, TIFF (petit et grand boutiste),
#: boîte de signature JPEG 2000 (ISO/IEC 15444-1, annexe I).
_PREFIXES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"II*\x00",
    b"MM\x00*",
    b"\x00\x00\x00\x0cjP  \r\n\x87\n",
)


def looks_like_image(payload: bytes) -> bool:
    """Les octets commencent-ils par la signature d'un format accepté ?
    WebP : conteneur RIFF (``RIFF`` + taille + ``WEBP``)."""
    if payload.startswith(_PREFIXES):
        return True
    return payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"


def image_media_type(suffix: str) -> str | None:
    """Type MIME d'une extension (``".JP2"`` comme ``".jp2"``), ``None`` hors
    de la table : un appelant refuse ou choisit son défaut, il ne devine pas."""
    return _MEDIA_TYPES.get(suffix.lower())


__all__ = ["IMAGE_SUFFIXES", "image_media_type", "looks_like_image"]
