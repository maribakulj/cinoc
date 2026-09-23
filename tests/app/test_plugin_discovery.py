"""Découverte de modules tiers par entry-points (``cinoc.modules``).

Vérifie le **seul** point d'extension tiers : un builder tiers découvert et
enregistré comme le socle (même `Module` Protocol), le **fail-closed en mode
public**, la résilience (plugin cassé / non-builder ignoré), et qu'un segmenteur
tiers découvert **produit un LAYOUT** consommable par le fan-out — le cas d'usage
« brancher un YOLO sans forker ».
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import EntryPoint
from pathlib import Path

from cinoc.app.modules import ModuleRegistry, discover_plugins
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.layout import CanonicalLayout
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.fixtures.sample_segmenter_plugin import build_sample_segmenter


class _FakeEntryPoint:
    """Entry-point factice : ``name`` + ``load()`` (suffit à ``discover_plugins``)."""

    def __init__(self, name: str, loader: Callable[[], object]) -> None:
        self.name = name
        self._loader = loader

    def load(self) -> object:
        return self._loader()


def _loader(*eps: _FakeEntryPoint) -> Callable[[], list[_FakeEntryPoint]]:
    return lambda: list(eps)


def _sample_ep() -> _FakeEntryPoint:
    return _FakeEntryPoint("sample_seg", lambda: build_sample_segmenter)


def test_discovers_and_registers_third_party_builder() -> None:
    registry = ModuleRegistry()
    kinds = discover_plugins(
        registry,
        enabled=True,
        entry_points_loader=_loader(_sample_ep()),
    )
    assert kinds == ("sample_seg",)
    module = registry.build("sample_seg", {})
    assert isinstance(module, Module)
    assert module.output_types == frozenset({ArtifactType.LAYOUT})
    assert module.version == "9.9-demo"  # version tierce → captée au RunManifest


def test_public_mode_disables_discovery() -> None:
    registry = ModuleRegistry()
    kinds = discover_plugins(
        registry,
        enabled=False,
        entry_points_loader=_loader(_sample_ep()),
    )
    assert kinds == ()  # fail-closed : aucun code tiers chargé sur serveur exposé
    assert "sample_seg" not in registry.kinds()


def test_broken_plugin_is_skipped_others_load() -> None:
    def boom() -> object:
        raise RuntimeError("plugin cassé à l'import")

    registry = ModuleRegistry()
    kinds = discover_plugins(
        registry,
        enabled=True,
        entry_points_loader=_loader(
            _FakeEntryPoint("bad", boom),
            _FakeEntryPoint("sample_seg", lambda: build_sample_segmenter),
        ),
    )
    assert kinds == ("sample_seg",)  # le cassé est journalisé+ignoré, pas fatal


def test_non_callable_entry_point_is_skipped() -> None:
    registry = ModuleRegistry()
    kinds = discover_plugins(
        registry,
        enabled=True,
        entry_points_loader=_loader(_FakeEntryPoint("notbuilder", lambda: 42)),
    )
    assert kinds == ()


def test_real_entry_point_load_resolves_dotted_path() -> None:
    # Vrai importlib.metadata.EntryPoint : .load() fait la VRAIE résolution
    # dotted-path (≠ fake .load()), comme un paquet installé.
    entry_point = EntryPoint(
        name="sample_seg",
        value="tests.fixtures.sample_segmenter_plugin:build_sample_segmenter",
        group="cinoc.modules",
    )
    registry = ModuleRegistry()
    kinds = discover_plugins(
        registry, enabled=True, entry_points_loader=lambda: [entry_point]
    )
    assert kinds == ("sample_seg",)
    assert registry.build("sample_seg", {}).output_types == frozenset(
        {ArtifactType.LAYOUT}
    )


def test_default_loader_runs_clean() -> None:
    """Le vrai chemin ``importlib.metadata`` est branché et ne lève pas.

    Ce test affirmait ``== ()``. Il ne vérifiait donc le câblage qu'**en
    l'absence** de ce qu'il câble, et tombait dès qu'un module tiers était
    réellement installé — c'est-à-dire dans le cas d'usage supporté. Ce qui se
    vérifie ici est la **forme** du résultat : des ``kind`` enregistrés, quels
    qu'ils soient.
    """
    registry = ModuleRegistry()
    découverts = discover_plugins(registry, enabled=True)
    assert isinstance(découverts, tuple)
    assert all(isinstance(kind, str) and kind for kind in découverts)
    # Ce qui est découvert est enregistré : c'est tout le contrat.
    assert set(découverts) <= set(registry.kinds())


def test_discovered_segmenter_produces_layout(tmp_path: Path) -> None:
    registry = ModuleRegistry()
    discover_plugins(
        registry,
        enabled=True,
        entry_points_loader=_loader(_sample_ep()),
    )
    segmenter = registry.build("sample_seg", {})
    image = Artifact(
        id="d:img", document_id="d", type=ArtifactType.IMAGE, uri="mem://x"
    )
    context = RunContext(
        document_id="d", code_version="1.0", pipeline_name="p",
        workspace_uri=str(tmp_path),
    )
    outputs = segmenter.execute({ArtifactType.IMAGE: image}, {}, context, RunControl())
    layout = CanonicalLayout.model_validate_json(
        Path(outputs.artifacts[ArtifactType.LAYOUT].uri).read_bytes()
    )
    # Le segmenteur tiers a produit une mise en page → consommable par le fan-out.
    assert len(layout.pages[0].regions) == 2
