"""Section significativité inter-moteurs : tests, correction, post-hoc, IC.

Pour chaque ``vue:métrique`` de ``RunResult.cross_engine`` : le **test**
apparié (Wilcoxon signé-rangs à 2 pipelines, Friedman au-delà), sa p brute,
sa p **corrigée de Holm** sur les tests du run, et un **verdict** factuel sur
la p corrigée — ou le **motif** pour lequel le test n'a pas été calculé. Le
verdict est une **fonction auditable** du payload ``inference`` — une
étiquette, pas de la prose (narratif supprimé, ``CLAUDE.md`` §6). Une ligne
sans payload (résultat antérieur au schéma 5) garde sa p brute et le dit
« non corrigé ».

Sous le tableau, la section **lit** (sans recalculer) les payloads
``inference`` : rangs moyens, post-hoc de Nemenyi s'il a eu lieu (paires
significatives, barres CD qui se chevauchent), IC bootstrap en mode détaillé
— celui de l'agrégat **micro** du tableau, à côté de ce même agrégat.
Puis les payloads ``inter_engine`` : complémentarité oracle (borne
**supérieure** bag-of-words, documentée comme telle — anti-surinterprétation)
et divergence Jensen-Shannon des profils d'erreurs.
"""

from __future__ import annotations

from collections.abc import Mapping

from cinoc.evaluation.analysis import (
    InferencePayload,
    InterEngineComplementarity,
    InterEngineDivergence,
    InterEnginePayload,
)
from cinoc.evaluation.result import MetricScore, RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized, view_label, view_prefix
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._inference_text import (
    is_significant,
    omnibus_label,
    p_text,
    posthoc_text,
    reason_text,
)


def _format_p(value: float | None, lang: str) -> str:
    return "—" if value is None else p_text(value, lang)


def _split_key(key: str) -> tuple[str, str]:
    """``"text:cer:significance_p"`` → ``("text", "cer")`` ; sinon (clé, "")."""
    parts = key.split(":")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return key, ""


def _payloads(result: RunResult) -> dict[tuple[str, str], InferencePayload]:
    return {
        (analysis.view, analysis.payload.metric): analysis.payload
        for analysis in result.analyses
        if isinstance(analysis.payload, InferencePayload)
    }


def _row(
    score: MetricScore, payload: InferencePayload | None, lang: str
) -> tuple[str, str, str, str]:
    """(test, p brute, p Holm, verdict + classe CSS) d'une ligne du tableau."""
    if payload is None:
        verdict = (
            localized(lang, "non corrigé", "uncorrected")
            if score.value is not None
            else "—"
        )
        cell = f'<td class="verdict">{verdict}</td>'
        return "—", _format_p(score.value, lang), "—", cell
    if payload.test is None:
        label = (
            f'{omnibus_label(payload, lang)} <span class="muted">'
            f"({escape(reason_text(payload, lang))})</span>"
        )
        return label, "—", "—", '<td class="verdict">—</td>'
    if is_significant(payload):
        verdict = '<td class="verdict sig">' + localized(
            lang, "significatif", "significant"
        ) + "</td>"
    else:
        verdict = '<td class="verdict">' + localized(
            lang, "non sig.", "not sig."
        ) + "</td>"
    return (
        escape(omnibus_label(payload, lang)),
        _format_p(payload.p_value, lang),
        _format_p(payload.p_holm, lang),
        verdict,
    )


