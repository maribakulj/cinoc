"""Section structure / mise en page (couche 7) : Region-F1 + CER par région.

Rend, en **lecture seule**, les scores de la vue ``structure`` — produite quand
le corpus porte une vérité-terrain ``LAYOUT`` (segmentation). Absente sinon
(aucun pipeline ne porte ces métriques) : pas de section vide, par construction.
"""

from __future__ import annotations

from cinoc.evaluation.result import PipelineResult, RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import localized
from cinoc.reports.section import Html, SectionContext

#: Métriques de la vue structure (Region-F1 de détection + CER par région).
_METRICS = ("region_detection", "region_cer")


def _value(
    result: RunResult, pipeline: PipelineResult, metric: str
) -> float | None:
    return next(
        (s.value for s in result.principal_aggregate(pipeline) if s.metric == metric),
        None,
    )


def _cell(value: float | None, lang: str) -> str:
    if value is None:
        return '<td class="disp muted">—</td>'
    return f'<td class="disp">{localize_decimal(f"{value:.4f}", lang)}</td>'


class StructureSection:
    """Region-F1 (détection de régions) + CER par région — runs de segmentation."""

    name = "structure"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        rows = [
            p
            for p in result.pipelines
            if any(s.metric in _METRICS for s in result.principal_aggregate(p))
        ]
        if not rows:
            return None
        order = engine_order(p.pipeline for p in result.pipelines)
        title = localized(ctx.lang, "Structure (mise en page)", "Layout structure")
        prose = localized(
            ctx.lang,
            '<p class="muted"><b>Region-F1</b> = qualité de la <b>segmentation</b> '
            "(régions appariées par IoU de boîte ≥ 0,5, coordonnées relatives — "
            "plus haut = mieux). <b>CER région</b> = erreur caractère région par "
            "région, micro-agrégée à la page (plus bas = mieux). N'apparaît que "
            "pour les runs portant une vérité-terrain de mise en page.</p>\n",
            '<p class="muted"><b>Region-F1</b> = <b>segmentation</b> quality '
            "(regions matched by box IoU ≥ 0.5, relative coordinates — higher is "
            "better). <b>Region CER</b> = per-region character error, "
            "page-micro-aggregated (lower is better). Shown only for runs "
            "carrying layout ground truth.</p>\n",
        )
        th_pipeline = localized(ctx.lang, "Pipeline", "Pipeline")
        th_f1 = localized(ctx.lang, "Region-F1 ↑", "Region-F1 ↑")
        th_cer = localized(ctx.lang, "CER région ↓", "Region CER ↓")
        body = "".join(
            f'<tr><td class="eng-cell">'
            f"{engine_cell(p.pipeline, order.get(p.pipeline, 0))}</td>"
            + _cell(_value(result, p, "region_detection"), ctx.lang)
            + _cell(_value(result, p, "region_cer"), ctx.lang)
            + "</tr>"
            for p in rows
        )
        return Html(
            f"<h2>{title}</h2>\n{prose}"
            f'<div class="table-scroll"><table class="data">\n'
            f"<thead><tr><th>{th_pipeline}</th>"
            f'<th class="num-cell">{th_f1}</th>'
            f'<th class="num-cell">{th_cer}</th></tr></thead>\n'
            f"<tbody>{body}</tbody>\n</table></div>\n"
        )


__all__ = ["StructureSection"]
