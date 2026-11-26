"""``AzureDocIntelAdapter`` — OCR cloud (Azure AI Document Intelligence, modèle Read).

Moteur cloud **first-party**. API **REST** (``httpx``) plutôt que le SDK
``azure-ai-documentintelligence`` (lourd, auth credential) : transport léger,
**testable par cassette HTTP**. Auth par **clé d'abonnement**
(``AZURE_DOC_INTEL_KEY``) + endpoint de la ressource (``AZURE_DOC_INTEL_ENDPOINT``).
Implémente le ``Module`` Protocol **directement** ; ``httpx`` (dépendance
de base) est importé **paresseusement** (mockable, CI sans clé ni réseau).

Flux **asynchrone** propre à Azure DI (fidèlement modélisé) : ``POST …:analyze``
renvoie ``202`` + un en-tête ``Operation-Location`` ; on **sonde** cette URL
(GET) jusqu'à ``status == "succeeded"`` (ou ``failed``/délai). Sortie :
``analyzeResult.content`` du modèle ``prebuilt-read`` — le texte complet d'une page.

Sidecar ``NATIVE_JSON`` : le corps de la **sonde terminale** (``succeeded``), le
seul des appels d'une page qui porte le résultat — mots, polygones, confiances,
lignes. La soumission (202) n'a pas de corps ; les sondes ``running`` ne disent
que l'attente. Ni la clé (en-tête) ni l'``Operation-Location`` n'y entrent.

L'endpoint (``AZURE_DOC_INTEL_ENDPOINT``) désigne la ressource — donc, possiblement,
un autre déploiement : il est lu **à la construction** et écrit dans les réglages
effectifs avec le modèle et la version d'API (manifeste, empreinte de l'étape).

Confiances (``CONFIDENCES``) : ``analyzeResult.pages[].words[]`` porte, par mot,
``content`` et ``confidence`` ∈ [0, 1] — lues par :func:`_confidences` sur le même
corps (même forme que le sidecar de Tesseract).

Délai fini (``timeout``, défaut 120 s : soumission, sondes et retries compris) ;
soumission **et** sonde passent par ``call_resilient`` (429, 5xx, transport),
chacune pour elle-même : une sonde perdue se retente sur la sonde — resoumettre
ferait analyser, et facturer, la page deux fois. Une soumission acceptée (202)
est une page facturée (règle : ``adapters/_resilience``).
"""

from __future__ import annotations

import os
from base64 import b64encode
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from cinoc.adapters._native import public_endpoint
from cinoc.adapters._params import label_param, timeout_param
from cinoc.adapters._resilience import (
    DEFAULT_OCR_TIMEOUT,
    BillingMeter,
    call_resilient,
    cut_on_cancel_hooks,
    request_timeout,
    step_deadline,
    validate_timeout,
)
from cinoc.adapters.ocr._base import run_remote_image_to_text, word_confidence
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError, DeadlineExceeded
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

if TYPE_CHECKING:  # annotations seules — pas d'import httpx au chargement du module
    import httpx

#: 1.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas. 1.2 : les confiances par mot sont publiées (``CONFIDENCES``).
_VERSION = "1.2"
_PROVIDER = "azure_di"
_MODEL = "prebuilt-read"
_API_VERSION = "2024-11-30"
_ANALYZE_PATH = f"/documentintelligence/documentModels/{_MODEL}:analyze"
_KEY_HEADER = "Ocp-Apim-Subscription-Key"
_ENDPOINT_ENV = "AZURE_DOC_INTEL_ENDPOINT"
_KEY_ENV = "AZURE_DOC_INTEL_KEY"
#: Borne dure du *polling* (en plus de la ``Deadline``) — évite la boucle infinie
#: si le service reste indéfiniment ``running`` sous une deadline infinie.
_MAX_POLLS = 60


