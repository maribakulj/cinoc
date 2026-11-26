"""``AnthropicAdapter`` — post-correction LLM **et** transcription VLM (Claude).

Implémente le ``Module`` Protocol, trois modes (``PipelineMode``) selon le rôle :
``text_only`` (texte → corrigé), ``text_and_image`` (Claude vision : image +
texte → corrigé), ``zero_shot`` (Claude vision : image → texte). Clé
``ANTHROPIC_API_KEY`` ; SDK ``anthropic`` = **extra** importé paresseusement dans
``_invoke_anthropic`` / ``_invoke_anthropic_vision`` (isolés → **mockables**, CI
sans clé ni réseau). La ``Deadline`` borne l'appel.

Réglages : seul ``max_tokens`` est transmis. L'API Anthropic refuse
``temperature``, ``top_p`` et ``top_k`` sur tous les modèles depuis la version
d'API 2026-10-21 (400), et le SDK 2.x ne les expose plus ; elle n'a jamais eu de
``seed``. Le constructeur accepte donc les mêmes réglages que les trois autres
fournisseurs — une spec peut les nommer d'un même geste — mais **refuse** une
valeur pour ceux-là au lieu de l'ignorer, et le manifeste écrit ``None`` (non
transmis) : le banc ne prétend pas avoir fixé ce qu'il ne pouvait pas fixer.
"""

from __future__ import annotations

from typing import Any, ClassVar

from cinoc.adapters._resilience import call_resilient
from cinoc.adapters.llm._base import (
    DEFAULT_MAX_TOKENS,
    InferenceSettings,
    LLMCompletion,
    StopReason,
    default_prompt_for_role,
    llm_input_types,
    llm_output_type,
    normalize_llm_content,
    run_llm_step,
    stop_reason_from,
    usage_tokens,
    validate_llm_label,
    validate_role,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.pipeline import PipelineMode
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

#: 2 : raison d'arrêt lue ; ``max_tokens`` paramétrable (8 192 par défaut, au
#: lieu de 4 096 codés) — une sortie peut changer.
_VERSION = "2.0"
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

#: ``stop_reason`` (SDK anthropic 2.14 : ``end_turn``, ``max_tokens``,
#: ``stop_sequence``, ``tool_use``, ``pause_turn``, ``refusal``,
#: ``model_context_window_exceeded``) → raison normalisée. ``tool_use`` et
#: ``pause_turn`` n'ont pas de sens sans outil : ``unknown``.
_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "refusal": "refusal",
}


def _completion_from_message(response: Any) -> LLMCompletion:
    """Réponse SDK ``messages.create`` → ``LLMCompletion`` (texte, jetons, arrêt).

    **Pur** (aucun réseau, aucun SDK) → la cartographie usage→jetons
    (``input_tokens``/``output_tokens``, **noms propres à Claude**) et
    ``stop_reason`` est **testable sur cassette** ; le client live
    (``# pragma: no cover``) ne le permettrait pas. Jetons → économie.
    """
    usage = getattr(response, "usage", None)
    return LLMCompletion(
        normalize_llm_content(getattr(response, "content", None)),
        usage_tokens(getattr(usage, "input_tokens", None)),
        usage_tokens(getattr(usage, "output_tokens", None)),
        stop_reason_from(getattr(response, "stop_reason", None), _STOP_REASONS),
    )


def _request_kwargs(
    model: str, content: object, settings: InferenceSettings
) -> dict[str, object]:
    """Arguments de ``messages.create`` — **pur**, testé sans SDK."""
    return {
        "model": model,
        "max_tokens": settings.max_tokens,
        "messages": [{"role": "user", "content": content}],
    }


def _anthropic_client(  # pragma: no cover -- réseau + clé API (cf. 'live')
    model: str, content: object, deadline: Deadline, settings: InferenceSettings
) -> LLMCompletion:
    """Appel ``messages.create`` partagé (texte ou multimodal)."""
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise AdapterStepError("anthropic : ANTHROPIC_API_KEY manquante.")
    try:
        from anthropic import (  # type: ignore[import-not-found]
            Anthropic,
            AnthropicError,
        )
    except ImportError as exc:
        raise AdapterStepError(
            "anthropic : SDK non installé (pip install 'cinoc[anthropic]')."
        ) from exc
    client_kwargs: dict[str, object] = {"api_key": api_key}
    timeout = deadline.as_sdk_timeout()
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    try:
        # SDK anthropic typé strictement ; dicts valides à l'exécution (tests live).
        client = Anthropic(**client_kwargs)  # type: ignore[arg-type]

        def _create() -> Any:
            return client.messages.create(
                **_request_kwargs(model, content, settings)  # type: ignore[arg-type]
            )

        # Cap de concurrence (≤ N appels Anthropic simultanés) + retry borné sur
        # 429/5xx (Retry-After respecté) — par défaut, sans configuration UI.
        response = call_resilient("anthropic", _create)
    except (AnthropicError, ValueError) as exc:
        # ``ValueError`` : le SDK refuse **avant** l'envoi une requête sans flux
        # dont ``max_tokens`` laisse prévoir plus de 10 minutes (~21 000 jetons,
        # moins pour certains modèles) — une erreur de réglage, pas un bug.
        raise AdapterStepError(
            f"anthropic a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    return _completion_from_message(response)


def _invoke_anthropic(  # pragma: no cover -- réseau + clé API (cf. marqueur 'live')
    *, model: str, prompt: str, deadline: Deadline, settings: InferenceSettings
) -> LLMCompletion:
    return _anthropic_client(model, prompt, deadline, settings)


def _invoke_anthropic_vision(  # pragma: no cover -- réseau + clé API (cf. 'live')
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
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_b64,
            },
        },
    ]
    return _anthropic_client(model, content, deadline, settings)


class AnthropicAdapter:
    """Adapter Anthropic multi-mode (post-correction texte/image, transcription)."""

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
        temperature: float | None = None,
        top_p: float | None = None,
        seed: int | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._label = validate_llm_label(label, "AnthropicAdapter")
        # Réglages que l'API refuse (voir la docstring du module).
        refuses = {"temperature": temperature, "top_p": top_p, "seed": seed}
        for key, value in refuses.items():
            if value is not None:
                raise AdapterStepError(
                    f"AnthropicAdapter : {key!r} n'est pas transmissible — l'API "
                    "Anthropic refuse temperature/top_p depuis la version "
                    "2026-10-21 et n'a pas de seed. Retirez-le de la spec."
                )
        self._settings = InferenceSettings.build(
            temperature=None, top_p=None, seed=None, max_tokens=max_tokens
        )
        self._model = model
        self._role: PipelineMode = validate_role(
            role, "AnthropicAdapter", self.SUPPORTED_MODES
        )
        self._prompt = (
            prompt if prompt is not None else default_prompt_for_role(self._role)
        )

    @property
    def name(self) -> str:
        return f"anthropic:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    def inference_settings(self) -> dict[str, float | int | None]:
        """Réglages **effectifs** (``None`` = non transmis), recopiés au manifeste."""
        return self._settings.as_manifest()

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return llm_input_types(self._role)

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({llm_output_type(self._role)})

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        def text_invoke(prompt: str) -> LLMCompletion:
            return _invoke_anthropic(
                model=self._model,
                prompt=prompt,
                deadline=context.deadline,
                settings=self._settings,
            )

        def vision_invoke(
            prompt: str, media_type: str, image_b64: str
        ) -> LLMCompletion:
            return _invoke_anthropic_vision(
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


__all__ = ["AnthropicAdapter"]
