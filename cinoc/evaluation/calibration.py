"""Calibration des confidences moteur : ECE / MCE + bins (couche 3).

Un moteur **calibré** a raison à hauteur de ce qu'il annonce : parmi les mots
déclarés à 0,9 de confiance, ~90 % sont corrects. ECE (Expected Calibration
Error) = Σ (n_b/N)·|acc_b − conf_b| sur des bins de confiance ; MCE = l'écart
maximal. Référence : Guo et al. 2017 (*On Calibration of Modern Neural
Networks*) — formules publiées, vérifiables à la main.

« Correct » = le mot du jeton apparaît **exactement** dans le multi-ensemble
des mots de la référence du document — proxy volontairement simple et
auditable (pas d'alignement positionnel : un mot juste mais déplacé reste
juste pour la recherche). Heuristique maison pour ce choix de proxy →
valeurs de test dérivées à la main (PLAN_PARITE §5.8b).

Consomme le sidecar ``CONFIDENCES`` (``ConfidenceToken``) produit par les
moteurs qui s'auto-estiment (tesseract) ; aucun jeton sur le run → pas
d'analyse (``None``), jamais un score fabriqué.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.corpus import CorpusSpec
from cinoc.evaluation.analysis import (
    Analysis,
    CalibrationBin,
    CalibrationPayload,
    PipelineCalibration,
)
from cinoc.formats.text import read_plaintext

#: Nombre de bins de fiabilité (convention usuelle).
N_BINS = 10

_TOKENS = TypeAdapter(list[ConfidenceToken])

#: { pipeline: { document_id: { ArtifactType: Artifact } } } — le **pool** de
#: chaque unité (sortie finale par type), que le runner déduit de ``by_step``.
_Pools = Mapping[str, Mapping[str, Mapping[ArtifactType, Artifact]]]


def load_confidence_tokens(artifact: Artifact) -> list[ConfidenceToken]:
    """Sidecar JSON → jetons ; illisible/invalide → ``[]`` (best-effort amont)."""
    if artifact.uri is None:
        return []
    try:
        return _TOKENS.validate_json(Path(artifact.uri).read_bytes())
    except (OSError, ValueError, ValidationError):
        return []


def calibration_from_pairs(
    pairs: list[tuple[float, bool]], n_bins: int = N_BINS
) -> tuple[float, float, tuple[CalibrationBin, ...]]:
    """``(ece, mce, bins)`` depuis des paires (confiance, correct)."""
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for confidence, correct in pairs:
        index = min(int(confidence * n_bins), n_bins - 1)
        buckets[index].append((confidence, correct))
    bins: list[CalibrationBin] = []
    ece = 0.0
    mce = 0.0
    total = len(pairs)
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        mean_confidence = sum(c for c, _ in bucket) / len(bucket)
        accuracy = sum(1 for _, ok in bucket if ok) / len(bucket)
        gap = abs(accuracy - mean_confidence)
        ece += len(bucket) / total * gap
        mce = max(mce, gap)
        bins.append(
            CalibrationBin(
                lower=index / n_bins,
                upper=(index + 1) / n_bins,
                mean_confidence=mean_confidence,
                accuracy=accuracy,
                count=len(bucket),
            )
        )
    return ece, mce, tuple(bins)


def _reference_words(document_id: str, corpus: CorpusSpec) -> Counter[str] | None:
    """Multi-ensemble des mots de la GT ``RAW_TEXT`` du document, si lisible."""
    for document in corpus.documents:
        if document.id != document_id:
            continue
        for truth in document.ground_truths:
            if truth.type is ArtifactType.RAW_TEXT and truth.uri:
                try:
                    text = read_plaintext(Path(truth.uri).read_bytes())
                except (OSError, ValueError):
                    return None
                return Counter(text.split())
    return None


def calibration_analysis(
    view: str,
    corpus: CorpusSpec,
    pipeline_outputs: _Pools,
) -> Analysis | None:
    """``Analysis`` calibration de la vue ; ``None`` sans jeton de confiance."""
    rows: list[PipelineCalibration] = []
    for pipeline in sorted(pipeline_outputs):
        pairs: list[tuple[float, bool]] = []
        for document_id, artifacts in sorted(pipeline_outputs[pipeline].items()):
            sidecar = artifacts.get(ArtifactType.CONFIDENCES)
            if sidecar is None:
                continue
            tokens = load_confidence_tokens(sidecar)
            if not tokens:
                continue
            reference = _reference_words(document_id, corpus)
            if reference is None:
                continue
            remaining = reference.copy()
            for token in tokens:
                correct = remaining[token.text] > 0
                if correct:
                    remaining[token.text] -= 1
                pairs.append((token.confidence, correct))
        if not pairs:
            continue
        ece, mce, bins = calibration_from_pairs(pairs)
        rows.append(
            PipelineCalibration(
                pipeline=pipeline,
                n_tokens=len(pairs),
                ece=ece,
                mce=mce,
                bins=bins,
            )
        )
    if not rows:
        return None
    payload = CalibrationPayload(n_bins=N_BINS, pipelines=tuple(rows))
    return Analysis(scope="corpus", view=view, payload=payload)


__all__ = [
    "N_BINS",
    "calibration_analysis",
    "calibration_from_pairs",
    "load_confidence_tokens",
]
