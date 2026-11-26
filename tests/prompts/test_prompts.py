"""Catalogue de prompts curés : lecture dynamique, placeholder, erreurs."""

from __future__ import annotations

import re

import pytest

from cinoc.prompts import PromptError, available_prompts, load_prompt


def test_sixteen_prompts_available_and_sorted() -> None:
    names = available_prompts()
    assert len(names) == 16  # 13 correction + 3 zero-shot (portés de Picarones)
    assert list(names) == sorted(names)
    assert "correction_medieval_french" in names
    assert "zero_shot_medieval_french" in names


def test_correction_prompts_use_ocr_text_placeholder() -> None:
    # Les prompts de correction injectent le texte OCR via {ocr_text} (convention
    # Cinoc, ≠ {ocr_output} de Picarones) ; sinon l'OCR ne serait jamais inséré.
    for name in available_prompts():
        text = load_prompt(name)
        assert text  # jamais vide
        if name.startswith("correction_"):
            assert "{ocr_text}" in text, name
        else:  # zero_shot_* : image → texte, aucun placeholder
            assert "{ocr_text}" not in text, name


def test_unknown_prompt_raises_not_silent() -> None:
    with pytest.raises(PromptError, match="inconnu"):
        load_prompt("nexiste_pas")


def test_no_stale_picarones_references() -> None:
    # Donnée portée et nettoyée (CLAUDE §8 : aucun marqueur Picarones/sprint).
    for name in available_prompts():
        lowered = load_prompt(name).lower()
        assert "picarones" not in lowered


def test_no_placeholder_is_left_for_the_model_to_read() -> None:
    """Seul ``{ocr_text}`` est substitué (``build_prompt``) : tout autre
    ``{…}`` part tel quel au modèle. Trois prompts zero-shot finissaient sur
    « Image (base64) : {image_b64} » — l'image est jointe à part, le modèle
    lisait l'accolade."""
    for name in available_prompts():
        placeholders = set(re.findall(r"{[A-Za-z_0-9]+}", load_prompt(name)))
        expected = {"{ocr_text}"} if name.startswith("correction_") else set()
        assert placeholders == expected, name