def _inference_block(
    view: str, payload: InferencePayload, order: Mapping[str, int], lang: str
) -> str:
    """Rendu d'un payload ``inference`` : rangs, post-hoc, IC (mode détaillé)."""
    rows: list[str] = []
    intervals = {item.pipeline: item for item in payload.intervals}
    for rank in payload.mean_ranks:
        interval = intervals.get(rank.pipeline)
        cells = ""
        if intervals:
            ic = (
                localize_decimal(
                    f"[{interval.lower:.4f} ; {interval.upper:.4f}]", lang
                )
                if interval is not None
                else "—"
            )
            point = (
                localize_decimal(f"{interval.value:.4f}", lang)
                if interval is not None
                else "—"
            )
            cells = f'<td class="disp">{point}</td><td class="disp">{ic}</td>'
        badge = engine_cell(rank.pipeline, order.get(rank.pipeline, 0))
        rows.append(
            f'<tr><td class="eng-cell">{badge}</td>'
            f'<td class="disp">{localize_decimal(f"{rank.mean_rank:.3f}", lang)}</td>'
            f"{cells}</tr>"
        )
    posthoc = posthoc_text(payload, lang) or escape(reason_text(payload, lang))
    head = localized(
        lang,
        f"<h3>{view}{escape(payload.metric)} — rangs "
        f"{'&amp; IC ' if intervals else ''}(n={payload.n_documents})</h3>\n",
        f"<h3>{view}{escape(payload.metric)} — ranks "
        f"{'&amp; CI ' if intervals else ''}(n={payload.n_documents})</h3>\n",
    )
    th_pipeline = localized(lang, "Pipeline", "Pipeline")
    th_mean_rank = localized(lang, "rang moyen", "mean rank")
    th_ic = ""
    if intervals:
        th_point = localized(lang, "agrégat (micro)", "aggregate (micro)")
        th_ci = localized(lang, "IC 95 % (bootstrap)", "95% CI (bootstrap)")
        th_ic = (
            f'<th class="num-cell">{th_point}</th>'
            f'<th class="num-cell">{th_ci}</th>'
        )
    return (
        head
        + f'<p class="muted">{posthoc}</p>\n'
        + '<table class="data">\n'
        f"<thead><tr><th>{th_pipeline}</th>"
        f'<th class="num-cell">{th_mean_rank}</th>{th_ic}</tr></thead>\n'
        f"<tbody>{''.join(rows)}</tbody>\n</table>\n"
    )


def _complementarity_block(
    view: str, comp: InterEngineComplementarity, order: Mapping[str, int], lang: str
) -> str:
    """Rendu du bloc complémentarité : rappel par moteur seul vs oracle."""
    rows: list[str] = []
    for item in comp.per_engine_recall:
        badge = engine_cell(item.pipeline, order.get(item.pipeline, 0))
        best = localized(
            lang,
            " (meilleur seul)" if item.pipeline == comp.best_engine else "",
            " (best single)" if item.pipeline == comp.best_engine else "",
        )
        rows.append(
            f'<tr><td class="eng-cell">{badge}{best}</td>'
            f'<td class="disp">{localize_decimal(f"{item.recall:.1%}", lang)}</td></tr>'
        )
    oracle_recall = localize_decimal(f"{comp.oracle_recall:.1%}", lang)
    rows.append(
        localized(
            lang,
            f'<tr><td class="eng-cell">oracle (union des '
            f"{len(comp.per_engine_recall)} moteurs)</td>"
            f'<td class="disp">{oracle_recall}</td></tr>',
            f'<tr><td class="eng-cell">oracle (union of '
            f"{len(comp.per_engine_recall)} engines)</td>"
            f'<td class="disp">{oracle_recall}</td></tr>',
        )
    )
    gap_documents = [d for d in comp.per_document if d.absolute_gap > 0]
    documents = ""
    if gap_documents:
        document_rows = "".join(
            f'<tr><td class="eng-cell">{escape(d.document_id)}</td>'
            f'<td class="disp">{localize_decimal(f"{d.oracle_recall:.1%}", lang)}</td>'
            f'<td class="disp">'
            f'{localize_decimal(f"{d.best_single_recall:.1%}", lang)}</td>'
            f'<td class="disp">{localize_decimal(f"{d.absolute_gap:.1%}", lang)}</td>'
            "</tr>"
            for d in gap_documents
        )
        doc_prose = localized(
            lang,
            '<p class="muted">Documents au plus fort écart oracle − meilleur '
            "(échantillon borné) :</p>\n",
            '<p class="muted">Documents with the largest oracle − best gap '
            "(bounded sample):</p>\n",
        )
        th_document = localized(lang, "Document", "Document")
        th_oracle = localized(lang, "oracle", "oracle")
        th_best_single = localized(lang, "meilleur seul", "best single")
        th_gap = localized(lang, "écart", "gap")
        documents = (
            doc_prose
            + '<table class="data">\n<thead><tr><th>'
            f"{th_document}</th>"
            f'<th class="num-cell">{th_oracle}</th>'
            f'<th class="num-cell">{th_best_single}</th>'
            f'<th class="num-cell">{th_gap}</th></tr></thead>\n'
            f"<tbody>{document_rows}</tbody>\n</table>\n"
        )
    head = localized(
        lang,
        f"<h3>{view}complémentarité des moteurs "
        f"(oracle, n={comp.n_documents} documents)</h3>\n",
        f"<h3>{view}engine complementarity "
        f"(oracle, n={comp.n_documents} documents)</h3>\n",
    )
    prose = localized(
        lang,
        '<p class="muted">Rappel des tokens de la GT (multiset) par moteur '
        "seul, contre l'<strong>oracle</strong> : l'union des moteurs où "
        "chaque token est rattrapé par le meilleur moteur sur ce token. "
        "<strong>Borne supérieure</strong> optimiste, en sac de mots — "
        "l'<strong>ordre est ignoré</strong> ; un vote séquentiel réel ferait "
        "au mieux autant, en général moins. À lire comme un plafond de gain "
        "d'ensemble, pas une prédiction.</p>\n",
        '<p class="muted">Recall of GT tokens (multiset) per single '
        "engine, against the <strong>oracle</strong>: the union of engines where "
        "each token is recovered by the best engine on that token. "
        "<strong>Upper bound</strong>, optimistic, bag-of-words — "
        "<strong>order is ignored</strong>; a real sequential vote would do "
        "at best as well, generally less. Read it as a ceiling of ensemble gain, "
        "not a prediction.</p>\n",
    )
    th_pipeline = localized(lang, "Pipeline", "Pipeline")
    th_token_recall = localized(lang, "rappel tokens", "token recall")
    abs_gap = localize_decimal(f"{comp.absolute_gap:.1%}", lang)
    rel_gap = localize_decimal(f"{comp.relative_gap:.1%}", lang)
    gap_prose = localized(
        lang,
        f'<p class="muted">Écart absolu oracle − meilleur '
        f"({escape(comp.best_engine)}) : {abs_gap} ; écart "
        f"relatif : {rel_gap} des erreurs du meilleur moteur "
        "théoriquement rattrapables par un ensemble.</p>\n",
        f'<p class="muted">Absolute oracle − best gap '
        f"({escape(comp.best_engine)}): {abs_gap} ; relative "
        f"gap: {rel_gap} of the best engine's errors "
        "theoretically recoverable by an ensemble.</p>\n",
    )
    return (
        head
        + prose
        + '<table class="data">\n<thead><tr><th>'
        f"{th_pipeline}</th>"
        f'<th class="num-cell">{th_token_recall}</th></tr></thead>\n'
        f"<tbody>{''.join(rows)}</tbody>\n</table>\n"
        + gap_prose
        + documents
    )


