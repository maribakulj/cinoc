"""``AnthropicAdapter`` — post-correction LLM **et** transcription VLM (Claude).

Implémente le ``Module`` Protocol, trois modes (``PipelineMode``) selon le rôle :
``text_only`` (texte → corrigé), ``text_and_image`` (Claude vision : image +
texte → corrigé), ``zero_shot`` (Claude vision : image → texte). Clé
``ANTHROPIC_API_KEY`` ; SDK ``anthropic`` = **extra** importé paresseusement dans
``_invoke_anthropic`` / ``_invoke_anthropic_vision`` (isolés → **mockables**, CI
sans clé ni réseau). La ``Deadline`` borne l'appel.
"""

from __future__ import annotations

from typing import Any, ClassVar

from cinoc.adapters._resilience import call_resilient
from cinoc.adapters.llm._base import (
    LLMCompletion,
    default_prompt_for_role,
    llm_input_types,
    llm_output_type,
    normalize_llm_content,
    run_llm_step,
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

_VERSION = "1.0"
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 4096


def _completion_from_message(response: Any) -> LLMCompletion:
    """Réponse SDK ``messages.create`` → ``LLMCompletion`` (texte + jetons).

    **Pur** (aucun réseau, aucun SDK) → la cartographie usage→jetons
    (``input_tokens``/``output_tokens``, **noms propres à Claude**) est **testable
    sur cassette** (étape 2d) ; le client live (``# pragma: no cover``) ne le
    permettrait pas. Jetons → économie (coût cloud réel).
    """
    usage = getattr(response, "usage", None)
    return LLMCompletion(
        normalize_llm_content(getattr(response, "content", None)),
        usage_tokens(getattr(usage, "input_tokens", None)),
        usage_tokens(getattr(usage, "output_tokens", None)),
    )


def _anthropic_client(  # pragma: no cover -- réseau + clé API (cf. 'live')
    model: str, content: object, deadline: Deadline
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
                model=model,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": content}],  # type: ignore[typeddict-item]
            )

        # Cap de concurrence (≤ N appels Anthropic simultanés) + retry borné sur
        # 429/5xx (Retry-After respecté) — par défaut, sans configuration UI.
        response = call_resilient("anthropic", _create)
    except AnthropicError as exc:
        raise AdapterStepError(
            f"anthropic a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    return _completion_from_message(response)


def _invoke_anthropic(  # pragma: no cover -- réseau + clé API (cf. marqueur 'live')
    *, model: str, prompt: str, deadline: Deadline
) -> LLMCompletion:
    return _anthropic_client(model, prompt, deadline)


def _invoke_anthropic_vision(  # pragma: no cover -- réseau + clé API (cf. 'live')
    *, model: str, prompt: str, media_type: str, image_b64: str, deadline: Deadline
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
    return _anthropic_client(model, content, deadline)


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
    ) -> None:
        self._label = validate_llm_label(label, "AnthropicAdapter")
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
                model=self._model, prompt=prompt, deadline=context.deadline
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
        )


__all__ = ["AnthropicAdapter"]
