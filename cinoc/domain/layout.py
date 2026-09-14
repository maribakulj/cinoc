"""``CanonicalLayout`` — modèle de mise en page **neutre** (ALTO/PAGE unifiés).

Payload de ``ArtifactType.LAYOUT``. Type **pivot** (axe 1, enveloppe) :
dimensionné pour représenter *fidèlement* ALTO **et** PAGE — mots, géométrie
(bbox + polygone), baseline, confiance, régions imbriquées, ordre de lecture —
même si la tranche segmentation **ne remplit d'abord** que régions → lignes →
texte (le reste arrive avec les mappers `alto/page → layout`, différés).

Géométrie en `domain` (et non en `formats`) : un point/une boîte neutres sont du
**vocabulaire transversal**, pas une spécificité de format. ``Point`` y est le
même alias structurel que ``formats._geometry.Point`` (``tuple[int, int]``) — une
coïncidence de forme, **pas** un shim (aucune conversion).

Convention de coordonnées : pixels entiers, origine haut-gauche, *y* vers le bas
(image). Valeurs négatives tolérées (une région peut déborder la page). La
réconciliation d'unités/résolution est une affaire de couche 3.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")

#: Point image : ``(x, y)`` en pixels entiers (origine haut-gauche).
Point = tuple[int, int]


class BBox(BaseModel):
    """Boîte englobante axis-aligned (pixels)."""

    model_config = _FROZEN
    x: int
    y: int
    width: int
    height: int


class Geometry(BaseModel):
    """Géométrie d'un élément : boîte et/ou polygone (au moins l'un)."""

    model_config = _FROZEN
    bbox: BBox | None = None
    polygon: tuple[Point, ...] = ()


class Word(BaseModel):
    """Mot (granularité ALTO ``<String>`` ; absent de PAGE → tuple vide)."""

    model_config = _FROZEN
    text: str
    geometry: Geometry | None = None
    confidence: float | None = None
    #: ``SUBS_TYPE`` ALTO (``HypPart1``/``HypPart2``/``Abbreviation``…) et son
    #: ``SUBS_CONTENT``. Portés ici parce que la césure est une propriété du
    #: **mot** en ALTO, et parce qu'un post-correcteur qui recolle un mot coupé
    #: en a besoin : sans eux, un aller-retour par ``CanonicalLayout`` perd
    #: quelle ligne continue quelle autre.
    subs_type: str | None = None
    subs_content: str | None = None


class Line(BaseModel):
    """Ligne de texte. ``text`` est le contenu reconnu ; ``words`` l'affine."""

    model_config = _FROZEN
    id: str | None = None
    text: str = ""
    geometry: Geometry | None = None
    baseline: tuple[Point, ...] = ()
    words: tuple[Word, ...] = ()
    confidence: float | None = None


class Region(BaseModel):
    """Région de page (bloc). ``region_type`` = label neutre libre
    (``"text"``/``"image"``/``"table"``…). ``regions`` porte l'imbrication
    (ALTO ``ComposedBlock`` / PAGE régions imbriquées).

    Une sortie de **segmentation** est une région **sans lignes** (``lines=()``) ;
    la **reconnaissance** la remplit. C'est ce qui distingue « niveau structure
    présent » de « niveau texte présent » (cf. métriques par bloc).
    """

    model_config = _FROZEN
    id: str = Field(min_length=1, max_length=256)
    region_type: str | None = Field(default=None, max_length=64)
    geometry: Geometry | None = None
    lines: tuple[Line, ...] = ()
    regions: tuple[Region, ...] = ()


class LayoutPage(BaseModel):
    """Page : dimensions, régions de premier niveau, ordre de lecture.

    ``reading_order`` = liste **plate** d'``id`` de région (parcours profondeur
    d'abord côté PAGE) ; vide → ordre des ``regions``.
    """

    model_config = _FROZEN
    width: int | None = None
    height: int | None = None
    regions: tuple[Region, ...] = ()
    reading_order: tuple[str, ...] = ()

    def leaf_regions(self) -> tuple[Region, ...]:
        """Régions **atomiques**, imbrication aplatie.

        Un bloc composé (ALTO ``ComposedBlock``) porte ses lignes dans ses
        enfants, pas à son niveau : qui lit ``regions`` sans descendre voit des
        régions vides et conclut à une page blanche. Ce fut le cas — toute mise
        en page issue de Tesseract se projetait en texte vide, sans un
        avertissement, parce que trois modules descendaient et un quatrième non.

        Accesseur du type lui-même, comme ``PipelineSpec.step_by_id`` : c'est le
        modèle qui explique sa propre forme, pas un calcul métier.
        """
        return _leaves(self.regions)


def _leaves(regions: tuple[Region, ...]) -> tuple[Region, ...]:
    out: list[Region] = []
    for region in regions:
        if region.regions:
            out.extend(_leaves(region.regions))
        else:
            out.append(region)
    return tuple(out)


class CanonicalLayout(BaseModel):
    """Document de mise en page neutre : une ou plusieurs pages.

    Le squelette segmentation remplit **une** page ; le multi-page est réservé
    pour la fidélité ALTO/PAGE (documents multi-pages).
    """

    model_config = _FROZEN
    pages: tuple[LayoutPage, ...] = ()


Region.model_rebuild()
LayoutPage.model_rebuild()
CanonicalLayout.model_rebuild()

__all__ = [
    "BBox",
    "CanonicalLayout",
    "Geometry",
    "Line",
    "LayoutPage",
    "Point",
    "Region",
    "Word",
]
