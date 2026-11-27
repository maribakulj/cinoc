"""Comparaison de deux ``RunResult`` (couche 7) → rapport HTML de deltas.

Hors ``Protocol Section`` (qui ne prend qu'**un** résultat) : ``compare`` met deux
runs côte à côte et calcule, par ``(pipeline, vue, métrique)``, le delta
``B − A``. Le rapport reste **autonome** (assembleur ``render_document``).
"""

from __future__ import annotations

from dataclasses import dataclass

from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import fmt
from cinoc.reports.composition_diff import PairedDifference, paired_differences
from cinoc.reports.html import escape, localized, render_document
from cinoc.reports.section import Html

_Key = tuple[str, str, str]


@dataclass(frozen=True)
class MetricDelta:
    """Valeur d'une métrique dans deux runs + leur écart (``B − A``)."""

    pipeline: str
    view: str
    metric: str
    value_a: float | None
    value_b: float | None
    delta: float | None


def compare_runs(run_a: RunResult, run_b: RunResult) -> tuple[MetricDelta, ...]:
    """Aligne deux runs par ``(pipeline, vue, métrique)`` et calcule les deltas."""
    index_a = _index(run_a)
    index_b = _index(run_b)
    deltas: list[MetricDelta] = []
    for key in sorted(set(index_a) | set(index_b)):
        value_a = index_a.get(key)
        value_b = index_b.get(key)
        delta = (
            value_b - value_a
            if value_a is not None and value_b is not None
            else None
        )
        deltas.append(
            MetricDelta(
                pipeline=key[0],
                view=key[1],
                metric=key[2],
                value_a=value_a,
                value_b=value_b,
                delta=delta,
            )
        )
    return tuple(deltas)


def _index(result: RunResult) -> dict[_Key, float | None]:
    return {
        (pipeline.pipeline, pipeline.view, score.metric): score.value
        for pipeline in result.pipelines
        for score in pipeline.aggregate
    }


def _format(value: float | None, lang: str, spec: str = ".4f") -> str:
    """Décimale localisée (D22 du pilote : « 0,3000 » en français)."""
    return "—" if value is None else fmt(value, lang, spec)


def _side(result: RunResult, source: str | None) -> str:
    """Ce qui distingue un côté : son ``run_id``, puis le **nom** du fichier
    (jamais un chemin local, D5) et l'heure de début — deux runs d'une même
    spec relancée portent le même ``run_id`` (D22)."""
    started = result.manifest.started_at.strftime("%Y-%m-%d %H:%M UTC")
    detail = ", ".join(x for x in (source, started) if x)
    return f"{escape(result.manifest.run_id)} ({escape(detail)})"


def _composition_warning(paires: tuple[PairedDifference, ...], lang: str) -> str:
    """Les chaînes appariées par leur nom qui ne sont pas composées pareil :
    leur delta mêle l'effet de ces réglages au changement qu'on croit lire."""
    if not paires:
        return ""
    items = "".join(
        f"<li><strong>{escape(p.pipeline)}</strong> — "
        + " · ".join(
            f"<code>{escape(d.label())}</code> : {escape(d.value_a or '—')} → "
            f"{escape(d.value_b or '—')}"
            for d in p.differences
        )
        + "</li>"
        for p in paires
    )
    chapeau = localized(
        lang,
        "Attention : ces chaînes sont appariées par leur nom, mais n'ont pas la "
        "même composition dans A et B ; leur Δ mêle l'effet de ces différences "
        "(A → B) :",
        "Warning: these pipelines are paired by name, but do not have the same "
        "composition in A and B; their Δ mixes in the effect of these "
        "differences (A → B):",
    )
    return f"<p><strong>{chapeau}</strong></p>\n<ul>{items}</ul>\n"


def render_comparison(
    run_a: RunResult,
    run_b: RunResult,
    *,
    lang: str = "fr",
    source_a: str | None = None,
    source_b: str | None = None,
) -> str:
    """Rend un rapport HTML autonome des deltas entre deux runs (FR ou EN).

    ``source_a`` / ``source_b`` : le nom du fichier lu de chaque côté."""
    rows = "".join(
        f"<tr><td>{escape(delta.pipeline)}</td><td>{escape(delta.view)}</td>"
        f"<td>{escape(delta.metric)}</td>"
        f'<td class="num">{_format(delta.value_a, lang)}</td>'
        f'<td class="num">{_format(delta.value_b, lang)}</td>'
        f'<td class="num">{_format(delta.delta, lang, "+.4f")}</td></tr>'
        for delta in compare_runs(run_a, run_b)
    )
    # NB : le sens « mieux » dépend de la métrique. Les métriques livrées
    # (CER/WER/MER) sont **toutes** des taux d'erreur → on l'annonce explicitement
    # plutôt qu'en supposant l'universalité. Porter `higher_is_better` jusque dans
    # `RunResult` est différé tant qu'aucune métrique « plus haut = mieux » n'existe.
    note = localized(
        lang,
        "taux d'erreur CER/WER/MER : Δ &lt; 0 = amélioration",
        "CER/WER/MER error rates: Δ &lt; 0 = improvement",
    )
    head = localized(
        lang,
        "<th>Pipeline</th><th>Vue</th><th>Métrique</th>",
        "<th>Pipeline</th><th>View</th><th>Metric</th>",
    )
    body = Html(
        f'<p class="muted">A = {_side(run_a, source_a)} · '
        f"B = {_side(run_b, source_b)} · Δ = B − A ({note}).</p>\n"
        + _composition_warning(paired_differences(run_a.manifest, run_b.manifest), lang)
        + f"<table>\n<thead><tr>{head}"
        + "<th>A</th><th>B</th><th>Δ</th></tr></thead>\n"
        + f"<tbody>{rows}</tbody>\n</table>\n"
    )
    title = localized(
        lang, "Cinoc — comparaison de runs", "Cinoc — run comparison"
    )
    return render_document(title, body, lang=lang)


__all__ = ["MetricDelta", "compare_runs", "render_comparison"]
