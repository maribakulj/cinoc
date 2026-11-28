"""Widget « comparer un run » : surface, déterminisme, hash CSP, sûreté JSON."""

from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.reports.compare_widget import compare_script_hash, compare_widget
from cinoc.reports.embedded import asset_text

FIXED = datetime(2026, 1, 1, tzinfo=UTC)
_JS = Path(__file__).resolve().parents[2] / "cinoc/reports/_assets/compare.js"


def _result(cer: float = 0.1) -> RunResult:
    manifest = RunManifest(
        run_id="r", corpus_name="d", n_documents=1, code_version="1.0",
        started_at=FIXED, completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="tesseract", view="text",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=cer, support=1),
                ),
            ),
        ),
    )


def test_widget_has_button_data_and_inline_script() -> None:
    html = compare_widget(_result())
    assert 'id="cinoc-compare-btn"' in html
    assert 'id="cinoc-compare-file"' in html
    assert 'id="cinoc-compare-data" type="application/json"' in html
    assert "<script>" in html  # script inliné (autonomie du rapport)
    # Données du run courant : CER par "pipeline · view".
    assert "tesseract" in html and "0.1" in html


def test_widget_is_deterministic() -> None:
    assert compare_widget(_result()) == compare_widget(_result())


def test_payload_escapes_angle_brackets() -> None:
    # Un nom de pipeline hostile ne doit pas pouvoir rompre </script>.
    manifest = RunManifest(
        run_id="r", corpus_name="d", n_documents=1, code_version="1.0",
        started_at=FIXED, completed_at=FIXED,
    )
    evil = RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="</script><x>", view="text",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=0.2, support=1),
                ),
            ),
        ),
    )
    html = compare_widget(evil)
    assert "</script><x>" not in html  # littéral neutralisé
    assert "\\u003c/script\\u003e" in html  # échappé en \uXXXX


def test_hash_is_sha256_of_the_script() -> None:
    digest = hashlib.sha256(asset_text("compare.js").encode("utf-8")).digest()
    expected = "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"
    assert compare_script_hash() == expected
    assert compare_script_hash().startswith("'sha256-")


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_compare_js_syntax_is_valid() -> None:
    subprocess.run(["node", "--check", str(_JS)], check=True)
