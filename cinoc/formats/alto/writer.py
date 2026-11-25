"""Writer ALTO 4 déterministe (lxml + canonicalisation C14N).

Sérialise un ``AltoDocument`` (construit par nous) en octets ALTO 4, **conformes
au XSD officiel ALTO 4.4** (vérifié en test contre le schéma de loc.gov,
arbitrage A9 — jamais à l'exécution). Le C14N2 fixe l'ordre des attributs et la
forme des namespaces → sortie **déterministe** (cache d'artefacts, round-trip).
Construction sans état global → thread-safe.

Une seule cible : ALTO 4, la seule que produit le banc (l'``AltoAssembler``).
Écrire l'espace de noms v2 ou v3 n'avait que des tests pour consommateurs, et
aucune de ces sorties n'était valide dans sa version (ALTO 2 exige la géométrie
de chaque bloc, que la lecture tolérante ne garantit pas).

Ce que le XSD exige et que le document peut ne pas porter est **dérivé**, de
façon déterministe, jamais horodaté :

- ``Page@ID`` et l'``ID`` de bloc manquants → ``page_<n>`` / ``block_<n>``,
  choisis hors des identifiants déjà présents (``xsd:ID`` est unique) ;
- ``Page@PHYSICAL_IMG_NR`` manquant → le rang de la page dans le document ;
- le type d'un ``TextBlock`` → ``TAGREFS`` vers un ``<OtherTag>`` de ``<Tags>``
  (``LABEL`` = le type), ALTO 4 interdisant ``TextBlock@TYPE``. C'est la
  convention d'export d'eScriptorium, que relit le parser.

Garantie : ``parse_alto(write_alto(doc)) == doc`` pour un document **complet**
(pages et blocs identifiés, ``physical_img_nr`` présent, ``source_version``
``"v4"``) ; pour tout document, ``write_alto`` est un point fixe dès le second
passage.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from lxml import etree

from cinoc.formats._geometry import format_points
from cinoc.formats.alto.types import (
    AltoBBox,
    AltoBlock,
    AltoComposedBlock,
    AltoDocument,
    AltoIllustration,
    AltoLine,
    AltoPage,
    AltoString,
    AltoTextBlock,
)

logger = logging.getLogger(__name__)

_NS = "http://www.loc.gov/standards/alto/ns-v4#"

#: Valeurs de ``MeasurementUnitType`` (ALTO 4).
_UNITS = frozenset({"pixel", "mm10", "inch1200"})

#: ``DESCRIPTION`` des ``OtherTag`` de type de bloc (convention eScriptorium).
_BLOCK_TYPE_TAG = "block type"


def _q(local: str) -> str:
    return f"{{{_NS}}}{local}"


def _number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


class _Ids:
    """Identifiants que le XSD exige et que le document ne porte pas."""

    def __init__(self, used: set[str]) -> None:
        self._used = used
        self._next: dict[str, int] = {}

    def fresh(self, prefix: str) -> str:
        n = self._next.get(prefix, 1)
        while f"{prefix}{n}" in self._used:
            n += 1
        self._next[prefix] = n + 1
        self._used.add(f"{prefix}{n}")
        return f"{prefix}{n}"


def _walk(blocks: tuple[AltoBlock, ...]) -> Iterator[AltoBlock]:
    for block in blocks:
        yield block
        if isinstance(block, AltoComposedBlock):
            yield from _walk(block.blocks)


def _existing_ids(document: AltoDocument) -> set[str]:
    used: set[str] = set()
    for page in document.pages:
        used.add(page.id or "")
        for block in _walk(page.blocks):
            used.add(block.id or "")
            if isinstance(block, AltoTextBlock):
                for line in block.lines:
                    used.add(line.id or "")
                    used.update(s.id or "" for s in line.strings)
    used.discard("")
    return used


class _Writer:
    """État d'une sérialisation : identifiants dérivés et étiquettes de type."""

    def __init__(self, document: AltoDocument) -> None:
        self._ids = _Ids(_existing_ids(document))
        types = sorted(
            {
                block.block_type
                for page in document.pages
                for block in _walk(page.blocks)
                if isinstance(block, AltoTextBlock) and block.block_type
            }
        )
        self.type_tags = {label: self._ids.fresh("BT") for label in types}

    def block_id(self, block: AltoBlock) -> str:
        return block.id or self._ids.fresh("block_")

    def page_id(self, page: AltoPage) -> str:
        return page.id or self._ids.fresh("page_")


def _set_bbox(el: etree._Element, bbox: AltoBBox | None) -> None:
    if bbox is None:
        return
    el.set("HPOS", str(bbox.hpos))
    el.set("VPOS", str(bbox.vpos))
    el.set("WIDTH", str(bbox.width))
    el.set("HEIGHT", str(bbox.height))


def _write_polygon(
    parent: etree._Element, polygon: tuple[tuple[int, int], ...] | None
) -> None:
    if polygon is None:
        return
    shape = etree.SubElement(parent, _q("Shape"))
    poly = etree.SubElement(shape, _q("Polygon"))
    poly.set("POINTS", format_points(polygon))


def _write_string(parent: etree._Element, s: AltoString) -> None:
    el = etree.SubElement(parent, _q("String"))
    el.set("CONTENT", s.content)
    if s.id is not None:
        el.set("ID", s.id)
    if s.confidence is not None:
        el.set("WC", str(s.confidence))
    _set_bbox(el, s.bbox)
    if s.subs_type is not None:
        el.set("SUBS_TYPE", s.subs_type)
    if s.subs_content is not None:
        el.set("SUBS_CONTENT", s.subs_content)


