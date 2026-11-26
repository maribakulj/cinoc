"""P5f 8 (S22, D-294) — le coût lit les jetons de cache et de raisonnement.

Valeurs **à la main**. Avant S22, l'économie ne voyait que ``tokens_in`` et
``tokens_out`` : chez OpenAI, une entrée lue en cache (facturée 0,5× chez
gpt-4o-mini, 0,1× chez Claude) était comptée au tarif plein — un coût faux par
excès, présenté comme exact. Règles :

- un tarif de lecture en cache dans la table → appliqué aux jetons lus ;
- pas de tarif pour des jetons de cache rendus (lecture sans tarif, ou
  **toute** écriture : son prix dépend d'une durée de vie que le total ne dit
  pas) → coût ``None``, « jetons de cache non tarifés » — ni tarif plein, ni
  oubli silencieux ;
- les jetons de raisonnement sont **dans** ``tokens_out`` (OpenAI, Anthropic) :
  affichés, jamais ajoutés une seconde fois.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run import RunManifest
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.analysis import EconomicsPayload, PipelineEconomics
from cinoc.evaluation.economics import economics_analysis, load_pricing
from cinoc.evaluation.result import DocumentUsage, MetricScore

FIXED = datetime(2026, 6, 1, tzinfo=UTC)

_TABLE: dict[str, Any] = {
    "meta": {
        "currency": "EUR",
        "last_updated": "2026-06-01",
        "valid_until": "2026-12-01",
        "hourly_rate_local_cpu_eur": 0.10,
        "time_per_error_seconds": 5.0,
    },
    "cloud_models": {
        "openai/gpt-4o-mini": {
            "input_eur_per_mtok": 0.20,
            "cache_read_eur_per_mtok": 0.10,
            "output_eur_per_mtok": 0.60,
        },
        "mistral/mistral-small-latest": {
            "input_eur_per_mtok": 0.20,
            "output_eur_per_mtok": 0.60,
        },
    },
    "token_kinds": ["mistral", "openai"],
}


def _manifest(kind: str, model: str) -> RunManifest:
    step = PipelineStep(
        id="llm",
        kind="transcription",
        adapter_name=f"{kind}:x",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=2,
        pipeline_specs=(
            PipelineSpec(
                name="vlm", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
            ),
        ),
        adapter_kwargs={f"{kind}:x": {"model": model}},
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def _row(
    usages: tuple[ResourceUsage, ...],
    *,
    kind: str = "openai",
    model: str = "gpt-4o-mini",
    table: dict[str, Any] | None = None,
) -> PipelineEconomics:
    usage = tuple(
        DocumentUsage(document_id=f"d{i}", pipeline="vlm", usage=u)
        for i, u in enumerate(usages)
    )
    series = {"vlm": [MetricScore(metric="cer", value=0.1, support=100)]}
    analysis = economics_analysis(
        "text", "cer", series, usage, _manifest(kind, model),
        pricing=table if table is not None else _TABLE,
    )
    assert analysis is not None
    assert isinstance(analysis.payload, EconomicsPayload)
    (row,) = analysis.payload.pipelines
    return row


def _cached(read: int | None = 200_000, write: int | None = None) -> ResourceUsage:
    return ResourceUsage(
        duration_seconds=270.0,
        tokens_in=250_000,
        tokens_out=50_000,
        tokens_cache_read=read,
        tokens_cache_write=write,
        tokens_reasoning=10_000,
    )


def test_cache_reads_are_billed_at_the_cache_rate() -> None:
    row = _row((_cached(), _cached()))
    # Machine : 540 s × 0,10 €/h = 0,015 €.
    # Entrée hors cache : 2 × 50 000 = 0,1 MTok × 0,20 = 0,02 €.
    # Lue en cache : 2 × 200 000 = 0,4 MTok × 0,10 = 0,04 €.
    # Sortie : 0,1 MTok × 0,60 = 0,06 € — raisonnement compris, pas ajouté.
    assert row.cost_eur == pytest.approx(0.135)
    assert row.basis == "machine+jetons"
    assert (row.tokens_in, row.tokens_cache_read, row.tokens_reasoning) == (
        500_000,
        400_000,
        20_000,
    )
    assert row.tokens_cache_write is None
    assert row.unpriced_cache == ()


def test_cache_reads_without_a_cache_rate_are_said_unpriced() -> None:
    row = _row((_cached(read=1024),), kind="mistral", model="mistral-small-latest")
    assert row.cost_eur is None
    assert row.basis == "jetons de cache non tarifés : mistral/mistral-small-latest"
    assert row.unpriced_cache == ("mistral/mistral-small-latest",)
    assert row.tokens_cache_read == 1024


def test_a_cache_write_is_unpriced_even_with_a_read_rate() -> None:
    row = _row((_cached(read=0, write=7_000),))
    assert row.cost_eur is None
    assert row.unpriced_cache == ("openai/gpt-4o-mini",)


def test_zero_cache_tokens_need_no_cache_rate() -> None:
    row = _row(
        (_cached(read=0, write=0),), kind="mistral", model="mistral-small-latest"
    )
    # 270 s × 0,10/3600 + 0,25 MTok × 0,20 + 0,05 MTok × 0,60.
    assert row.cost_eur == pytest.approx(0.0075 + 0.05 + 0.03)
    assert row.unpriced_cache == ()
    assert row.tokens_cache_read == 0


def test_units_without_cache_counts_keep_the_full_rate_and_none() -> None:
    plain = ResourceUsage(duration_seconds=270.0, tokens_in=250_000, tokens_out=50_000)
    row = _row((plain, plain))
    assert row.cost_eur == pytest.approx(0.175)
    assert (row.tokens_cache_read, row.tokens_cache_write, row.tokens_reasoning) == (
        None,
        None,
        None,
    )


def test_anthropic_cache_read_at_the_packaged_rate() -> None:
    # La réponse « cached » de la cassette : 105 hors cache + 1 800 lus.
    usage = ResourceUsage(
        tokens_in=1905, tokens_out=40, tokens_cache_read=1800, tokens_cache_write=0
    )
    row = _row(
        (usage,),
        kind="anthropic",
        model="claude-haiku-4-5-20251001",
        table=load_pricing(),
    )
    # 105 × 0,91 + 1 800 × 0,09 + 40 × 4,57 (€/MTok).
    assert row.cost_eur == pytest.approx((105 * 0.91 + 1800 * 0.09 + 40 * 4.57) / 1e6)


def test_the_packaged_cache_rates_are_below_the_input_rate() -> None:
    models = load_pricing()["cloud_models"]
    rated = {k for k, v in models.items() if "cache_read_eur_per_mtok" in v}
    assert rated == {
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "anthropic/claude-haiku-4-5-20251001",
        "anthropic/claude-sonnet-4-6",
    }
    for key in rated:
        entry = models[key]
        assert 0 < entry["cache_read_eur_per_mtok"] < entry["input_eur_per_mtok"]
