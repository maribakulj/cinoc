"""Sous-couche texte : normalisation de comparaison, lecture de texte brut,
markdown d'OCR → texte brut."""

from __future__ import annotations

from cinoc.formats.text.markdown import markdown_to_text
from cinoc.formats.text.normalization import (
    DEFAULT_PROFILE,
    NORMALIZATION_PROFILES,
    NormalizationProfile,
    get_builtin_profile,
)
from cinoc.formats.text.plain import read_plaintext

__all__ = [
    "NormalizationProfile",
    "NORMALIZATION_PROFILES",
    "DEFAULT_PROFILE",
    "get_builtin_profile",
    "markdown_to_text",
    "read_plaintext",
]
