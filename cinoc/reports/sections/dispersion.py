"""Section dispersion : étendue du CER par moteur, en **bandes SVG** (couche 7).

Visualise ce que ``by_engine`` montre en texte (min · médiane · max par document)
sous forme graphique — la **fiabilité** que l'agrégat masque. Échelle commune
entre moteurs (max global) → comparaison directe. Server-side, déterministe,
zéro JS. Donnée : ``RunResult.documents`` (CER par document, déjà calculé).
"""

from __future__ import annotations

from statistics import fmean, median, quantiles

from cinoc.evaluation.result import RunDocumentResult, RunResult
from cinoc.reports._numbers import fmt_pct
from cinoc.reports.engine_badges import engine_accent, engine_letter, engine_order
from cinoc.reports.html import escape, localized, view_label
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import ordered_unique
from cinoc.reports.svg import box_plot

_METRIC = "cer"


def _per_doc_cer(
    documents: tuple[RunDocumentResult, ...], pipeline: str, view: str
) -> list[float]:
    return [
        score.value
        for doc in documents
        if doc.pipeline == pipeline and doc.view == view
        for score in doc.scores
        if score.metric == _METRIC and score.value is not None
    ]


def _pct(v: float, lang: str) -> str:
    return fmt_pct(v, lang)


class DispersionSection:
    """Boîtes à moustaches du CER par moteur (Q1·médiane·µ·Q3, échelle commune)."""

    name = "dispersion"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not result.viewed_documents:
            return None
        views = ordered_unique(d.view for d in result.viewed_documents)
        view = views[0]
        multi = len(views) > 1
        order = engine_order(p.pipeline for p in result.pipelines) or engine_order(
            d.pipeline for d in result.viewed_documents
        )
        # (pipeline, valeurs) dans l'ordre canonique des badges.
        series: list[tuple[str, list[float]]] = []
        for pipeline in sorted(order, key=lambda p: order[p]):
            vals = _per_doc_cer(result.viewed_documents, pipeline, view)
            if vals:
                series.append((pipeline, vals))
        if not series:
            return None
        scale_max = max(max(v) for _, v in series)
        lang = ctx.lang
        rows = "".join(self._row(p, v, order[p], scale_max, lang) for p, v in series)
        vlbl = escape(view_label(view, lang))
        title = localized(
            lang,
            f"Dispersion du CER{f' (vue : {vlbl})' if multi else ''}",
            f"CER dispersion{f' (view: {vlbl})' if multi else ''}",
        )
        intro = localized(
            lang,
            '<p class="muted">Boîte à moustaches par moteur : moustaches min→max, '
            "boîte interquartile Q1→Q3, trait médian, tick moyenne. Échelle "
            "commune entre moteurs.</p>\n",
            '<p class="muted">Box plot per engine: whiskers min→max, interquartile '
            "box Q1→Q3, median line, mean tick. Common scale across engines.</p>\n",
        )
        return Html(
            f"<h2>{title}</h2>\n"
            f"{intro}"
            f'<div class="disp-grid">{rows}</div>\n'
        )

    @staticmethod
    def _row(
        pipeline: str, vals: list[float], index: int, scale_max: float, lang: str
    ) -> str:
        lo, hi = min(vals), max(vals)
        med, mean = median(vals), fmean(vals)
        # Quartiles : ``quantiles`` exige ≥2 points ; sinon boîte plate sur la valeur.
        if len(vals) >= 2:
            q1, _q2, q3 = quantiles(vals, n=4)
        else:
            q1 = q3 = med
        accent = engine_accent(index)
        plot = box_plot(lo, q1, med, q3, hi, mean, scale_max, accent=accent)
        med_label = localized(lang, "méd", "med")
        return (
            '<div class="disp-row">'
            f'<div class="disp-head"><span class="eng-badge" style="--badge:{accent}">'
            f"{engine_letter(index)}</span>"
            f'<span class="disp-name">{escape(pipeline)}</span></div>'
            f"{plot}"
            '<div class="disp-labels mono">'
            f"min {_pct(lo, lang)} · Q1 {_pct(q1, lang)} · "
            f"{med_label} {_pct(med, lang)} · "
            f"µ {_pct(mean, lang)} · Q3 {_pct(q3, lang)} · max {_pct(hi, lang)}"
            "</div></div>"
        )


__all__ = ["DispersionSection"]
