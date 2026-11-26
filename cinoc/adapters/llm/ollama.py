"""``OllamaAdapter`` — post-correction LLM via un serveur ollama local.

Deuxième famille LLM : prouve que le ``Module`` Protocol **généralise au-delà
d'openai** — même contrat ``RAW_TEXT`` → ``CORRECTED_TEXT``, sortie identique,
aucun cas particulier. Transport ``httpx`` (extra), importé paresseusement et
**isolé** dans ``_invoke_ollama`` (→ mockable, CI sans serveur).

C'est l'**implémentation de référence de l'annulation câblée** : ``_invoke_ollama``
enregistre ``client.close`` via ``RunControl.register_cancel_handle`` ; un
``trigger_cancel`` ferme la connexion et **interrompt la requête en vol**. La
distinction « annulation vs vraie panne réseau » se fait en sondant
``is_cancelled`` (``_fail_or_cancel``) — pas par une heuristique de message
fragile (dette de l'implémentation source, corrigée au portage).

Réglages (``InferenceSettings``) passés dans ``options`` : ``temperature``,
``top_p``, ``seed``, ``max_tokens`` → ``num_predict``, et ``num_ctx`` **explicite**.
Sans lui, c'est le défaut du serveur (2 048 ou 4 096 jetons selon la version)
qui borne l'**entrée** : une page et son image dépassent, et ollama tronque le
prompt **en silence** — le modèle répond alors à une page qu'il n'a vue qu'en
partie. ``done_reason`` (``stop`` · ``length``) est lu : une sortie coupée par
``num_predict`` se voit. Une entrée rognée par ``num_ctx``, elle, ne laisse
aucune raison d'arrêt : seul un ``num_ctx`` suffisant la prévient.

Délai fini (``timeout``, défaut 600 s) : l'appel tournait **sans aucun délai**
(``httpx.Client(timeout=None)`` sous une deadline infinie). Un délai dépassé est
``DeadlineExceeded`` (motif « arrêtée (délai) »), pas une panne du moteur. Pas
de retry : un serveur local qui répond une erreur ne la répare pas en 30 s, et
il n'y a pas de quota à ménager.

Créneau réseau **du serveur** (``endpoint_slot_key`` : ``hôte:port``) : l'appel
passe par ``call_resilient`` sans retry, sous le créneau du ``host`` — le même
qu'une instance ``openai`` pointée sur ce serveur (``…:11434/v1``). Deux
adaptateurs qui frappent le même processus Ollama se partagent donc son quota
au lieu de le doubler.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, NoReturn

from cinoc.adapters._native import public_endpoint, served_model
from cinoc.adapters._resilience import (
    DEFAULT_LLM_TIMEOUT,
    call_resilient,
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
)
from cinoc.adapters.llm._listing import (
    ModelInfo,
    ModelListingError,
    declared_text,
    require_model,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError, DeadlineExceeded
from cinoc.domain.pipeline import PipelineMode
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

#: 2 : ``options`` explicites (``temperature``, ``seed``, ``num_predict``,
#: ``num_ctx``) et ``done_reason`` lu — une sortie peut changer.
#: 2.1 : la réponse native est publiée en sidecar (``NATIVE_JSON``) ; le texte
#: ne change pas.
_VERSION = "2.1"

_DEFAULT_HOST = "http://localhost:11434"
#: Fenêtre de contexte demandée au serveur : la sortie (``max_tokens`` = 8 192)
#: plus autant pour l'entrée — prompt, texte OCR et jetons d'image d'une page.
DEFAULT_NUM_CTX = 16384

#: ``done_reason`` (``stop``, ``length``, ``load``, ``unload``) → raison
#: normalisée. ``load``/``unload`` ne concernent pas une génération : ``unknown``.
_STOP_REASONS: dict[str, StopReason] = {"stop": "stop", "length": "length"}


def _options(settings: InferenceSettings, num_ctx: int) -> dict[str, float | int]:
    """``options`` de ``/api/chat`` — **pur** ; un réglage ``None`` n'est pas envoyé."""
    options: dict[str, float | int] = {}
    if settings.temperature is not None:
        options["temperature"] = settings.temperature
    if settings.top_p is not None:
        options["top_p"] = settings.top_p
    if settings.seed is not None:
        options["seed"] = settings.seed
    options["num_predict"] = settings.max_tokens
    options["num_ctx"] = num_ctx
    return options


