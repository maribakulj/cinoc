"""Section économie : lecture seule du payload, avertissement de péremption."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    EconomicsPayload,
    MarginalCost,
    PipelineEconomics,
)
from cinoc.evaluation.result import RunResult
from cinoc.reports.section import Section, SectionContext
from cinoc.reports.sections.economics import EconomicsSection

FIXED = datetime(2026, 6, 1, tzinfo=UTC)


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=2,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def _payload(stale: bool = False) -> EconomicsPayload:
    return EconomicsPayload(
        metric="cer",
        currency="EUR",
        hourly_rate_eur=0.10,
        time_per_error_seconds=5.0,
        pricing_valid_until="2026-12-01",
        pricing_stale=stale,
        pipelines=(
            PipelineEconomics(
                pipeline="ocr_seul",
                n_documents=2,
                duration_seconds=180.0,
                cost_eur=0.005,
                basis="machine",
                cer=0.1333,
                estimated_errors=200.0,
                pages_per_hour=40.0,
                pages_per_hour_effective=6.1,
            ),
            PipelineEconomics(
                pipeline="ocr_llm",
                n_documents=2,
                duration_seconds=540.0,
                tokens_in=500_000,
                tokens_out=100_000,
                cost_eur=0.175,
                basis="machine+jetons",
                cer=0.0667,
                estimated_errors=100.0,
                pages_per_hour=13.3,
                pages_per_hour_effective=6.9,
            ),
        ),
        pareto_cost=("ocr_llm", "ocr_seul"),
        pareto_speed=("ocr_llm", "ocr_seul"),
        marginal=(
            MarginalCost(
                pipeline="ocr_llm",
                baseline="ocr_seul",
                cost_delta_eur=0.17,
                errors_avoided=100.0,
                eur_per_avoided_error=0.0017,
            ),
        ),
    )


def _result(stale: bool = False) -> RunResult:
    return RunResult(
        manifest=_manifest(),
        analyses=(Analysis(scope="corpus", view="text", payload=_payload(stale)),),
    )


def test_satisfies_section_protocol() -> None:
    section = EconomicsSection()
    assert isinstance(section, Section)
    assert section.name == "economics"


def test_renders_costs_pareto_and_marginal_read_only() -> None:
    html = EconomicsSection().render(_result(), SectionContext())
    assert html is not None
    assert "0,0050" in html and "0,1750" in html  # coûts du payload, pas recalculés
    assert "machine+jetons" in html
    assert "Front de Pareto" in html and "ocr_llm" in html
    assert "EUR/erreur évitée" in html and "0,0017" in html
    # Déterminisme : même RunResult → même HTML, bit à bit.
    assert html == EconomicsSection().render(_result(), SectionContext())


def test_stale_pricing_renders_explicit_warning() -> None:
    fresh = EconomicsSection().render(_result(stale=False), SectionContext())
    stale = EconomicsSection().render(_result(stale=True), SectionContext())
    assert fresh is not None and stale is not None
    assert "périmée" not in fresh
    assert "Table de tarifs périmée" in stale


def test_renders_english_labels() -> None:
    html = EconomicsSection().render(_result(), SectionContext(lang="en"))
    assert html is not None
    assert "Economics" in html and "Économie" not in html
    assert "costs &amp; throughput" in html and "coûts &amp; débit" not in html
    assert "Pareto front" in html and "Front de Pareto" not in html
    assert "duration (s)" in html and "durée (s)" not in html


def test_without_economics_payload_renders_nothing() -> None:
    result = RunResult(manifest=_manifest())
    assert EconomicsSection().render(result, SectionContext()) is None


def test_human_cost_is_labelled_a_simulation_in_both_languages() -> None:
    """Le débit « effectif » retire un temps de relecture **supposé** (5 s par
    erreur caractère) : ce n'est pas une mesure, et il le dit (D-288) — à
    l'en-tête de sa colonne comme dans la prose, en français et en anglais."""
    fr = EconomicsSection().render(_result(), SectionContext())
    en = EconomicsSection().render(_result(), SectionContext(lang="en"))
    assert fr is not None and en is not None
    assert "pages/h effectif (simulation)" in fr
    assert "hypothèse : 5 s par erreur caractère" in fr
    assert "<strong>simulation</strong>" in fr
    assert "pages/h effective (simulation)" in en
    assert "assumption: 5 s per character error" in en
    assert "<strong>simulation</strong>" in en


