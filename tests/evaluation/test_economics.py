"""Économie : coûts, débit effectif, Pareto — valeurs dérivées **à la main**.

Règle d'ancrage (D-068) : l'économie est une heuristique maison —
chaque valeur attendue ci-dessous est calculée sur papier depuis le modèle
documenté (durée × taux + jetons × tarif ; débit corrigé), jamais générée en
exécutant l'implémentation source.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run import RunManifest
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.analysis import EconomicsPayload
from cinoc.evaluation.economics import (
    economics_analysis,
    load_pricing,
    pareto_front,
)
from cinoc.evaluation.result import DocumentUsage, MetricScore
from cinoc.evaluation.statistics import EditCounts

FIXED = datetime(2026, 6, 1, tzinfo=UTC)

#: Table contrôlée par le test : taux 0.10 €/h, 5 s/erreur, gpt-4o-mini
#: à 0.20 €/MTok in et 0.60 €/MTok out, valable jusqu'au 2026-12-01.
_PRICING = {
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
            "output_eur_per_mtok": 0.60,
        }
    },
    "token_kinds": ["openai"],
}


def _manifest(completed: datetime = FIXED) -> RunManifest:
    ocr_step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="tesseract:fra",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    llm_step = PipelineStep(
        id="llm",
        kind="post_correction",
        adapter_name="openai:gpt",
        input_types=(ArtifactType.RAW_TEXT,),
        output_types=(ArtifactType.CORRECTED_TEXT,),
        inputs_from={ArtifactType.RAW_TEXT: "ocr"},
    )
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=2,
        pipeline_specs=(
            PipelineSpec(
                name="ocr_seul",
                initial_inputs=(ArtifactType.IMAGE,),
                steps=(ocr_step,),
            ),
            PipelineSpec(
                name="ocr_llm",
                initial_inputs=(ArtifactType.IMAGE,),
                steps=(ocr_step, llm_step),
            ),
        ),
        adapter_kwargs={"openai:gpt": {"model": "gpt-4o-mini"}},
        code_version="1.0",
        started_at=completed,
        completed_at=completed,
    )


def _usage() -> tuple[DocumentUsage, ...]:
    # ocr_seul : 2 docs × 90 s, pas de jetons. ocr_llm : 2 docs × 270 s,
    # 500k jetons in + 100k out au total.
    return (
        DocumentUsage(
            document_id="d1", pipeline="ocr_seul",
            usage=ResourceUsage(duration_seconds=90.0),
        ),
        DocumentUsage(
            document_id="d2", pipeline="ocr_seul",
            usage=ResourceUsage(duration_seconds=90.0),
        ),
        DocumentUsage(
            document_id="d1", pipeline="ocr_llm",
            usage=ResourceUsage(
                duration_seconds=270.0, tokens_in=250_000, tokens_out=50_000
            ),
        ),
        DocumentUsage(
            document_id="d2", pipeline="ocr_llm",
            usage=ResourceUsage(
                duration_seconds=270.0, tokens_in=250_000, tokens_out=50_000
            ),
        ),
    )


def _series() -> dict[str, list[MetricScore]]:
    # ocr_seul : CER 0.10 sur 1000 chars + 0.20 sur 500 → 200 erreurs.
    # ocr_llm  : CER 0.05 sur 1000 + 0.10 sur 500 → 100 erreurs.
    # Les erreurs se lisent dans la statistique du CER (K1), plus dans un poids.
    def score(errors: int, length: int) -> MetricScore:
        return MetricScore(
            metric="cer",
            value=errors / length,
            stat=EditCounts(
                substitutions=errors, deletions=0, insertions=0,
                reference_length=length,
            ),
        )

    return {
        "ocr_seul": [score(100, 1000), score(100, 500)],
        "ocr_llm": [score(50, 1000), score(50, 500)],
    }


def _payload() -> EconomicsPayload:
    analysis = economics_analysis(
        "text", "cer", _series(), _usage(), _manifest(), pricing=_PRICING
    )
    assert analysis is not None
    assert isinstance(analysis.payload, EconomicsPayload)
    return analysis.payload


def test_machine_cost_hand_computed() -> None:
    rows = {r.pipeline: r for r in _payload().pipelines}
    # 180 s = 0.05 h × 0.10 €/h = 0.005 €.
    assert rows["ocr_seul"].cost_eur == pytest.approx(0.005)
    assert rows["ocr_seul"].basis == "machine"


def test_token_cost_hand_computed() -> None:
    rows = {r.pipeline: r for r in _payload().pipelines}
    # Machine : 540 s = 0.15 h × 0.10 = 0.015 €.
    # Jetons : 0.5 MTok × 0.20 + 0.1 MTok × 0.60 = 0.10 + 0.06 = 0.16 €.
    assert rows["ocr_llm"].cost_eur == pytest.approx(0.175)
    assert rows["ocr_llm"].basis == "machine+jetons"


def test_throughput_effective_hand_computed() -> None:
    rows = {r.pipeline: r for r in _payload().pipelines}
    # ocr_seul : 2 docs / 180 s → 40 pages/h ; 200 erreurs × 5 s = 1000 s de
    # relecture → 2 / 1180 s = 6.1017 pages/h.
    assert rows["ocr_seul"].estimated_errors == pytest.approx(200.0)
    assert rows["ocr_seul"].pages_per_hour == pytest.approx(40.0)
    assert rows["ocr_seul"].pages_per_hour_effective == pytest.approx(
        2 / 1180 * 3600
    )


def test_failed_unit_is_not_counted_as_a_processed_page() -> None:
    """Une unité en échec n'a rien produit ni rien mesuré : la compter dans le
    débit inventerait une page traitée en zéro seconde."""
    failed = DocumentUsage(
        document_id="d3", pipeline="ocr_seul", usage=ResourceUsage(),
        outcome="failed", reason="engine", message="boom",
    )
    analysis = economics_analysis(
        "text", "cer", _series(), (*_usage(), failed), _manifest(), pricing=_PRICING
    )
    assert analysis is not None and isinstance(analysis.payload, EconomicsPayload)
    rows = {r.pipeline: r for r in analysis.payload.pipelines}
    assert rows["ocr_seul"].n_documents == 2
    assert rows["ocr_seul"].pages_per_hour == pytest.approx(40.0)


def test_marginal_cost_vs_cheapest() -> None:
    payload = _payload()
    assert len(payload.marginal) == 1
    marginal = payload.marginal[0]
    # Référence = le moins cher (ocr_seul, 0.005 €) ; surcoût 0.17 € pour
    # 100 erreurs évitées → 0.0017 €/erreur.
    assert marginal.baseline == "ocr_seul"
    assert marginal.pipeline == "ocr_llm"
    assert marginal.cost_delta_eur == pytest.approx(0.17)
    assert marginal.errors_avoided == pytest.approx(100.0)
    assert marginal.eur_per_avoided_error == pytest.approx(0.0017)


def test_pareto_fronts() -> None:
    payload = _payload()
    # Coût : ocr_seul (0.10, 0.005) et ocr_llm (0.0667, 0.175) ne se dominent
    # pas → tous deux au front. Durée : idem (180 s vs 540 s).
    assert set(payload.pareto_cost) == {"ocr_seul", "ocr_llm"}
    assert set(payload.pareto_speed) == {"ocr_seul", "ocr_llm"}


def test_pareto_front_drops_dominated_point() -> None:
    # c est dominé par a (mieux sur les deux axes) ; tri stable par (x, y).
    assert pareto_front(
        [("a", 0.1, 1.0), ("b", 0.05, 2.0), ("c", 0.2, 1.5)]
    ) == ("b", "a")


def test_unknown_cloud_model_yields_none_not_zero() -> None:
    manifest = _manifest().model_copy(
        update={"adapter_kwargs": {"openai:gpt": {"model": "gpt-99-futur"}}}
    )
    analysis = economics_analysis(
        "text", "cer", _series(), _usage(), manifest, pricing=_PRICING
    )
    assert analysis is not None
    rows = {r.pipeline: r for r in analysis.payload.pipelines}  # type: ignore[union-attr]
    assert rows["ocr_llm"].cost_eur is None
    assert "tarif inconnu" in rows["ocr_llm"].basis
    # Le pipeline sans tarif sort du front coût, pas du front durée.
    assert analysis.payload.pareto_cost == ("ocr_seul",)  # type: ignore[union-attr]


def test_staleness_compares_to_run_date_not_now() -> None:
    fresh = economics_analysis(
        "text", "cer", _series(), _usage(),
        _manifest(datetime(2026, 6, 1, tzinfo=UTC)), pricing=_PRICING,
    )
    stale = economics_analysis(
        "text", "cer", _series(), _usage(),
        _manifest(datetime(2027, 1, 1, tzinfo=UTC)), pricing=_PRICING,
    )
    assert fresh is not None and stale is not None
    assert fresh.payload.pricing_stale is False  # type: ignore[union-attr]
    assert stale.payload.pricing_stale is True  # type: ignore[union-attr]


def test_no_usage_yields_none() -> None:
    assert (
        economics_analysis("text", "cer", _series(), (), _manifest(), pricing=_PRICING)
        is None
    )


def test_packaged_pricing_table_loads_and_is_dated() -> None:
    table = load_pricing()
    meta = table["meta"]
    assert meta["currency"] == "EUR"
    # La donnée est datée : une table sans péremption serait un chiffre
    # silencieusement périmé (règle anti-chaos n°5 du plan de parité).
    assert "valid_until" in meta and "last_updated" in meta
    assert table["cloud_models"]


def test_payload_round_trips_through_run_result_json() -> None:
    from cinoc.evaluation.result import RunResult

    analysis = economics_analysis(
        "text", "cer", _series(), _usage(), _manifest(), pricing=_PRICING
    )
    assert analysis is not None
    result = RunResult(manifest=_manifest(), analyses=(analysis,))
    reloaded = RunResult.model_validate_json(result.model_dump_json())
    assert reloaded.analyses == result.analyses
    assert isinstance(reloaded.analyses[0].payload, EconomicsPayload)


def test_per_page_cloud_kind_hand_computed() -> None:
    # Pipeline mistral_ocr seul : 2 docs × 0.92 €/1000 pages = 0.00184 € de
    # pages + 180 s machine (0.05 h × 0.10) = 0.005 € → 0.00684 €.
    pricing = {
        **_PRICING,
        "cloud_page_kinds": {"mistral_ocr": {"eur_per_1k_pages": 0.92}},
    }
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="mistral_ocr:c0",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    manifest = _manifest().model_copy(
        update={
            "pipeline_specs": (
                PipelineSpec(
                    name="ocr_seul",
                    initial_inputs=(ArtifactType.IMAGE,),
                    steps=(step,),
                ),
                _manifest().pipeline_specs[1],
            )
        }
    )
    analysis = economics_analysis(
        "text", "cer", _series(), _usage(), manifest, pricing=pricing
    )
    assert analysis is not None
    rows = {r.pipeline: r for r in analysis.payload.pipelines}  # type: ignore[union-attr]
    assert rows["ocr_seul"].cost_eur == pytest.approx(0.005 + 0.00184)


def test_google_vision_priced_from_packaged_table() -> None:
    # Anti-silence : un moteur cloud facturé à l'image NE doit PAS retomber en
    # « temps machine seul ». La table PACKAGÉE porte google_vision (tarif à la
    # page). Pipeline google_vision seul, 2 docs × 90 s, taux packagé 0.08 €/h :
    #   machine = 0.05 h × 0.08 = 0.004 € ; pages = 2/1000 × tarif.
    packaged = load_pricing()
    # Le tarif est **lu** dans la table packagée, jamais recopié ici : une mise à
    # jour des prix ne doit pas casser un test qui protège la facturation à la page.
    per_1k = packaged["cloud_page_kinds"]["google_vision"]["eur_per_1k_pages"]
    assert per_1k > 0
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="google_vision:c0",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    manifest = _manifest().model_copy(
        update={
            "pipeline_specs": (
                PipelineSpec(
                    name="ocr_seul",
                    initial_inputs=(ArtifactType.IMAGE,),
                    steps=(step,),
                ),
                _manifest().pipeline_specs[1],
            )
        }
    )
    analysis = economics_analysis(
        "text", "cer", _series(), _usage(), manifest, pricing=packaged
    )
    assert analysis is not None
    rows = {r.pipeline: r for r in analysis.payload.pipelines}  # type: ignore[union-attr]
    assert rows["ocr_seul"].cost_eur == pytest.approx(0.004 + 2 / 1000 * per_1k)
    assert "pages" in rows["ocr_seul"].basis


def test_azure_di_priced_from_packaged_table() -> None:
    # Même anti-silence pour Azure DI (facturé à la page).
    #   machine = 0.05 h × 0.08 = 0.004 € ; pages = 2/1000 × tarif.
    packaged = load_pricing()
    # Le tarif est **lu** dans la table packagée, jamais recopié ici : une mise à
    # jour des prix ne doit pas casser un test qui protège la facturation à la page.
    per_1k = packaged["cloud_page_kinds"]["azure_di"]["eur_per_1k_pages"]
    assert per_1k > 0
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="azure_di:c0",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    manifest = _manifest().model_copy(
        update={
            "pipeline_specs": (
                PipelineSpec(
                    name="ocr_seul",
                    initial_inputs=(ArtifactType.IMAGE,),
                    steps=(step,),
                ),
                _manifest().pipeline_specs[1],
            )
        }
    )
    analysis = economics_analysis(
        "text", "cer", _series(), _usage(), manifest, pricing=packaged
    )
    assert analysis is not None
    rows = {r.pipeline: r for r in analysis.payload.pipelines}  # type: ignore[union-attr]
    assert rows["ocr_seul"].cost_eur == pytest.approx(0.004 + 2 / 1000 * per_1k)
    assert "pages" in rows["ocr_seul"].basis


# --------------------------------------------------------------------------- #
# Instantané daté : le tarif de l'alias demandé, dit comme tel
# --------------------------------------------------------------------------- #


def _llm_row(
    requested: str, served: str, pricing: dict[str, object] | None = None
) -> tuple[float | None, str]:
    """``(coût, basis)`` du pipeline ``ocr_llm`` : ``requested`` demandé,
    ``served`` servi selon la réponse du fournisseur."""
    manifest = _manifest().model_copy(
        update={
            "adapter_kwargs": {"openai:gpt": {"model": requested}},
            "served_models": {"openai:gpt": (served,)},
        }
    )
    analysis = economics_analysis(
        "text", "cer", _series(), _usage(), manifest,
        pricing=pricing if pricing is not None else _PRICING,
    )
    assert analysis is not None
    rows = {r.pipeline: r for r in analysis.payload.pipelines}  # type: ignore[union-attr]
    return rows["ocr_llm"].cost_eur, rows["ocr_llm"].basis


@pytest.mark.parametrize(
    "served",
    [
        "gpt-4o-mini-2024-07-18",  # forme OpenAI (-AAAA-MM-JJ)
        "gpt-4o-mini-20240718",  # forme Anthropic (-AAAAMMJJ)
    ],
)
def test_a_dated_snapshot_of_the_requested_alias_takes_the_alias_price(
    served: str,
) -> None:
    cost, basis = _llm_row("gpt-4o-mini", served)
    # Même calcul que ``test_token_cost_hand_computed`` : 0.015 + 0.16 €.
    assert cost == pytest.approx(0.175)
    assert basis == (
        f"machine+jetons — tarif de l'alias demandé : openai/gpt-4o-mini "
        f"pour {served}"
    )


def test_a_snapshot_of_another_alias_stays_unknown() -> None:
    """``gpt-4o`` demandé, ``gpt-4o-mini-…`` servi : un préfixe commun n'est pas
    une correspondance."""
    pricing = {
        **_PRICING,
        "cloud_models": {
            **_PRICING["cloud_models"],  # type: ignore[dict-item]
            "openai/gpt-4o": {"input_eur_per_mtok": 2.0, "output_eur_per_mtok": 8.0},
        },
    }
    cost, basis = _llm_row("gpt-4o", "gpt-4o-mini-2024-07-18", pricing)
    assert cost is None
    assert basis == "tarif inconnu : openai/gpt-4o-mini-2024-07-18"


@pytest.mark.parametrize(
    "served",
    [
        # Attesté dans le SDK openai 3.59 (``ChatModel``) : un autre modèle,
        # pas un instantané de ``gpt-4o-mini``.
        "gpt-4o-mini-search-preview-2025-03-11",
        "gpt-4o-mini-2024-13-40",  # pas une date
        "gpt-4o-mini-2024-07",  # forme non attestée
        "gpt-4o-mini-latest",
    ],
)
def test_only_a_date_suffix_falls_back_to_the_alias(served: str) -> None:
    cost, basis = _llm_row("gpt-4o-mini", served)
    assert cost is None
    assert basis == f"tarif inconnu : openai/{served}"


def test_a_served_model_listed_in_the_table_keeps_its_own_price() -> None:
    pricing = {
        **_PRICING,
        "cloud_models": {
            **_PRICING["cloud_models"],  # type: ignore[dict-item]
            "openai/gpt-4o-mini-2024-07-18": {
                "input_eur_per_mtok": 1.0,
                "output_eur_per_mtok": 0.0,
            },
        },
    }
    cost, basis = _llm_row("gpt-4o-mini", "gpt-4o-mini-2024-07-18", pricing)
    # Machine 0.015 € + 0.5 MTok × 1.0 € = 0.515 € : son tarif, pas l'alias.
    assert cost == pytest.approx(0.515)
    assert basis == "machine+jetons"


def test_mistral_latest_to_yymm_is_not_taken_for_a_snapshot() -> None:
    """Forme écartée, faute d'attestation : la cassette Mistral (synthétique)
    sert ``mistral-small-2506`` à qui demande ``mistral-small-latest``, mais le
    SDK mistralai 1.12.4 montre la réponse qui **reprend** l'alias demandé
    (``model="mistral-large-latest"``, ``extra/tests/test_struct_chat.py``). Et
    ``-AAMM`` remplace ``-latest`` au lieu de le suivre : ce n'est pas un
    suffixe de date de l'alias."""
    pricing = {
        **_PRICING,
        "cloud_models": {
            "mistral/mistral-small-latest": {
                "input_eur_per_mtok": 0.1,
                "output_eur_per_mtok": 0.3,
            }
        },
        "token_kinds": ["mistral"],
    }
    step = PipelineStep(
        id="llm",
        kind="post_correction",
        adapter_name="mistral:c0",
        input_types=(ArtifactType.RAW_TEXT,),
        output_types=(ArtifactType.CORRECTED_TEXT,),
        inputs_from={ArtifactType.RAW_TEXT: "ocr"},
    )
    base = _manifest()
    ocr_llm = base.pipeline_specs[1]
    manifest = base.model_copy(
        update={
            "pipeline_specs": (
                base.pipeline_specs[0],
                ocr_llm.model_copy(update={"steps": (ocr_llm.steps[0], step)}),
            ),
            "adapter_kwargs": {"mistral:c0": {"model": "mistral-small-latest"}},
            "served_models": {"mistral:c0": ("mistral-small-2506",)},
        }
    )
    analysis = economics_analysis(
        "text", "cer", _series(), _usage(), manifest, pricing=pricing
    )
    assert analysis is not None
    rows = {r.pipeline: r for r in analysis.payload.pipelines}  # type: ignore[union-attr]
    assert rows["ocr_llm"].cost_eur is None
    assert rows["ocr_llm"].basis == "tarif inconnu : mistral/mistral-small-2506"


