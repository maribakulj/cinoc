"""``MistralStructuredClient`` — sortie JSON contrainte, API Mistral.

Jumeau distant de :mod:`cinoc.adapters.correction.ollama_structured` : ``saknussemm``
ne consomme qu'une capacité d'un modèle (``StructuredCompletionClient``) — rendre
le JSON décrit par un schéma — et ce client la fournit depuis l'API Mistral.

Pourquoi un client **dédié** plutôt qu'un élargissement de
:class:`~cinoc.adapters.llm.mistral.MistralAdapter` : celui-ci est un ``Module``
de pipeline (il produit un artefact), celui-là est un *fournisseur* consommé par
une bibliothèque tierce. Les deux parlent à la même API, mais l'un rend un
``StepOutput`` et l'autre un couple ``(json, usage)`` — les confondre ferait
porter à l'adapter une signature qu'il n'a pas à honorer.

Deux détails qui ne sont pas des détails :

* le repli ``json_object``. ``response_format: json_schema`` n'est pas honoré par
  tous les modèles du catalogue ; sans repli, un modèle par ailleurs capable
  échoue sur la forme de la requête et non sur la tâche.
* les échecs de transport sont traduits en ``ProviderTransientError`` /
  ``ProviderPermanentError``. La recouvrabilité de ``saknussemm`` est une liste
  blanche : une exception brute est traitée comme un bug et **fait échouer** le
  run au lieu d'être réessayée en boucle.

Chaque corps reçu est gardé dans ``responses`` (ordre d'appel), **avant** d'être
lu — une réponse rejetée (hors schéma) a été payée, et c'est elle qui explique
la nouvelle tentative. L'étape de correction l'écrit en sidecar ``NATIVE_JSON``.
Le corps seul : la clé voyage en en-tête, jamais dans la réponse.
"""

from __future__ import annotations

import json
from typing import Any

from cinoc.adapters.llm.mistral import _completion_from_chat
from cinoc.domain.usage import ResourceUsage

#: Hôte de l'API. Constante, jamais fournie par l'utilisateur — donc hors du
#: périmètre du garde SSRF (qui protège les URI *de corpus*, elles saisies).
MISTRAL_BASE = "https://api.mistral.ai"


def provider_errors() -> tuple[type[Exception], type[Exception]]:
    """``(Transient, Permanent)`` de ``saknussemm``, importés paresseusement.

    Les classes concrètes vivent en ``core.protocols``, à côté du contrat qui
    les lève — ``errors`` n'ancre que leur base ``ProviderError``.
    """
    from saknussemm.core.protocols import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
        ProviderPermanentError,
        ProviderTransientError,
    )

    return ProviderTransientError, ProviderPermanentError


def parse_chat_json(data: dict[str, Any], model: str) -> dict[str, Any]:
    """Extrait l'objet JSON du premier choix d'une réponse *chat completions*.

    Partagé avec le client multimodal : les deux endpoints rendent la même
    enveloppe, et en dupliquer la lecture ferait diverger deux traductions
    d'erreur qui doivent rester identiques.
    """
    transient, permanent = provider_errors()
    choices = data.get("choices") or []
    content = ""
    finish_reason = None
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""
        finish_reason = choices[0].get("finish_reason")
    # La raison d'arrêt tranche **avant** le JSON : une coupure au plafond
    # (``length``) ou à la fenêtre du modèle (``model_length``) se reproduirait
    # à l'identique — permanente, donc jamais rejouée ni repayée par
    # ``saknussemm`` (ADR-008 : fatale pour la correction, qui échoue bruyamment
    # au lieu d'écrire un texte à demi corrigé). Une ``error`` de génération,
    # elle, peut guérir : transitoire.
    if finish_reason in ("length", "model_length"):
        raise permanent(
            f"mistral ({model}) : réponse tronquée (finish_reason="
            f"{finish_reason}) — la rejouer la couperait à l'identique ; "
            f"réduire le lot ou choisir un modèle à fenêtre plus large : "
            f"{content[:200]!r}"
        )
    if finish_reason == "error":
        raise transient(
            f"mistral ({model}) : génération interrompue (finish_reason=error)."
        )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise transient(
            f"mistral ({model}) n'a pas rendu du JSON — hors schéma, sans "
            f"troncature déclarée : {content[:200]!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise transient(
            f"mistral ({model}) a rendu {type(parsed).__name__}, pas un objet."
        )
    return parsed


