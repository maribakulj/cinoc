"""Outillage commun de la contre-expertise « applicabilité et échecs ».

Tout passe par les API publiques : les briques de test implémentent le
``Module`` Protocol avec ce qu'exporte ``cinoc.adapters.extension`` et sont
branchées par ``discover_plugins`` (le point d'extension tiers, entry-points
simulés) ; les runs passent par ``cinoc.app.run``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from cinoc.adapters.extension import (
    AdapterStepError,
    Artifact,
    ArtifactType,
    RunContext,
    RunControl,
    StepOutput,
    compute_content_hash,
    workspace_artifact_path,
)
from cinoc.app import run
from cinoc.app.modules.discovery import discover_plugins
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.resume import ResumeStore
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.result import MetricScore, RunResult

T = ArtifactType

#: Comportement d'une brique pour un document : texte rendu, ou exception.
Behaviour = Callable[[str], str | AdapterStepError]


@dataclass
class TextBrick:
    """Brique ``in_type → out_type`` écrite comme un module tiers.

    ``behaviour(document_id)`` rend le texte de sortie ou l'erreur typée à
    lever. ``usage`` est remonté à chaque succès (moteur facturé). ``inline``
    : documents pour lesquels l'artefact est rendu **sans contenu**
    (``uri=None``) ; ``dangling`` : documents pour lesquels l'URI désigne un
    fichier jamais écrit ; ``truncate`` : documents dont la sortie est coupée.
    """

    name: str
    behaviour: Behaviour
    in_type: ArtifactType = T.IMAGE
    out_type: ArtifactType = T.RAW_TEXT
    usage: ResourceUsage | None = None
    inline: frozenset[str] = frozenset()
    dangling: frozenset[str] = frozenset()
    truncate: frozenset[str] = frozenset()
    calls: list[str] = field(default_factory=list)
    version: str = "1.0"

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({self.in_type})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({self.out_type})

    def execute(
        self,
        inputs: Mapping[ArtifactType, Artifact],
        params: Mapping[str, object],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        document_id = context.document_id
        self.calls.append(document_id)
        produced = self.behaviour(document_id)
        if isinstance(produced, AdapterStepError):
            raise produced
        assert context.workspace_uri is not None
        path = workspace_artifact_path(
            context.workspace_uri, document_id, self.name.replace(":", "_"), "txt"
        )
        payload = produced.encode("utf-8")
        if document_id not in self.dangling:
            path.write_bytes(payload)
        artifact = Artifact(
            id=f"{document_id}:{self.name}:{self.out_type.value}",
            document_id=document_id,
            type=self.out_type,
            uri=None if document_id in self.inline else str(path),
            content_hash=compute_content_hash(payload),
        )
        return StepOutput(
            artifacts={self.out_type: artifact},
            usage=self.usage,
            truncation="max_tokens" if document_id in self.truncate else None,
        )


@dataclass(frozen=True)
class _EntryPoint:
    """Entry-point ``cinoc.modules`` simulé (forme de ``importlib.metadata``)."""

    name: str
    target: object

    def load(self) -> object:
        return self.target


def registry_with(*bricks: object) -> ModuleRegistry:
    """Socle + briques tierces branchées par la découverte d'entry-points."""
    registry = ModuleRegistry()
    register_default_modules(registry)
    entry_points = [
        _EntryPoint(name=brick.name, target=(lambda _kwargs, b=brick: b))  # type: ignore[attr-defined]
        for brick in bricks
    ]
    discovered = discover_plugins(
        registry, enabled=True, entry_points_loader=lambda: entry_points
    )
    assert set(discovered) >= {b.name for b in bricks}  # type: ignore[attr-defined]
    return registry


def corpus(tmp_path: Path, references: Mapping[str, str | None]) -> CorpusSpec:
    """Un document par entrée ; ``None`` = pas de vérité terrain du tout."""
    documents = []
    for document_id, reference in references.items():
        image = tmp_path / f"{document_id}.png"
        image.write_bytes(b"\x89PNG stub " + document_id.encode())
        ground_truths: tuple[GroundTruthRef, ...] = ()
        if reference is not None:
            gt = tmp_path / f"{document_id}.gt.txt"
            gt.write_text(reference, encoding="utf-8")
            ground_truths = (GroundTruthRef(type=T.RAW_TEXT, uri=str(gt)),)
        documents.append(
            DocumentRef(id=document_id, image_uri=str(image), ground_truths=ground_truths)
        )
    return CorpusSpec(name="ce", documents=tuple(documents))


def step(
    step_id: str,
    adapter: str,
    in_type: ArtifactType = T.IMAGE,
    out_type: ArtifactType = T.RAW_TEXT,
) -> PipelineStep:
    return PipelineStep(
        id=step_id,
        kind="ocr" if in_type is T.IMAGE else "correction",
        adapter_name=adapter,
        input_types=(in_type,),
        output_types=(out_type,),
    )


def pipeline(name: str, *steps: PipelineStep) -> PipelineSpec:
    return PipelineSpec(name=name, initial_inputs=(T.IMAGE,), steps=steps)


def text_view(
    name: str = "texte",
    metrics: Sequence[str] = ("cer",),
    candidates: Iterable[ArtifactType] = (T.RAW_TEXT,),
    target_step: str | None = None,
) -> EvaluationView:
    return EvaluationView(
        name=name,
        candidate_types=frozenset(candidates),
        metric_names=tuple(metrics),
        target_step=target_step,
    )


def spec(
    corpus_spec: CorpusSpec,
    pipelines: Sequence[PipelineSpec],
    views: Sequence[EvaluationView],
    **evaluation: object,
) -> RunSpec:
    return RunSpec(
        run_id="ce-applicabilite",
        corpus=corpus_spec,
        pipelines=tuple(pipelines),
        evaluation=EvaluationSpec(views=tuple(views), **evaluation),  # type: ignore[arg-type]
    )


def execute(
    run_spec: RunSpec,
    registry: ModuleRegistry,
    resume_dir: Path | None = None,
) -> RunResult:
    return run(
        run_spec,
        registry=registry,
        code_version="ce",
        max_workers=1,
        resume_store=ResumeStore(resume_dir) if resume_dir is not None else None,
    )


def aggregate(
    result: RunResult, pipeline_name: str, metric: str = "cer", view: str = "texte"
) -> MetricScore:
    for entry in result.pipelines:
        if (entry.pipeline, entry.view) == (pipeline_name, view):
            return next(s for s in entry.aggregate if s.metric == metric)
    raise AssertionError((pipeline_name, view))


def per_document(
    result: RunResult,
    pipeline_name: str,
    document_id: str,
    metric: str = "cer",
    view: str = "texte",
) -> MetricScore:
    for entry in result.documents:
        if (entry.pipeline, entry.document_id, entry.view) == (
            pipeline_name,
            document_id,
            view,
        ):
            return next(s for s in entry.scores if s.metric == metric)
    raise AssertionError((pipeline_name, document_id, view))


def fixed(texts: Mapping[str, str]) -> Behaviour:
    """Comportement : le texte prévu pour le document (``KeyError`` sinon)."""
    return lambda document_id: texts[document_id]


def levenshtein(a: str, b: str) -> int:
    """Distance d'édition de référence, écrite à la main (oracle indépendant)."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]
