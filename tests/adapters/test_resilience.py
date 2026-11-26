"""Résilience réseau : cap de concurrence par fournisseur + retry borné 429/5xx.

Tout est déterministe : ``sleep``/``jitter`` injectés, exceptions factices avec
``status_code``/``headers``. Le câblage live de Mistral est ``# pragma: no cover``
(réseau + clé) ; ici on couvre le mécanisme générique qu'il consomme.
"""

from __future__ import annotations

import threading
import time

import pytest

from cinoc.adapters._resilience import (
    BillingMeter,
    call_resilient,
    http_is_retryable,
    http_retry_after,
    is_transient,
    network_slot,
    step_deadline,
)
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import DeadlineExceeded, RunCancelledError
from cinoc.pipeline.run_control import RunControl

_INF = Deadline.infinite()


class _FakeHTTPError(Exception):
    """Imite une erreur SDK httpx : porte ``status_code`` (+ ``headers`` option.)."""

    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        if headers is not None:
            self.headers = headers


# --- prédicats HTTP -------------------------------------------------------


def test_is_retryable_on_429_and_5xx() -> None:
    assert http_is_retryable(_FakeHTTPError(429))
    assert http_is_retryable(_FakeHTTPError(503))


def test_not_retryable_on_4xx_or_no_status() -> None:
    assert not http_is_retryable(_FakeHTTPError(400))
    assert not http_is_retryable(ValueError("réseau coupé"))  # pas de status_code


def test_retry_after_reads_header() -> None:
    assert http_retry_after(_FakeHTTPError(429, {"retry-after": "7"})) == 7.0


def test_retry_after_absent_is_none() -> None:
    assert http_retry_after(_FakeHTTPError(429)) is None
    assert http_retry_after(_FakeHTTPError(429, {"x": "y"})) is None


def test_retry_after_is_capped() -> None:
    # Un Retry-After absurde est borné (anti-blocage).
    assert http_retry_after(_FakeHTTPError(429, {"retry-after": "9999"})) == 30.0


# --- call_resilient -------------------------------------------------------


def test_returns_first_success_without_retry() -> None:
    calls = []

    def once() -> str:
        calls.append(1)
        return "ok"

    result = call_resilient("p-ok", once, deadline=_INF, sleep=lambda d: None)
    assert result == "ok"
    assert len(calls) == 1


def test_retries_then_succeeds() -> None:
    attempts = {"n": 0}
    slept: list[float] = []

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _FakeHTTPError(429)
        return "done"

    result = call_resilient(
        "p-flaky", flaky, deadline=_INF, sleep=slept.append, jitter=lambda: 0.0
    )
    assert result == "done"
    assert attempts["n"] == 3
    assert len(slept) == 2  # deux attentes entre trois tentatives


def test_honours_retry_after() -> None:
    slept: list[float] = []

    def always_429() -> str:
        raise _FakeHTTPError(429, {"retry-after": "5"})

    with pytest.raises(_FakeHTTPError):
        call_resilient(
            "p-ra", always_429, deadline=_INF, attempts=2, sleep=slept.append
        )
    assert slept == [5.0]  # le Retry-After serveur prime sur le backoff calculé


def test_gives_up_after_attempts() -> None:
    attempts = {"n": 0}

    def always_503() -> str:
        attempts["n"] += 1
        raise _FakeHTTPError(503)

    with pytest.raises(_FakeHTTPError):
        call_resilient(
            "p-503",
            always_503,
            deadline=_INF,
            attempts=4,
            sleep=lambda d: None,
            jitter=lambda: 0.0,
        )
    assert attempts["n"] == 4  # épuise les tentatives puis relance la dernière


def test_does_not_retry_non_retryable() -> None:
    attempts = {"n": 0}

    def bad_request() -> str:
        attempts["n"] += 1
        raise _FakeHTTPError(400)

    with pytest.raises(_FakeHTTPError):
        call_resilient("p-400", bad_request, deadline=_INF, sleep=lambda d: None)
    assert attempts["n"] == 1  # 4xx → échec immédiat, pas de retry


# --- cap de concurrence (network_slot) ------------------------------------


def test_slot_caps_concurrency_per_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINOC_NETWORK_CONCURRENCY", "2")
    provider = "test-cap-2"  # nom frais : plafond figé à 2 à la création
    active = 0
    peak = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal active, peak
        with network_slot(provider):
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak <= 2  # jamais plus de 2 appels simultanés malgré 6 threads


def test_invalid_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINOC_NETWORK_CONCURRENCY", "pas-un-entier")
    # Ne lève pas : nom frais → plafond défaut (3), au moins 1 détenteur possible.
    with network_slot("test-bad-env"):
        assert True


# --- bornes : deadline, annulation, transport (P5f 7, S20) ----------------


def test_the_deadline_is_required() -> None:
    """Aucun appelant ne passait de deadline : elle est désormais exigée."""
    with pytest.raises(TypeError):
        call_resilient("p-req", lambda: "ok")  # type: ignore[call-arg]


def test_an_expired_deadline_stops_before_any_attempt() -> None:
    calls: list[int] = []
    with pytest.raises(DeadlineExceeded):
        call_resilient(
            "p-exp", lambda: calls.append(1), deadline=Deadline.at_monotonic(0.0)
        )
    assert calls == []


