"""Archives modernes : détection bornée + containment multiset, valeurs main.

Vérifie les frontières de mot (``arr.`` ≠ « arracher »), la lentille
strict/expansion, le comptage multiset et le câblage runner (famille
``modern_archives``, stratégie ``archival``).
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
from cinoc.evaluation.archives import CATEGORY_ORDER, archival_counts
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def test_strict_preserved() -> None:
    assert archival_counts("Mme Dupont", "Mme Dupont") == {"civility_titles": (1, 1, 1)}


def test_strict_lost_but_expansion_present() -> None:
    """« Mme » → « Madame » : strict perdu, développement présent."""
    assert archival_counts("Mme Dupont", "Madame Dupont") == {
        "civility_titles": (1, 0, 1)
    }


def test_word_boundary_blocks_false_positive() -> None:
    """« arr. » (point requis) ne se détecte PAS dans « arracher »."""
    assert archival_counts("arracher le sol", "arracher") == {}
    # Avec le point et la frontière, en revanche, c'est détecté.
    assert archival_counts("arr. 5", "arr. 5") == {"administrative": (1, 1, 1)}


def test_multiset_counts_occurrences() -> None:
    """Deux « Mme » en GT, un seul restitué (l'autre devient « Mlle »)."""
    counts = archival_counts("Mme et Mme", "Mme et Mlle")
    assert counts == {"civility_titles": (2, 1, 1)}


def test_greedy_longest_wins_no_double_count() -> None:
    """« S.A.R. » compté une fois (pas « S. » + suffixes)."""
    assert archival_counts("S.A.R. arrive", "S.A.R. arrive") == {
        "civility_titles": (1, 1, 1)
    }


def test_typographic_punctuation_pair() -> None:
    counts = archival_counts("« mot »", "« mot »")
    assert counts == {"typographic_punctuation": (2, 2, 2)}


def test_ordinal_superscript() -> None:
    counts = archival_counts("le XIXᵉ siècle", "le XIXᵉ siècle")
    assert counts == {"ordinals": (1, 1, 1)}


def test_no_signal_returns_empty() -> None:
    assert archival_counts("texte sans marqueur", "texte") == {}


def test_category_order_is_canonical() -> None:
    assert CATEGORY_ORDER[0] == "civility_titles"
    assert "address" in CATEGORY_ORDER
    assert len(CATEGORY_ORDER) == 9


def test_through_evaluate_run(tmp_path: Path) -> None:
    """Le runner câble la famille archival : une catégorie présente apparaît."""
    gt = tmp_path / "doc1.gt.txt"
    gt.write_text("Mme Dupont", encoding="utf-8")
    hyp = tmp_path / "doc1.hyp.txt"
    hyp.write_text("Mme Dupont", encoding="utf-8")
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
    assert row.family == "modern_archives"
    (marker,) = row.markers
    assert marker.sign == "civility_titles"
    assert (marker.n_total, marker.n_strict, marker.n_expansion) == (1, 1, 1)
