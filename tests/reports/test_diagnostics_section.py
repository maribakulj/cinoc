"""Section diagnostic : lecture seule du payload, rendu déterministe."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    CharConfusion,
    DiagnosticsPayload,
    HardDocument,
    PipelineConfusions,
    WorstLine,
)
from cinoc.evaluation.result import RunResult
from cinoc.reports.section import Section, SectionContext
from cinoc.reports.sections.diagnostics import DiagnosticsSection

FIXED = datetime(2026, 6, 1, tzinfo=UTC)


def _result() -> RunResult:
    payload = DiagnosticsPayload(
        metric="cer",
        confusions=(
            PipelineConfusions(
                pipeline="tess",
                pairs=(
                    CharConfusion(expected="e", observed="o", count=12),
                    # paire porteuse de méta-caractères : vérifie l'échappement.
                    CharConfusion(expected="&", observed="<", count=5),
                ),
                # Liste complète : le payload le dit (N7), sans quoi la phrase
                # « ni plus ni moins » n'est pas écrite.
                n_pairs=2,
                n_substitutions=17,
            ),
        ),
        worst_lines=(
            WorstLine(
                pipeline="tess",
                document_id="d7",
                line_index=3,
                cer=0.62,
                reference="le chevalier <s>preux</s>",
                hypothesis="lo chovalior preux",
            ),
        ),
        hardest_documents=(
            HardDocument(document_id="d7", mean_cer=0.41, n_pipelines=3),
        ),
    )
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )


def test_satisfies_section_protocol() -> None:
    section = DiagnosticsSection()
    assert isinstance(section, Section)
    assert section.name == "diagnostics"


def test_renders_confusions_lines_and_hardest_with_escaping() -> None:
    html = DiagnosticsSection().render(_result(), SectionContext())
    assert html is not None
    # #8 flux de confusion : glyphes attendu → produit, prominents + fréquence.
    assert 'class="cf-grid"' in html and "tess" in html
    assert 'class="cf-glyph">e</span>' in html  # glyphe attendu
    assert 'class="cf-glyph">o</span>' in html  # glyphe produit
    assert "12" in html and "5" in html  # fréquences (deux paires)
    # Anti-XSS : les glyphes méta-caractères sont **échappés** dans leur slot.
    assert 'class="cf-glyph">&amp;</span>' in html
    assert 'class="cf-glyph">&lt;</span>' in html
    assert "0,6200" in html and "d7" in html
    # Drill-in : diff GT↔hypothèse surligné caractère à caractère.
    assert 'class="d-del"' in html  # suppressions (présentes en GT)
    assert 'class="d-ins"' in html  # insertions (produites par le moteur)
    # Les extraits verbatim restent **échappés** même découpés par le diff
    # (anti-XSS) : `<s>` n'apparaît jamais brut, seulement `&lt;s&gt;`.
    assert "<s>preux</s>" not in html and "&lt;s&gt;" in html
    assert "preux" in html  # segment identique rendu tel quel
    assert "0,4100" in html
    assert html == DiagnosticsSection().render(_result(), SectionContext())


def test_confusion_flow_title_is_bilingual() -> None:
    english = DiagnosticsSection().render(_result(), SectionContext(lang="en"))
    assert english is not None and "expected → produced" in english
    french = DiagnosticsSection().render(_result(), SectionContext(lang="fr"))
    assert french is not None and "attendu → produit" in french


def test_without_payload_renders_nothing() -> None:
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=0,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    assert (
        DiagnosticsSection().render(RunResult(manifest=manifest), SectionContext())
        is None
    )


def test_worst_lines_say_how_lines_are_paired_in_both_languages() -> None:
    # D-286 : appariées par l'alignement de lignes (F15), plus par index.
    english = DiagnosticsSection().render(_result(), SectionContext(lang="en"))
    assert english is not None
    assert "Worst lines of the corpus" in english
    assert "an added line does not shift the following ones" in english
    assert "<th>hypothesis</th>" in english and "Pires lignes" not in english
    french = DiagnosticsSection().render(_result(), SectionContext(lang="fr"))
    assert french is not None
    assert "une ligne ajoutée ne décale pas les suivantes" in french
    assert "substitutions que compte le CER" in french
