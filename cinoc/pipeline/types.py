"""``RunContext`` — contexte d'exécution propagé à chaque ``Module.execute``.

Porte l'identité du document, la version de code (provenance), le nom de la
pipeline et la ``Deadline`` coopérative. Concern d'exécution → couche 4 ; fait
paire avec ``RunControl`` (raison pour laquelle il ne vit pas en ``domain``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import CinocError
from cinoc.domain.usage import FailureReason, ResourceUsage, UnitOutcome


class RunContext(BaseModel):
    """Contexte d'exécution d'une étape, pour un document donné.

    Immuable. La ``Deadline`` se sérialise via ``remaining_seconds`` (cf.
    ``domain.deadline``), donc reste transposable entre process.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    code_version: str = Field(min_length=1, max_length=128)
    pipeline_name: str = Field(min_length=1, max_length=128)
    workspace_uri: str | None = Field(default=None, max_length=2048)
    deadline: Deadline = Field(default_factory=Deadline.infinite)


@dataclass(frozen=True)
class StepOutput:
    """Sortie d'un ``Module.execute`` : artefacts produits + consommation.

    ``artifacts`` contient tous les ``output_types`` déclarés (contrat module).
    ``usage`` ne porte que ce que le module **sait** (jetons d'un appel LLM) —
    la durée de l'étape est mesurée par l'**exécuteur**, jamais par le module.
    """

    artifacts: Mapping[ArtifactType, Artifact]
    usage: ResourceUsage | None = None


@dataclass(frozen=True)
class DocumentExecution:
    """Résultat de l'exécution d'une pipeline sur **un** document.

    ``artifacts`` est le pool final (dernier artefact par type) ; ``usage``
    agrège durées et jetons de toutes les étapes (somme ``None``-tolérante).

    ``outcome`` est l'**issue** de l'unité, produite ici et non reconstruite au
    rapport : une unité en échec n'est pas une unité absente. ``failed`` exige
    un ``reason`` codé et n'a pas d'artefact ; ``message`` est l'explication
    lisible (sans secret — l'appelant qui connaît les secrets la caviarde).
    """

    artifacts: Mapping[ArtifactType, Artifact]
    usage: ResourceUsage = field(default_factory=ResourceUsage)
    outcome: UnitOutcome = "ok"
    reason: FailureReason | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if (self.outcome == "failed") != (self.reason is not None):
            raise CinocError(
                "DocumentExecution : un motif d'échec accompagne une issue "
                f"« failed », et elle seule (issue {self.outcome!r}, "
                f"motif {self.reason!r})."
            )
        if self.outcome == "failed" and self.artifacts:
            raise CinocError(
                "DocumentExecution : une unité en échec n'a pas d'artefact."
            )

    @classmethod
    def failed(cls, reason: FailureReason, message: str) -> DocumentExecution:
        """Unité sans sortie : motif codé + message, aucune consommation mesurée."""
        return cls(artifacts={}, outcome="failed", reason=reason, message=message)


__all__ = ["DocumentExecution", "RunContext", "StepOutput"]
