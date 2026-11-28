"""États d'exécution lus par l'évaluation, supports et grappes (tranche 1b).

L'évaluation **lit** l'état déclaré par l'étape (``DocumentUsage``) et ne le
reconstruit jamais : ces tests posent la lecture par étape (``view_outcome``),
le refus des vérités terrain absentes, les unités du critère D^M et les grappes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CorpusSpecError
from cinoc.domain.evaluation import EvaluationSpec
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.result import DocumentUsage
from cinoc.evaluation.scoring import missing_ground_truths, view_outcome
from cinoc.evaluation.statistics import (
    EditCounts,
    MatchCounts,
    Proportion,
    invented_units,
    reference_defines,
)
from tests.evaluation.test_runner import TEXT_VIEW


def _unit(outcome: str, **fields: object) -> DocumentUsage:
    return DocumentUsage(
        document_id="d",
        pipeline="p",
        usage=ResourceUsage(),
        outcome=outcome,  # type: ignore[arg-type]
        **fields,  # type: ignore[arg-type]
    )


STEPS = ["__initial__", "ocr", "corr"]


def test_a_view_reads_the_declared_state_of_its_own_step() -> None:
    """Une correction aval coupée laisse la lecture amont complète ; une étape
    amont incomplète rend incomplet ce qui en dérive."""
    cut = _unit("truncated", step_issues={"corr": "truncated"})
    assert view_outcome(cut, STEPS, "ocr") == "ok"
    assert view_outcome(cut, STEPS, "corr") == "truncated"
    upstream = _unit("partial", step_issues={"ocr": "partial", "corr": "truncated"})
    assert view_outcome(upstream, STEPS, "corr") == "partial"
    assert view_outcome(upstream, STEPS, "__initial__") == "ok"


def test_without_named_steps_the_unit_outcome_applies_to_every_view() -> None:
    assert view_outcome(_unit("partial"), STEPS, "ocr") == "partial"
    assert view_outcome(_unit("failed", reason="engine"), STEPS, "ocr") == "failed"
    assert view_outcome(None, STEPS, "ocr") == "ok"


def test_references_absent_from_the_disk_are_named_before_any_call(
    tmp_path: Path,
) -> None:
    present = tmp_path / "a.gt.txt"
    present.write_text("abc", encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="a",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(present)),
                ),
            ),
            DocumentRef(
                id="b",
                ground_truths=(
                    GroundTruthRef(
                        type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "b.gt.txt")
                    ),
                ),
            ),
        ),
    )
    registry = MetricRegistry()
    register_default_metrics(registry)
    missing = missing_ground_truths(
        corpus, EvaluationSpec(views=(TEXT_VIEW,)), registry
    )
    assert missing == [("b", str(tmp_path / "b.gt.txt"))]


def test_the_reference_alone_defines_the_macro_support() -> None:
    blank = EditCounts(substitutions=0, deletions=0, insertions=5, reference_length=0)
    read = EditCounts(substitutions=1, deletions=0, insertions=0, reference_length=4)
    assert reference_defines(blank) is False
    assert reference_defines(read)
    assert reference_defines(MatchCounts(tp=0, fp=7, fn=0)) is False
    assert reference_defines(MatchCounts(tp=0, fp=0, fn=1))
    assert reference_defines(Proportion(count=0, total=0)) is False


def test_the_invented_unit_is_declared_by_family() -> None:
    assert invented_units(
        EditCounts(substitutions=0, deletions=0, insertions=5, reference_length=0)
    ) == ("insertions", 5)
    assert invented_units(MatchCounts(tp=1, fp=3, fn=0)) == ("false_positives", 3)
    assert invented_units(Proportion(count=1, total=2)) is None


def test_cluster_weighting_needs_declared_clusters() -> None:
    with pytest.raises(CorpusSpecError, match="grappe"):
        CorpusSpec(
            name="c",
            documents=(DocumentRef(id="a"),),
            cluster_weighting="cluster",
        )
