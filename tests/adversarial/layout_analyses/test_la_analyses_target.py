"""Contre-expertise — les analyses lisent-elles la **cible** de la vue ? (couche 3)

Affirmation 9 : ``correction_analysis`` et ``decisions_analysis`` consomment
les **pools finaux** (``latest_by_type`` de tout ``by_step``, ``runner.py``) et
non l'étape que la vue note (``EvaluationView.target_step``). On passe par
``evaluate_run`` en mode détaillé (``analyses="toutes"``), avec une chaîne
``ocr → correction → refine`` et trois vues : cible ``ocr``, cible
``correction``, défaut (étape la plus aval).

Textes (préparés ``flat_text``) :
    GT       « le chat dort »
    ocr      « le chat dart »   (1 mot faux)
    correction « le chat dort » (parfaite)
    refine   « le chien dort »  (régresse)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.analysis import (
    CalibrationPayload,
    CorrectionPayload,
    DecisionsPayload,
    DocumentTextsPayload,
    EconomicsPayload,
)
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.result import DocumentUsage, RunResult
from cinoc.evaluation.runner import evaluate_run

T = datetime(2026, 1, 1, tzinfo=UTC)
TEXT = frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT})
FINAL = EvaluationView(name="final", candidate_types=TEXT, metric_names=("cer",))
OCR_SEUL = FINAL.model_copy(update={"name": "ocr_seul", "target_step": "ocr"})
CORR_1 = FINAL.model_copy(update={"name": "correction_1", "target_step": "correction"})


def _art(tmp: Path, step: str, kind: ArtifactType, body: str) -> Artifact:
    path = tmp / f"{step}.{kind.value}"
    path.write_text(body, encoding="utf-8")
    return Artifact(id=f"d:{step}:{kind.value}", document_id="d", type=kind, uri=str(path))


def _decisions(tmp: Path, step: str, final: str) -> Artifact:
    body = json.dumps(
        {"document_id": "d", "lines": [{
            "document_id": "d", "page_id": "P1", "line_id": f"{step}.l1",
            "status": "corrected", "source_text": "le chat dart", "final_text": final,
            "proposed_text": final, "reason_code": None, "reason_detail": None,
        }]}
    )
    return _art(tmp, step, ArtifactType.DECISIONS, body)


def _run(tmp: Path, by_step: dict, *views: EvaluationView, usage=()) -> RunResult:
    gt = tmp / "gt.txt"
    gt.write_text("le chat dort", encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(DocumentRef(id="d", ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),)),),
    )
    registry = MetricRegistry()
    register_default_metrics(registry)
    return evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=views, analyses="toutes"),
        pipeline_outputs={"p": {"d": by_step}},
        registry=registry,
        manifest=RunManifest(
            run_id="r", corpus_name="c", n_documents=1,
            pipeline_specs=(PipelineSpec(name="p", initial_inputs=(ArtifactType.IMAGE,)),),
            code_version="1", started_at=T, completed_at=T,
        ),
        usage=usage,
    )


def _chain(tmp: Path) -> dict:
    return {
        "ocr": {
            ArtifactType.RAW_TEXT: _art(tmp, "ocr", ArtifactType.RAW_TEXT, "le chat dart"),
            ArtifactType.CONFIDENCES: _art(
                tmp, "ocr", ArtifactType.CONFIDENCES,
                json.dumps([{"text": "dart", "confidence": 0.9}]),
            ),
        },
        "correction": {
            ArtifactType.CORRECTED_TEXT: _art(tmp, "correction", ArtifactType.CORRECTED_TEXT, "le chat dort"),
            ArtifactType.DECISIONS: _decisions(tmp, "correction", "le chat dort"),
        },
        "refine": {
            ArtifactType.CORRECTED_TEXT: _art(tmp, "refine", ArtifactType.CORRECTED_TEXT, "le chien dort"),
            ArtifactType.DECISIONS: _decisions(tmp, "refine", "le chien dort"),
        },
    }


def _payload(result: RunResult, view: str, kind: type):
    found = [a.payload for a in result.analyses if a.view == view and isinstance(a.payload, kind)]
    return found[0] if found else None


def _cer(result: RunResult, view: str) -> float | None:
    return next(p.aggregate[0].value for p in result.pipelines if p.view == view)


# --- témoins : le scoring et les collecteurs suivent la cible -----------------

def test_score_et_collecteurs__suivent_target_step(tmp_path: Path) -> None:
    """Témoin : CER et ``document_texts`` (collecteur) lisent bien l'étape ciblée."""
    result = _run(tmp_path, _chain(tmp_path), OCR_SEUL, CORR_1, FINAL)
    assert _cer(result, "ocr_seul") == pytest.approx(1 / 12)
    assert _cer(result, "correction_1") == pytest.approx(0.0)
    assert _cer(result, "final") > 0
    texts = _payload(result, "ocr_seul", DocumentTextsPayload)
    assert texts.documents[0].hypotheses == (("p", "le chat dart"),)


