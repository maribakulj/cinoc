"""Découverte de modules de pipeline **tiers** via entry-points (couche 6).

Le **seul** point d'extension tiers du produit (CLAUDE.md §3) : un paquet pip
déclare ::

    [project.entry-points."cinoc.modules"]
    yolo_seg = "mon_paquet.seg:build_yolo"

Chaque entrée nomme un ``kind`` (``yolo_seg``) et charge un ``ModuleBuilder``
(``build_yolo``), enregistré dans le ``ModuleRegistry`` runtime — **exactement**
comme le socle (``register_default_modules``), même ``Module`` Protocol, seule la
source diffère. Un YOLO de segmentation se branche ainsi **sans forker** : c'est
un ``Module`` ``IMAGE → LAYOUT`` que le fan-out consomme comme les autres.

``inspect_plugins`` est la même mécanique sans effet de bord : elle sert au
catalogue (``cinoc list engines``), qui doit montrer les modules tiers — et
surtout ceux qui **échouent**, jusqu'ici invisibles hors du journal.

**Sécurité** : le code tiers s'exécute **in-process**. En **mode public** la
découverte est **désactivée (fail-closed)** — jamais de chargement de code
arbitraire sur un serveur exposé. Un plugin défectueux est **journalisé et
ignoré**, il n'abat pas le démarrage.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from cinoc.app.modules.registry import ModuleBuilder, ModuleRegistry

logger = logging.getLogger(__name__)

#: Groupe d'entry-points scanné pour les modules de pipeline tiers.
ENTRY_POINT_GROUP = "cinoc.modules"


class _EntryPoint(Protocol):
    """Forme minimale consommée d'un entry-point (``importlib.metadata``)."""

    @property
    def name(self) -> str: ...

    def load(self) -> object: ...


#: Fournit les entry-points du groupe — injectable pour les tests.
EntryPointsLoader = Callable[[], Iterable[_EntryPoint]]


def _default_entry_points() -> Iterable[_EntryPoint]:
    from importlib.metadata import entry_points

    return entry_points(group=ENTRY_POINT_GROUP)


@dataclass(frozen=True)
class PluginReport:
    """Ce qu'un entry-point tiers a donné : son builder, ou la raison du refus.

    ``builder`` et ``reason`` sont exclusifs. La **raison** existe pour être
    montrée : un plugin installé mais inutilisable est le cas qu'un utilisateur
    doit pouvoir diagnostiquer sans lire un journal.
    """

    name: str
    source: str
    builder: ModuleBuilder | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.builder is not None


def inspect_plugins(
    entry_points_loader: EntryPointsLoader | None = None,
) -> tuple[PluginReport, ...]:
    """Charge chaque entry-point du groupe et dit ce qu'il a donné.

    Séparé de l'enregistrement pour que le **catalogue** (``cinoc list
    engines``) montre les modules tiers sans avoir à en enregistrer, et surtout
    pour qu'il montre ceux qui **échouent** — invisibles jusqu'ici, puisque
    ``discover_plugins`` se contente de les journaliser.
    """
    loader = entry_points_loader or _default_entry_points
    reports: list[PluginReport] = []
    for entry_point in loader():
        source = getattr(entry_point, "value", "?")
        try:
            builder = entry_point.load()
        except Exception as exc:  # le code tiers peut lever n'importe quoi
            reports.append(
                PluginReport(name=entry_point.name, source=source, reason=str(exc))
            )
            continue
        if not callable(builder):
            reports.append(
                PluginReport(
                    name=entry_point.name,
                    source=source,
                    reason=f"{type(builder).__name__} n'est pas un builder appelable",
                )
            )
            continue
        reports.append(
            PluginReport(name=entry_point.name, source=source, builder=builder)
        )
    return tuple(reports)


def discover_plugins(
    registry: ModuleRegistry,
    *,
    enabled: bool,
    entry_points_loader: EntryPointsLoader | None = None,
) -> tuple[str, ...]:
    """Enregistre les builders tiers du groupe ``cinoc.modules`` dans ``registry``.

    Renvoie les ``kind`` découverts (ordre de découverte). ``enabled=False``
    (mode public) → aucune découverte. Un entry-point qui échoue à charger, ou
    qui ne fournit pas un builder appelable, est **journalisé et sauté**.
    """
    if not enabled:
        logger.info("[plugins] découverte désactivée (mode public, fail-closed)")
        return ()
    discovered: list[str] = []
    for report in inspect_plugins(entry_points_loader):
        if report.builder is None:
            logger.warning(
                "[plugins] entry-point %r ignoré : %s", report.name, report.reason
            )
            continue
        registry.register_builder(report.name, report.builder)
        discovered.append(report.name)
        logger.info("[plugins] module tiers enregistré : %r", report.name)
    return tuple(discovered)


__all__ = [
    "ENTRY_POINT_GROUP",
    "EntryPointsLoader",
    "PluginReport",
    "discover_plugins",
    "inspect_plugins",
]
