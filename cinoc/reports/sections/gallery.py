"""Section **galerie** des documents (couche 7) — présentation visuelle au design.

≠ la table ``by_document`` (détail dense) : une **carte par document** avec un
**aperçu de page synthétique** (lignes monochromes sur ``--paper``, dans la charte
du rapport — pas de placeholder coloré, le travers évité), l'identifiant, et le
**CER de chaque moteur** via les badges A→E (le meilleur du document surligné en
``--fern``). 100 % données déjà présentes (``RunResult.documents``), **zéro image**,
autonome. Server-side, déterministe.
"""

from __future__ import annotations

from cinoc.evaluation.result import MetricScore, RunResult
from cinoc.reports._anomaly import ANOMALY_LABELS, ANOMALY_ORDER, compute_anomalies
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_accent, engine_letter, engine_order
from cinoc.reports.html import escape, localized, view_label
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import ordered_unique


def _cer(scores: tuple[MetricScore, ...]) -> float | None:
    for score in scores:
        if score.metric == "cer":
            return score.value
    return None


def _row(
    pipeline: str, cer: float | None, index: int, lang: str, *, best: bool
) -> str:
    value = "—" if cer is None else localize_decimal(f"{cer:.4f}", lang)
    cls = "dc-row best" if best else "dc-row"
    return (
        f'<div class="{cls}">'
        f'<span class="eng-badge" style="--badge:{engine_accent(index)}">'
        f"{engine_letter(index)}</span>"
        f'<span class="dc-name">{escape(pipeline)}</span>'
        f'<span class="dc-cer">{value}</span></div>'
    )


def _card(
    doc_id: str,
    entries: list[tuple[str, float | None]],
    order: dict[str, int],
    idx: int,
    thumb: str | None,
    stratum: str | None = None,
    anomalies: frozenset[str] = frozenset(),
    *,
    lang: str,
) -> str:
    scored = [c for _, c in entries if c is not None]
    best = min(scored) if scored else None
    rows = "".join(
        _row(
            pipeline,
            cer,
            order.get(pipeline, 0),
            lang,
            best=cer is not None and cer == best,
        )
        for pipeline, cer in sorted(
            entries, key=lambda e: (e[1] is None, e[1] or 0.0, e[0])
        )
    )
    # Vignette réelle si résolue (intrant de rendu), sinon aperçu synthétique.
    preview = (
        f'<div class="doc-preview doc-preview-img"><img src="{escape(thumb)}" '
        f'alt="" loading="lazy" decoding="async"></div>'
        if thumb
        else '<div class="doc-preview" aria-hidden="true"></div>'
    )
    # Carte = lien drill-in vers le détail du document (ancre #doc-<idx>). Le
    # ``data-stratum`` et ``data-anom`` (verbatim/triés, échappés) servent aux
    # filtres client (strate · anomalie) qui **composent** ; absent → "".
    strat_attr = f' data-stratum="{escape(stratum)}"' if stratum else ' data-stratum=""'
    anom = " ".join(t for t in ANOMALY_ORDER if t in anomalies)
    anom_attr = f' data-anom="{anom}"'
    # Pastille « ⚑ » discrète si le document porte ≥ 1 anomalie (repère visuel).
    mark = '<span class="dc-anom" aria-hidden="true">⚑</span>' if anom else ""
    return (
        f'<a class="doc-card" href="#doc-{idx}"{strat_attr}{anom_attr}>{preview}'
        f'<div class="dc-id">{escape(doc_id)}{mark}</div>'
        f'<div class="dc-rows">{rows}</div></a>'
    )


