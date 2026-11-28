"""Spécifications de pipeline qui **déclarent** leurs types de sortie.

``not_in_view`` est une propriété du pipeline : une vue ne voit un pipeline que
si l'une de ses étapes **déclare** un type candidat (``CONTRATS.md`` D1). Un
manifeste construit à la main pour ``evaluate_run`` doit donc nommer des étapes
et leurs types — un ``PipelineSpec`` sans étape ne voit aucune vue.
"""

from __future__ import annotations

from collections.abc import Sequence

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.pipeline import PipelineSpec, PipelineStep

#: Les types qu'une vue de test peut noter.
CANDIDATE_TYPES: tuple[ArtifactType, ...] = (
    ArtifactType.RAW_TEXT,
    ArtifactType.CORRECTED_TEXT,
    ArtifactType.LAYOUT,
    ArtifactType.ENTITIES,
)


def declared_pipeline(
    name: str,
    steps: Sequence[str] = ("ocr",),
    outputs: Sequence[ArtifactType] = CANDIDATE_TYPES,
) -> PipelineSpec:
    """Un pipeline dont chaque étape de ``steps`` déclare ``outputs``."""
    return PipelineSpec(
        name=name,
        initial_inputs=(ArtifactType.IMAGE,),
        steps=tuple(
            PipelineStep(
                id=step_id,
                kind="ocr",
                adapter_name="declared",
                input_types=(ArtifactType.IMAGE,),
                output_types=tuple(outputs),
            )
            for step_id in steps
        ),
    )


__all__ = ["CANDIDATE_TYPES", "declared_pipeline"]
