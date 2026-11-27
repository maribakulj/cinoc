"""Section overview : bande de **readouts** (portée du corpus) + une table par
vue, pipelines × métriques, avec **data-bars** proportionnelles. Couche 7.

Le contenu reste piloté par les **vraies** métriques de ``RunResult`` (ce que le
moteur calcule : CER/WER/MER aujourd'hui) — **jamais** par les métriques que le
design *dessine* mais que le moteur ne produit pas encore (note d'archi :
pas de rapport en avance sur sa donnée). Les sections plus riches arrivent au fil
des métriques.
"""

from __future__ import annotations

from cinoc.evaluation.result import PipelineResult, RunResult
from cinoc.reports.composition_diff import homonym_hints
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized, view_label
from cinoc.reports.metric_categories import category_legend, category_mark
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import (
    bar_cell,
    bar_legend,
    col_max,
    group_header_row,
    metric_short_label,
    nonempty_metric_indices,
    ordered_unique,
)


class OverviewSection:
    """Métriques par vue (data-bars). La **portée** (docs/moteurs) vit dans le
    héros de la vue (rendu par le renderer), plus dans une bande de readouts ici."""

    name = "overview"
    requires: tuple[str, ...] = ()  # générique : affiche les métriques présentes

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not result.pipelines:
            return None
        views = ordered_unique(p.view for p in result.pipelines)
        corpus = localized(ctx.lang, "Corpus", "Corpus")
        parts: list[str] = [
            f"<h2>{localized(ctx.lang, 'Métriques par vue', 'Metrics per view')}</h2>",
            f'<p class="muted">{corpus} : '
            f"{escape(result.manifest.corpus_name)}</p>",
        ]
        note = failures_note(result, ctx.lang)
        if note:
            parts.append(note)
        multi = len(views) > 1
        for view_name in views:
            parts.append(_table_for_view(result, view_name, ctx.lang, multi=multi))
        return Html("\n".join(parts) + "\n")


#: Libellé du motif codé d'un échec (``FailureReason``) : ``(fr, en)``.
REASON_LABELS: dict[str, tuple[str, str]] = {
    "engine": ("moteur", "engine"),
    "infrastructure": ("infrastructure", "infrastructure"),
    "unsupported": ("pipeline inapplicable", "pipeline not applicable"),
    "cancelled": ("arrêtée (délai)", "stopped (deadline)"),
}


def failures_note(result: RunResult, lang: str) -> str:
    """**Pourquoi** une unité manque ou cloche : échecs, puis coupures.

    Lu dans ``RunResult.usage`` (issue produite par l'exécution), jamais déduit
    d'un score absent : un ``None`` peut aussi vouloir dire « pas de vérité
    terrain » ou « métrique inapplicable », qui ne sont pas des échecs.
    """
    return _failed_note(result, lang) + _truncated_note(result, lang)


def _truncated_note(result: RunResult, lang: str) -> str:
    """Unités **tronquées** : notées, mais signalées — leur score mesure aussi
    la coupure. ``failure_policy`` ne s'y applique pas : elles ont une sortie."""
    cut = [u for u in result.usage if u.outcome == "truncated"]
    if not cut:
        return ""
    order = engine_order(p.pipeline for p in result.pipelines)
    title = localized(lang, "Unités tronquées", "Truncated units")
    rule = localized(
        lang,
        "<strong>notées sur leur sortie réelle</strong>, coupée par un plafond "
        "de jetons : leur score compte dans la moyenne et mesure aussi la "
        "coupure",
        "<strong>scored on their actual output</strong>, cut by a token limit: "
        "their score counts in the mean and also measures the cut",
    )
    items = []
    for unit in cut:
        badge = engine_cell(unit.pipeline, order.get(unit.pipeline, 0))
        message = f" — {escape(unit.message)}" if unit.message else ""
        items.append(
            f'<li><span class="eng-cell">{badge}</span> · '
            f"{escape(unit.document_id)}{message}</li>"
        )
    return (
        f'<div class="failures"><p><strong>{title}</strong> ({len(cut)}) — '
        f"{rule}.</p><ul>{''.join(items)}</ul></div>"
    )


