"""Section radar : profil multi-métrique par moteur, superposé (couche 7).

Un seul graphique « toile d'araignée » qui superpose tous les moteurs sur des
axes normalisés « plus loin = meilleur » ([0,1]) — la **forme** de chaque
polygone révèle ses forces/faiblesses d'un coup d'œil. Pure présentation : lit
les scores d'agrégat du ``RunResult`` (aucun recalcul), rendu SVG serveur
déterministe (≠ Chart.js), zéro JS.
"""

from __future__ import annotations

from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import fmt_pct, localize_decimal
from cinoc.reports.engine_badges import engine_accent, engine_letter, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import ordered_unique
from cinoc.reports.svg import radar_chart

#: Axes du radar : (clé métrique, inverser ?, libellé fr, libellé en). Toutes les
#: valeurs sont ramenées à « plus haut = meilleur » dans [0,1] (les métriques
#: d'erreur sont inversées : 1 − valeur). L'axe ``unanchored_trigrams`` inversé
#: EST l'ancrage des trigrammes (1 − part non ancrée) → libellé « Ancrage ».
#: ``fca`` porte son nom, pas « Fidélité » : elle vaut 0 dès que les lignes
#: sont fusionnées (D-288) — un axe « fidélité » à zéro mentirait.
_AXES: tuple[tuple[str, bool, str, str], ...] = (
    ("char_accuracy", False, "Caract.", "Char."),
    ("word_accuracy", False, "Mot", "Word"),
    ("fca", False, "FCA", "FCA"),
    ("bow_f1", False, "F1", "F1"),
    ("searchability", False, "Rappel", "Recall"),
    ("unanchored_trigrams", True, "Ancrage", "Anchoring"),
)


class EngineRadarSection:
    """Radar multi-métrique superposant tous les moteurs (carte autonome)."""

    name = "engine_radar"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not result.pipelines:
            return None
        view = ordered_unique(p.view for p in result.pipelines)[0]
        order = engine_order(p.pipeline for p in result.pipelines)
        pipes = sorted(
            (p for p in result.pipelines if p.view == view),
            key=lambda p: order[p.pipeline],
        )
        if not pipes:
            return None
        scores = {
            p.pipeline: {s.metric: s.value for s in p.aggregate if s.value is not None}
            for p in pipes
        }
        # Axes retenus : ceux présents pour **tous** les moteurs affichés (sinon le
        # polygone n'est pas comparable). Radar utile à partir de 3 axes. Les axes
        # candidats absents pour au moins un moteur sont **signalés** (note de bas),
        # jamais comblés par un zéro silencieux.
        axes = [
            ax for ax in _AXES if all(ax[0] in scores[p.pipeline] for p in pipes)
        ]
        if len(axes) < 3:
            return None
        dropped = [
            (ax[2] if ctx.lang != "en" else ax[3])
            for ax in _AXES
            if ax not in axes and any(ax[0] in scores[p.pipeline] for p in pipes)
        ]
        labels = [ax[2] if ctx.lang != "en" else ax[3] for ax in axes]
        series: list[tuple[str, list[float]]] = []
        accents: list[str] = []
        point_titles: list[list[str]] = []
        for p in pipes:
            values: list[float] = []
            tips: list[str] = []
            for key, invert, fr, en in axes:
                raw = scores[p.pipeline][key]
                norm = 1.0 - raw if invert else raw
                values.append(norm)
                lbl = fr if ctx.lang != "en" else en
                # Infobulle : valeur **brute** (% lisible) ET normalisée (auditables).
                raw_pct = fmt_pct(raw, ctx.lang)
                norm_v = localize_decimal(f"{norm:.2f}", ctx.lang)
                tips.append(f"{lbl} : {raw_pct} (norm. {norm_v})")
            series.append((p.pipeline, values))
            accents.append(engine_accent(order[p.pipeline]))
            point_titles.append(tips)
        aria = localized(
            ctx.lang,
            "Radar des profils moteur (axes normalisés, plus loin = meilleur)",
            "Engine profile radar (normalised axes, further = better)",
        )
        svg = radar_chart(
            labels, series, accents=accents, point_titles=point_titles, aria_label=aria
        )
        if not svg:
            return None
        legend = " · ".join(
            f'<span class="eng-badge" style="--badge:{engine_accent(i)}">'
            f"{engine_letter(i)}</span> {escape(p.pipeline)}"
            for p in pipes
            for i in (order[p.pipeline],)
        )
        title = localized(ctx.lang, "Profil radar", "Radar profile")
        intro = localized(
            ctx.lang,
            "Profil multi-métrique par moteur. Chaque axe est une métrique dans "
            "[0,1] orientée « plus loin = meilleur » (les taux d'erreur sont "
            "inversés : 1 − valeur) ; l'échelle est <strong>absolue</strong> (pas "
            "de min-max relatif), donc un petit écart reste un petit écart. "
            "Survolez un sommet pour la valeur brute et normalisée.",
            "Multi-metric profile per engine. Each axis is a metric in [0,1] "
            "oriented 'further = better' (error rates are inverted: 1 − value); "
            "the scale is <strong>absolute</strong> (no relative min-max), so a "
            "small gap stays a small gap. Hover a vertex for raw and normalised "
            "values.",
        )
        note = ""
        if dropped:
            note = (
                '<p class="muted radar-legend">'
                + localized(
                    ctx.lang,
                    "Dimensions non comparables masquées (absentes pour au moins "
                    "un moteur) : ",
                    "Non-comparable dimensions hidden (missing for at least one "
                    "engine): ",
                )
                + escape(", ".join(dropped))
                + ".</p>\n"
            )
        return Html(
            f"<h2>{title}</h2>\n"
            f'<p class="muted">{intro}</p>\n'
            f'<div class="radar-wrap">{svg}</div>\n'
            f'<p class="muted radar-legend">{legend}</p>\n'
            f"{note}"
        )


__all__ = ["EngineRadarSection"]
