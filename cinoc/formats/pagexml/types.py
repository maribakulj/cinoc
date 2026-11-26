"""Modèle de types PAGE XML (PRIMA / Transkribus / eScriptorium).

Symétrique d'ALTO mais avec les conventions PAGE : géométrie en **polygones**
(``Coords``) + ``Baseline``, texte via ``TextEquiv > Unicode``. Régions de tout
type (``TextRegion`` + régions génériques non-texte), **imbriquées**. Niveaux
**ligne et mot** (pas de glyphe : aucun consommateur). Ordre de lecture en
**arbre** (``ReadingOrder``) avec ``flatten()`` pour les métriques séquentielles.

``coords = None`` dit « géométrie inconnue ». PAGE l'exige partout ; l'écrivain
le dit alors explicitement plutôt que d'inventer une forme (voir ``writer``).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from cinoc.formats._geometry import Point

_FROZEN = ConfigDict(frozen=True, extra="forbid")


# --- ordre de lecture (arbre) -----------------------------------------------


class ReadingOrderRef(BaseModel):
    """Référence à une région dans l'ordre de lecture."""

    model_config = _FROZEN
    kind: Literal["ref"] = "ref"
    region_ref: str


class ReadingOrderGroup(BaseModel):
    """Groupe ordonné ou non de l'ordre de lecture (récursif)."""

    model_config = _FROZEN
    kind: Literal["group"] = "group"
    id: str | None = None
    ordered: bool = True
    children: tuple[ReadingOrderNode, ...] = ()

    def flatten(self) -> tuple[str, ...]:
        """Liste plate des IDs de région, en parcours profondeur-d'abord."""
        refs: list[str] = []
        for child in self.children:
            if isinstance(child, ReadingOrderRef):
                refs.append(child.region_ref)
            else:
                refs.extend(child.flatten())
        return tuple(refs)


#: Nœud de l'arbre : référence ou sous-groupe.
ReadingOrderNode = Annotated[
    ReadingOrderRef | ReadingOrderGroup,
    Field(discriminator="kind"),
]


# --- régions -----------------------------------------------------------------


class PageWord(BaseModel):
    """Mot PAGE (``<Word>``) : texte, polygone et confiance du ``TextEquiv`` retenu.

    Lu parce qu'il porte ce que la ligne ne dit pas : la position et la
    confiance de chaque mot. Les ignorer perdait 161 et 258 mots sur deux pages
    de vérité terrain OCR-D (audit D-264)."""

    model_config = _FROZEN
    id: str | None = None
    coords: tuple[Point, ...] | None = None
    text: str = ""
    confidence: float | None = None


class PageTextLine(BaseModel):
    """Ligne PAGE (``<TextLine>``)."""

    model_config = _FROZEN
    id: str | None = None
    coords: tuple[Point, ...] | None = None
    baseline: tuple[Point, ...] | None = None
    words: tuple[PageWord, ...] = ()
    text: str = ""
    confidence: float | None = None  # conf du TextEquiv retenu


class PageTextRegion(BaseModel):
    """Région de texte PAGE (``<TextRegion>``), pouvant contenir des sous-régions."""

    model_config = _FROZEN
    kind: Literal["text"] = "text"
    id: str | None = None
    #: Attribut ``type`` ; à défaut, le ``structure {type:…;}`` de ``custom``
    #: (convention Transkribus/eScriptorium, seule place d'un type hors de
    #: l'énumération PRImA).
    region_type: str | None = None
    coords: tuple[Point, ...] | None = None
    text_lines: tuple[PageTextLine, ...] = ()
    regions: tuple[PageRegion, ...] = ()


class PageGenericRegion(BaseModel):
    """Région non-texte PAGE (Image/Separator/Graphic/Table…) — géométrie seule.

    ``region_name`` porte le nom d'élément PRImA (ex. ``"ImageRegion"``)."""

    model_config = _FROZEN
    kind: Literal["generic"] = "generic"
    region_name: str
    id: str | None = None
    region_type: str | None = None
    coords: tuple[Point, ...] | None = None
    regions: tuple[PageRegion, ...] = ()


#: Union discriminée des régions.
PageRegion = Annotated[
    PageTextRegion | PageGenericRegion,
    Field(discriminator="kind"),
]


class PagePage(BaseModel):
    """Page PAGE (``<Page>``)."""

    model_config = _FROZEN
    image_filename: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    reading_order: ReadingOrderGroup | None = None
    regions: tuple[PageRegion, ...] = ()


class PageDocument(BaseModel):
    """Document PAGE complet."""

    model_config = _FROZEN
    pages: tuple[PagePage, ...] = ()
    source_namespace: str | None = None


ReadingOrderGroup.model_rebuild()
PageTextRegion.model_rebuild()
PageGenericRegion.model_rebuild()
PagePage.model_rebuild()

__all__ = [
    "ReadingOrderRef",
    "ReadingOrderGroup",
    "ReadingOrderNode",
    "PageWord",
    "PageTextLine",
    "PageTextRegion",
    "PageGenericRegion",
    "PageRegion",
    "PagePage",
    "PageDocument",
]