def test_a_self_hosted_instance_says_so_in_both_languages() -> None:
    """P5f 6 (D-293) : un serveur auto-hébergé n'a ni « tarif inconnu » ni un
    tarif de fournisseur — la cellule et la note le disent, en FR et en EN."""
    payload = _payload().model_copy(
        update={
            "pipelines": (
                PipelineEconomics(
                    pipeline="vlm_local",
                    n_documents=2,
                    duration_seconds=140.0,
                    tokens_in=2_000,
                    tokens_out=400,
                    cost_eur=0.0031,
                    basis="machine",
                    self_hosted=("openai/qwen2.5vl:3b",),
                ),
            ),
            "marginal": (),
        }
    )
    result = RunResult(
        manifest=_manifest(),
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )
    fr = EconomicsSection().render(result, SectionContext())
    en = EconomicsSection().render(result, SectionContext(lang="en"))
    assert fr is not None and en is not None
    assert "auto-hébergé : openai/qwen2.5vl:3b" in fr
    assert "aucun tarif de fournisseur" in fr
    assert "self-hosted: openai/qwen2.5vl:3b" in en
    assert "no provider price" in en
    assert "auto-hébergé" not in en and "self-hosted" not in fr


def _cache_result(**fields: object) -> RunResult:
    base: dict[str, object] = {
        "pipeline": "vlm",
        "n_documents": 2,
        "duration_seconds": 10.0,
        "tokens_in": 2_048,
        "tokens_out": 75,
        "cost_eur": 0.0004,
        "basis": "machine+jetons",
    }
    row = PipelineEconomics.model_validate({**base, **fields})
    payload = _payload().model_copy(update={"pipelines": (row,), "marginal": ()})
    return RunResult(
        manifest=_manifest(),
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )


def test_cache_and_reasoning_tokens_show_inside_their_totals() -> None:
    """P5f 8 (S22, D-294) : les jetons de cache et de raisonnement sont des
    **parties** des colonnes de jetons existantes — affichées dans leur cellule,
    en FR et en EN, sans colonne ni section nouvelle."""
    result = _cache_result(
        tokens_cache_read=1_536, tokens_cache_write=0, tokens_reasoning=64
    )
    fr = EconomicsSection().render(result, SectionContext())
    en = EconomicsSection().render(result, SectionContext(lang="en"))
    assert fr is not None and en is not None
    assert "dont 1536 lus en cache, 0 écrits en cache" in fr
    assert "dont 64 de raisonnement" in fr
    assert "incl. 1536 read from cache, 0 written to cache" in en
    assert "incl. 64 reasoning" in en
    assert "en cache" not in en and "from cache" not in fr


def test_counts_a_provider_did_not_give_are_not_shown() -> None:
    fr = EconomicsSection().render(_cache_result(), SectionContext())
    assert fr is not None
    assert "en cache" not in fr and "raisonnement" not in fr


def test_unpriced_cache_tokens_are_said_in_both_languages() -> None:
    result = _cache_result(
        cost_eur=None,
        basis="jetons de cache non tarifés : mistral/mistral-small-latest",
        tokens_cache_read=1_024,
        unpriced_cache=("mistral/mistral-small-latest",),
    )
    fr = EconomicsSection().render(result, SectionContext())
    en = EconomicsSection().render(result, SectionContext(lang="en"))
    assert fr is not None and en is not None
    assert "jetons de cache non tarifés : mistral/mistral-small-latest" in fr
    assert "cache tokens not priced: mistral/mistral-small-latest" in en
    assert "non tarifés" not in en