def tokens_of(data: dict[str, Any]) -> ResourceUsage | None:
    """Jetons d'une réponse *chat completions*, lus **comme l'adaptateur
    Mistral** (``_completion_from_chat``) : ``tokens_in``/``tokens_out``, et les
    jetons lus en cache quand la réponse les rend (``prompt_tokens_details``).
    Une seule lecture : un compte que l'adaptateur sait lire ne se perd pas ici
    (S29a — avant, seuls ``prompt_tokens``/``completion_tokens`` étaient lus, et
    hors ``ResourceUsage``). ``None`` : aucun total rendu."""
    return _completion_from_chat(data).usage()


def responses_usage(responses: list[dict[str, Any]]) -> ResourceUsage | None:
    """Somme des jetons de toutes les réponses reçues (rejetées comprises :
    elles ont été payées) — l'``usage`` de l'étape de correction."""
    total: ResourceUsage | None = None
    for data in responses:
        part = tokens_of(data)
        if part is not None:
            total = part if total is None else total.merged_with(part)
    return total


def usage_from(data: dict[str, Any]) -> Any:
    """``usage`` de l'API → ``saknussemm.core.schemas.Usage`` (ou ``None``).

    Lu par ``tokens_of`` : les jetons alimentent l'axe coût du rapport ; les
    perdre rendrait un run payant indiscernable d'un run local. Le renommage
    n'est pas cosmétique : ``saknussemm`` dit ``input``/``output``, et le modèle
    Pydantic **accepte en silence** un nom inconnu — donc une traduction
    manquante ne lève pas, elle rend zéro jeton. Sa ``Usage`` n'a pas de
    compte de cache : celui-ci ne vit que dans ``ResourceUsage``.

    ``id`` de la réponse est repris dans ``response_ids`` : c'est ce qui permet
    à un rapport de nommer chaque réponse du fournisseur qui a contribué au run.
    """
    tokens = tokens_of(data)
    if tokens is None:
        return None
    from saknussemm.core.schemas import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
        Usage,
    )

    response_id = data.get("id")
    return Usage(
        input_tokens=tokens.tokens_in or 0,
        output_tokens=tokens.tokens_out or 0,
        response_ids=[str(response_id)] if response_id else [],
    )


async def post_chat(
    *,
    api_key: str,
    body: dict[str, Any],
    fallback_body: dict[str, Any] | None,
    model: str,
    timeout: float,
) -> dict[str, Any]:
    """POST ``/v1/chat/completions``, avec repli de ``response_format``.

    Un ``400`` sur le corps principal **et seulement lui** déclenche le repli :
    c'est la signature d'un modèle qui refuse ``json_schema``, pas d'une panne.
    Tout autre code garde sa sémantique (4xx permanent, 5xx transitoire).
    """
    import httpx  # noqa: PLC0415

    transient, permanent = provider_errors()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{MISTRAL_BASE}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=body, headers=headers)
            if response.status_code == 400 and fallback_body is not None:
                response = await client.post(
                    url, json=fallback_body, headers=headers
                )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = exc.response.text[:200]
        message = f"mistral a répondu {status} ({model}) : {detail}"
        # 4xx = la requête est fautive, la réessayer la referait échouer. 429 est
        # l'exception : c'est un débit dépassé, pas une requête malformée.
        if 400 <= status < 500 and status != 429:
            raise permanent(message) from exc
        raise transient(message) from exc
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise transient(f"mistral injoignable ({model}) : {exc}") from exc
    if not isinstance(payload, dict):
        raise transient(f"mistral ({model}) n'a pas rendu un objet JSON.")
    return payload


class MistralStructuredClient:
    """``complete_structured`` sur ``/v1/chat/completions``, schéma contraint."""

    def __init__(self, *, timeout: float = 300.0) -> None:
        self._timeout = timeout
        #: Corps reçus, dans l'ordre d'appel (cf. docstring du module).
        self.responses: list[dict[str, Any]] = []

    async def complete_structured(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], Any]:
        body: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_schema", "json_schema": json_schema},
        }
        data = await post_chat(
            api_key=api_key,
            body=body,
            fallback_body={**body, "response_format": {"type": "json_object"}},
            model=model,
            timeout=self._timeout,
        )
        self.responses.append(data)
        return parse_chat_json(data, model), usage_from(data)

    def usage(self) -> ResourceUsage | None:
        """Jetons de toutes les réponses reçues (``responses_usage``)."""
        return responses_usage(self.responses)


__all__ = [
    "MISTRAL_BASE",
    "MistralStructuredClient",
    "parse_chat_json",
    "post_chat",
    "provider_errors",
    "responses_usage",
    "tokens_of",
    "usage_from",
]
