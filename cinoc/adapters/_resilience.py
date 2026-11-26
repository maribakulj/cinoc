"""Résilience des appels réseau (couche 5, adapters) : délai, quota, retry.

**La seule politique de retry** des moteurs distants (P5f 7) : les SDK sont
construits sans la leur (``max_retries=0`` chez OpenAI et Anthropic,
``retry_config=None`` chez Mistral — le SDK 3.x n'en a pas par défaut, on
l'écrit pour qu'un défaut futur ne s'ajoute pas en silence). Avant, OpenAI et
Anthropic retentaient deux fois sous chacune des cinq tentatives de Cinoc :
jusqu'à 15 appels, invisibles.

- **Délai fini** (``step_deadline``) : chaque moteur distant a un délai par
  défaut (``DEFAULT_LLM_TIMEOUT``, ``DEFAULT_OCR_TIMEOUT``), réglable par le
  réglage ``timeout`` de la spec — celui qui existait déjà pour Tesseract et
  les segmenteurs ; la deadline d'une étape est la plus proche de celle du run
  et de ce délai. Aucun appelant ne passait de deadline : Ollama, Azure et
  Google tournaient sans aucun délai.
- **Cap de concurrence par serveur** (``network_slot``) : un sémaphore borné
  *par serveur* (``hôte:port`` de l'endpoint, ``endpoint_slot_key``) quand
  l'appelant le connaît, *par fournisseur* sinon → au plus N appels
  simultanés. Deux instances OpenAI-compatibles sur deux serveurs ne se
  bloquent pas ; deux sur le même serveur partagent ses créneaux (P5f 6). L'attente
  d'un créneau est bornée par la deadline (sous contention, elle ne bloque plus).
- **Retry borné** (``call_resilient``) : sur 429/5xx **et** erreur de
  transport, attend ``Retry-After`` si le serveur l'indique, sinon un backoff
  exponentiel borné + gigue — sans jamais attendre au-delà de la deadline, et
  interrompu par l'annulation (``RunControl``).
- **Tentatives comptées** (``BillingMeter``) : chaque tentative facturable,
  pour l'économie. Règle, la même pour les sept moteurs distants faute de
  source primaire qui la contredise : un **succès** est facturé ; un **refus
  HTTP** (429, 5xx, 4xx) ne l'est pas — le service a répondu qu'il ne
  traitait pas (à confirmer chez chacun : aucune des sept documentations ne
  l'écrit ; seules des réponses de forum, OpenAI et Azure OpenAI, l'indiquent) ;
  une **connexion refusée** ne l'est pas — rien n'est parti ; une **requête
  coupée après envoi** (lecture interrompue, délai de lecture) l'est
  peut-être — le service a pu la traiter : elle est **comptée** (à confirmer ;
  le forum OpenAI dit qu'un délai dépassé peut être facturé).

Stdlib pure (aucune dépendance). **Déterminisme (invariant §12)** : ces mécanismes
ne changent que le *timing*, jamais la valeur renvoyée → le ``RunResult`` reste
byte-identique. ``N`` = ``CINOC_NETWORK_CONCURRENCY`` (défaut 3, plancher 1).
"""

from __future__ import annotations

import logging
import os
import random
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TypeVar
from urllib.parse import urlsplit

from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError, DeadlineExceeded, RunCancelledError
from cinoc.domain.usage import ResourceUsage
from cinoc.pipeline.run_control import RunControl

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Délai par défaut d'une étape LLM/VLM (OpenAI, Anthropic, Mistral, Ollama),
#: retries compris : les 10 minutes qui étaient le défaut des SDK openai et
#: anthropic — le seul délai qu'ils avaient. Un VLM local sur CPU met 36 à
#: 136 s par page (pilote D-281).
DEFAULT_LLM_TIMEOUT = 600.0
#: Délai par défaut d'une étape d'OCR distant (Mistral OCR, Azure DI, Google
#: Vision), retries et sondes compris : celui de Tesseract pour une page.
DEFAULT_OCR_TIMEOUT = 120.0
#: Borne haute d'un délai réglé : au-delà, ce n'est plus un délai.
_TIMEOUT_MAX = 3600.0

