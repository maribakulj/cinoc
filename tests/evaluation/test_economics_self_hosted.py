"""Économie d'une instance OpenAI-compatible auto-hébergée (P5f 6, S21, D-293).

Défauts reproduits d'abord sur le code d'avant : l'économie lisait le kind et le
modèle, **jamais l'endpoint**. Un vLLM local servant un modèle nommé
``gpt-4o-mini`` recevait donc le tarif d'OpenAI ; un ``qwen`` servi par Ollama
sortait en « tarif inconnu » — sans tarif à chercher, puisque personne ne le
facture. Valeurs dérivées à la main (taux 0,10 €/h, jetons à 0,20/0,60 €/MTok).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run import RunManifest
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.analysis import EconomicsPayload, PipelineEconomics
from cinoc.evaluation.economics import economics_analysis, load_pricing
from cinoc.evaluation.result import DocumentUsage, MetricScore

FIXED = datetime(2026, 6, 1, tzinfo=UTC)
_OPENAI = "https://api.openai.com/v1"
_LOCAL = "http://127.0.0.1:8000/v1"

_PRICING = {
    "meta": {
        "currency": "EUR",
        "last_updated": "2026-06-01",
        "valid_until": "2026-12-01",
        "hourly_rate_local_cpu_eur": 0.10,
        "time_per_error_seconds": 5.0,
    },
    "cloud_models": {
        "openai/gpt-4o-mini": {"input_eur_per_mtok": 0.20, "output_eur_per_mtok": 0.60}
    },
    "token_kinds": ["openai"],
    "endpoints": {"openai": _OPENAI},
}


def _row(kwargs: dict[str, object], served: str | None = None) -> PipelineEconomics:
    step = PipelineStep(
        id="vlm",
        kind="ocr",
        adapter_name="openai:vlm",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(
            PipelineSpec(
                name="vlm", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
            ),
        ),
        adapter_kwargs={"openai:vlm": kwargs},
        served_models={"openai:vlm": (served,)} if served else {},
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    # 360 s = 0,1 h × 0,10 €/h = 0,01 € ; 0,5 MTok in + 0,1 MTok out.
    usage = (
        DocumentUsage(
            document_id="d1",
            pipeline="vlm",
            usage=ResourceUsage(
                duration_seconds=360.0, tokens_in=500_000, tokens_out=100_000
            ),
        ),
    )
    series = {"vlm": [MetricScore(metric="cer", value=0.1, support=100)]}
    analysis = economics_analysis(
        "text", "cer", series, usage, manifest, pricing=_PRICING
    )
    assert analysis is not None and isinstance(analysis.payload, EconomicsPayload)
    (row,) = analysis.payload.pipelines
    return row


def test_the_official_endpoint_keeps_the_table_price() -> None:
    row = _row({"model": "gpt-4o-mini", "base_url": _OPENAI})
    # 0,01 € + 0,5 × 0,20 + 0,1 × 0,60 = 0,17 €.
    assert row.cost_eur == pytest.approx(0.17)
    assert row.basis == "machine+jetons"
    assert row.self_hosted == ()


def test_a_self_hosted_instance_is_never_given_openai_s_price() -> None:
    """Même nom de modèle que la table : le serveur local n'est pas OpenAI."""
    row = _row({"model": "gpt-4o-mini", "base_url": _LOCAL, "self_hosted": True})
    # Temps machine seul : 0,01 €. Les jetons restent affichés, pas facturés.
    assert row.cost_eur == pytest.approx(0.01)
    assert row.tokens_in == 500_000
    assert row.basis == "machine"
    assert row.self_hosted == ("openai/gpt-4o-mini",)


def test_a_self_hosted_instance_is_named_by_the_model_it_served() -> None:
    row = _row(
        {"model": "qwen2.5vl:3b", "base_url": _LOCAL, "self_hosted": True},
        served="qwen2.5vl:3b",
    )
    assert row.cost_eur == pytest.approx(0.01)
    assert row.self_hosted == ("openai/qwen2.5vl:3b",)
    assert "inconnu" not in row.basis


def test_an_undeclared_custom_endpoint_is_an_unknown_price_not_openai_s() -> None:
    """Un endpoint tiers non déclaré auto-hébergé (une passerelle payante…) :
    on ne sait pas ce qu'il facture — jamais le tarif d'OpenAI, jamais 0."""
    row = _row({"model": "gpt-4o-mini", "base_url": _LOCAL})
    assert row.cost_eur is None
    assert row.basis == "tarif inconnu : openai/gpt-4o-mini @ 127.0.0.1:8000"
    assert row.self_hosted == ()


def test_a_manifest_without_endpoint_is_priced_as_before() -> None:
    """Un JSON antérieur (aucun ``base_url`` écrit) garde sa lecture."""
    row = _row({"model": "gpt-4o-mini"})
    assert row.cost_eur == pytest.approx(0.17)


def test_the_packaged_table_names_the_endpoint_its_prices_apply_to() -> None:
    table = load_pricing()
    assert table["endpoints"]["openai"] == _OPENAI
    assert table["endpoints"]["anthropic"] == "https://api.anthropic.com"
    assert set(table["endpoints"]) <= set(table["token_kinds"])
