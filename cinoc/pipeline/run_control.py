"""``RunControl`` — signal d'annulation coopératif d'un run.

Porté à chaque ``Module.execute`` : l'adapter vérifie ``raise_if_cancelled()``
entre deux opérations bloquantes et lève ``RunCancelledError`` si le caller
(utilisateur, deadline globale) a demandé l'arrêt. C'est un concern d'exécution
→ couche 4 (jamais ``domain``).

Au-delà du sondage coopératif, un adapter qui **bloque sur un appel réseau** peut
enregistrer un *handle* (``register_cancel_handle``) : un callback que
``trigger_cancel`` invoque pour **interrompre l'appel en vol** (p. ex. fermer la
connexion HTTP). Le sondage reste la **garantie** ; le handle n'est qu'une
accélération *best-effort*. L'adapter ``ollama`` en est l'implémentation de
référence (cf. couche 5).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from cinoc.domain.errors import RunCancelledError

#: Callback d'interruption, invoqué **une fois** à l'annulation. Doit être sûr —
#: idempotent et sans lever : un handle qui échoue masquerait les suivants.
CancelHandle = Callable[[], None]


class RunControl:
    """Poignée d'annulation coopérative, partagée le temps d'un run.

    Thread-safe (``threading.Event`` + ``Lock``). Le sondage coopératif
    (``raise_if_cancelled``) est la garantie d'arrêt ; ``register_cancel_handle``
    ajoute une interruption *best-effort* des appels bloquants (fermeture de
    connexion). Enregistrement et déclenchement se synchronisent sur le même
    verrou : aucun handle n'est ni perdu (course register/trigger) ni appelé
    deux fois.

    Limite assumée : un ``cancel_event`` *partagé* mis à ``set()`` **en dehors**
    de ``trigger_cancel`` (p. ex. par une deadline globale) propage bien l'état
    (``is_cancelled``) mais **ne déclenche pas** les handles — seul le sondage
    coopératif reste alors actif. Les handles sont liés à l'API ``trigger_cancel``.
    """

    def __init__(self, cancel_event: threading.Event | None = None) -> None:
        self._cancel = (
            cancel_event if cancel_event is not None else threading.Event()
        )
        self._lock = threading.Lock()
        self._handles: list[CancelHandle] = []

    def trigger_cancel(self) -> None:
        """Signale l'annulation et déclenche les handles enregistrés. Idempotent.

        Les handles sont vidés sous verrou avant d'être appelés (hors verrou) :
        un second ``trigger_cancel`` n'en rappelle aucun.
        """
        with self._lock:
            self._cancel.set()
            handles = tuple(self._handles)
            self._handles.clear()
        for handle in handles:
            handle()

    def register_cancel_handle(self, handle: CancelHandle) -> None:
        """Enregistre un callback d'interruption d'appel bloquant.

        Invoqué une fois quand ``trigger_cancel`` survient. Si l'annulation a
        **déjà** eu lieu, le handle est appelé **immédiatement** (pas de course :
        le test et l'enregistrement sont sous le même verrou que le déclenchement).
        """
        with self._lock:
            if not self._cancel.is_set():
                self._handles.append(handle)
                return
        handle()

    def is_cancelled(self) -> bool:
        """Sonde **non levante** de l'annulation (poll coopératif, p. ex. boucle
        worker). ``raise_if_cancelled`` est la variante qui lève."""
        return self._cancel.is_set()

    def wait(self, seconds: float) -> bool:
        """Attend au plus ``seconds`` — **interrompu** par l'annulation.

        Rend ``True`` si l'annulation est survenue (pendant ou avant). C'est
        l'attente d'un retry ou d'une sonde : un arrêt demandé pendant un
        backoff de 30 s ne doit pas attendre 30 s.
        """
        return self._cancel.wait(max(0.0, seconds))

    def raise_if_cancelled(self) -> None:
        """Lève ``RunCancelledError`` si l'annulation a été demandée."""
        if self._cancel.is_set():
            raise RunCancelledError("run annulé (annulation coopérative).")


__all__ = ["CancelHandle", "RunControl"]
