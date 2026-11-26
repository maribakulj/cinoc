"""``Deadline`` — type valeur représentant une échéance d'opération.

Contrat de timeout propagé aux adapters via le contexte d'exécution.
Permet à chaque adapter de respecter coopérativement un budget temps par
document (passage du timeout au SDK, check entre opérations bloquantes,
levée de ``DeadlineExceeded`` à expiration).

Une ``Deadline`` est soit infinie (aucune contrainte), soit finie avec
une expiration absolue dans l'horloge monotonic du process courant.
L'horloge monotonic ne recule jamais mais a une origine privée au
process : la sérialisation convertit donc vers ``remaining_seconds`` au
moment du transfert, et une nouvelle ``Deadline`` est reconstruite
relativement à l'horloge du process receveur.
"""

from __future__ import annotations

import math
import time
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

from cinoc.domain.errors import CinocError


class Deadline:
    """Type valeur immuable représentant une échéance d'opération."""

    _expires_at_monotonic: float | None
    __slots__ = ("_expires_at_monotonic",)

    def __init__(self, expires_at_monotonic: float | None) -> None:
        if expires_at_monotonic is not None and not isinstance(
            expires_at_monotonic, (int, float),
        ):
            raise CinocError(
                "Deadline : expires_at_monotonic doit être float ou None, "
                f"reçu {type(expires_at_monotonic).__name__}",
            )
        object.__setattr__(
            self,
            "_expires_at_monotonic",
            float(expires_at_monotonic)
            if expires_at_monotonic is not None
            else None,
        )

    # ── Constructeurs ────────────────────────────────────────────────

    @classmethod
    def infinite(cls) -> Deadline:
        """Pas d'échéance — ``remaining_seconds()`` → ``None``,
        ``is_expired()`` → ``False``."""
        return cls(expires_at_monotonic=None)

    @classmethod
    def in_seconds(cls, budget: float) -> Deadline:
        """Échéance dans ``budget`` secondes (> 0) à partir de maintenant."""
        if not isinstance(budget, (int, float)):
            raise CinocError(
                "Deadline.in_seconds : budget doit être numérique, "
                f"reçu {type(budget).__name__}",
            )
        if budget <= 0:
            raise CinocError(
                f"Deadline.in_seconds : budget doit être > 0 (reçu {budget}). "
                "Pour une deadline déjà expirée en test, utiliser "
                "``Deadline.at_monotonic(0.0)``.",
            )
        now = time.monotonic()
        expires = now + float(budget)
        # ``(now + b) - now`` peut arrondir au-dessus de ``b`` : tant que
        # l'horloge n'a pas avancé (Windows rend volontiers deux fois la même
        # valeur), le temps restant dépasserait le budget. On recule
        # l'échéance d'un ulp jusqu'à ce que l'invariant tienne.
        while expires - now > budget:
            expires = math.nextafter(expires, -math.inf)
        return cls(expires_at_monotonic=expires)

    @classmethod
    def at_monotonic(cls, expires_at: float) -> Deadline:
        """Échéance à l'instant monotonic absolu ``expires_at`` (surtout
        utile en tests : ``at_monotonic(0.0)`` = déjà expirée)."""
        return cls(expires_at_monotonic=expires_at)

    # ── Interrogation ────────────────────────────────────────────────

    @property
    def is_infinite(self) -> bool:
        return self._expires_at_monotonic is None

    def remaining_seconds(self) -> float | None:
        """Secondes restantes, ou ``None`` si infinie. Jamais négatif."""
        if self._expires_at_monotonic is None:
            return None
        return max(0.0, self._expires_at_monotonic - time.monotonic())

    def is_expired(self) -> bool:
        if self._expires_at_monotonic is None:
            return False
        return time.monotonic() >= self._expires_at_monotonic

    def clamp_to_remaining(self, seconds: float) -> float:
        """Retourne ``min(seconds, remaining_seconds())``.

        Si infinie, retourne ``seconds`` tel quel. Utile pour borner le
        backoff d'un retry qui ne doit pas dépasser le budget restant.
        """
        if seconds < 0:
            raise CinocError(
                f"Deadline.clamp_to_remaining : seconds doit être >= 0 "
                f"(reçu {seconds})",
            )
        if self._expires_at_monotonic is None:
            return seconds
        remaining = self.remaining_seconds()
        assert remaining is not None
        return min(seconds, remaining)

    # ── Sérialisation cross-process ──────────────────────────────────
    #
    # ``expires_at_monotonic`` n'a aucun sens dans un autre process. On
    # sérialise via ``remaining_seconds`` (transposable) ; à la réception,
    # on reconstruit relativement à l'horloge du process receveur.

    def to_dict(self) -> dict[str, float | None]:
        """Forme sérialisable JSON / IPC : ``{"remaining_seconds": …}``.
        ``None`` = infinie."""
        return {"remaining_seconds": self.remaining_seconds()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Deadline:
        """Reconstruit une ``Deadline`` depuis sa forme sérialisée."""
        if not isinstance(data, dict):
            raise CinocError(
                f"Deadline.from_dict : data doit être un dict, "
                f"reçu {type(data).__name__}",
            )
        if "remaining_seconds" not in data:
            raise CinocError(
                "Deadline.from_dict : clé 'remaining_seconds' manquante.",
            )
        r = data["remaining_seconds"]
        if r is None:
            return cls.infinite()
        if not isinstance(r, (int, float)):
            raise CinocError(
                "Deadline.from_dict : remaining_seconds doit être numérique "
                f"ou None, reçu {type(r).__name__}",
            )
        if r <= 0:
            # Reçue déjà expirée côté émetteur → on reconstruit expirée.
            return cls.at_monotonic(time.monotonic())
        return cls.in_seconds(float(r))

    def __getstate__(self) -> dict[str, float | None]:
        return self.to_dict()

    def __setstate__(self, state: dict[str, float | None]) -> None:
        r = state.get("remaining_seconds")
        if r is None:
            object.__setattr__(self, "_expires_at_monotonic", None)
        elif r <= 0:
            object.__setattr__(self, "_expires_at_monotonic", time.monotonic())
        else:
            object.__setattr__(
                self, "_expires_at_monotonic", time.monotonic() + float(r),
            )

    # ── Dunder — immutabilité, égalité, repr ─────────────────────────

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            f"Deadline est immuable — impossible d'assigner {name!r}",
        )

    def __delattr__(self, name: str) -> None:
        raise AttributeError(
            f"Deadline est immuable — impossible de supprimer {name!r}",
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Deadline):
            return NotImplemented
        # Égalité stricte sur l'instant d'expiration : deux
        # ``in_seconds(60)`` créées à des instants différents ne sont PAS
        # égales (l'égalité sur ``remaining_seconds`` serait instable).
        return self._expires_at_monotonic == other._expires_at_monotonic

    def __hash__(self) -> int:
        return hash(self._expires_at_monotonic)

    def __repr__(self) -> str:
        if self._expires_at_monotonic is None:
            return "Deadline.infinite()"
        remaining = self.remaining_seconds()
        if remaining is None or remaining <= 0.0:
            return "Deadline(expired)"
        return f"Deadline(remaining={remaining:.3f}s)"

    # ── Compat Pydantic (utilisable comme type de champ) ─────────────

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,  # noqa: ARG003
        handler: GetCoreSchemaHandler,  # noqa: ARG003
    ) -> core_schema.CoreSchema:
        """Validation : instance ``Deadline`` (pass-through) ou dict
        ``{"remaining_seconds": …}``. Sérialisation : ``to_dict()``."""

        def _validate(value: Any) -> Deadline:
            if isinstance(value, cls):
                return value
            if isinstance(value, dict):
                return cls.from_dict(value)
            raise ValueError(
                "Deadline : impossible de valider une valeur de type "
                f"{type(value).__name__} (attendu Deadline ou dict).",
            )

        return core_schema.no_info_plain_validator_function(
            _validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda d: d.to_dict(),
            ),
        )


__all__ = ["Deadline"]
