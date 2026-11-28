"""Section **décisions** : ce qu'un correcteur a changé, refusé, ou déclaré en repli.

Le CER dit de combien un texte s'est rapproché de la référence. Il ne dit pas
ce que l'appelant achète : **une garantie sur ce qui sort**. Un correcteur
prudent et un correcteur inerte rendent le même texte quand rien ne bouge, et
un correcteur qui gagne en moyenne peut abîmer davantage de lignes qu'un autre
— mesuré le 2026-08-21 : un modèle gagnait *plus* de CER qu'un second et
**abîmait quatre fois plus de lignes**.

La **classe de chaque ligne est déclarée** par l'adaptateur (corrigée, à revoir,
abstention, refus technique, repli — disjointes, § 2.1 f) : cette section la
**lit**, jamais ne la recalcule. Les comptes viennent de l'analyse
``decisions`` quand elle a été demandée, sinon de ``PipelineResult.
line_outcomes`` (déclaré par l'adaptateur, porté par l'exécuteur) : le rapport
ne dépend pas d'une analyse facultative pour dire ce qui a été corrigé. Absente
si aucun correcteur n'en déclare : pas de section vide, par construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from cinoc.evaluation.analysis import DecisionsPayload, PipelineDecisions
from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized, view_prefix
from cinoc.reports.section import Html, SectionContext


@dataclass(frozen=True)
class _Row:
    """Les comptes déclarés d'un pipeline, d'où qu'ils viennent."""

    pipeline: str
    n_lines: int | None
    corrected: int | None
    review_required: int | None
    abstained: int | None
    refused: tuple[tuple[str, int], ...]
    fallback: tuple[tuple[str, int], ...]
    review_reasons: tuple[tuple[str, int], ...] = ()
    detail: PipelineDecisions | None = None

    @property
    def declared(self) -> bool:
        """Faux quand l'archive n'a pas déclaré la classe de ses lignes (N3)."""
        return self.n_lines is not None


def _from_payload(row: PipelineDecisions) -> _Row:
    return _Row(
        pipeline=row.pipeline,
        n_lines=row.n_lines,
        corrected=row.corrected,
        review_required=row.review_required,
        abstained=row.abstained,
        refused=tuple((r.code, r.n) for r in row.refused),
        fallback=tuple((r.code, r.n) for r in row.fallback),
        review_reasons=tuple((r.code, r.n) for r in row.review_reasons),
        detail=row,
    )


def _declared_rows(result: RunResult, covered: set[str]) -> list[_Row]:
    """Les pipelines dont l'unité a déclaré des issues de lignes, sans analyse."""
    rows: list[_Row] = []
    seen = set(covered)
    for entry in result.pipelines:
        declared = entry.line_outcomes
        if declared is None or entry.pipeline in seen:
            continue
        seen.add(entry.pipeline)
        refused = tuple(sorted(declared.refused.items()))
        fallback = tuple(sorted(declared.fallback.items()))
        rows.append(
            _Row(
                pipeline=entry.pipeline,
                n_lines=(
                    declared.corrected
                    + declared.review_required
                    + declared.abstained
                    + sum(declared.refused.values())
                    + sum(declared.fallback.values())
                ),
                corrected=declared.corrected,
                review_required=declared.review_required,
                abstained=declared.abstained,
                refused=refused,
                fallback=fallback,
            )
        )
    return rows


def _part(n: int, total: int, lang: str) -> str:
    if not total:
        return "—"
    return localize_decimal(f"{n / total:.1%}", lang)


def _count(n: int | None, total: int | None, lang: str) -> str:
    assert n is not None and total is not None  # une ligne déclarée

    share = _part(n, total, lang)
    return f'<td class="disp">{n} <span class="muted">({share})</span></td>'


def _row_html(row: _Row, order: dict[str, int], lang: str) -> str:
    badge = engine_cell(row.pipeline, order.get(row.pipeline, 0))
    if not row.declared:
        # Une non-mesure, jamais un zéro : aucun nombre dans la ligne (N3).
        texte = localized(
            lang,
            "classes non déclarées par l'archive",
            "line classes not declared by the archive",
        )
        return (
            f'<tr><td class="eng-cell">{badge}</td>'
            f'<td class="muted" colspan="6">{texte}</td></tr>'
        )
    refused = sum(n for _, n in row.refused)
    fallback = sum(n for _, n in row.fallback)
    return (
        f'<tr><td class="eng-cell">{badge}</td>'
        f'<td class="disp">{row.n_lines}</td>'
        + _count(row.corrected, row.n_lines, lang)
        + _count(row.review_required, row.n_lines, lang)
        + _count(row.abstained, row.n_lines, lang)
        + _count(refused, row.n_lines, lang)
        + _count(fallback, row.n_lines, lang)
        + "</tr>"
    )


def _reasons(row: _Row, lang: str) -> str:
    blocks = []
    for reasons, titre in (
        (
            row.refused,
            localized(
                lang,
                "Refus techniques (décisions valides, la source est gardée)",
                "Technical refusals (valid decisions, the source is kept)",
            ),
        ),
        (
            row.fallback,
            localized(
                lang,
                "Replis (incident d'exécution : l'étape est partielle)",
                "Fallbacks (execution incident: the stage is partial)",
            ),
        ),
        (row.review_reasons, localized(lang, "Motifs de relecture", "Review reasons")),
    ):
        if reasons:
            items = "".join(
                f"<li><code>{escape(code)}</code> — {n}</li>"
                for code, n in sorted(reasons, key=lambda r: (-r[1], r[0]))
            )
            blocks.append(
                f'<p class="muted"><b>{escape(row.pipeline)}</b> · {titre}</p>'
                f"<ul>{items}</ul>"
            )
    return "".join(blocks)


