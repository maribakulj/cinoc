"""``MistralAdapter`` — post-correction LLM **et** transcription VLM (API Mistral).

Implémente le ``Module`` Protocol, trois modes (``PipelineMode``) selon le rôle :
``text_only`` (texte → corrigé), ``text_and_image`` (Pixtral : image + texte →
corrigé), ``zero_shot`` (Pixtral : image → texte). Clé ``MISTRAL_API_KEY`` ; SDK
``mistralai`` = **extra** importé paresseusement dans ``_invoke_mistral`` /
``_invoke_mistral_vision`` (isolés → **mockables**, CI sans clé ni réseau).

Réglages (``InferenceSettings``) : ``temperature``, ``top_p``, ``max_tokens`` et
``seed`` — ce dernier sous le nom de l'API Mistral, ``random_seed``.

Délai fini (``timeout``, défaut 600 s, retries compris), passé à **chaque**
appel (``timeout_ms``) ; client construit avec ``retry_config=None`` — le SDK
3.x n'en a pas par défaut (``retries`` reste non posé), on l'écrit pour qu'un
défaut futur ne s'ajoute pas sous celle de Cinoc : la seule politique de retry
est ``call_resilient``. SDK épinglé par majeure (``mistralai>=3,<4``) : le
client vit dans ``mistralai.client`` depuis la 2.x.
"""

from __future__ import annotations

from typing import Any, ClassVar

from cinoc.adapters._native import sdk_native, served_model
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
    declared_flag,
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

#: 2 : raison d'arrêt lue, réglages d'inférence transmis (``top_p``,
#: ``random_seed``, ``max_tokens``) — une sortie peut changer.
#: 2.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas.
_VERSION = "2.1"

#: ``finish_reason`` (SDK mistralai 3.9 : ``stop``, ``length``,
#: ``model_length``, ``error``, ``tool_calls``) → raison normalisée.
#: ``model_length`` = fenêtre du modèle épuisée : une coupure comme ``length``.
_STOP_REASONS: dict[str, StopReason] = {
    "stop": "stop",
    "length": "length",
    "model_length": "length",
    "error": "error",
}


def _completion_from_chat(response: object) -> LLMCompletion:
    """Corps de ``chat.complete`` → ``LLMCompletion`` (texte, jetons, arrêt).

    **Pur** (aucun réseau, aucun SDK) et lu sur le **corps** de la réponse — le
    dict que ``sdk_native`` tire du modèle du SDK, gardé en sidecar
    ``NATIVE_JSON`` : relire le sidecar rend la même complétion. Usage→jetons
    (``prompt_tokens``/``completion_tokens``) et ``finish_reason`` se testent sur
    cassette. Jetons → économie (coût cloud réel).

    ``usage.prompt_tokens_details.cached_tokens`` (SDK mistralai 3.9,
    ``UsageInfo``) est lu comme une partie de ``prompt_tokens`` — la forme
    d'OpenAI, que Mistral reprend ; à confirmer sur une réponse réelle. Le
    chat ne rend aucun compte de raisonnement (seule l'API Responses en a un).
    """
    usage = wire_field(response, "usage")
    cached = usage_tokens(
        wire_field(wire_field(usage, "prompt_tokens_details"), "cached_tokens")
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
            tokens_cache_read=cached,
        )
    choice = choices[0]
    return LLMCompletion(
        normalize_llm_content(wire_field(wire_field(choice, "message"), "content")),
        tokens_in,
        tokens_out,
        stop_reason_from(wire_field(choice, "finish_reason"), _STOP_REASONS),
        native=response,
        model=model,
        tokens_cache_read=cached,
    )


def _request_kwargs(
    model: str, content: object, settings: InferenceSettings
) -> dict[str, object]:
    """Arguments de ``chat.complete`` — **pur** ; un ``None`` n'est pas envoyé."""
    kwargs: dict[str, object] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }
    if settings.temperature is not None:
        kwargs["temperature"] = settings.temperature
    if settings.top_p is not None:
        kwargs["top_p"] = settings.top_p
    if settings.seed is not None:
        kwargs["random_seed"] = settings.seed
    kwargs["max_tokens"] = settings.max_tokens
    return kwargs


def _mistral_client(
    model: str,
    content: object,
    deadline: Deadline,
    settings: InferenceSettings,
    control: RunControl | None = None,
) -> LLMCompletion:
    """Appel ``chat.complete`` partagé (texte ou multimodal)."""
    import os

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise AdapterStepError("mistral : MISTRAL_API_KEY manquante.")
    try:
        from mistralai.client import Mistral  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AdapterStepError(
            "mistral : SDK non installé (pip install 'cinoc[mistral]')."
        ) from exc
    try:
        # Le SDK mistralai type strictement ses kwargs/messages ; on lui passe
        # des dicts valides à l'exécution (cf. tests live). ``ignore`` ciblé.
        # ``retry_config=None`` : une seule politique de retry, celle de Cinoc.
        client = Mistral(api_key=api_key, retry_config=None)
        if control is not None:
            register_close(control, client)

        def _complete() -> Any:
            timeout = request_timeout(deadline)
            return client.chat.complete(
                **_request_kwargs(model, content, settings),  # type: ignore[arg-type]
                timeout_ms=int(timeout * 1000) if timeout is not None else None,
            )

        # Cap de concurrence (≤ N appels Mistral simultanés) + retry borné sur
        # 429/5xx/transport (Retry-After respecté), dans le délai de l'étape.
        response = call_resilient(
            "mistral", _complete, deadline=deadline, control=control
        )
    except CinocError:
        raise  # délai, annulation : déjà typés
    except Exception as exc:  # le SDK lève des erreurs HTTP/SDK variées
        raise AdapterStepError(
            f"mistral a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    return _completion_from_chat(sdk_native(response, "mistral"))


def _invoke_mistral(
    *,
    model: str,
    prompt: str,
    deadline: Deadline,
    settings: InferenceSettings,
    control: RunControl | None = None,
) -> LLMCompletion:
    return _mistral_client(model, prompt, deadline, settings, control)


def _invoke_mistral_vision(
    *,
    model: str,
    prompt: str,
    media_type: str,
    image_b64: str,
    deadline: Deadline,
    settings: InferenceSettings,
    control: RunControl | None = None,
) -> LLMCompletion:
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": f"data:{media_type};base64,{image_b64}"},
    ]
    return _mistral_client(model, content, deadline, settings, control)


