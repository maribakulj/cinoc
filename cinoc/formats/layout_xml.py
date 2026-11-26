"""ALTO ou PAGE → ``CanonicalLayout``, le format **reconnu au contenu**.

Trois copies de la même reconnaissance vivaient en couches 3, 5 et 6 (vue
d'évaluation, sortie d'un outil de mise en page, vérité-terrain déposée) : une
seule ici, en couche 2, à côté des deux lecteurs qu'elle choisit (P5g 6, D-303).
Chaque appelant garde son erreur — elle dit **où** le XML était illisible.

Le format est déduit de la racine, pas de l'extension : les deux sortent en
``.xml``, et se fier au nom ferait dépendre la lecture d'une convention que
l'outil n'a pas promise.
"""

from __future__ import annotations

from typing import Literal

from cinoc.domain.layout import CanonicalLayout
from cinoc.formats.alto.layout_map import alto_to_layout
from cinoc.formats.alto.parser import parse_alto
from cinoc.formats.pagexml import parse_pagexml
from cinoc.formats.pagexml.layout_map import page_to_layout


def layout_xml_kind(data: bytes) -> Literal["ALTO", "PAGE"]:
    """``PAGE`` si la tête du document nomme ``PcGts``/``PageContent``,
    ``ALTO`` sinon."""
    head = data[:4096].lower()
    return "PAGE" if b"pcgts" in head or b"pagecontent" in head else "ALTO"


def parse_layout_xml(data: bytes) -> CanonicalLayout:
    """Lit un ALTO ou un PAGE ; lève ``FormatError``/``ValueError`` s'il est
    illisible (``layout_xml_kind`` nomme le format pour le message)."""
    if layout_xml_kind(data) == "PAGE":
        return page_to_layout(parse_pagexml(data))
    return alto_to_layout(parse_alto(data))


__all__ = ["layout_xml_kind", "parse_layout_xml"]
