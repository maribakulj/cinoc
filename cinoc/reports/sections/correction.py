"""Section bilan de correction : que vaut l'étage LLM ? (couche 7)

Rend le payload ``correction`` en **lecture seule** : triplet de
non-régression, pcis, ampleur d'intervention, absorption, sur-normalisation,
pires régressions. Tous les seuils affichés viennent du payload (auditable).
"""

from __future__ import annotations

from cinoc.evaluation.analysis import CorrectionPayload, PipelineCorrection
from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._payload import render_payload_section


def _pct(value: float | None, lang: str) -> str:
    return "—" if value is None else localize_decimal(f"{value:.1%}", lang)


def _num(value: float | None, lang: str, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    raw = f"{value:+.4f}" if signed else f"{value:.4f}"
    return localize_decimal(raw, lang)


def _row(label: str, *cells: str) -> str:
    body = "".join(f'<td class="disp">{cell}</td>' for cell in cells)
    return f'<tr><td class="eng-cell">{escape(label)}</td>{body}</tr>'


def _pipeline_block(
    row: PipelineCorrection, payload: CorrectionPayload, lang: str
) -> str:
    missing = (
        localized(
            lang,
            f" · R-1.8 : {row.n_missing_raw} brut(s) / {row.n_missing_corrected} "
            f"corrigé(s) matérialisés vides",
            f" · R-1.8: {row.n_missing_raw} raw / {row.n_missing_corrected} "
            f"corrected materialized empty",
        )
        if row.n_missing_raw or row.n_missing_corrected
        else ""
    )
    cata = localize_decimal(f"{payload.catastrophic_threshold:g}", lang)
    over = localize_decimal(f"{payload.overedit_threshold:g}", lang)
    ins = localize_decimal(f"{payload.insertion_threshold:g}", lang)
    rows = [
        _row(
            localized(
                lang,
                "Triplet (amélioration / régression / égalité)",
                "Triplet (improvement / regression / no change)",
            ),
            _pct(row.improvement_rate, lang),
            _pct(row.regression_rate, lang),
            _pct(row.no_change_rate, lang),
        ),
        _row(
            localized(
                lang,
                f"pref · catastrophiques (Δ > {cata})",
                f"pref · catastrophic (Δ > {cata})",
            ),
            _num(row.pref_score, lang, signed=True),
            f"{row.n_catastrophic} ({_pct(row.catastrophic_rate, lang)})",
            "",
        ),
        _row(
            localized(
                lang,
                "pcis (macro · médiane · |pcis| > 1)",
                "pcis (macro · median · |pcis| > 1)",
            ),
            _num(row.pcis_macro, lang, signed=True),
            _num(row.pcis_median, lang, signed=True),
            str(row.n_pcis_extreme),
        ),
        _row(
            localized(
                lang,
                f"Intervention (CCR · ratio · sur-édités > "
                f"{over})",
                f"Intervention (CCR · ratio · over-edited > "
                f"{over})",
            ),
            _num(row.ccr, lang),
            _num(row.change_ratio, lang),
            str(row.n_overedited),
        ),
        _row(
            localized(
                lang,
                f"Insertions (part · lourds > {ins} "
                f"· longueur)",
                f"Insertions (share · heavy > {ins} "
                f"· length)",
            ),
            _num(row.char_ins_ratio, lang),
            str(row.n_heavy_insertion),
            _num(row.length_ratio, lang),
        ),
        _row(
            localized(
                lang,
                "Absorption (corrigées · introduites · net)",
                "Absorption (corrected · introduced · net)",
            ),
            str(row.corrected),
            str(row.introduced),
            f"{row.net_improvement:+d}",
        ),
        _row(
            localized(
                lang,
                "Sur-normalisation (mots OCR-justes dégradés)",
                "Over-normalization (OCR-correct words degraded)",
            ),
            f"{row.n_over_normalized}/{row.n_correct_ocr_words}",
            _num(row.over_normalization, lang),
            "",
        ),
        _row(
            localized(
                lang,
                f"Éditions consécutives (médiane · max · part > "
                f"{payload.edit_run_threshold})",
                f"Consecutive edits (median · max · share > "
                f"{payload.edit_run_threshold})",
            ),
            _num(row.edit_run_median, lang),
            str(row.edit_run_max),
            _num(row.edit_run_share, lang),
        ),
    ]
    documents_label = localized(
        lang,
        f"{row.n_documents} documents",
        f"{row.n_documents} documents",
    )
    parts = [
        f"<h4>{escape(row.pipeline)} — {documents_label}{missing}</h4>\n"
        '<table class="data">\n<tbody>' + "".join(rows) + "</tbody>\n</table>\n"
    ]
    if row.worst_regressions:
        regression_rows = "".join(
            f'<tr><td class="eng-cell">{escape(sample.document_id)}</td>'
            f'<td class="disp">'
            f'{localize_decimal(f"{sample.cmer_raw:.4f}", lang)}</td>'
            f'<td class="disp">'
            f'{localize_decimal(f"{sample.cmer_corrected:.4f}", lang)}</td>'
            f'<td class="disp">'
            f'{localize_decimal(f"{sample.delta:+.4f}", lang)}</td></tr>'
            for sample in row.worst_regressions
        )
        worst_summary = localized(
            lang,
            f"Pires régressions ({len(row.worst_regressions)})",
            f"Worst regressions ({len(row.worst_regressions)})",
        )
        th_document = localized(lang, "document", "document")
        th_cmer_raw = localized(lang, "cmer brut", "cmer raw")
        th_cmer_corrected = localized(lang, "cmer corrigé", "cmer corrected")
        parts.append(
            f'<details><summary class="muted">{worst_summary}</summary>'
            f'<table class="data">\n<thead><tr><th>{th_document}</th>'
            f'<th class="num-cell">{th_cmer_raw}</th>'
            f'<th class="num-cell">{th_cmer_corrected}</th>'
            '<th class="num-cell">Δ</th></tr></thead>\n'
            f"<tbody>{regression_rows}</tbody>\n</table></details>\n"
        )
    if row.over_normalized_samples:
        # #16 : flux mot OCR-juste → forme du correcteur (« ∅ » = supprimé).
        flows = "".join(
            f'<div class="wf-row">'
            f'<span class="wf-word wf-src">{escape(s.reference)}</span>'
            f'<span class="wf-arrow">→</span>'
            f'<span class="wf-word">{escape(s.corrected)}</span>'
            f'<span class="wf-meta">{escape(s.document_id)}</span></div>'
            for s in row.over_normalized_samples
        )
        over_summary = localized(
            lang,
            f"Mots sur-normalisés ({len(row.over_normalized_samples)} exemples "
            f"— mot OCR-juste → forme du correcteur)",
            f"Over-normalized words ({len(row.over_normalized_samples)} examples "
            f"— OCR-correct word → corrector's form)",
        )
        parts.append(
            f'<details><summary class="muted">{over_summary}</summary>\n'
            f'<div class="wflow">{flows}</div></details>\n'
        )
    return "".join(parts)


def _block(view: str, payload: CorrectionPayload, lang: str) -> str:
    head = localized(
        lang,
        f"{view}bilan de correction",
        f"{view}correction balance",
    )
    prose = localized(
        lang,
        '<p class="muted">Pipelines 2 étages (OCR → correcteur) : le triplet '
        "compte les documents améliorés/dégradés (jamais le pref seul) ; CCR "
        "mesure combien le correcteur a touché, indépendamment de la justesse "
        "(à qualité égale, un CCR plus faible = intervention plus parcimonieuse) ; "
        "l'absorption "
        "compte les mots corrigés vs introduits ; les longues séquences "
        "d'éditions signalent une réécriture de passage. Étage absent = "
        "matérialisé vide (erreur maximale), jamais exclu en silence.</p>\n",
        '<p class="muted">2-stage pipelines (OCR → corrector): the triplet '
        "counts improved/degraded documents (never pref alone); CCR "
        "measures how much the corrector touched, regardless of correctness "
        "(at equal quality, a lower CCR = more parsimonious intervention); "
        "absorption "
        "counts corrected vs introduced words; long edit runs "
        "signal a passage rewrite. Missing stage = "
        "materialized empty (maximal error), never silently excluded.</p>\n",
    )
    return (
        f"<h3>{head}</h3>\n"
        + prose
        + "".join(_pipeline_block(row, payload, lang) for row in payload.pipelines)
    )


class CorrectionSection:
    """Bilan de l'étage de correction, par pipeline 2 étages."""

    name = "correction"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        return render_payload_section(
            result,
            ctx,
            payload_type=CorrectionPayload,
            title=localized(ctx.lang, "Bilan de correction", "Correction balance"),
            block=lambda view, payload: _block(view, payload, ctx.lang),
        )


__all__ = ["CorrectionSection"]
