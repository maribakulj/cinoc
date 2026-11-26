"""Assemblage HTML **autonome** au design + échappement (couche 7).

Produit un document autonome (**CSS inline**, aucune dépendance CDN/JS), donc
hébergeable tel quel **et déterministe** (cf. plan §Cibles de distribution). Le
style reprend le **design** (gris chaud, chrome pilule, cartes ``sec``, tables
tabulaires) ; les **polices du design** — titres *Mona Sans*, corps *IBM Plex
Sans*, données *IBM Plex Mono*, accents *Fluxisch Else*, logo *OCR-A* — sont
**incorporées en data-URI** (``_style.font_face_css``) pour garder
l'identité typographique **et** l'autonomie (S4.b.1a, option (a) — cf. D-019). Les
**données** sont échappées via ``escape`` ; la **structure** est de l'``Html`` de
confiance.
"""

from __future__ import annotations

import html as _html
from functools import cache

from cinoc.reports._style import font_face_css
from cinoc.reports.embedded import asset_text
from cinoc.reports.section import Html


@cache
def _report_css() -> str:
    """CSS du rapport au design (``_assets/report.css``, sous-ensemble de
    ``design/tokens.css``), lu **une fois**. Les ``@font-face`` (data-URI) sont
    préfixés au rendu par ``font_face_css()``.

    Le fichier est écrit une ligne par fragment, commenté : ses lignes sont
    concaténées sans séparateur et ses lignes de commentaire (``/* … */``)
    retirées — le rapport porte exactement les octets du littéral Python
    qu'il remplace (D-301). Statique → le rapport reste octet-stable ; inliné
    dans ``<style>`` (``style-src 'unsafe-inline'``, aucune empreinte à
    tenir), il voyage avec le document.
    """
    return "".join(
        line
        for line in asset_text("report.css").splitlines()
        if not line.startswith("/*")
    )


def escape(text: str) -> str:
    """Échappe une donnée pour insertion sûre dans le HTML."""
    return _html.escape(text, quote=True)


def localized(lang: str, fr: str, en: str) -> str:
    """Choisit la chaîne selon la langue du rapport (``en`` si ``"en"``, sinon ``fr``).

    Mécanisme i18n **minimal** : les sections gardent leurs deux formulations
    **adjacentes** au point d'usage (revue/maintenance faciles), sélectionnées via
    ``SectionContext.lang`` — **pas de catalogue ni de registre** de chaînes. Repli
    sur le français pour toute langue non gérée (déterminisme : même langue →
    mêmes octets)."""
    return en if lang == "en" else fr


#: Libellés humains des vues d'évaluation : nom interne → (FR, EN). **Source
#: unique** consommée par toutes les sections (fin du « vue : text » brut dans les
#: titres). Une vue absente d'ici porte déjà un nom lisible (ex. « référence OCR
#: (pas une vérité-terrain manuelle) ») → affichée telle quelle.
_VIEW_LABELS: dict[str, tuple[str, str]] = {
    # Ni « brut » ni « plain » : la vue texte est normalisée (profil par
    # défaut, D-285) — son profil est écrit à côté du chiffre.
    "texte": ("Texte", "Text"),
    "texte (lignes)": ("Texte (lignes)", "Text (lines)"),
    "text": ("Texte", "Text"),
    "structure": ("Structure (mise en page)", "Layout structure"),
    "entites": ("Entités nommées", "Named entities"),
    "diplomatic": ("Transcription diplomatique", "Diplomatic transcription"),
}


def view_label(view: str, lang: str) -> str:
    """Libellé humain d'une vue d'évaluation (repli sur le nom brut si inconnu).

    Centralise la traduction du **nom interne** de vue (``"texte"``) vers un
    libellé lisible (« Texte » / « Text »). Déterministe (même vue + langue → mêmes
    octets) ; n'échappe pas (l'appelant échappe au point d'insertion HTML)."""
    pair = _VIEW_LABELS.get(view)
    if pair is None:
        return view
    return pair[1] if lang == "en" else pair[0]


def view_prefix(view: str, lang: str, *, multi: bool) -> str:
    """Préfixe de titre de bloc « <Libellé de vue> — », **seulement** si le run
    porte plusieurs vues à distinguer ; sinon ``""`` (le libellé est déjà porté
    par le héros/onglet → pas de ressassage « Texte brut — » sur chaque section).
    Déjà échappé (fragment HTML prêt) : l'appelant l'insère tel quel."""
    return f"{escape(view_label(view, lang))} — " if multi else ""


def render_document(
    title: str,
    body: Html,
    *,
    footer: Html | None = None,
    lang: str = "fr",
    tabs: str = "",
    meta: str = "",
) -> str:
    """Assemble un document HTML autonome, au design, et déterministe.

    ``footer`` (optionnel) : HTML inséré en fin de ``<body>``, après le contenu
    principal — p. ex. le widget « comparer un run » (client-side). Absent → rien
    n'est ajouté (le rapport reste identique au squelette, ex. la voie
    ``compare`` server-side qui n'embarque pas le widget). ``lang`` pilote
    l'attribut ``<html lang>`` (a11y / lecteurs d'écran). ``tabs``/``meta`` :
    HTML **de confiance** intégré au **chrome** (barre d'onglets et méta+exports) ;
    vides → chrome minimal (wordmark seul). Le corps n'est **plus** enveloppé dans
    une carte unique : chaque section rend **sa** carte ``.sec``."""
    safe_title = escape(title)
    safe_lang = escape(lang)
    sub = "Report · benchmark" if lang == "en" else "Rapport · benchmark"
    tail = f"{footer}" if footer is not None else ""
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{safe_lang}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{safe_title}</title>\n"
        f"<style>{font_face_css()}{_report_css()}</style>\n"
        "</head>\n"
        '<body class="report-board">\n'
        '<header class="report-chrome">'
        '<span class="wm-mark">C</span>'
        '<span class="wm-name">Cin<span class="wm-o">o</span>c</span>'
        f'<span class="wm-sep"></span><span class="wm-sub">{sub}</span>'
        f"{tabs}{meta}</header>\n"
        f'<main class="report-main">{body}</main>\n'
        f"{tail}"
        "</body>\n"
        "</html>\n"
    )


__all__ = [
    "escape",
    "localized",
    "render_document",
    "view_label",
    "view_prefix",
]
