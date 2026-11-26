"""``markdown_to_text`` : la syntaxe d'un markdown d'OCR retirée, le texte gardé.

Chaque convention du module (docstring de ``cinoc.formats.text.markdown``) a
son cas ; plus deux propriétés : aucun saut de ligne ajouté, ordre gardé.
"""

from __future__ import annotations

import pytest

from cinoc.formats.text import markdown_to_text


@pytest.mark.parametrize(
    ("markdown", "texte"),
    [
        # Titres, ouverts et fermés.
        ("# LE PETIT JOURNAL", "LE PETIT JOURNAL"),
        ("### Chronique ###", "Chronique"),
        ("#hashtag", "#hashtag"),  # pas d'espace : pas un titre
        # Emphase appariée, emboîtée.
        ("**Supplément illustré**", "Supplément illustré"),
        ("un *mot* et un _autre_", "un mot et un autre"),
        ("***tout*** et __gras__", "tout et gras"),
        ("**un _mot_ dedans**", "un mot dedans"),
        ("~~barré~~", "barré"),
        # Un astérisque isolé (appel de note) et un souligné intra-mot restent.
        ("Voir la note * ci-dessous", "Voir la note * ci-dessous"),
        ("nom_de_fichier", "nom_de_fichier"),
        ("2 * 3 = 6", "2 * 3 = 6"),
        # Échappements : le caractère, pas l'emphase.
        (r"\*pas italique\*", "*pas italique*"),
        (r"\# pas un titre", "# pas un titre"),
        # Images retirées entièrement, liens réduits à leur texte.
        ("![img-0.jpeg](img-0.jpeg)", ""),
        ("avant ![img-1.jpeg](img-1.jpeg) après", "avant  après"),
        ("[voir page 4](#p4)", "voir page 4"),
        ("<https://gallica.bnf.fr>", "https://gallica.bnf.fr"),
        # Code en ligne.
        ("le `code` ici", "le code ici"),
        # Listes : puces retirées, numéros gardés (imprimés sur la page).
        ("- Prix : 5 centimes", "Prix : 5 centimes"),
        ("* item", "item"),
        ("+ item", "item"),
        ("1. Article premier", "1. Article premier"),
        # Citation.
        ("> cité", "cité"),
        ("> > cité deux fois", "cité deux fois"),
        # Séparations.
        ("---", ""),
        ("* * *", ""),
        ("___", ""),
        ("===", ""),
    ],
)
def test_convention(markdown: str, texte: str) -> None:
    assert markdown_to_text(markdown) == texte


def test_tableau_une_ligne_par_rangee_cellules_separees_d_une_espace() -> None:
    markdown = (
        "| Ville | Pertes |\n"
        "|---|---:|\n"
        "| Boulogne | 2 maisons |\n"
        "| Wimereux |  |\n"
        "| **Calais** | 1<br>grange |"
    )
    assert markdown_to_text(markdown) == (
        "Ville Pertes\nBoulogne 2 maisons\nWimereux\nCalais 1 grange"
    )


def test_separateur_d_une_seule_colonne() -> None:
    assert markdown_to_text("| Titre |\n|---|\n| a |") == "Titre\na"


def test_barre_verticale_dans_une_phrase_reste_du_texte() -> None:
    assert markdown_to_text("oui | non") == "oui | non"


def test_lignes_blanches_retirees_sans_saut_ajoute() -> None:
    markdown = "premier paragraphe\n\n![img-0.jpeg](img-0.jpeg)\n\n\nsecond"
    assert markdown_to_text(markdown) == "premier paragraphe\nsecond"


def test_bloc_de_code_garde_son_contenu() -> None:
    assert markdown_to_text("```\n**brut**\n```") == "**brut**"


def test_fins_de_ligne_windows() -> None:
    assert markdown_to_text("# a\r\n\r\nb\rc") == "a\nb\nc"


@pytest.mark.parametrize(
    "markdown",
    [
        "# T\n\n**a** b\n\n| x | y |\n|---|---|\n| 1 | 2 |\n\n- c\n- d",
        "ligne\nligne\n\n\n> e\n---\n![i](i)\n[f](g)",
    ],
)
def test_aucun_saut_de_ligne_ajoute_et_ordre_garde(markdown: str) -> None:
    texte = markdown_to_text(markdown)
    assert texte.count("\n") <= markdown.count("\n")
    mots = [m for m in ("T", "a", "x", "1", "c", "d", "ligne", "e", "f") if m in texte]
    positions = [texte.index(m) for m in mots]
    assert positions == sorted(positions)
    assert markdown_to_text(markdown) == texte  # déterministe


def test_texte_sans_markdown_inchange() -> None:
    texte = "Le Petit Journal, 12 mars 1894. — On annonce de Boulogne-fur-Mer"
    assert markdown_to_text(texte) == texte
