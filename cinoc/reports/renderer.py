"""``ReportRenderer`` — compose des sections en un document HTML autonome.

**Injecté par l'``app``** (reports ne connaît pas app) : ``app`` choisit les
sections. ``default_report_renderer`` fournit le socle (overview) du squelette.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping

from cinoc.evaluation.result import RunResult
from cinoc.reports.compare_widget import compare_widget
from cinoc.reports.csv_export import run_result_csv
from cinoc.reports.embedded import inline_script
from cinoc.reports.glossary_panel import glossary_chrome_link, glossary_dialog
from cinoc.reports.html import escape, render_document
from cinoc.reports.section import Html, Section, SectionContext

#: Libellés FR des sections pour le sommaire (deeplinks) ; repli = nom brut.
_SECTION_LABELS = {
    "key_measures": "Mesures clés",
    "overview": "Vue d'ensemble",
    "corpus_composition": "Composition",
    "by_engine": "Par moteur",
    "engine_radar": "Profil radar",
    "engine_profiles": "Profils moteur",
    "document_details": "Détail document",
    "documents": "Par document",
    "dispersion": "Dispersion",
    "cross_engine": "Inter-moteurs",
    "engine_duel": "Duel par document",
    "word_errors": "Carte des mots",
    "conformity": "Conformité HIPE",
    "structure": "Structure",
    "correction": "Bilan de correction",
    "structured_data": "Données structurées",
    "philology": "Philologie",
    "textual_fidelity": "Fidélité textuelle",
    "decisions": "Décisions du correcteur",
    "lines": "Par ligne",
    "ner": "Entités nommées",
    "economics": "Économie",
    "diagnostics": "Diagnostic",
    "taxonomy": "Taxonomie",
    "calibration": "Calibration",
    "composition": "Composition des chaînes",
    "methodology": "Méthodologie",
}

#: Libellés **EN** des sections (parité de clés avec ``_SECTION_LABELS``) — pour
#: l'``aria-label`` des blocs quand le rapport est rendu en anglais (``?lang=en``).
_SECTION_LABELS_EN = {
    "key_measures": "Key measures",
    "overview": "Overview",
    "corpus_composition": "Composition",
    "by_engine": "By engine",
    "engine_radar": "Radar profile",
    "engine_profiles": "Engine profiles",
    "document_details": "Document detail",
    "documents": "By document",
    "dispersion": "Dispersion",
    "cross_engine": "Cross-engine",
    "engine_duel": "Per-document duel",
    "conformity": "HIPE conformity",
    "structure": "Layout structure",
    "correction": "Correction balance",
    "structured_data": "Structured data",
    "philology": "Philology",
    "textual_fidelity": "Textual fidelity",
    "decisions": "Corrector decisions",
    "lines": "Per line",
    "ner": "Named entities",
    "economics": "Economics",
    "diagnostics": "Diagnostics",
    "taxonomy": "Taxonomy",
    "calibration": "Calibration",
    "composition": "Pipeline composition",
    "methodology": "Methodology",
}


def _label(name: str, lang: str = "fr") -> str:
    table = _SECTION_LABELS_EN if lang == "en" else _SECTION_LABELS
    return table.get(name, name)


#: Deux **modes** d'interaction (≠ onglets par sujet) : « Rapport » (document
#: défilant, lecture/impression) et « Explorer » (triage des documents). La bascule
#: vit dans le chrome (réutilise la barre ``.report-tabs`` → ancres ``#mode-*``).
_MODE_ORDER = ("rapport", "explorer")
_MODE_LABELS = {
    "fr": {"rapport": "Rapport", "explorer": "Explorer"},
    "en": {"rapport": "Report", "explorer": "Explorer"},
}
_MODE_SWITCH_LABEL = {"fr": "Mode de lecture", "en": "Reading mode"}
_SPINE_LABEL = {"fr": "Sommaire", "en": "Contents"}

#: Groupes ordonnés ``(mode, clé, fr, en, sections…)``. Chaque groupe présent
#: ouvre un sous-titre ancré (``#grp-<clé>``) que le spine du mode référence. Une
#: section hors de tout groupe et non-détail est rendue en **pied** (annexe, ex.
#: ``methodology``). Garde-fou : ``test_groups_cover_grouped_sections``.
_GROUPS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("rapport", "key", "Mesures clés", "Key measures",
     ("key_measures", "overview", "corpus_composition", "composition")),
    ("rapport", "compare", "Comparaison", "Engine comparison",
     ("by_engine", "engine_radar", "dispersion")),
    ("rapport", "crosses", "Significativité & recouvrement", "Significance & overlap",
     ("cross_engine", "engine_duel", "word_errors")),
    ("rapport", "errors", "Familles d'erreurs & analyses fines",
     "Error families & fine-grained analyses",
     ("conformity", "structure", "correction", "decisions", "structured_data",
      "philology",
      "textual_fidelity", "lines", "ner", "taxonomy", "calibration", "diagnostics")),
    ("rapport", "economics", "Économie", "Economics", ("economics",)),
    ("explorer", "documents", "Documents", "Documents", ("documents",)),
)

#: Section **détail** (maître/détail) de chaque mode : rendue dans un conteneur
#: ``.tab-detail`` que ``report.js`` échange au clic (≠ ancre). Hors groupes.
_DETAIL_OF_MODE = {"rapport": "engine_profiles", "explorer": "document_details"}

#: Index inverse section → mode (groupes + détails). Sert au pied (annexe) et au
#: garde-fou de couverture.
_SECTION_MODE: dict[str, str] = {
    **{name: mode for mode, _k, _fr, _en, names in _GROUPS for name in names},
    **{detail: mode for mode, detail in _DETAIL_OF_MODE.items()},
}


#: Sections **intrinsèquement larges** (tableaux multi-colonnes, galeries, charts
#: pleine largeur) : elles prennent toute la largeur dans le flux de cartes
#: (``column-span:all``). Les autres (petits charts/listes) s'écoulent en colonnes.
_WIDE_SECTIONS: frozenset[str] = frozenset({
    # ``composition`` : un tableau de cinq colonnes par pipeline, dont une de
    # réglages qui peut être longue. En colonne étroite, chaque cellule se
    # replie sur trois lignes et le montage devient illisible — c'est-à-dire
    # que la section rate précisément ce pour quoi elle existe.
    "composition",
    "key_measures", "overview", "by_engine", "engine_profiles", "conformity",
    "structured_data", "ner", "lines", "economics", "cross_engine",
    "word_errors", "taxonomy", "correction", "decisions", "textual_fidelity",
    "documents",
    "diagnostics",
})


def _block(name: str, html: str, lang: str) -> str:
    """Une section = sa **propre carte** ``.sec``, région ancrée (``#r-<name>``)."""
    wide = " r-wide" if name in _WIDE_SECTIONS else ""
    return (
        f'<section id="r-{escape(name)}" class="r-block sec{wide}" '
        f'aria-label="{escape(_label(name, lang))}">{html}</section>'
    )


def _spine(links: list[tuple[str, str]], lang: str) -> str:
    """Sommaire collant d'un mode : liens ancrés vers les sous-titres de groupe."""
    if not links:
        return ""
    items = "".join(
        f'<a class="spine-link" href="#{gid}">{label}</a>' for gid, label in links
    )
    aria = escape(_SPINE_LABEL.get(lang, _SPINE_LABEL["fr"]))
    return f'<nav class="spine" aria-label="{aria}">{items}</nav>'


def _mode_body(
    mode: str, by_name: dict[str, str], lang: str
) -> tuple[str, list[tuple[str, str]]]:
    """Corps d'un mode : maître groupé (sous-titres ancrés, cartes ``.sec``) +
    détail (``_DETAIL_OF_MODE``) brut dans ``.tab-detail``, le tout dans un
    ``.drill-scope`` (unité maître/détail échangée par ``report.js``). ``("", [])``
    si le mode n'a aucune section. Renvoie aussi les ancres pour le spine."""
    detail_name = _DETAIL_OF_MODE.get(mode, "")
    groups: list[tuple[str, str, list[str]]] = []
    for m, key, fr, en, names in _GROUPS:
        if m != mode:
            continue
        present = [n for n in names if n in by_name and n != detail_name]
        if not present:
            continue
        label = escape(en if lang == "en" else fr)
        groups.append((f"grp-{escape(key)}", label, present))
    # Un seul groupe présent → son sous-titre (et un sommaire à un seul lien) font
    # double emploi avec le nom du mode : on les omet, les sections s'écoulent
    # directement. Plusieurs groupes → sous-titres ancrés + spine collant.
    show_heads = len(groups) > 1
    parts: list[str] = []
    spine_links: list[tuple[str, str]] = []
    for gid, label, present in groups:
        if show_heads:
            parts.append(f'<h2 class="tab-subhead" id="{gid}">{label}</h2>')
            spine_links.append((gid, label))
        parts.extend(_block(n, by_name[n], lang) for n in present)
    detail_raw = by_name.get(detail_name, "") if detail_name else ""
    if not parts and not detail_raw:
        return "", []
    master = f'<div class="tab-master">{"".join(parts)}</div>'
    detail = (
        f'<div class="tab-detail" data-mode="{escape(mode)}">{detail_raw}</div>'
        if detail_raw
        else ""
    )
    return f'<div class="drill-scope">{master}{detail}</div>', spine_links


def _mode_layout(rendered: list[tuple[str, str]], lang: str) -> tuple[str, str]:
    """Compose les sections en **2 modes** → ``(bascule, corps)``.

    La **bascule** (réutilise ``.report-tabs`` → ancres ``#mode-*``) part dans le
    chrome ; le **corps** (modes empilés) dans ``<main>``. Chaque mode porte un
    spine collant + son maître/détail. Sans JS, les deux modes restent visibles
    (rapport plat) ; ``report.js`` n'en montre qu'un. Sous 2 modes actifs, pas de
    bascule. Sections hors mode (ex. ``methodology``) → **pied**, hors modes."""
    by_name = dict(rendered)
    mlabels = _MODE_LABELS.get(lang, _MODE_LABELS["fr"])
    modes: list[tuple[str, str]] = []
    for mode in _MODE_ORDER:
        body, links = _mode_body(mode, by_name, lang)
        if not body:
            continue
        section = (
            f'<section class="mode" id="mode-{mode}" '
            f'aria-label="{escape(mlabels[mode])}">'
            f'{_spine(links, lang)}<div class="mode-body">{body}</div></section>'
        )
        modes.append((mode, section))
    trailer = "".join(
        _block(n, h, lang) for n, h in rendered if n not in _SECTION_MODE
    )
    corps = "".join(html for _m, html in modes) + trailer
    if len(modes) < 2:
        return "", corps
    switch = "".join(
        f'<a id="msw-{m}" class="report-tab{" on" if i == 0 else ""}" role="tab" '
        f'href="#mode-{m}" aria-controls="mode-{m}" '
        f'aria-selected="{"true" if i == 0 else "false"}">{escape(mlabels[m])}</a>'
        for i, (m, _html) in enumerate(modes)
    )
    nav = (
        f'<nav class="report-tabs mode-switch" role="tablist" '
        f'aria-label="{escape(_MODE_SWITCH_LABEL.get(lang, _MODE_SWITCH_LABEL["fr"]))}'
        f'">{switch}</nav>'
    )
    return nav, corps


def _data_href(text: str, mime: str) -> str:
    """``data:`` URI base64 d'un export — téléchargeable, hors-ligne, déterministe."""
    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return f"data:{mime};charset=utf-8;base64,{payload}"


def _chrome_meta(result: RunResult, lang: str, *, glossary_btn: str = "") -> str:
    """Méta de run (docs/moteurs/date) + actions (**Glossaire** · CSV · JSON).

    Exports = ``<a download>`` vers des ``data:`` URI (zéro JS, autonome,
    hors-ligne). Le JSON embarqué est le ``RunResult`` complet — la matière à
    redonner à un outil tiers (cf. saveur « données » du cadre rapport).
    ``glossary_btn`` (lien-ancre vers le dialog) précède les exports ; vide si
    aucune métrique présente n'a d'entrée de glossaire."""
    n_docs = result.manifest.n_documents
    n_engines = len({p.pipeline for p in result.pipelines})
    date = result.manifest.completed_at.date().isoformat()
    docs_lbl = "docs"
    eng_lbl = "engines" if lang == "en" else "moteurs"
    csv_href = _data_href(run_result_csv(result), "text/csv")
    json_href = _data_href(result.model_dump_json(), "application/json")
    stem = escape(result.manifest.run_id)
    return (
        '<div class="chrome-meta">'
        f'<span><span class="v">{n_docs}</span> {docs_lbl}</span>'
        f'<span><span class="v">{n_engines}</span> {eng_lbl}</span>'
        f'<span class="v">{escape(date)}</span>'
        '<div class="chrome-actions">'
        f"{glossary_btn}"
        f'<a class="chrome-btn" download="{stem}.csv" href="{csv_href}">⬇ CSV</a>'
        f'<a class="chrome-btn" download="{stem}.json" href="{json_href}">⬇ JSON</a>'
        "</div></div>"
    )


class ReportRenderer:
    """Assemble les sections applicables en un rapport HTML."""

    def __init__(self, sections: tuple[Section, ...]) -> None:
        self._sections = sections

    def render(
        self,
        result: RunResult,
        *,
        title: str = "Cinoc — rapport",
        lang: str = "fr",
        images: Mapping[str, str] | None = None,
        facsimiles: Mapping[str, str] | None = None,
    ) -> str:
        known = {
            score.metric
            for pipeline in result.pipelines
            for score in pipeline.aggregate
        }
        ctx = SectionContext(
            title=title,
            lang=lang,
            images=images or {},
            facsimiles=facsimiles or {},
        )
        rendered: list[tuple[str, str]] = []
        for section in self._sections:
            if section.requires and not set(section.requires) <= known:
                continue  # no-orphan : métriques requises absentes
            html = section.render(result, ctx)
            if html is not None:
                rendered.append((section.name, html))
        # 2 modes (Rapport/Explorer) : bascule (→ chrome) + corps (→ main).
        # Sections rendues serveur ; ``report.js`` bascule l'affichage.
        switch, body = _mode_layout(rendered, lang)
        # Glossaire = périphérie (chrome) : dialog (vide si aucune métrique connue
        # n'a d'entrée) + lien-ancre dans la barre d'actions.
        gloss_dialog = glossary_dialog(known, lang)
        gloss_link = glossary_chrome_link(lang) if gloss_dialog else ""
        meta = _chrome_meta(result, lang, glossary_btn=gloss_link)
        # Pied : widget « comparer un run » + dialog glossaire + script (onglets +
        # dialog + nav clavier + palette). Tous client-side, déterministes, inlinés.
        footer = Html(
            compare_widget(result) + gloss_dialog + inline_script("report.js")
        )
        return render_document(
            title, Html(body), footer=footer, lang=lang, tabs=switch, meta=meta
        )


def default_report_renderer() -> ReportRenderer:
    """Socle : synthèse, overview, par-moteur/document, stats, économie,
    diagnostic. Le glossaire est **hors sections** (dialog du chrome)."""
    from cinoc.reports.sections.by_engine import EngineSection
    from cinoc.reports.sections.calibration import CalibrationSection
    from cinoc.reports.sections.composition import CompositionSection
    from cinoc.reports.sections.conformity import ConformitySection
    from cinoc.reports.sections.corpus_composition import CorpusCompositionSection
    from cinoc.reports.sections.correction import CorrectionSection
    from cinoc.reports.sections.cross_engine import CrossEngineSection
    from cinoc.reports.sections.decisions import DecisionsSection
    from cinoc.reports.sections.diagnostics import DiagnosticsSection
    from cinoc.reports.sections.dispersion import DispersionSection
    from cinoc.reports.sections.document_detail import DocumentDetailSection
    from cinoc.reports.sections.documents import DocumentsSection
    from cinoc.reports.sections.economics import EconomicsSection
    from cinoc.reports.sections.engine_duel import EngineDuelSection
    from cinoc.reports.sections.engine_profile import EngineProfileSection
    from cinoc.reports.sections.engine_radar import EngineRadarSection
    from cinoc.reports.sections.key_measures import KeyMeasuresSection
    from cinoc.reports.sections.lines import LinesSection
    from cinoc.reports.sections.methodology import MethodologySection
    from cinoc.reports.sections.ner import NerSection
    from cinoc.reports.sections.overview import OverviewSection
    from cinoc.reports.sections.philology import PhilologySection
    from cinoc.reports.sections.structure import StructureSection
    from cinoc.reports.sections.structured_data import StructuredDataSection
    from cinoc.reports.sections.taxonomy import TaxonomySection
    from cinoc.reports.sections.textual_fidelity import TextualFidelitySection
    from cinoc.reports.sections.word_errors import WordErrorsSection

    return ReportRenderer(
        (
            KeyMeasuresSection(),
            OverviewSection(),
            CorpusCompositionSection(),
            CompositionSection(),
            EngineSection(),
            EngineRadarSection(),
            EngineProfileSection(),
            DispersionSection(),
            DocumentsSection(),
            DocumentDetailSection(),
            CrossEngineSection(),
            WordErrorsSection(),
            EngineDuelSection(),
            ConformitySection(),
            StructureSection(),
            CorrectionSection(),
            DecisionsSection(),
            StructuredDataSection(),
            PhilologySection(),
            TextualFidelitySection(),
            LinesSection(),
            NerSection(),
            EconomicsSection(),
            DiagnosticsSection(),
            TaxonomySection(),
            CalibrationSection(),
            MethodologySection(),
        )
    )


__all__ = ["ReportRenderer", "default_report_renderer"]
