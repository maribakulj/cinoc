"""Importeur de corpus **IIIF** (Presentation API v2 & v3) — couche 5.

Rôle : **localiser** les pages d'un manifeste (parsing du schéma → URLs d'image).
La **matérialisation disque** (téléchargement → ``CorpusSpec``) vit en couche
``app`` (``app/corpus_import.py``) : un adapter parle protocole, pas filesystem.

Périmètre : **images seules**. Un manifeste IIIF porte des pages numérisées, pas
de transcription ; le corpus importé est donc sans vérité-terrain (OCR exécutable,
métriques non applicables tant qu'une GT n'est pas appariée). C'est un choix
assumé de la tranche, pas un manque.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cinoc.adapters.corpus._http import DEFAULT_TIMEOUT, HttpFetchError, fetch_json


@dataclass(frozen=True)
class IIIFImage:
    """Une page du manifeste : son URL d'image + un label lisible."""

    image_url: str
    label: str


def _extract_label(raw: object) -> str:
    """Aplati les formats de label IIIF (str, liste, map de langue v3)."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list) and raw:
        return _extract_label(raw[0])
    if isinstance(raw, dict):
        for lang in ("fr", "en", "none", "@value"):
            val = raw.get(lang)
            if val:
                return str(val[0]) if isinstance(val, list) and val else str(val)
        for val in raw.values():
            return _extract_label(val)
    return str(raw) if raw else ""


#: Signature d'une version de l'Image API dans un service (``type``/``@type``,
#: ``@context`` ou ``profile``). Le profil v3 est un mot nu (``level1``).
_IMAGE_API_MARKERS: tuple[tuple[str, int], ...] = (
    ("ImageService3", 3),
    ("iiif.io/api/image/3", 3),
    ("ImageService2", 2),
    ("iiif.io/api/image/2", 2),
    ("ImageService1", 1),
    ("iiif.io/api/image/1", 1),
    ("library.stanford.edu/iiif/image-api", 1),
)
_V3_BARE_PROFILES = frozenset({"level0", "level1", "level2"})

#: Requête « image entière, plus grande taille servie » selon la version : la
#: taille ``max`` n'existe pas en 2.0, ``full`` n'existe plus en 3.0, et la
#: qualité ``default`` est apparue en 2.0 (``native`` avant).
_FULL_IMAGE_PATH = {
    1: "full/full/0/native.jpg",
    2: "full/full/0/default.jpg",
    3: "full/max/0/default.jpg",
}


def _service_signals(service: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    for key in ("type", "@type", "@context", "profile"):
        value = service.get(key)
        values = value if isinstance(value, list) else [value]
        signals.extend(v for v in values if isinstance(v, str))
    return signals


def _image_api_version(service: dict[str, Any]) -> int | None:
    """Version de l'Image API déclarée par ``service``, ``None`` si muette."""
    signals = _service_signals(service)
    for marker, version in _IMAGE_API_MARKERS:
        if any(marker in signal for signal in signals):
            return version
    profile = service.get("profile")
    if isinstance(profile, str) and profile in _V3_BARE_PROFILES:
        return 3
    return None


def _service_id(service: dict[str, Any]) -> str:
    svc_id = service.get("@id") or service.get("id") or ""
    return svc_id.rstrip("/") if isinstance(svc_id, str) else ""


def _service_image_url(raw: object) -> str:
    """URL de l'image **pleine résolution** servie par un service Image API.

    Le service déclarant sa version l'emporte ; à défaut, la forme de son
    identifiant tranche (``id`` est la forme 3.0, ``@id`` celle de 2.x et avant —
    et ``full`` est accepté par toute la 2.x, quand ``max`` ne l'est qu'en 2.1).
    """
    services = raw if isinstance(raw, list) else [raw]
    candidates = [s for s in services if isinstance(s, dict) and _service_id(s)]
    for service in candidates:
        version = _image_api_version(service)
        if version is not None:
            return f"{_service_id(service)}/{_FULL_IMAGE_PATH[version]}"
    if not candidates:
        return ""
    service = candidates[0]
    version = 3 if "id" in service and "@id" not in service else 2
    return f"{_service_id(service)}/{_FULL_IMAGE_PATH[version]}"


def _resource_image_url(resource: dict[str, Any]) -> str:
    """URL d'image d'une ressource peinte (v2 ``resource``, v3 ``body``).

    **Le service d'images d'abord** : l'URL directe d'une ressource n'est pas
    tenue d'être l'image pleine résolution — Wellcome y met une vignette 12×
    plus petite que ce que sert le service, Bodleian l'URL de base du service
    lui-même (qui répond par son ``info.json``). L'URL directe ne sert qu'en
    l'absence de service, et jamais si elle désigne un ``info.json``.
    """
    from_service = _service_image_url(resource.get("service"))
    if from_service:
        return from_service
    direct = resource.get("@id") or resource.get("id") or ""
    if isinstance(direct, str) and direct and not direct.endswith("/info.json"):
        return direct
    return ""


def _image_url_v2(canvas: dict[str, Any]) -> str:
    images = canvas.get("images") or []
    if not images or not isinstance(images[0], dict):
        return ""
    resource = images[0].get("resource", {})
    if not isinstance(resource, dict):
        return ""
    return _resource_image_url(resource)


def _image_url_v3(canvas: dict[str, Any]) -> str:
    for annotation_page in canvas.get("items") or []:
        for annotation in annotation_page.get("items") or []:
            body = annotation.get("body", {})
            if isinstance(body, list):
                body = body[0] if body else {}
            if not isinstance(body, dict):
                continue
            url = _resource_image_url(body)
            if url:
                return url
    return ""


def _detect_version(manifest: dict[str, Any]) -> int:
    context = manifest.get("@context", "")
    contexts = context if isinstance(context, list) else [context]
    if any(isinstance(c, str) and "presentation/3" in c for c in contexts):
        return 3
    if manifest.get("type") == "Manifest" and "items" in manifest:
        return 3
    return 2


def parse_manifest(manifest: dict[str, Any]) -> tuple[IIIFImage, ...]:
    """Parse un manifeste IIIF (v2/v3 auto-détecté) → pages avec image. Pur."""
    if _detect_version(manifest) == 3:
        canvases = manifest.get("items") or []
        extract = _image_url_v3
    else:
        sequences = manifest.get("sequences") or []
        canvases = sequences[0].get("canvases", []) if sequences else []
        extract = _image_url_v2
    images: list[IIIFImage] = []
    for i, canvas in enumerate(canvases, start=1):
        if not isinstance(canvas, dict):
            continue
        url = extract(canvas)
        if not url:
            continue
        label = _extract_label(canvas.get("label", f"canvas_{i}")) or f"canvas_{i}"
        images.append(IIIFImage(image_url=url, label=label))
    return tuple(images)


class IIIFImporter:
    """Localise les pages d'un manifeste IIIF (fetch + parse, **sans disque**)."""

    name = "iiif"

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    def fetch_images(self, manifest_url: str) -> tuple[IIIFImage, ...]:
        manifest = fetch_json(manifest_url, timeout=self._timeout)
        if not isinstance(manifest, dict):
            raise HttpFetchError(
                f"manifeste IIIF {manifest_url!r} : objet JSON attendu."
            )
        return parse_manifest(manifest)


__all__ = ["IIIFImage", "IIIFImporter", "parse_manifest"]
