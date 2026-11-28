"""Renderer : structure 2-modes (Rapport/Explorer), déterminisme, no-orphan."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import (
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.reports.renderer import (
    _DETAIL_OF_MODE,
    _GROUPS,
    _SECTION_MODE,
    ReportRenderer,
    _label,
    _mode_body,
    _mode_layout,
    default_report_renderer,
)
from cinoc.reports.section import Html, SectionContext

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _result() -> RunResult:
    manifest = RunManifest(
        run_id="r",
        corpus_name="demo",
        n_documents=2,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    # Documents présents → le mode Explorer est actif (les deux modes → bascule).
    docs = tuple(
        RunDocumentResult(
            document_id=f"d{i}", pipeline="p", view="text",
            scores=(MetricScore(metric="cer", value=(i % 2) / 10, support=1),),
        )
        for i in range(2)
    )
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(
                pipeline="p",
                view="text",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=0.1, support=1),
                ),
            ),
        ),
        documents=docs,
    )


def test_document_structure_and_determinism() -> None:
    renderer = default_report_renderer()
    html1 = renderer.render(_result())
    html2 = renderer.render(_result())
    assert html1 == html2  # octet-stable
    assert html1.startswith("<!DOCTYPE html>")
    assert "<title>" in html1 and "</html>" in html1
    assert 'class="report-board"' in html1
    assert 'class="report-chrome"' in html1
    assert 'class="r-block sec' in html1  # chaque section = sa propre carte .sec
    assert "data:image/svg+xml" in html1 and "fill-opacity" in html1
    assert 'id="cinoc-compare-btn"' in html1
    assert 'class="eng-badge"' in html1
    # 2 modes : bascule (réutilise .report-tabs) + sections « Rapport » et « Explorer »
    assert 'class="report-tabs mode-switch"' in html1
    assert 'role="tablist"' in html1
    assert 'id="mode-rapport"' in html1 and 'id="mode-explorer"' in html1
    assert 'class="spine"' in html1  # sommaire collant du mode
    assert 'class="drill-scope"' in html1  # unité maître/détail
    assert 'id="r-by_engine"' in html1  # région de section ancrée
    assert 'aria-selected="true"' in html1
    # autonome : aucune ressource externe
    assert "@import" not in html1
    assert "https://" not in html1
    assert "<link" not in html1


class _NeedsWer:
    name = "wer_section"
    requires = ("wer",)

    def render(self, result: RunResult, ctx: SectionContext) -> Html:
        return Html("<p>WER</p>")


class _Always:
    name = "always"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html:
        return Html("<p>ALWAYS</p>")


def test_no_orphan_skips_section_with_unmet_requires() -> None:
    html = ReportRenderer((_NeedsWer(), _Always())).render(_result())
    assert "<p>ALWAYS</p>" in html  # requires=() rendu
    assert "<p>WER</p>" not in html  # requires=("wer",) sauté (seul cer présent)


def test_mode_layout_switch_and_modes() -> None:
    # _mode_layout → (bascule, corps). Vide → rien.
    assert _mode_layout([], "fr") == ("", "")
    # Un seul mode actif → pas de bascule, corps rendu.
    sw1, body1 = _mode_layout([("by_engine", "<p>E</p>")], "fr")
    assert sw1 == "" and 'id="mode-rapport"' in body1 and 'id="r-by_engine"' in body1
    # Deux modes → bascule (.report-tabs) + les deux modes + drill-scope.
    sw, body = _mode_layout(
        [("by_engine", "<p>E</p>"), ("documents", "<p>D</p>")], "fr"
    )
    assert 'class="report-tabs mode-switch"' in sw and 'role="tablist"' in sw
    assert 'href="#mode-rapport"' in sw and 'href="#mode-explorer"' in sw
    assert sw.count('aria-selected="true"') == 1  # un seul mode actif au départ
    assert 'id="mode-rapport"' in body and 'id="mode-explorer"' in body
    assert 'class="drill-scope"' in body
    # Un seul groupe par mode → ni sous-titre ni sommaire (redondant avec le nom
    # du mode).
    assert 'class="spine"' not in body and 'class="tab-subhead"' not in body
    # ≥ 2 groupes dans un mode → le sommaire collant + les sous-titres reviennent.
    _, body2 = _mode_layout(
        [("by_engine", "<p>E</p>"), ("economics", "<p>C</p>")], "fr"
    )
    assert 'class="spine"' in body2 and 'class="tab-subhead"' in body2


def test_mode_body_groups_detail_and_spine() -> None:
    by_name = {
        "by_engine": "<b>RANK</b>",
        "engine_profiles": "<i>PROF</i>",
        "economics": "<i>EC</i>",
    }
    body, links = _mode_body("rapport", by_name, "fr")
    assert 'class="tab-master"' in body and 'class="tab-detail"' in body
    master, _, detail = body.partition('<div class="tab-detail"')
    assert "RANK" in master and "PROF" not in master  # détail hors flux maître
    assert "PROF" in detail
    head = '<h2 class="tab-subhead" id="grp-compare">Comparaison</h2>'
    assert head in master
    assert ("grp-compare", "Comparaison") in links
    assert ("grp-economics", "Économie") in links
    assert master.index("grp-compare") < master.index("grp-economics")
    # EN localisé.
    en_body, _ = _mode_body("rapport", by_name, "en")
    assert "Engine comparison" in en_body


def test_mode_body_empty_mode_returns_nothing() -> None:
    assert _mode_body("explorer", {"by_engine": "x"}, "fr") == ("", [])


def test_groups_cover_sections_no_duplicates() -> None:
    # Pas de doublon entre groupes ; _SECTION_MODE = groupes ∪ détails.
    grouped = [n for _m, _k, _f, _e, names in _GROUPS for n in names]
    assert len(grouped) == len(set(grouped))
    details = set(_DETAIL_OF_MODE.values())
    assert set(grouped) | details == set(_SECTION_MODE)


def test_mode_labels_are_localized() -> None:
    pair = [("by_engine", "<p>E</p>"), ("documents", "<p>D</p>")]
    sw_fr, _ = _mode_layout(pair, "fr")
    assert "Rapport" in sw_fr and "Explorer" in sw_fr
    sw_en, _ = _mode_layout(pair, "en")
    assert "Report" in sw_en and "Explorer" in sw_en


def test_unmapped_section_renders_after_modes() -> None:
    # Une section hors mode (ex. methodology/notes) → pied, après les modes.
    _, body = _mode_layout(
        [("by_engine", "<p>E</p>"), ("documents", "<p>D</p>"), ("notes", "<p>N</p>")],
        "fr",
    )
    assert 'id="r-notes"' in body
    assert body.index('id="r-notes"') > body.index('id="mode-explorer"')


def test_methodology_is_trailer_not_in_a_mode() -> None:
    # methodology n'est dans aucun groupe → rendu en pied (annexe).
    assert "methodology" not in _SECTION_MODE


def test_glossary_is_a_chrome_dialog_not_a_section() -> None:
    html = default_report_renderer().render(_result())
    assert '<dialog id="glossary-dialog"' in html
    assert 'href="#glossary-dialog"' in html
    assert 'id="r-glossary"' not in html


def test_label_falls_back_to_raw_name() -> None:
    assert _label("by_engine") == "Par moteur"
    assert _label("by_engine", "en") == "By engine"
    assert _label("inconnue") == "inconnue"
    assert _label("inconnue", "en") == "inconnue"


def test_chrome_meta_and_exports_present() -> None:
    html = default_report_renderer().render(_result())
    assert 'class="chrome-meta"' in html
    assert "docs" in html and "moteurs" in html
    assert 'download="r.csv"' in html
    assert 'href="data:text/csv' in html
    assert 'download="r.json"' in html
    assert 'href="data:application/json' in html
    assert "https://" not in html


def test_each_section_is_its_own_card() -> None:
    html = default_report_renderer().render(_result())
    assert 'class="r-block sec' in html
    assert '<main class="report-main"><section class="sec">' not in html