def _completion_from_chat(data: object, model: str) -> LLMCompletion:
    """Corps de ``/api/chat`` → ``LLMCompletion`` (texte, jetons, arrêt) — **pur**.

    Le corps est gardé tel quel en sidecar ``NATIVE_JSON`` (``native``) : le
    relire rend la même complétion. Un serveur ollama n'a pas de clé ; l'hôte,
    qui pourrait en porter une dans son URL, n'est pas dans le corps.

    Ollama peut renvoyer une **erreur en HTTP 200** (modèle introuvable sous ce
    nom, mémoire insuffisante…) : ``raise_for_status`` ne la voit pas. On la
    remonte explicitement, sinon la « correction » serait un texte vide silencieux.
    """
    if isinstance(data, dict) and data.get("error"):
        raise AdapterStepError(f"ollama a échoué ({model}) : {data['error']}")
    counts = data if isinstance(data, dict) else {}
    message = counts.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    # /api/chat expose la consommation : prompt_eval_count / eval_count.
    return LLMCompletion(
        normalize_llm_content(content),
        usage_tokens(counts.get("prompt_eval_count")),
        usage_tokens(counts.get("eval_count")),
        stop_reason_from(counts.get("done_reason"), _STOP_REASONS),
        native=data,
        model=served_model(data),
    )


def _fail_or_cancel(
    control: RunControl,
    model: str,
    exc: Exception,
    deadline: Deadline | None = None,
) -> NoReturn:
    """Traduit un échec d'appel ollama.

    Si l'annulation a été déclenchée, le ``client.close`` enregistré a fait
    échouer la requête en vol : on lève alors ``RunCancelledError`` (via
    ``raise_if_cancelled``). Si la deadline de l'étape est écoulée, le délai
    passé au client s'est déclenché → ``DeadlineExceeded``. Sinon c'est une
    vraie panne → ``AdapterStepError``. Sonder ``is_cancelled`` est **fiable**,
    là où l'implémentation source devinait par le message d'exception
    (heuristique fragile, D-A).
    """
    control.raise_if_cancelled()
    if deadline is not None and deadline.is_expired():
        raise DeadlineExceeded(
            f"ollama ({model}) : délai dépassé ({type(exc).__name__})."
        ) from exc
    raise AdapterStepError(f"ollama a échoué ({model}) : {exc}") from exc


def _invoke_ollama(
    *,
    model: str,
    prompt: str,
    host: str,
    deadline: Deadline,
    control: RunControl,
    options: dict[str, float | int],
    image_b64: str | None = None,
) -> LLMCompletion:
    import httpx
    # L'image voyage dans un tableau ``images`` **du message**, en base64 nu —
    # pas d'URI ``data:``, pas de type de média : ollama ne suit pas la
    # convention d'OpenAI ici, et un ``data:`` passé tel quel est ignoré en
    # silence (le modèle répond alors sans avoir rien vu).
    demande: dict[str, object] = {"role": "user", "content": prompt}
    if image_b64 is not None:
        demande["images"] = [image_b64]
    payload = {
        "model": model,
        "messages": [demande],
        "stream": False,
        "options": options,
    }
    client = httpx.Client(timeout=request_timeout(deadline))
    # Annulation câblée : fermer le client interrompt la requête en vol.
    control.register_cancel_handle(client.close)

    def _post() -> Any:
        # **/api/chat** (et non /api/generate) : applique le gabarit de chat du
        # modèle. Indispensable pour les modèles *instruct*, qui échouent sur
        # /api/generate (complétion brute). C'est l'endpoint qu'utilise
        # ``ollama run``.
        response = client.post(f"{host}/api/chat", json=payload)
        response.raise_for_status()
        return response.json()

    try:
        # Sous le créneau du serveur, **sans retry** (voir le module).
        data = call_resilient(
            "ollama",
            _post,
            deadline=deadline,
            endpoint=host,
            control=control,
            is_retryable=_never_retry,
        )
    except httpx.HTTPError as exc:
        _fail_or_cancel(control, model, exc, deadline)
    finally:
        client.close()
    return _completion_from_chat(data, model)


