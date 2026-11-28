"""Section diagnostic : confusions, pires lignes, documents difficiles (couche 7).

Rend les payloads ``diagnostics`` de ``RunResult.analyses`` en **lecture
seule** : « voir où ça casse », texte à l'appui. Les extraits sont verbatim du
``RunResult`` (chargés et normalisés au scoring) — aucun recalcul au rendu. Les
confusions sont mises en **flux de glyphes** (#8) : le glyphe attendu → produit,
prominents, barre de fréquence — « voir les symboles » et leur direction.
"""

from __future__ import annotations

from cinoc.evaluation.analysis import (
    CharConfusion,
    DiagnosticsPayload,
    PipelineConfusions,
    WorstLine,
)
from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized, view_prefix
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._alignment_note import alignment_note
from cinoc.reports.text_diff import char_diff

#: Libellés bilingues du **flux de confusion** (#8) ; les pires lignes le sont
#: aussi (D-286). Le tableau des documents difficiles, antérieur à la consigne
#: FR/EN des graphiques, reste FR (i18n rapport = jalon).
_CONFUSION_TEXT: dict[str, dict[str, str]] = {
    "fr": {
        "title": "Confusions de caractères récurrentes (attendu → produit)",
        "intro": (
            "Le glyphe attendu (vérité-terrain) → le glyphe produit par le "
            "moteur ; la barre indique la fréquence. La <strong>direction</strong> "
            "compte : « ſ → f » (long s lu f) n'est pas « f → ſ »."
        ),
        "decomposes": (
            " Ce sont les substitutions que compte le CER, ni plus ni moins."
        ),
    },
    "en": {
        "title": "Recurring character confusions (expected → produced)",
        "intro": (
            "The expected glyph (ground truth) → the glyph the engine produced; "
            "the bar shows frequency. <strong>Direction</strong> matters: "
            "“ſ → f” (long s read as f) is not “f → ſ”."
        ),
        "decomposes": " These are exactly the substitutions the CER counts.",
    },
}


def _confusion_chip(pair: CharConfusion, max_count: int) -> str:
    """Une paire de confusion : glyphes attendu → produit + barre de fréquence."""
    width = round(pair.count / max_count * 48)
    return (
        '<div class="cf-pair">'
        f'<span class="cf-glyph">{escape(pair.expected)}</span>'
        '<span class="cf-arrow">→</span>'
        f'<span class="cf-glyph">{escape(pair.observed)}</span>'
        f'<span class="cf-bar" style="width:{width}px"></span>'
        f'<span class="cf-count">{pair.count}</span></div>'
    )


def _is_truncated(block: PipelineConfusions) -> bool:
    """La liste est tronquée : moins de paires montrées que de paires distinctes."""
    return block.n_pairs is not None and len(block.pairs) < block.n_pairs


def _truncation_note(block: PipelineConfusions, lang: str) -> str:
    """« les k plus fréquentes sur N » : une liste tronquée ne se présente pas
    comme la décomposition des comptes (N7)."""
    if not _is_truncated(block):
        return ""
    k, n, s = len(block.pairs), block.n_pairs, block.n_substitutions
    text = localized(
        lang,
        f"Liste tronquée : les {k} plus fréquentes sur {n} : "
        f"{k} paires sur {n} paires distinctes ({s} substitutions).",
        f"Truncated list: the {k} most frequent of {n}: "
        f"{k} of {n} distinct pairs ({s} substitutions).",
    )
    return f'<p class="muted cf-truncated">{text}</p>'


def _confusion_flow(
    payload: DiagnosticsPayload, lang: str, order: dict[str, int]
) -> str:
    """Flux de confusion (#8) : par moteur, glyphes attendu → produit + fréquence.

    Les glyphes sont **prominents** (le symbole *est* la donnée — on juge à l'œil) ;
    la barre est proportionnelle au compte (pairs déjà triées -count). Verbatim,
    échappés (anti-XSS) ; le slot bordé rend une espace confondue **visible**."""
    groups: list[str] = []
    for block in payload.confusions:
        if not block.pairs:
            continue
        max_count = block.pairs[0].count  # pairs triées -count → pairs[0] = max
        chips = "".join(_confusion_chip(pair, max_count) for pair in block.pairs)
        badge = engine_cell(block.pipeline, order.get(block.pipeline, 0))
        groups.append(
            f'<div class="cf-engine"><span class="cf-eng-name">{badge}</span>'
            f"{_truncation_note(block, lang)}"
            f'<div class="cf-grid">{chips}</div></div>'
        )
    if not groups:
        return ""
    text = _CONFUSION_TEXT.get(lang, _CONFUSION_TEXT["fr"])
    # Ces confusions ne sont les substitutions du CER que si l'alignement qui les
    # nomme égale les comptes canoniques (``matches_canonical_counts``, D8) **et**
    # que la liste est complète : une liste tronquée ne décompose rien (N7), pas
    # plus qu'une liste dont on ne sait pas si elle l'est.
    complete = all(
        block.n_pairs is not None and not _is_truncated(block)
        for block in payload.confusions
        if block.pairs
    )
    decomposes = (
        text["decomposes"] if payload.matches_canonical_counts and complete else ""
    )
    return (
        f"<h4>{text['title']}</h4>\n"
        f'<p class="muted">{text["intro"]}{decomposes}</p>\n'
        + alignment_note(
            payload.alignment_path,
            lang,
            concordant=payload.matches_canonical_counts,
        )
        + "".join(groups)
    )


