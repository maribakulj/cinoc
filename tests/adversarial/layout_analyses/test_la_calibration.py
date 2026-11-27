"""Contre-expertise — calibration jugée sur le **multi-ensemble** des mots de la VT.

``calibration.py`` déclare « correct » un jeton dont le mot reste disponible
dans le multi-ensemble des mots de la référence, sans alignement. La
littérature (Guo et al. 2017 : *accuracy* = la prédiction **de cette position**
est juste) et les outils OCR (ocrevalUAtion, dinglehopper) jugent un mot par
**alignement** avec la référence. Référence indépendante ici :
``difflib.SequenceMatcher(autojunk=False)`` sur les listes de mots — un mot est
correct s'il tombe dans un bloc ``equal`` de l'alignement.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.calibration import calibration_analysis

VIEW = EvaluationView(
    name="texte", candidate_types=frozenset({ArtifactType.RAW_TEXT}), metric_names=("cer",)
)


def _aligned_ece(reference: str, tokens: list[tuple[str, float]]) -> float:
    """ECE (10 bins) avec correction **par alignement** — calcul indépendant."""
    ref, hyp = reference.split(), [t for t, _ in tokens]
    correct = [False] * len(hyp)
    matcher = difflib.SequenceMatcher(a=ref, b=hyp, autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            correct[block.b + k] = True
    bins: dict[int, list[tuple[float, bool]]] = {}
    for (_, c), ok in zip(tokens, correct):
        bins.setdefault(min(int(c * 10), 9), []).append((c, ok))
    n = len(tokens)
    return sum(
        len(b) / n * abs(sum(ok for _, ok in b) / len(b) - sum(c for c, _ in b) / len(b))
        for b in bins.values()
    )


def _cinoc_ece(tmp: Path, reference: str, tokens: list[tuple[str, float]]) -> float:
    gt = tmp / "gt.txt"
    gt.write_text(reference, encoding="utf-8")
    conf = tmp / "conf.json"
    conf.write_text(json.dumps([{"text": t, "confidence": c} for t, c in tokens]), encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(DocumentRef(id="d", ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),)),),
    )
    outputs = {
        ArtifactType.CONFIDENCES: Artifact(id="d:ocr:conf", document_id="d", type=ArtifactType.CONFIDENCES, uri=str(conf))
    }
    analysis = calibration_analysis(VIEW, corpus, {"p": {"d": ("ocr", outputs)}})
    assert analysis is not None
    return analysis.payload.pipelines[0].ece  # type: ignore[union-attr]


def test_calibration_mots_permutes__correct_par_alignement(tmp_path: Path) -> None:
    """VT « un deux », jetons « deux »(0,95) « un »(0,95) : un seul mot alignable
    (exactitude 0,5) → ECE attendu 0,45, pas 0,05 (multi-ensemble : tout « juste »)."""
    tokens = [("deux", 0.95), ("un", 0.95)]
    expected = _aligned_ece("un deux", tokens)
    assert expected == pytest.approx(0.45)
    assert _cinoc_ece(tmp_path, "un deux", tokens) == pytest.approx(expected)


def test_calibration_mot_repete_deplace__correct_par_alignement(tmp_path: Path) -> None:
    """VT « de la ville de paris » ; l'OCR perd le 2ᵉ « de » et en insère un en fin :
    « de la ville paris de », tous à 0,99. Par alignement 4/5 justes → ECE 0,19 ;
    le multi-ensemble juge le « de » inséré juste → ECE 0,01."""
    reference = "de la ville de paris"
    tokens = [(w, 0.99) for w in "de la ville paris de".split()]
    expected = _aligned_ece(reference, tokens)
    assert expected == pytest.approx(0.19)
    assert _cinoc_ece(tmp_path, reference, tokens) == pytest.approx(expected)


def test_calibration_sans_desordre__multiensemble_et_alignement_concordent(tmp_path: Path) -> None:
    """Témoin (réfutation partielle) : sans permutation ni répétition, les deux
    jugements coïncident (VT « le chat noir », jetons « le chat nuit »)."""
    tokens = [("le", 0.9), ("chat", 0.8), ("nuit", 0.7)]
    assert _cinoc_ece(tmp_path, "le chat noir", tokens) == pytest.approx(
        _aligned_ece("le chat noir", tokens)
    )