def _divergence_block(
    view: str, divergence: InterEngineDivergence, order: Mapping[str, int], lang: str
) -> str:
    """Rendu du bloc divergence : JS paire-à-paire sur les profils d'erreurs."""
    rows = "".join(
        f'<tr><td class="eng-cell">'
        f"{engine_cell(pair.a, order.get(pair.a, 0))} · "
        f"{engine_cell(pair.b, order.get(pair.b, 0))}</td>"
        f'<td class="disp">{localize_decimal(f"{pair.divergence:.4f}", lang)}</td></tr>'
        for pair in divergence.pairs
    )
    if divergence.max_pair is not None:
        max_div = localize_decimal(f"{divergence.max_pair.divergence:.4f}", lang)
        max_pair = localized(
            lang,
            f'<p class="muted">Paire la plus divergente : '
            f"{escape(divergence.max_pair.a)} · {escape(divergence.max_pair.b)} "
            f"({max_div} bit).</p>\n",
            f'<p class="muted">Most divergent pair: '
            f"{escape(divergence.max_pair.a)} · {escape(divergence.max_pair.b)} "
            f"({max_div} bit).</p>\n",
        )
    else:
        max_pair = localized(
            lang,
            '<p class="muted">Profils d\'erreurs identiques : aucune paire '
            "divergente.</p>\n",
            '<p class="muted">Identical error profiles: no divergent '
            "pair.</p>\n",
        )
    head = localized(
        lang,
        f"<h3>{view}divergence des profils d'erreurs "
        "(Jensen-Shannon)</h3>\n",
        f"<h3>{view}divergence of error profiles "
        "(Jensen-Shannon)</h3>\n",
    )
    prose = localized(
        lang,
        '<p class="muted">Divergence JS en bits ([0 ; 1]) entre les '
        "distributions de classes d'erreurs (taxonomie) des moteurs : 0 = "
        "mêmes natures d'erreurs, 1 = profils disjoints. Une paire divergente "
        "se trompe différemment — candidate naturelle à un ensemble.</p>\n",
        '<p class="muted">JS divergence in bits ([0 ; 1]) between the '
        "error-class distributions (taxonomy) of the engines: 0 = "
        "same kinds of errors, 1 = disjoint profiles. A divergent pair "
        "errs differently — a natural candidate for an ensemble.</p>\n",
    )
    th_pair = localized(lang, "Paire", "Pair")
    return (
        head
        + prose
        + '<table class="data">\n<thead><tr><th>'
        f"{th_pair}</th>"
        '<th class="num-cell">JS (bits)</th></tr></thead>\n'
        f"<tbody>{rows}</tbody>\n</table>\n"
        + max_pair
    )


