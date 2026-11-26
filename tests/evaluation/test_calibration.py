"""Calibration : ECE/MCE + analyse — valeurs dérivées **à la main** (§5.8b)."""

from __future__ import annotations

import json
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.evaluation.calibration import (
    calibration_analysis,
    calibration_from_pairs,
    load_confidence_tokens,
)


def test_ece_mce_hand_computed() -> None:
    # 4 jetons, un par bin : (0.95,T)=écart .05 ; (0.85,T)=.15 ; (0.75,F)=.75 ;
    # (0.05,F)=.05. ECE = ¼·(.05+.15+.75+.05)=0.25 ; MCE = 0.75.
    pairs = [(0.95, True), (0.85, True), (0.75, False), (0.05, False)]
    ece, mce, bins = calibration_from_pairs(pairs)
    assert ece == pytest.approx(0.25)
    assert mce == pytest.approx(0.75)
    assert len(bins) == 4
    assert all(b.count == 1 for b in bins)


def test_perfectly_calibrated_bin() -> None:
    # Bin [0.8;0.9[ : confiances 0.8/0.8/0.8/0.8/0.8, 4 corrects sur 5 → acc 0.8
    # = confiance moyenne → ECE 0.
    pairs = [(0.8, True)] * 4 + [(0.8, False)]
    ece, mce, bins = calibration_from_pairs(pairs)
    assert ece == pytest.approx(0.0)
    assert mce == pytest.approx(0.0)
    assert bins[0].accuracy == pytest.approx(0.8)


_VIEW = EvaluationView(name="texte", candidate_types=frozenset({ArtifactType.RAW_TEXT}))


def _setup(
    tmp_path: Path, tokens: list[dict[str, object]], gt_text: str = "le chat noir"
) -> tuple[CorpusSpec, dict]:
    gt = tmp_path / "d1.gt.txt"
    gt.write_text(gt_text, encoding="utf-8")
    sidecar = tmp_path / "d1.confidences.json"
    sidecar.write_text(json.dumps(tokens), encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="d1",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            ),
        ),
    )
    outputs = {
        "tess": {
            "d1": (
                "ocr",
                {
                    ArtifactType.CONFIDENCES: Artifact(
                        id="d1:tess:confidences",
                        document_id="d1",
                        type=ArtifactType.CONFIDENCES,
                        uri=str(sidecar),
                    )
                },
            )
        }
    }
    return corpus, outputs


def test_analysis_scores_tokens_against_reference_multiset(tmp_path: Path) -> None:
    # « chat » (0.9) est dans la GT → correct ; « chien » (0.7) absent → faux.
    corpus, outputs = _setup(
        tmp_path,
        [
            {"text": "chat", "confidence": 0.9},
            {"text": "chien", "confidence": 0.7},
        ],
    )
    analysis = calibration_analysis(_VIEW, corpus, outputs)
    assert analysis is not None
    row = analysis.payload.pipelines[0]  # type: ignore[union-attr]
    assert row.pipeline == "tess" and row.n_tokens == 2
    # L'étape dont les confiances sont mesurées est nommée (D-285, D9).
    assert row.step == "ocr"
    # Écarts : |1−0.9|=0.1 et |0−0.7|=0.7 → ECE ½·0.8 = 0.4 ; MCE 0.7.
    assert row.ece == pytest.approx(0.4)
    assert row.mce == pytest.approx(0.7)


def test_no_sidecar_yields_none(tmp_path: Path) -> None:
    corpus, outputs = _setup(tmp_path, [])
    assert calibration_analysis(_VIEW, corpus, outputs) is None


def test_reference_and_token_are_prepared_like_the_score(tmp_path: Path) -> None:
    """D-285 : la GT est lue sous le profil de la vue, le jeton aussi.

    GT en NFC, jeton du moteur en NFD : le CER de la vue (NFC) n'y voit pas
    d'erreur ; la calibration lisait la GT brute et jugeait le mot faux —
    ECE 0,9 au lieu de 0,1 sur ce cas.
    """
    nfd = unicodedata.normalize("NFD", "café")
    corpus, outputs = _setup(
        tmp_path, [{"text": nfd, "confidence": 0.9}], gt_text="un café noir"
    )
    analysis = calibration_analysis(_VIEW, corpus, outputs)
    assert analysis is not None
    row = analysis.payload.pipelines[0]  # type: ignore[union-attr]
    assert row.bins[0].accuracy == 1.0
    assert row.ece == pytest.approx(0.1)
    # Sous la comparaison brute, le mot redevient faux : c'est bien la vue qui
    # décide, pas un NFC caché.
    raw = _VIEW.model_copy(update={"normalization_profile": None})
    raw_row = calibration_analysis(raw, corpus, outputs).payload.pipelines[0]  # type: ignore[union-attr]
    assert raw_row.bins[0].accuracy == 0.0


