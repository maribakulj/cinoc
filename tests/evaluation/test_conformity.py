"""Analyse de conformité HIPE : payload ``hipe`` cross-vues, valeurs main.

Cas témoin dérivé à la main : GT « Œ—\\nc » / sortie « OEC ».
- vue ``hipe``     : les deux côtés se normalisent en « oec » → cmer = 0 ;
- vue ``heritage`` : « œc » vs « oec » → 1 substitution + 1 insertion → 2/3 ;
- vue ``raw``      : « Œ—\\nc » vs « OEC » → 3 substitutions + 1 suppression → 1.
Les deltas en découlent : Δnorm = 1 − 0, Δheritage = 2/3 − 0.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import ConformityPayload
from cinoc.evaluation.conformity import conformity_analysis
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _view(name: str, profile: str | None, metrics: tuple[str, ...]) -> EvaluationView:
    return EvaluationView(
        name=name,
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        normalization_profile=profile,
        metric_names=metrics,
    )


def _manifest(n: int) -> RunManifest:
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=n,
        pipeline_specs=(
            PipelineSpec(name="eng", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def _run(tmp_path: Path, views: tuple[EvaluationView, ...]):
    gt1 = tmp_path / "doc1.gt.txt"
    gt1.write_text("Œ—\nc", encoding="utf-8")
    gt2 = tmp_path / "doc2.gt.txt"
    gt2.write_text("x", encoding="utf-8")
    hyp1 = tmp_path / "doc1.hyp.txt"
    hyp1.write_text("OEC", encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="doc1",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt1)),
                ),
            ),
            DocumentRef(
                id="doc2",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt2)),
                ),
            ),
        ),
    )
    outputs = {
        "eng": {
            "doc1": {
                ArtifactType.RAW_TEXT: Artifact(
                    id="doc1:raw",
                    document_id="doc1",
                    type=ArtifactType.RAW_TEXT,
                    uri=str(hyp1),
                )
            }
            # doc2 : aucune sortie → non scoré (n_missing).
        }
    }
    registry = MetricRegistry()
    register_default_metrics(registry)
    return evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=views, analyses="toutes"),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=_manifest(2),
    )


def _payload(result) -> ConformityPayload | None:
    for analysis in result.analyses:
        if isinstance(analysis.payload, ConformityPayload):
            return analysis.payload
    return None


def test_conformity_payload_hand_values(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        (
            _view("raw", None, ("cmer",)),
            _view("hipe", "hipe", ("cmer", "mer")),
            _view("heritage", "heritage", ("cmer",)),
        ),
    )
    payload = _payload(result)
    assert payload is not None
    assert (payload.hipe_view, payload.raw_view, payload.heritage_view) == (
        "hipe",
        "raw",
        "heritage",
    )
    (row,) = payload.pipelines
    assert row.pipeline == "eng"
    assert row.cmer_micro == pytest.approx(0.0)
    assert row.cmer_macro == pytest.approx(0.0)
    assert row.wmer_micro == pytest.approx(0.0)
    assert row.wmer_macro == pytest.approx(0.0)
    assert row.delta_norm == pytest.approx(1.0)
    assert row.delta_heritage == pytest.approx(2 / 3)
    assert row.n_missing == 1


def test_cmer_view_without_hipe_still_produces_payload(tmp_path: Path) -> None:
    # Dégating : une vue portant ``cmer`` (sans profil HIPE) sert d'ancre →
    # cMER/wMER micro·macro sur tout corpus ; deltas None (pas de vues à comparer).
    result = _run(tmp_path, (_view("raw", None, ("cmer", "mer")),))
    payload = _payload(result)
    assert payload is not None
    assert payload.hipe_view == "raw"
    assert payload.raw_view is None and payload.heritage_view is None
    row = payload.pipelines[0]
    assert row.cmer_micro is not None and row.cmer_macro is not None
    assert row.delta_norm is None and row.delta_heritage is None


def test_no_cmer_anywhere_means_no_payload(tmp_path: Path) -> None:
    # Plus de cmer du tout (ni vue hipe, ni vue standard) → pas d'ancre → None.
    result = _run(tmp_path, (_view("raw", None, ("cer",)),))
    assert _payload(result) is None


def test_hipe_view_without_cmer_falls_back_or_none(tmp_path: Path) -> None:
    # Vue hipe sans cmer + aucune autre vue cmer → None (inutilisable comme ancre).
    result = _run(tmp_path, (_view("hipe", "hipe", ("cer",)),))
    assert _payload(result) is None


def test_builder_requires_pipelines() -> None:
    views = (_view("hipe", "hipe", ("cmer",)),)
    assert conformity_analysis(views, (), ()) is None
