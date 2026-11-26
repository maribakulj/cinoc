"""``OllamaStructuredClient`` — sortie JSON contrainte, serveur local.

``saknussemm`` ne consomme qu'une seule capacité d'un modèle
(``StructuredCompletionClient``) : rendre le JSON décrit par un schéma. Ce
client la fournit depuis un ``ollama`` local — aucune clé d'API, poids figés,
donc plus reproductible qu'un instantané d'API qui peut être déprécié.

Deux détails qui ne sont pas des détails :

* ``num_ctx`` est **explicite**. Le défaut d'``ollama`` est 2048 jetons et la
  troncature est **silencieuse** : le JSON revient coupé au milieu d'une chaîne,
  et l'erreur ressemble à une hallucination du modèle alors que c'est le serveur
  qui a coupé. Quand elle arrive quand même, ``done_reason: length`` la dit :
  erreur **permanente** (la rejouer la couperait à l'identique).
* les échecs de transport sont traduits en ``ProviderTransientError`` /
  ``ProviderPermanentError``. La recouvrabilité de ``saknussemm`` est une liste
  blanche : une exception brute est traitée comme un bug et **fait échouer** le
  run au lieu d'être réessayée en boucle.

Chaque corps reçu est gardé dans ``responses`` (ordre d'appel), avant d'être
lu : l'étape de correction l'écrit en sidecar ``NATIVE_JSON``.

**Interruptible en vol** (S29a, comme l'adaptateur Ollama en S28a) : l'appel est
**diffusé** (``stream: true``) et reconstitué en le corps du mode non diffusé
(``ChatStream`` : mêmes clés, même texte — le sidecar ne change pas) ; entre
deux morceaux, l'arrêt du run est sondé ; avant le premier, la trace
``cut_on_cancel_async`` coupe le socket. Un arrêt lève ``CorrectionAborted``,
l'annulation du contrat de ``saknussemm`` — ni rejouée ni prise pour une panne
— que l'étape traduit en ``RunCancelledError``. ``timeout`` borne l'appel
**entier** : en flux, le délai de lecture du client ne borne plus qu'un
morceau.
"""

from __future__ import annotations

import json
from typing import Any

from cinoc.adapters._resilience import cut_on_cancel_async
from cinoc.adapters.llm.ollama import ChatStream, _completion_from_chat
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.usage import ResourceUsage
from cinoc.pipeline.run_control import RunControl

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
        control: RunControl | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._num_ctx = num_ctx
        self._timeout = timeout
        self._control = control if control is not None else RunControl()
        #: Corps reçus, dans l'ordre d'appel (réponses rejetées comprises).
        self.responses: list[Any] = []

    def _abort_if_stopped(self, model: str) -> None:
        """L'arrêt du run → ``CorrectionAborted`` (propagée par ``saknussemm``)."""
        if self._control.is_cancelled():
            from saknussemm.errors import (  # type: ignore[import-not-found]  # noqa: PLC0415
                CorrectionAborted,
            )

            raise CorrectionAborted(f"ollama ({model}) : run arrêté pendant l'appel.")

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
            # **En flux** : seule forme où un arrêt coupe une génération en cours.
            "stream": True,
            "format": _bare_schema(json_schema),
            "options": {"temperature": temperature, "num_ctx": self._num_ctx},
        }
        self._abort_if_stopped(model)
        deadline = Deadline.in_seconds(self._timeout)
        stream = ChatStream(model)
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout) as client,
                client.stream(
                    "POST",
                    f"{self._host}/api/chat",
                    json=body,
                    extensions={"trace": cut_on_cancel_async(self._control)},
                ) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    self._abort_if_stopped(model)
                    if deadline.is_expired():
                        raise ProviderTransientError(
                            f"ollama ({model}) : délai de {self._timeout:g} s "
                            "dépassé en génération."
                        )
                    if stream.feed(line):
                        break
            data = stream.body()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            message = f"ollama a répondu {status} ({model})"
            # 4xx = la requête est fautive, la réessayer la referait échouer.
            if 400 <= status < 500:
                raise ProviderPermanentError(message) from exc
            raise ProviderTransientError(message) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            self._abort_if_stopped(model)  # le socket coupé par l'arrêt
            raise ProviderTransientError(
                f"ollama injoignable ({model}) : {exc}"
            ) from exc
        except AdapterStepError as exc:  # flux illisible ou interrompu
            raise ProviderTransientError(str(exc)) from exc

        if data.get("error"):
            # Une erreur en cours de génération arrive dans le flux, en 200 :
            # pas une réponse (comme l'erreur HTTP du mode non diffusé).
            raise ProviderTransientError(f"ollama ({model}) : {data['error']}")
        self.responses.append(data)
        content = (data.get("message") or {}).get("content") or ""
        # ``done_reason: length`` : le serveur a coupé (``num_ctx`` épuisé).
        # Rejouer couperait à l'identique : permanente, jamais rejouée par
        # ``saknussemm`` (ADR-008 : la correction échoue bruyamment).
        if data.get("done_reason") == "length":
            raise ProviderPermanentError(
                f"ollama ({model}) : réponse tronquée (done_reason=length) — "
                f"la rejouer la couperait à l'identique ; relever num_ctx "
                f"(actuel : {self._num_ctx}) : {content[:200]!r}"
            )
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


    def usage(self) -> ResourceUsage | None:
        """Jetons de toutes les réponses reçues (``prompt_eval_count`` /
        ``eval_count``), lus comme l'adaptateur Ollama."""
        total: ResourceUsage | None = None
        for data in self.responses:
            part = _completion_from_chat(data, "").usage()
            if part is not None:
                total = part if total is None else total.merged_with(part)
        return total


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
