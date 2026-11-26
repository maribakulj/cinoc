"""``AltoAssembler`` — assemblage ``LAYOUT → ALTO_XML`` (couche 5).

Troisième étage du pipeline de segmentation (``CLAUDE.md`` §3 : *assemblage
LAYOUT → ALTO_XML*). C'est un **constructeur d'ALTO** au sens du même `Module`
Protocol que les autres briques : il prend un ``CanonicalLayout`` **rempli**
(sortie du fan-out, sérialisé JSON) et émet de l'ALTO 4 déterministe
(``layout_to_alto`` + ``write_alto`` octet-stable).

L'assembleur vit en couche 5 (et non `pipeline`) parce qu'il dépend de `formats`
(`write_alto`) — un import légal pour un adapter, interdit à `pipeline`.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout
from cinoc.formats.alto import write_alto
from cinoc.formats.alto.layout_map import layout_to_alto
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"


class AltoAssembler:
    """Assemble un ``LAYOUT`` rempli en ``ALTO_XML`` (ALTO 4, déterministe)."""

    #: Réglages acceptés (``pipeline.params``) : tout autre est refusé, nommé.
    PARAMS: ClassVar[tuple[Param, ...]] = ()

    @property
    def name(self) -> str:
        return "alto_assembler"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.ALTO_XML})

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        layout_art = inputs.get(ArtifactType.LAYOUT)
        if layout_art is None or layout_art.uri is None:
            raise AdapterStepError(
                f"{self.name} : artefact LAYOUT manquant ou sans URI."
            )
        layout_path = Path(layout_art.uri)
        try:
            layout = CanonicalLayout.model_validate_json(layout_path.read_bytes())
        except (OSError, ValueError) as exc:
            raise AdapterStepError(
                f"{self.name} : LAYOUT illisible ({layout_path.name!r}) : {exc}"
            ) from exc
        payload = write_alto(layout_to_alto(layout))
        out_dir = (
            Path(context.workspace_uri)
            if context.workspace_uri
            else layout_path.parent
        )
        out_path = out_dir / f"{context.document_id.replace('/', '_')}.alto.xml"
        out_path.write_bytes(payload)
        return StepOutput(
            artifacts={
                ArtifactType.ALTO_XML: Artifact(
                    id=f"{context.document_id}:{self.name}:alto_xml",
                    document_id=context.document_id,
                    type=ArtifactType.ALTO_XML,
                    uri=str(out_path),
                    content_hash=compute_content_hash(payload),
                )
            }
        )


__all__ = ["AltoAssembler"]
