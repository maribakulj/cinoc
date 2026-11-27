"""L'archive garde chaque unité **dès qu'elle se termine**, écrite d'un coup.

Trouvé à l'essai de S31 : l'archive n'était écrite qu'après la dernière unité.
Un run coupé (Ctrl-C, machine perdue, délai de session) perdait tout ce qu'il
avait déjà produit — et, sur une API facturée, payé : la reprise rejouait et
repayait. Une unité doit donc être archivée à sa fin, et l'être **atomiquement**
(sous un nom temporaire, puis renommée) : une écriture coupée ne laisse jamais,
sous le nom qui fait foi, une unité à moitié réécrite.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cinoc.app.modules.registry import ModuleRegistry
from cinoc.app.orchestrator import run
from cinoc.app.resume import ResumeStore
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.pipeline.types import StepOutput


class _Coupure(BaseException):
    """Ce qu'aucun moteur ne rattrape : l'interruption du processus."""


class _OCR:
    """Écrit un texte fixe ; coupe le run au document ``stop``."""

    name = "coupe:eng"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def __init__(self, calls: list[str], stop: str | None) -> None:
        self._calls = calls
        self._stop = stop

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        self._calls.append(context.document_id)
        if context.document_id == self._stop:
            raise _Coupure
        path = Path(context.workspace_uri) / f"{context.document_id}.txt"
        path.write_text("abcd", encoding="utf-8")
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:coupe:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(path),
                    content_hash=compute_content_hash(b"abcd"),
                )
            }
        )


def _spec(tmp_path: Path) -> RunSpec:
    documents = []
    for doc_id in ("d1", "d2"):
        image = tmp_path / f"{doc_id}.png"
        image.write_bytes(b"\x89PNG " + doc_id.encode())
        gt = tmp_path / f"{doc_id}.gt.txt"
        gt.write_text("abcd", encoding="utf-8")
        documents.append(
            DocumentRef(
                id=doc_id,
                image_uri=str(image),
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            )
        )
    pipeline = PipelineSpec(
        name="p",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr",
                kind="ocr",
                adapter_name="coupe:eng",
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
        corpus=CorpusSpec(name="c", documents=tuple(documents)),
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=(view,)),
        run_id="incremental",
    )


def _registry(calls: list[str], stop: str | None = None) -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register_builder("coupe", lambda kwargs: _OCR(calls, stop))
    return registry


def _units(base: Path) -> list[Path]:
    return sorted(p for p in base.iterdir() if (p / "index.json").is_file())


def test_a_unit_finished_before_the_run_is_cut_is_not_paid_twice(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    archive = tmp_path / "archive"
    spec = _spec(tmp_path)
    with pytest.raises(_Coupure):
        run(
            spec,
            registry=_registry(calls, stop="d2"),
            code_version="1.0",
            resume_store=ResumeStore(archive),
            max_workers=1,
        )
    assert calls == ["d1", "d2"]
    assert len(_units(archive)) == 1  # d1, archivée avant la coupure
    # Les binaires aussi : sans eux, la relecture hors ligne ne retrouverait
    # pas la clé de l'unité gardée.
    assert (archive / "binaries.json").is_file()

    run(
        spec,
        registry=_registry(calls),
        code_version="1.0",
        resume_store=ResumeStore(archive),
        max_workers=1,
    )
    assert calls == ["d1", "d2", "d2"]  # d1 relue, pas rejouée


def test_the_archive_is_the_same_as_when_written_at_the_end(tmp_path: Path) -> None:
    """Même contenu, unité par unité, qu'un run qui va jusqu'au bout."""
    archive = tmp_path / "archive"
    run(
        _spec(tmp_path),
        registry=_registry([]),
        code_version="1.0",
        resume_store=ResumeStore(archive),
        max_workers=2,
    )
    units = _units(archive)
    assert len(units) == 2
    assert not [p for p in archive.iterdir() if p.name.startswith(".")]
    for unit in units:
        index = json.loads((unit / "index.json").read_text(encoding="utf-8"))
        assert index["outcome"] == "ok"
        assert (unit / "ocr.raw_text.txt").read_text(encoding="utf-8") == "abcd"


def test_a_cut_rewrite_leaves_the_previous_unit_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une unité réécrite (un échec retenté, une unité refaite) : si l'écriture
    est coupée, l'archive garde l'ancienne entière — jamais un mélange de
    l'ancien index et de nouveaux fichiers à moitié copiés."""
    archive = tmp_path / "archive"
    spec = _spec(tmp_path)
    run(
        spec,
        registry=_registry([]),
        code_version="1.0",
        resume_store=ResumeStore(archive),
    )
    before = {
        unit.name: {f.name: f.read_bytes() for f in unit.iterdir()}
        for unit in _units(archive)
    }
    for unit in _units(archive):
        (unit / "ocr.raw_text.txt").write_text("ancien", encoding="utf-8")
        before[unit.name]["ocr.raw_text.txt"] = b"ancien"
        # L'index nomme une unité « en échec » : une reprise normale la retente.
        index = json.loads((unit / "index.json").read_text(encoding="utf-8"))
        index["outcome"] = "failed"
        index["reason"] = "adapter"
        index["message"] = "échec simulé"
        (unit / "index.json").write_text(json.dumps(index), encoding="utf-8")
        before[unit.name]["index.json"] = (unit / "index.json").read_bytes()

    real_copy = shutil.copyfile

    def coupee(src, dst, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        real_copy(src, dst, *args, **kwargs)
        raise _Coupure

    monkeypatch.setattr(shutil, "copyfile", coupee)
    with pytest.raises(_Coupure):
        run(
            spec,
            registry=_registry([]),
            code_version="1.0",
            resume_store=ResumeStore(archive),
            max_workers=1,
        )
    after = {
        unit.name: {f.name: f.read_bytes() for f in unit.iterdir()}
        for unit in _units(archive)
    }
    assert after == before
