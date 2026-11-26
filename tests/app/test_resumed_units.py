"""D10 (pilote D-281) — une unité reprise de l'archive le dit.

Une unité relue de l'archive (``--resume-dir``) garde la durée — et les jetons —
de sa **première** exécution. Le pilote en a montré l'effet : 114,6 s mesurées
sous contention, reprises telles quelles, donnaient « 244,6 pages/h » contre
1 410 pour l'autre Tesseract, sans que rien ne le signale. Le ``RunResult`` dit
désormais, par unité, qu'elle est reprise (``DocumentUsage.resumed``) ;
l'économie compte les unités reprises, le CSV nomme leur durée.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry
from cinoc.app.resume import ResumeStore
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.analysis import EconomicsPayload
from cinoc.evaluation.result import RunResult
from cinoc.pipeline.types import StepOutput
from cinoc.reports.csv_export import run_result_csv

_DOCS = ("p1", "p2")


class _Ocr:
    name = "fakeocr:fra"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        path = Path(context.workspace_uri) / f"{context.document_id}.txt"
        path.write_text("le texte", encoding="utf-8")
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:fakeocr:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(path),
                    content_hash=compute_content_hash(b"le texte"),
                )
            }
        )


def _spec(folder: Path, docs: tuple[str, ...]) -> RunSpec:
    folder.mkdir(parents=True, exist_ok=True)
    documents = []
    for doc in docs:
        image = folder / f"{doc}.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + doc.encode())
        gt = folder / f"{doc}.gt.txt"
        gt.write_text("le texte", encoding="utf-8")
        documents.append(
            DocumentRef(
                id=doc,
                image_uri=str(image),
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            )
        )
    return RunSpec(
        corpus=CorpusSpec(name="c", documents=tuple(documents)),
        pipelines=(
            PipelineSpec(
                name="ocr",
                initial_inputs=(ArtifactType.IMAGE,),
                steps=(
                    PipelineStep(
                        id="ocr",
                        kind="ocr",
                        adapter_name="fakeocr:fra",
                        input_types=(ArtifactType.IMAGE,),
                        output_types=(ArtifactType.RAW_TEXT,),
                    ),
                ),
            ),
        ),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="texte",
                    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
                    metric_names=("cer",),
                ),
            ),
            analyses="toutes",
        ),
    )


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register_builder("fakeocr", lambda _kwargs: _Ocr())
    return registry


def _run(spec: RunSpec, store: ResumeStore, *, offline: bool = False) -> RunResult:
    return run(
        spec,
        registry=_registry(),
        code_version="t",
        resume_store=store,
        max_workers=1,
        offline=offline,
    )


def _resumed(result: RunResult) -> dict[str, bool]:
    return {u.document_id: u.resumed for u in result.usage}


def test_a_unit_read_from_the_archive_is_marked_resumed(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "archive")
    first = _run(_spec(tmp_path / "c", ("p1",)), store)
    assert _resumed(first) == {"p1": False}
    # Un document s'ajoute : p1 est relu, p2 exécuté.
    second = _run(_spec(tmp_path / "c", _DOCS), store)
    assert _resumed(second) == {"p1": True, "p2": False}
    offline = _run(_spec(tmp_path / "c", _DOCS), store, offline=True)
    assert _resumed(offline) == {"p1": True, "p2": True}


def test_the_economics_counts_the_resumed_units(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "archive")
    _run(_spec(tmp_path / "c", ("p1",)), store)
    second = _run(_spec(tmp_path / "c", _DOCS), store)
    (economics,) = [
        a.payload for a in second.analyses if isinstance(a.payload, EconomicsPayload)
    ]
    (row,) = economics.pipelines
    assert row.n_documents == 2 and row.n_resumed == 1


def test_the_csv_names_an_inherited_duration(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "archive")
    _run(_spec(tmp_path / "c", ("p1",)), store)
    csv = run_result_csv(_run(_spec(tmp_path / "c", _DOCS), store))
    usage = [line for line in csv.splitlines() if line.startswith("usage,")]
    assert any(",p1,duration_seconds_first_run," in line for line in usage)
    assert any(",p2,duration_seconds," in line for line in usage)


def test_a_json_without_the_flag_reads_as_not_resumed() -> None:
    from cinoc.domain.usage import ResourceUsage
    from cinoc.evaluation.result import DocumentUsage

    unit = DocumentUsage.model_validate(
        {"document_id": "d", "pipeline": "p", "usage": ResourceUsage().model_dump()}
    )
    assert unit.resumed is False


class _Billed(_Ocr):
    """Échoue après un appel facturé (la page soumise, la sonde perdue)."""

    name = "billedocr:fra"

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        from cinoc.domain.errors import AdapterStepError
        from cinoc.domain.usage import ResourceUsage

        raise AdapterStepError(
            "sonde perdue", billed=ResourceUsage(billed_pages=1, tokens_in=10)
        )


def test_a_failed_unit_keeps_what_it_got_billed_through_the_archive(
    tmp_path: Path,
) -> None:
    """Une tentative facturable est comptée même quand l'unité échoue — et une
    re-notation hors ligne relit la même consommation."""
    spec = _spec(tmp_path / "c", ("p1",))
    step = spec.pipelines[0].steps[0].model_copy(
        update={"adapter_name": "billedocr:fra"}
    )
    pipeline = spec.pipelines[0].model_copy(update={"steps": (step,)})
    spec = spec.model_copy(update={"pipelines": (pipeline,)})
    registry = ModuleRegistry()
    registry.register_builder("billedocr", lambda _kwargs: _Billed())
    store = ResumeStore(tmp_path / "archive")
    for offline in (False, True):
        result = run(
            spec, registry=registry, code_version="t", resume_store=store,
            max_workers=1, offline=offline,
        )
        (unit,) = result.usage
        assert unit.outcome == "failed"
        assert unit.usage.billed_pages == 1 and unit.usage.tokens_in == 10
        assert unit.usage.duration_seconds is None
