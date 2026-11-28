"""Section documents : galerie d'entrée + bascule ⊞ Grille / ≡ Liste."""

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
from cinoc.reports.sections.documents import DocumentsSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _doc(doc_id: str, pipeline: str, cer: float) -> RunDocumentResult:
    return RunDocumentResult(
        document_id=doc_id, pipeline=pipeline, view="text",
        scores=(MetricScore(metric="cer", value=cer, support=1),),
    )


def _result() -> RunResult:
    manifest = RunManifest(
        run_id="r", corpus_name="demo", n_documents=2,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="tess", view="text", conditional_aggregate=()
            ),
        ),
        documents=(_doc("d1", "tess", 0.10), _doc("d2", "tess", 0.20)),
    )


def test_gallery_is_entry_grid_visible_list_hidden() -> None:
    html = DocumentsSection().render(_result(), SectionContext())
    assert html is not None
    # toggle présent, grille (galerie) = entrée visible, liste (table) cachée
    assert 'class="view-toggle"' in html
    assert 'data-view="grid"' in html and 'data-view="list" hidden' in html
    # la grille porte la galerie, la liste porte la table
    assert 'class="doc-grid"' in html  # cartes de galerie (entrée)
    assert 'data-view="list"' in html  # table by_document (mode liste)
    # la grille précède la liste (galerie = entrée)
    assert html.index('data-view="grid"') < html.index('data-view="list"')


def test_renders_english_labels() -> None:
    html = DocumentsSection().render(_result(), SectionContext(lang="en"))
    assert html is not None
    assert "aria-label=\"Display\"" in html and 'aria-label="Affichage"' not in html
    assert "⊞ Grid" in html and "⊞ Grille" not in html
    assert "≡ List" in html and "≡ Liste" not in html


def test_none_without_documents() -> None:
    manifest = RunManifest(
        run_id="r", corpus_name="demo", n_documents=0,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    empty = RunResult(manifest=manifest)
    assert DocumentsSection().render(empty, SectionContext()) is None


def test_deterministic() -> None:
    r = _result()
    assert DocumentsSection().render(r, SectionContext()) == DocumentsSection().render(
        r, SectionContext()
    )
