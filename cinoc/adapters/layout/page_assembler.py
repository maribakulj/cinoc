"""``PageAssembler`` — ``LAYOUT → PAGE_XML`` (couche 5).

Le banc savait ressortir de l'ALTO. C'est le format de NDNP et de la presse
numérisée, mais il a une limite que PAGE n'a pas : **l'ordre de lecture n'y est
qu'implicite**, dans la suite des blocs. Un ordre corrigé — à la main dans
eScriptorium, ou par l'étape d'ordonnancement du banc — ne survit donc pas à un
export ALTO autrement qu'en réarrangeant le document.

PAGE le porte explicitement, et c'est le format qu'attendent eScriptorium,
Transkribus et la chaîne OCR-D. Un benchmark n'a de valeur d'archive que si sa
sortie rentre dans l'outil de relecture de celui qui la reçoit.

Ferme aussi un type mort : ``page_xml`` était réservé au domaine, le parseur
existait depuis le début, et rien ne le produisait.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout
from cinoc.formats.pagexml.layout_map import layout_to_page
from cinoc.formats.pagexml.writer import write_pagexml
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"


class PageAssembler:
    """Assemble un ``LAYOUT`` rempli en ``PAGE_XML`` (PAGE 2019, déterministe)."""

    @property
    def name(self) -> str:
        return "page_assembler"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.PAGE_XML})

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],  # noqa: ARG002 — contrat Module
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
        payload = write_pagexml(layout_to_page(layout))
        out_dir = (
            Path(context.workspace_uri)
            if context.workspace_uri
            else layout_path.parent
        )
        out_path = out_dir / f"{context.document_id.replace('/', '_')}.page.xml"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        return StepOutput(
            artifacts={
                ArtifactType.PAGE_XML: Artifact(
                    id=f"{context.document_id}:{self.name}:page_xml",
                    document_id=context.document_id,
                    type=ArtifactType.PAGE_XML,
                    uri=str(out_path),
                    content_hash=compute_content_hash(payload),
                    produced_by_step=self.name,
                )
            }
        )


__all__ = ["PageAssembler"]