def _line_layout(line: AltoLine) -> tuple[list[bool], str | None]:
    """Où mettre les ``<SP>``, et quelle marque de coupure finale.

    ``line.text`` fait autorité : il vient du parser, qui a lu les ``SP`` et le
    ``HYP`` d'origine. On y relit la position de chaque ``String`` pour savoir
    si ses voisins étaient séparés par un blanc. Sans ce texte (document
    construit à la main), on retombe sur un blanc partout — ce que faisait
    l'ancienne jointure.

    Écrire les ``String`` sans ``SP`` produisait un ALTO qui dit ``helloworld``.
    Ça ne se voyait pas : le parser ignorait les ``SP`` et rejoignait par des
    blancs, donc l'aller-retour se comparait égal à lui-même.
    """
    default = [True] * max(len(line.strings) - 1, 0)
    if not line.text:
        return default, None
    pos = 0
    gaps: list[bool] = []
    for i, s in enumerate(line.strings):
        idx = line.text.find(s.content, pos)
        if idx < 0:
            return default, None  # texte et String désaccordés : repli
        if i:
            gaps.append(" " in line.text[pos:idx])
        pos = idx + len(s.content)
    return gaps, line.text[pos:].strip() or None


def _write_line(parent: etree._Element, line: AltoLine) -> None:
    el = etree.SubElement(parent, _q("TextLine"))
    if line.id is not None:
        el.set("ID", line.id)
    if line.baseline is not None:
        el.set("BASELINE", format_points(line.baseline))
    _set_bbox(el, line.bbox)
    _write_polygon(el, line.polygon)
    gaps, break_mark = _line_layout(line)
    for i, s in enumerate(line.strings):
        if i and gaps[i - 1]:
            etree.SubElement(el, _q("SP"))
        _write_string(el, s)
    if break_mark is not None:
        etree.SubElement(el, _q("HYP")).set("CONTENT", break_mark)


def _write_block(parent: etree._Element, block: AltoBlock, w: _Writer) -> None:
    if isinstance(block, AltoTextBlock):
        el = etree.SubElement(parent, _q("TextBlock"))
        el.set("ID", w.block_id(block))
        if block.block_type:
            el.set("TAGREFS", w.type_tags[block.block_type])
        _set_bbox(el, block.bbox)
        _write_polygon(el, block.polygon)
        for line in block.lines:
            _write_line(el, line)
    elif isinstance(block, AltoComposedBlock):
        el = etree.SubElement(parent, _q("ComposedBlock"))
        el.set("ID", w.block_id(block))
        if block.block_type is not None:
            el.set("TYPE", block.block_type)
        _set_bbox(el, block.bbox)
        _write_polygon(el, block.polygon)
        for child in block.blocks:
            _write_block(el, child, w)
    elif isinstance(block, AltoIllustration):
        el = etree.SubElement(parent, _q("Illustration"))
        el.set("ID", w.block_id(block))
        if block.block_type is not None:
            el.set("TYPE", block.block_type)
        _set_bbox(el, block.bbox)
        _write_polygon(el, block.polygon)
    else:  # AltoGraphicalElement
        el = etree.SubElement(parent, _q("GraphicalElement"))
        el.set("ID", w.block_id(block))
        _set_bbox(el, block.bbox)
        _write_polygon(el, block.polygon)


def _write_page(layout: etree._Element, page: AltoPage, rank: int, w: _Writer) -> None:
    el = etree.SubElement(layout, _q("Page"))
    el.set("ID", w.page_id(page))
    el.set(
        "PHYSICAL_IMG_NR",
        _number(page.physical_img_nr if page.physical_img_nr is not None else rank),
    )
    if page.width is not None:
        el.set("WIDTH", str(page.width))
    if page.height is not None:
        el.set("HEIGHT", str(page.height))
    print_space = etree.SubElement(el, _q("PrintSpace"))
    for block in page.blocks:
        _write_block(print_space, block, w)


def _write_unit(root: etree._Element, unit: str | None) -> None:
    if unit is None:
        return
    if unit not in _UNITS:
        # Lecture tolérante, écriture conforme : une unité hors énumération
        # n'est pas recopiée — elle rendrait le fichier invalide.
        logger.warning("[alto] unité de mesure %r hors ALTO 4, non écrite", unit)
        return
    description = etree.SubElement(root, _q("Description"))
    etree.SubElement(description, _q("MeasurementUnit")).text = unit


def write_alto(document: AltoDocument) -> bytes:
    """Sérialise un ``AltoDocument`` en octets ALTO 4 canoniques (C14N2)."""
    w = _Writer(document)
    root = etree.Element(_q("alto"), nsmap={None: _NS})  # type: ignore[dict-item]
    _write_unit(root, document.measurement_unit)
    if w.type_tags:
        tags = etree.SubElement(root, _q("Tags"))
        for label, tag_id in w.type_tags.items():
            tag = etree.SubElement(tags, _q("OtherTag"))
            tag.set("ID", tag_id)
            tag.set("LABEL", label)
            tag.set("DESCRIPTION", f"{_BLOCK_TYPE_TAG} {label}")
    layout = etree.SubElement(root, _q("Layout"))
    for rank, page in enumerate(document.pages, start=1):
        _write_page(layout, page, rank, w)
    return etree.tostring(root, method="c14n2")


__all__ = ["write_alto"]
