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
                aggregate=(MetricScore(metric="cer", value=0.25, support=1),),
            ),
        ),
    )


def test_serialisation_is_deterministic() -> None:
    assert _result().model_dump_json() == _result().model_dump_json()


def test_schema_version_and_stable_keys() -> None:
    result = _result()
    assert result.schema_version == 3
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


def test_v2_payload_still_loads_as_ok_units_without_expected() -> None:
    """Un JSON v2 se recharge : unités ``ok`` par défaut, ``expected`` absent —
    il ne savait pas distinguer un échec d'une absence, et ne le prétend pas."""
    v2 = {
        "schema_version": 2,
        "manifest": _manifest().model_dump(mode="json"),
        "pipelines": [
            {
                "pipeline": "p",
                "view": "text",
                "aggregate": [{"metric": "cer", "value": 0.25, "support": 1}],
            }
        ],
        "usage": [
            {
                "document_id": "d1",
                "pipeline": "p",
                "usage": {"duration_seconds": 1.0},
            }
        ],
    }
    manifest = v2["manifest"]
    assert isinstance(manifest, dict)
    manifest.pop("failure_policy")
    reloaded = RunResult.model_validate(v2)
    assert reloaded.schema_version == 2
    assert reloaded.usage[0].outcome == "ok"
    assert reloaded.pipelines[0].aggregate[0].expected is None
    assert reloaded.manifest.failure_policy == "exclude"
