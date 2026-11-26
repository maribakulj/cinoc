"""Parser ALTO tolérant (v2/v3/v4), via l'entonnoir ``safe_parse_xml``.

Extrait toute la structure mesurable : régions de tout type (TextBlock,
ComposedBlock récursif, Illustration, GraphicalElement), géométrie numérique
(bbox + polygone + baseline), confidence de mot. Les éléments non modélisés
(contenu de marge…) sont signalés par un ``warning``, jamais perdus en silence.

Tolérant **par décision** (arbitrage A9) : la vérité terrain réelle n'est pas
toujours conforme au XSD, et rien n'est validé à l'entrée. Le type d'un
``TextBlock`` se lit sur ``TYPE`` (ALTO 2/3, ou fichiers non conformes) puis,
à défaut, sur l'``OtherTag`` que désigne ``TAGREFS`` — la forme qu'ALTO 4
permet, et celle qu'écrivent eScriptorium et ``write_alto``.
"""

from __future__ import annotations

import logging
import math

from lxml import etree

from cinoc.domain.errors import FormatError
from cinoc.formats._geometry import Point, parse_points
from cinoc.formats._xml import safe_parse_xml
from cinoc.formats.alto.types import (
    AltoBBox,
    AltoBlock,
    AltoComposedBlock,
    AltoDocument,
    AltoGraphicalElement,
    AltoIllustration,
    AltoLine,
    AltoPage,
    AltoString,
    AltoTextBlock,
)

logger = logging.getLogger(__name__)

_MARGINS = {"TopMargin", "LeftMargin", "RightMargin", "BottomMargin"}
_BLOCK_NAMES = {"TextBlock", "ComposedBlock", "Illustration", "GraphicalElement"}


class AltoParseError(FormatError):
    """ALTO illisible (XML invalide, vide, DOCTYPE interdit, ou sans page)."""


def _lname(el: etree._Element) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _detect_version(tag: str) -> str | None:
    namespace = etree.QName(tag).namespace
    if namespace is None:
        return "none"
    for marker in ("ns-v2", "ns-v3", "ns-v4"):
        if marker in namespace:
            return marker.replace("ns-", "")
    return None


def _int_attr(el: etree._Element, name: str) -> int | None:
    raw = el.get(name)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _float_attr(el: etree._Element, name: str) -> float | None:
    raw = el.get(name)
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _bbox(el: etree._Element) -> AltoBBox | None:
    hpos = _int_attr(el, "HPOS")
    vpos = _int_attr(el, "VPOS")
    width = _int_attr(el, "WIDTH")
    height = _int_attr(el, "HEIGHT")
    if hpos is None or vpos is None or width is None or height is None:
        return None
    return AltoBBox(hpos=hpos, vpos=vpos, width=width, height=height)


def _points_attr(el: etree._Element, name: str) -> tuple[Point, ...] | None:
    raw = el.get(name)
    if raw is None:
        return None
    try:
        return parse_points(raw)
    except ValueError:
        logger.warning("[alto] %s illisible, géométrie ignorée : %r", name, raw)
        return None


def _polygon(el: etree._Element) -> tuple[Point, ...] | None:
    for shape in el:
        if _lname(shape) == "Shape":
            for poly in shape:
                if _lname(poly) == "Polygon":
                    return _points_attr(poly, "POINTS")
    return None


def _parse_string(el: etree._Element) -> AltoString:
    confidence: float | None = None
    wc = el.get("WC")
    if wc is not None:
        try:
            confidence = float(wc)
        except ValueError:
            confidence = None
    return AltoString(
        content=el.get("CONTENT", ""),
        id=el.get("ID"),
        bbox=_bbox(el),
        confidence=confidence,
        subs_type=el.get("SUBS_TYPE"),
        subs_content=el.get("SUBS_CONTENT"),
    )


#: Marques de coupure de mot rencontrées en fin de ligne. Une ``<HYP>`` qui
#: répète une marque déjà présente dans le ``CONTENT`` du ``String`` précédent
#: ne doit être rendue qu'une fois.
_BREAK_MARKS = ("-", "\u00ad", "\u2010", "\u2011", "\u2013", "\u00ac", "\u2e17")


def _reconstruct_text(el: etree._Element) -> str:
    """Texte logique d'une ``<TextLine>`` : ``String`` + ``SP`` + ``HYP``.

    Les trois règles d'ALTO, qu'une jointure par espaces ne peut pas deviner :
    un ``String`` rend son ``CONTENT`` **verbatim** (deux ``String`` voisins
    sans ``SP`` sont collés — ``L``+``r``+``s`` est ``Lrs``, pas ``L r s``) ;
    un ``SP`` rend **une** espace ; un ``HYP`` rend son ``CONTENT`` (défaut
    ``-``), le tiret conditionnel U+00AD étant ramené à ``-``.
    """
    out: list[str] = []
    for child in el:
        name = _lname(child)
        if name == "String":
            out.append(child.get("CONTENT", ""))
        elif name == "SP":
            out.append(" ")
        elif name == "HYP":
            mark = child.get("CONTENT") or "-"
            if mark == "\u00ad":
                mark = "-"
            # Un producteur qui écrit la marque dans le String ET émet un HYP
            # veut une marque, pas deux.
            if not "".join(out).rstrip().endswith(_BREAK_MARKS):
                out.append(mark)
    return "".join(out).replace("\r", "").strip()


