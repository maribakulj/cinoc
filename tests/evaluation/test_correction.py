"""Bilan de correction : payload ``correction``, valeurs dérivées à la main.

Cas témoin (pipeline « chain », vue sans profil) :
- doc1 : gt « le chat dort » · brut « le chot dort » · corrigé « le chat dort »
  → cmer brut 1/12, corrigé 0 → **amélioration** ; pcis = (1 − 11/12)/(11/12)
  = 1/11 ; ccr = 1/12 ; absorption : « chat » corrigé.
- doc2 : gt « abc » · brut « abc » · corrigé « abx »
  → cmer brut 0, corrigé 1/3 → **régression catastrophique** (Δ = 1/3 > 0.10) ;
  pcis = −1/3 ; sur-normalisation : « abc » (mot OCR-juste dégradé).
Agrégats : pref = 0 ; ccr micro = 2/15 ; cmer brut micro = 1/15 →
change_ratio = 2.0 ; net d'absorption = 0 (1 corrigée, 1 introduite).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import CorrectionPayload
from cinoc.evaluation.correction import correction_analysis
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)
VIEW = EvaluationView(
    name="text",
    candidate_types=frozenset({ArtifactType.CORRECTED_TEXT, ArtifactType.RAW_TEXT}),
    metric_names=("cer",),
)


def _artifact(doc: str, kind: ArtifactType, path: Path) -> Artifact:
    return Artifact(
        id=f"{doc}:{kind.value}", document_id=doc, type=kind, uri=str(path)
    )


def _doc(tmp_path: Path, doc_id: str, gt: str) -> DocumentRef:
    path = tmp_path / f"{doc_id}.gt.txt"
    path.write_text(gt, encoding="utf-8")
    return DocumentRef(
        id=doc_id,
        ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(path)),),
    )


def _stage(tmp_path: Path, doc_id: str, kind: ArtifactType, text: str) -> Artifact:
    suffix = "raw" if kind is ArtifactType.RAW_TEXT else "cor"
    path = tmp_path / f"{doc_id}.{suffix}.txt"
    path.write_text(text, encoding="utf-8")
    return _artifact(doc_id, kind, path)


def _witness_outputs(tmp_path: Path):
    corpus = CorpusSpec(
        name="c",
        documents=(
            _doc(tmp_path, "doc1", "le chat dort"),
            _doc(tmp_path, "doc2", "abc"),
        ),
    )
    outputs = {
        "chain": {
            "doc1": {
                ArtifactType.RAW_TEXT: _stage(
                    tmp_path, "doc1", ArtifactType.RAW_TEXT, "le chot dort"
                ),
                ArtifactType.CORRECTED_TEXT: _stage(
                    tmp_path, "doc1", ArtifactType.CORRECTED_TEXT, "le chat dort"
                ),
            },
            "doc2": {
                ArtifactType.RAW_TEXT: _stage(
                    tmp_path, "doc2", ArtifactType.RAW_TEXT, "abc"
                ),
                ArtifactType.CORRECTED_TEXT: _stage(
                    tmp_path, "doc2", ArtifactType.CORRECTED_TEXT, "abx"
                ),
            },
        }
    }
    return corpus, outputs


def test_witness_values_hand_derived(tmp_path: Path) -> None:
    corpus, outputs = _witness_outputs(tmp_path)
    analysis = correction_analysis(VIEW, corpus, outputs)
    assert analysis is not None
    payload = analysis.payload
    assert isinstance(payload, CorrectionPayload)
    (row,) = payload.pipelines
    assert row.pipeline == "chain" and row.n_documents == 2
    assert row.improvement_rate == pytest.approx(0.5)
    assert row.regression_rate == pytest.approx(0.5)
    assert row.no_change_rate == pytest.approx(0.0)
    assert row.pref_score == pytest.approx(0.0)
    assert row.n_catastrophic == 1
    assert row.catastrophic_rate == pytest.approx(0.5)
    assert row.pcis_macro == pytest.approx((1 / 11 - 1 / 3) / 2)
    assert row.pcis_median == pytest.approx((1 / 11 - 1 / 3) / 2)
    assert row.n_pcis_extreme == 0
    assert row.ccr == pytest.approx(2 / 15)
    assert row.change_ratio == pytest.approx(2.0)
    assert row.length_ratio == pytest.approx(1.0)
    assert row.n_overedited == 0
    assert row.char_ins_ratio == pytest.approx(0.0)
    assert (row.errors_before, row.errors_after) == (1, 1)
    assert (row.corrected, row.introduced, row.kept_wrong) == (1, 1, 0)
    assert row.correction_rate == pytest.approx(1.0)
    assert row.introduction_rate == pytest.approx(1.0)
    assert row.net_improvement == 0
    assert row.corrected_samples == ("chat",)
    assert row.introduced_samples == ("abc",)
    assert (row.n_correct_ocr_words, row.n_over_normalized) == (3, 1)
    assert row.over_normalization == pytest.approx(1 / 3)
    (over,) = row.over_normalized_samples
    assert (over.document_id, over.reference, over.corrected) == (
        "doc2",
        "abc",
        "abx",
    )
    (regression,) = row.worst_regressions
    assert regression.document_id == "doc2"
    assert regression.delta == pytest.approx(1 / 3)
    # doc2 : un seul bloc d'édition d'un caractère → médiane 1, max 1.
    assert row.edit_run_median == pytest.approx(1.0)
    assert row.edit_run_max == 1
    assert row.edit_run_share == pytest.approx(0.0)


def test_missing_corrected_stage_is_scored_empty(tmp_path: Path, caplog) -> None:
    """R-1.8 : l'étage corrigé absent est matérialisé vide (erreur maximale)."""
    corpus = CorpusSpec(name="c", documents=(_doc(tmp_path, "doc1", "xy"),))
    outputs = {
        "chain": {
            "doc1": {
                ArtifactType.RAW_TEXT: _stage(
                    tmp_path, "doc1", ArtifactType.RAW_TEXT, "xy"
                ),
            },
            # CORRECTED_TEXT ailleurs dans le pipeline → 2 étages quand même.
            "doc0": {
                ArtifactType.CORRECTED_TEXT: _stage(
                    tmp_path, "doc0", ArtifactType.CORRECTED_TEXT, "zz"
                ),
            },
        }
    }
    with caplog.at_level(logging.WARNING):
        analysis = correction_analysis(VIEW, corpus, outputs)
    assert analysis is not None
    (row,) = analysis.payload.pipelines
    assert row.n_missing_corrected == 1
    assert row.regression_rate == pytest.approx(1.0)
    assert row.n_catastrophic == 1  # Δ = 1.0 − 0.0
    assert "matérialisé" in caplog.text


