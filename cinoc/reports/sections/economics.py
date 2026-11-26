"""Section économie : coûts estimés, débit effectif, Pareto (couche 7).

Le débit « effectif » est une **simulation** (temps de relecture supposé par
erreur caractère, ``time_per_error_seconds``), étiquetée comme telle (D-288).

Rend les payloads ``economics`` de ``RunResult.analyses`` en **lecture seule**
(tout est calculé en couche 3 — anti data-layer). Chaque nombre est une
fonction auditable des mesures E1 + de la table de tarifs **datée** : si la
table est périmée au moment du run (``pricing_stale``), un avertissement
explicite est rendu — jamais un chiffre silencieusement périmé.
"""

from __future__ import annotations

from cinoc.evaluation.analysis import EconomicsPayload, MarginalCost
from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._payload import render_payload_section


def _fmt(value: float | None, lang: str, pattern: str = "{:.4f}") -> str:
    return "—" if value is None else localize_decimal(pattern.format(value), lang)


def _marginal_row(m: MarginalCost, lang: str) -> str:
    delta = localize_decimal(f"{m.cost_delta_eur:+.4f}", lang)
    avoided = localize_decimal(f"{m.errors_avoided:+.1f}", lang)
    return (
        f'<tr><td class="eng-cell">{escape(m.pipeline)}</td>'
        f'<td class="eng-cell">{escape(m.baseline)}</td>'
        f'<td class="disp">{delta}</td>'
        f'<td class="disp">{avoided}</td>'
        f'<td class="disp">{_fmt(m.eur_per_avoided_error, lang)}</td></tr>'
    )


def _fmt_int(value: int | None) -> str:
    return "—" if value is None else f"{value}"


