"""Scripts embarqués du rapport : chargement, hashes CSP, report.js (nav/palette)."""

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
from cinoc.reports.embedded import (
    EMBEDDED_SCRIPTS,
    asset_text,
    inline_script,
    script_csp_hashes,
    script_hash,
)
from cinoc.reports.renderer import default_report_renderer

_ASSETS = Path(__file__).resolve().parents[2] / "cinoc/reports/_assets"
FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def test_embedded_scripts_listed() -> None:
    assert EMBEDDED_SCRIPTS == ("compare.js", "report.js")


def test_hashes_cover_every_embedded_script() -> None:
    csp = script_csp_hashes()
    for name in EMBEDDED_SCRIPTS:
        digest = hashlib.sha256(asset_text(name).encode("utf-8")).digest()
        expected = "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"
        assert script_hash(name) == expected
        assert expected in csp  # le hash de chaque script est dans la CSP


def test_inline_script_wraps_in_tag() -> None:
    tag = inline_script("report.js")
    assert tag.startswith("<script>") and tag.endswith("</script>")
    assert "addEventListener" in tag  # le vrai contenu est inliné


def test_report_js_does_palette_and_keyboard_nav() -> None:
    js = asset_text("report.js")
    assert "palette-cb" in js  # ?palette=cb → classe
    assert 'e.key === "j"' in js and 'e.key === "k"' in js  # navigation vim j/k


def test_report_embeds_both_scripts_and_palette_css() -> None:
    manifest = RunManifest(
        run_id="r", corpus_name="d", n_documents=1, code_version="1.0",
        started_at=FIXED, completed_at=FIXED,
    )
    result = RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="tesseract", view="text",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=0.1, support=1),
                ),
            ),
        ),
    )
    html = default_report_renderer().render(result)
    assert "cinoc-compare-btn" in html  # compare.js
    assert "palette-cb" in html  # report.js + sa CSS
    assert ".palette-cb{--fern" in html  # bascule daltonien (variable CSS)


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_report_js_syntax_is_valid() -> None:
    subprocess.run(["node", "--check", str(_ASSETS / "report.js")], check=True)
