"""Section Mesures clés : **socle chiffré neutre** par vue (couche 7).

Le **headline** du rapport : les scores des métriques **établies** de la vue
(CER, WER, cMER… — D-289 : seules celles-là sont classées et testées ; les
adaptées et les exploratoires sont au diagnostic) et la **durée par page**
(D-281, D11 : un moteur 25 fois plus lent ne se lisait qu'au mode détaillé),
par moteur, en table **triable** (colonnes annotées du sens de lecture ↓/↑), un
**dot plot classé** du CER avec **IC 95 % bootstrap** du CER micro affiché
(calculé en couche evaluation — montre l'écart *et* son incertitude), et le
**résultat du test** inter-moteurs comme **fait** : Wilcoxon (2 moteurs) ou
Friedman (≥ 3), p brute et p corrigée de Holm, puis les paires que Nemenyi
sépare quand le Friedman est rejeté — ou le motif pour lequel le test n'a pas
été calculé.

**Aucun verdict** : pas de « meilleur » déclaré, pas de recommandation. On trie
par une valeur mesurée, on affiche un fait statistique — l'utilisateur interprète
(remplace l'ancienne « Synthèse » qui nommait un gagnant ; cf. moteur narratif
supprimé §6, anti-hallucination §12). Gatée sur ``cer``.
"""

from __future__ import annotations

from dataclasses import dataclass

from cinoc.evaluation.analysis import InferencePayload
from cinoc.evaluation.result import (
    DocumentUsage,
    MetricScore,
    PipelineResult,
    RunResult,
)
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.composition_diff import homonym_hints
from cinoc.reports.engine_badges import (
    engine_accent,
    engine_cell,
    engine_letter,
    engine_order,
)
from cinoc.reports.html import escape, localized, view_label
from cinoc.reports.metric_categories import higher_is_better, is_established
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._inference_text import (
    exploratory_label,
    omnibus_label,
    p_text,
    posthoc_text,
    reason_text,
)
from cinoc.reports.sections._profile_text import convention_html
from cinoc.reports.sections._tables import coverage, is_displayed, ordered_unique
from cinoc.reports.svg import dot_plot_ci

_PRIMARY = "cer"
#: Libellé d'en-tête d'une métrique établie (le nom en capitales sinon).
_LABELS: dict[str, str] = {"cmer": "cMER"}


def _label(metric: str) -> str:
    return _LABELS.get(metric, metric.upper())


@dataclass(frozen=True)
class _Durations:
    """Durées par page d'un pipeline : toutes, et séparées selon leur source."""

    all: float
    measured: tuple[float, ...]
    resumed: tuple[float, ...]


def _seconds_per_page(usage: tuple[DocumentUsage, ...]) -> dict[str, _Durations]:
    """Durée par page de chaque pipeline : Σ durées / n unités.

    Sur les unités **produites** dont la durée est mesurée : une unité en
    échec n'a rien mesuré, et la compter ferait passer une page perdue pour
    une page rapide. Wall-clock de l'exécuteur, une fois par (pipeline ×
    document) — les vues n'ont pas de coût propre. Une unité **reprise** de
    l'archive garde la durée de sa première exécution : séparée de celles que
    ce run a mesurées (D10).
    """
    measured: dict[str, list[float]] = {}
    resumed: dict[str, list[float]] = {}
    for unit in usage:
        duration = unit.usage.duration_seconds
        if unit.outcome != "failed" and duration is not None:
            (resumed if unit.resumed else measured).setdefault(
                unit.pipeline, []
            ).append(duration)
    names = sorted(set(measured) | set(resumed))
    out: dict[str, _Durations] = {}
    for name in names:
        values = (*measured.get(name, ()), *resumed.get(name, ()))
        out[name] = _Durations(
            all=sum(values) / len(values),
            measured=tuple(measured.get(name, ())),
            resumed=tuple(resumed.get(name, ())),
        )
    return out


def _score(pipeline: PipelineResult, metric: str) -> MetricScore | None:
    return next((s for s in pipeline.aggregate if s.metric == metric), None)


def _val(pipeline: PipelineResult, metric: str) -> float | None:
    score = _score(pipeline, metric)
    return score.value if score is not None else None


