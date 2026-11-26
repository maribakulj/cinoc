"""Tests de bord de la normalisation (folding caseless, YAML invalide)."""

from __future__ import annotations

import pytest

from cinoc.formats.text.normalization import NormalizationProfile


def test_caseless_excludes_letter_case_insensitively() -> None:
    """Sous caseless, l'ensemble exclu est casefoldé : exclure ``A`` retire
    aussi ``a`` (le texte est déjà casefoldé)."""
    prof = NormalizationProfile(name="e", caseless=True, exclude_chars="A")
    assert prof.normalize("Abc") == "bc"


def test_from_yaml_text_rejects_non_mapping() -> None:
    with pytest.raises(ValueError):
        NormalizationProfile.from_yaml_text("- not\n- a\n- mapping\n")
