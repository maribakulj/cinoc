"""Préservation des marqueurs : containment + expansion, valeurs main.

Réparation R3 vérifiée : un développement ne matche qu'en **mot entier**
(« per » ne compte pas dans « permettre »).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import PhilologyPayload
from cinoc.evaluation.markers import (
    ABBREVIATIONS,
    EARLY_MODERN,
    MarkerCollector,
    family_counts,
    positional_counts,
)
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def test_strict_preservation_multiset() -> None:
    counts = family_counts(ABBREVIATIONS, "ꝑ et ꝑ", "ꝑ et X")
    item = counts["ꝑ"]
    assert (item.n_total, item.n_strict) == (2, 1)  # 2 en GT, 1 reproduit


def test_expansion_counts_developed_form() -> None:
    counts = family_counts(ABBREVIATIONS, "ꝓ verbum", "pro verbum")
    item = counts["ꝓ"]
    assert item.n_total == 1
    assert item.n_strict == 0  # signe absent de l'hyp
    assert item.n_expansion == 1  # « pro » développé


def test_r3_expansion_requires_whole_word() -> None:
    """« per » ne doit PAS matcher dans « permettre » (bug source réparé)."""
    counts = family_counts(ABBREVIATIONS, "ꝑ", "permettre")
    item = counts["ꝑ"]
    assert item.n_expansion == 0  # aucun mot entier « per »/« par »
    # En mot entier, en revanche, ça compte.
    assert family_counts(ABBREVIATIONS, "ꝑ", "per omnia")["ꝑ"].n_expansion == 1


def test_expansion_is_optimistic_upper_bound() -> None:
    """Capé au total GT : 1 ⁊ en GT, plusieurs « et » → 1 (pas plus)."""
    counts = family_counts(ABBREVIATIONS, "⁊", "et et et")
    assert counts["⁊"].n_expansion == 1


def test_combining_sign_matched_in_nfc() -> None:
    counts = family_counts(ABBREVIATIONS, "p̃", "p̃")
    assert counts["p̃"].n_strict == 1


def test_no_signal_returns_empty() -> None:
    assert family_counts(ABBREVIATIONS, "texte moderne", "texte") == {}


def test_collector_aggregates_micro() -> None:
    collector = MarkerCollector()
    collector.observe("eng", "ꝑ et ꝓ", "ꝑ et pro")
    collector.observe("eng", "ꝑ encore", "par encore")
    analysis = collector.build("text")
    assert analysis is not None
    payload = analysis.payload
    assert isinstance(payload, PhilologyPayload)
    (row,) = payload.pipelines
    assert row.family == "abbreviations"
    by_sign = {m.sign: m for m in row.markers}
    # ꝑ : 2 en GT (1 strict « ꝑ » + 1 développé « par »).
    assert by_sign["ꝑ"].n_total == 2
    assert by_sign["ꝑ"].n_strict == 1
    assert by_sign["ꝑ"].n_expansion == 2
    # ꝓ : 1 en GT, développé « pro ».
    assert by_sign["ꝓ"].n_strict == 0
    assert by_sign["ꝓ"].n_expansion == 1
    assert row.n_total == 3


def test_collector_silent_without_signal() -> None:
    collector = MarkerCollector()
    collector.observe("eng", "bonjour", "bonjour")
    assert collector.build("text") is None


def test_positional_preserved_when_identical() -> None:
    counts = positional_counts(EARLY_MODERN, "meſme", "meſme")
    item = counts["long_s"]
    assert (item.n_total, item.n_strict, item.n_expansion) == (1, 1, 1)


def test_positional_lost_under_substitution() -> None:
    """``ſ`` (index 2) substitué par ``s`` → hors opcode equal → perdu."""
    counts = positional_counts(EARLY_MODERN, "meſme", "mesme")
    item = counts["long_s"]
    assert item.n_total == 1
    assert item.n_strict == 0  # un seul score : préservation


def test_positional_per_category() -> None:
    """``ﬁ`` (index 0) préservé, ``ſ`` (index 2) perdu — deux catégories."""
    counts = positional_counts(EARLY_MODERN, "ﬁ ſ", "ﬁ s")
    assert counts["ligatures"].n_total == 1
    assert counts["ligatures"].n_strict == 1
    assert counts["long_s"].n_total == 1
    assert counts["long_s"].n_strict == 0


def test_positional_nfc_collapses_decomposed_tilde() -> None:
    """``a`` + U+0303 (décomposé) ramené à ``ã`` par NFC, puis détecté/préservé."""
    counts = positional_counts(EARLY_MODERN, "cãpo", "cãpo")
    item = counts["nasal_tildes"]
    assert (item.n_total, item.n_strict) == (1, 1)


def test_positional_no_signal_returns_empty() -> None:
    assert positional_counts(EARLY_MODERN, "texte moderne", "texte") == {}


def test_collector_mixes_strategies() -> None:
    """Une famille containment + une famille positionnelle, sur deux documents."""
    collector = MarkerCollector()
    collector.observe("eng", "ꝑ omnia", "per omnia")  # abréviation développée
    collector.observe("eng", "meſme ﬁn", "mesme ﬁn")  # ſ perdu, ﬁ préservé
    analysis = collector.build("text")
    assert analysis is not None
    assert isinstance(analysis.payload, PhilologyPayload)
    by_family = {row.family: row for row in analysis.payload.pipelines}
    assert set(by_family) == {"abbreviations", "early_modern"}
    early = by_family["early_modern"]
    by_cat = {m.sign: m for m in early.markers}
    assert by_cat["long_s"].n_strict == 0
    assert by_cat["ligatures"].n_strict == 1
    assert early.n_total == 2  # un ſ + un ﬁ
    assert early.n_strict == 1


def test_through_evaluate_run(tmp_path: Path) -> None:
    gt = tmp_path / "doc1.gt.txt"
    gt.write_text("ꝑ omnia ꝓ nobis", encoding="utf-8")
    hyp = tmp_path / "doc1.hyp.txt"
    hyp.write_text("per omnia pro nobis", encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="doc1",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
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
                    uri=str(hyp),
                )
            }
        }
    }
    registry = MetricRegistry()
    register_default_metrics(registry)
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(
            PipelineSpec(name="eng", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,), analyses="toutes"),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=manifest,
    )
    payloads = [
        a.payload for a in result.analyses if isinstance(a.payload, PhilologyPayload)
    ]
    assert len(payloads) == 1
    (row,) = payloads[0].pipelines
    # Tout développé, rien strict (les signes sont devenus du latin).
    assert row.n_total == 2
    assert row.n_strict == 0
    assert row.n_expansion == 2


def test_early_modern_through_evaluate_run(tmp_path: Path) -> None:
    """Le runner câble la famille positionnelle : ``ﬁ`` préservé, ``ſ`` perdu."""
    gt = tmp_path / "doc1.gt.txt"
    gt.write_text("meſme ﬁn", encoding="utf-8")
    hyp = tmp_path / "doc1.hyp.txt"
    hyp.write_text("mesme ﬁn", encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="doc1",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
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
                    uri=str(hyp),
                )
            }
        }
    }
    registry = MetricRegistry()
    register_default_metrics(registry)
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(
            PipelineSpec(name="eng", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,), analyses="toutes"),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=manifest,
    )
    payloads = [
        a.payload for a in result.analyses if isinstance(a.payload, PhilologyPayload)
    ]
    assert len(payloads) == 1
    # GT sans abréviation → seule la famille positionnelle apparaît (adaptatif).
    (row,) = payloads[0].pipelines
    assert row.family == "early_modern"
    by_cat = {m.sign: m for m in row.markers}
    assert by_cat["ligatures"].n_strict == 1
    assert by_cat["long_s"].n_strict == 0
    assert row.n_total == 2
    assert row.n_strict == 1
