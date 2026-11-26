"""Section taxonomie : composition des classes d'erreurs (couche 7).

Rend les payloads ``taxonomy`` en **lecture seule** : par pipeline, une **barre
empilée SVG** (part de chaque classe) + une légende (classe · part · occurrences)
— quelles erreurs, pas seulement combien. Sous 2 moteurs ou plus, un **profil
comparatif** (classe × moteur, part en databar) donne l'autre lecture : non plus
la composition d'un moteur, mais quel moteur est lourd sur *quelle* classe (#5).
Server-side, déterministe, zéro JS.
"""

from __future__ import annotations

from collections.abc import Mapping

from cinoc.evaluation.analysis import PipelineTaxonomy, TaxonomyPayload
from cinoc.evaluation.result import RunResult
from cinoc.reports.engine_badges import engine_accent, engine_cell, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._payload import render_payload_section
from cinoc.reports.svg import composition_bar

#: Libellés bilingues du **profil comparatif** (le reste de la section, antérieur
#: à la consigne FR/EN des graphiques, reste FR — i18n du rapport = jalon à part).
_PROFILE_TEXT: dict[str, dict[str, str]] = {
    "fr": {
        "title": "profil comparatif des moteurs",
        "intro": (
            "Part de chaque classe d'erreur, moteur par moteur — lire une "
            "<strong>ligne</strong> pour comparer les moteurs sur une classe (qui "
            "est lourd en diacritiques, en segmentation…). « · » = classe absente "
            "chez ce moteur."
        ),
        "th_class": "Classe d'erreur",
    },
    "en": {
        "title": "comparative engine profile",
        "intro": (
            "Share of each error class, engine by engine — read a <strong>row</strong> "
            "to compare engines on one class (which is heavy on diacritics, "
            "segmentation…). “·” = class absent for that engine."
        ),
        "th_class": "Error class",
    },
}


#: Libellés **lisibles bilingues** des classes d'erreur (la donnée garde ses clés
#: stables ``CLASSES``). ``other`` = substitutions résiduelles = **vrais misreads**
#: (ni casse/diacritique/ligature/confusion visuelle) → nommé « substitution »,
#: pas un fourre-tout « other » : sur de l'OCR fautif, c'est légitimement la classe
#: dominante (le moteur produit le mauvais mot, pas juste un accent près).
_CLASS_LABELS: dict[str, tuple[str, str]] = {
    "segmentation": ("segmentation", "segmentation"),
    "case": ("casse", "case"),
    "diacritic": ("diacritique", "diacritic"),
    "ligature": ("ligature", "ligature"),
    "visual": ("confusion visuelle", "visual confusion"),
    "lacuna": ("omission", "omission"),
    "insertion": ("insertion", "insertion"),
    "other": ("substitution", "substitution"),
}


def _class_label(key: str, lang: str) -> str:
    """Libellé lisible d'une classe d'erreur (clé brute si non répertoriée)."""
    pair = _CLASS_LABELS.get(key)
    if pair is None:
        return key
    return pair[1] if lang == "en" else pair[0]


def composition_html(
    classes: tuple[str, ...], pipeline: PipelineTaxonomy, lang: str = "fr"
) -> str:
    """Barre empilée + légende pour **un** pipeline (réutilisable : section + profil).

    Couleur par classe = palette cyclique partagée, indexée sur l'ordre canonique
    ``classes``. Renvoie ``""`` si le pipeline n'a aucune erreur classée."""
    color = {cls: engine_accent(i) for i, cls in enumerate(classes)}

    def _c(label: str) -> str:
        return color.get(label, engine_accent(0))

    total = pipeline.total_errors
    present = [(c.label, c.count) for c in pipeline.counts if c.count > 0]
    if not present:
        return ""
    segments = [(cnt / total, _c(lbl)) for lbl, cnt in present]
    legend = "".join(
        f'<div class="comp-row">'
        f'<span class="comp-sw" style="background:{_c(lbl)}"></span>'
        f'<span class="comp-label">{escape(_class_label(lbl, lang))}</span>'
        f'<span class="comp-share mono">{cnt / total:.0%}</span>'
        f'<span class="comp-count mono">{cnt}</span></div>'
        for lbl, cnt in present
    )
    return (
        f'<div class="comp">{composition_bar(segments)}'
        f'<div class="comp-legend">{legend}</div></div>'
    )


