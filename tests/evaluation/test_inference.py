"""Inférence : test omnibus, Holm, Nemenyi conditionné, barres CD.

L'IC bootstrap (ratio micro) a ses preuves dans ``test_micro_interval.py``.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from scipy import stats  # type: ignore[import-untyped]

from cinoc.evaluation.analysis import InferencePayload
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.inference import (
    MIN_SUPPORT,
    InferenceEntry,
    holm_adjusted,
    inference_analyses,
    nemenyi_critical_value,
    omnibus_test,
)

#: Jeu apparié 3 pipelines × 8 documents.
_DATA: dict[str, list[float | None]] = {
    "alpha": [0.10, 0.12, 0.08, 0.11, 0.09, 0.13, 0.10, 0.12],
    "beta": [0.20, 0.22, 0.18, 0.21, 0.19, 0.23, 0.20, 0.22],
    "gamma": [0.15, 0.11, 0.16, 0.12, 0.17, 0.12, 0.15, 0.11],
}


def _entry(
    metric: str, data: dict[str, list[float | None]]
) -> InferenceEntry:
    """Une ligne de famille à poids unitaires (micro = moyenne des documents)."""
    return ("text", metric, data, {name: [1] * len(s) for name, s in data.items()})


def _payload(
    data: dict[str, list[float | None]], **kwargs: object
) -> InferencePayload:
    (analysis,) = inference_analyses([_entry("cer", data)], **kwargs)  # type: ignore[arg-type]
    assert isinstance(analysis.payload, InferencePayload)
    return analysis.payload


def test_friedman_nemenyi_match_scipy() -> None:
    payload = _payload(_DATA)
    columns = [_DATA[name] for name in ("alpha", "beta", "gamma")]
    assert payload.test == "friedman"
    assert payload.p_value == pytest.approx(stats.friedmanchisquare(*columns).pvalue)
    assert payload.family_size == 1 and payload.p_holm == payload.p_value
    q = stats.studentized_range.ppf(0.95, 3, math.inf) / math.sqrt(2)
    assert payload.q_alpha == pytest.approx(q)  # 2,3437 (la table disait 2,343)
    assert payload.critical_distance == pytest.approx(q * math.sqrt(12 / 48))
    ranks = {r.pipeline: r.mean_rank for r in payload.mean_ranks}
    assert ranks == pytest.approx({"alpha": 1.375, "gamma": 1.625, "beta": 3.0})
    assert [r.pipeline for r in payload.mean_ranks] == ["alpha", "gamma", "beta"]
    assert payload.cd_groups == (("alpha", "gamma"), ("beta",))
    significant = {(pair.a, pair.b): pair.significant for pair in payload.pairwise}
    assert significant == {
        ("alpha", "beta"): True,
        ("alpha", "gamma"): False,
        ("beta", "gamma"): True,
    }


def test_cd_bars_overlap_instead_of_implying_a_difference() -> None:
    """Rangs 1,2 / 2,0 / 2,8 sur 10 documents, CD ≈ 1,048 : a–b et b–c sont
    indiscernables, seul a–c diffère. Des groupes disjoints ({a, b}, {c})
    faisaient lire b ≠ c ; les barres se chevauchent."""
    payload = _payload(
        {
            "a": [0.1] * 8 + [0.1, 0.3],
            "b": [0.2] * 8 + [0.3, 0.1],
            "c": [0.3] * 8 + [0.2, 0.2],
        }
    )
    ranks = {r.pipeline: r.mean_rank for r in payload.mean_ranks}
    assert ranks == pytest.approx({"a": 1.2, "b": 2.0, "c": 2.8})
    assert payload.critical_distance == pytest.approx(1.048, abs=1e-3)
    assert payload.cd_groups == (("a", "b"), ("b", "c"))
    assert [(p.a, p.b) for p in payload.pairwise if p.significant] == [("a", "c")]


def test_critical_value_is_exact_for_any_k_and_alpha() -> None:
    # La table manuscrite était anti-conservatrice au-delà de k = 30 (q(50) =
    # 3,945 contre 3,992) et servait la colonne α = 0,05 pour tout α ≠ 0,01.
    assert nemenyi_critical_value(50) == pytest.approx(3.9923, abs=1e-4)
    assert nemenyi_critical_value(50) > 3.945
    assert nemenyi_critical_value(3, 0.10) < nemenyi_critical_value(3, 0.05)
    assert nemenyi_critical_value(4, 0.01) == pytest.approx(3.1133, abs=1e-4)
    with pytest.raises(EvaluationError):
        nemenyi_critical_value(1)


def test_holm_matches_the_step_down_definition() -> None:
    p = [0.01, 0.04, 0.03, 0.005, 0.5]
    adjusted = holm_adjusted(p)
    assert adjusted == pytest.approx((0.04, 0.09, 0.09, 0.025, 0.5))
    assert holm_adjusted([]) == ()
    assert holm_adjusted([0.6, 0.7]) == (1.0, 1.0)  # plafonnée à 1


def test_posthoc_only_after_a_rejected_friedman() -> None:
    """Friedman non rejeté → ni distance critique, ni paires, ni barres."""
    flat = {
        "a": [0.1, 0.2, 0.3, 0.1, 0.2, 0.3],
        "b": [0.2, 0.3, 0.1, 0.2, 0.3, 0.1],
        "c": [0.3, 0.1, 0.2, 0.3, 0.1, 0.2],
    }
    payload = _payload(flat)  # type: ignore[arg-type]
    assert payload.test == "friedman" and payload.p_holm is not None
    assert payload.p_holm >= 0.05
    assert payload.critical_distance is None
    assert payload.cd_groups == () and payload.pairwise == ()
    assert len(payload.mean_ranks) == 3  # les rangs restent lisibles


def test_holm_family_is_the_whole_run() -> None:
    """Le même Friedman rejeté seul n'est plus rejeté parmi 20 tests."""
    noise = {
        "a": [0.1, 0.2, 0.3, 0.1, 0.2, 0.3],
        "b": [0.2, 0.3, 0.1, 0.2, 0.3, 0.1],
        "c": [0.3, 0.1, 0.2, 0.3, 0.1, 0.2],
    }
    clear: dict[str, list[float | None]] = {
        "a": [0.1] * 6 + [0.3],
        "b": [0.2] * 6 + [0.1],
        "c": [0.3] * 6 + [0.2],
    }
    alone = _payload(clear)  # p ≈ 0,0119 : rejeté seul
    assert alone.critical_distance is not None
    entries = [_entry("cer", clear)] + [
        _entry(f"m{i}", noise)  # type: ignore[arg-type]
        for i in range(19)
    ]
    crowded = inference_analyses(entries)
    first = crowded[0].payload
    assert isinstance(first, InferencePayload)
    assert first.p_value == alone.p_value and first.family_size == 20
    assert first.p_holm == pytest.approx(min(1.0, 20 * (alone.p_value or 0)))
    assert first.critical_distance is None  # post-hoc retiré avec le rejet