def _inference(result: RunResult, view: str) -> InferencePayload | None:
    for analysis in result.analyses:
        payload = analysis.payload
        if (
            analysis.view == view
            and isinstance(payload, InferencePayload)
            and payload.metric == _PRIMARY
        ):
            return payload
    return None


class KeyMeasuresSection:
    """Scores standard par moteur (triables) + dot plot CER (IC 95 %) + test."""

    name = "key_measures"
    requires: tuple[str, ...] = (_PRIMARY,)

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        if not any(_val(p, _PRIMARY) is not None for p in result.pipelines):
            return None  # gatée sur le CER (cf. ``requires``)
        order = engine_order(p.pipeline for p in result.pipelines)
        lang = ctx.lang
        views = ordered_unique(p.view for p in result.pipelines)
        multi = len(views) > 1
        specs = {v.name: v for v in result.manifest.view_specs}
        durations = _seconds_per_page(result.usage)
        blocks: list[str] = []
        for view in views:
            pipes = [p for p in result.pipelines if p.view == view]
            # Les établies seules (D-289), dans l'ordre de la vue.
            cols = [
                s.metric
                for s in pipes[0].aggregate
                if is_established(s.metric)
                and is_displayed(s.metric)
                and any(_val(p, s.metric) is not None for p in pipes)
            ]
            if not cols:
                continue
            head = ""
            if multi:
                head = f"<h3>{escape(view_label(view, lang))}</h3>\n"
            # La convention à côté du chiffre (D-285) : un CER ne se lit pas
            # sans sa normalisation.
            spec = specs.get(view)
            if spec is not None:
                head += convention_html(spec, lang)
            blocks.append(
                head
                + self._table(
                    pipes, cols, durations, order, lang,
                    homonym_hints(result.manifest),
                )
                + self._dotplot(result, view, order, lang)
                + self._significance(
                    result, view, lang, view_label(view, lang) if multi else None
                )
            )
        if not blocks:
            return None
        title = localized(lang, "Mesures clés", "Key measures")
        par_vue = (
            localized(
                lang,
                " Chaque vue a son test : un verdict ne vaut que pour sa vue "
                "(sa normalisation, ses unités).",
                " Each view has its own test: a verdict holds for its view only "
                "(its normalisation, its units).",
            )
            if multi
            else ""
        )
        time_fr = " — et durée par page" if durations else ""
        time_en = " — and duration per page" if durations else ""
        caption = localized(
            lang,
            "Scores des métriques <strong>établies</strong> par moteur — les "
            "seules classées et testées ; les métriques adaptées et "
            f"exploratoires sont au diagnostic (« Comparaison »){time_fr} "
            "(↓ = plus bas est meilleur · ↑ = plus haut est meilleur). "
            "<strong>Triez</strong> par n'importe quelle colonne. Aucun gagnant "
            "n'est déclaré : les chiffres et le test sont fournis, "
            f"l'interprétation vous revient.{par_vue}",
            "Scores of the <strong>established</strong> metrics per engine — the "
            "only ones ranked and tested; adapted and exploratory metrics are "
            f"diagnostic (“Engine comparison”){time_en} (↓ = lower is better · "
            "↑ = higher is better). <strong>Sort</strong> by any column. No "
            "winner is declared: figures and the test are provided; "
            f"interpretation is yours.{par_vue}",
        )
        return Html(
            f"<h2>{title}</h2>\n<p class=\"muted\">{caption}</p>\n"
            + "".join(blocks)
            + _duration_note(durations, lang)
        )

    @staticmethod
    def _table(
        pipes: list[PipelineResult],
        cols: list[str],
        durations: dict[str, _Durations],
        order: dict[str, int],
        lang: str,
        hints: dict[str, str],
    ) -> str:
        th_engine = localized(lang, "Moteur", "Engine")
        headers = "".join(
            f'<th class="num-cell sortable" aria-sort="none">'
            f'{escape(_label(m))} {"↑" if higher_is_better(m) else "↓"}</th>'
            for m in cols
        )
        if durations:
            tip = localized(
                lang,
                "Durée par page : Σ durées wall-clock des unités "
                "produites / leur nombre (une unité en échec n'est pas comptée).",
                "Duration per page: Σ wall-clock durations of the units "
                "produced / their number (a failed unit is not counted).",
            )
            headers += (
                f'<th class="num-cell sortable" aria-sort="none" '
                f'title="{escape(tip)}">{localized(lang, "s/page", "s/page")} '
                "↓</th>"
            )
        ranked = sorted(
            pipes,
            key=lambda p: (
                _val(p, _PRIMARY) is None,
                _val(p, _PRIMARY) if _val(p, _PRIMARY) is not None else 0.0,
                p.pipeline,
            ),
        )
        body: list[str] = []
        for p in ranked:
            cells = ""
            for m in cols:
                score = _score(p, m)
                v = score.value if score is not None else None
                cov = coverage(score, lang) if score is not None else ""
                if v is None:
                    cells += f'<td class="disp muted">—{cov}</td>'
                else:
                    disp = localize_decimal(f"{v:.4f}", lang)
                    cells += (
                        f'<td class="disp" data-sort="{v:.6f}">{disp}{cov}</td>'
                    )
            if durations:
                timing = durations.get(p.pipeline)
                if timing is None:
                    cells += '<td class="disp muted">—</td>'
                else:
                    seconds = timing.all
                    disp = localize_decimal(f"{seconds:.1f}", lang)
                    # ↺ : au moins une durée relue de l'archive (note dessous).
                    mark = " ↺" if timing.resumed else ""
                    cells += (
                        f'<td class="disp" data-sort="{seconds:.6f}">'
                        f"{disp}{mark}</td>"
                    )
            badge = engine_cell(
                p.pipeline, order.get(p.pipeline, 0), hints.get(p.pipeline, "")
            )
            body.append(f'<tr><td class="eng-cell">{badge}</td>{cells}</tr>')
        return (
            '<table class="data sortable">\n<thead><tr>'
            f"<th>{th_engine}</th>{headers}</tr></thead>\n"
            f"<tbody>{''.join(body)}</tbody>\n</table>\n"
        )

    @staticmethod
    def _dotplot(
        result: RunResult, view: str, order: dict[str, int], lang: str
    ) -> str:
        payload = _inference(result, view)
        if payload is None or not payload.intervals:
            return ""
        items = sorted(payload.intervals, key=lambda it: (it.value, it.pipeline))
        rows = [
            (
                engine_letter(order.get(it.pipeline, 0)),
                engine_accent(order.get(it.pipeline, 0)),
                it.value,
                it.lower,
                it.upper,
            )
            for it in items
        ]
        scale_max = max(it.upper for it in items)
        # IC **marginal** : chaque moteur sur ses propres documents notés — un
        # moteur qui a perdu une unité a un n plus petit, et on le montre.
        ns = sorted({it.n_documents for it in items})
        n = f"{ns[0]}–{ns[-1]}" if len(ns) > 1 else str(ns[0])
        cap = localized(
            lang,
            f'<span class="muted">CER par moteur — point = CER du tableau (micro : '
            f"Σ erreurs / Σ caractères de référence), barre = son IC 95 % "
            f"(bootstrap des documents, n={n}), trié par CER croissant, "
            f"axe commun.</span>",
            f'<span class="muted">CER per engine — dot = the table’s CER (micro: '
            f"Σ errors / Σ reference characters), bar = its 95% CI "
            f"(document bootstrap, n={n}), sorted by CER, shared axis.</span>",
        )
        return (
            f'<div class="prof-chart"><div class="drill-caption">{cap}</div>'
            f"{dot_plot_ci(rows, scale_max)}</div>\n"
        )

    @staticmethod
    def _significance(
        result: RunResult, view: str, lang: str, label: str | None = None
    ) -> str:
        """Le test de la métrique principale, tel que le payload le dit.

        Toujours une phrase : le test et ses p (brute, corrigée), le post-hoc
        s'il a eu lieu — ou le motif pour lequel rien n'a été calculé.
        ``label`` (plusieurs vues) : la vue que le test juge, nommée à côté du
        résultat — un test peut donner une p basse dans une vue et haute dans
        une autre (S34b).
        """
        if label is None:
            head = localized(
                lang,
                "<strong>Test inter-moteurs (CER)</strong> — ",
                "<strong>Inter-engine test (CER)</strong> — ",
            )
        else:
            head = localized(
                lang,
                f"<strong>Test inter-moteurs (CER, vue « {escape(label)} »)"
                "</strong> — ",
                f"<strong>Inter-engine test (CER, “{escape(label)}” view)"
                "</strong> — ",
            )
        payload = _inference(result, view)
        if payload is None:
            txt = localized(lang, "test non calculé.", "test not computed.")
            return f'<p class="muted">{head}{txt}</p>\n'
        if payload.test is None or payload.p_value is None or payload.p_holm is None:
            txt = localized(
                lang,
                f"test non calculé : {escape(reason_text(payload, lang))}.",
                f"test not computed: {escape(reason_text(payload, lang))}.",
            )
            return f'<p class="muted">{head}{txt}</p>\n'
        status = exploratory_label(lang)
        k = len(payload.mean_ranks)
        between = localized(
            lang,
            "entre les deux moteurs" if k == 2 else f"entre les {k} moteurs",
            "between the two engines" if k == 2 else f"between the {k} engines",
        )
        raw, holm = p_text(payload.p_value, lang), p_text(payload.p_holm, lang)
        m = payload.family_size
        txt = localized(
            lang,
            f"{escape(omnibus_label(payload, lang))} : p = {raw}, corrigée de "
            f"Holm sur {m} test(s) : {holm} → résultat ({status}) {between} "
            f"({payload.n_documents} cas complets).",
            f"{escape(omnibus_label(payload, lang))}: p = {raw}, Holm-corrected "
            f"over {m} test(s): {holm} → result ({status}) {between} "
            f"({payload.n_documents} complete cases).",
        )
        posthoc = posthoc_text(payload, lang) if payload.test == "friedman" else ""
        tail = f" {posthoc}" if posthoc else ""
        return f'<p class="muted">{head}{txt}{tail}</p>\n'