def _profile_block(
    view: str, payload: TaxonomyPayload, order: Mapping[str, int], lang: str
) -> str:
    """Profil comparatif (#5) : classe × moteur, part en databar (lecture par ligne).

    Complémentaire des barres empilées par-moteur ci-dessus (lecture par moteur) :
    ici on lit une **classe** à travers les moteurs. **À 2 moteurs et plus** (à 1,
    la barre suffit — pas de comparaison). Pure présentation du payload."""
    if len(payload.pipelines) < 2:
        return ""
    present = [
        cls
        for cls in payload.classes
        if any(
            count.label == cls and count.count > 0
            for pipeline in payload.pipelines
            for count in pipeline.counts
        )
    ]
    if not present:
        return ""
    text = _PROFILE_TEXT.get(lang, _PROFILE_TEXT["fr"])
    headers = "".join(
        f'<th class="num-cell">{engine_cell(p.pipeline, order.get(p.pipeline, 0))}</th>'
        for p in payload.pipelines
    )
    rows: list[str] = []
    for cls in present:
        cells: list[str] = []
        for pipeline in payload.pipelines:
            count = next((c.count for c in pipeline.counts if c.label == cls), 0)
            share = count / pipeline.total_errors if pipeline.total_errors else 0.0
            if count > 0:
                cells.append(
                    '<td class="databar">'
                    f'<span class="db-fill" style="width:{round(share * 100)}%">'
                    f'</span><span class="db-num">{share:.0%}</span></td>'
                )
            else:
                cells.append('<td class="databar"><span class="db-num">·</span></td>')
        rows.append(
            f'<tr><td class="eng-cell">{escape(_class_label(cls, lang))}</td>'
            f'{"".join(cells)}</tr>'
        )
    return (
        f"<h3>{view}{text['title']}</h3>\n"
        f'<p class="muted">{text["intro"]}</p>\n'
        '<table class="data">\n'
        f'<thead><tr><th>{text["th_class"]}</th>{headers}</tr></thead>\n'
        f"<tbody>{''.join(rows)}</tbody>\n</table>\n"
    )


def _block(
    view: str, payload: TaxonomyPayload, order: Mapping[str, int], lang: str
) -> str:
    head = localized(
        lang,
        f"{view}composition des erreurs",
        f"{view}error composition",
    )
    prose = localized(
        lang,
        '<p class="muted">Classification par règles pures (casse, diacritiques, '
        "ligatures, confusions visuelles, segmentation, lacunes, insertions) — "
        "part relative au total des erreurs de mots du pipeline. Chaque édition "
        "du WER reçoit une classe et une seule : les omissions sont ses "
        "suppressions, les insertions ses insertions, hors fusions et "
        "scissions de mots.</p>\n",
        '<p class="muted">Pure rule-based classification (case, diacritics, '
        "ligatures, visual confusions, segmentation, gaps, insertions) — "
        "share relative to the pipeline's total word errors. Each WER edit gets "
        "exactly one class: omissions are its deletions, insertions its "
        "insertions, outside word merges and splits.</p>\n",
    )
    parts: list[str] = [f"<h3>{head}</h3>\n", prose]
    for pipeline in payload.pipelines:
        block = composition_html(payload.classes, pipeline, lang)
        if block:
            label = localized(
                lang,
                f"{pipeline.total_errors} erreurs",
                f"{pipeline.total_errors} errors",
            )
            parts.append(
                f"<h4>{escape(pipeline.pipeline)} — {label}</h4>\n{block}\n"
            )
    parts.append(_profile_block(view, payload, order, lang))
    return "".join(parts)


class TaxonomySection:
    """Composition des classes d'erreurs par pipeline (barre empilée + légende)."""

    name = "taxonomy"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        order = engine_order(p.pipeline for p in result.pipelines)
        return render_payload_section(
            result,
            ctx,
            payload_type=TaxonomyPayload,
            title=localized(ctx.lang, "Taxonomie des erreurs", "Error taxonomy"),
            block=lambda view, payload: _block(view, payload, order, ctx.lang),
        )


__all__ = ["TaxonomySection", "composition_html"]
