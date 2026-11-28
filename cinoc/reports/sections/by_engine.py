"""Section by-engine : **comparaison** des moteurs sur la vue primaire +
**dispersion** du taux d'erreur par-document. Couche 7.

Distinct de l'overview (tables descriptives, une par vue) : ici la table des
métriques **établies** — les seules classées (D-289) —, **ordonnée** selon le tri
du support global (un tri, pas un rang ordinal attribué), plus
l'**étendue** (min · médiane · max) du CER sur les documents, c.-à-d. la
**fiabilité** que l'agrégat masque (et que ni l'overview ni le par-document ne
donnent). Puis une table **diagnostic** des métriques adaptées et exploratoires,
marquées comme telles, sans tri ni test. On expose les chiffres ; l'utilisateur
interprète (aucun gagnant déclaré — cf. ``key_measures`` §6/§12).
"""

from __future__ import annotations

from statistics import median

from cinoc.domain.evaluation import MetricCategory
from cinoc.evaluation.result import (
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized, view_label
from cinoc.reports.metric_categories import (
    category_label,
    category_legend,
    category_of,
    is_established,
)
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import (
    bar_cell,
    bar_legend,
    col_max,
    global_ranking,
    group_header_row,
    in_ranking_order,
    metric_th,
    nonempty_metric_indices,
    ordered_unique,
)


def _per_doc_values(
    documents: tuple[RunDocumentResult, ...], pipeline: str, view: str, metric: str
) -> list[float]:
    """Valeurs par-document (non ``None``) d'une métrique pour un moteur/vue."""
    out: list[float] = []
    for doc in documents:
        if doc.pipeline == pipeline and doc.view == view:
            for score in doc.scores:
                if score.metric == metric and score.value is not None:
                    out.append(score.value)
    return out


class EngineSection:
    """Comparaison des moteurs (vue primaire, métriques établies) + dispersion
    par-document du CER + table diagnostic des adaptées et exploratoires."""

    name = "by_engine"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not result.pipelines:
            return None
        view = ordered_unique(p.view for p in result.pipelines)[0]
        rows = [p for p in result.pipelines if p.view == view]
        aggregates = {p.pipeline: result.principal_aggregate(p) for p in rows}
        metrics = tuple(s.metric for s in aggregates[rows[0].pipeline])
        if not metrics:
            return None
        sort_metric = "cer" if "cer" in metrics else metrics[0]
        # Le tri est celui du **support global** publié (B7) : classer d'après
        # les valeurs propres de chaque pipeline, sur des supports différents,
        # contredirait le tri que le résultat publie (D7).
        ordered = in_ranking_order(rows, global_ranking(result, view, sort_metric))
        # Badge moteur (lettre + accent) = identité STABLE, indépendante du rang :
        # ordre canonique = première apparition dans le run (partagé entre sections).
        order = engine_order(p.pipeline for p in result.pipelines)
        # Masque les colonnes tout-« — ».
        keep = nonempty_metric_indices([aggregates[p.pipeline] for p in rows])
        ranked = [i for i in keep if is_established(metrics[i])]
        # Adaptées puis exploratoires (ordre de la vue dans chaque catégorie).
        diagnostic = sorted(
            (i for i in keep if not is_established(metrics[i])),
            key=lambda i: (
                category_of(metrics[i]) is MetricCategory.EXPLORATORY,
                keep.index(i),
            ),
        )
        multi = len(ordered_unique(p.view for p in result.pipelines)) > 1
        vlbl = escape(view_label(view, ctx.lang))
        out = ""
        if ranked:
            out += self._ranking(
                result, view, ordered, aggregates, metrics, ranked, sort_metric,
                order, ctx.lang,
                f" (vue : {vlbl})" if multi else "",
                f" (view: {vlbl})" if multi else "",
            )
        if diagnostic:
            out += self._diagnostic(
                ordered, aggregates, metrics, diagnostic, order, ctx.lang
            )
        return Html(out) if out else None

    @staticmethod
    def _ranking(
        result: RunResult,
        view: str,
        ordered: list[PipelineResult],
        aggregates: dict[str, tuple[MetricScore, ...]],
        metrics: tuple[str, ...],
        keep: list[int],
        sort_metric: str,
        order: dict[str, int],
        lang: str,
        suffix_fr: str,
        suffix_en: str,
    ) -> str:
        maxes = [col_max([aggregates[p.pipeline] for p in ordered], i) for i in keep]
        profil_title = localized(lang, "Profil", "Profile")
        body: list[str] = []
        # Lignes ordonnées selon le tri global (un **tri** lisible, pas un rang
        # ordinal attribué : aucune colonne « # », aucun gagnant désigné).
        for pipeline in ordered:
            cells = "".join(
                bar_cell(
                    aggregates[pipeline.pipeline][i], maxes[j], lang=lang, sortable=True
                )
                for j, i in enumerate(keep)
            )
            vals = _per_doc_values(
                result.documents, pipeline.pipeline, view, sort_metric
            )
            disp = (
                localize_decimal(
                    f"{min(vals):.3f} · {median(vals):.3f} · {max(vals):.3f}",
                    lang,
                )
                if vals
                else "—"
            )
            idx = order.get(pipeline.pipeline, 0)
            badge = engine_cell(pipeline.pipeline, idx)
            # Le **nom du moteur** est le lien vers son profil drill-in (#engine-N) :
            # cliquer le moteur ouvre son analyse détaillée (≠ une petite flèche).
            body.append(
                f'<tr><td class="eng-cell"><a href="#engine-{idx}" '
                f'title="{profil_title}">{badge}</a></td>{cells}'
                f'<td class="disp">{disp}</td></tr>'
            )
        display_metrics = [metrics[i] for i in keep]
        header = "".join(metric_th(m, lang, sortable=True) for m in display_metrics)
        heading = localized(
            lang,
            f"Comparaison des moteurs{suffix_fr}",
            f"Engine comparison{suffix_en}",
        )
        prose = localized(
            lang,
            f'<p class="muted">Métriques <strong>établies</strong> — conformes à '
            f"une référence nommée, les seules classées et testées. Ordonné selon "
            f"le tri du support global ({escape(sort_metric)} ↑ sur les documents "
            "que tous les moteurs ont notés ; un tri, pas un rang attribué) · "
            f"dispersion = {escape(sort_metric)} min · médiane · "
            "max par document. Cliquer un en-tête de métrique pour réordonner ; "
            "survoler pour la définition. Aucun gagnant n'est déclaré.</p>\n",
            f'<p class="muted"><strong>Established</strong> metrics — conforming '
            f"to a named reference, the only ones ranked and tested. Ordered by "
            f"the global-support ranking ({escape(sort_metric)} ↑ over the documents "
            "every engine scored; a sort, not an assigned rank) · "
            f"dispersion = {escape(sort_metric)} min · median · "
            "max per document. Click a metric header to reorder; hover for the "
            "definition. No winner is declared.</p>\n",
        )
        th_engine = localized(lang, "Moteur", "Engine")
        th_dispersion = localized(lang, "dispersion", "dispersion")
        return (
            f"<h2>{heading}</h2>\n"
            + prose
            + '<div class="table-scroll"><table class="data sortable">\n'
            "<thead>"
            + group_header_row(display_metrics, lang, lead=1, trail=1)
            + f"<tr><th>{th_engine}</th>{header}"
            f'<th class="num-cell">{th_dispersion}</th></tr></thead>\n'
            f"<tbody>{''.join(body)}</tbody>\n</table></div>\n"
            + bar_legend(lang)
        )

    @staticmethod
    def _diagnostic(
        ordered: list[PipelineResult],
        aggregates: dict[str, tuple[MetricScore, ...]],
        metrics: tuple[str, ...],
        keep: list[int],
        order: dict[str, int],
        lang: str,
    ) -> str:
        """Adaptées et exploratoires : mêmes moteurs, même ordre, **sans tri**
        ni test — au diagnostic, affichées comme telles (D-289)."""
        maxes = [col_max([aggregates[p.pipeline] for p in ordered], i) for i in keep]
        body = "".join(
            f'<tr><td class="eng-cell">'
            f"{engine_cell(p.pipeline, order.get(p.pipeline, 0))}</td>"
            + "".join(
                bar_cell(aggregates[p.pipeline][i], maxes[j], lang=lang)
                for j, i in enumerate(keep)
            )
            + "</tr>"
            for p in ordered
        )
        display = [metrics[i] for i in keep]
        # Super-en-tête par catégorie (colonnes déjà regroupées).
        spans: list[tuple[str, int]] = []
        for metric in display:
            category = category_of(metric)
            label = category_label(category, lang) if category is not None else ""
            if spans and spans[-1][0] == label:
                spans[-1] = (label, spans[-1][1] + 1)
            else:
                spans.append((label, 1))
        group_row = '<tr class="grp-row"><th></th>' + "".join(
            f'<th class="grp-head" colspan="{n}">{escape(label)}</th>'
            for label, n in spans
        ) + "</tr>"
        header = "".join(metric_th(m, lang) for m in display)
        heading = localized(lang, "Diagnostic", "Diagnostic")
        prose = localized(
            lang,
            '<p class="muted">Métriques <strong>adaptées</strong> et '
            "<strong>exploratoires</strong> : elles éclairent un aspect que les "
            "établies ne disent pas, sans la validité qu'un classement leur "
            "prêterait — ni tri, ni test de significativité. Une exploratoire "
            "n'est pas fausse ; sa fiche au glossaire dit ce qu'elle mesure et "
            "ses limites.</p>\n",
            '<p class="muted"><strong>Adapted</strong> and '
            "<strong>exploratory</strong> metrics: they shed light on what the "
            "established ones do not say, without the validity a ranking would "
            "lend them — no sorting, no significance test. An exploratory metric "
            "is not wrong; its glossary card says what it measures and its "
            "limits.</p>\n",
        )
        th_engine = localized(lang, "Moteur", "Engine")
        return (
            f"<h3>{heading}</h3>\n"
            + prose
            + '<div class="table-scroll"><table class="data">\n'
            f"<thead>{group_row}<tr><th>{th_engine}</th>{header}</tr></thead>\n"
            f"<tbody>{body}</tbody>\n</table></div>\n"
            + category_legend(display, lang)
        )


__all__ = ["EngineSection"]
