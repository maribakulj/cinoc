"""Section profil moteur : panneaux **drill-in** par moteur (couche 7).

Pour chaque moteur, un panneau **caché** (révélé au clic d'une ligne du tableau
de classement, ancre ``#engine-<idx>``) : bande KPI (CER/WER/… de l'agrégat,
ECE si calibration) + **CER par document** trié (barres SVG). Enrichissement
progressif : sans JS, le panneau s'affiche via ``:target`` ; ``report.js`` le
révèle en masquant les autres (← retour, précédent/suivant). Server-side,
déterministe, zéro donnée reconstruite. Réutilise les builders SVG (U2).
"""

from __future__ import annotations

from cinoc.evaluation.analysis import CalibrationPayload, TaxonomyPayload
from cinoc.evaluation.result import PipelineResult, RunResult
from cinoc.reports._binning import histogram
from cinoc.reports._numbers import fmt_pct
from cinoc.reports.engine_badges import engine_accent, engine_letter, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import ordered_unique
from cinoc.reports.sections.composition import settings_html
from cinoc.reports.sections.taxonomy import composition_html
from cinoc.reports.svg import bar_series, calibration_curve

_METRIC = "cer"
#: Classes de l'histogramme de CER par document (constant → graphe borné, même
#: forme que le moteur ait été évalué sur 20 ou 6000 documents).
_N_BINS = 24


def _per_doc_cer(result: RunResult, pipeline: str, view: str) -> list[float]:
    return [
        score.value
        for doc in result.documents
        if doc.pipeline == pipeline and doc.view == view
        for score in doc.scores
        if score.metric == _METRIC and score.value is not None
    ]


def _calibration(
    result: RunResult, view: str, pipeline: str
) -> tuple[float, str] | None:
    """(ECE, courbe SVG) du moteur si calibration présente, sinon ``None``."""
    for analysis in result.analyses:
        payload = analysis.payload
        if analysis.view == view and isinstance(payload, CalibrationPayload):
            for row in payload.pipelines:
                if row.pipeline == pipeline:
                    curve = calibration_curve(
                        [(b.mean_confidence, b.accuracy) for b in row.bins],
                        accent="var(--fern)",
                    )
                    return row.ece, curve
    return None


def _composition(result: RunResult, view: str, pipeline: str, lang: str) -> str:
    """Composition d'erreurs du moteur (réutilise ``taxonomy.composition_html``)."""
    for analysis in result.analyses:
        payload = analysis.payload
        if analysis.view == view and isinstance(payload, TaxonomyPayload):
            for row in payload.pipelines:
                if row.pipeline == pipeline:
                    return composition_html(payload.classes, row, lang)
    return ""


def _kpi(label: str, value: str) -> str:
    return (
        f'<div class="kpi"><div class="kpi-k">{escape(label)}</div>'
        f'<div class="kpi-v">{escape(value)}</div></div>'
    )


def _pct(v: float, lang: str) -> str:
    return fmt_pct(v, lang)


def _config_block(result: RunResult, name: str, lang: str) -> str:
    """Config repliable (reproductibilité) : étapes du pipeline + adapter + version
    déclarée + paramètres, depuis le ``RunManifest``. ``<details>`` natif (zéro JS,
    imprimable). Omise si le manifeste ne porte pas la spec (ex. données de démo).

    « Paramètres » = les réglages **effectifs** du module (``adapter_kwargs`` du
    manifeste, même lecture que la composition des chaînes), puis ceux de
    l'étape. Ne lire que ``step.params`` affichait « — » à côté d'une
    composition qui montrait ``lang``, ``model``, ``prompt`` (pilote D-281, D12).
    """
    spec = next(
        (s for s in result.manifest.pipeline_specs if s.name == name), None
    )
    if spec is None or not spec.steps:
        return ""
    versions = result.manifest.module_versions
    kwargs = result.manifest.adapter_kwargs
    body = ""
    for step in spec.steps:
        ver = escape(versions.get(step.adapter_name, "—"))
        reglages = [
            settings_html(kwargs.get(step.adapter_name) or {}),
            settings_html(step.params),
        ]
        params = " · ".join(r for r in reglages if r) or "—"
        body += (
            f'<tr><td class="lbl">{escape(step.kind)}</td>'
            f'<td class="lbl">{escape(step.adapter_name)}</td>'
            f'<td class="disp">{ver}</td><td class="lbl">{params}</td></tr>'
        )
    summ = localized(lang, "Configuration & reproductibilité", "Configuration")
    th_s = localized(lang, "Étape", "Step")
    th_a = localized(lang, "Adapter", "Adapter")
    th_v = localized(lang, "Version", "Version")
    th_p = localized(lang, "Paramètres", "Parameters")
    return (
        f'<details><summary class="muted">{summ}</summary>\n'
        f'<table class="data compact"><thead><tr><th>{th_s}</th><th>{th_a}</th>'
        f'<th class="num-cell">{th_v}</th><th>{th_p}</th></tr></thead>'
        f"<tbody>{body}</tbody></table></details>"
    )


