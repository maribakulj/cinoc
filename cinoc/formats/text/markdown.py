"""Markdown → texte brut : la syntaxe retirée, le texte de la page gardé.

Un OCR qui rend du markdown (Mistral OCR) écrit la **mise en forme** avec des
caractères : ``# `` d'un titre, ``**`` d'un gras, ``|---|`` d'un tableau,
``![img-0.jpeg](img-0.jpeg)`` d'une figure. Notés comme du texte, ces caractères
comptent en insertions et pénalisent le moteur pour avoir *décrit* la page. Ce
module les retire, et rien d'autre : fonction **pure** et déterministe, sur une
chaîne (zéro I/O).

**Conventions** (une ligne de markdown → au plus une ligne de texte, dans
l'ordre ; aucun saut de ligne n'est ajouté) :

- **retiré** : marqueurs de titre (``#``… et la fermeture ``#``), de citation
  (``>``), de puce (``-``, ``*``, ``+`` suivis d'une espace), d'emphase
  (``*``, ``**``, ``***``, ``_``, ``__``, ``~~`` appariés autour d'un texte non
  blanc — un astérisque isolé, appel de note d'un texte ancien, reste) et de
  code (accents graves, lignes de clôture ````` `` ``` `` ````` / ``~~~``) ;
  séparations (``---``, ``***``, ``___``, soulignés ``===``) ; images
  (``![…](…)``, entièrement : leur texte alternatif est un nom de fichier, pas
  la page) ; échappements (``\\*`` → ``*``) ; espaces de bord de ligne.
- **gardé** : le texte d'un lien (``[voir page 4](#p4)`` → ``voir page 4``) ou
  d'un lien automatique (``<https://…>`` → l'URL) ; les **numéros** de liste
  ordonnée (``1. Article premier`` : sur une page imprimée, le numéro est
  imprimé) ; le LaTeX (``$…$``), qu'aucune convention de transcription ne
  traduit.
- **tableaux** : une ligne par rangée, cellules **séparées par une espace**,
  cellules vides omises, rangée de séparation (``|---|:---:|``) retirée ; un
  ``<br>`` de cellule devient une espace. Seules les rangées qui commencent par
  ``|`` sont lues comme tableau : une barre verticale dans une phrase reste du
  texte.
- **lignes blanches** retirées : en markdown, une ligne blanche sépare deux
  paragraphes — c'est de la syntaxe, et son équivalent texte est le saut de ligne
  qui sépare déjà les deux lignes. Une ligne que le retrait a vidée (une image
  seule) disparaît de même.
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"^\s*(```|~~~)")
_THEMATIC_BREAK = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_SETEXT_EQUALS = re.compile(r"^\s{0,3}={3,}\s*$")
#: Rangée de séparation : rien que ``|``, ``-``, ``:`` et des blancs, avec au
#: moins une barre et un tiret (``|---|``, ``|:--|--:|``, ``---|---``).
_TABLE_SEPARATOR = re.compile(r"^(?=[^|]*\|)(?=[^-]*-)[\s|:\-]+$")
_BLOCKQUOTE = re.compile(r"^\s{0,3}(>\s?)+")
_HEADING = re.compile(r"^\s{0,3}#{1,6}(\s+|$)")
_HEADING_CLOSE = re.compile(r"\s+#+\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)

_IMAGE = re.compile(r"(?<!\\)!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"(?<![\\!])\[([^\]]*)\]\([^)]*\)")
_AUTOLINK = re.compile(r"<((?:https?|mailto):[^>\s]+)>")
_CODE = re.compile(r"(?<!\\)(`+)(.+?)\1")
_STAR_EMPHASIS = re.compile(r"(?<!\\)(\*{1,3})(?=\S)(.+?)(?<=[^\s\\])\1")
_UNDERSCORE_EMPHASIS = re.compile(
    r"(?<![\\\w])(_{1,3})(?=\S)(.+?)(?<=[^\s\\])\1(?!\w)"
)
_STRIKE = re.compile(r"(?<!\\)~~(?=\S)(.+?)(?<=[^\s\\])~~")
_ESCAPE = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])")


def _inline(text: str) -> str:
    """Syntaxe en ligne retirée (images, liens, code, emphase), échappements
    résolus en dernier : un ``\\*`` ne doit pas ouvrir une emphase."""
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _AUTOLINK.sub(r"\1", text)
    text = _CODE.sub(r"\2", text)
    # L'emphase s'emboîte (``***gras italique***``, ``**un _mot_**``) : on
    # retire jusqu'à stabilité — chaque passe raccourcit la chaîne, donc finit.
    while True:
        stripped = _STRIKE.sub(r"\1", text)
        stripped = _STAR_EMPHASIS.sub(r"\2", stripped)
        stripped = _UNDERSCORE_EMPHASIS.sub(r"\2", stripped)
        if stripped == text:
            break
        text = stripped
    return _ESCAPE.sub(r"\1", text)


def _table_row(line: str) -> str:
    """``| a | | b |`` → ``a b`` : cellules non vides, séparées d'une espace."""
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    cells = (_inline(_BR.sub(" ", cell)).strip() for cell in _CELL_SPLIT.split(inner))
    return " ".join(cell for cell in cells if cell)


def _line(line: str) -> str:
    """Une ligne hors bloc de code → son texte (vide = la ligne disparaît)."""
    if (
        not line.strip()
        or _THEMATIC_BREAK.match(line)
        or _SETEXT_EQUALS.match(line)
        or _TABLE_SEPARATOR.match(line)
    ):
        return ""
    line = _BLOCKQUOTE.sub("", line)
    if _HEADING.match(line):
        line = _HEADING_CLOSE.sub("", _HEADING.sub("", line))
    line = _BULLET.sub("", line)
    if line.lstrip().startswith("|"):
        return _table_row(line)
    return _inline(line).strip().rstrip("\\").rstrip()


def markdown_to_text(markdown: str) -> str:
    """Texte brut d'un markdown d'OCR (conventions : docstring du module)."""
    out: list[str] = []
    in_fence = False
    for raw in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _FENCE.match(raw):
            in_fence = not in_fence
            continue
        text = raw.strip() if in_fence else _line(raw)
        if text:
            out.append(text)
    return "\n".join(out)


__all__ = ["markdown_to_text"]
