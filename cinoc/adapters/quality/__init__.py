"""Scoreurs de qualité (couche 5) : ils *informent*, ils ne décident pas.

Un scoreur note le besoin de correction d'une ligne ; c'est le routeur de
``saknussemm`` qui, sous une politique, en tire une décision (sauter, appeler le
modèle, escalader). Même doctrine que les confiances OCR — le modèle informe,
l'application décide.
"""

from __future__ import annotations

__all__: list[str] = []