#: Plafond par défaut d'appels réseau concurrents **par serveur** (anti-429).
_DEFAULT_LIMIT = 3
_LIMIT_ENV = "CINOC_NETWORK_CONCURRENCY"
#: Politique de retry : tentatives + backoff exponentiel borné (secondes).
_DEFAULT_ATTEMPTS = 5
_BASE_BACKOFF = 1.0
_MAX_BACKOFF = 30.0
#: Statuts HTTP retentés : 429 (rate limit) + 5xx transitoires (instabilité).
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
#: Erreurs de transport, reconnues par le **nom** de leur classe (le SDK qui les
#: lève n'est pas importé ici) : ``httpx.TransportError`` (Mistral, Azure,
#: Google, Ollama) et ``APIConnectionError`` (openai, anthropic — qui
#: enveloppent leur client HTTP ; ``APITimeoutError`` en hérite).
_TRANSPORT_NAMES = frozenset({"TransportError", "APIConnectionError"})
#: Erreurs qui disent que **rien n'est parti** : la connexion n'a pas abouti.
_NOT_SENT_NAMES = frozenset({"ConnectError", "ConnectTimeout", "PoolTimeout"})

#: Registre process-global des sémaphores, créés paresseusement (aucun effet de
#: bord à l'import). Protégé par un verrou : ``network_slot`` est thread-safe.
_SEMAPHORES: dict[str, threading.BoundedSemaphore] = {}
_REGISTRY_LOCK = threading.Lock()


def validate_timeout(value: object, owner: str) -> float:
    """Le délai d'une étape, en secondes : un nombre dans ]0, 3600]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterStepError(f"{owner} : timeout numérique attendu, reçu {value!r}.")
    if not 0 < float(value) <= _TIMEOUT_MAX:
        raise AdapterStepError(
            f"{owner} : timeout ∈ ]0, {_TIMEOUT_MAX:g}] secondes, reçu {value}."
        )
    return float(value)


def step_deadline(deadline: Deadline, timeout: float) -> Deadline:
    """La deadline de l'étape : la plus proche de celle du run et du délai."""
    remaining = deadline.remaining_seconds()
    if remaining is not None and remaining <= timeout:
        return deadline
    return Deadline.in_seconds(timeout)


def request_timeout(deadline: Deadline) -> float | None:
    """Délai à passer à **un** appel : le temps restant (``None`` si infini)."""
    remaining = deadline.remaining_seconds()
    return None if remaining is None else max(remaining, 0.001)


def register_close(control: RunControl, client: object) -> None:
    """Annulation câblée *best-effort* : fermer le client interrompt l'appel
    en vol. ``close`` (openai, anthropic), sinon la sortie de son contexte
    (``mistralai`` 3.x n'a que ``__exit__``, qui ferme son transport) ; un
    client sans l'un ni l'autre reste sous le sondage."""
    close = getattr(client, "close", None)
    if callable(close):
        control.register_cancel_handle(close)
        return
    exit_ = getattr(client, "__exit__", None)
    if callable(exit_):
        control.register_cancel_handle(lambda: exit_(None, None, None))


@dataclass
class BillingMeter:
    """Tentatives **facturables** d'un appel (voir la règle du module)."""

    pages: int = 0

    def usage(self) -> ResourceUsage | None:
        """Pages facturées, pour ``StepOutput.usage`` (``None`` si aucune)."""
        return ResourceUsage(billed_pages=self.pages) if self.pages else None


def _network_limit() -> int:
    """Plafond effectif depuis l'environnement (défaut ``_DEFAULT_LIMIT``)."""
    raw = os.environ.get(_LIMIT_ENV)
    if raw is None:
        return _DEFAULT_LIMIT
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "[resilience] %s=%r invalide (entier attendu) — défaut %d.",
            _LIMIT_ENV,
            raw,
            _DEFAULT_LIMIT,
        )
        return _DEFAULT_LIMIT
    return max(1, value)


_DEFAULT_PORTS = {"http": 80, "https": 443}


