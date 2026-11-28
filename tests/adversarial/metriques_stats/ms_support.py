"""Fabrique de corpus minimaux pour la contre-expertise ``metriques_stats``.

Tout passe par les API publiques : fichiers GT + artefacts pré-calculés sur
disque, ``evaluate_run`` (couche 3) et le registre par défaut. Aucun
monkeypatch du code testé.

Importé de la contre-expertise (commit ``04a1c17b``) ; la refonte y ajoute
``Bench.truncate`` (une sortie coupée, issue ``truncated``), pour R6, et
``Bench.partial`` (étape déclarée partielle, issue ``partial``), pour § 2.1 f.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run import RunManifest
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.analysis import InferencePayload
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.result import DocumentUsage, MetricScore, RunResult
from cinoc.evaluation.runner import evaluate_run
from tests.adversarial._contrat import issue_partielle

FIXED = datetime(2026, 1, 1, tzinfo=UTC)

_EXT = {
    ArtifactType.RAW_TEXT: "txt",
    ArtifactType.ENTITIES: "entities.json",
    ArtifactType.LAYOUT: "layout.json",
    ArtifactType.CONFIDENCES: "conf.json",
}


def registry() -> MetricRegistry:
    reg = MetricRegistry()
    register_default_metrics(reg)
    return reg


@dataclass
class Bench:
    """Un corpus + les sorties de plusieurs pipelines, écrits dans ``root``."""

    root: Path
    gt_type: ArtifactType = ArtifactType.RAW_TEXT
    documents: list[DocumentRef] = field(default_factory=list)
    outputs: dict[str, dict[str, dict[str, dict[ArtifactType, Artifact]]]] = field(
        default_factory=dict
    )
    failed: list[tuple[str, str]] = field(default_factory=list)
    truncated: set[tuple[str, str]] = field(default_factory=set)
    partials: set[tuple[str, str]] = field(default_factory=set)
    pipelines: list[str] = field(default_factory=list)

    def _write(self, name: str, content: str | bytes) -> Path:
        path = self.root / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def document(self, doc_id: str, gt: str) -> None:
        path = self._write(f"{doc_id}.gt.{_EXT[self.gt_type]}", gt)
        self.documents.append(
            DocumentRef(
                id=doc_id,
                ground_truths=(GroundTruthRef(type=self.gt_type, uri=str(path)),),
            )
        )

    def output(
        self,
        pipeline: str,
        doc_id: str,
        content: str,
        artifact_type: ArtifactType | None = None,
        extra: Mapping[ArtifactType, str] | None = None,
    ) -> None:
        kind = artifact_type or self.gt_type
        if pipeline not in self.pipelines:
            self.pipelines.append(pipeline)
        step: dict[ArtifactType, Artifact] = {}
        for typ, body in {kind: content, **(extra or {})}.items():
            path = self._write(f"{doc_id}.{pipeline}.{_EXT[typ]}", body)
            step[typ] = Artifact(
                id=f"{doc_id}:{pipeline}:{typ.value}",
                document_id=doc_id,
                type=typ,
                uri=str(path),
            )
        self.outputs.setdefault(pipeline, {})[doc_id] = {"step": step}

    def truncate(self, pipeline: str, doc_id: str, content: str) -> None:
        """Sortie ``content`` coupée (``max_tokens``) : l'unité est ``truncated``."""
        self.output(pipeline, doc_id, content)
        self.truncated.add((pipeline, doc_id))

    def partial(self, pipeline: str, doc_id: str, content: str) -> None:
        """Sortie ``content`` d'une étape **déclarée partielle** (§ 2.1 f) :
        l'unité est ``partial``, ce qui a été produit reste lisible."""
        issue_partielle()
        self.output(pipeline, doc_id, content)
        self.partials.add((pipeline, doc_id))

    def fail(self, pipeline: str, doc_id: str) -> None:
        if pipeline not in self.pipelines:
            self.pipelines.append(pipeline)
        self.failed.append((pipeline, doc_id))

    def run(
        self,
        view: EvaluationView,
        *,
        failure_policy: str = "exclude",
        analyses: object = "toutes",
    ) -> RunResult:
        usage = [
            DocumentUsage(
                document_id=d,
                pipeline=p,
                usage=ResourceUsage(),
                outcome="failed",
                reason="engine",
                message="panne simulée",
            )
            for p, d in self.failed
        ]
        for p, by_doc in self.outputs.items():
            for d in by_doc:
                usage.append(
                    DocumentUsage(
                        document_id=d,
                        pipeline=p,
                        usage=ResourceUsage(duration_seconds=1.0),
                        outcome=(
                            "truncated"
                            if (p, d) in self.truncated
                            else "partial"
                            if (p, d) in self.partials
                            else "ok"
                        ),
                    )
                )
        manifest = RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=len(self.documents),
            # Une étape par pipeline, qui **déclare** le type que la vue note :
            # « hors vue » est une propriété du pipeline, lue sur ses types de
            # sortie déclarés (D1) — un pipeline sans étape ne voit aucune vue.
            pipeline_specs=tuple(
                PipelineSpec(
                    name=p,
                    initial_inputs=(ArtifactType.IMAGE,),
                    steps=(
                        PipelineStep(
                            id="step",
                            kind="ocr",
                            adapter_name="bench",
                            input_types=(ArtifactType.IMAGE,),
                            output_types=tuple(sorted(view.candidate_types)),
                        ),
                    ),
                )
                for p in self.pipelines
            ),
            failure_policy=failure_policy,  # type: ignore[arg-type]
            code_version="1.0",
            started_at=FIXED,
            completed_at=FIXED,
        )
        return evaluate_run(
            corpus=CorpusSpec(name="c", documents=tuple(self.documents)),
            evaluation=EvaluationSpec(
                views=(view,),
                analyses=analyses,  # type: ignore[arg-type]
                failure_policy=failure_policy,  # type: ignore[arg-type]
            ),
            pipeline_outputs=self.outputs,  # type: ignore[arg-type]
            registry=registry(),
            manifest=manifest,
            usage=tuple(usage),
        )


