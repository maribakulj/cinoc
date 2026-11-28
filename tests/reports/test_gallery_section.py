"""Section galerie : cartes par document, CER/badges, meilleur surligné, échappement."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import (
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.reports.section import Section, SectionContext
from cinoc.reports.sections.gallery import DocumentGallerySection

FIXED = datetime(2026, 6, 1, tzinfo=UTC)


def _doc(doc_id: str, pipeline: str, cer: float | None) -> RunDocumentResult:
    score = MetricScore(metric="cer", value=cer, support=1)
    return RunDocumentResult(
        document_id=doc_id, pipeline=pipeline, view="text", scores=(score,)
    )


def _result(*docs: RunDocumentResult) -> RunResult:
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=2, code_version="1.0",
        started_at=FIXED, completed_at=FIXED,
    )
    pipelines = (
        PipelineResult(
            pipeline="tesseract", view="text",
            conditional_aggregate=(MetricScore(metric="cer", value=0.25, support=2),),
        ),
        PipelineResult(
            pipeline="openai", view="text",
            conditional_aggregate=(MetricScore(metric="cer", value=0.10, support=1),),
        ),
    )
    return RunResult(manifest=manifest, pipelines=pipelines, documents=docs)


def test_satisfies_section_protocol() -> None:
    section = DocumentGallerySection()
    assert isinstance(section, Section)
    assert section.name == "documents_gallery"


def test_returns_none_without_documents() -> None:
    empty = _result()
    assert DocumentGallerySection().render(empty, SectionContext()) is None


def test_renders_card_per_document_with_cer_and_badges() -> None:
    result = _result(
        _doc("doc1", "tesseract", 0.20),
        _doc("doc1", "openai", 0.10),
        _doc("doc2", "tesseract", 0.30),
    )
    html = DocumentGallerySection().render(result, SectionContext())
    assert html is not None
    assert "Galerie des documents" in html
    assert 'class="doc-grid"' in html
    assert "doc1" in html and "doc2" in html
    assert "doc-preview" in html  # aperçu synthétique (zéro image)
    assert 'class="eng-badge"' in html  # CER par moteur via badges A→E
    assert "0,1000" in html and "0,2000" in html
    # le meilleur moteur du document (openai 0.10 sur doc1) est surligné
    assert "dc-row best" in html


def test_is_deterministic_and_escapes_ids() -> None:
    result = _result(_doc("<x>", "tesseract", 0.20))
    html = DocumentGallerySection().render(result, SectionContext())
    assert html is not None
    assert "<x>" not in html and "&lt;x&gt;" in html  # id échappé (anti-XSS)
    assert html == DocumentGallerySection().render(result, SectionContext())


def test_renders_english_labels() -> None:
    result = _result(_doc("doc1", "tesseract", 0.20))
    html = DocumentGallerySection().render(result, SectionContext(lang="en"))
    assert html is not None
    assert "Document gallery" in html and "Galerie des documents" not in html
    assert "Preview + CER per engine" in html
    assert "Aperçu + CER par moteur" not in html


def _doc_s(
    doc_id: str, pipeline: str, cer: float, stratum: str | None
) -> RunDocumentResult:
    return RunDocumentResult(
        document_id=doc_id, pipeline=pipeline, view="text",
        scores=(MetricScore(metric="cer", value=cer, support=1),), stratum=stratum,
    )


def test_no_stratum_filter_when_fewer_than_two_strata() -> None:
    # 0 strate (None) → pas de filtre ; 1 seule strate → inutile, pas de filtre.
    none_strata = _result(_doc("d1", "tesseract", 0.2), _doc("d2", "tesseract", 0.3))
    html = DocumentGallerySection().render(none_strata, SectionContext())
    assert html is not None and 'class="doc-filter"' not in html
    one = _result(
        _doc_s("d1", "tesseract", 0.2, "presse"),
        _doc_s("d2", "tesseract", 0.3, "presse"),
    )
    html1 = DocumentGallerySection().render(one, SectionContext())
    assert html1 is not None and 'class="doc-filter"' not in html1


def test_stratum_filter_chips_and_card_data_attr() -> None:
    result = _result(
        _doc_s("d1", "tesseract", 0.2, "presse"),
        _doc_s("d2", "tesseract", 0.3, "manuscrit"),
    )
    html = DocumentGallerySection().render(result, SectionContext())
    assert html is not None
    # Rangée de filtre + chip « Toutes » + un chip par strate présente (verbatim).
    assert 'class="doc-filter"' in html
    assert 'data-stratum="*"' in html and "Toutes" in html
    assert 'data-stratum="presse"' in html and 'data-stratum="manuscrit"' in html
    # Les cartes portent leur strate (cible du filtre client).
    assert html.count("doc-card") >= 2
    assert html.count('data-stratum="presse"') >= 2  # 1 chip + ≥1 carte
    # Anti-XSS : une strate est échappée comme tout le reste.
    evil = _result(
        _doc_s("d1", "tesseract", 0.2, "<x>"),
        _doc_s("d2", "tesseract", 0.3, "presse"),
    )
    he = DocumentGallerySection().render(evil, SectionContext())
    assert he is not None and "<x>" not in he and "&lt;x&gt;" in he


def test_real_thumbnail_when_image_provided() -> None:
    result = _result(_doc("doc1", "tesseract", 0.20))
    ctx = SectionContext(images={"doc1": "data:image/jpeg;base64,AAAA"})
    html = DocumentGallerySection().render(result, ctx)
    assert html is not None
    assert 'class="doc-preview doc-preview-img"' in html  # vignette réelle
    assert '<img src="data:image/jpeg;base64,AAAA"' in html
    # un doc sans vignette retombe sur l'aperçu synthétique
    plain = DocumentGallerySection().render(result, SectionContext())
    assert plain is not None and "doc-preview-img" not in plain