def _block(
    view: str, payload: EconomicsPayload, lang: str, order: dict[str, int]
) -> str:
    rows: list[str] = []
    for row in payload.pipelines:
        badge = engine_cell(row.pipeline, order.get(row.pipeline, 0))
        dur = _fmt(row.duration_seconds, lang, "{:.1f}")
        if row.n_resumed:
            dur += " ↺"  # durées relues de l'archive (note sous le tableau)
        basis = escape(row.basis)
        if row.billed_pages is not None:
            basis += localized(
                lang,
                f" ({row.billed_pages} p. facturée(s))",
                f" ({row.billed_pages} billed p.)",
            )
        if row.self_hosted:
            served = ", ".join(escape(m) for m in row.self_hosted)
            basis += localized(
                lang, f" — auto-hébergé : {served}", f" — self-hosted: {served}"
            )
        pph = _fmt(row.pages_per_hour, lang, "{:.1f}")
        pph_eff = _fmt(row.pages_per_hour_effective, lang, "{:.1f}")
        rows.append(
            f'<tr><td class="eng-cell">{badge}</td>'
            f'<td class="disp">{_fmt(row.cer, lang)}</td>'
            f'<td class="disp">{dur}</td>'
            f'<td class="disp">{_fmt_int(row.tokens_in)}</td>'
            f'<td class="disp">{_fmt_int(row.tokens_out)}</td>'
            f'<td class="disp">{_fmt(row.cost_eur, lang)}</td>'
            f'<td class="eng-cell">{basis}</td>'
            f'<td class="disp">{pph}</td>'
            f'<td class="disp">{pph_eff}</td>'
            "</tr>"
        )
    stale = (
        localized(
            lang,
            '<p class="verdict sig">⚠ Table de tarifs périmée au moment du run '
            f"(valable jusqu'au {escape(payload.pricing_valid_until)}) — coûts à "
            "revalider.</p>\n",
            '<p class="verdict sig">⚠ Pricing table stale at run time '
            f"(valid until {escape(payload.pricing_valid_until)}) — costs to "
            "revalidate.</p>\n",
        )
        if payload.pricing_stale
        else ""
    )
    marginal = ""
    if payload.marginal:
        items = "".join(_marginal_row(m, lang) for m in payload.marginal)
        marginal_head = localized(
            lang,
            "Coût marginal (vs pipeline le moins cher)",
            "Marginal cost (vs cheapest pipeline)",
        )
        th_pipeline = localized(lang, "Pipeline", "Pipeline")
        th_baseline = localized(lang, "Référence", "Baseline")
        th_cost_delta = localized(
            lang,
            f"Δ coût ({escape(payload.currency)})",
            f"Δ cost ({escape(payload.currency)})",
        )
        th_errors_avoided = localized(lang, "erreurs évitées", "errors avoided")
        th_per_avoided = localized(
            lang,
            f"{escape(payload.currency)}/erreur évitée",
            f"{escape(payload.currency)}/avoided error",
        )
        marginal = (
            f"<h4>{marginal_head}</h4>\n"
            f'<table class="data">\n<thead><tr><th>{th_pipeline}</th>'
            f"<th>{th_baseline}</th>"
            f'<th class="num-cell">{th_cost_delta}</th>'
            f'<th class="num-cell">{th_errors_avoided}</th>'
            f'<th class="num-cell">{th_per_avoided}</th>'
            f"</tr></thead>\n<tbody>{items}</tbody>\n</table>\n"
        )
    resumed = [r for r in payload.pipelines if r.n_resumed]
    inherited = ""
    if resumed:
        names = ", ".join(
            f"{escape(r.pipeline)} : {r.n_resumed}/{r.n_documents}" for r in resumed
        )
        inherited = localized(
            lang,
            f'<p class="muted">↺ Unités relues de l\'archive ({names}) : leur durée '
            "et leurs jetons sont ceux de leur première exécution, pas une "
            "mesure de ce run.</p>\n",
            f'<p class="muted">↺ Units read from the archive ({names}): their '
            "duration and tokens are those of their first execution, not a "
            "measurement of this run.</p>\n",
        )
    self_hosted = (
        localized(
            lang,
            '<p class="muted">Auto-hébergé : servi par un serveur que '
            "l'opérateur fait tourner — aucun tarif de fournisseur appliqué ; "
            "coût = temps machine seul, jetons mesurés sans être facturés.</p>\n",
            '<p class="muted">Self-hosted: served by a server the operator '
            "runs — no provider price applied; cost = machine time only, tokens "
            "measured but not billed.</p>\n",
        )
        if any(r.self_hosted for r in payload.pipelines)
        else ""
    )
    pareto = ""
    if payload.pareto_cost or payload.pareto_speed:
        cost_names = ", ".join(escape(n) for n in payload.pareto_cost) or "—"
        speed_names = ", ".join(escape(n) for n in payload.pareto_speed) or "—"
        pareto = localized(
            lang,
            f'<p class="muted">Front de Pareto {escape(payload.metric)} × coût : '
            f"{cost_names} · {escape(payload.metric)} × durée : {speed_names}.</p>\n",
            f'<p class="muted">Pareto front {escape(payload.metric)} × cost: '
            f"{cost_names} · {escape(payload.metric)} × duration: {speed_names}.</p>\n",
        )
    head = localized(
        lang,
        f"{view}coûts &amp; débit",
        f"{view}costs &amp; throughput",
    )
    rate = localize_decimal(f"{payload.hourly_rate_eur:g}", lang)
    tpe = localize_decimal(f"{payload.time_per_error_seconds:g}", lang)
    prose = localized(
        lang,
        '<p class="muted">Coûts <strong>indicatifs</strong> : temps machine '
        f"(durée mesurée × {rate} "
        f"{escape(payload.currency)}/h) + jetons cloud et pages facturées au "
        "tarif de la table — chaque tentative facturable comptée, unités en "
        "échec comprises — "
        f"(valable jusqu'au {escape(payload.pricing_valid_until)}). Le débit "
        "effectif est une <strong>simulation</strong>, pas une mesure : il "
        "retire un temps de relecture supposé (hypothèse : "
        f"{tpe} s par erreur caractère).</p>\n",
        '<p class="muted">Costs are <strong>indicative</strong>: machine time '
        f"(measured duration × {rate} "
        f"{escape(payload.currency)}/h) + cloud tokens and billed pages at the "
        "table's rate — every billable attempt counted, failed units included "
        f"(valid until {escape(payload.pricing_valid_until)}). Effective "
        "throughput is a <strong>simulation</strong>, not a measurement: it "
        "subtracts an assumed proofreading time (assumption: "
        f"{tpe} s per character error).</p>\n",
    )
    th_pipeline = localized(lang, "Pipeline", "Pipeline")
    th_duration = localized(lang, "durée (s)", "duration (s)")
    th_tokens_in = localized(lang, "jetons in", "tokens in")
    th_tokens_out = localized(lang, "jetons out", "tokens out")
    th_cost = localized(
        lang,
        f"coût ({escape(payload.currency)})",
        f"cost ({escape(payload.currency)})",
    )
    th_basis = localized(lang, "base", "basis")
    th_pages_per_hour = localized(lang, "pages/h", "pages/h")
    th_pages_per_hour_eff = localized(
        lang, "pages/h effectif (simulation)", "pages/h effective (simulation)"
    )
    return (
        f"<h3>{head}</h3>\n"
        + stale
        + prose
        + '<table class="data">\n'
        f"<thead><tr><th>{th_pipeline}</th>"
        f'<th class="num-cell">{escape(payload.metric)}</th>'
        f'<th class="num-cell">{th_duration}</th>'
        f'<th class="num-cell">{th_tokens_in}</th>'
        f'<th class="num-cell">{th_tokens_out}</th>'
        f'<th class="num-cell">{th_cost}</th>'
        f"<th>{th_basis}</th>"
        f'<th class="num-cell">{th_pages_per_hour}</th>'
        f'<th class="num-cell">{th_pages_per_hour_eff}</th></tr></thead>\n'
        f"<tbody>{''.join(rows)}</tbody>\n</table>\n"
        + inherited
        + self_hosted
        + pareto
        + marginal
    )


class EconomicsSection:
    """Coûts estimés, débit effectif et fronts de Pareto, par vue."""

    name = "economics"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        order = engine_order(p.pipeline for p in result.pipelines)
        return render_payload_section(
            result,
            ctx,
            payload_type=EconomicsPayload,
            title=localized(ctx.lang, "Économie", "Economics"),
            block=lambda view, payload: _block(view, payload, ctx.lang, order),
        )


__all__ = ["EconomicsSection"]
