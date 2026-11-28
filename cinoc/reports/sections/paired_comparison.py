"""Section **comparaison appariée** : supports par paire, support global, invention
hors référence (couche 7).

Lit, en **lecture seule**, les analyses ``comparison`` et
``invention_outside_reference`` : « publié » veut dire affiché (D7). Deux
pipelines ne se comparent que sur les documents qu'ils ont **tous deux** (support
apparié) ; le tri multi-pipelines est celui du **support global** (B7). Les
valeurs sont des micro et des macro sur ces supports — métrologiques, sans test
(les p des analyses de rangs relèvent de la section inter-moteurs, et sont
exploratoires). Le macro ne voit pas l'invention d'un pipeline sur un document
sans référence : la seconde table la montre, avec la couverture de ces pages.

Absente quand aucune vue ne compare deux pipelines : pas de section vide.
"""

from __future__ import annotations

from cinoc.evaluation.comparison import ComparisonPayload, InventionPayload
from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized, view_label
from cinoc.reports.metric_categories import is_established
from cinoc.reports.section import Html, SectionContext

#: Métrique affichée d'emblée ; les autres établies sont repliées.
_PRIMARY = "cer"


def _value(value: float | None, lang: str) -> str:
    return "—" if value is None else localize_decimal(f"{value:.4f}", lang)


def _comparison_block(
    payload: ComparisonPayload, order: dict[str, int], lang: str
) -> str:
    th_a = localized(lang, "Moteur A", "Engine A")
    th_b = localized(lang, "Moteur B", "Engine B")
    th_docs = localized(lang, "Documents appariés", "Paired documents")
    th_micro = localized(lang, "Micro A · B", "Micro A · B")
    th_macro = localized(lang, "Macro A · B", "Macro A · B")
    rows = []
    for pair in payload.pairs:
        rows.append(
            f'<tr><td class="eng-cell">{engine_cell(pair.a, order.get(pair.a, 0))}</td>'
            f'<td class="eng-cell">{engine_cell(pair.b, order.get(pair.b, 0))}</td>'
            f'<td class="disp">{len(pair.micro_documents)}</td>'
            f'<td class="disp">{_value(pair.micro.get(pair.a), lang)} · '
            f"{_value(pair.micro.get(pair.b), lang)}</td>"
            f'<td class="disp">{_value(pair.macro.get(pair.a), lang)} · '
            f"{_value(pair.macro.get(pair.b), lang)} "
            f'<span class="muted">({len(pair.macro_documents)})</span></td></tr>'
        )
    glob = payload.global_support
    ranking = " &gt; ".join(
        f"{escape(p)} ({_value(glob.micro.get(p), lang)})" for p in glob.ranking
    )
    macro = " · ".join(
        f"{escape(p)} {_value(value, lang)}" for p, value in sorted(glob.macro.items())
    )
    legend = localized(
        lang,
        f"Support global : {len(glob.micro_documents)} documents communs à tous "
        f"les moteurs — tri sur le micro (meilleur en premier) : "
        f"{ranking or '—'} ; macro sur {len(glob.macro_documents)} documents : "
        f"{macro or '—'}.",
        f"Global support: {len(glob.micro_documents)} documents common to all "
        f"engines — ranking on the micro (best first): {ranking or '—'}; macro "
        f"over {len(glob.macro_documents)} documents: {macro or '—'}.",
    )
    return (
        f"<h4>{escape(payload.metric)}</h4>\n"
        '<div class="table-scroll"><table class="data">\n'
        f"<thead><tr><th>{th_a}</th><th>{th_b}</th>"
        f'<th class="num-cell">{th_docs}</th>'
        f'<th class="num-cell">{th_micro}</th>'
        f'<th class="num-cell">{th_macro}</th></tr></thead>\n'
        f"<tbody>{''.join(rows)}</tbody>\n</table></div>\n"
        f'<p class="muted">{legend}</p>\n'
    )


