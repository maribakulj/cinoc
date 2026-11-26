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
"""

from __future__ import annotations

import os
import time
from base64 import b64encode
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cinoc.adapters.ocr._base import run_remote_image_to_text
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

if TYPE_CHECKING:  # annotations seules — pas d'import httpx au chargement du module
    import httpx

#: 1.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas.
_VERSION = "1.1"
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


def _invoke_azure_di(
    *,
    endpoint: str,
    image_path: str,
    deadline: Deadline,
    key: str,
    transport: httpx.BaseTransport | None = None,
    poll_interval: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
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
    content = b64encode(Path(image_path).read_bytes()).decode("ascii")
    analyze_url = endpoint.rstrip("/") + _ANALYZE_PATH
    with httpx.Client(
        timeout=deadline.as_sdk_timeout(), transport=transport
    ) as client:
        operation_url = _submit_analysis(
            client, analyze_url=analyze_url, key=key, content=content
        )
        return _poll_result(
            client,
            operation_url=operation_url,
            key=key,
            deadline=deadline,
            poll_interval=poll_interval,
            sleep=sleep,
        )


def _submit_analysis(
    client: httpx.Client, *, analyze_url: str, key: str, content: str
) -> str:
    """POST l'analyse ; renvoie l'URL ``Operation-Location`` à sonder."""
    import httpx

    headers = {_KEY_HEADER: key, "Content-Type": "application/json"}
    try:
        response = client.post(
            analyze_url,
            params={"api-version": _API_VERSION},
            headers=headers,
            json={"base64Source": content},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AdapterStepError(
            f"azure_di : statut HTTP {exc.response.status_code} (soumission)."
        ) from exc
    except httpx.HTTPError as exc:
        raise AdapterStepError(
            f"azure_di : échec de transport (soumission) : {type(exc).__name__}."
        ) from exc
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
    poll_interval: float,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    """Sonde l'``Operation-Location`` jusqu'à un état terminal (ou délai)."""
    import httpx

    for _ in range(_MAX_POLLS):
        try:
            response = client.get(operation_url, headers={_KEY_HEADER: key})
            response.raise_for_status()
            data = response.json()
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
            break
        sleep(poll_interval)
    raise AdapterStepError("azure_di : analyse non terminée (délai de sonde dépassé).")


class AzureDocIntelAdapter:
    """OCR cloud Azure DI : ``IMAGE`` → ``RAW_TEXT`` + ``NATIVE_JSON``."""

    def __init__(self, *, label: str) -> None:
        if not label or not all(c.isalnum() or c in "_-" for c in label):
            raise AdapterStepError(f"azure_di : label invalide {label!r}.")
        self._label = label

    @property
    def name(self) -> str:
        return f"azure_di:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

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
        def call(image_uri: str) -> dict[str, Any]:
            endpoint = os.environ.get(_ENDPOINT_ENV)
            key = os.environ.get(_KEY_ENV)
            if not endpoint:
                raise AdapterStepError(f"{self.name} : {_ENDPOINT_ENV} manquant.")
            if not key:
                raise AdapterStepError(f"{self.name} : {_KEY_ENV} manquante.")
            return _invoke_azure_di(
                endpoint=endpoint,
                image_path=image_uri,
                deadline=context.deadline,
                key=key,
            )

        return run_remote_image_to_text(
            name=self.name,
            label=self._label,
            inputs=inputs,
            context=context,
            control=control,
            call=call,
            extract=_extract_text,
        )


__all__ = ["AzureDocIntelAdapter"]
