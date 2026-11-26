"""P5f 8 (S22, D-294) — les jetons de cache et de raisonnement, du corps au coût.

Bout en bout, sans réseau : réponses « cached » des cassettes OpenAI et
Anthropic → adaptateurs → ``RunResult.usage`` → archive → relecture
``--offline`` **à l'identique** (aucun module de pipeline appelé) → économie.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.resume import ResumeStore
from cinoc.app.run_planning import Competitor, plan_benchmark_run
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.analysis import EconomicsPayload
from cinoc.evaluation.economics import economics_analysis
from cinoc.evaluation.result import RunResult
from tests.adapters._native_fakes import (
    cut_network,
    install_fake_sdks,
    set_keys,
    wire,
)


def _corpus(folder: Path) -> CorpusSpec:
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / "p1.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\np1")
    gt = folder / "p1.gt.txt"
    gt.write_text("Le Petit Journal, 12 mars 1894.", encoding="utf-8")
    return CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="p1",
                image_uri=str(image),
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            ),
        ),
    )


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def _usage(result: RunResult) -> dict[str, ResourceUsage]:
    return {
        u.pipeline: u.usage.model_copy(update={"duration_seconds": None})
        for u in result.usage
    }


def test_cache_and_reasoning_tokens_survive_the_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_keys(monkeypatch)
    install_fake_sdks(
        monkeypatch,
        {
            "openai": lambda: wire("llm", "openai", "cached"),
            "anthropic": lambda: wire("llm", "anthropic", "cached"),
        },
    )
    spec = plan_benchmark_run(
        (
            Competitor(engine="openai", mode="zero_shot", model="gpt-4o-mini"),
            Competitor(
                engine="anthropic", mode="zero_shot", model="claude-haiku-4-5"
            ),
        ),
        _corpus(tmp_path / "corpus"),
        "s22",
    )(tmp_path)
    store = ResumeStore(tmp_path / "archive")
    first = run(spec, registry=_registry(), code_version="1.0", resume_store=store)
    usage = _usage(first)
    by_kind = {name.split(" ", 1)[0]: u for name, u in usage.items()}
    assert by_kind["openai"] == ResourceUsage(
        tokens_in=2048, tokens_out=75, tokens_cache_read=1536, tokens_reasoning=64
    )
    assert by_kind["anthropic"] == ResourceUsage(
        tokens_in=1905,
        tokens_out=40,
        tokens_cache_read=1800,
        tokens_cache_write=0,
        tokens_reasoning=28,
    )

    cut_network(monkeypatch)
    second = run(
        spec,
        registry=_registry(),
        code_version="1.0.1",
        resume_store=store,
        offline=True,
    )
    assert _usage(second) == usage

    series: dict[str, list[Any]] = {doc.pipeline: [] for doc in second.documents}
    for doc in second.documents:
        series[doc.pipeline].extend(s for s in doc.scores if s.metric == "cer")
    analysis = economics_analysis(
        "text", "cer", series, second.usage, second.manifest
    )
    assert analysis is not None and isinstance(analysis.payload, EconomicsPayload)
    rows = {r.pipeline.split(" ", 1)[0]: r for r in analysis.payload.pipelines}
    assert rows["openai"].tokens_cache_read == 1536
    assert rows["anthropic"].tokens_reasoning == 28
    # Les deux modèles ont un tarif de lecture en cache sourcé : coût chiffré.
    assert rows["openai"].cost_eur is not None
    assert rows["anthropic"].cost_eur is not None
    assert rows["openai"].unpriced_cache == ()
