"""Les demandes de relecture ne sont ni des refus ni des validations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import PipelineDecisions
from cinoc.evaluation.decisions import decisions_analysis
from cinoc.evaluation.result import RunResult
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.decisions import DecisionsSection
from tests.evaluation.test_decisions import _ligne, _outputs, _payload


def test_review_counts_lines_once_per_reason_and_keeps_every_detail(
    tmp_path: Path,
) -> None:
    first = _ligne("L1", "a", "b") | {
        "status": "review_required",
        "review_reasons": [
            {"code": "systematic_removal", "detail": "a"},
            {"code": "systematic_removal", "detail": "b"},
            {"code": "digits_changed", "detail": "1 → 2"},
        ],
    }
    # A hyphen partner can be referred without changing its own text.
    second = _ligne("L2", "c", "c") | {
        "status": "review_required",
        "review_reasons": [{"code": "systematic_removal", "detail": "c"}],
    }
    row = _payload(
        decisions_analysis("text", _outputs(tmp_path, first, second))
    ).pipelines[0]
    assert (row.changed, row.untouched, row.refused, row.review_required) == (
        1,
        1,
        0,
        2,
    )
    assert {r.code: r.n for r in row.review_reasons} == {
        "systematic_removal": 2,
        "digits_changed": 1,
    }
    assert [r.detail for r in row.samples[0].review_reasons] == ["a", "b", "1 → 2"]
    assert len(row.samples) == 2


def test_archives_without_review_fields_remain_readable_and_unknown() -> None:
    row = PipelineDecisions.model_validate(
        {
            "pipeline": "p",
            "n_lines": 1,
            "changed": 1,
            "refused": 0,
            "untouched": 0,
        }
    )
    assert row.review_required is None
    assert row.review_reasons == ()


def test_review_count_does_not_depend_on_sample_limit_or_available_reasons(
    tmp_path: Path,
) -> None:
    lines = [
        _ligne(f"L{i}", "a", "b") | {"status": "review_required"} for i in range(41)
    ]
    row = _payload(decisions_analysis("text", _outputs(tmp_path, *lines))).pipelines[0]
    assert row.review_required == 41
    assert len(row.samples) == 40
    assert [(r.code, r.n) for r in row.review_reasons] == [("sans_motif", 41)]


def test_decision_counts_use_complete_text_not_the_display_excerpt(
    tmp_path: Path,
) -> None:
    prefix = "a" * 300
    row = _payload(
        decisions_analysis(
            "text",
            _outputs(
                tmp_path,
                _ligne("L1", prefix + "x", prefix + "y", proposed=prefix + "y"),
                _ligne("L2", prefix + "x", prefix + "x", proposed=prefix + "x"),
                _ligne("L3", prefix + "x", prefix + "x", proposed=prefix + "y"),
            ),
        )
    ).pipelines[0]
    assert (row.changed, row.untouched, row.refused) == (1, 1, 1)
    assert row.samples[0].source_text == row.samples[0].final_text == prefix


def test_review_status_and_reasons_are_escaped_in_the_report(tmp_path: Path) -> None:
    malicious = "<script>alert(1)</script>"
    analysis = decisions_analysis(
        "text",
        _outputs(
            tmp_path,
            _ligne("L1", "a", "b")
            | {
                "status": malicious,
                "review_reasons": [{"code": malicious, "detail": malicious}],
            },
        ),
    )
    assert analysis is not None
    result = RunResult(
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=1,
            code_version="1.0",
            started_at=datetime(2026, 10, 7, tzinfo=UTC),
            completed_at=datetime(2026, 10, 7, tzinfo=UTC),
        ),
        analyses=(analysis,),
    )
    html = DecisionsSection().render(result, SectionContext(lang="fr"))
    assert html is not None
    assert malicious not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