def view(
    metrics: Sequence[str], candidate: ArtifactType = ArtifactType.RAW_TEXT
) -> EvaluationView:
    return EvaluationView(
        name="v", candidate_types=frozenset({candidate}), metric_names=tuple(metrics)
    )


def aggregate(result: RunResult, pipeline: str, metric: str) -> MetricScore:
    (row,) = [p for p in result.pipelines if p.pipeline == pipeline]
    (score,) = [
        s for s in result.principal_aggregate(row) if s.metric == metric
    ]
    return score


def observation(
    result: RunResult, pipeline: str, document: str, metric: str
) -> MetricScore:
    """L'observation (pipeline × document × métrique) de la vue unique du banc."""
    for entry in result.documents:
        if (entry.pipeline, entry.document_id) == (pipeline, document):
            return next(s for s in entry.scores if s.metric == metric)
    raise AssertionError(f"aucune observation pour {(pipeline, document, metric)}")


def inference(result: RunResult, metric: str) -> InferencePayload:
    found = [
        a.payload
        for a in result.analyses
        if isinstance(a.payload, InferencePayload) and a.payload.metric == metric
    ]
    (payload,) = found
    return payload


def substitute(text: str, k: int, char: str = "0") -> str:
    """``text`` avec ses ``k`` premiers caractères remplacés (k substitutions)."""
    assert char not in text
    return char * k + text[k:]


def letters(n: int, seed: int = 0) -> str:
    """Texte de ``n`` lettres sans blanc ni ``0`` (distance = substitutions)."""
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    return "".join(alphabet[(i * 7 + seed) % 26] for i in range(n))


def entities_json(text: str, spans: Sequence[tuple[str, int, int]]) -> str:
    return json.dumps(
        {
            "text": text,
            "entities": [{"label": lab, "start": s, "end": e} for lab, s, e in spans],
        }
    )


def layout_json(
    regions: Sequence[
        tuple[str, tuple[int, int, int, int] | None, Sequence[tuple[str, str]]]
    ],
    reading_order: Sequence[str] = (),
    size: tuple[int, int] = (1000, 1000),
) -> str:
    """``CanonicalLayout`` JSON d'une page : ``(id, bbox|None, [(line_id, texte)])``."""
    regs = []
    for rid, bbox, lines in regions:
        reg: dict[str, object] = {"id": rid}
        if bbox is not None:
            x, y, w, h = bbox
            reg["geometry"] = {"bbox": {"x": x, "y": y, "width": w, "height": h}}
        if lines:
            reg["lines"] = [{"id": lid, "text": txt} for lid, txt in lines]
        regs.append(reg)
    return json.dumps(
        {
            "pages": [
                {
                    "width": size[0],
                    "height": size[1],
                    "regions": regs,
                    "reading_order": list(reading_order),
                }
            ]
        }
    )


def prf_f1(tp: int, fp: int, fn: int) -> float:
    """F1 de référence (calcul indépendant) : 2TP / (2TP + FP + FN)."""
    return 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0
