"""Garde-fou : une brique hors de son rôle est **refusée**, jamais retombée.

La file de recettes ne doit jamais assembler silencieusement une spec d'un autre
moteur pour une brique **non proposée** par le rôle de l'étape : soit la bonne
spec, soit un **refus explicite** (``RecipeError``). Verrou de non-régression du
défaut historique « ``mistral`` → tesseract », hérité de l'ancien composeur
(D-298 : il n'y a plus que ce constructeur).
"""

from __future__ import annotations

import pytest

from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.app.recipes import RecipeError
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef


def _corpus() -> CorpusSpec:
    return CorpusSpec(
        name="t",
        documents=(DocumentRef(id="d", image_uri="d.png", ground_truths=()),),
    )


def _plan(recipe: str, **choices: str) -> None:
    plan_recipe_run(
        _corpus(), (RecipeEntry(recipe=recipe, choices=choices),), run_id="r-1"
    )


def test_an_llm_is_not_an_ocr_engine() -> None:
    # 'mistral' n'est pas un moteur OCR : refusé, jamais retombé sur tesseract.
    with pytest.raises(RecipeError, match="pas proposé"):
        _plan("ocr_simple", ocr="mistral")


def test_zero_shot_requires_a_vision_model() -> None:
    with pytest.raises(RecipeError, match="pas proposé"):
        _plan("vlm_seul", vlm="tesseract")


def test_a_correction_requires_a_language_model() -> None:
    with pytest.raises(RecipeError, match="pas proposé"):
        _plan("ocr_puis_llm", correction="tesseract")


def test_text_and_image_rejects_a_provider_without_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fournisseur sans vision est refusé en ``text_and_image``.

    Cette vérification citait ``ollama`` en exemple — « pas de vision ». C'est
    devenu faux à la PR #91, et le test a alors **protégé** la dérive au lieu de
    la détecter (D-233). L'intention reste juste ; c'est l'exemple codé en dur
    qui ne l'était pas. On retire donc le mode à un adapter pour la vérifier,
    plutôt que de parier sur ce qu'un fournisseur sait faire cette année.
    """
    from cinoc.adapters.llm.ollama import OllamaAdapter

    monkeypatch.setattr(OllamaAdapter, "SUPPORTED_MODES", frozenset({"text_only"}))
    with pytest.raises(RecipeError, match="pas proposé"):
        _plan("ocr_puis_vlm", correction="ollama")


def test_a_vision_provider_is_accepted_in_text_and_image() -> None:
    """Le pendant : ce qui déclare la vision doit passer."""
    _plan("ocr_puis_vlm", correction="ollama")
