"""``RunContext`` — contexte d'exécution propagé à chaque ``Module.execute``.

Porte l'identité du document, la version de code (provenance), le nom de la
pipeline et la ``Deadline`` coopérative. Concern d'exécution → couche 4 ; fait
paire avec ``RunControl`` (raison pour laquelle il ne vit pas en ``domain``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from cinoc.domain.artifacts import (
    Artifact,
    ArtifactType,
    StepArtifacts,
    latest_by_type,
)
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

    ``truncation`` dit pourquoi la sortie est **coupée** (un LLM arrêté par son
    plafond de jetons), ``None`` si elle est complète — ou si le module ne peut
    pas le savoir. Une sortie coupée reste une sortie : ses artefacts sont rendus
    et notés, et l'unité est marquée ``truncated`` au lieu de passer pour
    complète. Seul le module le sait (il lit la réponse native) : c'est donc lui
    qui le déclare, comme ses jetons.

    ``served_models`` : le ou les modèles que le fournisseur dit avoir **servis**
    (``response.model``), lus dans sa réponse — pas l'alias demandé, qui peut
    désigner un autre modèle d'un mois à l'autre. Vide quand la réponse ne le dit
    pas (moteur local, API qui ne le rend pas) : rien n'est supposé. Plusieurs
    valeurs pour un fan-out (un appel par région) ou un lot de correction.
    """

    artifacts: Mapping[ArtifactType, Artifact]
    usage: ResourceUsage | None = None
    truncation: str | None = None
    served_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentExecution:
    """Résultat de l'exécution d'une pipeline sur **un** document.

    ``by_step`` garde la sortie de **chaque** étape, dans l'ordre d'exécution
    (entrées initiales d'abord, sous ``INITIAL_STEP_ID``) ; ``step_usage`` la
    consommation de chacune (durée mesurée par l'exécuteur + jetons remontés).
    Le pool (``artifacts``, dernier artefact par type) et la consommation totale
    (``usage``) s'en **déduisent** : une seule structure, deux lectures. Rendre
    le seul pool laissait deux étapes de même type s'écraser, et l'étape amont
    devenait inobservable dans le run qui l'avait payée.

    ``outcome`` est l'**issue** de l'unité, produite ici et non reconstruite au
    rapport : une unité en échec n'est pas une unité absente. ``failed`` exige
    un ``reason`` codé et n'a pas d'artefact ; ``message`` est l'explication
    lisible (sans secret — l'appelant qui connaît les secrets la caviarde).
    """

    by_step: StepArtifacts = field(default_factory=dict)
    step_usage: Mapping[str, ResourceUsage] = field(default_factory=dict)
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
        if self.outcome == "failed" and self.by_step:
            raise CinocError(
                "DocumentExecution : une unité en échec n'a pas d'artefact."
            )

    @property
    def artifacts(self) -> dict[ArtifactType, Artifact]:
        """Le pool : dernier artefact par type (déduit de ``by_step``)."""
        return latest_by_type(self.by_step)

    @property
    def usage(self) -> ResourceUsage:
        """Consommation de l'unité : somme ``None``-tolérante des étapes."""
        total = ResourceUsage()
        for step in self.step_usage.values():
            total = total.merged_with(step)
        return total

    @classmethod
    def failed(cls, reason: FailureReason, message: str) -> DocumentExecution:
        """Unité sans sortie : motif codé + message, aucune consommation mesurée."""
        return cls(outcome="failed", reason=reason, message=message)


__all__ = ["DocumentExecution", "RunContext", "StepOutput"]
