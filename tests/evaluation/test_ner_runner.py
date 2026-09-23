"""NER de bout en bout via ``evaluate_run`` : scalaire ``ner_f1`` + payload + R14.

Prouve la tranche dans le runner réel (≠ test unitaire du collecteur) : une vue
``entities`` (candidat ENTITIES) sur des artefacts ENTITIES pré-calculés + une
GT entités sidecar. Le décalage d'offset OCR/GT (insert amont) est reprojeté
(R14) → l'entité bien transcrite reste un vrai positif (ner_f1 = 1.0).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import NerPayload
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.result import RunResult
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)
ENTITIES_VIEW = EvaluationView(
    name="entities",
    candidate_types=frozenset({ArtifactType.ENTITIES}),
    metric_names=("ner_f1",),
)


def _write_entities(path: Path, text: str, entities: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"text": text, "entities": entities}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _registry() -> MetricRegistry:
    registry = MetricRegistry()
    register_default_metrics(registry)
    return registry


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(
            PipelineSpec(name="alpha", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def test_ner_f1_and_payload_through_evaluate_run(tmp_path: Path) -> None:
    gt_text = "Marie de Bourgogne"
    gt = _write_entities(
        tmp_path / "d0.gt.entities.json",
        gt_text,
        [
            {"label": "PER", "start": 0, "end": 5},
            {"label": "LOC", "start": 9, "end": 18},
        ],
    )
    # OCR a inséré 5 caractères au début → tous les offsets décalés de +5. Sans
    # R14, les deux entités rateraient l'IoU ; avec, elles sont reprojetées.
    ocr_text = "XXXXXMarie de Bourgogne"
    hyp = _write_entities(
        tmp_path / "d0.alpha.entities.json",
        ocr_text,
        [
            {"label": "PER", "start": 5, "end": 10},
            {"label": "LOC", "start": 14, "end": 23},
        ],
    )
    document = DocumentRef(
        id="d0",
        ground_truths=(GroundTruthRef(type=ArtifactType.ENTITIES, uri=str(gt)),),
    )
    corpus = CorpusSpec(name="c", documents=(document,))
    outputs = {
        "alpha": {
            "d0": {
                ArtifactType.ENTITIES: Artifact(
                    id="d0:alpha:entities",
                    document_id="d0",
                    type=ArtifactType.ENTITIES,
                    uri=str(hyp),
                )
            }
        }
    }
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(ENTITIES_VIEW,), analyses="toutes"),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=_manifest(),
    )
    # Scalaire : R14 reprojette → les 2 entités matchent → ner_f1 micro = 1.0.
    (pipeline,) = result.pipelines
    ner_score = next(s for s in pipeline.aggregate if s.metric == "ner_f1")
    assert ner_score.value == 1.0
    assert ner_score.support == 1  # 1 document applicable (poids interne = 2 entités)
    # Payload : présent, F1 parfait, deux catégories, aucune manquée/hallucinée.
    ner_payloads = [a for a in result.analyses if isinstance(a.payload, NerPayload)]
    assert len(ner_payloads) == 1
    payload = ner_payloads[0].payload
    assert isinstance(payload, NerPayload)
    (row,) = payload.pipelines
    assert row.f1 == 1.0 and row.n_reference == 2
    assert {c.label for c in row.per_category} == {"PER", "LOC"}
    assert row.missed == () and row.hallucinated == ()
    # Round-trip JSON : le payload survit tel quel.
    assert RunResult.model_validate_json(result.model_dump_json()) == result