def test_token_erased_by_the_view_is_not_judged(tmp_path: Path) -> None:
    corpus, outputs = _setup(
        tmp_path,
        [{"text": "chat", "confidence": 0.9}, {"text": "—", "confidence": 0.2}],
    )
    view = _VIEW.model_copy(update={"char_exclude": "—"})
    analysis = calibration_analysis(view, corpus, outputs)
    assert analysis is not None
    assert analysis.payload.pipelines[0].n_tokens == 1  # type: ignore[union-attr]


def test_bin_boundaries_are_half_open_but_the_last_is_closed() -> None:
    """Convention documentée : [b/10 ; (b+1)/10[, dernier bin [0,9 ; 1,0]."""
    _, _, bins = calibration_from_pairs([(0.3, True), (1.0, True), (0.0, False)])
    assert [(b.lower, b.upper) for b in bins] == [(0.0, 0.1), (0.3, 0.4), (0.9, 1.0)]
    _, _, (just_below,) = calibration_from_pairs([(0.29999, True)])
    assert (just_below.lower, just_below.upper) == (0.2, 0.3)


def test_unreadable_sidecar_degrades_to_empty() -> None:
    artifact = Artifact(
        id="x", document_id="d1", type=ArtifactType.CONFIDENCES,
        uri="/nonexistent/conf.json",
    )
    assert load_confidence_tokens(artifact) == []


def _artifact(tmp_path: Path, name: str, kind: ArtifactType, body: str) -> Artifact:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return Artifact(id=f"d1:{name}", document_id="d1", type=kind, uri=str(path))


def test_chain_does_not_borrow_the_ocr_calibration(tmp_path: Path) -> None:
    """D-285 (pilote D9) : sous OCR → LLM, la vue note le texte corrigé.

    L'ECE de l'OCR amont s'affichait sous le nom du pipeline corrigé (0,1234,
    identique à Tesseract seul). Les confiances sont celles de l'étape notée :
    l'étape LLM n'en a pas, le pipeline n'a pas de ligne ; nommer l'étape OCR
    en ``target_step`` la rend, attribuée à ``ocr``.
    """
    from cinoc.domain.pipeline import PipelineSpec
    from cinoc.domain.run import RunManifest
    from cinoc.evaluation.analysis import CalibrationPayload
    from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
    from cinoc.evaluation.runner import evaluate_run

    corpus, _ = _setup(tmp_path, [])
    tokens = json.dumps([{"text": "chat", "confidence": 0.9}])
    ocr = {
        ArtifactType.RAW_TEXT: _artifact(
            tmp_path, "ocr.txt", ArtifactType.RAW_TEXT, "le chat noir"
        ),
        ArtifactType.CONFIDENCES: _artifact(
            tmp_path, "conf.json", ArtifactType.CONFIDENCES, tokens
        ),
    }
    llm = {
        ArtifactType.CORRECTED_TEXT: _artifact(
            tmp_path, "llm.txt", ArtifactType.CORRECTED_TEXT, "le chat noir"
        )
    }
    outputs = {"tess": {"d1": {"ocr": ocr}}, "chaine": {"d1": {"ocr": ocr, "llm": llm}}}
    registry = MetricRegistry()
    register_default_metrics(registry)
    candidates = frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT})
    final = EvaluationView(
        name="texte", candidate_types=candidates, metric_names=("cer",)
    )
    amont = final.model_copy(update={"name": "ocr seul", "target_step": "ocr"})
    when = datetime(2026, 1, 1, tzinfo=UTC)
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(final, amont), analyses=("calibration",)),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=1,
            pipeline_specs=tuple(
                PipelineSpec(name=n, initial_inputs=(ArtifactType.IMAGE,))
                for n in ("tess", "chaine")
            ),
            code_version="1.0",
            started_at=when,
            completed_at=when,
        ),
    )
    rows = {
        analysis.view: [(r.pipeline, r.step) for r in analysis.payload.pipelines]
        for analysis in result.analyses
        if isinstance(analysis.payload, CalibrationPayload)
    }
    assert rows == {
        "texte": [("tess", "ocr")],
        "ocr seul": [("chaine", "ocr"), ("tess", "ocr")],
    }
