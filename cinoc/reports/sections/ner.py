"""Section entités nommées : précision/rappel/F1 par pipeline (couche 7).

Lecture seule du payload ``ner`` : F1 global + détail par catégorie, échantillon
des entités manquées et hallucinées. La prose documente la limite — la métrique
mesure **conjointement** la qualité de l'OCR et celle de l'extracteur NER.
"""

from __future__ import annotations

from collections.abc import Mapping

from cinoc.evaluation.analysis import EntityMention, NerPayload, PipelineNer
from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._payload import render_payload_section


def _mentions(mentions: tuple[EntityMention, ...]) -> str:
    if not mentions:
        return "—"
    labels = ", ".join(
        f"{escape(m.text)} ({escape(m.label)})" if m.text else escape(m.label)
        for m in mentions
    )
    return f'<span class="muted">{labels}</span>'


def _share(value: float | None, lang: str) -> str:
    """Pourcentage localisé ; indéfini (dénominateur nul : aucune entité
    prédite, ou catégorie seulement prédite) → « indéfini », jamais un 0 (M3)."""
    if value is None:
        return localized(lang, "indéfini", "undefined")
    return localize_decimal(f"{value:.1%}", lang)


def _global_row(row: PipelineNer, order: Mapping[str, int], lang: str) -> str:
    badge = engine_cell(row.pipeline, order.get(row.pipeline, 0))
    return (
        f'<tr><td class="eng-cell">{badge}</td>'
        f'<td class="disp">{row.n_reference}</td>'
        f'<td class="disp">{_share(row.precision, lang)}</td>'
        f'<td class="disp">{localize_decimal(f"{row.recall:.1%}", lang)}</td>'
        f'<td class="disp">{localize_decimal(f"{row.f1:.1%}", lang)}</td>'
        f'<td class="disp">{row.true_positives}/{row.false_positives}'
        f"/{row.false_negatives}</td></tr>"
    )


def _category_rows(row: PipelineNer, order: Mapping[str, int], lang: str) -> str:
    rows: list[str] = []
    for cat in row.per_category:
        badge = engine_cell(row.pipeline, order.get(row.pipeline, 0))
        rows.append(
            f'<tr><td class="eng-cell">{badge}</td>'
            f'<td class="eng-cell">{escape(cat.label)}</td>'
            f'<td class="disp">{cat.support}</td>'
            f'<td class="disp">{_share(cat.precision, lang)}</td>'
            f'<td class="disp">{_share(cat.recall, lang)}</td>'
            f'<td class="disp">{_share(cat.f1, lang)}</td></tr>'
        )
    return "".join(rows)


def _samples_rows(row: PipelineNer, order: Mapping[str, int]) -> str:
    badge = engine_cell(row.pipeline, order.get(row.pipeline, 0))
    return (
        f'<tr><td class="eng-cell">{badge}</td>'
        f"<td>{_mentions(row.missed)}</td>"
        f"<td>{_mentions(row.hallucinated)}</td></tr>"
    )


def _block(
    view: str, payload: NerPayload, order: Mapping[str, int], lang: str
) -> str:
    global_rows = "".join(
        _global_row(row, order, lang) for row in payload.pipelines
    )
    category_rows = "".join(
        _category_rows(row, order, lang) for row in payload.pipelines
    )
    samples_rows = "".join(_samples_rows(row, order) for row in payload.pipelines)
    iou = localize_decimal(f"{payload.iou_threshold:.2f}", lang)
    th_pipeline = localized(lang, "Pipeline", "Pipeline")
    th_precision = localized(lang, "précision", "precision")
    th_recall = localized(lang, "rappel", "recall")
    global_head = localized(
        lang,
        f"{view}entités nommées (IoU ≥ {iou})",
        f"{view}named entities (IoU ≥ {iou})",
    )
    global_prose = localized(
        lang,
        '<p class="muted">Part des entités de la GT retrouvées dans la sortie, '
        "spans alignés en coordonnées GT (un décalage d'OCR amont ne pénalise "
        "pas une entité bien transcrite). La mesure est <strong>conjointe</strong> "
        "— elle reflète l'OCR <em>et</em> l'extracteur NER. TP/FP/FN = vrais "
        "positifs / hallucinés / manqués.</p>\n",
        '<p class="muted">Share of GT entities found in the output, '
        "spans aligned in GT coordinates (an upstream OCR shift does not penalize "
        "a well-transcribed entity). The measure is <strong>joint</strong> "
        "— it reflects the OCR <em>and</em> the NER extractor. TP/FP/FN = true "
        "positives / hallucinated / missed.</p>\n",
    )
    th_gt_entities = localized(lang, "entités GT", "GT entities")
    blocks = (
        f"<h3>{global_head}</h3>\n"
        f"{global_prose}"
        f'<table class="data">\n<thead><tr><th>{th_pipeline}</th>'
        f'<th class="num-cell">{th_gt_entities}</th>'
        f'<th class="num-cell">{th_precision}</th>'
        f'<th class="num-cell">{th_recall}</th><th class="num-cell">F1</th>'
        '<th class="num-cell">TP/FP/FN</th></tr></thead>\n'
        f"<tbody>{global_rows}</tbody>\n</table>\n"
    )
    if category_rows:
        cat_head = localized(
            lang,
            f"{view}F1 par catégorie",
            f"{view}F1 per category",
        )
        th_category = localized(lang, "catégorie", "category")
        th_support = localized(lang, "support", "support")
        blocks += (
            f"<h3>{cat_head}</h3>\n"
            f'<table class="data">\n<thead><tr><th>{th_pipeline}</th>'
            f"<th>{th_category}</th>"
            f'<th class="num-cell">{th_support}</th>'
            f'<th class="num-cell">{th_precision}</th>'
            f'<th class="num-cell">{th_recall}</th><th class="num-cell">F1</th>'
            "</tr></thead>\n"
            f"<tbody>{category_rows}</tbody>\n</table>\n"
        )
    samples_head = localized(
        lang,
        f"{view}entités manquées &amp; hallucinées (échantillon)",
        f"{view}missed &amp; hallucinated entities (sample)",
    )
    th_missed = localized(lang, "manquées", "missed")
    th_hallucinated = localized(lang, "hallucinées", "hallucinated")
    blocks += (
        f"<h3>{samples_head}</h3>\n"
        f'<table class="data">\n<thead><tr><th>{th_pipeline}</th>'
        f"<th>{th_missed}</th>"
        f"<th>{th_hallucinated}</th></tr></thead>\n"
        f"<tbody>{samples_rows}</tbody>\n</table>\n"
    )
    return blocks


class NerSection:
    """Précision sur entités nommées, par pipeline (lecture seule)."""

    name = "ner"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        order = engine_order(p.pipeline for p in result.pipelines)
        return render_payload_section(
            result,
            ctx,
            payload_type=NerPayload,
            title=localized(ctx.lang, "Entités nommées", "Named entities"),
            block=lambda view, payload: _block(view, payload, order, ctx.lang),
        )


__all__ = ["NerSection"]