def _parse_line(el: etree._Element) -> AltoLine:
    strings = tuple(_parse_string(c) for c in el if _lname(c) == "String")
    return AltoLine(
        id=el.get("ID"),
        bbox=_bbox(el),
        polygon=_polygon(el),
        baseline=_points_attr(el, "BASELINE"),
        strings=strings,
        text=_reconstruct_text(el),
    )


#: ``ID`` d'``OtherTag`` → son ``LABEL`` (``<Tags>`` du document).
_TagLabels = dict[str, str]


def _tag_labels(root: etree._Element) -> _TagLabels:
    return {
        tag_id: tag.get("LABEL", "")
        for tag in root.iter()
        if isinstance(tag.tag, str)
        and _lname(tag) == "OtherTag"
        and (tag_id := tag.get("ID")) is not None
    }


def _block_type(el: etree._Element, tags: _TagLabels) -> str | None:
    if (declared := el.get("TYPE")) is not None:
        return declared
    for ref in (el.get("TAGREFS") or "").split():
        if tags.get(ref):
            return tags[ref]
    return None


def _parse_text_block(el: etree._Element, tags: _TagLabels) -> AltoTextBlock:
    lines = tuple(_parse_line(c) for c in el if _lname(c) == "TextLine")
    return AltoTextBlock(
        id=el.get("ID"),
        block_type=_block_type(el, tags),
        bbox=_bbox(el),
        polygon=_polygon(el),
        lines=lines,
    )


def _parse_composed(el: etree._Element, tags: _TagLabels) -> AltoComposedBlock:
    return AltoComposedBlock(
        id=el.get("ID"),
        block_type=el.get("TYPE"),
        bbox=_bbox(el),
        polygon=_polygon(el),
        blocks=_parse_blocks(el, tags),
    )


def _parse_blocks(parent: etree._Element, tags: _TagLabels) -> tuple[AltoBlock, ...]:
    out: list[AltoBlock] = []
    for child in parent:
        name = _lname(child)
        if name == "TextBlock":
            out.append(_parse_text_block(child, tags))
        elif name == "ComposedBlock":
            out.append(_parse_composed(child, tags))
        elif name == "Illustration":
            out.append(
                AltoIllustration(
                    id=child.get("ID"),
                    block_type=child.get("TYPE"),
                    bbox=_bbox(child),
                    polygon=_polygon(child),
                )
            )
        elif name == "GraphicalElement":
            out.append(
                AltoGraphicalElement(
                    id=child.get("ID"),
                    bbox=_bbox(child),
                    polygon=_polygon(child),
                )
            )
    return tuple(out)


def _parse_page(el: etree._Element, tags: _TagLabels) -> AltoPage:
    print_space: etree._Element | None = None
    for child in el:
        name = _lname(child)
        if name == "PrintSpace":
            print_space = child
        elif name in _MARGINS and any(_lname(g) in _BLOCK_NAMES for g in child):
            logger.warning("[alto] contenu de %s non modélisé (ignoré)", name)
    container = print_space if print_space is not None else el
    return AltoPage(
        id=el.get("ID"),
        width=_int_attr(el, "WIDTH"),
        height=_int_attr(el, "HEIGHT"),
        physical_img_nr=_float_attr(el, "PHYSICAL_IMG_NR"),
        blocks=_parse_blocks(container, tags),
    )


def parse_alto(data: bytes) -> AltoDocument:
    """Parse des octets ALTO en ``AltoDocument`` (lève ``AltoParseError``)."""
    root = safe_parse_xml(data)
    if root is None:
        raise AltoParseError("ALTO illisible (XML invalide, vide ou DOCTYPE interdit).")

    version = _detect_version(root.tag) if isinstance(root.tag, str) else None

    measurement_unit: str | None = None
    for el in root.iter():
        if isinstance(el.tag, str) and _lname(el) == "MeasurementUnit":
            measurement_unit = (el.text or "").strip() or None
            break

    tags = _tag_labels(root)
    pages = tuple(
        _parse_page(el, tags)
        for el in root.iter()
        if isinstance(el.tag, str) and _lname(el) == "Page"
    )
    return AltoDocument(
        pages=pages, source_version=version, measurement_unit=measurement_unit
    )


__all__ = ["parse_alto", "AltoParseError"]
