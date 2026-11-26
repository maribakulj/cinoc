"""Étape 2d — zero-shot **bout-en-bout** : ``IMAGE → RAW_TEXT`` via un VLM (1 étage).

Prouve que le mode ``zero_shot`` traverse tout (plan → exécuteur → métriques) et
que les **jetons** du VLM remontent dans ``RunResult.usage`` (économie). Le seul
appel réseau (``_invoke_openai_vision``) est **mocké** : ni clé, ni SDK, ni réseau.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.llm._base import LLMCompletion
from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def test_zero_shot_runs_and_reports_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Le VLM « transcrit » l'image et déclare ses jetons (7 in / 3 out).
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai_vision",
        lambda **_: LLMCompletion("abcd", tokens_in=7, tokens_out=3),
    )
    image = tmp_path / "doc1.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    document = DocumentRef(
        id="doc1",
        image_uri=str(image),
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "doc1.gt.txt")
            ),
        ),
    )
    corpus = CorpusSpec(name="c", documents=(document,))

    spec = plan_recipe_run(
        corpus,
        (
            RecipeEntry(
                recipe="vlm_seul",
                choices={"vlm": "openai"},
                params={"vlm": {"model": "m"}},
            ),
        ),
        run_id="zs-run",
    )

    # Topologie : 1 concurrent, 1 étage IMAGE → RAW_TEXT (pas d'OCR amont).
    assert len(spec.pipelines) == 1
    (step,) = spec.pipelines[0].steps
    assert ArtifactType.IMAGE in step.input_types
    assert step.output_types == (ArtifactType.RAW_TEXT,)

    result = run(spec, registry=_registry(), code_version="1.0")

    # Le texte transcrit == GT → CER 0 (le run a bien produit du RAW_TEXT scoré).
    aggregate = result.pipelines[0].aggregate[0]
    assert aggregate.metric == "cer"
    assert aggregate.value == 0.0

    # Les jetons du VLM remontent dans l'usage (alimente l'économie).
    token_usages = [u for u in result.usage if u.usage.tokens_in is not None]
    assert token_usages, "aucun jeton remonté par le VLM"
    assert token_usages[0].usage.tokens_in == 7
    assert token_usages[0].usage.tokens_out == 3