# --------------------------------------------------------------------------- #
# Tentatives comptées (P5f 7, S20)
# --------------------------------------------------------------------------- #


def _page_manifest() -> RunManifest:
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="mistral_ocr:c0",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    return _manifest().model_copy(
        update={
            "pipeline_specs": (
                PipelineSpec(
                    name="ocr_seul", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
                ),
                _manifest().pipeline_specs[1],
            )
        }
    )


def _rows(usage: tuple[DocumentUsage, ...], manifest: RunManifest) -> dict[str, object]:
    pricing = {
        **_PRICING,
        "cloud_page_kinds": {"mistral_ocr": {"eur_per_1k_pages": 1.0}},
    }
    analysis = economics_analysis(
        "text", "cer", _series(), usage, manifest, pricing=pricing
    )
    assert analysis is not None and isinstance(analysis.payload, EconomicsPayload)
    return {r.pipeline: r for r in analysis.payload.pipelines}


def test_every_billed_page_is_counted_not_one_per_document() -> None:
    """Un document qui a coûté trois pages (fan-out sur trois régions, ou une
    tentative facturée avant le succès) en coûte trois, pas une. Machine :
    180 s × 0,10 €/h = 0,005 € ; pages : (3 + 1) / 1000 × 1 € = 0,004 €."""
    usage = (
        DocumentUsage(
            document_id="d1", pipeline="ocr_seul",
            usage=ResourceUsage(duration_seconds=90.0, billed_pages=3),
        ),
        DocumentUsage(
            document_id="d2", pipeline="ocr_seul",
            usage=ResourceUsage(duration_seconds=90.0, billed_pages=1),
        ),
        *_usage()[2:],
    )
    rows = _rows(usage, _page_manifest())
    row = rows["ocr_seul"]
    assert row.cost_eur == pytest.approx(0.005 + 0.004)  # type: ignore[attr-defined]
    assert row.billed_pages == 4  # type: ignore[attr-defined]
    assert row.n_documents == 2  # type: ignore[attr-defined]