def test_calibration__lit_les_confiances_de_l_etape_ciblee(tmp_path: Path) -> None:
    """Témoin : la calibration n'existe que sous la vue qui cible l'OCR (étape
    porteuse des confiances), attribuée à ``ocr``."""
    result = _run(tmp_path, _chain(tmp_path), OCR_SEUL, FINAL)
    assert _payload(result, "final", CalibrationPayload) is None
    calib = _payload(result, "ocr_seul", CalibrationPayload)
    assert calib is not None and calib.pipelines[0].step == "ocr"


# --- correction : pool final au lieu de la cible -----------------------------

@pytest.mark.valide
def test_correction_vue_cible_ocr__pas_de_bilan_hors_du_prefixe_evalue(tmp_path: Path) -> None:
    """Vue « OCR seul » (ablation : le préfixe s'arrête à l'OCR) : aucun étage de
    correction n'y est évalué, donc pas de bilan de correction sous cette vue."""
    result = _run(tmp_path, _chain(tmp_path), OCR_SEUL)
    assert _payload(result, "ocr_seul", CorrectionPayload) is None


@pytest.mark.valide
def test_correction_vue_cible_correction__lit_la_sortie_de_cette_etape(tmp_path: Path) -> None:
    """Vue ciblant ``correction`` (CER 0) : le bilan doit juger cette sortie
    (amélioration 1/1, 0 erreur de mot après), pas celle de ``refine``."""
    result = _run(tmp_path, _chain(tmp_path), CORR_1)
    assert _cer(result, "correction_1") == pytest.approx(0.0)
    row = _payload(result, "correction_1", CorrectionPayload).pipelines[0]
    assert (row.improvement_rate, row.regression_rate, row.errors_after) == (1.0, 0.0, 0)


@pytest.mark.valide
def test_correction_etape_brute_en_aval__le_brut_est_l_entree_du_correcteur(tmp_path: Path) -> None:
    """Chaîne réelle documentée par ``runner._scored_step`` : ``ocr → correction →
    projection`` (un RAW_TEXT **après** le CORRECTED_TEXT). Le « brut » du bilan doit
    être l'OCR (1 erreur de mot avant), pas le texte final reprojeté."""
    by_step = {
        "ocr": {ArtifactType.RAW_TEXT: _art(tmp_path, "ocr", ArtifactType.RAW_TEXT, "le chat dart")},
        "correction": {ArtifactType.CORRECTED_TEXT: _art(tmp_path, "correction", ArtifactType.CORRECTED_TEXT, "le chat dort")},
        "texte": {ArtifactType.RAW_TEXT: _art(tmp_path, "texte", ArtifactType.RAW_TEXT, "le chat dort")},
    }
    row = _payload(_run(tmp_path, by_step, FINAL), "final", CorrectionPayload).pipelines[0]
    assert (row.errors_before, row.improvement_rate) == (1, 1.0)


# --- décisions : pool final au lieu de la cible ------------------------------

@pytest.mark.valide
def test_decisions_vue_cible_ocr__pas_de_decisions_hors_du_prefixe(tmp_path: Path) -> None:
    """Vue « OCR seul » : les décisions d'un correcteur en aval n'y ont pas lieu."""
    result = _run(tmp_path, _chain(tmp_path), OCR_SEUL)
    assert _payload(result, "ocr_seul", DecisionsPayload) is None


@pytest.mark.valide
def test_decisions_vue_cible_correction__lit_les_decisions_de_cette_etape(tmp_path: Path) -> None:
    """Deux étapes publient des DECISIONS ; la vue cible la première : l'échantillon
    doit montrer sa ligne (``correction.l1``), pas celle de ``refine``."""
    result = _run(tmp_path, _chain(tmp_path), CORR_1)
    decisions = _payload(result, "correction_1", DecisionsPayload)
    assert [s.line_id for s in decisions.pipelines[0].samples] == ["correction.l1"]


# --- économie : coût du pipeline entier sous une vue de préfixe ---------------

@pytest.mark.discutable("C12-granularite-etape")
def test_economie_vue_cible_ocr__ne_facture_pas_l_etage_llm(tmp_path: Path) -> None:
    """Sous « OCR seul », le coût mis en regard du CER de l'OCR ne doit pas porter
    les jetons de l'étage LLM (l'OCR n'en consomme aucun)."""
    usage = (DocumentUsage(
        document_id="d", pipeline="p",
        usage=ResourceUsage(duration_seconds=2.0, tokens_in=1000, tokens_out=500),
    ),)
    result = _run(tmp_path, _chain(tmp_path), OCR_SEUL, FINAL, usage=usage)
    ocr_row = _payload(result, "ocr_seul", EconomicsPayload).pipelines[0]
    final_row = _payload(result, "final", EconomicsPayload).pipelines[0]
    assert ocr_row.cer != final_row.cer  # le CER suit bien la vue…
    assert ocr_row.tokens_in is None, (ocr_row.tokens_in, final_row.tokens_in)
