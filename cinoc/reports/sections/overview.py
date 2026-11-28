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
from cinoc.reports.metric_categories import (
    category_legend,
    category_mark,
    is_established,
)
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import (
    bar_cell,
    bar_legend,
    col_max,
    format_value,
    group_header_row,
    is_displayed,
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
        population = _population_note(result, ctx.lang)
        if population:
            parts.append(population)
        note = failures_note(result, ctx.lang)
        if note:
            parts.append(note)
        multi = len(views) > 1
        for view_name in views:
            parts.append(_table_for_view(result, view_name, ctx.lang, multi=multi))
            parts.append(_qualities_block(result, view_name, ctx.lang))
        return Html("\n".join(part for part in parts if part) + "\n")


def _population_note(result: RunResult, lang: str) -> str:
    """La **population cible** du corpus et la **pondération** de son macro (B3),
    quand le corpus les déclare : l'échantillon représente quelque chose, et le
    macro est une moyenne par document ou par grappe."""
    entry = next(iter(result.pipelines), None)
    if entry is None:
        return ""
    by_cluster = entry.cluster_weighting == "cluster"
    if entry.target_population is None and not by_cluster:
        return ""
    weighting = localized(
        lang,
        "moyenne par grappe (chaque grappe pèse autant)"
        if by_cluster
        else "moyenne par document",
        "mean per cluster (each cluster weighs the same)"
        if by_cluster
        else "mean per document",
    )
    pieces = []
    if entry.target_population is not None:
        pieces.append(
            f"{localized(lang, 'Population cible', 'Target population')} : "
            f"{escape(entry.target_population)}"
        )
    pieces.append(
        f"{localized(lang, 'Pondération du macro', 'Macro weighting')} : {weighting}"
    )
    return f'<p class="muted">{" · ".join(pieces)}</p>'


def _qualities_block(result: RunResult, view_name: str, lang: str) -> str:
    """Les **deux qualités** (§ 2.1 f), avec leur couverture, là où elles
    diffèrent : la conditionnelle (observations complètes) et l'opérationnelle
    (ce que l'utilisateur reçoit : partielles telles que produites, échecs notés
    comme une sortie vide). Rien quand toutes les unités sont complètes."""
    rows: list[str] = []
    order = engine_order(p.pipeline for p in result.pipelines)
    for entry in result.pipelines:
        if entry.view != view_name:
            continue
        operationals = {s.metric: s for s in entry.operational_aggregate}
        for conditional in entry.conditional_aggregate:
            metric = conditional.metric
            operational = operationals.get(metric)
            if operational is None:
                continue
            same = (conditional.value, conditional.support) == (
                operational.value,
                operational.support,
            )
            if same or not (is_established(metric) and is_displayed(metric)):
                continue
            expected = conditional.expected if conditional.expected is not None else 0
            motifs = " · ".join(
                f"{escape(motif)} {n}"
                for motif, n in (conditional.coverage or {}).items()
            )
            badge = engine_cell(entry.pipeline, order.get(entry.pipeline, 0))
            rows.append(
                f'<tr><td class="eng-cell">{badge}'
                f"</td><td>{escape(conditional.metric)}</td>"
                f'<td class="disp">{format_value(conditional, lang)} '
                f'<span class="muted">{conditional.support}/{expected}</span></td>'
                f'<td class="disp">{format_value(operational, lang)} '
                f'<span class="muted">{operational.support}/{expected}</span></td>'
                f'<td class="muted">{motifs or "—"}</td></tr>'
            )
    if not rows:
        return ""
    title = localized(lang, "Deux qualités de lecture", "Two readings of quality")
    prose = localized(
        lang,
        '<p class="muted"><b>Conditionnelle</b> : les observations complètes '
        "seules — ce que le pipeline sait faire quand il va au bout. "
        "<b>Opérationnelle</b> : toutes les unités attendues, les partielles "
        "telles que produites et les échecs notés comme une sortie vide — ce que "
        "l'utilisateur reçoit. Chaque cellule dit « notées / attendues » ; la "
        "couverture donne, par motif, les attendues non entrées dans "
        "l'agrégat conditionnel.</p>\n",
        '<p class="muted"><b>Conditional</b>: complete observations only — what '
        "the pipeline does when it goes through. <b>Operational</b>: every "
        "expected unit, partial ones as produced and failures scored as an "
        "empty output — what the user actually gets. Each cell reads “scored / "
        "expected”; the coverage lists, by reason, the expected units that did "
        "not enter the conditional aggregate.</p>\n",
    )
    th = (
        localized(lang, "Pipeline", "Pipeline"),
        localized(lang, "Métrique", "Metric"),
        localized(lang, "Conditionnelle", "Conditional"),
        localized(lang, "Opérationnelle", "Operational"),
        localized(lang, "Couverture (motifs)", "Coverage (reasons)"),
    )
    return (
        f"<h3>{title}</h3>\n{prose}"
        '<div class="table-scroll"><table class="data">\n'
        f"<thead><tr><th>{th[0]}</th><th>{th[1]}</th>"
        f'<th class="num-cell">{th[2]}</th><th class="num-cell">{th[3]}</th>'
        f"<th>{th[4]}</th></tr></thead>\n"
        f"<tbody>{''.join(rows)}</tbody>\n</table></div>\n"
    )


#: Libellé du motif codé d'un échec (``FailureReason``) : ``(fr, en)``.
REASON_LABELS: dict[str, tuple[str, str]] = {
    "engine": ("moteur", "engine"),
    "infrastructure": ("infrastructure", "infrastructure"),
    "unsupported": ("pipeline inapplicable", "pipeline not applicable"),
    "cancelled": ("arrêtée (délai)", "stopped (deadline)"),
}


def failures_note(result: RunResult, lang: str) -> str:
    """**Pourquoi** une unité manque ou cloche : échecs, puis sorties incomplètes.

    Lu dans ``RunResult.usage`` (issue produite par l'exécution), jamais déduit
    d'un score absent : un ``None`` peut aussi vouloir dire « pas de vérité
    terrain » ou « métrique inapplicable », qui ne sont pas des échecs.
    """
    return (
        _failed_note(result, lang)
        + _incomplete_note(result, lang, "partial")
        + _incomplete_note(result, lang, "truncated")
    )


#: ``issue → (titre FR, titre EN, cause FR, cause EN)`` d'une sortie incomplète.
_INCOMPLETE = {
    "partial": (
        "Unités partielles",
        "Partial units",
        "étape déclarée incomplète (régions perdues, lignes restées en repli)",
        "stage declared incomplete (lost regions, lines fallen back)",
    ),
    "truncated": (
        "Unités tronquées",
        "Truncated units",
        "sortie coupée par un plafond de jetons",
        "output cut by a token limit",
    ),
}


def _incomplete_note(result: RunResult, lang: str, outcome: str) -> str:
    """Unités à sortie **incomplète** (partielle ou tronquée) : elles ont une
    sortie, signalée. Par défaut elles ne sont **pas notées** (leur statistique
    est gardée à part, la couverture les compte) ; sous ``empty_page`` elles le
    sont sur leur sortie réelle, la part manquante comprise (§ 2.1 e, f)."""
    cut = [u for u in result.usage if u.outcome == outcome]
    if not cut:
        return ""
    order = engine_order(p.pipeline for p in result.pipelines)
    fr_title, en_title, fr_cause, en_cause = _INCOMPLETE[outcome]
    title = localized(lang, fr_title, en_title)
    if result.manifest.failure_policy == "empty_page":
        rule = localized(
            lang,
            f"<strong>notées sur leur sortie réelle</strong> ({fr_cause}) : leur "
            "score compte dans l'agrégat et mesure aussi la part manquante",
            f"<strong>scored on their actual output</strong> ({en_cause}): their "
            "score counts in the aggregate and also measures the missing part",
        )
    else:
        rule = localized(
            lang,
            f"<strong>non notées par défaut</strong> ({fr_cause}) : elles "
            "sortent de l'agrégat conditionnel, que la couverture compte ; la "
            "qualité opérationnelle du résultat les note sur leur sortie réelle",
            f"<strong>not scored by default</strong> ({en_cause}): they leave "
            "the conditional aggregate, which the coverage counts; the result's "
            "operational quality scores their actual output",
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
    if result.manifest.failure_policy == "empty_page":
        rule = localized(
            lang,
            "notées comme une <strong>page vide</strong> (les comptes de leur "
            "référence face à une sortie sans texte)",
            "scored as an <strong>empty page</strong> (the counts of their "
            "reference against an output with no text)",
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
    rows = [result.principal_aggregate(p) for p in pipelines]
    keep = nonempty_metric_indices(rows)  # masque les colonnes tout-« — »
    if not keep:
        # Un tableau d'en-têtes sans une valeur ne dit rien — pire, il laisse
        # croire à un rendu cassé. On dit pourquoi rien n'est noté (D-307).
        return _unscored_note(result, pipelines, view_name, lang, multi=multi)
    all_metrics = tuple(
        score.metric for score in result.principal_aggregate(pipelines[0])
    )
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
            bar_cell(
                result.principal_aggregate(pipeline)[i], maxes[j], lang=lang
            )
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
