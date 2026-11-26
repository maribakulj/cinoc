"""L'intervalle porte sur le chiffre affiché : bootstrap du ratio micro."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from scipy import stats  # type: ignore[import-untyped]

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import InferencePayload
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.inference import (
    BOOTSTRAP_SEED,
    N_RESAMPLES,
    bootstrap_batch,
    inference_analyses,
    micro_ratio,
    micro_ratio_ci,
)
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.result import RunResult
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _unbalanced_run(tmp_path: Path) -> RunResult:
    """Un long document presque juste, neuf courts à moitié faux.

    ``long`` : 20 erreurs sur 2 000 caractères (CER 0,01), puis 5 sur 10
    (CER 0,5) neuf fois → micro (20 + 45)/2 090 ≈ 0,031, macro ≈ 0,451.
    """
    documents: list[DocumentRef] = []
    outputs: dict[str, dict[str, dict[str, dict[ArtifactType, Artifact]]]] = {
        "long": {},
        "exact": {},
    }
    texts = [("x" * 2000, "y" * 20 + "x" * 1980)] + [
        ("abcdefghij", "XXXXXfghij")
    ] * 9
    for i, (gt, hyp) in enumerate(texts):
        doc_id = f"d{i}"
        gt_path = tmp_path / f"{doc_id}.gt.txt"
        gt_path.write_text(gt, encoding="utf-8")
        documents.append(
            DocumentRef(
                id=doc_id,
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt_path)),
                ),
            )
        )
        for name, text in (("long", hyp), ("exact", gt)):
            path = tmp_path / f"{doc_id}.{name}.txt"
            path.write_text(text, encoding="utf-8")
            outputs[name][doc_id] = {
                "ocr": {
                    ArtifactType.RAW_TEXT: Artifact(
                        id=f"{doc_id}:{name}:raw_text",
                        document_id=doc_id,
                        type=ArtifactType.RAW_TEXT,
                        uri=str(path),
                    )
                }
            }
    registry = MetricRegistry()
    register_default_metrics(registry)
    return evaluate_run(
        corpus=CorpusSpec(name="c", documents=tuple(documents)),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="text",
                    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
                    metric_names=("cer", "wer", "char_accuracy"),
                ),
            ),
            analyses=["inference"],
        ),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=len(documents),
            pipeline_specs=tuple(
                PipelineSpec(name=name, initial_inputs=(ArtifactType.IMAGE,))
                for name in ("long", "exact")
            ),
            code_version="1.0",
            started_at=FIXED,
            completed_at=FIXED,
        ),
    )


def test_the_displayed_point_is_inside_its_interval(tmp_path: Path) -> None:
    """Corpus très déséquilibré (micro ≠ macro) : l'IC d'une moyenne macro
    excluait le CER micro du tableau ; celui du ratio micro le contient."""
    result = _unbalanced_run(tmp_path)
    displayed = {
        (p.view, p.pipeline, score.metric): score.value
        for p in result.pipelines
        for score in p.aggregate
    }
    assert displayed[("text", "long", "cer")] == 65 / 2090
    checked = 0
    for analysis in result.analyses:
        payload = analysis.payload
        if not isinstance(payload, InferencePayload):
            continue
        for interval in payload.intervals:
            point = displayed[(analysis.view, interval.pipeline, payload.metric)]
            assert point is not None
            assert interval.lower <= point <= interval.upper, (
                payload.metric,
                interval.pipeline,
                point,
                interval,
            )
            checked += 1
    assert checked == 6
    # Et c'est le bootstrap de ce ratio-là : documents de ``long`` en CER.
    scores = [
        next(s for s in d.scores if s.metric == "cer")
        for d in result.documents
        if d.pipeline == "long"
    ]
    values = [s.value for s in scores if s.value is not None]
    weights = [s.support or 0 for s in scores]
    assert sum(values) / len(values) == pytest.approx(0.451)  # la macro
    (cer,) = (
        a.payload
        for a in result.analyses
        if isinstance(a.payload, InferencePayload) and a.payload.metric == "cer"
    )
    interval = next(i for i in cer.intervals if i.pipeline == "long")
    assert interval.value == displayed[("text", "long", "cer")]
    assert (interval.lower, interval.upper) == pytest.approx(
        _scipy_interval(values, weights), rel=1e-12
    )
    # Large et honnête : sans le long document (≈ 35 % des tirages, 0,9¹⁰),
    # le ratio vaut 0,5 — l'ancien IC de la macro, [0,353 ; 0,5], l'excluait.
    assert interval.lower < 0.03 and interval.upper == pytest.approx(0.5)


def _scipy_interval(values: list[float], weights: list[int]) -> tuple[float, float]:
    """Oracle : ``scipy.stats.bootstrap`` apparié, percentile, même graine."""

    def ratio(v: np.ndarray, w: np.ndarray, axis: int = -1) -> np.ndarray:
        return (v * w).sum(axis=axis) / w.sum(axis=axis)

    n = len(values)
    result = stats.bootstrap(
        (np.asarray(values), np.asarray(weights, dtype=np.float64)),
        ratio,
        paired=True,
        vectorized=True,
        n_resamples=N_RESAMPLES,
        batch=bootstrap_batch(n),
        method="percentile",
        confidence_level=0.95,
        rng=np.random.default_rng(BOOTSTRAP_SEED),
    )
    interval = result.confidence_interval
    return float(interval.low), float(interval.high)


@pytest.mark.parametrize("n", [2, 7, 40, 3000])  # 3 000 : plusieurs lots
def test_interval_is_scipy_bootstrap_of_the_ratio(n: int) -> None:
    rng = np.random.default_rng(n)
    values = [float(v) for v in rng.random(n)]
    weights = [int(w) for w in rng.integers(1, 500, n)]
    assert micro_ratio_ci(values, weights) == pytest.approx(
        _scipy_interval(values, weights), rel=1e-12
    )


def test_golden_interval_is_pinned_and_deterministic() -> None:
    """Valeurs figées — recalculées contre scipy, pas contre l'ancien code
    (D-265) : un changement du flux de ``default_rng`` se verrait ici."""
    values = [0.10, 0.12, 0.08, 0.11, 0.09, 0.13, 0.10, 0.12]
    weights = [120, 80, 300, 45, 210, 60, 150, 95]
    golden = (0.08819908163265307, 0.11330935251798561)
    assert micro_ratio_ci(values, weights) == golden  # mêmes octets
    assert golden == pytest.approx(_scipy_interval(values, weights), rel=1e-12)
    point = micro_ratio(values, weights)
    assert point is not None and golden[0] <= point <= golden[1]


def test_point_is_inside_its_interval_on_seeded_corpora() -> None:
    """1 000 corpus tirés (1 à 80 documents, poids log-normaux, un document
    dominant une fois sur trois, valeurs constantes une fois sur dix) ;
    l'ancien IC (bootstrap de la moyenne des documents) excluait le point
    micro dans 340 de ces 1 000 tirages."""
    rng = np.random.default_rng(7)
    for _ in range(1000):
        n = int(rng.integers(1, 80))
        weights = np.maximum(1, np.round(rng.lognormal(3, 1.5, n))).astype(int)
        if rng.random() < 0.3:
            weights[int(rng.integers(n))] *= int(rng.integers(50, 2000))
        values = rng.beta(0.6, 4, n) * float(rng.choice([1.0, 1.5]))
        if rng.random() < 0.1:
            values[:] = values[0]
        v, w = [float(x) for x in values], [int(x) for x in weights]
        point = micro_ratio(v, w)
        lower, upper = micro_ratio_ci(v, w)
        # À l'ulp près : pour des valeurs constantes, le point (``sum`` de
        # Python, compensé depuis 3.12) et les tirages (somme par paires de
        # numpy) arrondissent la même constante différemment.
        slack = 1e-12 * abs(point or 0.0)
        assert point is not None and lower - slack <= point <= upper + slack, (v, w)


def test_zero_weight_documents_weigh_nothing() -> None:
    """Un document de poids nul (référence vide) n'entre ni dans le point ni
    dans le rééchantillonnage : l'IC et son n sont ceux des autres."""
    values: dict[str, list[float | None]] = {
        "a": [0.1, 0.2, 0.3, 0.1, 0.2, 0.3],
        "b": [0.2, 0.3, 0.4, 0.2, 0.3, 0.4],
    }
    weights = {"a": [10, 20, 30, 40, 50, 60], "b": [10, 20, 30, 40, 50, 60]}
    padded_values: dict[str, list[float | None]] = {
        name: [*series, 1.0] for name, series in values.items()
    }
    padded_weights = {name: [*series, 0] for name, series in weights.items()}
    (plain,) = inference_analyses([("v", "cer", values, weights)])
    (padded,) = inference_analyses([("v", "cer", padded_values, padded_weights)])
    assert isinstance(plain.payload, InferencePayload)
    assert isinstance(padded.payload, InferencePayload)
    assert plain.payload.intervals == padded.payload.intervals
    assert {i.n_documents for i in padded.payload.intervals} == {6}
    with pytest.raises(EvaluationError):
        micro_ratio_ci([0.1, 0.2], [3, 0])
    assert micro_ratio([0.5], [0]) is None
