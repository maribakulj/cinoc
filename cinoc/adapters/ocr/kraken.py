"""``KrakenAdapter`` — moteur HTR réel (kraken, le moteur d'eScriptorium).

Implémente le ``Module`` Protocol directement. Couvre le **manuscrit** (HTR),
là où tesseract couvre l'imprimé. Le SDK ``kraken`` est un **extra optionnel**
(``cinoc[kraken]``), importé paresseusement dans ``_invoke_kraken`` — importer
ce module ne requiert rien ; seule l'exécution exige SDK + **modèle** (.mlmodel,
paramètre ``model`` obligatoire : pas de modèle par défaut embarqué).

Sorties : ``RAW_TEXT`` (lignes reconnues, ordre de lecture kraken) +
``CONFIDENCES`` (un jeton par mot, confiance = moyenne des confiances de
caractères du mot — best-effort, sidecar vide en dégradé).
"""

from __future__ import annotations

import json
import logging
from typing import ClassVar

from cinoc.adapters._params import label_param, model_param
from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

_VERSION = "1.0"


def tokens_from_lines(
    lines: list[tuple[str, list[float]]],
) -> list[ConfidenceToken]:
    """Jetons mot+confiance depuis (texte de ligne, confiances par caractère).

    La confiance d'un mot = moyenne des confiances de ses caractères (bornée
    [0,1]) ; un mot sans couverture de confiance est ignoré.
    """
    tokens: list[ConfidenceToken] = []
    for text, confidences in lines:
        cursor = 0
        for word in text.split():
            start = text.find(word, cursor)
            if start < 0:
                continue
            cursor = start + len(word)
            window = confidences[start : start + len(word)]
            if not window:
                continue
            value = max(0.0, min(sum(window) / len(window), 1.0))
            tokens.append(ConfidenceToken(text=word, confidence=value))
    return tokens


def _invoke_kraken(  # pragma: no cover -- SDK + modèle requis (cf. 'live')
    *, image_path: str, model_path: str
) -> list[tuple[str, list[float]]]:
    """Segmentation + reconnaissance kraken → (texte, confiances/char) par ligne."""
    try:
        from kraken import (  # type: ignore[import-not-found]
            binarization,
            pageseg,
            rpred,
        )
        from kraken.lib import models  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AdapterStepError(
            "kraken : SDK non installé (pip install 'cinoc[kraken]')."
        ) from exc
    try:
        model = models.load_any(model_path)
    except (OSError, ValueError, RuntimeError) as exc:  # loader kraken
        raise AdapterStepError(
            f"kraken : modèle illisible {model_path!r} : {exc}"
        ) from exc
    image = Image.open(image_path)
    binarized = binarization.nlbin(image)
    segmentation = pageseg.segment(binarized)
    out: list[tuple[str, list[float]]] = []
    for record in rpred.rpred(model, binarized, segmentation):
        out.append((str(record), [float(c) for c in record.confidences]))
    return out


class KrakenAdapter:
    """HTR kraken : ``IMAGE`` → ``RAW_TEXT`` + ``CONFIDENCES``."""

    #: Réglages acceptés (``pipeline.params``) : tout autre est refusé, nommé.
    PARAMS: ClassVar[tuple[Param, ...]] = (
        label_param(),
        model_param("Modèle (chemin .mlmodel)", "Model (.mlmodel path)"),
    )

    def __init__(self, *, label: str, model: str) -> None:
        if not label or not all(c.isalnum() or c in "_-" for c in label):
            raise AdapterStepError(f"kraken : label invalide {label!r}.")
        if not model:
            raise AdapterStepError(
                "kraken : paramètre 'model' (chemin .mlmodel) requis."
            )
        self._label = label
        self._model = model

    @property
    def name(self) -> str:
        return f"kraken:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.RAW_TEXT, ArtifactType.CONFIDENCES})

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
        if context.workspace_uri is None:
            raise AdapterStepError(f"{self.name} : workspace requis.")
        lines = _invoke_kraken(image_path=image.uri, model_path=self._model)
        text = "\n".join(line for line, _ in lines)
        tokens = tokens_from_lines(lines)
        text_path = workspace_artifact_path(
            context.workspace_uri, context.document_id, self._label, "txt"
        )
        text_path.write_text(text, encoding="utf-8")
        sidecar = json.dumps(
            [token.model_dump() for token in tokens], ensure_ascii=False
        ).encode("utf-8")
        sidecar_path = workspace_artifact_path(
            context.workspace_uri, context.document_id, self._label,
            "confidences.json",
        )
        sidecar_path.write_bytes(sidecar)
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(text_path),
                    content_hash=compute_content_hash(text.encode("utf-8")),
                ),
                ArtifactType.CONFIDENCES: Artifact(
                    id=f"{context.document_id}:{self.name}:confidences",
                    document_id=context.document_id,
                    type=ArtifactType.CONFIDENCES,
                    uri=str(sidecar_path),
                    content_hash=compute_content_hash(sidecar),
                ),
            }
        )


__all__ = ["KrakenAdapter", "tokens_from_lines"]
