"""Bilan de **correction** : que vaut l'étage LLM d'un pipeline ? (couche 3)

Fonction d'analyse par vue (pattern ``calibration_analysis``) : pour chaque
pipeline **2 étages** (au moins un ``CORRECTED_TEXT`` produit), charge les
textes GT / brut / corrigé, les prépare **comme au scoring** (même
``prepare_text`` que le runner), et mesure sur les paires alignées :

- **triplet de non-régression** (signe de Δcmer par document, égalités
  strictes) + ``pref = improvement − regression`` + taux catastrophique ;
- **pcis** (SPEC §4.2 — non borné : macro + médiane + comptage |pcis| > 1) ;
- **ampleur d'intervention** (Koynov 2025) : CCR = MER(brut ↔ corrigé),
  ``change_ratio``, ``length_ratio``, drapeaux ``overedited`` ;
- **volume inséré** : ``char_ins_ratio`` = I/(H+S+D+I) sur (GT, corrigé) ;
- **absorption d'erreurs** (multiset de mots) : corrigées / introduites /
  conservées — le gain net ;
- **sur-normalisation** (positionnelle, mots) : mots OCR-justes dégradés ;
- **éditions consécutives** (R-2.6) : médiane/max/part des éditions en
  longues séquences — la signature d'une réécriture de passage.

R-1.8 : un étage absent est **matérialisé vide** (erreur maximale) + warning
et compté — jamais d'exclusion silencieuse. Un pipeline mono-étage n'a pas de
bilan (absence ≠ zéro muet).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping
from statistics import fmean, median

from rapidfuzz.distance import Levenshtein

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation._alignment import (
    aligned_to_reference,
    canonical_counts,
    char_mer,
)
from cinoc.evaluation.analysis import (
    Analysis,
    CorrectionPayload,
    OverNormalizedWord,
    PipelineCorrection,
    RegressionSample,
)
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.representations import load_representation, prepare_text

logger = logging.getLogger(__name__)

#: Δcmer au-delà duquel une régression est « catastrophique » (R-2.3).
_CATASTROPHIC_THRESHOLD = 0.10
#: ``change_ratio`` au-delà duquel le correcteur a sur-édité (R-1.9).
_OVEREDIT_THRESHOLD = 2.0
#: Part d'insertions au-delà de laquelle un document compte en « insertions
#: lourdes » (R-1.3, ``n_heavy_insertion``).
_HEAVY_INSERTION_THRESHOLD = 0.10
#: Longueur de séquence d'éditions au-delà de laquelle on parle de passage
#: réécrit (R-2.6).
_EDIT_RUN_THRESHOLD = 20
#: Plafonds d'échantillons embarqués (payload borné).
_MAX_TOKEN_SAMPLES = 12
_MAX_WORD_SAMPLES = 12
_MAX_REGRESSIONS = 10

_Outputs = Mapping[str, Mapping[str, Mapping[ArtifactType, Artifact]]]


def _edit_runs(reference: str, hypothesis: str) -> list[int]:
    """Longueurs des séquences d'éditions **consécutives** (blocs non-``equal``
    contigus de l'alignement) — une suppression suivie d'une insertion forme
    une seule séquence."""
    runs: list[int] = []
    current = 0
    for op in Levenshtein.opcodes(reference, hypothesis):
        if op.tag == "equal":
            if current:
                runs.append(current)
                current = 0
            continue
        current += max(op.src_end - op.src_start, op.dest_end - op.dest_start)
    if current:
        runs.append(current)
    return runs


def _missing(reference_words: list[str], words: list[str]) -> Counter[str]:
    """Occurrences de mots GT absentes de ``words`` (multiset, par mot)."""
    counts = Counter(words)
    out: Counter[str] = Counter()
    for word, n_ref in Counter(reference_words).items():
        lacking = n_ref - counts.get(word, 0)
        if lacking > 0:
            out[word] = lacking
    return out


def _text_of(
    outputs: _Outputs,
    pipeline: str,
    document_id: str,
    kind: ArtifactType,
    view: EvaluationView,
) -> str | None:
    artifact = outputs.get(pipeline, {}).get(document_id, {}).get(kind)
    if artifact is None or artifact.uri is None:
        return None
    try:
        return prepare_text(str(load_representation(artifact.uri, kind)), view)
    except EvaluationError as exc:
        # Une sortie illisible prive ce bilan d'un étage ; elle ne perd pas le
        # run (D9) : l'étage compte comme absent.
        logger.warning(
            "[correction] dégradé : sortie illisible (%s, %s) : %s",
            pipeline,
            document_id,
            exc,
        )
        return None


def _ground_truth(document: DocumentRef, view: EvaluationView) -> str | None:
    reference = document.gt_for(ArtifactType.RAW_TEXT)
    if reference is None:
        return None
    try:
        return prepare_text(
            str(load_representation(reference.uri, ArtifactType.RAW_TEXT)), view
        )
    except EvaluationError as exc:
        logger.warning(
            "[correction] dégradé : vérité terrain illisible (%s) : %s",
            document.id,
            exc,
        )
        return None


def _two_stage_pipelines(outputs: _Outputs) -> list[str]:
    return [
        pipeline
        for pipeline, by_document in outputs.items()
        if any(
            ArtifactType.CORRECTED_TEXT in artifacts
            for artifacts in by_document.values()
        )
    ]


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


class _CorrectionAccumulator:
    """État courant du bilan de correction d'un pipeline (**passe unique**).

    ``add`` agrège un document (textes déjà préparés ``prepare_text`` ; un étage
    absent = chaîne vide, compté R-1.8) ; ``build`` rend le ``PipelineCorrection``
    ou ``None`` si aucun document applicable. Les ~25 cumuls interdépendants sont
    regroupés ici : ``_pipeline_correction`` redevient une boucle lisible.
    """

    def __init__(self, pipeline: str) -> None:
        self.pipeline = pipeline
        self.n_documents = 0
        self.n_missing_raw = self.n_missing_corrected = 0
        self.improvement = self.regression = self.no_change = 0
        self.n_catastrophic = 0
        self.pcis_values: list[float] = []
        self.ccr_edits = self.ccr_total = 0
        self.n_overedited = 0
        self.sys_insertions = self.sys_total = 0
        self.n_heavy = 0
        self.corrected_len = self.reference_len = 0
        self.errors_before = self.errors_after = 0
        self.n_corrected = self.n_introduced = self.n_kept = 0
        self.corrected_tokens: set[str] = set()
        self.introduced_tokens: set[str] = set()
        self.n_correct_ocr = self.n_over_normalized = 0
        self.over_samples: list[OverNormalizedWord] = []
        self.runs: list[int] = []
        self.raw_edits = self.raw_total = 0
        self.regressions: list[RegressionSample] = []

    def add(
        self, document_id: str, reference: str, raw: str | None, corrected: str | None
    ) -> None:
        if raw is None:
            self.n_missing_raw += 1
            logger.warning(
                "[correction] %s · %s : étage brut absent — matérialisé vide "
                "(R-1.8).",
                self.pipeline,
                document_id,
            )
            raw = ""
        if corrected is None:
            self.n_missing_corrected += 1
            logger.warning(
                "[correction] %s · %s : étage corrigé absent — matérialisé "
                "vide (R-1.8).",
                self.pipeline,
                document_id,
            )
            corrected = ""
        self.n_documents += 1

        cmer_raw, raw_doc_edits, raw_doc_total = char_mer(reference, raw)
        self.raw_edits += raw_doc_edits
        self.raw_total += raw_doc_total
        s, d, i = canonical_counts(reference, corrected)
        sys_edits, sys_denom = s + d + i, len(reference) + i
        cmer_corrected = sys_edits / sys_denom if sys_denom else 0.0
        self.sys_insertions += i
        self.sys_total += sys_denom
        if sys_denom and i / sys_denom > _HEAVY_INSERTION_THRESHOLD:
            self.n_heavy += 1
        self.corrected_len += len(corrected)
        self.reference_len += len(reference)

        delta = cmer_corrected - cmer_raw
        if delta < 0:
            self.improvement += 1
        elif delta > 0:
            self.regression += 1
            self.regressions.append(
                RegressionSample(
                    document_id=document_id,
                    cmer_raw=cmer_raw,
                    cmer_corrected=cmer_corrected,
                    delta=delta,
                )
            )
        else:
            self.no_change += 1
        if delta > _CATASTROPHIC_THRESHOLD:
            self.n_catastrophic += 1

        # pcis (SPEC §4.2) : qualité q = 1 − cmer ; q_brut nul → clamp.
        q_raw, q_sys = 1.0 - cmer_raw, 1.0 - cmer_corrected
        self.pcis_values.append(
            max(-1.0, min(1.0, q_sys)) if q_raw == 0 else (q_sys - q_raw) / q_raw
        )

        ccr_doc, edits, total = char_mer(raw, corrected)
        self.ccr_edits += edits
        self.ccr_total += total
        if cmer_raw > 0 and ccr_doc / cmer_raw > _OVEREDIT_THRESHOLD:
            self.n_overedited += 1

        reference_words = reference.split()
        raw_words, corrected_words = raw.split(), corrected.split()
        missing_before = _missing(reference_words, raw_words)
        missing_after = _missing(reference_words, corrected_words)
        self.errors_before += sum(missing_before.values())
        self.errors_after += sum(missing_after.values())
        for word in set(missing_before) | set(missing_after):
            before, after = missing_before.get(word, 0), missing_after.get(word, 0)
            self.n_kept += min(before, after)
            if before > after:
                self.n_corrected += before - after
                self.corrected_tokens.add(word)
            elif after > before:
                self.n_introduced += after - before
                self.introduced_tokens.add(word)

        aligned_raw = aligned_to_reference(reference_words, raw_words)
        aligned_corrected = aligned_to_reference(reference_words, corrected_words)
        for index, word in enumerate(reference_words):
            if aligned_raw[index] != word:
                continue
            self.n_correct_ocr += 1
            if aligned_corrected[index] != word:
                self.n_over_normalized += 1
                if len(self.over_samples) < _MAX_WORD_SAMPLES:
                    self.over_samples.append(
                        OverNormalizedWord(
                            document_id=document_id,
                            reference=word[:64],
                            corrected=(aligned_corrected[index] or "∅")[:64],
                        )
                    )
        self.runs.extend(_edit_runs(reference, corrected))

    def build(self) -> PipelineCorrection | None:
        if self.n_documents == 0:
            return None
        cmer_raw_micro = _safe_ratio(self.raw_edits, self.raw_total)
        ccr_micro = _safe_ratio(self.ccr_edits, self.ccr_total)
        big_runs = sum(r for r in self.runs if r > _EDIT_RUN_THRESHOLD)
        return PipelineCorrection(
            pipeline=self.pipeline,
            n_documents=self.n_documents,
            n_missing_raw=self.n_missing_raw,
            n_missing_corrected=self.n_missing_corrected,
            improvement_rate=self.improvement / self.n_documents,
            regression_rate=self.regression / self.n_documents,
            no_change_rate=self.no_change / self.n_documents,
            pref_score=(self.improvement - self.regression) / self.n_documents,
            n_catastrophic=self.n_catastrophic,
            catastrophic_rate=self.n_catastrophic / self.n_documents,
            pcis_macro=fmean(self.pcis_values) if self.pcis_values else None,
            pcis_median=median(self.pcis_values) if self.pcis_values else None,
            n_pcis_extreme=sum(1 for value in self.pcis_values if abs(value) > 1),
            ccr=ccr_micro,
            change_ratio=(
                ccr_micro / cmer_raw_micro
                if ccr_micro is not None and cmer_raw_micro
                else None
            ),
            length_ratio=_safe_ratio(self.corrected_len, self.reference_len),
            n_overedited=self.n_overedited,
            char_ins_ratio=_safe_ratio(self.sys_insertions, self.sys_total),
            n_heavy_insertion=self.n_heavy,
            errors_before=self.errors_before,
            errors_after=self.errors_after,
            corrected=self.n_corrected,
            introduced=self.n_introduced,
            kept_wrong=self.n_kept,
            correction_rate=_safe_ratio(self.n_corrected, self.errors_before),
            introduction_rate=_safe_ratio(self.n_introduced, self.errors_after),
            net_improvement=self.n_corrected - self.n_introduced,
            corrected_samples=tuple(
                sorted(self.corrected_tokens)[:_MAX_TOKEN_SAMPLES]
            ),
            introduced_samples=tuple(
                sorted(self.introduced_tokens)[:_MAX_TOKEN_SAMPLES]
            ),
            n_correct_ocr_words=self.n_correct_ocr,
            n_over_normalized=self.n_over_normalized,
            over_normalization=_safe_ratio(self.n_over_normalized, self.n_correct_ocr),
            over_normalized_samples=tuple(self.over_samples),
            edit_run_median=float(median(self.runs)) if self.runs else None,
            edit_run_max=max(self.runs, default=0),
            edit_run_share=_safe_ratio(big_runs, sum(self.runs)),
            worst_regressions=tuple(
                sorted(self.regressions, key=lambda r: (-r.delta, r.document_id))[
                    :_MAX_REGRESSIONS
                ]
            ),
        )


def _pipeline_correction(
    pipeline: str, corpus: CorpusSpec, outputs: _Outputs, view: EvaluationView
) -> PipelineCorrection | None:
    acc = _CorrectionAccumulator(pipeline)
    for document in corpus.documents:
        reference = _ground_truth(document, view)
        if reference is None:
            continue
        raw = _text_of(outputs, pipeline, document.id, ArtifactType.RAW_TEXT, view)
        corrected = _text_of(
            outputs, pipeline, document.id, ArtifactType.CORRECTED_TEXT, view
        )
        acc.add(document.id, reference, raw, corrected)
    return acc.build()


def correction_analysis(
    view: EvaluationView, corpus: CorpusSpec, outputs: _Outputs
) -> Analysis | None:
    """Payload ``correction`` de la vue, ou ``None`` sans pipeline 2 étages."""
    rows = [
        row
        for pipeline in _two_stage_pipelines(outputs)
        if (row := _pipeline_correction(pipeline, corpus, outputs, view))
        is not None
    ]
    if not rows:
        return None
    return Analysis(
        scope="corpus",
        view=view.name,
        payload=CorrectionPayload(
            metric="cmer",
            catastrophic_threshold=_CATASTROPHIC_THRESHOLD,
            overedit_threshold=_OVEREDIT_THRESHOLD,
            insertion_threshold=_HEAVY_INSERTION_THRESHOLD,
            edit_run_threshold=_EDIT_RUN_THRESHOLD,
            pipelines=tuple(rows),
        ),
    )


__all__ = ["correction_analysis"]