def _extract_text(data: object) -> str:
    """Texte complet de ``analyzeResult.content`` ; page vide → ``""``.

    **Pur** : la seule lecture du texte, à l'exécution comme à la relecture.
    """
    if not isinstance(data, dict):
        raise AdapterStepError("azure_di : réponse JSON inattendue (objet).")
    result = data.get("analyzeResult")
    if not isinstance(result, dict):
        raise AdapterStepError("azure_di : 'analyzeResult' absent de la réponse.")
    content = result.get("content")
    return str(content).strip() if content else ""


def _confidences(data: object) -> list[ConfidenceToken]:
    """Confiances par mot (``analyzeResult.pages[].words[]``) — **pur**.

    Un mot sans confiance, ou hors [0, 1], n'en reçoit pas : il est omis.
    """
    result = data.get("analyzeResult") if isinstance(data, dict) else None
    pages = result.get("pages") if isinstance(result, dict) else None
    tokens: list[ConfidenceToken] = []
    for page in pages if isinstance(pages, list) else ():
        words = page.get("words") if isinstance(page, dict) else None
        for word in words if isinstance(words, list) else ():
            if isinstance(word, dict):
                token = word_confidence(word.get("content"), word.get("confidence"))
                if token is not None:
                    tokens.append(token)
    return tokens


