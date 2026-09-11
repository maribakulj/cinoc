"""``MistralStructuredClient`` — sortie JSON contrainte, API Mistral.

Jumeau distant de :mod:`cinoc.adapters.llm.ollama_structured` : ``saknussemm``
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
"""

from __future__ import annotations

import json
from typing import Any

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
    transient, _ = provider_errors()
    choices = data.get("choices") or []
    content = ""
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise transient(
            f"mistral ({model}) n'a pas rendu du JSON — réponse tronquée ou "
            f"hors schéma : {content[:200]!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise transient(
            f"mistral ({model}) a rendu {type(parsed).__name__}, pas un objet."
        )
    return parsed


def usage_from(data: dict[str, Any]) -> Any:
    """``usage`` de l'API → ``saknussemm.core.schemas.Usage`` (ou ``None``).

    Les jetons alimentent l'axe coût du rapport ; les perdre rendrait un run
    payant indiscernable d'un run local. Le renommage n'est pas cosmétique :
    l'API dit ``prompt``/``completion``, ``saknussemm`` dit ``input``/``output``,
    et le modèle Pydantic **accepte en silence** un nom inconnu — donc une
    traduction manquante ne lève pas, elle rend zéro jeton.

    ``id`` de la réponse est repris dans ``response_ids`` : c'est ce qui permet
    à un rapport de nommer chaque réponse du fournisseur qui a contribué au run.
    """
    raw = data.get("usage")
    if not isinstance(raw, dict):
        return None
    from saknussemm.core.schemas import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
        Usage,
    )

    response_id = data.get("id")
    return Usage(
        input_tokens=int(raw.get("prompt_tokens") or 0),
        output_tokens=int(raw.get("completion_tokens") or 0),
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
        return parse_chat_json(data, model), usage_from(data)


__all__ = [
    "MISTRAL_BASE",
    "MistralStructuredClient",
    "parse_chat_json",
    "post_chat",
    "provider_errors",
    "usage_from",
]
