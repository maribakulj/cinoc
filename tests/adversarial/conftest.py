"""Marqueurs des tests rouges de la refonte des contrats (``CONTRATS.md``).

- ``valide`` : défaut confirmé sans réserve par la relecture indépendante de la
  contre-expertise (branche ``claude/contre-expertise-04a1c17b``).
- ``discutable(convention)`` : défaut réel dont l'attendu dépendait d'une
  convention ; l'argument est l'identifiant de sa fiche dans le
  ``CONVENTIONS.md`` de la contre-expertise. L'attendu retenu est celui que
  fixe la révision n° 6 de ``CONTRATS.md`` (arbitrages B1-B9).
- ``tranche(id)`` : la tranche de la refonte qui rend ce test vert (``1a``,
  ``1b``, puis ``2``, ``3``, ``4``, ``I`` quand leurs tests seront importés) ;
  déclaré dans ``pyproject.toml``, car les tests inversés hors de ce dossier
  le portent aussi.

Un test écrit pendant la refonte (contre-exemple de la revue, propriété) ne
porte que ``tranche`` : la relecture ne l'a pas classé.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "valide: test rouge valide sans réserve (relecture indépendante)"
    )
    config.addinivalue_line(
        "markers",
        "discutable(convention): test rouge dont l'attendu dépendait d'une "
        "convention (fiche de CONVENTIONS.md, contre-expertise)",
    )
