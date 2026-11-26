"""Section Mesures clés : **socle chiffré neutre** par vue (couche 7).

Le **headline** du rapport : les scores standard (CER/WER/FCA/exactitude/cMER)
par moteur, en table **triable** (colonnes annotées du sens de lecture ↓/↑), un
**dot plot classé** du CER avec **IC 95 % bootstrap** (calculé en couche
evaluation — montre l'écart *et* son incertitude), et le **résultat du test**
inter-moteurs comme **fait** (Nemenyi corrigé ou Wilcoxon).

**Aucun verdict** : pas de « meilleur » déclaré, pas de recommandation. On trie
par une valeur mesurée, on affiche un fait statistique — l'utilisateur interprète
(remplace l'ancienne « Synthèse » qui nommait un gagnant ; cf. moteur narratif
supprimé §6, anti-hallucination §12). Gatée sur ``cer``.
"""

from __future__ import annotations

from cinoc.evaluation.analysis import InferencePayload
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import (
    engine_accent,
    engine_cell,
    engine_letter,
    engine_order,
)
from cinoc.reports.html import escape, localized, view_label
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._tables import coverage, ordered_unique
from cinoc.reports.svg import dot_plot_ci

_PRIMARY = "cer"
#: Scores standard (ICDAR/HIPE) du headline : ``(clé, plus_haut_est_meilleur,
#: libellé_fr, libellé_en)``. Ordre fixe ; seuls ceux présents dans la vue sont
#: rendus. Le sens de lecture (↓/↑) est annoté en en-tête (donnée d'affichage).
_HEADLINE: tuple[tuple[str, bool, str, str], ...] = (
    ("cer", False, "CER", "CER"),
    ("wer", False, "WER", "WER"),
    ("fca", True, "FCA", "FCA"),
    ("char_accuracy", True, "Exact. car.", "Char acc."),
    ("word_accuracy", True, "Exact. mot", "Word acc."),
    ("cmer", False, "cMER", "cMER"),
)


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


def _significance(result: RunResult, view: str) -> MetricScore | None:
    """Test brut (Wilcoxon/Friedman) : sa valeur **et** son support (cas complets)."""
    for score in result.cross_engine:
        parts = score.metric.split(":")
        if len(parts) >= 2 and parts[0] == view and parts[1] == _PRIMARY:
            return score
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
        blocks: list[str] = []
        for view in views:
            pipes = [p for p in result.pipelines if p.view == view]
            cols = [
                (m, hib, fr, en)
                for m, hib, fr, en in _HEADLINE
                if any(_val(p, m) is not None for p in pipes)
            ]
            if not cols:
                continue
            head = ""
            if multi:
                head = f"<h3>{escape(view_label(view, lang))}</h3>\n"
            blocks.append(
                head
                + self._table(pipes, cols, order, lang)
                + self._dotplot(result, view, order, lang)
                + self._significance(result, view, lang)
            )
        if not blocks:
            return None
        title = localized(lang, "Mesures clés", "Key measures")
        caption = localized(
            lang,
            "Scores standard par moteur (↓ = plus bas est meilleur · ↑ = plus haut "
            "est meilleur). <strong>Triez</strong> par n'importe quelle colonne. "
            "Aucun gagnant n'est déclaré : les chiffres et le test sont fournis, "
            "l'interprétation vous revient.",
            "Standard scores per engine (↓ = lower is better · ↑ = higher is "
            "better). <strong>Sort</strong> by any column. No winner is declared: "
            "figures and the test are provided; interpretation is yours.",
        )
        return Html(
            f"<h2>{title}</h2>\n<p class=\"muted\">{caption}</p>\n" + "".join(blocks)
        )

    @staticmethod
    def _table(
        pipes: list[PipelineResult],
        cols: list[tuple[str, bool, str, str]],
        order: dict[str, int],
        lang: str,
    ) -> str:
        th_engine = localized(lang, "Moteur", "Engine")
        headers = "".join(
            f'<th class="num-cell sortable" aria-sort="none">'
            f'{escape(en if lang == "en" else fr)} {"↑" if hib else "↓"}</th>'
            for _m, hib, fr, en in cols
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
            for m, _hib, _fr, _en in cols:
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
            badge = engine_cell(p.pipeline, order.get(p.pipeline, 0))
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
        items = sorted(payload.intervals, key=lambda it: (it.mean, it.pipeline))
        rows = [
            (
                engine_letter(order.get(it.pipeline, 0)),
                engine_accent(order.get(it.pipeline, 0)),
                it.mean,
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
            f'<span class="muted">CER par moteur — point = moyenne, barre = IC 95 % '
            f"(bootstrap, n={n}), trié par CER croissant, axe commun.</span>",
            f'<span class="muted">CER per engine — dot = mean, bar = 95 % CI '
            f"(bootstrap, n={n}), sorted by CER, shared axis.</span>",
        )
        return (
            f'<div class="prof-chart"><div class="drill-caption">{cap}</div>'
            f"{dot_plot_ci(rows, scale_max)}</div>\n"
        )

    @staticmethod
    def _significance(result: RunResult, view: str, lang: str) -> str:
        payload = _inference(result, view)
        if payload is not None and payload.critical_distance is not None:
            groups = " · ".join(
                "{" + ", ".join(escape(p) for p in g) + "}"
                for g in payload.tied_groups
            )
            alpha = localize_decimal(f"{payload.alpha:g}", lang)
            cd = localize_decimal(f"{payload.critical_distance:.3f}", lang)
            txt = localized(
                lang,
                f"<strong>Test inter-moteurs (CER)</strong> — post-hoc Nemenyi "
                f"(α={alpha}, CD={cd}, "
                f"{payload.n_documents} cas complets) : groupes d'indiscernables "
                f"{groups}. Deux moteurs hors d'un même groupe = différence "
                f"significative.",
                f"<strong>Inter-engine test (CER)</strong> — Nemenyi post-hoc "
                f"(α={alpha}, CD={cd}, "
                f"{payload.n_documents} complete cases): indistinguishable groups "
                f"{groups}. Two engines outside one group = significant difference.",
            )
            return f'<p class="muted">{txt}</p>\n'
        raw = _significance(result, view)
        p = raw.value if raw is not None else None
        if raw is not None and p is not None:
            verdict = localized(
                lang,
                "significative" if p < 0.05 else "non significative",
                "significant" if p < 0.05 else "not significant",
            )
            pv = localize_decimal(f"{p:.4f}", lang)
            txt = localized(
                lang,
                f"<strong>Test inter-moteurs (CER)</strong> — Wilcoxon : p = "
                f"{pv} → différence {verdict} au seuil α = 0,05 "
                f"({raw.support} cas complets).",
                f"<strong>Inter-engine test (CER)</strong> — Wilcoxon: p = "
                f"{pv} → difference {verdict} at α = 0.05 "
                f"({raw.support} complete cases).",
            )
            return f'<p class="muted">{txt}</p>\n'
        return ""


__all__ = ["KeyMeasuresSection"]
