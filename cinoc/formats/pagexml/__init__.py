"""Format PAGE XML (PRImA) : types, parser tolérant, writer déterministe."""

from __future__ import annotations

from cinoc.formats.pagexml.parser import PageParseError, parse_pagexml
from cinoc.formats.pagexml.types import (
    PageDocument,
    PageGenericRegion,
    PagePage,
    PageRegion,
    PageTextLine,
    PageTextRegion,
    PageWord,
    ReadingOrderGroup,
    ReadingOrderNode,
    ReadingOrderRef,
)
from cinoc.formats.pagexml.writer import (
    PAGE_NS,
    PageWriteError,
    write_pagexml,
)

__all__ = [
    "ReadingOrderRef",
    "ReadingOrderGroup",
    "ReadingOrderNode",
    "PageTextLine",
    "PageTextRegion",
    "PageWord",
    "PageGenericRegion",
    "PageRegion",
    "PagePage",
    "PageDocument",
    "parse_pagexml",
    "PageParseError",
    "write_pagexml",
    "PageWriteError",
    "PAGE_NS",
]
