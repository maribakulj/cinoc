"""Profil Hypothesis des propriétés de la refonte (CONTRATS.md § 3, « P »).

Déterministe (décision B rendue, révision n° 1) : ``derandomize=True`` tire les
exemples d'une graine fixée par le test, aucune base d'exemples n'est lue ni
écrite (``database=None``), aucune échéance (``deadline=None``) — un rouge se
rejoue à l'identique sur toute machine, en série comme sous ``-n``.
"""

from __future__ import annotations

from hypothesis import HealthCheck, settings

DETERMINISTE = settings(
    derandomize=True,
    database=None,
    deadline=None,
    max_examples=60,
    suppress_health_check=[HealthCheck.too_slow],
    print_blob=False,
)
