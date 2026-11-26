"""``MistralAdapter`` — post-correction LLM **et** transcription VLM (API Mistral).

Implémente le ``Module`` Protocol, trois modes (``PipelineMode``) selon le rôle :
``text_only`` (texte → corrigé), ``text_and_image`` (Pixtral : image + texte →
corrigé), ``zero_shot`` (Pixtral : image → texte). Clé ``MISTRAL_API_KEY`` ; SDK
``mistralai`` = **extra** importé paresseusement dans ``_invoke_mistral`` /
``_invoke_mistral_vision`` (isolés → **mockables**, CI sans clé ni réseau).

Réglages (``InferenceSettings``) : ``temperature``, ``top_p``, ``max_tokens`` et
``seed`` — ce dernier sous le nom de l'API Mistral, ``random_seed``.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from cinoc.adapters._native import sdk_native, served_model
from cinoc.adapters._resilience import call_resilient
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
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.pipeline import PipelineMode
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

#: 2 : raison d'arrêt lue, réglages d'inférence transmis (``top_p``,
#: ``random_seed``, ``max_tokens``) — une sortie peut changer.
#: 2.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas.
_VERSION = "2.1"
_DEFAULT_MODEL = "mistral-small-latest"

#: ``finish_reason`` (SDK mistralai 1.12 : ``stop``, ``length``,
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
    model: str, content: object, deadline: Deadline, settings: InferenceSettings
) -> LLMCompletion:
    """Appel ``chat.complete`` partagé (texte ou multimodal)."""
    import os

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise AdapterStepError("mistral : MISTRAL_API_KEY manquante.")
    try:
        from mistralai import Mistral  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AdapterStepError(
            "mistral : SDK non installé (pip install 'cinoc[mistral]')."
        ) from exc
    client_kwargs: dict[str, object] = {"api_key": api_key}
    timeout = deadline.as_sdk_timeout()
    if timeout is not None:
        client_kwargs["timeout_ms"] = int(timeout * 1000)
    try:
        # Le SDK mistralai 1.x type strictement ses kwargs/messages ; on lui
        # passe des dicts valides à l'exécution (cf. tests live). ``ignore`` ciblé.
        client = Mistral(**client_kwargs)  # type: ignore[arg-type]

        def _complete() -> Any:
            return client.chat.complete(
                **_request_kwargs(model, content, settings)  # type: ignore[arg-type]
            )

        # Cap de concurrence (≤ N appels Mistral simultanés) + retry borné sur
        # 429/5xx (Retry-After respecté) — par défaut, sans configuration UI.
        response = call_resilient("mistral", _complete)
    except Exception as exc:  # le SDK lève des erreurs HTTP/SDK variées
        raise AdapterStepError(
            f"mistral a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    return _completion_from_chat(sdk_native(response, "mistral"))


def _invoke_mistral(
    *, model: str, prompt: str, deadline: Deadline, settings: InferenceSettings
) -> LLMCompletion:
    return _mistral_client(model, prompt, deadline, settings)


def _invoke_mistral_vision(
    *,
    model: str,
    prompt: str,
    media_type: str,
    image_b64: str,
    deadline: Deadline,
    settings: InferenceSettings,
) -> LLMCompletion:
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": f"data:{media_type};base64,{image_b64}"},
    ]
    return _mistral_client(model, content, deadline, settings)


class MistralAdapter:
    """Adapter Mistral multi-mode (post-correction texte/image, transcription VLM)."""

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
    ) -> None:
        self._label = validate_llm_label(label, "MistralAdapter")
        self._settings = InferenceSettings.build(
            temperature=temperature, top_p=top_p, seed=seed, max_tokens=max_tokens
        )
        self._model = model
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
        l'étape. Le SDK mistralai 1.x ne lit aucun endpoint dans
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
        def text_invoke(prompt: str) -> LLMCompletion:
            return _invoke_mistral(
                model=self._model,
                prompt=prompt,
                deadline=context.deadline,
                settings=self._settings,
            )

        def vision_invoke(
            prompt: str, media_type: str, image_b64: str
        ) -> LLMCompletion:
            return _invoke_mistral_vision(
                model=self._model,
                prompt=prompt,
                media_type=media_type,
                image_b64=image_b64,
                deadline=context.deadline,
                settings=self._settings,
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


def list_mistral_models(*, timeout: float = 5.0) -> tuple[str, ...]:
    """IDs des modèles disponibles pour la clé Mistral courante (``models.list``).

    **Best-effort, commodité d'UI** : ``MISTRAL_API_KEY`` absente, SDK absent ou
    erreur réseau → ``()`` (l'interface retombe sur la saisie libre). Rien de
    hardcodé : la liste vient **directement de l'API Mistral**.
    """
    import os

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        return ()
    try:
        from mistralai import Mistral  # type: ignore[import-not-found]
    except ImportError:
        return ()
    try:
        client = Mistral(api_key=api_key, timeout_ms=int(timeout * 1000))
        response = client.models.list()
    except Exception as exc:  # noqa: BLE001 — voir rationale ci-dessous
        # Catch-all **assumé** : commodité d'UI qui ne doit jamais casser la
        # page du composeur. Le SDK mistralai **enveloppe** ses erreurs HTTP
        # (auth/429/5xx) dans ses propres types + propage des erreurs httpx pour
        # le transport ; narrower au seul ``httpx.HTTPError`` (comme ollama, qui
        # appelle httpx en direct) laisserait fuir une erreur SDK et casserait la
        # page. On trace (§7) et on retombe sur la saisie libre.
        logger.warning("[mistral] liste des modèles indisponible : %s", exc)
        return ()
    data = getattr(response, "data", None) or ()
    ids = [m.id for m in data if isinstance(getattr(m, "id", None), str)]
    return tuple(sorted(set(ids)))


__all__ = ["MistralAdapter", "list_mistral_models"]
