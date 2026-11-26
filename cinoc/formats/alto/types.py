"""Modèle de types ALTO — représentation interne, source de vérité structurelle.

Géométrie **numérique native** : ``bbox`` (HPOS/VPOS/WIDTH/HEIGHT), ``polygon``
(Shape/Polygon) et ``baseline`` (BASELINE). Régions de tout type : ``TextBlock``,
``ComposedBlock`` (récursif), ``Illustration``, ``GraphicalElement``. Confidence de
mot (``WC``) conservée. Ordre de lecture = ordre des blocs (document).

Modèles pydantic figés : ces types sont la cible **permanente** du parsing ; le
modèle neutre ``CanonicalLayout`` (plus tard) est en aval via adaptateur.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from cinoc.formats._geometry import Point

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class AltoBBox(BaseModel):
    """Boîte englobante ALTO (pixels ; valeurs négatives conservées)."""

    model_config = _FROZEN
    hpos: int
    vpos: int
    width: int
    height: int


class AltoString(BaseModel):
    """Mot ALTO (``<String>``)."""

    model_config = _FROZEN
    content: str
    id: str | None = None
    bbox: AltoBBox | None = None
    confidence: float | None = None  # attribut WC
    subs_type: str | None = None  # césure : HypPart1/HypPart2, Abbreviation…
    subs_content: str | None = None


class AltoLine(BaseModel):
    """Ligne ALTO (``<TextLine>``)."""

    model_config = _FROZEN
    id: str | None = None
    bbox: AltoBBox | None = None
    polygon: tuple[Point, ...] | None = None
    baseline: tuple[Point, ...] | None = None
    strings: tuple[AltoString, ...] = ()
    #: Texte logique de la ligne, reconstruit des enfants ``String``/``SP``/
    #: ``HYP`` au parsing. ``strings`` seul ne suffit pas : l'espace ALTO est
    #: **explicite** (``<SP>``) et le tiret de coupure est un élément frère
    #: (``<HYP>``), donc recoller les ``String`` par une espace invente des
    #: blancs et perd la marque de césure. Vide pour un document construit
    #: sans parser — les consommateurs retombent alors sur la jointure.
    text: str = ""


class AltoTextBlock(BaseModel):
    """Bloc de texte ALTO (``<TextBlock>``)."""

    model_config = _FROZEN
    kind: Literal["text"] = "text"
    id: str | None = None
    #: Type de bloc. Lu sur ``TYPE`` (ALTO 2/3) ou sur l'``OtherTag`` que
    #: désigne ``TAGREFS`` ; écrit **toujours** par ``TAGREFS`` + ``<Tags>``,
    #: ALTO 4 interdisant ``TextBlock@TYPE``.
    block_type: str | None = None
    bbox: AltoBBox | None = None
    polygon: tuple[Point, ...] | None = None
    lines: tuple[AltoLine, ...] = ()


class AltoIllustration(BaseModel):
    """Illustration ALTO (``<Illustration>``) — géométrie seule."""

    model_config = _FROZEN
    kind: Literal["illustration"] = "illustration"
    id: str | None = None
    block_type: str | None = None
    bbox: AltoBBox | None = None
    polygon: tuple[Point, ...] | None = None


class AltoGraphicalElement(BaseModel):
    """Élément graphique ALTO (``<GraphicalElement>``) — géométrie seule."""

    model_config = _FROZEN
    kind: Literal["graphical"] = "graphical"
    id: str | None = None
    bbox: AltoBBox | None = None
    polygon: tuple[Point, ...] | None = None


class AltoComposedBlock(BaseModel):
    """Bloc composé ALTO (``<ComposedBlock>``) — conteneur récursif de blocs."""

    model_config = _FROZEN
    kind: Literal["composed"] = "composed"
    id: str | None = None
    block_type: str | None = None
    bbox: AltoBBox | None = None
    polygon: tuple[Point, ...] | None = None
    blocks: tuple[AltoBlock, ...] = ()


#: Union discriminée des blocs (le champ ``kind`` choisit le type).
AltoBlock = Annotated[
    AltoTextBlock | AltoComposedBlock | AltoIllustration | AltoGraphicalElement,
    Field(discriminator="kind"),
]


class AltoPage(BaseModel):
    """Page ALTO (``<Page>`` ; ``blocks`` = contenu du ``PrintSpace``)."""

    model_config = _FROZEN
    id: str | None = None
    width: int | None = None
    height: int | None = None
    #: ``PHYSICAL_IMG_NR`` — rang de l'image dans le document (requis par
    #: ALTO 4 ; l'écrivain retombe sur le rang de la page s'il manque).
    physical_img_nr: float | None = None
    blocks: tuple[AltoBlock, ...] = ()


class AltoDocument(BaseModel):
    """Document ALTO complet."""

    model_config = _FROZEN
    pages: tuple[AltoPage, ...] = ()
    source_version: str | None = None  # "v2"/"v3"/"v4"/"none"
    measurement_unit: str | None = None  # pixel / mm10 / inch1200…


AltoComposedBlock.model_rebuild()
AltoPage.model_rebuild()

__all__ = [
    "AltoBBox",
    "AltoString",
    "AltoLine",
    "AltoTextBlock",
    "AltoComposedBlock",
    "AltoIllustration",
    "AltoGraphicalElement",
    "AltoBlock",
    "AltoPage",
    "AltoDocument",
]
