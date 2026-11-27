"""``JobStore`` — état des jobs de run, **en mémoire et thread-safe** (couche 5).

Un job = une exécution asynchrone d'un ``RunSpec`` (lancée par le ``JobRunner``,
couche 6). Le store ne *fait* rien : il garde l'état observable (la machine à
états ci-dessous) pour que le web le restitue et qu'un ``cancel`` soit traçable.

Concurrence : un seul verrou protège le dict ; ``Job`` est **immuable** (pydantic
``frozen``), donc un lecteur (requête HTTP) reçoit un instantané cohérent sans
risque de course avec le worker qui le remplace sous verrou.

Chaque transition est aussi **journalisée** (``_history``) : un instantané ``Job``
par changement d'état, indexé par un id monotone (1-based). C'est la matière
première du **flux SSE** + de la reprise ``Last-Event-ID`` (couche 8) — rejouable
même après la fin du job.
"""

from __future__ import annotations

import threading
import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from cinoc.domain.errors import CinocError
from cinoc.domain.run import utcnow


class JobState(StrEnum):
    """États d'un job. Terminaux : ``DONE``, ``FAILED``, ``CANCELLED``."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL


_TERMINAL = frozenset({JobState.DONE, JobState.FAILED, JobState.CANCELLED})


class JobError(CinocError):
    """Job introuvable."""


class Job(BaseModel):
    """Instantané immuable de l'état d'un job."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    state: JobState
    created_at: str
    updated_at: str
    #: Stem du ``RunResult`` JSON écrit quand ``state == DONE`` (sinon ``None``).
    report_name: str | None = None
    #: Message d'erreur quand ``state == FAILED`` (sinon ``None``).
    error: str | None = None
    #: URL distante du rapport publié si la persistance est active, sinon ``None``.
    published_url: str | None = None
    #: Progression : unités (document × concurrent) traitées / total. ``0/0`` =
    #: inconnu (job pas encore démarré). Alimente la barre de progression (SSE).
    done: int = 0
    total: int = 0
    #: L'unité dont la fin a produit cet instantané (``progress``) : chaîne,
    #: document et issue (``ok``/``truncated``/``failed``/``resumed``) — le
    #: journal de la page les nomme. ``None`` sur une transition d'état.
    pipeline: str | None = None
    document_id: str | None = None
    outcome: str | None = None


class JobStore:
    """Dictionnaire thread-safe ``job_id → Job`` (instantanés immuables)."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._history: dict[str, list[Job]] = {}
        self._lock = threading.Lock()

    def create(self) -> Job:
        """Crée un job ``PENDING`` (id généré) et le renvoie."""
        now = utcnow().isoformat()
        job = Job(id=uuid.uuid4().hex, state=JobState.PENDING, created_at=now,
                  updated_at=now)
        with self._lock:
            self._jobs[job.id] = job
            self._history[job.id] = [job]
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all_jobs(self) -> tuple[Job, ...]:
        """Tous les jobs, du plus récent au plus ancien."""
        with self._lock:
            jobs = tuple(self._jobs.values())
        return tuple(sorted(jobs, key=lambda j: j.created_at, reverse=True))

    def update(
        self,
        job_id: str,
        *,
        state: JobState,
        report_name: str | None = None,
        error: str | None = None,
        published_url: str | None = None,
    ) -> Job:
        """Remplace l'instantané du job (sous verrou). Lève si inconnu."""
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise JobError(f"job {job_id!r} introuvable.")
            updated = current.model_copy(
                update={
                    "state": state,
                    "report_name": report_name,
                    "error": error,
                    "published_url": published_url,
                    "pipeline": None,
                    "document_id": None,
                    "outcome": None,
                    "updated_at": utcnow().isoformat(),
                }
            )
            self._jobs[job_id] = updated
            self._history[job_id].append(updated)
        return updated

    def progress(
        self,
        job_id: str,
        done: int,
        total: int,
        *,
        pipeline: str | None = None,
        document_id: str | None = None,
        outcome: str | None = None,
    ) -> Job:
        """Met à jour la progression (``done``/``total``) **sans changer l'état**.

        Ajoute un instantané au journal → un **événement SSE** (de type ``running``)
        par unité traitée, que l'UI consomme pour la barre de progression. Les
        autres champs (état, rapport…) sont préservés (``model_copy`` ciblé).
        """
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise JobError(f"job {job_id!r} introuvable.")
            updated = current.model_copy(
                update={
                    "done": done,
                    "total": total,
                    "pipeline": pipeline,
                    "document_id": document_id,
                    "outcome": outcome,
                    "updated_at": utcnow().isoformat(),
                }
            )
            self._jobs[job_id] = updated
            self._history[job_id].append(updated)
        return updated

    def history_since(self, job_id: str, after_id: int) -> list[tuple[int, Job]]:
        """Instantanés (``event_id``, ``Job``) du journal **après** ``after_id``.

        ``event_id`` est la position 1-based dans le journal du job → c'est l'id
        d'événement SSE (``Last-Event-ID``). Job inconnu → liste vide.
        """
        with self._lock:
            history = list(self._history.get(job_id, ()))
        return [(i, job) for i, job in enumerate(history, start=1) if i > after_id]


__all__ = ["Job", "JobError", "JobState", "JobStore"]
