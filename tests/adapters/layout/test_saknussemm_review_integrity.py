"""La confiance OCR et les demandes de relecture survivent sans ambiguïté."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.adapters.layout.saknussemm_correct import SaknussemmCorrector
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Line, Region, Word
from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import DecisionsPayload
from cinoc.evaluation.decisions import decisions_analysis
from cinoc.evaluation.result import RunResult
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.decisions import DecisionsSection
from tests.adapters.layout.test_saknussemm_correct import _lines, _run

pytest.importorskip("saknussemm")


def test_changed_text_does_not_inherit_ocr_confidence(tmp_path: Path) -> None:
    source = (
        Line(
            id="L1",
            text="le ſoleil",
            confidence=0.99,
            words=(Word(text="le", confidence=0.99), Word(text="ſoleil")),
        ),
        Line(
            id="L2",
            text="rien à corriger",
            confidence=0.98,
            words=(Word(text="rien"), Word(text="à"), Word(text="corriger")),
        ),
    )
    layout = CanonicalLayout(
        pages=(LayoutPage(regions=(Region(id="R1", lines=source),)),)
    )
    lines = _lines(_run(tmp_path, layout)[ArtifactType.LAYOUT])
    assert lines[0].text == "le soleil"
    assert lines[0].confidence is None
    assert lines[0].words == ()
    assert lines[1] == source[1]


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_real_review_referral_reaches_artifact_analysis_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
) -> None:
    from saknussemm.producers.rules import RulesProducer, SubstitutionRule

    producer = RulesProducer([SubstitutionRule("document.", "document en 1789.")])
    monkeypatch.setattr(SaknussemmCorrector, "_build_producer", lambda self: producer)
    layout = CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(
                    Region(
                        id="R1",
                        lines=(
                            Line(
                                id="L1",
                                text="Une longue phrase dans le document.",
                                confidence=0.99,
                            ),
                        ),
                    ),
                )
            ),
        )
    )
    artifacts = _run(tmp_path, layout)
    saved = json.loads(Path(artifacts[ArtifactType.DECISIONS].uri).read_bytes())
    referral = saved["lines"][0]
    assert referral["status"] == "review_required"
    assert referral["review_reasons"] == [
        {"code": "digits_changed", "detail": "∅ → 1789"}
    ]
    analysis = decisions_analysis("text", {"p": {"doc1": artifacts}})
    assert analysis is not None and isinstance(analysis.payload, DecisionsPayload)
    row = analysis.payload.pipelines[0]
    assert (row.n_lines, row.changed, row.refused, row.review_required) == (1, 1, 0, 1)
    assert {reason.code: reason.n for reason in row.review_reasons} == {
        "digits_changed": 1
    }
    assert row.samples[0].review_reasons[0].detail == "∅ → 1789"
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
    html = DecisionsSection().render(result, SectionContext(lang=lang))
    assert html is not None
    assert ("À relire" if lang == "fr" else "Review required") in html
    assert "review_required" in html
    assert "digits_changed" in html
    assert "∅ → 1789" in html
