"""Marqueurs de la relecture indépendante des tests rouges de la contre-expertise.

- ``valide`` : défaut confirmé sans réserve.
- ``discutable(convention)`` : défaut réel, mais l'attendu exact dépend d'une
  convention ; l'argument est l'identifiant de sa fiche dans ``CONVENTIONS.md``.

Les tests verts ne portent aucun de ces marqueurs.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "valide: test rouge valide sans réserve (relecture indépendante)")
    config.addinivalue_line(
        "markers",
        "discutable(convention): test rouge valide mais dont l'attendu dépend d'une convention "
        "(identifiant de la fiche dans tests/adversarial/CONVENTIONS.md)",
    )
