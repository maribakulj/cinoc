"""``MistralOCRAdapter`` — OCR cloud (API Mistral OCR), facturé à la page.

Premier moteur **payant à la page** du socle : donne un sens réel à l'axe
coût du Pareto (économie T10, tarif ``cloud_page_kinds``). Implémente le
``Module`` Protocol ; SDK ``mistralai`` = extra (``cinoc[mistral]``), importé
paresseusement dans ``_invoke_mistral_ocr`` (mockable, CI sans clé ni réseau).
Clé ``MISTRAL_API_KEY``. Sortie : le **texte** des pages — leur markdown
débarrassé de sa syntaxe (``markdown_to_text`` : ``#``, ``**``, ``|---|``,
``![img](…)`` ne sont pas la page et ne doivent pas être notés) —, **lu** dans
la réponse par :func:`_text_from_response` ; la réponse entière (pages, images,
dimensions, en-têtes et pieds, blocs) gardée en sidecar ``NATIVE_JSON`` (un
appel par page) ; et, quand la réponse porte des **blocs**, leur projection en
``LAYOUT`` (``_mistral_layout.layout_from_response``), depuis ce même corps.

La requête **demande** les blocs (``include_blocks=True``) et leurs confiances
(``confidence_scores_granularity="block"``) : sans eux, la projection n'avait
rien à lire. Un modèle antérieur à OCR 4 répond ``blocks: []`` — pas de
``LAYOUT``, le texte reste noté. SDK épinglé par majeure (``mistralai>=3,<4``) :
la 1.x n'avait pas ces paramètres et retirait ``blocks`` et
``confidence_scores`` de la réponse qu'elle décodait.

Délai fini (``timeout``, défaut 120 s, retries compris), passé à chaque appel
(``timeout_ms``) ; le SDK est construit **sans** sa politique de retry
(``retry_config=None``) et l'appel passe par ``call_resilient`` (429, 5xx,
transport), sous le quota du fournisseur ``mistral`` (même clé, même compte que
le chat). Facturé à la page : chaque tentative facturable est comptée (règle :
``adapters/_resilience``).
"""

from __future__ import annotations

from base64 import b64encode
from pathlib import Path
from typing import Any

from cinoc.adapters._native import sdk_native, served_model
from cinoc.adapters._resilience import (
    DEFAULT_OCR_TIMEOUT,
    BillingMeter,
    call_resilient,
    register_close,
    request_timeout,
    step_deadline,
    validate_timeout,
)
from cinoc.adapters.llm._listing import require_model
from cinoc.adapters.ocr._base import run_remote_image_to_text
from cinoc.adapters.ocr._mistral_layout import layout_from_response
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError, CinocError
from cinoc.formats.text import markdown_to_text
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

#: 1.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas. 1.2 : le texte est le markdown **sans sa syntaxe** (il
#: change), et un ``LAYOUT`` est publié quand la réponse porte des blocs.
#: 1.3 : la requête demande les blocs et leurs confiances (``include_blocks``,
#: ``confidence_scores_granularity="block"``) — le sidecar et le ``LAYOUT``
#: changent : une archive 1.2 est ré-exécutée, pas relue sans ses blocs.
_VERSION = "1.3"
#: Granularité des confiances demandées : celle de la projection
#: (``Region.confidence`` = ``block_type_confidence_score``).
_CONFIDENCE_GRANULARITY = "block"
_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff"}


def _text_from_response(native: object) -> str:
    """Corps de ``POST /v1/ocr`` → texte : le markdown des pages, sans sa
    syntaxe, une page après l'autre (séparées d'un saut de ligne).

    **Pur** : c'est la seule lecture du texte, à l'exécution comme à la
    relecture d'un sidecar.
    """
    pages = native.get("pages") if isinstance(native, dict) else None
    if not isinstance(pages, list):
        return ""
    texts = (
        markdown_to_text(str(page.get("markdown") or ""))
        for page in pages
        if isinstance(page, dict)
    )
    return "\n".join(texts).strip()


def _invoke_mistral_ocr(
    *,
    model: str,
    image_path: str,
    deadline: Deadline,
    control: RunControl | None = None,
    meter: BillingMeter | None = None,
) -> dict[str, Any]:
    """Appelle l'OCR et rend le **corps** de la réponse (dump du modèle du SDK)."""
    import os

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise AdapterStepError("mistral_ocr : MISTRAL_API_KEY manquante.")
    try:
        from mistralai.client import Mistral  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AdapterStepError(
            "mistral_ocr : SDK non installé (pip install 'cinoc[mistral]')."
        ) from exc
    path = Path(image_path)
    media = _MEDIA.get(path.suffix.lower(), "image/png")
    image_b64 = b64encode(path.read_bytes()).decode("ascii")
    try:
        # ``retry_config=None`` : une seule politique de retry, celle de Cinoc.
        client = Mistral(api_key=api_key, retry_config=None)
        if control is not None:
            register_close(control, client)

        def process() -> Any:
            timeout = request_timeout(deadline)
            return client.ocr.process(
                model=model,
                document={
                    "type": "image_url",
                    "image_url": f"data:{media};base64,{image_b64}",
                },
                include_blocks=True,
                confidence_scores_granularity=_CONFIDENCE_GRANULARITY,
                timeout_ms=int(timeout * 1000) if timeout is not None else None,
            )

        response = call_resilient(
            "mistral", process, deadline=deadline, control=control, meter=meter
        )
    except CinocError:
        raise  # délai, annulation : déjà typés
    except Exception as exc:  # le SDK lève des erreurs HTTP/SDK variées
        raise AdapterStepError(
            f"mistral_ocr a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    return sdk_native(response, "mistral_ocr")


class MistralOCRAdapter:
    """OCR cloud Mistral : ``IMAGE`` → ``RAW_TEXT`` + ``NATIVE_JSON`` (+ ``LAYOUT``
    quand la réponse porte des blocs — publié en plus, non déclaré : une réponse
    sans blocs n'en a pas)."""

    def __init__(
        self,
        *,
        label: str,
        model: str,
        timeout: object = DEFAULT_OCR_TIMEOUT,
    ) -> None:
        if not label or not all(c.isalnum() or c in "_-" for c in label):
            raise AdapterStepError(f"mistral_ocr : label invalide {label!r}.")
        self._label = label
        self._model = require_model(model, "mistral_ocr")
        self._timeout = validate_timeout(timeout, "mistral_ocr")

    @property
    def name(self) -> str:
        return f"mistral_ocr:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    def effective_settings(self) -> dict[str, str]:
        """Le modèle **demandé** (nommé par la spec) : manifeste et empreinte. Le
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
        deadline = step_deadline(context.deadline, self._timeout)
        return run_remote_image_to_text(
            name=self.name,
            label=self._label,
            inputs=inputs,
            context=context,
            control=control,
            call=lambda image_uri, meter: _invoke_mistral_ocr(
                model=self._model,
                image_path=image_uri,
                deadline=deadline,
                control=control,
                meter=meter,
            ),
            extract=_text_from_response,
            served=served_model,
            layout=layout_from_response,
        )


__all__ = ["MistralOCRAdapter"]