def _stratum_block(result: RunResult, name: str, view: str, lang: str) -> str:
    """CER moyen par strate (macro-moyenne) — révèle forces/faiblesses du moteur
    selon le sous-corpus. Rendu seulement si ≥ 2 strates portent des documents
    notés (jamais une strate inventée). Trié du meilleur au pire."""
    buckets: dict[str, list[float]] = {}
    for d in result.documents:
        if d.pipeline != name or d.view != view or not d.stratum:
            continue
        cer = next(
            (s.value for s in d.scores if s.metric == "cer" and s.value is not None),
            None,
        )
        if cer is not None:
            buckets.setdefault(d.stratum, []).append(cer)
    if len(buckets) < 2:
        return ""
    rows_data = sorted(
        ((s, sum(v) / len(v), len(v)) for s, v in buckets.items()),
        key=lambda r: r[1],
    )
    rows = "".join(
        f'<tr><td class="lbl">{escape(s)}</td><td class="disp">{n}</td>'
        f'<td class="disp">{_pct(m, lang)}</td></tr>'
        for s, m, n in rows_data
    )
    cap = localized(lang, "Performance par strate", "Performance by stratum")
    th_n = localized(lang, "n", "n")
    th_c = localized(lang, "CER moyen ↓", "Mean CER ↓")
    th_s = localized(lang, "Strate", "Stratum")
    return (
        f'<div class="prof-cell"><div class="drill-caption">{cap}</div>'
        f'<table class="data compact"><thead><tr><th>{th_s}</th>'
        f'<th class="num-cell">{th_n}</th><th class="num-cell">{th_c}</th></tr>'
        f"</thead><tbody>{rows}</tbody></table></div>"
    )


class EngineProfileSection:
    """Panneaux profil par moteur (KPIs + CER/document), révélés au clic."""

    name = "engine_profiles"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not result.pipelines:
            return None
        view = ordered_unique(p.view for p in result.pipelines)[0]
        order = engine_order(p.pipeline for p in result.pipelines)
        view_pipes = {p.pipeline: p for p in result.pipelines if p.view == view}
        engines = [n for n in sorted(order, key=lambda n: order[n]) if n in view_pipes]
        if not engines:
            return None
        panels = "".join(
            self._panel(result, view, name, order, engines, pos, ctx.lang)
            for pos, name in enumerate(engines)
        )
        # Section **détail** (vue page d'un moteur) : pas d'en-tête « cliquer un
        # moteur… » (le maître = le tableau de classement est la liste cliquable ;
        # le routeur échange maître↔détail). Chaque panneau porte son fil d'Ariane.
        return Html(f'<div class="eng-profiles">{panels}</div>\n')

    def _panel(
        self,
        result: RunResult,
        view: str,
        name: str,
        order: dict[str, int],
        engines: list[str],
        pos: int,
        lang: str,
    ) -> str:
        idx = order[name]
        pipe: PipelineResult = next(
            p for p in result.pipelines if p.view == view and p.pipeline == name
        )
        total = len(engines)
        prev_idx = order[engines[(pos - 1) % total]]
        next_idx = order[engines[(pos + 1) % total]]
        # KPIs : métriques d'agrégat (réelles) + ECE si calibration présente.
        kpis = [
            _kpi(s.metric, _pct(s.value, lang))
            for s in result.principal_aggregate(pipe)
            if s.value is not None
        ]
        cal = _calibration(result, view, name)
        if cal is not None:
            kpis.append(_kpi("ece", _pct(cal[0], lang)))
        cer_vals = _per_doc_cer(result, name, view)
        chart_caption = localized(
            lang,
            f'<span class="muted">· distribution sur {len(cer_vals)} docs '
            f"({_N_BINS} classes, gauche = faible CER)</span>",
            f'<span class="muted">· distribution over {len(cer_vals)} docs '
            f"({_N_BINS} bins, left = low CER)</span>",
        )
        chart = (
            '<div class="prof-chart"><div class="drill-caption">'
            + localized(lang, "CER par document ", "CER per document ")
            + f"{chart_caption}</div>"
            f"{bar_series(histogram(cer_vals, _N_BINS), accent=engine_accent(idx))}"
            "</div>"
            if cer_vals
            else ""
        )
        # Calibration + composition du moteur (réutilise les builders U2b/U2c),
        # en 2 colonnes ; chaque bloc n'apparaît que si sa donnée est présente.
        cal_block = (
            '<div class="prof-cell"><div class="drill-caption">'
            + localized(lang, "Courbe de calibration", "Calibration curve")
            + f"</div>{cal[1]}</div>"
            if cal is not None
            else ""
        )
        comp = _composition(result, view, name, lang)
        comp_block = (
            '<div class="prof-cell"><div class="drill-caption">'
            + localized(lang, "Composition des erreurs", "Error composition")
            + f"</div>{comp}</div>"
            if comp
            else ""
        )
        strat_block = _stratum_block(result, name, view, lang)
        extras = (
            f'<div class="prof-row">{strat_block}{cal_block}{comp_block}</div>'
            if (strat_block or cal_block or comp_block)
            else ""
        )
        config = _config_block(result, name, lang)
        back_label = localized(lang, "← Tous les moteurs", "← All engines")
        prev_label = localized(lang, "← précédent", "← previous")
        next_label = localized(lang, "suivant →", "next →")
        pos_label = localized(
            lang,
            f"moteur {pos + 1} sur {total}",
            f"engine {pos + 1} of {total}",
        )
        return (
            f'<div class="drill-panel eng-profile" id="engine-{idx}" hidden '
            f'role="region" aria-label="{escape(name)}">'
            '<div class="drill-head">'
            f'<a class="drill-back" href="#">{back_label}</a>'
            '<div class="drill-nav">'
            f'<a class="btn-sm" href="#engine-{prev_idx}">{prev_label}</a>'
            f'<a class="btn-sm" href="#engine-{next_idx}">{next_label}</a></div></div>'
            f'<div class="drill-title"><span class="eng-badge" '
            f'style="--badge:{engine_accent(idx)}">{engine_letter(idx)}</span>'
            f"<span>{escape(name)}</span>"
            f'<span class="muted drill-pos">{pos_label}</span></div>'
            f'<div class="kpi-band">{"".join(kpis)}</div>'
            f"{chart}{extras}{config}</div>"
        )


__all__ = ["EngineProfileSection"]
