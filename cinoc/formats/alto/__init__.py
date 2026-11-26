"""Format ALTO XML : types, parser tolérant (v2/v3/v4), writer ALTO 4 déterministe."""

from __future__ import annotations

from cinoc.formats.alto.parser import AltoParseError, parse_alto
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
from cinoc.formats.alto.writer import write_alto

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
    "parse_alto",
    "AltoParseError",
    "write_alto",
]
