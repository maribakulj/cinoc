"""Section dispersion : bandes SVG min·médiane·µ·max par moteur (donnée par-doc)."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import (
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.dispersion import DispersionSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _doc(doc_id: str, pipeline: str, cer: float) -> RunDocumentResult:
    return RunDocumentResult(
        document_id=doc_id,
        pipeline=pipeline,
        view="text",
        scores=(MetricScore(metric="cer", value=cer, support=1),),
    )


def _result(*documents: RunDocumentResult) -> RunResult:
    manifest = RunManifest(
        run_id="r",
        corpus_name="demo",
        n_documents=2,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    pipelines = tuple(
        PipelineResult(pipeline=p, view="text", conditional_aggregate=())
        for p in dict.fromkeys(d.pipeline for d in documents)
    )
    return RunResult(manifest=manifest, pipelines=pipelines, documents=documents)


def test_renders_one_strip_per_engine() -> None:
    html = DispersionSection().render(
        _result(
            _doc("d1", "tesseract", 0.10),
            _doc("d2", "tesseract", 0.30),
            _doc("d1", "pero", 0.05),
            _doc("d2", "pero", 0.15),
        ),
        SectionContext(),
    )
    assert html is not None
    assert "Dispersion du CER" in html
    assert html.count('class="disp-row"') == 2  # un par moteur
    assert html.count('class="box-plot"') == 2  # une boîte SVG par moteur
    # labels min·Q1·méd·µ·Q3·max en pourcentage (échelle commune : max 30 %)
    assert (
        "min 10,0 % · Q1 5,0 % · méd 20,0 % · µ 20,0 % · Q3 35,0 % · max 30,0 %"
        in html
    )  # tesseract


def test_none_without_documents() -> None:
    manifest = RunManifest(
        run_id="r",
        corpus_name="demo",
        n_documents=0,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    empty = RunResult(manifest=manifest)
    assert DispersionSection().render(empty, SectionContext()) is None


def test_deterministic() -> None:
    r = _result(_doc("d1", "tess", 0.1), _doc("d2", "tess", 0.2))
    a = DispersionSection().render(r, SectionContext())
    b = DispersionSection().render(r, SectionContext())
    assert a == b


def test_renders_english_labels() -> None:
    html = DispersionSection().render(
        _result(
            _doc("d1", "tesseract", 0.10),
            _doc("d2", "tesseract", 0.30),
        ),
        SectionContext(lang="en"),
    )
    assert html is not None
    assert "CER dispersion" in html and "Dispersion du CER" not in html
    assert "Box plot per engine" in html and "Boîte à moustaches" not in html
    assert "Common scale across engines" in html
    # labels use the English "med" abbreviation, not the French "méd"
    assert "med 20.0 %" in html and "méd" not in html