class DocumentGallerySection:
    """Galerie visuelle : une carte par document (aperçu synthétique + CER/badges)."""

    name = "documents_gallery"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not result.viewed_documents:
            return None
        views = ordered_unique(d.view for d in result.viewed_documents)
        view = views[0]
        multi = len(views) > 1
        rows = [d for d in result.viewed_documents if d.view == view]
        # Ordre canonique des moteurs (badge stable, partagé avec les autres sections).
        order = engine_order(p.pipeline for p in result.pipelines) or engine_order(
            d.pipeline for d in rows
        )
        # Strate par document (verbatim ; None si le corpus n'en porte pas).
        strata = {
            d.document_id: d.stratum for d in rows if d.stratum is not None
        }
        # Anomalies par document (signaux factuels, cutoffs P90 du run) — triage.
        anomalies, cutoffs = compute_anomalies(result, view)
        cards = "".join(
            _card(
                doc_id,
                [(d.pipeline, _cer(d.scores)) for d in rows if d.document_id == doc_id],
                order,
                idx,
                ctx.images.get(doc_id),
                strata.get(doc_id),
                frozenset(anomalies.get(doc_id, set())),
                lang=ctx.lang,
            )
            for idx, doc_id in enumerate(ordered_unique(d.document_id for d in rows))
        )
        # Filtre par strate : chips seulement si ≥2 strates réellement présentes
        # (jamais une catégorie inventée). Sans JS, tout reste visible.
        present = ordered_unique(s for s in strata.values())
        filt = self._filter(present, ctx.lang) if len(present) >= 2 else ""
        # Filtre par anomalie : un type présent dès qu'≥ 1 doc le porte. Compose
        # avec la strate (filtres client indépendants). + critère affiché.
        present_anom = [
            t for t in ANOMALY_ORDER if any(t in v for v in anomalies.values())
        ]
        filt += self._anomaly_filter(present_anom, cutoffs, ctx.lang)
        vlbl = escape(view_label(view, ctx.lang))
        title = localized(
            ctx.lang,
            f"Galerie des documents{f' (vue : {vlbl})' if multi else ''}",
            f"Document gallery{f' (view: {vlbl})' if multi else ''}",
        )
        caption = localized(
            ctx.lang,
            "Aperçu + CER par moteur "
            "(pastille de couleur ; meilleur du document surligné).",
            "Preview + CER per engine "
            "(colour dot; best of the document highlighted).",
        )
        return Html(
            f"<h2>{title}</h2>\n"
            f'<p class="muted">{caption}</p>\n'
            f"{filt}"
            # ``data-paginate`` : toutes les cartes restent présentes (rien retiré) ;
            # ``report.js`` n'en affiche qu'une page à la fois (+ pager). Sans JS,
            # tout s'affiche (autonome). Compose avec le filtre par strate.
            f'<div class="doc-grid" data-paginate="60">{cards}</div>\n'
        )

    def _filter(self, strata: tuple[str, ...], lang: str) -> str:
        """Rangée de chips de filtre par strate (réutilise la pilule segmentée).

        Bouton « Toutes » (``data-stratum="*"``) + un bouton par strate présente
        (libellé verbatim). ``report.js`` masque les cartes hors strate ; sans JS,
        les boutons sont inertes et toutes les cartes restent visibles."""
        all_lbl = localized(lang, "Toutes", "All")
        aria = localized(lang, "Filtrer par strate", "Filter by stratum")
        chips = (
            '<button type="button" class="df-btn on" data-stratum="*" '
            f'aria-pressed="true">{all_lbl}</button>'
        )
        for s in strata:
            chips += (
                f'<button type="button" class="df-btn" data-stratum="{escape(s)}" '
                f'aria-pressed="false">{escape(s)}</button>'
            )
        return (
            '<div class="doc-filter" role="group" data-facet="stratum" '
            f'aria-label="{aria}">{chips}</div>'
        )

    def _anomaly_filter(
        self, present: list[str], cutoffs: dict[str, float], lang: str
    ) -> str:
        """Rangée de chips de filtre par **type d'anomalie** (composent avec la
        strate) + **légende du critère** (cutoff P90 affiché → auditable).

        Rendue seulement si ≥ 1 type présent. ``data-facet="anom"`` : le filtre
        client lit la **liste** ``data-anom`` de chaque carte (appartenance)."""
        if not present:
            return ""
        all_lbl = localized(lang, "Toutes", "All")
        aria = localized(lang, "Filtrer par anomalie", "Filter by anomaly")
        chips = (
            '<button type="button" class="df-btn on" data-anom="*" '
            f'aria-pressed="true">{all_lbl}</button>'
        )
        for t in present:
            label = ANOMALY_LABELS[t][1 if lang == "en" else 0]
            chips += (
                f'<button type="button" class="df-btn" data-anom="{t}" '
                f'aria-pressed="false">⚑ {escape(label)}</button>'
            )
        legend = self._anomaly_legend(present, cutoffs, lang)
        return (
            '<div class="doc-filter" role="group" data-facet="anom" '
            f'aria-label="{aria}">{chips}</div>{legend}'
        )

    @staticmethod
    def _anomaly_legend(
        present: list[str], cutoffs: dict[str, float], lang: str
    ) -> str:
        """Critère **exact** de chaque facette présente (cutoff = P90 observé)."""
        cc = localize_decimal(f"P90 ({cutoffs.get('cer', 0):.3f})", lang)
        uc = localize_decimal(f"P90 ({cutoffs.get('unanchored', 0):.3f})", lang)
        dc = localize_decimal(f"P90 ({cutoffs.get('disagree', 0):.3f})", lang)
        rule = {
            "cer": localized(
                lang, f"CER d'un moteur ≥ {cc}", f"an engine's CER ≥ {cc}"
            ),
            "unanchored": localized(
                lang,
                f"texte non ancré d'un moteur ≥ {uc}",
                f"an engine's unanchored text ≥ {uc}",
            ),
            "disagree": localized(
                lang,
                f"écart CER max−min entre moteurs ≥ {dc}",
                f"max−min CER across engines ≥ {dc}",
            ),
            "inserted": localized(
                lang,
                "≥ 1 bloc inséré sans contrepartie dans le GT",
                "≥ 1 block inserted with no GT counterpart",
            ),
        }
        items = " · ".join(
            f"<strong>{escape(ANOMALY_LABELS[t][1 if lang == 'en' else 0])}</strong> : "
            f"{rule[t]}"
            for t in present
        )
        head = localized(
            lang,
            "⚑ Anomalies (seuils relatifs au run, P90 de la distribution observée) — ",
            "⚑ Anomalies (run-relative cutoffs, P90 of the observed distribution) — ",
        )
        return f'<p class="muted anom-legend">{head}{items}.</p>\n'


__all__ = ["DocumentGallerySection"]
