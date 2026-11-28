"""Section composition du corpus : répartition par **strate** (couche 7).

Rendue **seulement si** le corpus porte des strates (``RunDocumentResult.stratum``,
projeté de ``DocumentRef.metadata["stratum"]``) — sinon ``None`` (pas de fausse
carte, pas de strate inventée). Une ligne par strate : nom, effectif, part + barre
proportionnelle. Server-side, déterministe, zéro JS.
"""

from __future__ import annotations

from collections import Counter

from cinoc.evaluation.result import RunResult
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import ordered_unique


def _strata_by_doc(result: RunResult, view: str) -> dict[str, str]:
    """``document_id -> strate`` (1ʳᵉ occurrence) pour les docs qui en portent une."""
    out: dict[str, str] = {}
    for d in result.viewed_documents:
        if d.view == view and d.stratum and d.document_id not in out:
            out[d.document_id] = d.stratum
    return out


class CorpusCompositionSection:
    """Répartition des documents par strate (effectif + part), si présentes."""

    name = "corpus_composition"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not result.viewed_documents:
            return None
        view = ordered_unique(d.view for d in result.viewed_documents)[0]
        strata = _strata_by_doc(result, view)
        if not strata:
            return None  # aucune strate → pas de carte (jamais de strate inventée)
        counts = Counter(strata.values())
        total = sum(counts.values())
        # Ordre déterministe : effectif décroissant puis nom.
        ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        rows = "".join(
            f'<div class="strata-row"><div class="strata-head">'
            f'<span class="strata-name">{escape(name)}</span>'
            f'<span class="chip">n = {n}</span></div>'
            f'<div class="track"><i '
            f'style="width:{round(n / total * 100)}%;background:var(--fern);'
            f'opacity:0.55"></i></div>'
            f'<span class="strata-pct">{n / total:.0%}</span></div>'
            for name, n in ordered
        )
        title = localized(ctx.lang, "Composition du corpus", "Corpus composition")
        caption = localized(
            ctx.lang,
            f"{len(ordered)} strates · {total} documents "
            "(répartition figée à la création du run).",
            f"{len(ordered)} strata · {total} documents "
            "(distribution fixed at run creation).",
        )
        return Html(
            f"<h2>{title}</h2>\n"
            f'<p class="muted">{caption}</p>\n'
            f'<div class="strata-grid">{rows}</div>\n'
        )


__all__ = ["CorpusCompositionSection"]
