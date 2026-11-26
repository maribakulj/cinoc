"""Helpers de présentation de ``reports.html`` : libellés de vue, i18n minimal."""

from __future__ import annotations

from cinoc.reports.html import _CSS, localized, view_label


def test_card_layout_uses_grid_not_columns_masonry() -> None:
    """Garde-fou anti-régression du chevauchement de cartes.

    La cause racine des cartes qui se chevauchaient était le masonry CSS
    ``columns`` (le flux ``column-span:all`` cassait l'empilement). La grille
    explicite (``display:grid`` + ``align-items:start``) pose des rangées
    intrinsèques sans chevauchement. Ce test verrouille le choix structurel.
    """
    # Les conteneurs de cartes sont des grilles, pas des flux multi-colonnes.
    # La grille porte sur la vue maître (.tab-master), pas l'onglet (maître+détail).
    assert ".tab-master{display:grid;" in _CSS
    assert ".dd-flow{display:grid;" in _CSS
    assert "align-items:start;" in _CSS
    grid_cols = "grid-template-columns:repeat(auto-fill,minmax(min(100%,23rem),1fr));"
    assert grid_cols in _CSS
    # Les cartes larges s'étendent sur toute la grille (≠ column-span:all).
    wide_rule = ".tab-master>.view-hero,.tab-master>.r-block.r-wide{grid-column:1/-1;}"
    assert wide_rule in _CSS
    assert ".dd-card.dd-wide{grid-column:1/-1;}" in _CSS
    # Plus aucun masonry ``columns``/``column-span`` sur les conteneurs de cartes
    # (le masonry ``columns`` reste légitime pour les listes-journal de texte
    # court — ``.wflow`` — mais jamais pour les cartes).
    assert ".tab-panel{columns:" not in _CSS
    assert ".dd-flow{columns:" not in _CSS
    assert "column-span:all" not in _CSS


def test_localized_picks_language() -> None:
    assert localized("fr", "Bonjour", "Hello") == "Bonjour"
    assert localized("en", "Bonjour", "Hello") == "Hello"
    assert localized("de", "Bonjour", "Hello") == "Bonjour"  # repli FR


def test_view_label_maps_internal_names_to_human() -> None:
    # le nom interne ne fuit plus dans l'UI ; « brut » non plus : la vue texte
    # est normalisée par défaut (D-285), son profil est dit à côté du chiffre.
    assert view_label("texte", "fr") == "Texte"
    assert view_label("texte", "en") == "Text"
    assert view_label("texte (lignes)", "en") == "Text (lines)"
    assert view_label("text", "fr") == "Texte"
    assert view_label("diplomatic", "fr") == "Transcription diplomatique"
    assert view_label("diplomatic", "en") == "Diplomatic transcription"


def test_view_label_passes_through_already_human_names() -> None:
    # une vue déjà lisible (ex. référence OCR) est rendue telle quelle
    name = "référence OCR (pas une vérité-terrain manuelle)"
    assert view_label(name, "fr") == name
    assert view_label("hipe", "en") == "hipe"


def test_view_label_is_deterministic() -> None:
    assert view_label("text", "fr") == view_label("text", "fr")


def test_a_wide_table_scrolls_in_its_own_box_on_a_phone() -> None:
    """À 390 px, un tableau de dix colonnes élargissait **toute** la page
    (défilement horizontal du rapport servi, D-299). Sur écran étroit, chaque
    ``table.data`` défile dans sa propre boîte — la page, jamais."""
    assert (
        "@media (max-width:720px){table.data{display:block;overflow-x:auto;"
        "max-width:100%;}}" in _CSS
    )
