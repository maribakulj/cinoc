"""``OpenAIAdapter`` — post-correction LLM **et** transcription VLM (API OpenAI).

Implémente le ``Module`` Protocol. Trois modes (``PipelineMode``) selon le rôle
passé à la construction : ``text_only`` (``RAW_TEXT`` → ``CORRECTED_TEXT``),
``text_and_image`` (image + texte → corrigé), ``zero_shot`` (image → texte). La
clé vient de ``OPENAI_API_KEY`` ; le SDK ``openai`` est un **extra** importé
paresseusement dans ``_invoke_openai`` / ``_invoke_openai_vision`` (isolés →
**mockables**, CI sans clé ni réseau). La ``Deadline`` borne l'appel.
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
_DEFAULT_MODEL = "gpt-4o-mini"


def _completion_from_chat(response: Any) -> LLMCompletion:
    """Réponse SDK ``chat.completions`` → ``LLMCompletion`` (texte + jetons).

    **Pur** (aucun réseau, aucun import SDK) → la cartographie usage→jetons
    (``prompt_tokens``/``completion_tokens``) est **testable sur une réponse de
    cassette**, ce que le client live (``# pragma: no cover``) ne permet pas. Les
    jetons alimentent l'économie (coût réel par modèle).
    """
    usage = getattr(response, "usage", None)
    tokens_in = usage_tokens(getattr(usage, "prompt_tokens", None))
    tokens_out = usage_tokens(getattr(usage, "completion_tokens", None))
    choices = getattr(response, "choices", None)
    if not choices:
        return LLMCompletion("", tokens_in, tokens_out)
    return LLMCompletion(
        normalize_llm_content(choices[0].message.content), tokens_in, tokens_out
    )


def _openai_client(  # pragma: no cover -- réseau + clé API (cf. marqueur 'live')
    model: str, messages: list[dict[str, object]], deadline: Deadline
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
    kwargs: dict[str, object] = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
    }
    timeout = deadline.as_sdk_timeout()
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        # SDK openai typé strictement ; kwargs valides à l'exécution (tests live).
        client = OpenAI(api_key=api_key)

        def _create() -> Any:
            return client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

        # Cap de concurrence (≤ N appels OpenAI simultanés) + retry borné sur
        # 429/5xx (Retry-After respecté) — par défaut, sans configuration UI.
        response = call_resilient("openai", _create)
    except OpenAIError as exc:
        raise AdapterStepError(
            f"openai a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    return _completion_from_chat(response)


def _invoke_openai(  # pragma: no cover -- réseau + clé API (cf. marqueur 'live')
    *, model: str, prompt: str, deadline: Deadline
) -> LLMCompletion:
    return _openai_client(model, [{"role": "user", "content": prompt}], deadline)


def _invoke_openai_vision(  # pragma: no cover -- réseau + clé API (cf. marqueur 'live')
    *, model: str, prompt: str, media_type: str, image_b64: str, deadline: Deadline
) -> LLMCompletion:
    content = [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
        },
    ]
    return _openai_client(model, [{"role": "user", "content": content}], deadline)


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
    ) -> None:
        self._label = validate_llm_label(label, "OpenAIAdapter")
        self._model = model
        self._role: PipelineMode = validate_role(
            role, "OpenAIAdapter", self.SUPPORTED_MODES
        )
        self._prompt = (
            prompt if prompt is not None else default_prompt_for_role(self._role)
        )

    @property
    def name(self) -> str:
        return f"openai:{self._label}"

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
            return _invoke_openai(
                model=self._model, prompt=prompt, deadline=context.deadline
            )

        def vision_invoke(
            prompt: str, media_type: str, image_b64: str
        ) -> LLMCompletion:
            return _invoke_openai_vision(
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


__all__ = ["OpenAIAdapter"]