def test_a_wait_longer_than_the_deadline_is_not_slept() -> None:
    """Un ``Retry-After`` de 30 s sous un délai restant de 5 s : on ne dort pas
    pour une tentative qui ne pourrait pas aboutir — l'unité s'arrête au délai,
    en nommant la dernière erreur."""
    slept: list[float] = []

    def throttled() -> str:
        raise _FakeHTTPError(429, {"retry-after": "30"})

    with pytest.raises(DeadlineExceeded, match="_FakeHTTPError"):
        call_resilient(
            "p-wait", throttled, deadline=Deadline.in_seconds(5), sleep=slept.append
        )
    assert slept == []


def test_a_failure_after_the_deadline_is_a_deadline() -> None:
    """Un délai de SDK qui se déclenche parce qu'on lui a passé le temps
    restant est la deadline, pas une panne du moteur."""
    deadline = Deadline.in_seconds(0.01)

    def slow() -> str:
        time.sleep(0.03)
        raise TimeoutError("lecture trop longue")

    with pytest.raises(DeadlineExceeded):
        call_resilient("p-slow", slow, deadline=deadline)


def test_cancellation_stops_the_retries() -> None:
    control = RunControl()
    calls: list[int] = []

    def throttled() -> str:
        calls.append(1)
        control.trigger_cancel()
        raise _FakeHTTPError(503)

    with pytest.raises(RunCancelledError):
        call_resilient(
            "p-cancel", throttled, deadline=_INF, control=control, jitter=lambda: 0.0
        )
    assert calls == [1]


def test_the_wait_between_attempts_is_interrupted_by_cancellation() -> None:
    """L'attente se fait sur l'annulation : un arrêt demandé pendant un backoff
    de 30 s n'attend pas 30 s."""
    control = RunControl()

    def throttled() -> str:
        raise _FakeHTTPError(429, {"retry-after": "30"})

    threading.Timer(0.05, control.trigger_cancel).start()
    started = time.monotonic()
    with pytest.raises(RunCancelledError):
        call_resilient("p-int", throttled, deadline=_INF, control=control)
    assert time.monotonic() - started < 5.0


def test_a_busy_slot_does_not_outlive_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sous contention (tous les créneaux pris), l'attente d'un créneau est
    bornée par la deadline au lieu de bloquer sans fin."""
    monkeypatch.setenv("CINOC_NETWORK_CONCURRENCY", "1")
    provider = "test-busy-1"
    slot = network_slot(provider)
    slot.acquire()
    try:
        with pytest.raises(DeadlineExceeded, match="créneau"):
            call_resilient(provider, lambda: "ok", deadline=Deadline.in_seconds(0.05))
    finally:
        slot.release()


def test_a_unit_waiting_for_a_slot_makes_no_call_once_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """« Arrêter » pendant qu'une unité attend son créneau réseau : quand le
    créneau se libère, elle **n'appelle pas** — un appel facturé lancé après
    l'arrêt est exactement ce que le bouton doit empêcher (D-299, trouvé au
    navigateur : la seconde page d'un VLM Ollama partait après l'arrêt)."""
    monkeypatch.setenv("CINOC_NETWORK_CONCURRENCY", "1")
    provider = "test-stop-waiting"
    slot = network_slot(provider)
    slot.acquire()
    control = RunControl()
    appels: list[str] = []
    issue: list[BaseException] = []

    def unite() -> None:
        try:
            call_resilient(
                provider,
                lambda: appels.append("appel") or "ok",
                deadline=Deadline.in_seconds(10.0),
                control=control,
            )
        except BaseException as exc:  # noqa: BLE001 -- constaté par le test
            issue.append(exc)

    fil = threading.Thread(target=unite)
    fil.start()
    time.sleep(0.05)
    control.trigger_cancel()
    slot.release()
    fil.join(5.0)
    assert appels == []
    assert len(issue) == 1 and isinstance(issue[0], RunCancelledError)
    # Le créneau rendu : une autre unité peut le prendre.
    assert slot.acquire(timeout=0.5)
    slot.release()


def test_transport_errors_are_transient() -> None:
    import httpx

    assert is_transient(httpx.ReadError("coupée"))
    assert is_transient(httpx.ConnectError("refusée"))
    assert is_transient(_FakeHTTPError(503))
    assert not is_transient(_FakeHTTPError(400))
    assert not is_transient(ValueError("bug local"))

    class APIConnectionError(Exception):  # forme d'openai / anthropic
        pass

    class APITimeoutError(APIConnectionError):
        pass

    assert is_transient(APITimeoutError("délai"))


def test_the_meter_counts_what_may_have_been_billed() -> None:
    """Règle : un succès compte ; un refus HTTP (429, 5xx) non — le service a
    répondu qu'il ne traitait pas ; une connexion refusée non — rien n'est
    parti ; une lecture coupée oui — la requête a pu être traitée."""
    import httpx

    replies: list[Exception | str] = [
        _FakeHTTPError(429),
        httpx.ConnectError("refusée"),
        httpx.ReadError("coupée"),
        "ok",
    ]

    def call() -> str:
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    meter = BillingMeter()
    assert (
        call_resilient(
            "p-meter", call, deadline=_INF, meter=meter, sleep=lambda d: None
        )
        == "ok"
    )
    assert meter.pages == 2


def test_step_deadline_is_the_nearest() -> None:
    near = step_deadline(Deadline.infinite(), 30.0)
    remaining = near.remaining_seconds()
    assert remaining is not None and 29.0 < remaining <= 30.0
    run = Deadline.in_seconds(5)
    assert step_deadline(run, 30.0) is run