def _invoke_azure_di(
    *,
    endpoint: str,
    image_path: str,
    deadline: Deadline,
    key: str,
    control: RunControl | None = None,
    meter: BillingMeter | None = None,
    transport: httpx.BaseTransport | None = None,
    poll_interval: float = 1.0,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Analyse l'image (POST → sonde l'``Operation-Location``) et rend le corps
    de la sonde terminale (``status: succeeded``).

    ``endpoint`` vient de la **configuration opérateur** (env), pas de
    l'utilisateur → endpoint de confiance, pas de durcissement anti-SSRF (≠
    importeurs de corpus). La clé est en **en-tête** (jamais journalisée : les
    messages d'erreur ne portent que le statut). ``transport``/``sleep`` injectés
    → cassette **et** sonde déterministes en test (aucune attente réelle).
    """
    import httpx
    ctrl = control if control is not None else RunControl()
    content = b64encode(Path(image_path).read_bytes()).decode("ascii")
    analyze_url = endpoint.rstrip("/") + _ANALYZE_PATH
    # Un arrêt coupe l'appel en vol (``cut_on_cancel_hooks``) : ``close()``
    # d'un autre fil ne réveille pas une lecture bloquante.
    with httpx.Client(
        timeout=request_timeout(deadline),
        transport=transport,
        event_hooks=cut_on_cancel_hooks(ctrl),
    ) as client:
        try:
            operation_url = call_resilient(
                _PROVIDER,
                lambda: _submit_analysis(
                    client, analyze_url=analyze_url, key=key, content=content,
                    deadline=deadline,
                ),
                deadline=deadline,
                control=ctrl,
                meter=meter,
                sleep=sleep,
            )
        except httpx.HTTPStatusError as exc:
            raise AdapterStepError(
                f"azure_di : statut HTTP {exc.response.status_code} (soumission)."
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterStepError(
                f"azure_di : échec de transport (soumission) : {type(exc).__name__}."
            ) from exc
        return _poll_result(
            client,
            operation_url=operation_url,
            key=key,
            deadline=deadline,
            control=ctrl,
            poll_interval=poll_interval,
            sleep=sleep,
        )


def _submit_analysis(
    client: httpx.Client,
    *,
    analyze_url: str,
    key: str,
    content: str,
    deadline: Deadline,
) -> str:
    """POST l'analyse ; renvoie l'URL ``Operation-Location`` à sonder.

    Les erreurs HTTP remontent telles quelles : ``call_resilient`` décide de
    les retenter, l'appelant de les traduire.
    """
    headers = {_KEY_HEADER: key, "Content-Type": "application/json"}
    response = client.post(
        analyze_url,
        params={"api-version": _API_VERSION},
        headers=headers,
        json={"base64Source": content},
        timeout=request_timeout(deadline),
    )
    response.raise_for_status()
    operation_url = response.headers.get("operation-location")
    if not operation_url:
        raise AdapterStepError("azure_di : réponse sans en-tête Operation-Location.")
    return str(operation_url)


def _poll_result(
    client: httpx.Client,
    *,
    operation_url: str,
    key: str,
    deadline: Deadline,
    control: RunControl,
    poll_interval: float,
    sleep: Callable[[float], None] | None,
) -> dict[str, Any]:
    """Sonde l'``Operation-Location`` jusqu'à un état terminal (ou délai)."""
    import httpx

    def probe() -> Any:
        response = client.get(
            operation_url,
            headers={_KEY_HEADER: key},
            timeout=request_timeout(deadline),
        )
        response.raise_for_status()
        return response.json()

    for _ in range(_MAX_POLLS):
        try:
            data = call_resilient(
                _PROVIDER, probe, deadline=deadline, control=control, sleep=sleep
            )
        except httpx.HTTPStatusError as exc:
            raise AdapterStepError(
                f"azure_di : statut HTTP {exc.response.status_code} (sonde)."
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterStepError(
                f"azure_di : échec de transport (sonde) : {type(exc).__name__}."
            ) from exc
        status = (
            str(data.get("status", "")).lower() if isinstance(data, dict) else ""
        )
        if status == "succeeded":
            return dict(data)
        if status == "failed":
            raise AdapterStepError("azure_di : analyse échouée (status 'failed').")
        if deadline.is_expired():
            raise DeadlineExceeded("azure_di : délai dépassé pendant la sonde.")
        pause = deadline.clamp_to_remaining(poll_interval)
        if sleep is not None:
            sleep(pause)
        else:
            control.wait(pause)
        control.raise_if_cancelled()
    raise AdapterStepError(
        f"azure_di : analyse non terminée après {_MAX_POLLS} sondes."
    )


class AzureDocIntelAdapter:
    """OCR cloud Azure DI : ``IMAGE`` → ``RAW_TEXT`` + ``NATIVE_JSON`` +
    ``CONFIDENCES``."""

    #: Réglages acceptés (``pipeline.params``) : tout autre est refusé, nommé.
    PARAMS: ClassVar[tuple[Param, ...]] = (
        label_param(),
        timeout_param(DEFAULT_OCR_TIMEOUT),
    )

    def __init__(self, *, label: str, timeout: object = DEFAULT_OCR_TIMEOUT) -> None:
        if not label or not all(c.isalnum() or c in "_-" for c in label):
            raise AdapterStepError(f"azure_di : label invalide {label!r}.")
        self._label = label
        self._timeout = validate_timeout(timeout, "azure_di")
        #: Lu une fois : la cible inscrite est celle qu'on appelle. Absent → la
        #: construction passe (le moteur reste listé), chaque page échoue en le
        #: nommant.
        self._endpoint = os.environ.get(_ENDPOINT_ENV, "").strip() or None

    @property
    def name(self) -> str:
        return f"azure_di:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    def effective_settings(self) -> dict[str, str | None]:
        """Ressource, modèle et version d'API : manifeste et empreinte."""
        return {
            "endpoint": (
                public_endpoint(self._endpoint) if self._endpoint is not None else None
            ),
            "model": _MODEL,
            "api_version": _API_VERSION,
        }

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset(
            {ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON, ArtifactType.CONFIDENCES}
        )

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        deadline = step_deadline(context.deadline, self._timeout)

        def call(image_uri: str, meter: BillingMeter) -> dict[str, Any]:
            endpoint = self._endpoint
            key = os.environ.get(_KEY_ENV)
            if not endpoint:
                raise AdapterStepError(f"{self.name} : {_ENDPOINT_ENV} manquant.")
            if not key:
                raise AdapterStepError(f"{self.name} : {_KEY_ENV} manquante.")
            return _invoke_azure_di(
                endpoint=endpoint,
                image_path=image_uri,
                deadline=deadline,
                key=key,
                control=control,
                meter=meter,
            )

        return run_remote_image_to_text(
            name=self.name,
            label=self._label,
            inputs=inputs,
            context=context,
            control=control,
            call=call,
            extract=_extract_text,
            confidences=_confidences,
        )


__all__ = ["AzureDocIntelAdapter"]