def _failed_note(result: RunResult, lang: str) -> str:
    failed = [u for u in result.usage if u.outcome == "failed"]
    if not failed:
        return ""
    order = engine_order(p.pipeline for p in result.pipelines)
    n = len(failed)
    if result.manifest.failure_policy == "max_error":
        rule = localized(
            lang,
            "notées à l'<strong>erreur maximale</strong> (1 pour un taux "
            "d'erreur, 0 pour un score), pondérées par leur référence",
            "scored at the <strong>maximum error</strong> (1 for an error rate, "
            "0 for a score), weighted by their reference",
        )
    else:
        rule = localized(
            lang,
            "<strong>exclues de la moyenne</strong> ; un agrégat qui en a perdu "
            "porte « n notés / n attendus »",
            "<strong>left out of the mean</strong>; an aggregate that lost some "
            "shows “n scored / n expected”",
        )
    title = localized(lang, "Unités en échec", "Failed units")
    items = []
    for unit in failed:
        fr, en = REASON_LABELS[str(unit.reason)]
        badge = engine_cell(unit.pipeline, order.get(unit.pipeline, 0))
        message = f" : {escape(unit.message)}" if unit.message else ""
        items.append(
            f'<li><span class="eng-cell">{badge}</span> · '
            f"{escape(unit.document_id)} — <strong>{localized(lang, fr, en)}</strong>"
            f"{message}</li>"
        )
    return (
        f'<div class="failures"><p><strong>{title}</strong> ({n}) — {rule}.</p>'
        f"<ul>{''.join(items)}</ul></div>"
    )


def _table_for_view(
    result: RunResult, view_name: str, lang: str, *, multi: bool
) -> str:
    pipelines = [p for p in result.pipelines if p.view == view_name]
    order = engine_order(p.pipeline for p in result.pipelines)
    hints = homonym_hints(result.manifest)
    rows = [p.aggregate for p in pipelines]
    keep = nonempty_metric_indices(rows)  # masque les colonnes tout-« — »
    if not keep:
        # Un tableau d'en-têtes sans une valeur ne dit rien — pire, il laisse
        # croire à un rendu cassé. On dit pourquoi rien n'est noté (D-307).
        return _unscored_note(result, pipelines, view_name, lang, multi=multi)
    all_metrics = tuple(score.metric for score in pipelines[0].aggregate)
    metrics = [all_metrics[i] for i in keep]
    header = "".join(
        f'<th class="num-cell" title="{escape(m)}">'
        f"{escape(metric_short_label(m))}{category_mark(m, lang)}</th>"
        for m in metrics
    )
    maxes = [col_max(rows, i) for i in keep]
    body_rows: list[str] = []
    for pipeline in pipelines:
        cells = "".join(
            bar_cell(pipeline.aggregate[i], maxes[j], lang=lang)
            for j, i in enumerate(keep)
        )
        badge = engine_cell(
            pipeline.pipeline,
            order.get(pipeline.pipeline, 0),
            hints.get(pipeline.pipeline, ""),
        )
        body_rows.append(f'<tr><td class="eng-cell">{badge}</td>{cells}</tr>')
    # Libellé de vue affiché **seulement** s'il y a plusieurs vues à distinguer
    # (sinon « Métriques par vue » + la ligne corpus suffisent — pas de ressassage).
    head = ""
    if multi:
        view_caption = localized(lang, "Vue", "View")
        head = f"<h2>{view_caption} : {escape(view_label(view_name, lang))}</h2>\n"
    return (
        f"{head}"
        '<div class="table-scroll">'
        f'<table class="data">\n<thead>{group_header_row(metrics, lang, lead=1)}'
        f"<tr><th>Pipeline</th>{header}</tr></thead>\n"
        f"<tbody>{''.join(body_rows)}</tbody>\n</table></div>\n"
        f"{bar_legend(lang)}{category_legend(metrics, lang)}"
    )


def _unscored_note(
    result: RunResult,
    pipelines: list[PipelineResult],
    view_name: str,
    lang: str,
    *,
    multi: bool,
) -> str:
    """Une vue sans aucun chiffre : faute de vérité terrain, ou d'unité réussie."""
    noms = {p.pipeline for p in pipelines}
    unites = [u for u in result.usage if u.pipeline in noms]
    head = ""
    if multi:
        view_caption = localized(lang, "Vue", "View")
        head = f"<h2>{view_caption} : {escape(view_label(view_name, lang))}</h2>\n"
    if unites and all(u.outcome == "failed" for u in unites):
        texte = localized(
            lang,
            "Aucun chiffre dans cette vue : toutes ses unités ont échoué "
            "(détail ci-dessus).",
            "No figure in this view: all its units failed (detail above).",
        )
    else:
        texte = localized(
            lang,
            "<strong>Rien n'est noté dans cette vue</strong> : aucune sortie n'y "
            "avait de vérité terrain à laquelle se comparer. Les autres sections "
            "décrivent ce qui a été produit — et, pour une correction, ce qui a "
            "été changé ou refusé —, pas son exactitude. Une transcription "
            "<code>&lt;nom&gt;.gt.txt</code> déposée à côté de chaque image en "
            "donne une.",
            "<strong>Nothing is scored in this view</strong>: no output had a "
            "ground truth to be compared with. The other sections describe what "
            "was produced — and, for a correction, what was changed or refused —, "
            "not how accurate it is. A transcription "
            "<code>&lt;name&gt;.gt.txt</code> next to each image provides one.",
        )
    return f'{head}<p class="muted">{texte}</p>\n'


__all__ = ["REASON_LABELS", "OverviewSection"]
