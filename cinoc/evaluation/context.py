"""``DocContext`` / ``CrossEngineContext`` — sacs d'entrées des métriques.

- ``DocContext`` (par-document) : référence + hypothèse déjà chargées/normalisées.
- ``CrossEngineContext`` (inter-moteurs) : pour une métrique de base, la suite des
  valeurs par-document de chaque pipeline, **alignée par document**.

Extensibles **par ajout de champ**, chacun avec son consommateur — jamais spéculé.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class DocContext:
    """Entrées d'une métrique pour un document donné."""

    document_id: str
    reference: object
    hypothesis: object
    #: La sortie est **déclarée incomplète** par l'étape (ou perdue : échec noté
    #: comme une sortie vide) : un niveau texte absent de l'hypothèse y est une
    #: part **manquante**, notée en suppressions, et non un « niveau absent »
    #: qui rendrait la métrique non applicable (``CLAUDE.md`` §3).
    partial: bool = False


@dataclass(frozen=True)
class CrossEngineContext:
    """Entrées d'une métrique inter-moteurs, pour une métrique de base.

    ``per_pipeline`` : pour chaque pipeline, ses valeurs par-document de la
    métrique de base, **alignées par document** (``None`` = non applicable).
    """

    metric: str
    per_pipeline: Mapping[str, tuple[float | None, ...]]


__all__ = ["CrossEngineContext", "DocContext"]
