"""Identifiants de région synthétisés — **une** règle pour ALTO et PAGE.

Une région sans ``ID`` (ALTO) ou ``id`` (PAGE) en reçoit un, déterministe et
unique dans le document : ``region_0``, ``region_1``… dans l'ordre de lecture du
fichier. Les deux projections vers ``CanonicalLayout`` (``alto.layout_map``,
``pagexml.layout_map``) tenaient chacune sa copie de ce compteur (S29a) : deux
copies d'une règle d'identité finissent par diverger, et la même page lue en
ALTO puis en PAGE ne nommerait plus ses régions de la même façon.
"""

from __future__ import annotations


class RegionIds:
    """Compteur déterministe des ``id`` de région manquants, un par document."""

    def __init__(self) -> None:
        self._n = 0

    def next_id(self) -> str:
        rid = f"region_{self._n}"
        self._n += 1
        return rid


__all__ = ["RegionIds"]
