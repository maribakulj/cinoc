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

Cible : l'endpoint d'Anthropic, **transmis explicitement** au client et écrit
dans les réglages effectifs (``base_url``) — manifeste et empreinte de l'étape.
``ANTHROPIC_BASE_URL``, que le SDK lirait en silence faute d'un ``base_url``
explicite, **n'est plus lue** (même règle qu'``OPENAI_BASE_URL`` en S21) : une
variable du processus redirigeait toutes les instances sans que la spec le dise.
Posée, elle vaut un avertissement, et l'appel part à l'endpoint d'Anthropic.

Délai fini (``timeout``, défaut 600 s, retries compris), passé à **chaque**
appel ; client construit avec ``max_retries=0`` (le SDK retentait deux fois
sous chacune des cinq tentatives de Cinoc) : la seule politique de retry est
``call_resilient``.
"""

from __future__ import annotations

import logging
import os
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
    declared_lifecycle,
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

#: 2 : raison d'arrêt lue ; ``max_tokens`` paramétrable (8 192 par défaut, au
#: lieu de 4 096 codés) — une sortie peut changer.
#: 2.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas.
_VERSION = "2.1"
#: L'endpoint d'Anthropic — celui de la table de tarifs (``pricing.json``).
_DEFAULT_BASE_URL = "https://api.anthropic.com"
#: Variable que le SDK lit quand on ne lui passe pas d'endpoint ; plus lue.
_RETIRED_BASE_URL_ENV = "ANTHROPIC_BASE_URL"

logger = logging.getLogger(__name__)

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


def _completion_from_message(response: object) -> LLMCompletion:
    """Corps de ``messages.create`` → ``LLMCompletion`` (texte, jetons, arrêt).

    **Pur** (aucun réseau, aucun SDK) et lu sur le **corps** de la réponse — le
    dict que ``sdk_native`` tire du ``Message`` du SDK, gardé en sidecar
    ``NATIVE_JSON`` : relire le sidecar rend la même complétion. Usage→jetons
    (``input_tokens``/``output_tokens``, **noms propres à Claude**) et
    ``stop_reason`` se testent sur cassette. Jetons → économie.

    ``input_tokens`` ne compte que l'entrée **hors cache** : les lectures
    (``cache_read_input_tokens``) et écritures (``cache_creation_input_tokens``)
    s'y **ajoutent** (doc « Prompt caching » d'Anthropic) — ``tokens_in`` en
    est la somme, pour dire la même chose que chez OpenAI.
    ``output_tokens_details.thinking_tokens`` (SDK anthropic 2.14) est une
    partie d'``output_tokens``, « total inclusif qui fait foi pour la
    facturation ». Absents → ``None``.
    """
    usage = wire_field(response, "usage")
    uncached = usage_tokens(wire_field(usage, "input_tokens"))
    read = usage_tokens(wire_field(usage, "cache_read_input_tokens"))
    write = usage_tokens(wire_field(usage, "cache_creation_input_tokens"))
    tokens_in = (
        None if uncached is None else uncached + (read or 0) + (write or 0)
    )
    return LLMCompletion(
        normalize_llm_content(wire_field(response, "content")),
        tokens_in,
        usage_tokens(wire_field(usage, "output_tokens")),
        stop_reason_from(wire_field(response, "stop_reason"), _STOP_REASONS),
        native=response,
        model=served_model(response),
        tokens_cache_read=read,
        tokens_cache_write=write,
        tokens_reasoning=usage_tokens(
            wire_field(wire_field(usage, "output_tokens_details"), "thinking_tokens")
        ),
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


def _anthropic_client(
    model: str,
    content: object,
    deadline: Deadline,
    settings: InferenceSettings,
    base_url: str = _DEFAULT_BASE_URL,
    control: RunControl | None = None,
) -> LLMCompletion:
    """Appel ``messages.create`` partagé (texte ou multimodal)."""
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
    try:
        # SDK anthropic typé strictement ; dicts valides à l'exécution (tests live).
        # ``max_retries=0`` : une seule politique de retry, celle de Cinoc.
        client = Anthropic(api_key=api_key, base_url=base_url, max_retries=0)
        if control is not None:
            register_close(control, client)

        def _create() -> Any:
            return client.messages.create(  # type: ignore[call-overload]
                **_request_kwargs(model, content, settings),  # type: ignore[arg-type]
                timeout=request_timeout(deadline),
            )

        # Cap de concurrence (≤ N appels Anthropic simultanés) + retry borné sur
        # 429/5xx/transport (Retry-After respecté), dans le délai de l'étape.
        response = call_resilient(
            "anthropic", _create, deadline=deadline, control=control
        )
    except CinocError:
        raise  # délai, annulation : déjà typés
    except (AnthropicError, ValueError) as exc:
        # ``ValueError`` : le SDK refuse **avant** l'envoi une requête sans flux
        # dont ``max_tokens`` laisse prévoir plus de 10 minutes (~21 000 jetons,
        # moins pour certains modèles) — une erreur de réglage, pas un bug.
        raise AdapterStepError(
            f"anthropic a échoué ({model}) : {type(exc).__name__}: {exc}"
        ) from exc
    return _completion_from_message(sdk_native(response, "anthropic"))


def _invoke_anthropic(
    *,
    model: str,
    prompt: str,
    deadline: Deadline,
    settings: InferenceSettings,
    base_url: str = _DEFAULT_BASE_URL,
    control: RunControl | None = None,
) -> LLMCompletion:
    return _anthropic_client(model, prompt, deadline, settings, base_url, control)


def _invoke_anthropic_vision(
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
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_b64,
            },
        },
    ]
    return _anthropic_client(model, content, deadline, settings, base_url, control)


#: Taille de page maximale de ``GET /v1/models`` (documentée : 1 à 1 000).
_LIST_PAGE = 1000


def model_from_info(item: object) -> ModelInfo | None:
    """Un élément de ``GET /v1/models`` (``ModelInfo`` de l'API) → modèle. **Pur.**

    Vision = ``capabilities.image_input.supported`` ; cycle de vie =
    ``lifecycle`` (``active``/``deprecated``/``retired``), ``deprecated_at``,
    ``retires_at`` — chacun lu **s'il est donné**, inconnu sinon.
    """
    if not isinstance(item, dict):
        return None
    name = declared_text(item.get("id"))
    if name is None:
        return None
    capabilities = item.get("capabilities")
    image = capabilities.get("image_input") if isinstance(capabilities, dict) else None
    supported = image.get("supported") if isinstance(image, dict) else None
    return ModelInfo(
        name=name,
        vision=declared_flag(supported),
        lifecycle=declared_lifecycle(item.get("lifecycle")),
        deprecated_at=declared_text(item.get("deprecated_at")),
        retires_at=declared_text(item.get("retires_at")),
    )


def models_from_listing(
    items: object, aliases: dict[str, str] | None = None
) -> tuple[ModelInfo, ...]:
    """Éléments listés (toutes pages) → modèles triés par nom. **Pur.**

    ``aliases`` : ``{alias: identifiant}`` résolus par ``GET /v1/models/{alias}``
    — la liste ne nomme que les identifiants, l'API accepte aussi leurs alias.
    """
    found: dict[str, ModelInfo] = {}
    for item in items if isinstance(items, list) else ():
        model = model_from_info(item)
        if model is not None:
            found[model.name] = model
    for alias, name in sorted((aliases or {}).items()):
        if name in found and alias != name:
            known = found[name]
            found[name] = known.model_copy(
                update={"aliases": tuple(sorted({*known.aliases, alias}))}
            )
    return tuple(found[name] for name in sorted(found))


def list_models(
    *, wanted: str | None = None, timeout: float = LISTING_TIMEOUT
) -> tuple[ModelInfo, ...]:
    """Les modèles que la clé permet, **demandés en direct** (``models.list``,
    toutes pages), à l'endpoint d'Anthropic.

    ``wanted`` absent de la liste est **résolu** (``models.retrieve`` accepte un
    identifiant ou un alias) : un alias valide apparaît alors dans les
    ``aliases`` de son modèle, au lieu d'être déclaré absent.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ModelListingError("clé ANTHROPIC_API_KEY absente")
    try:
        from anthropic import (  # type: ignore[import-not-found]
            Anthropic,
            AnthropicError,
            NotFoundError,
        )
    except ImportError as exc:
        raise ModelListingError(
            "SDK anthropic non installé (extra [anthropic])"
        ) from exc
    try:
        client = Anthropic(
            api_key=api_key,
            base_url=_DEFAULT_BASE_URL,
            max_retries=0,
            timeout=timeout,
        )
        items = [
            sdk_native(model, "anthropic")
            for model in client.models.list(limit=_LIST_PAGE)
        ]
        aliases: dict[str, str] = {}
        names = {item.get("id") for item in items}
        if wanted and wanted not in names:
            try:
                resolved = sdk_native(client.models.retrieve(wanted), "anthropic")
            except NotFoundError:
                resolved = {}
            if isinstance(resolved.get("id"), str):
                aliases[wanted] = resolved["id"]
    except AnthropicError as exc:
        status = getattr(exc, "status_code", None)
        raise ModelListingError(
            f"{_DEFAULT_BASE_URL} : {type(exc).__name__}"
            + (f" ({status})" if status else "")
        ) from exc
    return models_from_listing(items, aliases)


class AnthropicAdapter:
    """Adapter Anthropic multi-mode (post-correction texte/image, transcription)."""

    #: Modes que cet adapter implémente **réellement**. Déclaré ici, à côté du
    #: code qui les rend possibles : la capacité vision est une closure passée à
    #: ``run_llm_step``, invérifiable de l'extérieur. Une liste tenue ailleurs
    #: dérive — c'est arrivé (D-233).
    SUPPORTED_MODES: ClassVar[frozenset[PipelineMode]] = frozenset(
        {"text_only", "text_and_image", "zero_shot", "refine"}
    )
    #: Réglages acceptés : ceux des quatre fournisseurs **sans** l'échantillonnage
    #: — l'API refuse ``temperature``/``top_p`` et n'a pas de ``seed`` : non
    #: déclarés, ils sont refusés par nom à la planification, avant tout appel.
    PARAMS: ClassVar[tuple[Param, ...]] = llm_params(SUPPORTED_MODES, sampling=False)


    def __init__(
        self,
        *,
        label: str,
        model: str,
        role: str = "text_only",
        prompt: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        seed: int | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: object = DEFAULT_LLM_TIMEOUT,
    ) -> None:
        self._label = validate_llm_label(label, "AnthropicAdapter")
        self._timeout = validate_timeout(timeout, "AnthropicAdapter")
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
        self._model = require_model(model, "AnthropicAdapter")
        self._role: PipelineMode = validate_role(
            role, "AnthropicAdapter", self.SUPPORTED_MODES
        )
        self._prompt = (
            prompt if prompt is not None else default_prompt_for_role(self._role)
        )
        if os.environ.get(_RETIRED_BASE_URL_ENV, "").strip():
            logger.warning(
                "[anthropic] %s n'est plus lue : la cible n'est pas un réglage "
                "du processus — appel à %s.",
                _RETIRED_BASE_URL_ENV,
                _DEFAULT_BASE_URL,
            )
        self._base_url = _DEFAULT_BASE_URL

    @property
    def name(self) -> str:
        return f"anthropic:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    def effective_settings(self) -> EffectiveSettings:
        """Réglages **effectifs** (``None`` = non transmis, endpoint compris) :
        manifeste et empreinte de l'étape."""
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
            return _invoke_anthropic(
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
            return _invoke_anthropic_vision(
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


__all__ = [
    "AnthropicAdapter",
    "list_models",
    "model_from_info",
    "models_from_listing",
]
