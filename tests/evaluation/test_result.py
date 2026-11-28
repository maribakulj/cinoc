"""``RunResult`` : sérialisation déterministe (golden octet-stable)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cinoc.domain.run import RunManifest
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.result import (
    DocumentUsage,
    MetricScore,
    PipelineResult,
    RunResult,
)


def _manifest() -> RunManifest:
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    return RunManifest(
        run_id="demo",
        corpus_name="demo",
        n_documents=1,
        code_version="1.0",
        started_at=fixed,
        completed_at=fixed,
    )


def _result() -> RunResult:
    return RunResult(
        manifest=_manifest(),
        pipelines=(
            PipelineResult(
                pipeline="p",
                view="text",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=0.25, support=1),
                ),
            ),
        ),
    )


def test_serialisation_is_deterministic() -> None:
    assert _result().model_dump_json() == _result().model_dump_json()


def test_schema_version_and_stable_keys() -> None:
    result = _result()
    assert result.schema_version == 7
    blob = result.model_dump_json().replace(" ", "")
    assert '"metric":"cer"' in blob
    assert '"support":1' in blob


def test_usage_channel_round_trips() -> None:
    result = RunResult(
        manifest=_manifest(),
        usage=(
            DocumentUsage(
                document_id="d1",
                pipeline="p",
                usage=ResourceUsage(
                    duration_seconds=1.5, tokens_in=100, tokens_out=40
                ),
            ),
        ),
    )
    reloaded = RunResult.model_validate_json(result.model_dump_json())
    assert reloaded.usage[0].usage.tokens_out == 40
    assert reloaded.usage[0].usage.duration_seconds == 1.5


def test_v1_payload_without_usage_still_loads() -> None:
    blob = _result().model_dump_json()
    stripped = blob.replace(',"usage":[]', "")
    assert '"usage"' not in stripped
    reloaded = RunResult.model_validate_json(stripped)
    assert reloaded.usage == ()


def test_failed_unit_carries_its_reason_and_message() -> None:
    record = DocumentUsage(
        document_id="d1", pipeline="p", usage=ResourceUsage(),
        outcome="failed", reason="infrastructure", message="HTTP 404",
    )
    reloaded = RunResult.model_validate_json(
        RunResult(manifest=_manifest(), usage=(record,)).model_dump_json()
    )
    assert reloaded.usage[0] == record


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [("failed", None), ("ok", "engine"), ("truncated", "engine")],
)
def test_a_reason_goes_with_failed_and_only_with_it(
    outcome: str, reason: str | None
) -> None:
    with pytest.raises(ValidationError):
        DocumentUsage(
            document_id="d1", pipeline="p", usage=ResourceUsage(),
            outcome=outcome, reason=reason,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6])
def test_an_older_schema_is_refused_with_a_clear_message(version: int) -> None:
    """Remplace ``test_v2_payload_still_loads_…`` et ``test_v4_inference_…`` :
    le schéma 7 est une **rupture explicite** (K1, D-313) — un ``RunResult``
    d'avant portait des ratios pondérés, ou (v6) un agrégat principal stocké,
    sans les statistiques « sortie vide » ni la grappe de chaque document. Il
    n'est ni relu ni converti : il est refusé, et le message dit pourquoi et
    quoi faire, même sans aucun score à relire."""
    old = {
        "schema_version": version,
        "manifest": _manifest().model_dump(mode="json"),
    }
    with pytest.raises(ValidationError, match=r"schéma v\d, attendu v7.*Re-notez"):
        RunResult.model_validate(old)


def test_the_current_schema_round_trips() -> None:
    result = _result()
    assert RunResult.model_validate_json(result.model_dump_json()) == result


def test_calibration_row_without_its_step_is_refused_not_misread() -> None:
    """D-285 (pilote D9) : une ligne de calibration d'avant ne disait pas de
    quelle étape venaient ses confiances, et prêtait à un pipeline corrigé
    l'ECE de son OCR. Sans ``step``, elle est refusée ; une vue d'avant sans
    profil (``null`` = comparaison brute) se relit avec ce même sens."""
    manifest = _manifest().model_dump(mode="json")
    manifest["view_specs"] = [
        {"name": "text", "candidate_types": ["raw_text"], "normalization_profile": None}
    ]
    row = {"pipeline": "tess→llm", "n_tokens": 3, "ece": 0.1, "mce": 0.2}
    old = {
        "schema_version": 7,
        "manifest": manifest,
        "analyses": [
            {
                "scope": "corpus",
                "view": "text",
                "payload": {"kind": "calibration", "n_bins": 10, "pipelines": [row]},
            }
        ],
    }
    with pytest.raises(ValidationError):
        RunResult.model_validate(old)
    old["analyses"] = []
    (view,) = RunResult.model_validate(old).manifest.view_specs
    assert view.normalization_profile is None