def _mean(values: tuple[float, ...], lang: str) -> str:
    return localize_decimal(f"{sum(values) / len(values):.1f}", lang)


def _duration_note(durations: dict[str, _Durations], lang: str) -> str:
    """Ce que ce run a mesuré, séparé de ce qu'il a relu de l'archive (D10).

    Une unité reprise (``--resume-dir``) garde la durée de sa première
    exécution — 114,6 s mesurées sous contention donnaient « 244,6 pages/h »
    au pilote (D-281). Le ``RunResult`` dit lesquelles (``resumed``) : leur
    cellule est marquée ↺, et la note donne, par pipeline, les deux moyennes.
    """
    split = {name: d for name, d in sorted(durations.items()) if d.resumed}
    if not split:
        return ""
    if not any(d.measured for d in durations.values()):
        head = localized(
            lang,
            "Durées ↺ : toutes les unités sont relues de l'archive — aucune durée "
            "n'est mesurée par ce run ; chacune est celle de la première "
            "exécution de son unité.",
            "Durations ↺: every unit is read from the archive — no duration is "
            "measured by this run; each is its unit's first-execution duration.",
        )
        return f'<p class="muted">{head}</p>\n'
    parts = []
    for name, d in split.items():
        measured = (
            localized(
                lang,
                f"{len(d.measured)} mesurée(s) par ce run "
                f"({_mean(d.measured, lang)} s/page)",
                f"{len(d.measured)} measured by this run "
                f"({_mean(d.measured, lang)} s/page)",
            )
            if d.measured
            else localized(lang, "aucune mesurée par ce run", "none measured")
        )
        inherited = localized(
            lang,
            f"{len(d.resumed)} reprise(s) de l'archive "
            f"({_mean(d.resumed, lang)} s/page, durée de leur première exécution)",
            f"{len(d.resumed)} resumed from the archive "
            f"({_mean(d.resumed, lang)} s/page, first-execution duration)",
        )
        parts.append(f"{escape(name)} — {measured} · {inherited}")
    head = localized(
        lang,
        "Durées ↺ : une unité reprise de l'archive garde la durée de sa "
        "première exécution, pas une mesure de ce run. Séparées :",
        "Durations ↺: a unit resumed from the archive keeps its "
        "first-execution duration, not a measurement of this run. Split:",
    )
    return f'<p class="muted">{head} ' + " ; ".join(parts) + ".</p>\n"


__all__ = ["KeyMeasuresSection"]
