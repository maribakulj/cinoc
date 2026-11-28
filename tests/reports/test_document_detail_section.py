"""Section détail document : panneaux drill-in (CER/moteur + diff pires lignes)."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    DiagnosticsPayload,
    DocumentHallucination,
    DocumentHallucinationPayload,
    DocumentLines,
    DocumentLinesPayload,
    DocumentTexts,
    DocumentTextsPayload,
    HallucinatedBlock,
    PipelineHallucination,
    WorstLine,
)
from cinoc.evaluation.result import (
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.document_detail import DocumentDetailSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _doc(doc_id: str, pipeline: str, cer: float) -> RunDocumentResult:
    return RunDocumentResult(
        document_id=doc_id, pipeline=pipeline, view="text",
        scores=(MetricScore(metric="cer", value=cer, support=1),),
    )


def _result(*, with_worst: bool = False) -> RunResult:
    manifest = RunManifest(
        run_id="r", corpus_name="demo", n_documents=2,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    docs = (
        _doc("folio_1", "tesseract", 0.20), _doc("folio_1", "pero", 0.10),
        _doc("folio_2", "tesseract", 0.30),
    )
    analyses = ()
    if with_worst:
        payload = DiagnosticsPayload(
            metric="cer",
            worst_lines=(
                WorstLine(
                    pipeline="tesseract", document_id="folio_1", line_index=3,
                    cer=0.5, reference="le chat", hypothesis="le chien",
                ),
            ),
        )
        analyses = (Analysis(scope="corpus", view="text", payload=payload),)
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(pipeline="tesseract", view="text", conditional_aggregate=()),
            PipelineResult(pipeline="pero", view="text", conditional_aggregate=()),
        ),
        documents=docs,
        analyses=analyses,
    )


def test_one_template_per_document_plus_live_container() -> None:
    html = DocumentDetailSection().render(_result(), SectionContext())
    assert html is not None
    # Chaque fiche est dans un <template> inerte (clonée à la demande par report.js)
    # → DOM borné à grande échelle, fac-similés chargés seulement à l'ouverture.
    assert html.count("<template data-doc=") == 2  # une par document
    assert 'data-doc="0"' in html and 'data-doc="1"' in html  # ≡ ordre galerie
    assert html.count('class="drill-panel doc-detail"') == 2  # fiche rendue serveur
    assert 'class="doc-detail-live"' in html  # conteneur vivant unique (cible clone)
    assert " hidden " not in html.split("doc-detail-live")[0]  # live non caché
    assert "← Tous les documents" in html


def test_keeps_all_documents_as_templates_at_scale() -> None:
    # Tous les documents restent atteignables (un <template> chacun) ; rien retiré.
    manifest = RunManifest(
        run_id="r", corpus_name="demo", n_documents=300,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    docs = tuple(
        _doc(f"doc{i:04d}", "tesseract", (i % 100) / 100.0) for i in range(300)
    )
    result = RunResult(
        manifest=manifest,
        pipelines=(PipelineResult(pipeline="tesseract", view="text"),),
        documents=docs,
    )
    html = DocumentDetailSection().render(result, SectionContext())
    assert html is not None
    assert html.count("<template data-doc=") == 300  # les 300 fiches présentes
    assert 'data-doc="299"' in html


def test_panel_shows_cer_per_engine() -> None:
    html = DocumentDetailSection().render(_result(), SectionContext())
    assert html is not None
    assert "CER par moteur" in html
    assert "20,0 %" in html and "10,0 %" in html  # folio_1 : tesseract / pero


def test_worst_lines_diff_when_present() -> None:
    html = DocumentDetailSection().render(_result(with_worst=True), SectionContext())
    assert html is not None
    assert "Pires lignes" in html
    assert 'class="diff"' in html  # diff caractère réutilisé (text_diff)
    assert "ligne 3" in html


def test_facsimile_shown_when_provided() -> None:
    ctx = SectionContext(facsimiles={"folio_1": "data:image/jpeg;base64,ZZZ"})
    html = DocumentDetailSection().render(_result(), ctx)
    assert html is not None
    assert 'class="dd-fac-top"' in html  # fac-similé en haut (pleine largeur)
    assert 'class="dd-fac-zoom"' in html  # conteneur zoomable/pan
    assert 'class="dd-fac-img" src="data:image/jpeg;base64,ZZZ"' in html
    assert 'data-zoom="in"' in html and 'data-zoom="reset"' in html  # contrôles zoom
    # un doc sans fac-similé reste en pleine largeur (pas d'image vide)
    plain = DocumentDetailSection().render(_result(), SectionContext())
    assert plain is not None and "dd-fac-img" not in plain


def test_full_page_diff_with_engine_selector() -> None:
    base = _result()
    texts = DocumentTextsPayload(
        documents=(
            DocumentTexts(
                document_id="folio_1",
                reference="le chat noir",
                hypotheses=(("pero", "le chat noir"), ("tesseract", "le chien noir")),
            ),
        )
    )
    result = base.model_copy(
        update={"analyses": (Analysis(scope="corpus", view="text", payload=texts),)}
    )
    html = DocumentDetailSection().render(result, SectionContext())
    assert html is not None
    assert "page complète" in html  # diff pleine page (≠ pires lignes)
    assert 'class="dd-engine-tabs' in html  # sélecteur de moteur
    assert html.count('class="dd-fulldiff"') == 2  # un bloc par moteur
    assert html.count('class="dd-sbs"') == 2  # GT | sortie côte à côte par moteur
    assert "Vérité terrain" in html and "Sortie ·" in html
    # le diff caractère est marqué (insertion/suppression)
    assert 'class="d-ins"' in html or 'class="d-del"' in html



def test_line_heatmap_recentred_on_document() -> None:
    base = _result()
    dl = DocumentLinesPayload(
        documents=(
            DocumentLines(
                document_id="folio_1",
                pipelines=(("tesseract", (0.0, 0.20, 0.5)), ("pero", (0.0, 0.0, 0.1))),
            ),
        )
    )
    result = base.model_copy(
        update={"analyses": (Analysis(scope="corpus", view="text", payload=dl),)}
    )
    html = DocumentDetailSection().render(result, SectionContext())
    assert html is not None
    assert 'class="dd-lh"' in html  # distribution par ligne du doc
    assert "dd-lh-bar lh-g" in html and "dd-lh-bar lh-b" in html  # carte thermique
    assert "height:4px" in html and "height:22px" in html  # hauteur ∝ CER (0.0 / 0.5)
    assert html.count('class="dd-ld-row"') == 2  # une distribution par moteur
    assert 'class="dd-pct-row"' in html and "p99" in html  # percentiles CER
    assert "Gini" in html and "CER≥30 %" in html  # badges de distribution



def test_hallucination_block_recentred_on_document() -> None:
    base = _result()
    dh = DocumentHallucinationPayload(
        documents=(
            DocumentHallucination(
                document_id="folio_1",
                pipelines=(
                    PipelineHallucination(
                        pipeline="tesseract",
                        anchor_score=0.20,
                        length_ratio=1.35,
                        net_insertion_rate=0.45,
                        gt_words=36,
                        hyp_words=42,
                        is_hallucinating=True,
                        blocks=(
                            HallucinatedBlock(
                                start_token=0, end_token=5, text="durch beflhuß vom san"
                            ),
                        ),
                    ),
                ),
            ),
        )
    )
    result = base.model_copy(
        update={"analyses": (Analysis(scope="corpus", view="text", payload=dh),)}
    )
    html = DocumentDetailSection().render(result, SectionContext())
    assert html is not None
    assert 'class="dd-hl"' in html  # analyse hallucination du doc
    assert "Ancrage 20 %" in html and "Insertion nette 45 %" in html  # indicateurs
    assert 'class="dd-hl-flag"' in html  # drapeau hallucination détectée
    assert "durch beflhuß vom san" in html  # bloc halluciné affiché


def test_none_without_documents() -> None:
    manifest = RunManifest(
        run_id="r", corpus_name="demo", n_documents=0,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    empty = RunResult(manifest=manifest)
    assert DocumentDetailSection().render(empty, SectionContext()) is None


def test_renders_english_labels() -> None:
    html = DocumentDetailSection().render(
        _result(with_worst=True), SectionContext(lang="en")
    )
    assert html is not None
    assert "CER per engine" in html and "CER par moteur" not in html
    assert "Worst lines" in html and "Pires lignes" not in html
    assert "← All documents" in html and "← Tous les documents" not in html