def _never_retry(exc: BaseException) -> bool:
    """Un serveur local qui répond une erreur ne la répare pas en 30 s."""
    del exc
    return False


def same_model(asked: str, listed: str) -> bool:
    """``asked`` désigne-t-il ``listed`` ? Ollama lit un nom sans tag comme
    ``:latest`` (``llama`` = ``llama:latest``) ; rien d'autre n'est rapproché."""
    return asked == listed or (":" not in asked and listed == f"{asked}:latest")


def model_from_tag(item: object, show: object = None) -> ModelInfo | None:
    """Un élément de ``GET /api/tags`` (+ ``POST /api/show`` éventuel) → modèle.
    **Pur.**

    ``digest`` = l'empreinte des poids : c'est **elle** qui identifie le modèle
    (un tag se réaffecte par ``ollama pull``). Vision = ``"vision"`` parmi les
    ``capabilities`` déclarées — par ``/api/tags`` (versions récentes), sinon
    par ``/api/show`` ; ni l'un ni l'autre → inconnue.
    """
    if not isinstance(item, dict):
        return None
    name = declared_text(item.get("name"))
    if name is None:
        return None
    caps = item.get("capabilities")
    if not isinstance(caps, list) and isinstance(show, dict):
        caps = show.get("capabilities")
    return ModelInfo(
        name=name,
        vision=("vision" in caps) if isinstance(caps, list) else None,
        digest=declared_text(item.get("digest")),
    )


def list_models(
    host: str = _DEFAULT_HOST,
    *,
    timeout: float = 3.0,
    capabilities: bool = True,
) -> tuple[ModelInfo, ...]:
    """Les modèles **installés** sur le serveur Ollama (``GET /api/tags``),
    avec leur digest ; capacités par ``/api/show`` quand ``/api/tags`` ne les
    donne pas (``capabilities=False`` : le digest seul, un appel). Serveur
    injoignable ou réponse illisible → ``ModelListingError``. Le nom est le
    **tag exact** servable à ``/api/chat``.
    """
    import httpx

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{host}/api/tags")
            response.raise_for_status()
            data = response.json()
            items = data.get("models") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise ModelListingError(f"{public_endpoint(host)} : réponse illisible")
            found: list[ModelInfo] = []
            for item in items:
                show = None
                if (
                    capabilities
                    and isinstance(item, dict)
                    and not isinstance(item.get("capabilities"), list)
                ):
                    reply = client.post(
                        f"{host}/api/show", json={"model": item.get("name")}
                    )
                    show = reply.json() if reply.is_success else None
                model = model_from_tag(item, show)
                if model is not None:
                    found.append(model)
    except (httpx.HTTPError, ValueError) as exc:
        raise ModelListingError(
            f"serveur ollama injoignable ({public_endpoint(host)}) : "
            f"{type(exc).__name__}"
        ) from exc
    return tuple(sorted(found, key=lambda m: m.name))


