"""``PrecomputedTextAdapter`` — rejoue un texte OCR pré-calculé depuis le disque.

Module à **zéro dépendance et zéro réseau** : il lit ``<stem>.<source_label>.txt``
à côté de l'image et renvoie un ``RAW_TEXT``. Brique du *starter pack* — il fait
tourner le squelette ambulant (``cinoc demo``) et les tests déterministes sans
moteur réel. Implémente le ``Module`` Protocol (couche 4) **directement**.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"


class PrecomputedTextAdapter:
    """Lit un texte OCR pré-calculé (``<stem>.<label>.txt`` près de l'image)."""

    def __init__(self, *, source_label: str) -> None:
        if not source_label or not all(
            c.isalnum() or c in "_-" for c in source_label
        ):
            raise AdapterStepError(
                f"PrecomputedTextAdapter : source_label invalide "
                f"{source_label!r} (alphanumérique + _ - uniquement)."
            )
        self._label = source_label

    @property
    def name(self) -> str:
        return f"precomputed:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.RAW_TEXT})

    def _text_path(self, image_path: Path) -> Path:
        return image_path.parent / f"{image_path.stem}.{self._label}.txt"

    def unit_inputs(self, document: DocumentRef) -> tuple[Path, ...]:
        """Le fichier lu pour ``document`` (hook de reprise, facultatif).

        La sortie ne dépend pas de l'image mais de ce fichier : sans cette
        déclaration, la clé d'unité ne hachait que l'image, et un texte corrigé
        sous la même image était resservi périmé par l'archive.
        """
        if document.image_uri is None:
            return ()
        return (self._text_path(Path(document.image_uri)),)

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        image = inputs.get(ArtifactType.IMAGE)
        if image is None or image.uri is None:
            raise AdapterStepError(
                f"{self.name} : artefact IMAGE manquant ou sans URI."
            )
        image_path = Path(image.uri)
        text_path = self._text_path(image_path)
        if not text_path.is_file():
            raise AdapterStepError(
                f"{self.name} : texte pré-calculé introuvable — "
                f"{text_path.name!r} attendu près de {image_path.name!r}."
            )
        data = text_path.read_bytes()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdapterStepError(
                f"{self.name} : {text_path.name!r} n'est pas en UTF-8 : {exc}"
            ) from exc
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(text_path),
                    content_hash=compute_content_hash(data),
                )
            }
        )


__all__ = ["PrecomputedTextAdapter"]