def _invention_block(
    payload: InventionPayload, order: dict[str, int], lang: str
) -> str:
    title = localized(
        lang,
        f"Invention hors référence — {escape(payload.metric)}",
        f"Invention outside the reference — {escape(payload.metric)}",
    )
    if payload.unit is None:
        return (
            f"<h4>{title}</h4>\n"
            + localized(
                lang,
                '<p class="muted">Non définie : la statistique de cette métrique '
                "ne compte aucune unité de l'hypothèse (insensible à l'invention "
                "par construction).</p>\n",
                '<p class="muted">Undefined: this metric\'s statistic counts no '
                "unit of the hypothesis (insensitive to invention by "
                "construction).</p>\n",
            )
        )
    # « insertions inventées » (féminin), « faux positifs inventés » (masculin) :
    # l'accord suit le nom, jamais l'identifiant de l'unité (``false_positives``).
    if payload.unit == "insertions":
        invented_fr, invented_en = "insertions inventées", "insertions invented"
    else:
        invented_fr, invented_en = "faux positifs inventés", "false positives invented"
    th_a = localized(lang, "Moteur A", "Engine A")
    th_b = localized(lang, "Moteur B", "Engine B")
    th_docs = localized(
        lang, "Pages sans référence (communes)", "Pages without reference (common)"
    )
    th_a_inv = localized(lang, f"A : {invented_fr}", f"A: {invented_en}")
    th_b_inv = localized(lang, f"B : {invented_fr}", f"B: {invented_en}")
    rows = "".join(
        f'<tr><td class="eng-cell">{engine_cell(p.a, order.get(p.a, 0))}</td>'
        f'<td class="eng-cell">{engine_cell(p.b, order.get(p.b, 0))}</td>'
        f'<td class="disp">{len(p.documents)}</td>'
        f'<td class="disp">{p.invented.get(p.a, 0)}</td>'
        f'<td class="disp">{p.invented.get(p.b, 0)}</td></tr>'
        for p in payload.pairs
    )
    coverage = " · ".join(
        f"{escape(name)} {measured}/{expected}"
        for name, (measured, expected) in sorted(payload.coverage.items())
    )
    note = localized(
        lang,
        f"Couverture des pages sans référence (mesurées/attendues) : {coverage}. "
        "Le macro ne voit pas ce texte inventé ; le micro le compte.",
        f"Coverage of the pages without reference (measured/expected): "
        f"{coverage}. The macro does not see this invented text; the micro "
        "counts it.",
    )
    return (
        f"<h4>{title}</h4>\n"
        '<div class="table-scroll"><table class="data">\n'
        f"<thead><tr><th>{th_a}</th><th>{th_b}</th>"
        f'<th class="num-cell">{th_docs}</th>'
        f'<th class="num-cell">{th_a_inv}</th>'
        f'<th class="num-cell">{th_b_inv}</th></tr></thead>\n'
        f"<tbody>{rows}</tbody>\n</table></div>\n"
        f'<p class="muted">{note}</p>\n'
    )


class PairedComparisonSection:
    """Supports apparié et global, et invention hors référence (lecture seule)."""

    name = "paired_comparison"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        lang = ctx.lang
        order = engine_order(p.pipeline for p in result.pipelines)
        multi = len({a.view for a in result.analyses}) > 1
        blocks: list[str] = []
        for view in dict.fromkeys(a.view for a in result.analyses):
            comparisons = sorted(
                (
                    a.payload
                    for a in result.analyses
                    if a.view == view
                    and isinstance(a.payload, ComparisonPayload)
                    and is_established(a.payload.metric)
                ),
                key=lambda p: (p.metric != _PRIMARY, p.metric),
            )
            inventions = [
                a.payload
                for a in result.analyses
                if a.view == view
                and isinstance(a.payload, InventionPayload)
                and is_established(a.payload.metric)
            ]
            if not comparisons and not inventions:
                continue
            head = f"<h3>{escape(view_label(view, lang))}</h3>\n" if multi else ""
            main = [c for c in comparisons if c.metric == _PRIMARY]
            others = [c for c in comparisons if c.metric != _PRIMARY]
            inner = "".join(_comparison_block(c, order, lang) for c in main)
            if others:
                summary = localized(
                    lang, "Autres métriques établies", "Other established metrics"
                )
                inner += (
                    f"<details><summary>{summary}</summary>"
                    + "".join(_comparison_block(c, order, lang) for c in others)
                    + "</details>\n"
                )
            inner += "".join(_invention_block(i, order, lang) for i in inventions)
            blocks.append(head + inner)
        if not blocks:
            return None
        title = localized(lang, "Comparaison appariée", "Paired comparison")
        prose = localized(
            lang,
            '<p class="muted">Deux moteurs ne se comparent que sur les documents '
            "qu'ils ont <b>tous deux</b> notés (support apparié) ; le tri "
            "multi-pipelines est celui du <b>support global</b>, sur les "
            "documents que tous ont notés. Les valeurs sont des micro (somme des "
            "statistiques) et des macro (moyenne des scalaires) sur ces supports : "
            "des mesures, sans test. Les documents notés sont ceux de l'agrégat "
            "principal du run (complets, ou opérationnels sous la politique "
            "<code>empty_page</code>).</p>\n",
            '<p class="muted">Two engines are compared only on the documents '
            "<b>both</b> scored (paired support); the multi-pipeline ranking is "
            "that of the <b>global support</b>, over the documents all scored. "
            "Values are micro (sum of statistics) and macro (mean of scalars) on "
            "these supports: measurements, no test. The documents scored are "
            "those of the run's main aggregate (complete, or operational under "
            "the <code>empty_page</code> policy).</p>\n",
        )
        return Html(f"<h2>{title}</h2>\n{prose}" + "".join(blocks))


__all__ = ["PairedComparisonSection"]
