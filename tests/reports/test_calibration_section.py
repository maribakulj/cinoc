"""Section calibration : lecture seule, rendu déterministe."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    CalibrationBin,
    CalibrationPayload,
    PipelineCalibration,
)
from cinoc.evaluation.result import RunResult
from cinoc.reports.section import Section, SectionContext
from cinoc.reports.sections.calibration import CalibrationSection

FIXED = datetime(2026, 6, 1, tzinfo=UTC)


def _result() -> RunResult:
    payload = CalibrationPayload(
        n_bins=10,
        pipelines=(
            PipelineCalibration(
                pipeline="tess",
                step="ocr",
                n_tokens=2,
                ece=0.4,
                mce=0.7,
                bins=(
                    CalibrationBin(
                        lower=0.9, upper=1.0, mean_confidence=0.9,
                        accuracy=1.0, count=1, correct=1,
                        confidence_sum=Fraction(9, 10),
                    ),
                ),
            ),
        ),
    )
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=1,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )


def test_satisfies_section_protocol() -> None:
    section = CalibrationSection()
    assert isinstance(section, Section)
    assert section.name == "calibration"


def test_renders_ece_mce_and_bins() -> None:
    html = CalibrationSection().render(_result(), SectionContext())
    assert html is not None
    assert "ECE 0,4000" in html and "MCE 0,7000" in html
    # Le dernier bin est fermé à 1,0 (une confiance de 1,0 y tombe) : il
    # s'écrivait « [0,9 ; 1,0[ », ce qui l'excluait (D-285).
    assert "[0,9 ; 1,0]" in html and "1,0[" not in html
    # Les confiances sont attribuées à l'étape qu'elles mesurent (D9).
    assert "tess · étape <code>ocr</code>" in html
    assert html == CalibrationSection().render(_result(), SectionContext())


def test_renders_calibration_curve() -> None:
    html = CalibrationSection().render(_result(), SectionContext())
    assert html is not None
    assert 'class="calib-svg"' in html  # courbe SVG
    assert 'class="calib-diag"' in html  # diagonale = calibration parfaite
    assert 'class="calib-line"' in html  # polyligne du moteur


def test_without_payload_renders_nothing() -> None:
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=0,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    assert (
        CalibrationSection().render(RunResult(manifest=manifest), SectionContext())
        is None
    )


def test_renders_english_labels() -> None:
    html = CalibrationSection().render(_result(), SectionContext(lang="en"))
    assert html is not None
    assert "confidence calibration" in html
    assert "calibration des confidences" not in html
    assert "mean confidence" in html and "confiance moyenne" not in html
    assert "accuracy" in html and "exactitude" not in html
