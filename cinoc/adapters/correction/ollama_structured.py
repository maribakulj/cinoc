"""``OllamaStructuredClient`` — sortie JSON contrainte, serveur local.

``saknussemm`` ne consomme qu'une seule capacité d'un modèle
(``StructuredCompletionClient``) : rendre le JSON décrit par un schéma. Ce
client la fournit depuis un ``ollama`` local — aucune clé d'API, poids figés,
donc plus reproductible qu'un instantané d'API qui peut être déprécié.

Deux détails qui ne sont pas des détails :

* ``num_ctx`` est **explicite**. Le défaut d'``ollama`` est 2048 jetons et la
  troncature est **silencieuse** : le JSON revient coupé au milieu d'une chaîne,
  et l'erreur ressemble à une hallucination du modèle alors que c'est le serveur
  qui a coupé.
* les échecs de transport sont traduits en ``ProviderTransientError`` /
  ``ProviderPermanentError``. La recouvrabilité de ``saknussemm`` est une liste
  blanche : une exception brute est traitée comme un bug et **fait échouer** le
  run au lieu d'être réessayée en boucle.
"""

from __future__ import annotations

import json
from typing import Any

_DEFAULT_HOST = "http://localhost:11434"
#: Le défaut d'ollama (2048) tronque en silence une page de journal.
_DEFAULT_NUM_CTX = 8192


class OllamaStructuredClient:
    """``complete_structured`` sur ``/api/chat``, schéma JSON contraint."""

    def __init__(
        self,
        *,
        host: str = _DEFAULT_HOST,
        num_ctx: int = _DEFAULT_NUM_CTX,
        timeout: float = 300.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._num_ctx = num_ctx
        self._timeout = timeout

    async def complete_structured(
        self,
        api_key: str,  # noqa: ARG002 — un serveur local n'en a pas
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], Any]:
        import httpx  # noqa: PLC0415

        # Les classes concrètes vivent en ``core.protocols``, à côté du contrat
        # qui les lève — ``errors`` n'ancre que leur base ``ProviderError``.
        from saknussemm.core.protocols import (  # type: ignore[import-not-found]  # noqa: PLC0415
            ProviderPermanentError,
            ProviderTransientError,
        )

        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "stream": False,
            "format": _bare_schema(json_schema),
            "options": {"temperature": temperature, "num_ctx": self._num_ctx},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._host}/api/chat", json=body)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            message = f"ollama a répondu {status} ({model})"
            # 4xx = la requête est fautive, la réessayer la referait échouer.
            if 400 <= status < 500:
                raise ProviderPermanentError(message) from exc
            raise ProviderTransientError(message) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProviderTransientError(
                f"ollama injoignable ({model}) : {exc}"
            ) from exc

        content = (data.get("message") or {}).get("content") or ""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderTransientError(
                f"ollama ({model}) n'a pas rendu du JSON — réponse tronquée ou "
                f"hors schéma : {content[:200]!r}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ProviderTransientError(
                f"ollama ({model}) a rendu {type(parsed).__name__}, pas un objet."
            )
        return parsed, None


def _bare_schema(json_schema: dict[str, Any]) -> dict[str, Any]:
    """``format`` d'ollama attend le schéma **nu**, pas l'enveloppe OpenAI."""
    direct = json_schema.get("schema")
    if isinstance(direct, dict):
        return direct
    inner = json_schema.get("json_schema")
    if isinstance(inner, dict):
        nested = inner.get("schema")
        if isinstance(nested, dict):
            return nested
    return json_schema


__all__ = ["OllamaStructuredClient"]