def test_missing_raw_stage_pcis_is_clamped(tmp_path: Path) -> None:
    """q_brut = 0 (brut vide) → pcis = clamp(q_corrigé, −1, 1) — SPEC §4.2."""
    corpus = CorpusSpec(name="c", documents=(_doc(tmp_path, "doc1", "ab"),))
    outputs = {
        "chain": {
            "doc1": {
                ArtifactType.CORRECTED_TEXT: _stage(
                    tmp_path, "doc1", ArtifactType.CORRECTED_TEXT, "ab"
                ),
            },
        }
    }
    analysis = correction_analysis(VIEW, corpus, outputs)
    assert analysis is not None
    (row,) = analysis.payload.pipelines
    assert row.n_missing_raw == 1
    assert row.pcis_macro == pytest.approx(1.0)  # q_sys = 1, clampé
    assert row.improvement_rate == pytest.approx(1.0)


def test_long_edit_run_detected(tmp_path: Path) -> None:
    corpus = CorpusSpec(name="c", documents=(_doc(tmp_path, "doc1", "aaaa bbbb"),))
    outputs = {
        "chain": {
            "doc1": {
                ArtifactType.RAW_TEXT: _stage(
                    tmp_path, "doc1", ArtifactType.RAW_TEXT, "aaaa bbbb"
                ),
                ArtifactType.CORRECTED_TEXT: _stage(
                    tmp_path, "doc1", ArtifactType.CORRECTED_TEXT, "aaaa cccc"
                ),
            },
        }
    }
    analysis = correction_analysis(VIEW, corpus, outputs)
    assert analysis is not None
    (row,) = analysis.payload.pipelines
    # « bbbb » → « cccc » : un seul bloc de 4 substitutions consécutives.
    assert row.edit_run_median == pytest.approx(4.0)
    assert row.edit_run_max == 4
    assert row.edit_run_share == pytest.approx(0.0)  # 4 ≤ seuil 20


def test_mono_stage_pipeline_has_no_payload(tmp_path: Path) -> None:
    corpus = CorpusSpec(name="c", documents=(_doc(tmp_path, "doc1", "abc"),))
    outputs = {
        "ocr": {
            "doc1": {
                ArtifactType.RAW_TEXT: _stage(
                    tmp_path, "doc1", ArtifactType.RAW_TEXT, "abc"
                ),
            },
        }
    }
    assert correction_analysis(VIEW, corpus, outputs) is None


def test_through_evaluate_run(tmp_path: Path) -> None:
    corpus, outputs = _witness_outputs(tmp_path)
    registry = MetricRegistry()
    register_default_metrics(registry)
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=2,
        pipeline_specs=(
            PipelineSpec(name="chain", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(VIEW,), analyses="toutes"),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=manifest,
    )
    payloads = [
        analysis.payload
        for analysis in result.analyses
        if isinstance(analysis.payload, CorrectionPayload)
    ]
    assert len(payloads) == 1
    assert payloads[0].pipelines[0].change_ratio == pytest.approx(2.0)
