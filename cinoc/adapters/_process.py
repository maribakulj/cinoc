"""Attendre un binaire externe sans perdre la main (couche 5).

Un processus lancé par une brique (``tesseract``, un processeur OCR-D) est
attendu **par tranches courtes** : à l'annulation (``RunControl``) ou au
dépassement du délai de l'étape, il est arrêté — ``terminate``, puis ``kill``
s'il insiste — et **toujours attendu** (pas de zombie, sous Windows comme
ailleurs). Une interruption du parent (Ctrl-C) l'emporte aussi : l'enfant ne
survit pas au run. Délai → ``DeadlineExceeded`` (motif « arrêtée (délai) ») ;
arrêt → ``RunCancelledError``.

Partagé par ``ocr._tesseract_cli`` (D-300) et ``layout.ocrd_processor``
(D-301) : la même règle d'arrêt, écrite une fois.
"""

from __future__ import annotations

import subprocess
import time

from cinoc.domain.errors import DeadlineExceeded, RunCancelledError
from cinoc.pipeline.run_control import RunControl

#: Pas d'attente du processus : délai de réaction à un arrêt demandé.
POLL_SECONDS = 0.1
#: Ce que ``terminate`` laisse au binaire avant ``kill``.
GRACE_SECONDS = 2.0


def stop_process(process: subprocess.Popen[bytes]) -> None:
    """``terminate``, puis ``kill`` s'il insiste — et toujours ``wait`` (pas de
    zombie). Sous Windows, ``terminate`` est déjà ``TerminateProcess``."""
    process.terminate()
    try:
        process.wait(timeout=GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def wait_or_stop(
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
    control: RunControl,
    what: str,
    subject: str,
) -> int:
    """Code de sortie, en sondant l'arrêt et le délai toutes les 100 ms.

    ``what`` nomme la brique, ``subject`` ce qu'elle traitait (cité tel quel
    dans le message : à l'appelant de n'y mettre aucun chemin local)."""
    end = time.monotonic() + timeout
    try:
        while True:
            remaining = end - time.monotonic()
            try:
                return process.wait(timeout=max(0.0, min(POLL_SECONDS, remaining)))
            except subprocess.TimeoutExpired:
                pass
            if control.is_cancelled():
                stop_process(process)
                raise RunCancelledError(
                    f"{what} : arrêté à la demande sur {subject!r}."
                )
            if time.monotonic() >= end:
                stop_process(process)
                raise DeadlineExceeded(
                    f"{what} : délai dépassé sur {subject!r} "
                    f"(au-delà de {timeout:g} s)."
                )
    except BaseException:
        # Interruption du parent (Ctrl-C) : l'enfant ne survit pas au run.
        if process.poll() is None:
            stop_process(process)
        raise


__all__ = ["GRACE_SECONDS", "POLL_SECONDS", "stop_process", "wait_or_stop"]