def test_not_computed_says_why() -> None:
    short = {name: values[: MIN_SUPPORT - 1] for name, values in _DATA.items()}
    assert _payload(short).not_computed == "insufficient_support"
    single = _payload({"alpha": _DATA["alpha"]})
    assert single.not_computed == "single_pipeline" and single.test is None
    same = _payload({"a": [0.2] * 6, "b": [0.2] * 6})
    assert same.not_computed == "no_difference"
    assert same.p_value is None and same.p_holm is None and same.family_size == 0


def test_two_pipelines_use_wilcoxon_without_posthoc() -> None:
    data = {"alpha": _DATA["alpha"], "beta": _DATA["beta"]}
    payload = _payload(data)
    assert payload.test == "wilcoxon"
    assert payload.p_value == pytest.approx(
        stats.wilcoxon(_DATA["alpha"], _DATA["beta"]).pvalue
    )
    assert payload.critical_distance is None
    assert payload.cd_groups == () and payload.pairwise == ()
    assert len(payload.mean_ranks) == 2 and len(payload.intervals) == 2


def test_omnibus_drops_incomplete_documents() -> None:
    data = {
        "alpha": [*_DATA["alpha"], None],
        "beta": [*_DATA["beta"], 0.5],
        "gamma": [*_DATA["gamma"], 0.5],
    }
    assert len(omnibus_test(data).complete) == 8
    payload = _payload(data)
    assert payload.n_documents == 8  # le 9ᵉ document (None chez alpha) est exclu
    # L'IC marginal de beta utilise, lui, ses 9 valeurs valides.
    intervals = {i.pipeline: i for i in payload.intervals}
    assert intervals["beta"].n_documents == 9
    assert intervals["alpha"].n_documents == 8


def test_intervals_only_when_asked() -> None:
    assert _payload(_DATA, with_intervals=False).intervals == ()


def test_payload_refuses_incoherent_states() -> None:
    with pytest.raises(ValidationError):  # ni test ni motif
        InferencePayload(metric="cer", alpha=0.05, n_documents=6)
    with pytest.raises(ValidationError):  # post-hoc sans rejet
        InferencePayload(
            metric="cer", alpha=0.05, n_documents=6, test="friedman",
            p_value=0.2, p_holm=0.2, family_size=1, critical_distance=1.0,
        )


def test_payload_serialisation_is_deterministic() -> None:
    (first,) = inference_analyses([_entry("cer", _DATA)])
    (second,) = inference_analyses([_entry("cer", _DATA)])
    assert first.scope == "corpus"
    assert first.model_dump_json() == second.model_dump_json()