def _inter_engine_blocks(
    result: RunResult, order: Mapping[str, int], lang: str
) -> str:
    """Blocs complémentarité + divergence de chaque payload ``inter_engine``."""
    multi = len({a.view for a in result.analyses}) > 1
    blocks: list[str] = []
    for analysis in result.analyses:
        payload = analysis.payload
        if not isinstance(payload, InterEnginePayload):
            continue
        label = view_prefix(analysis.view, lang, multi=multi)
        if payload.complementarity is not None:
            blocks.append(
                _complementarity_block(
                    label, payload.complementarity, order, lang
                )
            )
        if payload.taxonomy_divergence is not None:
            blocks.append(
                _divergence_block(
                    label, payload.taxonomy_divergence, order, lang
                )
            )
    return "".join(blocks)


class CrossEngineSection:
    """Tests inter-moteurs (Wilcoxon / Friedman), Holm, post-hoc + verdict."""

    name = "cross_engine"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        lang = ctx.lang
        order = engine_order(p.pipeline for p in result.pipelines)
        inter_engine = _inter_engine_blocks(result, order, lang)
        if not result.cross_engine and not inter_engine:
            return None
        significance = ""
        payloads = _payloads(result)
        if result.cross_engine:
            body: list[str] = []
            for score in result.cross_engine:
                view, metric = _split_key(score.metric)
                test, raw, holm, verdict = _row(
                    score, payloads.get((view, metric)), lang
                )
                body.append(
                    f'<tr><td class="eng-cell">{escape(view_label(view, lang))}</td>'
                    f'<td class="eng-cell">{escape(metric)}</td>'
                    f"<td>{test}</td>"
                    f'<td class="disp">{raw}</td>'
                    f'<td class="disp">{holm}</td>'
                    f'<td class="disp">{score.support}</td>'
                    f"{verdict}</tr>"
                )
            family = max(
                (payload.family_size for payload in payloads.values()), default=0
            )
            alpha = localize_decimal(
                f"{next(iter(payloads.values())).alpha:g}" if payloads else "0.05",
                lang,
            )
            correction = (
                localized(
                    lang,
                    f"p corrigée par Holm sur les {family} test(s) calculé(s) du "
                    f"run ; significatif si p corrigée &lt; α = {alpha}.",
                    f"p corrected by Holm over the run's {family} computed "
                    f"test(s); significant if corrected p &lt; α = {alpha}.",
                )
                if family
                else localized(
                    lang,
                    "Aucun test n'a pu être calculé : le motif est donné par ligne.",
                    "No test could be computed: the reason is given per row.",
                )
            )
            prose = localized(
                lang,
                '<p class="muted">Test apparié sur les cas complets (n) : '
                "Wilcoxon signé-rangs à 2 pipelines, Friedman à 3 et plus. "
                f"{correction}</p>\n",
                '<p class="muted">Paired test over complete cases (n): '
                "Wilcoxon signed-rank for 2 pipelines, Friedman for 3 or more. "
                f"{correction}</p>\n",
            )
            th_view = localized(lang, "Vue", "View")
            th_metric = localized(lang, "Métrique", "Metric")
            th_test = localized(lang, "Test", "Test")
            th_raw = localized(lang, "p brute", "raw p")
            th_holm = localized(lang, "p (Holm)", "p (Holm)")
            th_verdict = localized(lang, "verdict", "verdict")
            significance = (
                prose
                + '<table class="data">\n'
                f"<thead><tr><th>{th_view}</th><th>{th_metric}</th>"
                f"<th>{th_test}</th>"
                f'<th class="num-cell">{th_raw}</th>'
                f'<th class="num-cell">{th_holm}</th>'
                '<th class="num-cell">n</th>'
                f"<th>{th_verdict}</th></tr></thead>\n"
                f"<tbody>{''.join(body)}</tbody>\n</table>\n"
            )
        # Préfixe « <vue> · » devant la métrique, seulement si plusieurs vues.
        multi = len({a.view for a in result.analyses}) > 1
        blocks = "".join(
            _inference_block(
                f"{escape(view_label(analysis.view, lang))} · " if multi else "",
                analysis.payload, order, lang,
            )
            for analysis in result.analyses
            if isinstance(analysis.payload, InferencePayload)
            and analysis.payload.mean_ranks
        )
        title = localized(
            lang, "Significativité inter-moteurs", "Inter-engine significance"
        )
        return Html(
            f"<h2>{title}</h2>\n"
            + significance
            + blocks
            + inter_engine
        )


__all__ = ["CrossEngineSection"]
