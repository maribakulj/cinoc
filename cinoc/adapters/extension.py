"""L'API d'écriture d'un module tiers — la surface **publique** de la couche 5.

Le seul point d'extension du produit (CLAUDE.md §3) est la brique de pipeline :
un paquet pip déclare un entry-point ``cinoc.modules``, cinoc le découvre et
l'exécute comme le socle. Mais écrire cette brique demandait jusqu'ici
d'importer des modules **privés** — ``adapters.layout._base`` pour convertir des
détections, ``adapters._workspace`` pour placer un artefact. Un point
d'extension dont l'usage normal passe par des `_` n'en est pas un : il n'offre
aucun engagement de stabilité, et il invite chaque auteur à recopier la
conversion plutôt qu'à la partager — donc à diverger du socle sur l'ordre des
régions ou le dédoublonnage, ce qui fausserait toute comparaison.

Ce module rassemble ce dont un auteur a besoin, et **rien d'autre**. Il ne
contient aucune logique : tout y est réexporté depuis son propriétaire, pour
qu'il n'existe jamais deux implémentations. Ce qui figure ici est tenu stable ;
ce qui n'y figure pas est interne et peut bouger.

Écrire un segmenteur tiers tient alors en un fichier ::

    from cinoc.adapters.extension import (
        ArtifactType, DetectedRegion, LayoutDetection,
        layout_step_output, to_canonical_layout,
    )

    class MonSegmenteur:
        name = "mon_segmenteur"
        version = "1.0.0"
        input_types = frozenset({ArtifactType.IMAGE})
        output_types = frozenset({ArtifactType.LAYOUT})

        def execute(self, inputs, params, context, control):
            control.raise_if_cancelled()
            detection = LayoutDetection(
                page_width=..., page_height=...,
                regions=(DetectedRegion(label="text", x=0, y=0,
                                        width=10, height=10, score=0.9),),
            )
            layout = to_canonical_layout(detection, min_score=0.0)
            return layout_step_output(layout, context, self.name)

et, dans son ``pyproject.toml`` ::

    [project.entry-points."cinoc.modules"]
    mon_segmenteur = "mon_paquet.seg:build"

Passer par ``to_canonical_layout`` n'est pas une commodité : c'est lui qui
applique le seuil de score, retire les détections redondantes et **trie** les
régions pour un ordre de lecture déterministe. Un module qui fabriquerait son
``CanonicalLayout`` à la main échapperait à ces garanties, et le banc
comparerait deux contrats au lieu de deux détecteurs.
"""

from __future__ import annotations

from cinoc.adapters._workspace import safe_document_stem, workspace_artifact_path
from cinoc.adapters.layout._base import (
    DetectedRegion,
    LayoutDetection,
    layout_step_output,
    to_canonical_layout,
)
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError, CinocError
from cinoc.domain.layout import CanonicalLayout
from cinoc.pipeline.protocols import Module, ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

__all__ = [
    "Artifact",
    "ArtifactType",
    "AdapterStepError",
    "CanonicalLayout",
    "CinocError",
    "DetectedRegion",
    "LayoutDetection",
    "Module",
    "ParamValue",
    "RunContext",
    "RunControl",
    "StepOutput",
    "compute_content_hash",
    "layout_step_output",
    "safe_document_stem",
    "to_canonical_layout",
    "workspace_artifact_path",
]
