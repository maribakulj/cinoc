"""Couche 2 — Formats documentaires.

Frontière entre les formats de fil (ALTO XML, PAGE XML, texte brut) et le reste du
système. N'opère que sur des ``bytes`` / des chaînes ; jamais sur un résultat
d'OCR ou un calcul de métrique. Peut importer ``lxml`` et ``pyyaml`` ; jamais une
lib de métrique (``jiwer``, ``rapidfuzz``) ni un moteur OCR.

Surface publique :

- sécurité XML (``safe_parse_xml``) — point d'entrée unique de tout parsing XML ;
- YAML d'une entrée non fiable (``safe_load_yaml``) — sans alias ;
- format ALTO (``parse_alto`` / ``write_alto`` + types) ;
- format PAGE (``parse_pagexml`` / ``write_pagexml`` + types) ;
- ALTO ou PAGE → ``CanonicalLayout``, reconnu au contenu
  (``layout_xml.parse_layout_xml``, ``layout_xml_kind``) ;
- normalisation de comparaison (``NormalizationProfile`` & profils) ;
- lecture de texte brut (``read_plaintext``) ;
- formats d'image d'une page (``images.IMAGE_SUFFIXES``, ``looks_like_image``,
  ``image_media_type``) — la table unique de ce qu'un import accepte et du type
  qu'un moteur annonce.
"""

from __future__ import annotations

from cinoc.formats._xml import safe_parse_xml
from cinoc.formats._yaml import safe_load_yaml
from cinoc.formats.alto import (
    AltoBBox,
    AltoDocument,
    AltoLine,
    AltoPage,
    AltoParseError,
    AltoString,
    AltoTextBlock,
    parse_alto,
    write_alto,
)
from cinoc.formats.pagexml import (
    PageDocument,
    PagePage,
    PageParseError,
    PageTextLine,
    PageTextRegion,
    parse_pagexml,
    write_pagexml,
)
from cinoc.formats.text import (
    DEFAULT_PROFILE,
    NORMALIZATION_PROFILES,
    NormalizationProfile,
    get_builtin_profile,
    read_plaintext,
)

__all__ = [
    "safe_parse_xml",
    "safe_load_yaml",
    "parse_alto",
    "write_alto",
    "AltoDocument",
    "AltoPage",
    "AltoTextBlock",
    "AltoLine",
    "AltoString",
    "AltoBBox",
    "AltoParseError",
    "parse_pagexml",
    "write_pagexml",
    "PageDocument",
    "PagePage",
    "PageTextRegion",
    "PageTextLine",
    "PageParseError",
    "NormalizationProfile",
    "NORMALIZATION_PROFILES",
    "DEFAULT_PROFILE",
    "get_builtin_profile",
    "read_plaintext",
]
