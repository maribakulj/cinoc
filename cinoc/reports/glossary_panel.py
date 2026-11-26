"""Glossaire contextuel — panneau ``<dialog>`` natif, ouvert depuis le chrome.

Remplace l'ancienne section bas-de-page (le glossaire est de la **périphérie**,
pas du flux de lecture). Le contenu vient de la DONNÉE ``glossary/{lang}.yaml``
(anti-hallucination, aucune prose générée), pour les **seules** métriques
présentes dans le ``RunResult``.

Enrichissement progressif : sans JS, le ``<dialog>`` s'affiche via ``:target``
(le lien-ancre du chrome) ; avec JS, ``report.js`` l'ouvre en **modale**
(``showModal()``). Le contenu (disclosures ``<details>``) reste lisible dans les
deux cas.
"""

from __future__ import annotations

from cinoc.reports.glossary import load_glossary
from cinoc.reports.html import escape, localized
from cinoc.reports.metric_categories import (
    category_label,
    category_of,
    unit_label,
    unit_of,
)

#: Id du dialog (cible de l'ancre du chrome + du repli ``:target``).
DIALOG_ID = "glossary-dialog"

#: Champs affichés, ordre stable (déterminisme) : ``(clé, libellé FR, libellé EN)``.
_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("definition", "Définition", "Definition"),
    ("measures", "Ce que ça mesure", "What it measures"),
    ("limits", "Limites", "Limits"),
    ("oracle", "Oracle", "Oracle"),
)
_HEADINGS = {"fr": "Glossaire", "en": "Glossary"}
_INTROS = {
    "fr": "Définitions des métriques présentes dans ce rapport, pour le lecteur "
    "non spécialiste.",
    "en": "Definitions of the metrics present in this report, for the "
    "non-specialist reader.",
}
_CLOSE = {"fr": "Fermer", "en": "Close"}


def _field_label(idx: int, lang: str) -> str:
    return _FIELDS[idx][2] if lang == "en" else _FIELDS[idx][1]


def _declared(metric: str, lang: str) -> str:
    """Catégorie et unité **déclarées au registre** (D-289) — pas recopiées
    dans le YAML : la fiche les lit là où le calcul les porte."""
    category, unit = category_of(metric), unit_of(metric)
    if category is None or unit is None:
        return ""
    return (
        f'<dt class="gl-k">{localized(lang, "Catégorie", "Category")}</dt>'
        f'<dd class="gl-v">{escape(category_label(category, lang))}</dd>'
        f'<dt class="gl-k">{localized(lang, "Unité", "Unit")}</dt>'
        f'<dd class="gl-v">{escape(unit_label(unit, lang))}</dd>'
    )


def _entry(metric: str, term: dict[str, str], lang: str) -> str:
    title = term.get("title", "")
    rows = _declared(metric, lang) + "".join(
        f'<dt class="gl-k">{escape(_field_label(i, lang))}</dt>'
        f'<dd class="gl-v">{escape(term[key])}</dd>'
        for i, (key, _, _) in enumerate(_FIELDS)
        if term.get(key)
    )
    return (
        '<details class="gl-item"><summary class="gl-term">'
        f"{escape(title)}</summary>\n"
        f'<dl class="gl-body">{rows}</dl></details>\n'
    )


def glossary_chrome_link(lang: str) -> str:
    """Lien « Glossaire » du chrome (ancre → ``#glossary-dialog``)."""
    label = escape(_HEADINGS.get(lang, _HEADINGS["fr"]))
    return f'<a class="chrome-btn" href="#{DIALOG_ID}">{label}</a>'


def glossary_dialog(present: set[str], lang: str) -> str:
    """``<dialog>`` du glossaire pour les métriques **présentes** ; ``""`` si aucune.

    Ordre stable = clés de métrique triées. Renvoie une chaîne vide si aucune
    métrique présente n'a d'entrée de glossaire (pas de dialog, pas de lien chrome).
    """
    glossary = load_glossary(lang)
    items = [
        _entry(m, glossary[m], lang) for m in sorted(present) if m in glossary
    ]
    if not items:
        return ""
    heading = escape(_HEADINGS.get(lang, _HEADINGS["fr"]))
    intro = escape(_INTROS.get(lang, _INTROS["fr"]))
    close = escape(_CLOSE.get(lang, _CLOSE["fr"]))
    return (
        f'<dialog id="{DIALOG_ID}" class="glossary-dialog" aria-label="{heading}">'
        f'<div class="gd-head"><h2>{heading}</h2>'
        f'<a class="gd-close" href="#" data-close aria-label="{close}">✕</a></div>'
        f'<p class="muted">{intro}</p>'
        f'<div class="glossary">{"".join(items)}</div></dialog>'
    )


__all__ = ["DIALOG_ID", "glossary_chrome_link", "glossary_dialog"]