def test_a_failed_unit_s_billed_consumption_is_paid_not_processed() -> None:
    """Une unité en échec n'est pas une page traitée (débit, durée) — mais ce
    qu'elle a fait facturer est payé : la page soumise à Azure avant une sonde
    perdue, les jetons d'une réponse refusée."""
    failed_page = DocumentUsage(
        document_id="d3", pipeline="ocr_seul",
        usage=ResourceUsage(billed_pages=1),
        outcome="failed", reason="engine", message="sonde perdue",
    )
    refused = DocumentUsage(
        document_id="d3", pipeline="ocr_llm",
        usage=ResourceUsage(tokens_in=1_000_000, tokens_out=0),
        outcome="failed", reason="engine", message="refus",
    )
    rows = _rows((*_usage(), failed_page, refused), _page_manifest())
    ocr = rows["ocr_seul"]
    assert ocr.n_documents == 2  # type: ignore[attr-defined]
    assert ocr.pages_per_hour == pytest.approx(40.0)  # type: ignore[attr-defined]
    # 0,005 € machine + 3 pages facturées (2 traitées + 1 perdue) / 1000.
    assert ocr.cost_eur == pytest.approx(0.005 + 0.003)  # type: ignore[attr-defined]
    llm = rows["ocr_llm"]
    # 540 s × 0,10 €/h = 0,015 € ; jetons : 1,5 MTok in × 0,20 + 0,1 × 0,60.
    assert llm.tokens_in == 1_500_000  # type: ignore[attr-defined]
    assert llm.cost_eur == pytest.approx(0.015 + 0.30 + 0.06)  # type: ignore[attr-defined]


def test_resumed_units_are_counted() -> None:
    usage = tuple(
        u.model_copy(update={"resumed": u.document_id == "d1"}) for u in _usage()
    )
    analysis = economics_analysis(
        "text", "cer", _series(), usage, _manifest(), pricing=_PRICING
    )
    assert analysis is not None and isinstance(analysis.payload, EconomicsPayload)
    assert {r.pipeline: r.n_resumed for r in analysis.payload.pipelines} == {
        "ocr_llm": 1,
        "ocr_seul": 1,
    }
