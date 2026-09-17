"""Un module tiers installé doit se voir — et un module cassé, se diagnostiquer.

Le catalogue des moteurs est écrit à la main : il ne pouvait pas montrer ce qui
est **découvert**. Un plugin installé était donc indiscernable d'un plugin
absent, et un plugin cassé n'existait que dans le journal.
"""

from __future__ import annotations

from cinoc.app.engines import third_party_statuses
from cinoc.app.modules.discovery import inspect_plugins


class _EntryPoint:
    def __init__(self, name: str, value: str, charge: object) -> None:
        self.name = name
        self.value = value
        self._charge = charge

    def load(self) -> object:
        if isinstance(self._charge, Exception):
            raise self._charge
        return self._charge


def _loader(*entrées: _EntryPoint):
    return lambda: entrées


def test_un_module_valide_est_rapporte_pret() -> None:
    rapports = inspect_plugins(
        _loader(_EntryPoint("seg", "p.m:build", lambda kw: None))
    )
    assert len(rapports) == 1
    assert rapports[0].ok
    assert rapports[0].source == "p.m:build"
    assert rapports[0].reason is None


def test_un_module_qui_leve_porte_la_raison() -> None:
    rapports = inspect_plugins(
        _loader(_EntryPoint("seg", "p.m:build", ImportError("torch absent")))
    )
    assert not rapports[0].ok
    assert "torch absent" in (rapports[0].reason or "")


def test_un_builder_non_appelable_est_refuse() -> None:
    rapports = inspect_plugins(_loader(_EntryPoint("seg", "p.m:X", 42)))
    assert not rapports[0].ok
    assert "appelable" in (rapports[0].reason or "")


def test_le_catalogue_montre_le_module_et_sa_cause() -> None:
    statuts = third_party_statuses(
        entry_points_loader=_loader(
            _EntryPoint("bon", "p.m:build", lambda kw: None),
            _EntryPoint("cassé", "p.m:autre", ImportError("onnxruntime absent")),
        )
    )
    par_kind = {s.kind: s for s in statuts}
    assert par_kind["bon"].available
    assert not par_kind["cassé"].available
    # La cause est lisible dans le catalogue, pas seulement dans le journal.
    assert "onnxruntime absent" in par_kind["cassé"].detail


def test_mode_public_ne_revele_aucun_module_tiers() -> None:
    """Même règle que la découverte : fail-closed sur un serveur exposé."""
    assert (
        third_party_statuses(
            enabled=False,
            entry_points_loader=_loader(
                _EntryPoint("seg", "p.m:build", lambda kw: None)
            ),
        )
        == ()
    )
