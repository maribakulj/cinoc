"""Pagination des longues listes : marqueur ``data-paginate`` présent et — surtout
— **aucun document retiré** (toutes les cartes/lignes restent dans le HTML ; seul
``report.js`` borne l'affichage à une page). Encode l'exigence : à 5000 docs, la
galerie et les tables **contiennent tout**."""

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
from cinoc.reports.sections.by_document import DocumentSection
from cinoc.reports.sections.gallery import DocumentGallerySection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)
_N = 300


def _result() -> RunResult:
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=_N, code_version="1.0",
        started_at=FIXED, completed_at=FIXED,
    )
    pipelines = (PipelineResult(
        pipeline="tesseract", view="text",
        conditional_aggregate=(MetricScore(metric="cer", value=0.2, support=_N),),
    ),)
    docs = tuple(
        RunDocumentResult(
            document_id=f"doc{i:04d}", pipeline="tesseract", view="text",
            scores=(MetricScore(metric="cer", value=(i % 100) / 100.0, support=10),),
        )
        for i in range(_N)
    )
    return RunResult(manifest=manifest, pipelines=pipelines, documents=docs)


def test_gallery_keeps_all_cards_and_marks_pagination() -> None:
    html = DocumentGallerySection().render(_result(), SectionContext())
    assert html is not None
    assert 'data-paginate="60"' in html
    assert html.count("doc-card") == _N  # TOUTES les cartes présentes, rien retiré


def test_by_document_keeps_all_documents_and_marks_pagination() -> None:
    html = DocumentSection().render(_result(), SectionContext())
    assert html is not None
    assert 'data-paginate="50"' in html
    for i in (0, 150, _N - 1):
        assert f"doc{i:04d}" in html  # documents début/milieu/fin tous présents
