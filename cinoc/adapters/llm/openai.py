"""``OpenAIAdapter`` — post-correction LLM **et** transcription VLM (API OpenAI).

Implémente le ``Module`` Protocol. Trois modes (``PipelineMode``) selon le rôle
passé à la construction : ``text_only`` (``RAW_TEXT`` → ``CORRECTED_TEXT``),
``text_and_image`` (image + texte → corrigé), ``zero_shot`` (image → texte). La
clé vient de ``OPENAI_API_KEY`` (ou de ``api_key_env``, ci-dessous) ; le SDK
``openai`` est un **extra** importé
paresseusement dans ``_invoke_openai`` / ``_invoke_openai_vision`` (isolés →
**mockables**, CI sans clé ni réseau). La ``Deadline`` borne l'appel.

Réglages (``InferenceSettings``) : ``temperature``, ``top_p``, ``seed`` et
``max_tokens`` — ce dernier envoyé comme ``max_completion_tokens`` : ``max_tokens``
est déprécié par l'API et refusé par les modèles de raisonnement (série o,
gpt-5). Ces modèles refusent aussi une ``temperature`` autre que 1 : l'API
répond 400, le SDK lève ``BadRequestError`` (un ``OpenAIError``), traduit en
``AdapterStepError`` → l'unité échoue avec le message de l'API (motif
``engine``), le run continue, et ``call_resilient`` ne rejoue pas un 400.
``temperature=None`` (API Python) ne l'envoie pas.

Cible **par instance** (P5f 6) : ``base_url`` — un serveur OpenAI-compatible
(vLLM, SGLang, Ollama ``/v1``, serveur local) — et ``api_key_env``, le **nom**
de la variable qui porte sa clé, jamais la valeur. Deux instances d'un même run
visent donc deux serveurs ; ``OPENAI_BASE_URL``, variable du processus qui les
redirigeait toutes, n'est plus lue. ``base_url`` est validé à la construction
(``validate_endpoint`` : http(s), ni identifiants, ni *query string*), écrit dans
les réglages effectifs — donc au manifeste et dans l'empreinte de l'étape : un
autre serveur n'est pas pris pour le même modèle. Sans saisie, l'endpoint
d'OpenAI, écrit aussi.

Clé : à l'endpoint d'OpenAI, ``OPENAI_API_KEY`` par défaut ; à tout autre, **aucune
par défaut** — la clé d'OpenAI ne part chez un tiers que si on la nomme. Un serveur
local sans authentification (vLLM ou SGLang sans ``--api-key``, Ollama) reçoit
alors ``_NO_KEY``, que le SDK exige et que le serveur ignore. Une variable
nommée mais absente ou vide est une erreur nommée, avant tout appel.

``self_hosted: true`` déclare un serveur que l'opérateur fait tourner lui-même :
l'économie ne lui applique aucun tarif de fournisseur (« auto-hébergé ») ; un
endpoint tiers non déclaré reste « tarif inconnu » — jamais le prix d'OpenAI.
Le créneau réseau est celui du **serveur** (``endpoint_slot_key``), pas du
fournisseur.

Délai fini (``timeout``, défaut 600 s, retries compris), passé à **chaque**
appel ; client construit avec ``max_retries=0`` — le SDK retentait deux fois
sous chacune des cinq tentatives de Cinoc —, la seule politique de retry est
``call_resilient`` (429, 5xx, transport).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, ClassVar

from cinoc.adapters._native import sdk_native, served_model, validate_endpoint
from cinoc.adapters._resilience import (
    DEFAULT_LLM_TIMEOUT,
    call_resilient,
    cut_on_cancel_hooks,
    request_timeout,
    step_deadline,
    validate_timeout,
)
from cinoc.adapters.llm._base import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_SEED,
    DEFAULT_TEMPERATURE,
    EffectiveSettings,
    InferenceSettings,
    LLMCompletion,
    StopReason,
    default_prompt_for_role,
    llm_effective_settings,
    llm_input_types,
    llm_output_types,
    llm_params,
    normalize_llm_content,
    run_llm_step,
    stop_reason_from,
    usage_tokens,
    validate_llm_label,
    validate_role,
    wire_field,
)
from cinoc.adapters.llm._listing import (
    LISTING_TIMEOUT,
    ModelInfo,
    ModelListingError,
    declared_text,
    require_model,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError, CinocError
from cinoc.domain.pipeline import PipelineMode
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

#: 2 : raison d'arrêt lue, réglages d'inférence transmis (``temperature``,
#: ``top_p``, ``seed``, ``max_completion_tokens``) — une sortie peut changer.
#: 2.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas.
_VERSION = "2.1"
#: L'endpoint d'OpenAI — celui de la table de tarifs (``pricing.json``).
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_KEY_ENV = "OPENAI_API_KEY"
#: Variable que le SDK lisait pour **toutes** les instances ; plus lue.
_RETIRED_BASE_URL_ENV = "OPENAI_BASE_URL"
#: Clé envoyée à un serveur sans authentification : le SDK en exige une, le
#: serveur l'ignore. Jamais une vraie clé, jamais lue dans l'environnement.
_NO_KEY = "cinoc-no-key"
#: Un nom de variable d'environnement — un nom, pas une valeur (``sk-…`` a un
#: tiret : refusé).
_KEY_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")

logger = logging.getLogger(__name__)

#: ``finish_reason`` (SDK openai 3.59 : ``stop``, ``length``, ``tool_calls``,
#: ``content_filter``, ``function_call``) → raison normalisée. Les appels
#: d'outil n'ont pas de sens ici : ``unknown``.
_STOP_REASONS: dict[str, StopReason] = {
    "stop": "stop",
    "length": "length",
    "content_filter": "refusal",
}


def _completion_from_chat(response: object) -> LLMCompletion:
    """Corps de ``chat.completions`` → ``LLMCompletion`` (texte, jetons, arrêt).

    **Pur** (aucun réseau, aucun import SDK) et lu sur le **corps** de la réponse
    — le dict que ``sdk_native`` tire du modèle du SDK, et que le sidecar
    ``NATIVE_JSON`` garde : relire le sidecar rend la même complétion. La
    cartographie usage→jetons (``prompt_tokens``/``completion_tokens``) et
    ``finish_reason`` → raison d'arrêt se teste sur cassette. Les jetons
    alimentent l'économie.

    Ventilation (SDK openai 3.60, ``CompletionUsage``) :
    ``prompt_tokens_details.cached_tokens`` et ``.cache_write_tokens`` sont des
    **parties** de ``prompt_tokens`` (guide « Prompt caching » : l'entrée
    ordinaire = entrée − lectures − écritures) ;
    ``completion_tokens_details.reasoning_tokens`` une partie de
    ``completion_tokens`` (« facturés comme jetons de sortie », guide
    « Reasoning » ; le SDK le dit aussi des prédictions rejetées). Absents →
    ``None``.
    """
    usage = wire_field(response, "usage")
    prompt = wire_field(usage, "prompt_tokens_details")
    read = usage_tokens(wire_field(prompt, "cached_tokens"))
    write = usage_tokens(wire_field(prompt, "cache_write_tokens"))
    reasoning = usage_tokens(
        wire_field(wire_field(usage, "completion_tokens_details"), "reasoning_tokens")
    )
    tokens_in = usage_tokens(wire_field(usage, "prompt_tokens"))
    tokens_out = usage_tokens(wire_field(usage, "completion_tokens"))
    choices = wire_field(response, "choices")
    model = served_model(response)
    if not isinstance(choices, list) or not choices:
        return LLMCompletion(
            "",
            tokens_in,
            tokens_out,
            native=response,
            model=model,
            tokens_cache_read=read,
            tokens_cache_write=write,
            tokens_reasoning=reasoning,
        )
    choice = choices[0]
    return LLMCompletion(
        normalize_llm_content(wire_field(wire_field(choice, "message"), "content")),
        tokens_in,
        tokens_out,
        stop_reason_from(wire_field(choice, "finish_reason"), _STOP_REASONS),
        native=response,
        model=model,
        tokens_cache_read=read,
        tokens_cache_write=write,
        tokens_reasoning=reasoning,
    )


def _request_kwargs(
    model: str, messages: list[dict[str, object]], settings: InferenceSettings
) -> dict[str, object]:
    """Arguments de ``chat.completions.create`` — **pur**, testé sans SDK.

    Un réglage ``None`` n'est pas envoyé : c'est le fournisseur qui décide, et le
    manifeste dit ``None``, pas un défaut supposé.
    """
    kwargs: dict[str, object] = {"model": model, "messages": messages}
    if settings.temperature is not None:
        kwargs["temperature"] = settings.temperature
    if settings.top_p is not None:
        kwargs["top_p"] = settings.top_p
    if settings.seed is not None:
        kwargs["seed"] = settings.seed
    kwargs["max_completion_tokens"] = settings.max_tokens
    return kwargs


def _openai_client(
    model: str,
    messages: list[dict[str, object]],
    deadline: Deadline,
    settings: InferenceSettings,
    base_url: str = _DEFAULT_BASE_URL,
    control: RunControl | None = None,
    api_key_env: str | None = _DEFAULT_KEY_ENV,
) -> LLMCompletion:
    """Appel ``chat.completions`` partagé (texte ou multimodal)."""
    if api_key_env is None:
        api_key = _NO_KEY
    else:
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            raise AdapterStepError(
                f"openai : {api_key_env} manquante (variable de la clé, "
                "api_key_env) — absente ou vide."
            )
    try:
        from openai import (  # type: ignore[import-not-found]
            DefaultHttpxClient,
            OpenAI,
            OpenAIError,
        )
    except ImportError as exc:
        raise AdapterStepError(
            "openai : SDK non installé (pip install 'cinoc[openai]')."
        ) from exc
    kwargs = _request_kwargs(model, messages, settings)
    ctrl = control if control is not None else RunControl()
    # Le client HTTP du SDK, ses défauts compris, + la trace qui coupe l'appel
    # en vol à l'arrêt (``cut_on_cancel_hooks``).
    http = DefaultHttpxClient(event_hooks=cut_on_cancel_hooks(ctrl))
    try:
        # SDK openai typé strictement ; kwargs valides à l'exécution (tests live).
        # ``max_retries=0`` : une seule politique de retry, celle de Cinoc.
        client = OpenAI(
            api_key=api_key, base_url=base_url, max_retries=0, http_client=http
        )

        def _create() -> Any:
            return client.chat.completions.create(  # type: ignore[call-overload]
                **kwargs, timeout=request_timeout(deadline)
            )

        # Cap de concurrence (≤ N appels simultanés **par serveur**) + retry borné sur
        # 429/5xx/transport (Retry-After respecté), dans le délai de l'étape.
        response = call_resilient(
            "openai", _create, deadline=deadline, endpoint=base_url, control=ctrl
        )
    except CinocError:
        raise  # délai, annulation : déjà typés
    except OpenAIError as exc:
        raise AdapterStepError(
            f"openai a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        http.close()
    return _completion_from_chat(sdk_native(response, "openai"))


def _invoke_openai(
    *,
    model: str,
    prompt: str,
    deadline: Deadline,
    settings: InferenceSettings,
    base_url: str = _DEFAULT_BASE_URL,
    control: RunControl | None = None,
    api_key_env: str | None = _DEFAULT_KEY_ENV,
) -> LLMCompletion:
    return _openai_client(
        model,
        [{"role": "user", "content": prompt}],
        deadline,
        settings,
        base_url,
        control,
        api_key_env,
    )


def _invoke_openai_vision(
    *,
    model: str,
    prompt: str,
    media_type: str,
    image_b64: str,
    deadline: Deadline,
    settings: InferenceSettings,
    base_url: str = _DEFAULT_BASE_URL,
    control: RunControl | None = None,
    api_key_env: str | None = _DEFAULT_KEY_ENV,
) -> LLMCompletion:
    content = [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
        },
    ]
    return _openai_client(
        model,
        [{"role": "user", "content": content}],
        deadline,
        settings,
        base_url,
        control,
        api_key_env,
    )


def _endpoint(base_url: object, api_key_env: object) -> tuple[str, str | None]:
    """``(endpoint, variable de la clé)`` d'une instance, validés.

    Sans ``base_url`` : l'endpoint d'OpenAI et ``OPENAI_API_KEY``. Avec : aucune
    clé par défaut — celle d'OpenAI n'a pas à partir chez un tiers.
    """
    if base_url is None:
        if os.environ.get(_RETIRED_BASE_URL_ENV, "").strip():
            logger.warning(
                "[openai] %s n'est plus lue : la cible se déclare par instance "
                "(base_url dans adapter_kwargs) — appel à %s.",
                _RETIRED_BASE_URL_ENV,
                _DEFAULT_BASE_URL,
            )
        url = _DEFAULT_BASE_URL
    else:
        url = validate_endpoint(base_url, "OpenAIAdapter")
    if api_key_env is None:
        return url, _DEFAULT_KEY_ENV if url == _DEFAULT_BASE_URL else None
    if not isinstance(api_key_env, str) or not _KEY_ENV_NAME.fullmatch(api_key_env):
        raise AdapterStepError(
            "OpenAIAdapter : api_key_env doit être le **nom** d'une variable "
            "d'environnement (lettres, chiffres, _ ; 128 au plus) — la valeur "
            "reçue n'est pas citée : ce pourrait être la clé elle-même."
        )
    return url, api_key_env


def instance_key_env(base_url: object, api_key_env: object) -> str | None:
    """La variable de clé qu'une **instance** exige (``None`` : aucune).

    Même règle que l'adaptateur, pour que la disponibilité d'une instance se
    décide avant de la construire : un serveur auto-hébergé sans
    ``api_key_env`` n'a pas besoin d'``OPENAI_API_KEY``. Réglages invalides →
    ``AdapterStepError``, comme à la construction.
    """
    return _endpoint(base_url, api_key_env)[1]


def models_from_listing(items: object) -> tuple[ModelInfo, ...]:
    """Éléments de ``GET /v1/models`` → modèles, triés par nom. **Pur.**

    OpenAI ne déclare **ni la vision ni le cycle de vie** : ils restent
    inconnus (``None``) ; ``shutdown_date``, quand l'API la donne, est l'arrêt
    annoncé (``retires_at``). Un serveur OpenAI-compatible (vLLM, Ollama
    ``/v1``) rend la même forme.
    """
    found: dict[str, ModelInfo] = {}
    for item in items if isinstance(items, list) else ():
        name = declared_text(item.get("id")) if isinstance(item, dict) else None
        if name is not None:
            found[name] = ModelInfo(
                name=name, retires_at=declared_text(item.get("shutdown_date"))
            )
    return tuple(found[name] for name in sorted(found))


def list_models(
    *,
    base_url: object = None,
    api_key_env: object = None,
    timeout: float = LISTING_TIMEOUT,
) -> tuple[ModelInfo, ...]:
    """Les modèles que l'endpoint d'une instance sert, **demandés en direct**
    (``models.list``) — celui d'OpenAI par défaut, un serveur auto-hébergé sous
    ``base_url``. Liste illisible → ``ModelListingError`` (raison, sans la clé
    ni le message de l'API, qui peut en citer un fragment)."""
    url, key_env = _endpoint(base_url, api_key_env)
    api_key = _NO_KEY if key_env is None else os.environ.get(key_env, "")
    if not api_key:
        raise ModelListingError(f"clé {key_env} absente")
    try:
        from openai import OpenAI, OpenAIError  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ModelListingError("SDK openai non installé (extra [openai])") from exc
    try:
        client = OpenAI(api_key=api_key, base_url=url, max_retries=0, timeout=timeout)
        items = [sdk_native(model, "openai") for model in client.models.list()]
    except OpenAIError as exc:
        status = getattr(exc, "status_code", None)
        raise ModelListingError(
            f"{url} : {type(exc).__name__}" + (f" ({status})" if status else "")
        ) from exc
    return models_from_listing(items)


class OpenAIAdapter:
    """Adapter OpenAI multi-mode (post-correction texte/image, transcription VLM)."""

    #: Modes que cet adapter implémente **réellement**. Déclaré ici, à côté du
    #: code qui les rend possibles : la capacité vision est une closure passée à
    #: ``run_llm_step``, invérifiable de l'extérieur. Une liste tenue ailleurs
    #: dérive — c'est arrivé (D-233).
    SUPPORTED_MODES: ClassVar[frozenset[PipelineMode]] = frozenset(
        {"text_only", "text_and_image", "zero_shot", "refine"}
    )
    #: Réglages acceptés : ceux des quatre fournisseurs, plus la cible de
    #: l'instance. ``api_key_env`` et ``self_hosted`` sont d'**exploitation** :
    #: le nom d'une variable et un marqueur d'économie ne changent aucune
    #: sortie — hors de l'empreinte (D-293 les y faisait entrer). ``base_url``,
    #: lui, est la cible : il y entre, normalisé (``validate_endpoint``).
    PARAMS: ClassVar[tuple[Param, ...]] = llm_params(
        SUPPORTED_MODES,
        extra=(
            Param("base_url", "str", "Endpoint OpenAI-compatible (défaut : OpenAI)",
                  "OpenAI-compatible endpoint (default: OpenAI)"),
            Param("api_key_env", "str", "Nom de la variable de la clé",
                  "Name of the key's variable", affects_output=False),
            Param("self_hosted", "bool", "Serveur auto-hébergé (économie)",
                  "Self-hosted server (economics)", default=False,
                  affects_output=False),
        ),
    )


    def __init__(
        self,
        *,
        label: str,
        model: str,
        role: str = "text_only",
        prompt: str | None = None,
        temperature: float | None = DEFAULT_TEMPERATURE,
        top_p: float | None = None,
        seed: int | None = DEFAULT_SEED,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: object = DEFAULT_LLM_TIMEOUT,
        base_url: object = None,
        api_key_env: object = None,
        self_hosted: object = False,
    ) -> None:
        self._label = validate_llm_label(label, "OpenAIAdapter")
        self._timeout = validate_timeout(timeout, "OpenAIAdapter")
        self._settings = InferenceSettings.build(
            temperature=temperature, top_p=top_p, seed=seed, max_tokens=max_tokens
        )
        self._model = require_model(model, "OpenAIAdapter")
        self._role: PipelineMode = validate_role(
            role, "OpenAIAdapter", self.SUPPORTED_MODES
        )
        self._prompt = (
            prompt if prompt is not None else default_prompt_for_role(self._role)
        )
        self._base_url, self._api_key_env = _endpoint(base_url, api_key_env)
        if not isinstance(self_hosted, bool):
            raise AdapterStepError(
                f"OpenAIAdapter : self_hosted (booléen) attendu, reçu {self_hosted!r}."
            )
        if self_hosted and self._base_url == _DEFAULT_BASE_URL:
            raise AdapterStepError(
                "OpenAIAdapter : self_hosted exige un base_url — l'endpoint "
                "d'OpenAI n'est pas un serveur auto-hébergé."
            )

    @property
    def name(self) -> str:
        return f"openai:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    def effective_settings(self) -> EffectiveSettings:
        """Réglages **effectifs** (défauts et endpoint compris) : manifeste et
        empreinte de l'étape."""
        return llm_effective_settings(
            model=self._model,
            role=self._role,
            prompt=self._prompt,
            settings=self._settings,
            base_url=self._base_url,
        )

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return llm_input_types(self._role)

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return llm_output_types(self._role)

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        deadline = step_deadline(context.deadline, self._timeout)

        def text_invoke(prompt: str) -> LLMCompletion:
            return _invoke_openai(
                model=self._model,
                prompt=prompt,
                deadline=deadline,
                settings=self._settings,
                base_url=self._base_url,
                control=control,
                api_key_env=self._api_key_env,
            )

        def vision_invoke(
            prompt: str, media_type: str, image_b64: str
        ) -> LLMCompletion:
            return _invoke_openai_vision(
                model=self._model,
                prompt=prompt,
                media_type=media_type,
                image_b64=image_b64,
                deadline=deadline,
                settings=self._settings,
                base_url=self._base_url,
                control=control,
                api_key_env=self._api_key_env,
            )

        return run_llm_step(
            role=self._role,
            label=self._label,
            name=self.name,
            prompt=self._prompt,
            inputs=inputs,
            context=context,
            control=control,
            text_invoke=text_invoke,
            vision_invoke=vision_invoke,
            max_tokens=self._settings.max_tokens,
        )


__all__ = [
    "OpenAIAdapter",
    "instance_key_env",
    "list_models",
    "models_from_listing",
]
