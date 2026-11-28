"""Section by-document : le détail **par-document** de ``RunResult`` rendu en
tables au design — une par vue, documents groupés, data-bars. Couche 7.

Surface une donnée **réelle déjà calculée** (``RunResult.documents``) jusqu'ici
**sans consommateur** dans le rapport ; aucune métrique inventée (note d'archi
du design). Génériques : affiche les métriques par-doc présentes, quelles
qu'elles soient.
"""

from __future__ import annotations

from collections.abc import Mapping

from cinoc.evaluation.result import RunDocumentResult, RunResult
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized, view_label
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import (
    bar_cell,
    col_max,
    nonempty_metric_indices,
    ordered_unique,
)


class DocumentSection:
    """Détail par-document : une table par vue (document × pipeline × métriques)."""

    name = "by_document"
    requires: tuple[str, ...] = ()  # générique ; absent si aucun détail par-doc

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not result.viewed_documents:
            return None
        # Ordre canonique des moteurs (badge stable) : première apparition dans
        # le run ; repli sur l'ordre des documents si aucun agrégat.
        order = engine_order(p.pipeline for p in result.pipelines) or engine_order(
            d.pipeline for d in result.viewed_documents
        )
        # Titre de vue porté par le héros (renderer) ; ici, les tables par vue.
        views = ordered_unique(d.view for d in result.viewed_documents)
        multi = len(views) > 1
        parts: list[str] = []
        for view_name in views:
            parts.append(
                _table_for_view(
                    result.viewed_documents, view_name, order, ctx.lang, multi=multi
                )
            )
        return Html("\n".join(parts) + "\n")


def _table_for_view(
    documents: tuple[RunDocumentResult, ...],
    view_name: str,
    order: Mapping[str, int],
    lang: str,
    *,
    multi: bool,
) -> str:
    rows = [d for d in documents if d.view == view_name]
    keep = nonempty_metric_indices([d.scores for d in rows])  # masque tout-« — »
    all_metrics = tuple(score.metric for score in rows[0].scores)
    metrics = [all_metrics[i] for i in keep]
    header = "".join(f'<th class="num-cell">{escape(m)}</th>' for m in metrics)
    maxes = [col_max([d.scores for d in rows], i) for i in keep]
    body: list[str] = []
    for doc_id in ordered_unique(d.document_id for d in rows):
        doc_rows = [d for d in rows if d.document_id == doc_id]
        for offset, doc in enumerate(doc_rows):
            label = escape(doc_id) if offset == 0 else ""  # groupé : nom 1×
            cells = "".join(
                bar_cell(doc.scores[i], maxes[j], lang=lang)
                for j, i in enumerate(keep)
            )
            badge = engine_cell(doc.pipeline, order.get(doc.pipeline, 0))
            body.append(
                f'<tr><td class="eng-cell">{label}</td>'
                f'<td class="eng-cell">{badge}</td>{cells}</tr>'
            )
    head = ""
    if multi:  # libellé de vue seulement s'il y a plusieurs vues à distinguer
        view_caption = localized(lang, "Vue", "View")
        head = f"<h2>{view_caption} : {escape(view_label(view_name, lang))}</h2>\n"
    # ``data-paginate`` : toutes les lignes restent présentes (rien retiré) ;
    # ``report.js`` n'affiche qu'une page de lignes à la fois (+ pager). Sans JS,
    # toute la table s'affiche (autonome, imprimable).
    return (
        f"{head}"
        f'<table class="data" data-paginate="50">\n'
        f"<thead><tr><th>Document</th><th>Pipeline</th>{header}</tr></thead>\n"
        f"<tbody>{''.join(body)}</tbody>\n</table>"
    )


__all__ = ["DocumentSection"]
