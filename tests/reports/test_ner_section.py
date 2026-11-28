"""Section ner : F1 global + par catégorie + échantillons, ``None`` sans payload."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    EntityCategoryScore,
    EntityMention,
    NerPayload,
    PipelineNer,
)
from cinoc.evaluation.result import RunResult
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.ner import NerSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=2,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def _result() -> RunResult:
    payload = NerPayload(
        iou_threshold=0.5,
        pipelines=(
            PipelineNer(
                pipeline="alpha",
                n_reference=10,
                true_positives=7,
                false_positives=2,
                false_negatives=3,
                precision=7 / 9,
                recall=0.7,
                f1=0.737,
                per_category=(
                    EntityCategoryScore(
                        label="PER", precision=0.8, recall=0.75, f1=0.77, support=8
                    ),
                ),
                missed=(EntityMention(label="LOC", text="Bourgogne"),),
                hallucinated=(EntityMention(label="PER", text="Charles"),),
            ),
        ),
    )
    return RunResult(
        manifest=_manifest(),
        analyses=(Analysis(scope="corpus", view="entities", payload=payload),),
    )


def test_renders_global_categories_and_samples() -> None:
    html = NerSection().render(_result(), SectionContext())
    assert html is not None
    assert "Entités nommées" in html
    assert "conjointe" in html  # caveat OCR + NER documenté
    assert "alpha" in html
    assert "70,0%" in html  # rappel global
    assert "7/2/3" in html  # TP/FP/FN
    assert "PER" in html and "support" in html  # bloc par catégorie
    assert "Bourgogne (LOC)" in html  # entité manquée
    assert "Charles (PER)" in html  # entité hallucinée
    # Déterminisme bit-à-bit.
    assert html == NerSection().render(_result(), SectionContext())


def test_renders_english_labels() -> None:
    html = NerSection().render(_result(), SectionContext(lang="en"))
    assert html is not None
    assert "Named entities" in html and "Entités nommées" not in html
    assert "joint" in html and "conjointe" not in html  # caveat OCR + NER
    assert "recall" in html and "rappel" not in html
    assert "F1 per category" in html and "F1 par catégorie" not in html


def test_no_payload_returns_none() -> None:
    section = NerSection()
    assert section.render(RunResult(manifest=_manifest()), SectionContext()) is None


def test_a_predicted_only_category_reads_undefined_recall() -> None:
    """M3 (tranche 1a) : une catégorie seulement prédite (support 0) a P = 0
    et un rappel indéfini — rendu « indéfini », jamais un faux 0 % ni une
    erreur."""
    base = _result()
    payload = base.analyses[0].payload
    assert isinstance(payload, NerPayload)
    row = payload.pipelines[0].model_copy(
        update={
            "per_category": (
                EntityCategoryScore(
                    label="LOC", precision=0.0, recall=None, f1=0.0, support=0
                ),
            )
        }
    )
    result = base.model_copy(
        update={
            "analyses": (
                Analysis(
                    scope="corpus",
                    view="entities",
                    payload=payload.model_copy(update={"pipelines": (row,)}),
                ),
            )
        }
    )
    html = NerSection().render(result, SectionContext())
    assert html is not None and "indéfini" in html
    english = NerSection().render(result, SectionContext(lang="en"))
    assert english is not None and "undefined" in english
