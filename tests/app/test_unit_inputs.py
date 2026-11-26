"""Fichiers d'entrée d'une unité : leur **contenu** entre dans la clé de reprise.

Une brique ``precomputed`` ne lit pas l'image : elle lit ``<stem>.<label>.txt``
posé à côté. Tant que la clé d'unité ne hachait que l'image, une sortie
pré-calculée **corrigée** sous la même image était resservie périmée par le
cache — et une archive re-notée hors ligne rendait l'ancienne lecture.

Le module déclare ces fichiers par un hook facultatif (``unit_inputs``), comme
``system_binaries``/``effective_settings`` ; la clé hache leur contenu, ou le
marqueur « absent » (apparaître ou disparaître invalide aussi).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout.alto_source import AltoLayoutSource
from cinoc.adapters.layout.precomputed import (
    PrecomputedLayoutSource,
    PrecomputedRegionRecognizer,
)
from cinoc.adapters.ocr.precomputed import PrecomputedTextAdapter
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.orchestrator import ArchiveIncompleteError, run
from cinoc.app.resume import ResumeStore
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.result import RunResult

_ADAPTER = "precomputed:ocr"


def _spec(folder: Path) -> RunSpec:
    image = folder / "d1.png"
    image.write_bytes(b"\x89PNG page d1")
    gt = folder / "d1.gt.txt"
    gt.write_text("abcd", encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="d1",
                image_uri=str(image),
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            ),
        ),
    )
    pipeline = PipelineSpec(
        name="p",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr",
                kind="ocr",
                adapter_name=_ADAPTER,
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
        ),
    )
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    return RunSpec(
        corpus=corpus,
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=(view,)),
        adapter_kwargs={_ADAPTER: {"source_label": "ocr"}},
        run_id="unit-inputs",
    )


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def _cer(result: RunResult) -> float | None:
    (score,) = (
        s for p in result.pipelines for s in p.aggregate if s.metric == "cer"
    )
    return score.value


def _run(spec: RunSpec, store: ResumeStore, *, offline: bool = False) -> RunResult:
    return run(
        spec,
        registry=_registry(),
        code_version="1.0",
        resume_store=store,
        offline=offline,
    )


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Compte les exécutions réelles de la brique pré-calculée."""
    seen: list[str] = []
    original = PrecomputedTextAdapter.execute

    def counted(self, inputs, params, context, control):  # noqa: ANN001, ANN202
        seen.append(context.document_id)
        return original(self, inputs, params, context, control)

    monkeypatch.setattr(PrecomputedTextAdapter, "execute", counted)
    return seen


def test_a_rewritten_precomputed_output_is_reexecuted_and_rescored(
    tmp_path: Path, calls: list[str]
) -> None:
    """Le défaut d'origine : sortie corrigée sous la même image → CER inchangé."""
    spec = _spec(tmp_path)
    store = ResumeStore(tmp_path / "archive")
    (tmp_path / "d1.ocr.txt").write_text("abcx", encoding="utf-8")
    assert _cer(_run(spec, store)) == pytest.approx(0.25)
    (tmp_path / "d1.ocr.txt").write_text("abcd", encoding="utf-8")
    assert _cer(_run(spec, store)) == 0.0
    assert calls == ["d1", "d1"]


def test_an_unchanged_precomputed_output_is_served_from_the_archive(
    tmp_path: Path, calls: list[str]
) -> None:
    spec = _spec(tmp_path)
    store = ResumeStore(tmp_path / "archive")
    (tmp_path / "d1.ocr.txt").write_text("abcx", encoding="utf-8")
    first = _run(spec, store)
    second = _run(spec, store)
    offline = _run(spec, store, offline=True)
    assert calls == ["d1"]
    assert _cer(first) == _cer(second) == _cer(offline) == pytest.approx(0.25)


def test_offline_refuses_a_unit_whose_input_file_changed(
    tmp_path: Path, calls: list[str]
) -> None:
    spec = _spec(tmp_path)
    store = ResumeStore(tmp_path / "archive")
    (tmp_path / "d1.ocr.txt").write_text("abcx", encoding="utf-8")
    _run(spec, store)
    (tmp_path / "d1.ocr.txt").write_text("abcd", encoding="utf-8")
    with pytest.raises(ArchiveIncompleteError) as refused:
        _run(spec, store, offline=True)
    message = str(refused.value)
    assert "p × d1" in message
    assert "fichier d'entrée" in message
    assert "Rien n'a été exécuté" in message
    assert calls == ["d1"]


def test_an_input_file_that_disappears_or_appears_invalidates_the_unit(
    tmp_path: Path, calls: list[str]
) -> None:
    spec = _spec(tmp_path)
    store = ResumeStore(tmp_path / "archive")
    text = tmp_path / "d1.ocr.txt"
    text.write_text("abcx", encoding="utf-8")
    _run(spec, store)
    text.unlink()
    with pytest.raises(ArchiveIncompleteError):
        _run(spec, store, offline=True)
    # Absente, l'unité échoue et l'échec est archivé sous la clé « absent » ;
    # hors ligne, il est restitué tel quel…
    failed = _run(spec, store)
    assert failed.usage[0].outcome == "failed"
    assert _run(spec, store, offline=True).usage[0].outcome == "failed"
    # … jusqu'à ce que le fichier réapparaisse : l'échec ne vaut plus.
    text.write_text("abcd", encoding="utf-8")
    with pytest.raises(ArchiveIncompleteError):
        _run(spec, store, offline=True)
    assert _cer(_run(spec, store)) == 0.0


# --------------------------------------------------------------------------- #
# Chaque brique qui lit un voisin de l'image le déclare
# --------------------------------------------------------------------------- #


def _document(folder: Path) -> DocumentRef:
    image = folder / "page.png"
    image.write_bytes(b"png")
    return DocumentRef(id="page", image_uri=str(image))


def test_precomputed_bricks_declare_the_file_they_read(tmp_path: Path) -> None:
    document = _document(tmp_path)
    assert PrecomputedTextAdapter(source_label="ocr").unit_inputs(document) == (
        tmp_path / "page.ocr.txt",
    )
    assert PrecomputedLayoutSource().unit_inputs(document) == (
        tmp_path / "page.layout.json",
    )
    assert PrecomputedRegionRecognizer(source_label="r").unit_inputs(document) == (
        tmp_path / "page.r.regions.json",
    )


def test_alto_source_declares_every_candidate_and_its_ocr_sidecar(
    tmp_path: Path,
) -> None:
    """Les deux emplacements tentés : qu'un ``.xml`` apparaisse là où seul
    ``.alto.xml`` existait change la lecture, donc la clé."""
    document = _document(tmp_path)
    assert AltoLayoutSource().unit_inputs(document) == (
        tmp_path / "page.xml",
        tmp_path / "page.alto.xml",
    )
    sidecar = tmp_path / "ocr.json"
    assert AltoLayoutSource(ocr_sidecar=str(sidecar)).unit_inputs(document) == (
        tmp_path / "page.xml",
        tmp_path / "page.alto.xml",
        sidecar,
    )


def test_a_document_without_image_declares_nothing() -> None:
    document = DocumentRef(id="sans-image")
    assert PrecomputedTextAdapter(source_label="ocr").unit_inputs(document) == ()
    assert AltoLayoutSource().unit_inputs(document) == ()