def endpoint_slot_key(url: str) -> str:
    """Le serveur qu'une URL désigne : ``hôte:port``, port par défaut du schéma.

    C'est la clé du créneau réseau : le quota protège un **serveur**, pas un
    fournisseur. Deux chemins vers le même serveur (``…:11434`` et
    ``…:11434/v1``) partagent sa clé ; deux ports, deux serveurs. Une clé de
    serveur porte toujours ``:`` — un nom de fournisseur jamais : elles ne se
    confondent pas.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:  # validé à la construction : ne devrait pas arriver
        port = None
    return f"{host}:{port if port is not None else _DEFAULT_PORTS.get(parts.scheme, 0)}"


def network_slot(key: str) -> threading.BoundedSemaphore:
    """Sémaphore borné d'un serveur ou d'un fournisseur : ``with network_slot(k): …``.

    Au plus ``_network_limit()`` détenteurs simultanés par clé. Chaque clé a son
    quota propre (un run OpenAI + Mistral ne les fait pas se partager le budget,
    ni deux serveurs OpenAI-compatibles). Le plafond est figé à la première
    création de la clé (lecture d'environnement unique, déterministe pour la
    durée du process)."""
    with _REGISTRY_LOCK:
        sem = _SEMAPHORES.get(key)
        if sem is None:
            sem = threading.BoundedSemaphore(_network_limit())
            _SEMAPHORES[key] = sem
    return sem


def _default_jitter() -> float:
    return random.uniform(0.0, 1.0)


def _backoff(attempt: int, jitter: Callable[[], float]) -> float:
    """Backoff exponentiel borné + gigue (désynchronise les threads concurrents)."""
    return min(_MAX_BACKOFF, _BASE_BACKOFF * (2.0**attempt)) + jitter()


def _status(exc: BaseException) -> object:
    """Statut HTTP porté par l'erreur : ``status_code`` (SDK), sinon celui de
    ``exc.response`` (``httpx.HTTPStatusError``)."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status


def _chain(exc: BaseException) -> Iterator[type[BaseException]]:
    """Classes de l'erreur et de ses causes (un SDK enveloppe son transport)."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield from type(current).__mro__  # type: ignore[misc]
        current = current.__cause__ or current.__context__


def http_is_retryable(exc: BaseException) -> bool:
    """Vrai si l'erreur porte un statut HTTP transitoire (429/5xx)."""
    return _status(exc) in _RETRYABLE_STATUS


def is_transient(exc: BaseException) -> bool:
    """Retentable : statut 429/5xx, ou erreur de **transport** (connexion
    refusée ou coupée, délai de lecture). Une erreur sans statut ni transport
    (bug local, 4xx) n'est pas retentée — on ne masque pas un vrai défaut."""
    if http_is_retryable(exc):
        return True
    return any(cls.__name__ in _TRANSPORT_NAMES for cls in type(exc).__mro__)


def attempt_billed(exc: BaseException) -> bool:
    """Une tentative **échouée** a-t-elle pu être facturée ? (règle du module)."""
    if _status(exc) is not None:
        return False  # le service a répondu : refus, rien de traité
    if not any(cls.__name__ in _TRANSPORT_NAMES for cls in type(exc).__mro__):
        return False  # rien n'a quitté la machine (erreur locale)
    return not any(cls.__name__ in _NOT_SENT_NAMES for cls in _chain(exc))


def http_retry_after(exc: BaseException) -> float | None:
    """Délai ``Retry-After`` (secondes, borné) si le serveur l'indique, sinon ``None``.

    Sonde l'en-tête sur ``exc.response.headers`` puis ``exc.headers`` ; tolère
    toute absence/forme invalide (→ ``None`` → l'appelant calcule un backoff)."""
    for holder in (getattr(exc, "response", None), exc):
        headers = getattr(holder, "headers", None)
        if headers is None or not hasattr(headers, "get"):
            continue
        raw = headers.get("retry-after")
        if raw is None:
            continue
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            continue
        if seconds >= 0:
            return min(_MAX_BACKOFF, seconds)
    return None


def _expired(
    provider: str, why: str, meter: BillingMeter | None
) -> DeadlineExceeded:
    return DeadlineExceeded(
        f"{provider} : délai dépassé ({why}).",
        billed=meter.usage() if meter is not None else None,
    )


