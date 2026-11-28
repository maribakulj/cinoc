"""Section duel par document : graphe haltère du CER par moteur (couche 7).

Une ligne par document, un point par moteur (CER), reliés : pour 2 moteurs c'est
un **duel** (qui gagne où, de combien) ; au-delà, un dot-plot. Trié par **écart
inter-moteurs décroissant** (les documents où les moteurs divergent le plus en
tête) et borné aux N premiers. Pure présentation : lit les CER par document du
``RunResult`` (aucun recalcul), rendu SVG serveur déterministe, zéro JS.
"""

from __future__ import annotations

from cinoc.evaluation.result import RunResult
from cinoc.reports.engine_badges import engine_accent, engine_letter, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import ordered_unique
from cinoc.reports.svg import dumbbell_rows

_METRIC = "cer"
#: Documents affichés (les plus discriminants) — borne la hauteur de la carte.
_MAX_ROWS = 18
#: Libellé document tronqué (l'id complet vit dans la galerie/le drill-in).
_LABEL_CHARS = 11


def _clip(label: str) -> str:
    return label if len(label) <= _LABEL_CHARS else label[: _LABEL_CHARS - 1] + "…"


class EngineDuelSection:
    """Graphe haltère : CER par moteur et document, trié par écart (carte autonome)."""

    name = "engine_duel"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not result.viewed_documents:
            return None
        view = ordered_unique(d.view for d in result.viewed_documents)[0]
        order = engine_order(p.pipeline for p in result.pipelines) or engine_order(
            d.pipeline for d in result.viewed_documents
        )
        present = {
            d.pipeline
            for d in result.viewed_documents
            if d.view == view and d.pipeline in order
        }
        engines = sorted(present, key=lambda n: order[n])
        if len(engines) < 2:
            return None  # un duel suppose au moins deux moteurs
        # {doc: {engine: cer}}
        per_doc: dict[str, dict[str, float]] = {}
        for doc in result.viewed_documents:
            if doc.view != view or doc.pipeline not in order:
                continue
            for score in doc.scores:
                if score.metric == _METRIC and score.value is not None:
                    per_doc.setdefault(doc.document_id, {})[doc.pipeline] = score.value
        # Ne garde que les documents mesurés sur **tous** les moteurs (duel complet).
        complete = {
            doc: vals for doc, vals in per_doc.items()
            if all(e in vals for e in engines)
        }
        if not complete:
            return None
        spread = {
            doc: max(vals[e] for e in engines) - min(vals[e] for e in engines)
            for doc, vals in complete.items()
        }
        # Tri par écart décroissant ; départage par id pour le déterminisme.
        ranked = sorted(complete, key=lambda d: (-spread[d], d))[:_MAX_ROWS]
        scale_max = max(max(complete[d][e] for e in engines) for d in ranked) or 1.0
        rows = [
            (_clip(doc), [(complete[doc][e], engine_accent(order[e])) for e in engines])
            for doc in ranked
        ]
        svg = dumbbell_rows(rows, scale_max=scale_max)
        legend = " · ".join(
            f'<span class="eng-badge" style="--badge:{engine_accent(order[e])}">'
            f"{engine_letter(order[e])}</span> {escape(e)}"
            for e in engines
        )
        title = localized(ctx.lang, "Duel par document", "Per-document duel")
        intro = localized(
            ctx.lang,
            f"CER par moteur sur chaque document, reliés — les {len(ranked)} "
            "documents où les moteurs <strong>divergent le plus</strong> (écart "
            f"décroissant). Échelle commune (max {scale_max * 100:.0f} %).",
            f"CER per engine on each document, linked — the {len(ranked)} documents "
            "where engines <strong>diverge most</strong> (decreasing gap). Common "
            f"scale (max {scale_max * 100:.0f} %).",
        )
        return Html(
            f"<h2>{title}</h2>\n"
            f'<p class="muted">{intro}</p>\n'
            f'<div class="dumb-wrap">{svg}</div>\n'
            f'<p class="muted dumb-legend">{legend}</p>\n'
        )


__all__ = ["EngineDuelSection"]
