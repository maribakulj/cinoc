"""``MistralOCRAdapter`` — OCR cloud (API Mistral OCR), facturé à la page.

Premier moteur **payant à la page** du socle : donne un sens réel à l'axe
coût du Pareto (économie T10, tarif ``cloud_page_kinds``). Implémente le
``Module`` Protocol ; SDK ``mistralai`` = extra (``cinoc[mistral]``), importé
paresseusement dans ``_invoke_mistral_ocr`` (mockable, CI sans clé ni réseau).
Clé ``MISTRAL_API_KEY``. Sortie : le texte (markdown) des pages, concaténé —
**lu** dans la réponse par :func:`_text_from_response`, et la réponse entière
(pages, images, dimensions, en-têtes et pieds) gardée en sidecar ``NATIVE_JSON``
(un appel par page) : la projection vers ``LAYOUT`` se fera depuis lui.
"""

from __future__ import annotations

from base64 import b64encode
from pathlib import Path
from typing import Any

from cinoc.adapters._native import sdk_native, served_model
from cinoc.adapters.ocr._base import run_remote_image_to_text
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

#: 1.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas.
_VERSION = "1.1"
_DEFAULT_MODEL = "mistral-ocr-latest"
_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff"}


def _text_from_response(native: object) -> str:
    """Corps de ``POST /v1/ocr`` → texte : le markdown des pages, concaténé.

    **Pur** : c'est la seule lecture du texte, à l'exécution comme à la
    relecture d'un sidecar.
    """
    pages = native.get("pages") if isinstance(native, dict) else None
    if not isinstance(pages, list):
        return ""
    return "\n\n".join(
        str((page.get("markdown") if isinstance(page, dict) else "") or "")
        for page in pages
    ).strip()


def _invoke_mistral_ocr(
    *, model: str, image_path: str, deadline: Deadline
) -> dict[str, Any]:
    """Appelle l'OCR et rend le **corps** de la réponse (dump du modèle du SDK)."""
    import os

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise AdapterStepError("mistral_ocr : MISTRAL_API_KEY manquante.")
    try:
        from mistralai import Mistral  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AdapterStepError(
            "mistral_ocr : SDK non installé (pip install 'cinoc[mistral]')."
        ) from exc
    path = Path(image_path)
    media = _MEDIA.get(path.suffix.lower(), "image/png")
    image_b64 = b64encode(path.read_bytes()).decode("ascii")
    client_kwargs: dict[str, object] = {"api_key": api_key}
    timeout = deadline.as_sdk_timeout()
    if timeout is not None:
        client_kwargs["timeout_ms"] = int(timeout * 1000)
    try:
        client = Mistral(**client_kwargs)  # type: ignore[arg-type]
        response = client.ocr.process(
            model=model,
            document={
                "type": "image_url",
                "image_url": f"data:{media};base64,{image_b64}",
            },
        )
    except Exception as exc:  # le SDK lève des erreurs HTTP/SDK variées
        raise AdapterStepError(
            f"mistral_ocr a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    return sdk_native(response, "mistral_ocr")


class MistralOCRAdapter:
    """OCR cloud Mistral : ``IMAGE`` → ``RAW_TEXT`` (markdown) + ``NATIVE_JSON``."""

    def __init__(self, *, label: str, model: str = _DEFAULT_MODEL) -> None:
        if not label or not all(c.isalnum() or c in "_-" for c in label):
            raise AdapterStepError(f"mistral_ocr : label invalide {label!r}.")
        self._label = label
        self._model = model

    @property
    def name(self) -> str:
        return f"mistral_ocr:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    def effective_settings(self) -> dict[str, str]:
        """Le modèle **demandé**, défaut compris : manifeste et empreinte. Le
        modèle servi (``mistral-ocr-latest`` → ``mistral-ocr-2505``) est lu dans
        chaque réponse."""
        return {"model": self._model}

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON})

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        return run_remote_image_to_text(
            name=self.name,
            label=self._label,
            inputs=inputs,
            context=context,
            control=control,
            call=lambda image_uri: _invoke_mistral_ocr(
                model=self._model, image_path=image_uri, deadline=context.deadline
            ),
            extract=_text_from_response,
            served=served_model,
        )


__all__ = ["MistralOCRAdapter"]
