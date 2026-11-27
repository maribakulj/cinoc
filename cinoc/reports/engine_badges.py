"""Badges moteur A→E (couche 7) — **source unique** lettre + accent cyclique.

Chaque moteur (nom de pipeline) reçoit une **lettre** (A, B, C…) et un **accent**
cyclique (fern/slate/clay/butter/ink). C'est une **identité visuelle stable** : le
moteur « A » est le même dans *toutes* les sections (classement, par-document,
crosses), indépendamment de son rang d'affichage. **Toute extension de la palette
se fait ICI** (les sections consomment ``engine_cell`` ; aucune ne recopie la
palette — anti-divergence : un seul point de vérité pour la palette).

Déterministe : l'index vient de l'**ordre de première apparition** des pipelines
dans le ``RunResult`` (``engine_order``), donc le badge est octet-stable.
"""

from __future__ import annotations

from collections.abc import Iterable

from cinoc.reports.html import escape
from cinoc.reports.section import Html

#: A→Z, puis cycle (au-delà de 26 moteurs — cas théorique).
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: Accents du design (oklch), cycliques. **Étendre la palette = modifier CECI.**
_ACCENTS: tuple[str, ...] = (
    "oklch(0.50 0.07 145)",  # fern
    "oklch(0.52 0.05 245)",  # slate
    "oklch(0.55 0.11 40)",  # clay
    "oklch(0.72 0.10 85)",  # butter
    "oklch(0.32 0.02 60)",  # ink
)


def engine_letter(index: int) -> str:
    """Lettre du moteur d'index ``index`` (A=0, B=1…) — cycle A→Z au-delà de 25."""
    return _LETTERS[index % len(_LETTERS)]


def engine_accent(index: int) -> str:
    """Accent CSS cyclique du moteur d'index ``index``."""
    return _ACCENTS[index % len(_ACCENTS)]


def engine_order(names: Iterable[str]) -> dict[str, int]:
    """Map nom→index dans l'**ordre de première apparition** (identité stable).

    À calculer **une fois** depuis ``result.pipelines`` et à partager entre
    sections : c'est ce qui garantit que « A » désigne le même moteur partout.
    """
    order: dict[str, int] = {}
    for name in names:
        if name not in order:
            order[name] = len(order)
    return order


def engine_cell(name: str, index: int, hint: str = "") -> Html:
    """Contenu d'une cellule moteur : **badge** (lettre + accent) + nom échappé.

    ``hint`` (``ocr.lang=fra``) : ce qui distingue la chaîne d'un homonyme
    (``composition_diff.homonym_hints``), écrit à côté du nom ; vide sinon."""
    note = f' <span class="eng-hint muted">{escape(hint)}</span>' if hint else ""
    return Html(
        f'<span class="eng-badge" style="--badge:{engine_accent(index)}">'
        f"{engine_letter(index)}</span>{escape(name)}{note}"
    )


__all__ = [
    "engine_accent",
    "engine_cell",
    "engine_letter",
    "engine_order",
]
