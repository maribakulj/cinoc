"""Writer PAGE XML 2019 déterministe (lxml + C14N2). Symétrique du writer ALTO.

Sérialise un ``PageDocument`` en octets PAGE 2019-07-15, **conformes au XSD
officiel de PRImA** (vérifié en test contre le schéma vendorisé, arbitrage A9 —
jamais à l'exécution). Une seule cible, comme pour ALTO (D-272) : un PAGE 2013
lu est réécrit en 2019 ; rien dans le banc n'écrivait le 2013 hors des tests.

Ce que le XSD exige et que le document peut ne pas porter est **dérivé** ou
**dit absent**, jamais inventé :

- ``Metadata`` : ``Creator`` = ``Cinoc``, ``Created`` = ``LastChange`` =
  ``1970-01-01T00:00:00Z``. Une date **fixe**, et visiblement pas celle de
  l'écriture : un horodatage réel changerait l'empreinte de l'artefact à chaque
  run, contre l'invariant de déterminisme (``CLAUDE.md`` §12) ;
- les identifiants (région, ligne, mot, groupe d'ordre de lecture) manquants,
  en double ou qui ne sont pas des ``NCName`` → ``region_<n>``, ``line_<n>``,
  ``word_<n>``, ``ro_<n>``, hors des identifiants déjà pris ; les références
  de l'ordre de lecture suivent le renommage, celles qui ne mènent à aucune
  région écrite sont retirées (``IDREF`` les exige résolues) ;
- ``imageFilename`` inconnu → chaîne vide (« pas de nom », relue ``None``) ;
  des **dimensions** inconnues, elles, font refuser l'écriture : ``0`` serait
  une mesure fausse, pas une absence ;
- une géométrie inconnue → ``<Coords points="0,0 0,0"/>`` **marqué**
  ``custom="coords {absent:true;}"``, que relit le parser. PAGE exige des
  coordonnées partout et n'a aucune façon de dire « inconnues » ; ne pas
  émettre l'élément perdrait son texte, et lui prêter la forme de son parent
  serait une géométrie inventée. Le polygone nul ne couvre aucune surface : il
  ne prétend rien, et la marque le dit à qui la lit ;
- un type de région hors de l'énumération PRImA (``TextRegion@type``,
  ``GraphicRegion@type``) ou porté par un élément sans attribut ``type`` →
  ``custom="structure {type:…;}"``, la convention de Transkribus et
  d'eScriptorium, relue par le parser.

Ce que le XSD interdit et que le modèle tolère est **ramené** avec un
avertissement : coordonnée négative → 0 (PAGE est borné à l'image), confiance
hors de [0, 1] → omise, ligne de base d'un seul point → omise.

Garantie : ``parse_pagexml(write_pagexml(doc)) == doc`` pour un document
**complet** (une page aux dimensions connues, identifiants présents et uniques,
``source_namespace`` 2019) ; pour tout document écrivable, ``write_pagexml`` est
un point fixe dès le second passage.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from lxml import etree

from cinoc.domain.errors import FormatError
from cinoc.formats._geometry import Point, format_points
from cinoc.formats.pagexml.types import (
    PageDocument,
    PagePage,
    PageRegion,
    PageTextLine,
    PageTextRegion,
    PageWord,
    ReadingOrderGroup,
    ReadingOrderRef,
)

logger = logging.getLogger(__name__)

PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"

_CREATOR = "Cinoc"
_FIXED_TIMESTAMP = "1970-01-01T00:00:00Z"
_NULL_POINTS = "0,0 0,0"

#: Éléments de région de PAGE 2019 (``RegionType`` et ``PageType``).
REGION_ELEMENTS = frozenset(
    {
        "TextRegion", "ImageRegion", "LineDrawingRegion", "GraphicRegion",
        "TableRegion", "ChartRegion", "MapRegion", "SeparatorRegion",
        "MathsRegion", "ChemRegion", "MusicRegion", "AdvertRegion",
        "NoiseRegion", "UnknownRegion", "CustomRegion",
    }
)

#: ``TextTypeSimpleType`` et ``GraphicsTypeSimpleType`` : les seuls ``type``
#: énumérés qu'on écrit en attribut.
_TYPE_ENUMS: dict[str, frozenset[str]] = {
    "TextRegion": frozenset(
        {
            "paragraph", "heading", "caption", "header", "footer",
            "page-number", "drop-capital", "credit", "floating",
            "signature-mark", "catch-word", "marginalia", "footnote",
            "footnote-continued", "endnote", "TOC-entry", "list-label", "other",
        }
    ),
    "GraphicRegion": frozenset(
        {
            "logo", "letterhead", "decoration", "frame",
            "handwritten-annotation", "stamp", "signature", "barcode",
            "paper-grow", "punch-hole", "other",
        }
    ),
}


class PageWriteError(FormatError):
    """Écriture PAGE impossible sans écrire faux (page absente ou multiple,
    dimensions inconnues, unité non pixel, élément de région inconnu)."""


def _q(local: str) -> str:
    return f"{{{PAGE_NS}}}{local}"


def _is_ncname(value: str) -> bool:
    """``value`` est-il un ``NCName`` (forme d'un ``xsd:ID``) ?"""
    if not value or "{" in value:
        return False
    try:
        etree.QName(value)
    except ValueError:
        return False
    return True


def _escape(value: str) -> str:
    """Échappe ce que la syntaxe ``custom`` réserve (``\\uXXXX``)."""
    return "".join(f"\\u{ord(c):04x}" if c in "\\;{}" else c for c in value)


def _walk(regions: tuple[PageRegion, ...]) -> Iterator[PageRegion]:
    for region in regions:
        yield region
        yield from _walk(region.regions)


def _groups(group: ReadingOrderGroup) -> Iterator[ReadingOrderGroup]:
    yield group
    for child in group.children:
        if isinstance(child, ReadingOrderGroup):
            yield from _groups(child)


def _valid_ids(page: PagePage) -> set[str]:
    found: list[str | None] = []
    for region in _walk(page.regions):
        found.append(region.id)
        if isinstance(region, PageTextRegion):
            for line in region.text_lines:
                found.append(line.id)
                found.extend(word.id for word in line.words)
    if page.reading_order is not None:
        found.extend(group.id for group in _groups(page.reading_order))
    return {i for i in found if i is not None and _is_ncname(i)}


class _Writer:
    """État d'une sérialisation : identifiants écrits, renommages de région."""

    def __init__(self, page: PagePage) -> None:
        self._reserved = _valid_ids(page)
        self._emitted: set[str] = set()
        self._next: dict[str, int] = {}
        self.region_ids: dict[str, str] = {}

    def ident(self, original: str | None, prefix: str) -> str:
        if (
            original is not None
            and original not in self._emitted
            and _is_ncname(original)
        ):
            self._emitted.add(original)
            return original
        n = self._next.get(prefix, 1)
        while f"{prefix}{n}" in self._reserved or f"{prefix}{n}" in self._emitted:
            n += 1
        self._next[prefix] = n + 1
        fresh = f"{prefix}{n}"
        self._emitted.add(fresh)
        if original is not None:
            logger.warning(
                "[page] identifiant %r invalide ou en double, écrit %r", original, fresh
            )
        return fresh

    # --- géométrie et texte -------------------------------------------------

    def coords(
        self, el: etree._Element, points: tuple[Point, ...] | None
    ) -> list[str]:
        """Écrit ``<Coords>`` ; rend l'entrée ``custom`` à poser s'il en faut une."""
        coords = etree.SubElement(el, _q("Coords"))
        if not points:
            coords.set("points", _NULL_POINTS)
            return ["coords {absent:true;}"]
        coords.set("points", _points(points))
        return []

    def text_equiv(self, el: etree._Element, text: str, conf: float | None) -> None:
        text_equiv = etree.SubElement(el, _q("TextEquiv"))
        text_equiv.set("index", "0")
        if conf is not None:
            if 0.0 <= conf <= 1.0:
                text_equiv.set("conf", str(conf))
            else:
                logger.warning("[page] confiance %r hors de [0, 1], omise", conf)
        etree.SubElement(text_equiv, _q("Unicode")).text = text

    # --- structure ----------------------------------------------------------

    def word(self, parent: etree._Element, word: PageWord) -> None:
        el = etree.SubElement(parent, _q("Word"))
        el.set("id", self.ident(word.id, "word_"))
        _set_custom(el, self.coords(el, word.coords))
        self.text_equiv(el, word.text, word.confidence)

    def line(self, parent: etree._Element, line: PageTextLine) -> None:
        el = etree.SubElement(parent, _q("TextLine"))
        el.set("id", self.ident(line.id, "line_"))
        custom = self.coords(el, line.coords)
        if line.baseline is not None:
            if len(line.baseline) >= 2:
                baseline = etree.SubElement(el, _q("Baseline"))
                baseline.set("points", _points(line.baseline))
            else:
                logger.warning("[page] ligne de base d'un point, omise : %r", line.id)
        for word in line.words:
            self.word(el, word)
        self.text_equiv(el, line.text, line.confidence)
        _set_custom(el, custom)

    def region(self, parent: etree._Element, region: PageRegion) -> None:
        name = (
            "TextRegion" if isinstance(region, PageTextRegion) else region.region_name
        )
        if name not in REGION_ELEMENTS:
            raise PageWriteError(f"élément de région PAGE inconnu : {name!r}")
        el = etree.SubElement(parent, _q(name))
        written = self.ident(region.id, "region_")
        el.set("id", written)
        if region.id is not None:
            self.region_ids.setdefault(region.id, written)
        custom = self.coords(el, region.coords)
        if region.region_type is not None:
            if region.region_type in _TYPE_ENUMS.get(name, frozenset()):
                el.set("type", region.region_type)
            else:
                custom.insert(0, f"structure {{type:{_escape(region.region_type)};}}")
        _set_custom(el, custom)
        # Le XSD place les sous-régions (``RegionType``) avant les lignes
        # (extension ``TextRegionType``).
        for child in region.regions:
            self.region(el, child)
        if isinstance(region, PageTextRegion):
            for line in region.text_lines:
                self.line(el, line)

    def group(
        self, parent: etree._Element, group: ReadingOrderGroup, index: int | None
    ) -> None:
        suffix = "Indexed" if index is not None else ""
        name = ("OrderedGroup" if group.ordered else "UnorderedGroup") + suffix
        el = etree.Element(_q(name))
        if index is not None:
            el.set("index", str(index))
        el.set("id", self.ident(group.id, "ro_"))
        position = 0
        for child in group.children:
            child_index = position if group.ordered else None
            if isinstance(child, ReadingOrderRef):
                target = self.region_ids.get(child.region_ref)
                if target is None:
                    logger.warning(
                        "[page] ordre de lecture : %r ne désigne aucune région, "
                        "retiré",
                        child.region_ref,
                    )
                    continue
                ref = etree.SubElement(
                    el, _q("RegionRefIndexed" if group.ordered else "RegionRef")
                )
                if child_index is not None:
                    ref.set("index", str(child_index))
                ref.set("regionRef", target)
            else:
                before = len(el)
                self.group(el, child, child_index)
                if len(el) == before:
                    continue
            position += 1
        # Un groupe vide est invalide (``choice minOccurs=1``) : il ne s'écrit pas.
        if len(el):
            parent.append(el)

    def page(self, root: etree._Element, page: PagePage) -> None:
        if page.image_width is None or page.image_height is None:
            raise PageWriteError(
                "dimensions de la page inconnues : PAGE les exige, et 0 serait "
                "une mesure fausse."
            )
        el = etree.SubElement(root, _q("Page"))
        el.set("imageFilename", page.image_filename or "")
        el.set("imageWidth", str(page.image_width))
        el.set("imageHeight", str(page.image_height))
        for region in page.regions:
            self.region(el, region)
        if page.reading_order is not None:
            order = etree.Element(_q("ReadingOrder"))
            self.group(order, page.reading_order, None)
            if len(order):
                el.insert(0, order)


def _set_custom(el: etree._Element, entries: list[str]) -> None:
    if entries:
        el.set("custom", " ".join(entries))


def _points(points: tuple[Point, ...]) -> str:
    if any(x < 0 or y < 0 for x, y in points):
        logger.warning("[page] coordonnées négatives ramenées à 0 (bord de l'image)")
        points = tuple((max(x, 0), max(y, 0)) for x, y in points)
    if len(points) == 1:  # ``PointsType`` exige deux points : un point dégénéré
        points = points * 2
    return format_points(points)


def _metadata(root: etree._Element) -> None:
    metadata = etree.SubElement(root, _q("Metadata"))
    etree.SubElement(metadata, _q("Creator")).text = _CREATOR
    etree.SubElement(metadata, _q("Created")).text = _FIXED_TIMESTAMP
    etree.SubElement(metadata, _q("LastChange")).text = _FIXED_TIMESTAMP


def write_pagexml(document: PageDocument) -> bytes:
    """Sérialise un ``PageDocument`` d'**une** page en PAGE 2019 canonique (C14N2).

    Lève ``PageWriteError`` quand le document ne s'écrit pas sans écrire faux :
    PAGE porte exactement une page par fichier, aux dimensions connues.
    """
    if len(document.pages) != 1:
        raise PageWriteError(
            f"PAGE porte une page par fichier ; le document en a "
            f"{len(document.pages)}."
        )
    root = etree.Element(_q("PcGts"), nsmap={None: PAGE_NS})  # type: ignore[dict-item]
    _metadata(root)
    page = document.pages[0]
    _Writer(page).page(root, page)
    return etree.tostring(root, method="c14n2")


__all__ = ["write_pagexml", "PageWriteError", "PAGE_NS", "REGION_ELEMENTS"]