def _worst_lines_row(line: WorstLine, lang: str) -> str:
    # Drill-in : GT vs hypothèse surlignées caractère à caractère (écarts visibles).
    ref_html, hyp_html = char_diff(line.reference, line.hypothesis)
    return (
        f'<tr><td class="eng-cell">{escape(line.pipeline)}</td>'
        f'<td class="eng-cell">{escape(line.document_id)}</td>'
        f'<td class="disp">{line.line_index}</td>'
        f'<td class="disp">{localize_decimal(f"{line.cer:.4f}", lang)}</td>'
        f'<td class="diff">{ref_html}</td>'
        f'<td class="diff">{hyp_html}</td></tr>'
    )


def _worst_lines_table(payload: DiagnosticsPayload, lang: str) -> str:
    if not payload.worst_lines:
        return ""
    rows = "".join(_worst_lines_row(line, lang) for line in payload.worst_lines)
    head = localized(
        lang,
        "<h4>Pires lignes du corpus — diff GT ↔ hypothèse</h4>\n"
        '<p class="muted">Lignes appariées par alignement des lignes, comme la '
        "distribution par ligne : une ligne ajoutée ne décale pas les suivantes, "
        "une ligne perdue est notée face à une sortie vide. Surlignage : "
        '<del class="d-del">supprimé</del> (présent en GT) · '
        '<ins class="d-ins">inséré</ins> (produit par le moteur).</p>\n',
        "<h4>Worst lines of the corpus — GT ↔ hypothesis diff</h4>\n"
        '<p class="muted">Lines paired by aligning the lines, as in the per-line '
        "distribution: an added line does not shift the following ones, a lost "
        "line is scored against an empty output. Highlighting: "
        '<del class="d-del">deleted</del> (present in the GT) · '
        '<ins class="d-ins">inserted</ins> (produced by the engine).</p>\n',
    )
    columns = localized(
        lang,
        '<th class="num-cell">ligne</th><th class="num-cell">CER</th>'
        "<th>référence (GT)</th><th>hypothèse</th>",
        '<th class="num-cell">line</th><th class="num-cell">CER</th>'
        "<th>reference (GT)</th><th>hypothesis</th>",
    )
    return (
        head
        + '<table class="data">\n<thead><tr><th>Pipeline</th><th>Document</th>'
        + columns
        + "</tr></thead>\n"
        f"<tbody>{rows}</tbody>\n</table>\n"
    )


def _hardest_table(payload: DiagnosticsPayload, lang: str) -> str:
    if not payload.hardest_documents:
        return ""
    rows = "".join(
        f'<tr><td class="eng-cell">{escape(doc.document_id)}</td>'
        f'<td class="disp">{localize_decimal(f"{doc.mean_cer:.4f}", lang)}</td>'
        f'<td class="disp">{doc.n_pipelines}</td></tr>'
        for doc in payload.hardest_documents
    )
    return (
        "<h4>Documents les plus difficiles</h4>\n"
        '<table class="data">\n<thead><tr><th>Document</th>'
        f'<th class="num-cell">{escape(payload.metric)} moyen</th>'
        '<th class="num-cell">pipelines scorés</th></tr></thead>\n'
        f"<tbody>{rows}</tbody>\n</table>\n"
    )


class DiagnosticsSection:
    """Diagnostic d'erreurs : confusions, pires lignes, documents difficiles."""

    name = "diagnostics"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        order = engine_order(p.pipeline for p in result.pipelines)
        multi = len({a.view for a in result.analyses}) > 1
        blocks: list[str] = []
        for analysis in result.analyses:
            payload = analysis.payload
            if not isinstance(payload, DiagnosticsPayload):
                continue
            inner = (
                _confusion_flow(payload, ctx.lang, order)
                + _worst_lines_table(payload, ctx.lang)
                + _hardest_table(payload, ctx.lang)
            )
            if inner:
                blocks.append(
                    f"<h3>{view_prefix(analysis.view, ctx.lang, multi=multi)}"
                    "où ça casse</h3>\n" + inner
                )
        if not blocks:
            return None
        return Html("<h2>Diagnostic d'erreurs</h2>\n" + "".join(blocks))


__all__ = ["DiagnosticsSection"]