def call_resilient(
    provider: str,
    fn: Callable[[], T],
    *,
    deadline: Deadline,
    endpoint: str | None = None,
    control: RunControl | None = None,
    meter: BillingMeter | None = None,
    is_retryable: Callable[[BaseException], bool] = is_transient,
    retry_after: Callable[[BaseException], float | None] = http_retry_after,
    attempts: int = _DEFAULT_ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
    jitter: Callable[[], float] = _default_jitter,
) -> T:
    """Exécute ``fn`` sous le quota de son serveur, borné par ``deadline``.

    ``endpoint`` (l'URL appelée) choisit le créneau du **serveur** ; sans lui,
    celui du fournisseur ``provider`` (un SDK à endpoint fixe).

    ``deadline`` est **exigée** : aucun appel distant ne part sans. Avant chaque
    tentative : annulation sondée, deadline vérifiée, créneau acquis **dans le
    temps restant** (relâché pendant l'attente → on ne gèle pas un quota en
    dormant). ``fn`` lit lui-même le temps restant (``request_timeout``) pour
    le passer à son appel. Sur erreur :

    - annulation demandée → ``RunCancelledError`` (le run s'arrête) ;
    - deadline écoulée → ``DeadlineExceeded`` : le délai de SDK qui s'est
      déclenché est celui qu'on lui a passé, pas une panne du moteur ;
    - retentable et tentatives restantes → attente ``Retry-After`` ou backoff,
      **sauf** si elle dépasse le temps restant (``DeadlineExceeded``, qui nomme
      la dernière erreur) ; l'attente est interrompue par l'annulation ;
    - sinon l'exception remonte (l'appelant la traduit en ``AdapterStepError``).

    ``meter`` compte les tentatives facturables. ``sleep``/``jitter``
    injectables (tests déterministes). **Ne change que le *timing*, jamais la
    valeur renvoyée.**
    """
    ctrl = control if control is not None else RunControl()
    slot_key = endpoint_slot_key(endpoint) if endpoint is not None else provider

    def wait(seconds: float) -> None:
        if sleep is not None:
            sleep(seconds)
        else:
            ctrl.wait(seconds)

    for attempt in range(attempts):
        ctrl.raise_if_cancelled()
        if deadline.is_expired():
            raise _expired(provider, f"avant la tentative {attempt + 1}", meter)
        slot = network_slot(slot_key)
        if not slot.acquire(timeout=request_timeout(deadline)):
            raise _expired(provider, "en attendant un créneau réseau", meter)
        if ctrl.is_cancelled():
            # Arrêté pendant l'attente du créneau : aucun appel (facturé)
            # ne part après l'arrêt (D-299).
            slot.release()
            raise RunCancelledError(f"{provider} : run annulé avant l'appel.")
        delay = 0.0
        try:
            result = fn()
        except Exception as exc:
            if meter is not None and attempt_billed(exc):
                meter.pages += 1
            if ctrl.is_cancelled():
                raise RunCancelledError(
                    f"{provider} : run annulé pendant l'appel."
                ) from exc
            if deadline.is_expired():
                raise _expired(provider, type(exc).__name__, meter) from exc
            if not is_retryable(exc) or attempt == attempts - 1:
                raise
            after = retry_after(exc)
            delay = after if after is not None else _backoff(attempt, jitter)
            remaining = deadline.remaining_seconds()
            if remaining is not None and delay >= remaining:
                raise _expired(
                    provider,
                    f"tentative {attempt + 1}/{attempts} échouée "
                    f"({type(exc).__name__}) ; attendre {delay:.1f} s dépasserait "
                    f"les {remaining:.1f} s restantes",
                    meter,
                ) from exc
            logger.warning(
                "[resilience] %s : tentative %d/%d échouée (%s) — "
                "nouvelle tentative dans %.1f s.",
                provider,
                attempt + 1,
                attempts,
                type(exc).__name__,
                delay,
            )
        else:
            if meter is not None:
                meter.pages += 1
            return result
        finally:
            slot.release()
        wait(delay)  # hors du créneau : on ne retient pas le quota en dormant
    raise AssertionError(  # pragma: no cover — la boucle retourne ou relance avant
        "call_resilient : boucle épuisée sans issue"
    )


__all__ = [
    "DEFAULT_LLM_TIMEOUT",
    "DEFAULT_OCR_TIMEOUT",
    "BillingMeter",
    "attempt_billed",
    "call_resilient",
    "endpoint_slot_key",
    "http_is_retryable",
    "http_retry_after",
    "is_transient",
    "network_slot",
    "register_close",
    "request_timeout",
    "step_deadline",
    "validate_timeout",
]