def _samples(row: _Row, lang: str) -> str:
    if row.detail is None or not row.detail.samples:
        return ""
    titre = localized(lang, "Lignes, avant et après", "Lines, before and after")
    th_line = localized(lang, "Ligne", "Line")
    th_before = localized(lang, "Avant", "Before")
    th_after = localized(lang, "Après", "After")
    th_class = localized(lang, "Classe déclarée", "Declared class")
    th_reason = localized(lang, "Motif", "Reason")
    corps = "".join(
        f"<tr><td><code>{escape(s.page_id)}/{escape(s.line_id)}</code></td>"
        f"<td>{escape(s.source_text)}</td>"
        f"<td>{escape(s.final_text)}</td>"
        f"<td><code>{escape(s.line_class)}</code></td>"
        f"<td>{escape(s.reason_code or '—')}"
        + "".join(
            f"<br><code>{escape(reason.code)}</code> — {escape(reason.detail or '—')}"
            for reason in s.review_reasons
        )
        + "</td></tr>"
        for s in row.detail.samples
    )
    return (
        f'<p class="muted"><b>{escape(row.pipeline)}</b> · {titre}</p>'
        f'<div class="table-scroll"><table class="data">'
        f"<thead><tr><th>{th_line}</th><th>{th_before}</th>"
        f"<th>{th_after}</th><th>{th_class}</th><th>{th_reason}</th></tr></thead>"
        f"<tbody>{corps}</tbody></table></div>"
    )


class DecisionsSection:
    """Ce que le correcteur a changé, refusé, ou laissé en repli — par classes
    déclarées."""

    name = "decisions"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        order = engine_order(p.pipeline for p in result.pipelines)
        lang = ctx.lang
        title = localized(lang, "Décisions du correcteur", "Corrector decisions")
        prose = localized(
            lang,
            '<p class="muted">Classes <b>déclarées</b> par le correcteur, '
            "disjointes. <b>Corrigées</b> = texte modifié. <b>À relire</b> = "
            "correction gardée, que le correcteur déclare ne pas pouvoir "
            "établir, comptée à part. <b>Abstentions</b> = source proposée "
            "inchangée. <b>Refusées</b> = un garde-fou ou une revue a écarté la "
            "proposition : décision valide, invisible dans le texte de sortie — "
            "c'est ce qui distingue un correcteur prudent d'un correcteur "
            "inerte. <b>Replis</b> = aucune proposition exploitable (délai, "
            "réponse illisible) : un incident d'exécution, qui rend l'étape "
            "partielle. Le CER seul ne distingue pas ces cas.</p>\n",
            '<p class="muted"><b>Declared</b> classes, disjoint. '
            "<b>Corrected</b> = text modified. <b>Review required</b> = "
            "correction kept, that the corrector declares it cannot establish, "
            "counted apart. <b>Abstained</b> = source proposed unchanged. "
            "<b>Refused</b> = a guard or a review rejected the proposal: a valid "
            "decision, invisible in the output text — what tells a cautious "
            "corrector from an inert one. <b>Fallbacks</b> = no usable proposal "
            "(timeout, unreadable answer): an execution incident, which makes "
            "the stage partial. CER alone does not tell these cases apart.</p>\n",
        )
        th_pipeline = localized(lang, "Pipeline", "Pipeline")
        th_lines = localized(lang, "Lignes", "Lines")
        th_corrected = localized(lang, "Corrigées", "Corrected")
        th_review = localized(lang, "À relire", "Review required")
        th_abstained = localized(lang, "Abstentions", "Abstained")
        th_refused = localized(lang, "Refusées", "Refused")
        th_fallback = localized(lang, "Replis", "Fallbacks")

        def block(prefix: str, rows: list[_Row]) -> str:
            corps = "".join(_row_html(r, order, lang) for r in rows)
            details = "".join(_reasons(r, lang) + _samples(r, lang) for r in rows)
            return (
                f"{prefix}{prose}"
                f'<div class="table-scroll"><table class="data">\n'
                f"<thead><tr><th>{th_pipeline}</th>"
                f'<th class="num-cell">{th_lines}</th>'
                f'<th class="num-cell">{th_corrected}</th>'
                f'<th class="num-cell">{th_review}</th>'
                f'<th class="num-cell">{th_abstained}</th>'
                f'<th class="num-cell">{th_refused}</th>'
                f'<th class="num-cell">{th_fallback}</th></tr></thead>\n'
                f"<tbody>{corps}</tbody>\n</table></div>\n{details}"
            )

        multi = len({a.view for a in result.analyses}) > 1
        blocks: list[str] = []
        covered: set[str] = set()
        for analysis in result.analyses:
            payload = analysis.payload
            if isinstance(payload, DecisionsPayload):
                rows = [_from_payload(r) for r in payload.pipelines]
                covered.update(r.pipeline for r in rows)
                blocks.append(
                    block(view_prefix(analysis.view, lang, multi=multi), rows)
                )
        declared = _declared_rows(result, covered)
        if declared:
            blocks.append(block("", declared))
        if not blocks:
            return None
        return Html(f"<h2>{title}</h2>\n" + "".join(blocks))


__all__ = ["DecisionsSection"]