class MistralAdapter:
    """Adapter Mistral multi-mode (post-correction texte/image, transcription VLM)."""

    #: Modes que cet adapter implémente **réellement**. Déclaré ici, à côté du
    #: code qui les rend possibles : la capacité vision est une closure passée à
    #: ``run_llm_step``, invérifiable de l'extérieur. Une liste tenue ailleurs
    #: dérive — c'est arrivé (D-233).
    SUPPORTED_MODES: ClassVar[frozenset[PipelineMode]] = frozenset(
        {"text_only", "text_and_image", "zero_shot", "refine"}
    )
    #: Réglages acceptés : ceux des quatre fournisseurs.
    PARAMS: ClassVar[tuple[Param, ...]] = llm_params(SUPPORTED_MODES)


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
    ) -> None:
        self._label = validate_llm_label(label, "MistralAdapter")
        self._timeout = validate_timeout(timeout, "MistralAdapter")
        self._settings = InferenceSettings.build(
            temperature=temperature, top_p=top_p, seed=seed, max_tokens=max_tokens
        )
        self._model = require_model(model, "MistralAdapter")
        self._role: PipelineMode = validate_role(
            role, "MistralAdapter", self.SUPPORTED_MODES
        )
        self._prompt = (
            prompt if prompt is not None else default_prompt_for_role(self._role)
        )

    @property
    def name(self) -> str:
        return f"mistral:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    def effective_settings(self) -> EffectiveSettings:
        """Réglages **effectifs** (défauts compris) : manifeste et empreinte de
        l'étape. Le SDK mistralai 3.x ne lit aucun endpoint dans
        l'environnement : la cible est celle du SDK, épinglé par
        ``dependencies_lock``."""
        return llm_effective_settings(
            model=self._model,
            role=self._role,
            prompt=self._prompt,
            settings=self._settings,
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
            return _invoke_mistral(
                model=self._model,
                prompt=prompt,
                deadline=deadline,
                settings=self._settings,
                control=control,
            )

        def vision_invoke(
            prompt: str, media_type: str, image_b64: str
        ) -> LLMCompletion:
            return _invoke_mistral_vision(
                model=self._model,
                prompt=prompt,
                media_type=media_type,
                image_b64=image_b64,
                deadline=deadline,
                settings=self._settings,
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


def models_from_listing(body: object) -> tuple[ModelInfo, ...]:
    """Corps de ``GET /v1/models`` (``data[]`` de cartes) → modèles. **Pur.**

    Vision et OCR = ``capabilities.vision``/``ocr`` **déclarés** ; ``aliases``
    gardés (un alias ``…-latest`` est un nom accepté) ; ``deprecation`` (date
    annoncée par Mistral) → ``deprecated_at``. Rien d'autre n'est déduit.
    """
    data = body.get("data") if isinstance(body, dict) else None
    found: dict[str, ModelInfo] = {}
    for card in data if isinstance(data, list) else ():
        name = declared_text(card.get("id")) if isinstance(card, dict) else None
        if name is None:
            continue
        caps = card.get("capabilities")
        caps = caps if isinstance(caps, dict) else {}
        aliases = card.get("aliases")
        found[name] = ModelInfo(
            name=name,
            vision=declared_flag(caps.get("vision")),
            ocr=declared_flag(caps.get("ocr")),
            deprecated_at=declared_text(card.get("deprecation")),
            aliases=tuple(
                sorted(
                    {a for a in aliases if isinstance(a, str) and a and a != name}
                )
            )
            if isinstance(aliases, list)
            else (),
        )
    return tuple(found[name] for name in sorted(found))


def list_models(*, timeout: float = LISTING_TIMEOUT) -> tuple[ModelInfo, ...]:
    """Les modèles que la clé Mistral permet, **demandés en direct**
    (``models.list``) — chat et OCR : un seul compte, une seule liste.

    Le SDK mistralai **enveloppe** ses erreurs HTTP (``MistralError``) et laisse
    passer celles du transport (``httpx2``) : on traduit toute erreur de
    l'appel en ``ModelListingError`` — jamais avalée, toujours nommée.
    """
    import os

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ModelListingError("clé MISTRAL_API_KEY absente")
    try:
        from mistralai.client import Mistral  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ModelListingError("SDK mistralai non installé (extra [mistral])") from exc
    try:
        client = Mistral(
            api_key=api_key, retry_config=None, timeout_ms=int(timeout * 1000)
        )
        body = sdk_native(client.models.list(), "mistral")
    except Exception as exc:  # SDK enveloppant + transport : voir la docstring
        status = getattr(exc, "status_code", None)
        raise ModelListingError(
            f"api.mistral.ai : {type(exc).__name__}"
            + (f" ({status})" if status else "")
        ) from exc
    return models_from_listing(body)


__all__ = ["MistralAdapter", "list_models", "models_from_listing"]
