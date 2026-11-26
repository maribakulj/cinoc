"""``CalamariAdapter`` — moteur OCR réel (calamari-ocr, reconnaissance de lignes).

Local et sans clé. Implémente le ``Module`` Protocol **directement** — même
contrat que le socle, livré in-tree (pas de discrimination socle/plugin). La lib
``calamari_ocr`` est un **extra optionnel** (``cinoc[calamari]``), importée
**paresseusement** dans ``_invoke_calamari`` : importer ce module ne requiert rien ;
seule l'exécution exige la lib + un **modèle** (``model`` = checkpoint, obligatoire).

Calamari reconnaît une **ligne** par image : utilisé seul sur une page, il traite
l'image comme une ligne unique ; son usage naturel est en **recognizer par
région** dans le pipeline de segmentation (fan-out par bloc). Sortie : ``RAW_TEXT``.

**Non déployé au Space** (dép lourde TensorFlow, free-tier) : listé « indisponible »
sans l'extra, comme Kraken/PERO.
"""

from __future__ import annotations

from typing import ClassVar

from cinoc.adapters._params import label_param, model_param
from cinoc.adapters.ocr._base import run_image_to_text
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"


def _invoke_calamari(  # pragma: no cover -- lib + modèle requis (cf. 'live')
    *, image_path: str, model_path: str
) -> str:
    """Reconnaissance Calamari de l'image (ligne) → texte prédit."""
    try:
        import numpy as np  # type: ignore[import-not-found]
        from calamari_ocr.ocr.predict.predictor import (  # type: ignore[import-not-found]
            Predictor,
            PredictorParams,
        )
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AdapterStepError(
            "calamari : lib non installée (pip install 'cinoc[calamari]')."
        ) from exc
    try:
        predictor = Predictor.from_checkpoint(
            params=PredictorParams(), checkpoint=model_path
        )
    except (OSError, ValueError, RuntimeError) as exc:  # loader calamari
        raise AdapterStepError(
            f"calamari : modèle illisible {model_path!r} : {exc}"
        ) from exc
    image = np.array(Image.open(image_path).convert("L"))
    predictions = predictor.predict_raw([image])
    texts = [str(prediction.sentence) for prediction in predictions]
    return " ".join(texts).strip()


class CalamariAdapter:
    """OCR Calamari : ``IMAGE`` → ``RAW_TEXT`` (texte de la ligne reconnue)."""

    #: Réglages acceptés (``pipeline.params``) : tout autre est refusé, nommé.
    PARAMS: ClassVar[tuple[Param, ...]] = (
        label_param(),
        model_param("Checkpoint Calamari (chemin)", "Calamari checkpoint (path)"),
    )

    def __init__(self, *, label: str, model: str) -> None:
        if not label or not all(c.isalnum() or c in "_-" for c in label):
            raise AdapterStepError(f"calamari : label invalide {label!r}.")
        if not model:
            raise AdapterStepError(
                "calamari : paramètre 'model' (checkpoint) requis."
            )
        self._label = label
        self._model = model

    @property
    def name(self) -> str:
        return f"calamari:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.RAW_TEXT})

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        return run_image_to_text(
            name=self.name,
            label=self._label,
            inputs=inputs,
            context=context,
            control=control,
            recognize=lambda image_uri: _invoke_calamari(
                image_path=image_uri, model_path=self._model
            ),
        )


__all__ = ["CalamariAdapter"]
