"""Calibration des confidences moteur : ECE / MCE + bins (couche 3).

Un moteur **calibré** a raison à hauteur de ce qu'il annonce : parmi les mots
déclarés à 0,9 de confiance, ~90 % sont corrects. ECE (Expected Calibration
Error) = Σ (n_b/N)·|acc_b − conf_b| sur des bins de confiance ; MCE = l'écart
maximal. Référence : Guo et al. 2017 (*On Calibration of Modern Neural
Networks*) — formules publiées, vérifiables à la main.

**Bins** : dix bins de largeur 0,1, le bin *b* = [b/10 ; (b+1)/10[, le dernier
**fermé** [0,9 ; 1,0] — indice ``min(⌊10·c⌋, 9)``, si bien qu'une confiance de
1,0 tombe dans le dernier, une de 0,3 dans [0,3 ; 0,4[. Un bin vide n'entre ni
dans l'ECE ni dans le MCE.

« Correct » = le mot du jeton apparaît **exactement** dans le multi-ensemble
des mots de la référence du document — proxy volontairement simple et
auditable (pas d'alignement positionnel : un mot juste mais déplacé reste
juste pour la recherche). Heuristique maison pour ce choix de proxy →
valeurs de test dérivées à la main (PLAN_PARITE §5.8b). **Mot et référence
sont préparés comme au scoring** (``prepare_text`` de la vue) : sous le profil
par défaut, un « é » décomposé du moteur et le « é » composé de la GT sont le
même mot, comme pour le CER (D-285). Un jeton que la vue efface entièrement
(``char_exclude``) n'est pas jugé.

**Quelle étape.** Les confiances sont celles de l'**étape que la vue note**
(``target_step``, sinon la plus aval qui produit un type candidat) : sous une
chaîne OCR → LLM, la vue note le texte corrigé, et l'ECE de l'OCR amont n'en
dit rien — il s'affichait pourtant sous le nom du pipeline corrigé (pilote BNL,
D-281 D9). Une étape notée sans sidecar ``CONFIDENCES`` ne donne pas de ligne ;
nommer l'étape OCR en ``target_step`` rend sa calibration.

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
from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.analysis import (
    Analysis,
    CalibrationBin,
    CalibrationPayload,
    PipelineCalibration,
)
from cinoc.evaluation.representations import prepare_text
from cinoc.formats.text import read_plaintext

#: Nombre de bins de fiabilité (convention usuelle).
N_BINS = 10

_TOKENS = TypeAdapter(list[ConfidenceToken])

#: { pipeline: { document_id: (étape notée, ses sorties) } } — ce que la vue
#: note de chaque unité, que le runner déduit de ``by_step``.
_Scored = Mapping[str, Mapping[str, tuple[str, Mapping[ArtifactType, Artifact]]]]


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


def _reference_words(
    document_id: str, corpus: CorpusSpec, view: EvaluationView
) -> Counter[str] | None:
    """Multi-ensemble des mots de la GT ``RAW_TEXT`` préparée par la vue."""
    for document in corpus.documents:
        if document.id != document_id:
            continue
        for truth in document.ground_truths:
            if truth.type is ArtifactType.RAW_TEXT and truth.uri:
                try:
                    text = read_plaintext(Path(truth.uri).read_bytes())
                except (OSError, ValueError):
                    return None
                return Counter(prepare_text(text, view).split())
    return None


def _judge(words: list[str], remaining: Counter[str]) -> bool:
    """Le jeton est juste si **tous** ses mots préparés restent dans la GT.

    Un jeton tient presque toujours en un mot ; un profil qui remplace la
    ponctuation par une espace peut en faire deux (« l'homme » → « l homme »).
    Juste, il consomme ses mots du multi-ensemble.
    """
    needed = Counter(words)
    if any(remaining[word] < count for word, count in needed.items()):
        return False
    remaining.subtract(needed)
    return True


def calibration_analysis(
    view: EvaluationView,
    corpus: CorpusSpec,
    scored: _Scored,
) -> Analysis | None:
    """``Analysis`` calibration de la vue ; ``None`` sans jeton de confiance.

    Une ligne par (pipeline, étape notée) qui porte des confiances.
    """
    pairs_by_row: dict[tuple[str, str], list[tuple[float, bool]]] = {}
    for pipeline in sorted(scored):
        for document_id, (step, outputs) in sorted(scored[pipeline].items()):
            sidecar = outputs.get(ArtifactType.CONFIDENCES)
            if sidecar is None:
                continue
            tokens = load_confidence_tokens(sidecar)
            if not tokens:
                continue
            reference = _reference_words(document_id, corpus, view)
            if reference is None:
                continue
            remaining = reference.copy()
            pairs = pairs_by_row.setdefault((pipeline, step), [])
            for token in tokens:
                words = prepare_text(token.text, view).split()
                if not words:
                    continue
                pairs.append((token.confidence, _judge(words, remaining)))
    rows: list[PipelineCalibration] = []
    for (pipeline, step), pairs in sorted(pairs_by_row.items()):
        if not pairs:
            continue
        ece, mce, bins = calibration_from_pairs(pairs)
        rows.append(
            PipelineCalibration(
                pipeline=pipeline,
                step=step,
                n_tokens=len(pairs),
                ece=ece,
                mce=mce,
                bins=bins,
            )
        )
    if not rows:
        return None
    payload = CalibrationPayload(n_bins=N_BINS, pipelines=tuple(rows))
    return Analysis(scope="corpus", view=view.name, payload=payload)


__all__ = [
    "N_BINS",
    "calibration_analysis",
    "calibration_from_pairs",
    "load_confidence_tokens",
]
