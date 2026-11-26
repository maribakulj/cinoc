"""Socle ``precomputed`` de la tranche segmentation (couche 5, 0 dép, 0 réseau).

Deux briques, **même ``Module`` Protocol** que les autres adapters, qui font
tourner le squelette segmentation **sans segmenteur ni OCR réels** :

- ``PrecomputedLayoutSource`` : ``IMAGE → LAYOUT`` — rejoue une mise en page
  pré-calculée (régions seules) depuis ``<stem>.layout.json``.
- ``PrecomputedRegionRecognizer`` : ``IMAGE → RAW_TEXT`` — rejoue le texte d'**une
  région** (clé = ``Artifact.region_id`` de l'IMAGE d'entrée) depuis
  ``<stem>.<label>.regions.json`` (``{region_id: texte}``). Appelé **une fois par
  région** par le fan-out (couche 4) ; aucun découpage d'image réel (la donnée
  est figée).
"""

from __future__ import annotations

import json
from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"


def _require_image(inputs: dict[ArtifactType, Artifact], who: str) -> Path:
    image = inputs.get(ArtifactType.IMAGE)
    if image is None or image.uri is None:
        raise AdapterStepError(f"{who} : artefact IMAGE manquant ou sans URI.")
    return Path(image.uri)


def _layout_path(image_path: Path) -> Path:
    return image_path.parent / f"{image_path.stem}.layout.json"


class PrecomputedLayoutSource:
    """Rejoue une mise en page pré-calculée (``<stem>.layout.json``)."""

    @property
    def name(self) -> str:
        return "precomputed_layout"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    def unit_inputs(self, document: DocumentRef) -> tuple[Path, ...]:
        """Le fichier lu pour ``document`` (hook de reprise, facultatif)."""
        if document.image_uri is None:
            return ()
        return (_layout_path(Path(document.image_uri)),)

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        image_path = _require_image(inputs, self.name)
        layout_path = _layout_path(image_path)
        if not layout_path.is_file():
            raise AdapterStepError(
                f"{self.name} : mise en page pré-calculée introuvable — "
                f"{layout_path.name!r} attendu près de {image_path.name!r}."
            )
        data = layout_path.read_bytes()
        try:
            CanonicalLayout.model_validate_json(data)
        except ValueError as exc:
            raise AdapterStepError(
                f"{self.name} : {layout_path.name!r} n'est pas un "
                f"CanonicalLayout valide : {exc}"
            ) from exc
        return StepOutput(
            artifacts={
                ArtifactType.LAYOUT: Artifact(
                    id=f"{context.document_id}:{self.name}:layout",
                    document_id=context.document_id,
                    type=ArtifactType.LAYOUT,
                    uri=str(layout_path),
                    content_hash=compute_content_hash(data),
                )
            }
        )


class PrecomputedRegionRecognizer:
    """Rejoue le texte d'une région (``<stem>.<label>.regions.json``)."""

    def __init__(self, *, source_label: str) -> None:
        if not source_label or not all(
            c.isalnum() or c in "_-" for c in source_label
        ):
            raise AdapterStepError(
                f"PrecomputedRegionRecognizer : source_label invalide "
                f"{source_label!r} (alphanumérique + _ - uniquement)."
            )
        self._label = source_label

    @property
    def name(self) -> str:
        return f"precomputed_region:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.RAW_TEXT})

    def _regions_path(self, image_path: Path) -> Path:
        return image_path.parent / f"{image_path.stem}.{self._label}.regions.json"

    def unit_inputs(self, document: DocumentRef) -> tuple[Path, ...]:
        """Le fichier lu pour ``document`` (hook de reprise, facultatif).

        Le fan-out passe à chaque région l'image **de la page** (sans découpe) :
        le fichier est donc celui de la page, le même pour toutes ses régions.
        """
        if document.image_uri is None:
            return ()
        return (self._regions_path(Path(document.image_uri)),)

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        image = inputs[ArtifactType.IMAGE]
        if image.region_id is None:
            raise AdapterStepError(
                f"{self.name} : IMAGE sans region_id — la reconnaissance par "
                "région attend une entrée déjà cadrée par le fan-out."
            )
        image_path = _require_image(inputs, self.name)
        regions_path = self._regions_path(image_path)
        if not regions_path.is_file():
            raise AdapterStepError(
                f"{self.name} : textes par région introuvables — "
                f"{regions_path.name!r} attendu près de {image_path.name!r}."
            )
        try:
            mapping = json.loads(regions_path.read_bytes())
        except ValueError as exc:
            raise AdapterStepError(
                f"{self.name} : {regions_path.name!r} JSON invalide : {exc}"
            ) from exc
        if not isinstance(mapping, dict) or image.region_id not in mapping:
            raise AdapterStepError(
                f"{self.name} : région {image.region_id!r} absente de "
                f"{regions_path.name!r}."
            )
        text = str(mapping[image.region_id])
        out_dir = (
            Path(context.workspace_uri)
            if context.workspace_uri
            else image_path.parent
        )
        out_path = out_dir / f"{image_path.stem}.{self._label}.{image.region_id}.txt"
        payload = text.encode("utf-8")
        out_path.write_bytes(payload)
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:{image.region_id}:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(out_path),
                    content_hash=compute_content_hash(payload),
                    region_id=image.region_id,
                )
            }
        )


__all__ = ["PrecomputedLayoutSource", "PrecomputedRegionRecognizer"]
