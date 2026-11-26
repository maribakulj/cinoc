"""Reprise d'exécution : cache par empreinte, invalidation, usage restauré."""

from __future__ import annotations

from pathlib import Path

from cinoc.app.modules.registry import ModuleRegistry
from cinoc.app.orchestrator import run
from cinoc.app.resume import ResumeStore, unit_key
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.pipeline.fingerprint import ModuleIdentity
from cinoc.pipeline.types import StepOutput


class _CountingOCR:
    """Moteur factice : écrit un texte fixe et compte ses exécutions."""

    name = "counting:eng"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        self._calls.append(context.document_id)
        path = Path(context.workspace_uri) / f"{context.document_id}.txt"
        path.write_text("abcd", encoding="utf-8")
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:counting:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(path),
                    content_hash=compute_content_hash(b"abcd"),
                )
            }
        )


def _spec(tmp_path: Path) -> RunSpec:
    image = tmp_path / "d1.png"
    image.write_bytes(b"\x89PNG fake")
    gt = tmp_path / "d1.gt.txt"
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
                adapter_name="counting:eng",
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
        run_id="resume-test",
    )


def _registry(calls: list[str]) -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register_builder("counting", lambda kwargs: _CountingOCR(calls))
    return registry


def test_second_run_executes_nothing_and_scores_identically(tmp_path: Path) -> None:
    calls: list[str] = []
    store = ResumeStore(tmp_path / "cache")
    spec = _spec(tmp_path)
    first = run(
        spec, registry=_registry(calls), code_version="1.0", resume_store=store
    )
    assert calls == ["d1"]
    second = run(
        spec, registry=_registry(calls), code_version="1.0", resume_store=store
    )
    assert calls == ["d1"]  # zéro ré-exécution
    cer = {
        (p.pipeline, s.metric): s.value
        for p in second.pipelines
        for s in p.aggregate
    }
    assert cer[("p", "cer")] == 0.0
    # L'usage du run d'origine est restauré (pas un coût de cache mensonger).
    assert second.usage[0].usage.duration_seconds == (
        first.usage[0].usage.duration_seconds
    )


def test_code_version_change_keeps_the_cache(tmp_path: Path) -> None:
    """La version du paquet n'est plus dans la clé (S9) : une correction de
    métrique ne rejoue aucune inférence."""
    calls: list[str] = []
    store = ResumeStore(tmp_path / "cache")
    spec = _spec(tmp_path)
    run(spec, registry=_registry(calls), code_version="1.0", resume_store=store)
    run(spec, registry=_registry(calls), code_version="2.0", resume_store=store)
    assert calls == ["d1"]


def test_module_version_change_invalidates_cache(tmp_path: Path) -> None:
    calls: list[str] = []
    store = ResumeStore(tmp_path / "cache")
    spec = _spec(tmp_path)
    run(spec, registry=_registry(calls), code_version="1.0", resume_store=store)
    bumped = ModuleRegistry()
    bumped.register_builder(
        "counting",
        lambda kwargs: type("_Bumped", (_CountingOCR,), {"version": "1.1"})(calls),
    )
    run(spec, registry=bumped, code_version="1.0", resume_store=store)
    assert calls == ["d1", "d1"]  # module relevé → ré-exécution


def test_image_content_change_invalidates_cache(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    document = spec.corpus.documents[0]
    identities = {"counting:eng": ModuleIdentity("1.0")}
    key_before = unit_key(
        pipeline=spec.pipelines[0],
        identities=identities,
        document=document,
        inputs={},
    )
    Path(document.image_uri).write_bytes(b"\x89PNG autre contenu")
    key_after = unit_key(
        pipeline=spec.pipelines[0],
        identities=identities,
        document=document,
        inputs={},
    )
    assert key_before != key_after


def test_corrupted_entry_falls_back_to_execution(tmp_path: Path) -> None:
    calls: list[str] = []
    store = ResumeStore(tmp_path / "cache")
    spec = _spec(tmp_path)
    run(spec, registry=_registry(calls), code_version="1.0", resume_store=store)
    for index in (tmp_path / "cache").rglob("index.json"):
        index.write_text("{corrompu", encoding="utf-8")
    run(spec, registry=_registry(calls), code_version="1.0", resume_store=store)
    assert calls == ["d1", "d1"]


class _CutOCR(_CountingOCR):
    """Comme ``_CountingOCR``, mais sa sortie est coupée (plafond de jetons)."""

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        output = super().execute(inputs, params, context, control)
        return StepOutput(artifacts=output.artifacts, truncation="plafond atteint")


def test_a_truncated_unit_is_reloaded_as_truncated(tmp_path: Path) -> None:
    """Une coupure se reproduirait à l'identique : on ne la rejoue pas (elle se
    repayerait), mais la reprise ne doit pas la rendre « complète » pour autant."""
    calls: list[str] = []
    registry = ModuleRegistry()
    registry.register_builder("counting", lambda kwargs: _CutOCR(calls))
    store = ResumeStore(tmp_path / "cache")
    spec = _spec(tmp_path)
    first = run(spec, registry=registry, code_version="1.0", resume_store=store)
    second = run(spec, registry=registry, code_version="1.0", resume_store=store)
    assert calls == ["d1"]
    for result in (first, second):
        (unit,) = result.usage
        assert unit.outcome == "truncated"
        assert unit.message == "étape 'ocr' : plafond atteint"
