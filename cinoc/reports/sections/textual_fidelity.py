"""Section fidélité textuelle : tokens rares + modernisation lexicale (couche 7).

Rend le payload ``textual_fidelity`` en **lecture seule** : par pipeline, le
rappel des tokens rares (avec un échantillon de manqués) et le **flux de
modernisation** (#17) — forme historique de la GT → variantes produites, chips
dimensionnés par fréquence (« voir les tokens réécrits »). Pédagogie en prose —
aucun scalaire de classement (≠ glossaire).
"""

from __future__ import annotations

from cinoc.evaluation.analysis import (
    ModernizedToken,
    PipelineTextualFidelity,
    TextualFidelityPayload,
)
from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._alignment_note import alignment_note
from cinoc.reports.sections._payload import render_payload_section


def _rare_row(
    row: PipelineTextualFidelity, order: dict[str, int], lang: str
) -> str:
    if row.n_rare_reference == 0:
        recall = "—"
        missed = "—"
    else:
        recall = (
            localize_decimal(f"{row.rare_recall:.1%}", lang)
            if row.rare_recall is not None
            else "—"
        )
        missed = (
            f'<span class="muted">{escape(", ".join(row.missed))}</span>'
            if row.missed
            else "—"
        )
    badge = engine_cell(row.pipeline, order.get(row.pipeline, 0))
    return (
        f'<tr><td class="eng-cell">{badge}</td>'
        f'<td class="disp">{row.n_rare_recalled}/{row.n_rare_reference}</td>'
        f'<td class="disp">{recall}</td>'
        f"<td>{missed}</td></tr>"
    )


def _token_flow(token: ModernizedToken, lang: str) -> str:
    """Une forme GT → ses variantes produites (chips, barre ∝ compte = taille)."""
    max_count = token.variants[0].count if token.variants else 1
    chips = "".join(
        f'<span class="wf-dst"><span class="wf-word">{escape(variant.form)}</span>'
        f'<span class="wf-bar" style="width:{round(variant.count / max_count * 40)}px">'
        f'</span><span class="wf-count">×{variant.count}</span></span>'
        for variant in token.variants
    )
    return (
        '<div class="wf-row">'
        f'<span class="wf-word wf-src">{escape(token.token)}</span>'
        f'<span class="wf-meta">{localize_decimal(f"{token.rate:.1%}", lang)}</span>'
        f'<span class="wf-arrow">→</span>{chips}</div>'
    )


def _modernization_block(
    view: str, payload: TextualFidelityPayload, lang: str, order: dict[str, int]
) -> str:
    """Flux de modernisation (#17) : par pipeline, forme GT → variantes produites."""
    groups: list[str] = []
    for row in payload.pipelines:
        if not row.modernization:
            continue
        flows = "".join(_token_flow(token, lang) for token in row.modernization)
        badge = engine_cell(row.pipeline, order.get(row.pipeline, 0))
        groups.append(
            f'<div class="cf-engine"><span class="cf-eng-name">{badge}</span>'
            f'<div class="wflow">{flows}</div></div>'
        )
    if not groups:
        return ""
    head = localized(
        lang,
        f"{view}modernisation lexicale",
        f"{view}lexical modernization",
    )
    prose = localized(
        lang,
        '<p class="muted">Formes historiques de la GT réécrites par le moteur '
        "(diagnostic de prompt LLM) : la forme attendue → les variantes produites "
        "(barre = fréquence ; taux de réécriture en regard ; « ∅ » = mot "
        "supprimé).</p>\n",
        '<p class="muted">Historical GT forms rewritten by the engine '
        "(LLM prompt diagnostic): the expected form → the produced variants "
        "(bar = frequency; rewrite rate alongside; “∅” = deleted "
        "word).</p>\n",
    )
    return f"<h3>{head}</h3>\n" + prose + "".join(groups)


def _block(
    view: str, payload: TextualFidelityPayload, lang: str, order: dict[str, int]
) -> str:
    rare_rows = "".join(_rare_row(row, order, lang) for row in payload.pipelines)
    head = localized(
        lang,
        f"{view}rappel des tokens rares "
        f"(≤ {payload.max_freq} occurrence(s))",
        f"{view}rare-token recall "
        f"(≤ {payload.max_freq} occurrence(s))",
    )
    prose = localized(
        lang,
        '<p class="muted">Les tokens rares (noms propres, toponymes, termes — '
        "hapax et dis legomena du corpus) pèsent en indexation prosopographique "
        "mais sont noyés dans le CER global. Rappel = part des occurrences rares "
        "de la GT retrouvées (multiset).</p>\n",
        '<p class="muted">Rare tokens (proper nouns, toponyms, terms — '
        "corpus hapax and dis legomena) matter for prosopographic indexing "
        "but are drowned out in the global CER. Recall = share of rare GT "
        "occurrences recovered (multiset).</p>\n",
    )
    th_pipeline = localized(lang, "Pipeline", "Pipeline")
    th_recalled_total = localized(lang, "rappelés/total", "recalled/total")
    th_recall = localized(lang, "rappel", "recall")
    th_missed = localized(lang, "manqués (échantillon)", "missed (sample)")
    rare_table = (
        f"<h3>{head}</h3>\n"
        + prose
        + '<table class="data">\n<thead><tr>'
        f"<th>{th_pipeline}</th>"
        f'<th class="num-cell">{th_recalled_total}</th>'
        f'<th class="num-cell">{th_recall}</th>'
        f"<th>{th_missed}</th></tr></thead>\n"
        f"<tbody>{rare_rows}</tbody>\n</table>\n"
    )
    return rare_table + _modernization_block(view, payload, lang, order)


class TextualFidelitySection:
    """Tokens rares + modernisation lexicale, par pipeline (lecture seule)."""

    name = "textual_fidelity"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        order = engine_order(p.pipeline for p in result.pipelines)
        return render_payload_section(
            result,
            ctx,
            payload_type=TextualFidelityPayload,
            title=localized(ctx.lang, "Fidélité textuelle", "Textual fidelity"),
            block=lambda view, payload: _block(view, payload, ctx.lang, order)
            + alignment_note(payload.alignment_path, ctx.lang),
        )


__all__ = ["TextualFidelitySection"]
