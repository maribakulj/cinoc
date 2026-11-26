"""``OpenAIAdapter`` — post-correction LLM **et** transcription VLM (API OpenAI).

Implémente le ``Module`` Protocol. Trois modes (``PipelineMode``) selon le rôle
passé à la construction : ``text_only`` (``RAW_TEXT`` → ``CORRECTED_TEXT``),
``text_and_image`` (image + texte → corrigé), ``zero_shot`` (image → texte). La
clé vient de ``OPENAI_API_KEY`` ; le SDK ``openai`` est un **extra** importé
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

Cible : ``OPENAI_BASE_URL`` (le contournement d'aujourd'hui pour un serveur
OpenAI-compatible, vLLM…) est lue **à la construction**, transmise au client et
écrite dans les réglages effectifs (``base_url``) — donc au manifeste et dans
l'empreinte de l'étape : un autre endpoint n'est plus pris pour le même modèle.
Sans elle, l'URL par défaut du SDK, écrite aussi.

Délai fini (``timeout``, défaut 600 s, retries compris), passé à **chaque**
appel ; client construit avec ``max_retries=0`` — le SDK retentait deux fois
sous chacune des cinq tentatives de Cinoc —, la seule politique de retry est
``call_resilient`` (429, 5xx, transport).
"""

from __future__ import annotations

from typing import Any, ClassVar

from cinoc.adapters._native import endpoint_from_env, sdk_native, served_model
from cinoc.adapters._resilience import (
    DEFAULT_LLM_TIMEOUT,
    call_resilient,
    register_close,
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
    normalize_llm_content,
    run_llm_step,
    stop_reason_from,
    usage_tokens,
    validate_llm_label,
    validate_role,
    wire_field,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError, CinocError
from cinoc.domain.pipeline import PipelineMode
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

#: 2 : raison d'arrêt lue, réglages d'inférence transmis (``temperature``,
#: ``top_p``, ``seed``, ``max_completion_tokens``) — une sortie peut changer.
#: 2.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas.
_VERSION = "2.1"
_DEFAULT_MODEL = "gpt-4o-mini"
#: Endpoint lu dans l'environnement par le SDK openai ; défaut = celui du SDK.
_BASE_URL_ENV = "OPENAI_BASE_URL"
_DEFAULT_BASE_URL = "https://api.openai.com/v1"

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
    """
    usage = wire_field(response, "usage")
    tokens_in = usage_tokens(wire_field(usage, "prompt_tokens"))
    tokens_out = usage_tokens(wire_field(usage, "completion_tokens"))
    choices = wire_field(response, "choices")
    model = served_model(response)
    if not isinstance(choices, list) or not choices:
        return LLMCompletion("", tokens_in, tokens_out, native=response, model=model)
    choice = choices[0]
    return LLMCompletion(
        normalize_llm_content(wire_field(wire_field(choice, "message"), "content")),
        tokens_in,
        tokens_out,
        stop_reason_from(wire_field(choice, "finish_reason"), _STOP_REASONS),
        native=response,
        model=model,
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
) -> LLMCompletion:
    """Appel ``chat.completions`` partagé (texte ou multimodal)."""
    import os

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise AdapterStepError("openai : OPENAI_API_KEY manquante.")
    try:
        from openai import OpenAI, OpenAIError  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AdapterStepError(
            "openai : SDK non installé (pip install 'cinoc[openai]')."
        ) from exc
    kwargs = _request_kwargs(model, messages, settings)
    try:
        # SDK openai typé strictement ; kwargs valides à l'exécution (tests live).
        # ``max_retries=0`` : une seule politique de retry, celle de Cinoc.
        client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        if control is not None:
            register_close(control, client)

        def _create() -> Any:
            return client.chat.completions.create(  # type: ignore[call-overload]
                **kwargs, timeout=request_timeout(deadline)
            )

        # Cap de concurrence (≤ N appels OpenAI simultanés) + retry borné sur
        # 429/5xx/transport (Retry-After respecté), dans le délai de l'étape.
        response = call_resilient(
            "openai", _create, deadline=deadline, control=control
        )
    except CinocError:
        raise  # délai, annulation : déjà typés
    except OpenAIError as exc:
        raise AdapterStepError(
            f"openai a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    return _completion_from_chat(sdk_native(response, "openai"))


def _invoke_openai(
    *,
    model: str,
    prompt: str,
    deadline: Deadline,
    settings: InferenceSettings,
    base_url: str = _DEFAULT_BASE_URL,
    control: RunControl | None = None,
) -> LLMCompletion:
    return _openai_client(
        model,
        [{"role": "user", "content": prompt}],
        deadline,
        settings,
        base_url,
        control,
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
    )


class OpenAIAdapter:
    """Adapter OpenAI multi-mode (post-correction texte/image, transcription VLM)."""

    #: Modes que cet adapter implémente **réellement**. Déclaré ici, à côté du
    #: code qui les rend possibles : la capacité vision est une closure passée à
    #: ``run_llm_step``, invérifiable de l'extérieur. Une liste tenue ailleurs
    #: dérive — c'est arrivé (D-233).
    SUPPORTED_MODES: ClassVar[frozenset[PipelineMode]] = frozenset(
        {"text_only", "text_and_image", "zero_shot", "refine"}
    )


    def __init__(
        self,
        *,
        label: str,
        model: str = _DEFAULT_MODEL,
        role: str = "text_only",
        prompt: str | None = None,
        temperature: float | None = DEFAULT_TEMPERATURE,
        top_p: float | None = None,
        seed: int | None = DEFAULT_SEED,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: object = DEFAULT_LLM_TIMEOUT,
    ) -> None:
        self._label = validate_llm_label(label, "OpenAIAdapter")
        self._timeout = validate_timeout(timeout, "OpenAIAdapter")
        self._settings = InferenceSettings.build(
            temperature=temperature, top_p=top_p, seed=seed, max_tokens=max_tokens
        )
        self._model = model
        self._role: PipelineMode = validate_role(
            role, "OpenAIAdapter", self.SUPPORTED_MODES
        )
        self._prompt = (
            prompt if prompt is not None else default_prompt_for_role(self._role)
        )
        self._base_url, self._public_base_url = endpoint_from_env(
            _BASE_URL_ENV, _DEFAULT_BASE_URL
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
            base_url=self._public_base_url,
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


__all__ = ["OpenAIAdapter"]
