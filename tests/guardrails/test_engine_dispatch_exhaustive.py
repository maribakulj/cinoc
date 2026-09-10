"""Garde-fou : le dispatch concurrent→spec est **exhaustif**, sans retombée muette.

``plan_benchmark_run`` ne doit jamais assembler silencieusement une spec d'un
autre moteur pour un moteur/mode **non câblé** : soit la bonne spec, soit un
**refus explicite** (``RunPlanningError``). Verrou de non-régression du défaut
historique « ``mistral`` → tesseract ».
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.run_planning import (
    Competitor,
    RunPlanningError,
    plan_benchmark_run,
)
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef


def _corpus() -> CorpusSpec:
    return CorpusSpec(
        name="t",
        documents=(DocumentRef(id="d", image_uri="d.png", ground_truths=()),),
    )


def test_uncabled_ocr_engine_is_refused() -> None:
    # 'mistral' n'est pas un moteur OCR : OCR seul (mode None) refusé, jamais
    # retombé en silence sur tesseract.
    with pytest.raises(RunPlanningError):
        plan_benchmark_run((Competitor(engine="mistral"),), _corpus(), "r-1")


def test_zero_shot_requires_vlm_engine() -> None:
    with pytest.raises(RunPlanningError):
        plan_benchmark_run(
            (Competitor(engine="tesseract", mode="zero_shot"),), _corpus(), "r-1"
        )


def test_text_only_requires_llm_provider() -> None:
    with pytest.raises(RunPlanningError):
        plan_benchmark_run(
            (Competitor(engine="tesseract", mode="text_only"),), _corpus(), "r-1"
        )


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

    monkeypatch.setattr(
        OllamaAdapter, "SUPPORTED_MODES", frozenset({"text_only"})
    )
    with pytest.raises(RunPlanningError, match="indisponible"):
        plan_benchmark_run(
            (Competitor(engine="tesseract", mode="text_and_image", llm="ollama"),),
            _corpus(),
            "r-1",
        )


def test_a_vision_provider_is_accepted_in_text_and_image() -> None:
    """Le pendant : ce qui déclare la vision doit passer."""
    spec = plan_benchmark_run(
        (Competitor(engine="tesseract", mode="text_and_image", llm="ollama"),),
        _corpus(),
        "r-1",
    )(Path("/tmp"))
    assert spec.pipelines