class OllamaAdapter:
    """LLM/VLM local (ollama), trois modes comme les fournisseurs distants.

    L'adapter était ``text_only`` : un modèle vision installé en local ne
    pouvait pas concourir au banc, alors que des poids figés sont **plus**
    reproductibles qu'un instantané d'API susceptible d'être déprécié.
    """

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
        model: str,
        host: str = _DEFAULT_HOST,
        role: str = "text_only",
        prompt: str | None = None,
        temperature: float | None = DEFAULT_TEMPERATURE,
        top_p: float | None = None,
        seed: int | None = DEFAULT_SEED,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        num_ctx: int = DEFAULT_NUM_CTX,
        timeout: object = DEFAULT_LLM_TIMEOUT,
    ) -> None:
        self._label = validate_llm_label(label, "OllamaAdapter")
        self._timeout = validate_timeout(timeout, "OllamaAdapter")
        self._settings = InferenceSettings.build(
            temperature=temperature, top_p=top_p, seed=seed, max_tokens=max_tokens
        )
        if isinstance(num_ctx, bool) or not isinstance(num_ctx, int) or num_ctx < 1:
            raise AdapterStepError(
                "OllamaAdapter : réglage 'num_ctx' : entier ≥ 1 attendu, "
                f"reçu {num_ctx!r}."
            )
        self._num_ctx = num_ctx
        self._model = require_model(model, "OllamaAdapter")
        self._host = host
        self._role: PipelineMode = validate_role(
            role, "OllamaAdapter", self.SUPPORTED_MODES
        )
        self._prompt = (
            prompt if prompt is not None else default_prompt_for_role(self._role)
        )

    @property
    def name(self) -> str:
        return f"ollama:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    def system_binaries(self) -> dict[str, str]:
        """Le **digest** des poids servis sous ce tag (``/api/tags``), sondé
        une fois avant la première page : au manifeste
        (``system_binaries_lock``) et dans la clé d'unité. Un tag se réaffecte
        (``ollama pull``) : deux digests sont deux modèles, et une archive d'un
        autre digest est ré-exécutée, pas relue. Relu de l'archive hors ligne.

        Best-effort comme le binaire de Tesseract : serveur injoignable ou
        modèle absent → ``{}`` (l'unité échouera alors en le nommant).
        """
        try:
            models = list_models(self._host, capabilities=False)
        except ModelListingError as exc:
            logger.warning("[ollama] digest de %s non lu : %s", self._model, exc)
            return {}
        for listed in models:
            if same_model(self._model, listed.name) and listed.digest:
                return {f"ollama:{listed.name}": listed.digest}
        logger.warning(
            "[ollama] %s absent du serveur %s : digest non lu.",
            self._model,
            public_endpoint(self._host),
        )
        return {}

    def effective_settings(self) -> EffectiveSettings:
        """Réglages **effectifs** (défauts compris) : manifeste et empreinte.

        ``max_tokens`` part comme ``options.num_predict`` : le même nom que chez
        les trois autres fournisseurs, pour que deux manifestes se comparent.
        ``host`` est la cible (un autre serveur peut servir un autre modèle sous
        le même nom), écrite sans identifiants ni *query string*.
        """
        return llm_effective_settings(
            model=self._model,
            role=self._role,
            prompt=self._prompt,
            settings=self._settings,
            num_ctx=self._num_ctx,
            host=public_endpoint(self._host),
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
        options = _options(self._settings, self._num_ctx)
        deadline = step_deadline(context.deadline, self._timeout)

        def text_invoke(prompt: str) -> LLMCompletion:
            return _invoke_ollama(
                model=self._model,
                prompt=prompt,
                host=self._host,
                deadline=deadline,
                control=control,
                options=options,
            )

        def vision_invoke(
            prompt: str, media_type: str, image_b64: str
        ) -> LLMCompletion:
            # ``media_type`` est ignoré : ollama devine le format des octets.
            del media_type
            return _invoke_ollama(
                model=self._model,
                prompt=prompt,
                host=self._host,
                deadline=deadline,
                control=control,
                options=options,
                image_b64=image_b64,
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


__all__ = ["OllamaAdapter", "list_models", "model_from_tag", "same_model"]
