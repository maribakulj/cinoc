"""Couche 1 — Domain.

Types purs et abstractions du modèle métier de Cinoc. Ce cercle
n'importe que la stdlib, ``pydantic`` et ``pydantic_core``. Il ne dépend
d'aucun moteur OCR, d'aucune métrique calculée, d'aucun rendu, d'aucune
couche réseau.

Règle d'or : si tu hésites à mettre quelque chose ici, c'est qu'il ne
devrait pas y être. Le domain ne fait presque rien — il décrit.

Note : ``RunResult`` / ``RunDocumentResult`` ne sont PAS ici — ils
agrègent des objets de couches plus externes (``evaluation``,
``pipeline``). Le domain ne décrit que des contrats.
"""

from __future__ import annotations

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.deadline import Deadline
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import (
    AdapterStepError,
    ArtifactValidationError,
    CinocError,
    CorpusSpecError,
    DeadlineExceeded,
    ProjectionError,
    RunCancelledError,
)
from cinoc.domain.evaluation import (
    EvaluationSpec,
    EvaluationView,
    MetricCategory,
    MetricSpec,
    MetricUnit,
)
from cinoc.domain.pipeline import (
    INITIAL_STEP_ID,
    PipelineMode,
    PipelineSpec,
    PipelineStep,
)
from cinoc.domain.projection import ProjectionSpec
from cinoc.domain.provenance import ProvenanceRecord
from cinoc.domain.run import RunManifest, utcnow
from cinoc.domain.usage import ResourceUsage

__all__ = [
    # Artifacts
    "Artifact",
    "ArtifactType",
    "compute_content_hash",
    # Corpus + documents
    "CorpusSpec",
    "DocumentRef",
    "GroundTruthRef",
    # Timeout
    "Deadline",
    # Provenance
    "ProvenanceRecord",
    # Errors
    "CinocError",
    "ArtifactValidationError",
    "ProjectionError",
    "CorpusSpecError",
    "AdapterStepError",
    "DeadlineExceeded",
    "RunCancelledError",
    # Evaluation contracts
    "MetricCategory",
    "MetricSpec",
    "MetricUnit",
    "EvaluationView",
    "EvaluationSpec",
    "ProjectionSpec",
    # Pipeline spec
    "PipelineSpec",
    "PipelineStep",
    "PipelineMode",
    "INITIAL_STEP_ID",
    # Run manifest
    "RunManifest",
    "utcnow",
    # Ressources mesurées
    "ResourceUsage",
    # Confidences moteur
    "ConfidenceToken",
]
