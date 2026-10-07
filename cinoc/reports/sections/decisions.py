"""Section **décisions** : ce qu'un correcteur a refusé de changer, et pourquoi.

Le CER dit de combien un texte s'est rapproché de la référence. Il ne dit pas
ce que l'appelant achète : **une garantie sur ce qui sort**. Un correcteur
prudent et un correcteur inerte rendent le même texte quand rien ne bouge, et
un correcteur qui gagne en moyenne peut abîmer davantage de lignes qu'un autre
— mesuré le 2026-08-21 : un modèle gagnait *plus* de CER qu'un second et
**abîmait quatre fois plus de lignes**.

Cette section rend le payload ``decisions`` en **lecture seule**. Absente si
aucun correcteur n'en produit : pas de section vide, par construction.
"""

from __future__ import annotations

from cinoc.evaluation.analysis import DecisionsPayload, PipelineDecisions
from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._payload import render_payload_section


def _part(n: int, total: int, lang: str) -> str:
    if not total:
        return "—"
    return localize_decimal(f"{n / total:.1%}", lang)


def _row(row: PipelineDecisions, order: dict[str, int], lang: str) -> str:
    badge = engine_cell(row.pipeline, order.get(row.pipeline, 0))
    review = row.review_required if row.review_required is not None else "—"
    return (
        f'<tr><td class="eng-cell">{badge}</td>'
        f'<td class="disp">{row.n_lines}</td>'
        f'<td class="disp">{row.changed} <span class="muted">'
        f"({_part(row.changed, row.n_lines, lang)})</span></td>"
        f'<td class="disp">{row.refused} <span class="muted">'
        f"({_part(row.refused, row.n_lines, lang)})</span></td>"
        f'<td class="disp">{row.untouched}</td>'
        f'<td class="disp">{review}</td></tr>'
    )


def _reasons(row: PipelineDecisions, lang: str) -> str:
    blocks = []
    for reasons, titre in (
        (row.reasons, localized(lang, "Motifs de refus", "Refusal reasons")),
        (row.review_reasons, localized(lang, "Motifs de relecture", "Review reasons")),
    ):
        if reasons:
            items = "".join(
                f"<li><code>{escape(reason.code)}</code> — {reason.n}</li>"
                for reason in sorted(reasons, key=lambda r: (-r.n, r.code))
            )
            blocks.append(
                f'<p class="muted"><b>{escape(row.pipeline)}</b> · {titre}</p>'
                f"<ul>{items}</ul>"
            )
    return "".join(blocks)


def _samples(row: PipelineDecisions, lang: str) -> str:
    if not row.samples:
        return ""
    titre = localized(lang, "Lignes, avant et après", "Lines, before and after")
    th_line = localized(lang, "Ligne", "Line")
    th_before = localized(lang, "Avant", "Before")
    th_after = localized(lang, "Après", "After")
    th_status = localized(lang, "Statut", "Status")
    th_reason = localized(lang, "Motif", "Reason")
    corps = "".join(
        f"<tr><td><code>{escape(s.page_id)}/{escape(s.line_id)}</code></td>"
        f"<td>{escape(s.source_text)}</td>"
        f"<td>{escape(s.final_text)}</td>"
        f"<td>{escape(s.status)}</td>"
        f"<td>{escape(s.reason_code or '—')}"
        + "".join(
            f"<br><code>{escape(reason.code)}</code> — {escape(reason.detail or '—')}"
            for reason in s.review_reasons
        )
        + "</td></tr>"
        for s in row.samples
    )
    return (
        f'<p class="muted"><b>{escape(row.pipeline)}</b> · {titre}</p>'
        f'<div class="table-scroll"><table class="data">'
        f"<thead><tr><th>{th_line}</th><th>{th_before}</th>"
        f"<th>{th_after}</th><th>{th_status}</th><th>{th_reason}</th></tr></thead>"
        f"<tbody>{corps}</tbody></table></div>"
    )


class DecisionsSection:
    """Ce que le correcteur a changé, refusé de changer, et pourquoi."""

    name = "decisions"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        order = engine_order(p.pipeline for p in result.pipelines)
        title = localized(ctx.lang, "Décisions du correcteur", "Corrector decisions")
        prose = localized(
            ctx.lang,
            '<p class="muted"><b>Changées</b> = lignes que le correcteur a '
            "modifiées. <b>Refusées</b> = lignes où un changement a été "
            "<i>proposé</i> puis écarté par une garde — invisible dans le texte "
            "de sortie, et pourtant la différence entre un correcteur prudent et "
            "un correcteur inerte. <b>Intactes</b> = aucune proposition. Le CER "
            "seul ne distingue pas ces trois cas. <b>À relire</b> = demande de "
            "jugement humain, comptée séparément : le texte retenu reste un "
            "candidat, pas une validation. « — » = information absente de "
            "l'archive.</p>\n",
            '<p class="muted"><b>Changed</b> = lines the corrector modified. '
            "<b>Refused</b> = lines where a change was <i>proposed</i> then "
            "rejected by a guard — invisible in the output text, yet the "
            "difference between a cautious corrector and an inert one. "
            "<b>Untouched</b> = nothing proposed. CER alone tells these three "
            "apart in no way. <b>Review required</b> = a request for human "
            "judgement, counted separately: retained text is a candidate, "
            "not an approval. ‘—’ = information absent from the archive.</p>\n",
        )
        th_pipeline = localized(ctx.lang, "Pipeline", "Pipeline")
        th_lines = localized(ctx.lang, "Lignes", "Lines")
        th_changed = localized(ctx.lang, "Changées", "Changed")
        th_refused = localized(ctx.lang, "Refusées", "Refused")
        th_untouched = localized(ctx.lang, "Intactes", "Untouched")
        th_review = localized(ctx.lang, "À relire", "Review required")

        def block(prefix: str, payload: DecisionsPayload) -> str:
            corps = "".join(_row(r, order, ctx.lang) for r in payload.pipelines)
            details = "".join(
                _reasons(r, ctx.lang) + _samples(r, ctx.lang) for r in payload.pipelines
            )
            return (
                f"{prefix}{prose}"
                f'<div class="table-scroll"><table class="data">\n'
                f"<thead><tr><th>{th_pipeline}</th>"
                f'<th class="num-cell">{th_lines}</th>'
                f'<th class="num-cell">{th_changed}</th>'
                f'<th class="num-cell">{th_refused}</th>'
                f'<th class="num-cell">{th_untouched}</th>'
                f'<th class="num-cell">{th_review}</th></tr></thead>\n'
                f"<tbody>{corps}</tbody>\n</table></div>\n{details}"
            )

        return render_payload_section(
            result,
            ctx,
            payload_type=DecisionsPayload,
            title=title,
            block=block,
        )


__all__ = ["DecisionsSection"]
