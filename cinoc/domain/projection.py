"""``ProjectionSpec`` — déclaration d'une projection entre types d'artefacts.

Documente la conversion d'un type vers un autre (ex. ``ALTO_XML`` →
``RAW_TEXT``). Ne contient pas la logique du projecteur (qui vit en
``evaluation/projectors``) : permet à une vue de référencer une
projection par nom dans un YAML, sans coupler à une implémentation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cinoc.domain.artifacts import ArtifactType


class ProjectionSpec(BaseModel):
    """Spec déclarative d'une projection entre deux types d'artefacts.

    Attributs
    ---------
    source_type / target_type:
        Types en entrée / sortie du projecteur. Peuvent être identiques
        (projection identité).
    projector_name:
        Identifiant du projecteur dans le registre runtime. Convention :
        ``"<source>_to_<target>"`` (ex. ``"alto_to_text"``).
    params:
        Paramètres passés au projecteur (validés par lui-même).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: ArtifactType
    target_type: ArtifactType
    projector_name: str = Field(min_length=1, max_length=128)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)


__all__ = ["ProjectionSpec"]
