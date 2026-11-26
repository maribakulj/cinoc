from __future__ import annotations

import pickle

import pytest
from pydantic import BaseModel

from cinoc.domain import Deadline
from cinoc.domain.errors import CinocError

# ``in_seconds(b)`` stocke ``monotonic() + b`` (un grand flottant) ; le calcul
# de ``remaining = (monotonic() + b) - monotonic()`` peut, par arrondi du flottant,
# rendre une valeur dépassant ``b`` de quelques epsilon (observé ~6e-14 sous Windows).
# On tolère cette marge sur la borne haute — l'invariant testé reste « positif et
# ~= budget », pas l'égalité exacte au bit près.
_CLOCK_EPS = 1e-6


def test_infinite():
    d = Deadline.infinite()
    assert d.is_infinite
    assert d.remaining_seconds() is None
    assert not d.is_expired()


def test_in_seconds_positive():
    d = Deadline.in_seconds(10)
    remaining = d.remaining_seconds()
    assert remaining is not None and 0 < remaining <= 10 + _CLOCK_EPS
    assert not d.is_expired()


def test_in_seconds_rejects_nonpositive():
    with pytest.raises(CinocError):
        Deadline.in_seconds(0)


def test_expired():
    d = Deadline.at_monotonic(0.0)
    assert d.is_expired()
    assert d.remaining_seconds() == 0.0


def test_immutable():
    d = Deadline.infinite()
    with pytest.raises(AttributeError):
        d._expires_at_monotonic = 1.0  # type: ignore[misc]


def test_roundtrip_dict_infinite():
    assert Deadline.from_dict(Deadline.infinite().to_dict()).is_infinite


def test_roundtrip_dict_finite():
    d = Deadline.from_dict(Deadline.in_seconds(30).to_dict())
    remaining = d.remaining_seconds()
    assert remaining is not None and 0 < remaining <= 30 + _CLOCK_EPS


def test_pickle():
    d = pickle.loads(pickle.dumps(Deadline.in_seconds(30)))
    remaining = d.remaining_seconds()
    assert remaining is not None and 0 < remaining <= 30 + _CLOCK_EPS


def test_pydantic_field():
    class M(BaseModel):
        dl: Deadline

    m = M(dl=Deadline.infinite())
    assert m.model_dump()["dl"] == {"remaining_seconds": None}
    m2 = M.model_validate({"dl": {"remaining_seconds": None}})
    assert m2.dl.is_infinite


def test_in_seconds_never_exceeds_its_budget_when_the_clock_has_not_ticked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Horloge figée (Windows : ``monotonic()`` peut rendre deux fois la même
    valeur) sur un instant où ``(t + 30) - t`` arrondit **au-dessus** de 30 :
    le temps restant ne dépasse pas pour autant le budget donné."""
    frozen = 8191.610680565681
    assert (frozen + 30.0) - frozen > 30.0  # l'arrondi qui faisait rougir la CI
    monkeypatch.setattr("cinoc.domain.deadline.time.monotonic", lambda: frozen)
    remaining = Deadline.in_seconds(30.0).remaining_seconds()
    assert remaining is not None and 0 < remaining <= 30.0
