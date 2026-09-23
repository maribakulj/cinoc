"""Carte des mots : alignement, matrice + regroupements (valeurs **dérivées main**).

Aucune valeur n'est empruntée à une autre implémentation : chaque matrice et
chaque signature de regroupement est calculée au crayon sur des ref/hyp courts
(misses mot scriptés). L'alignement réutilise la tokenisation partagée et
``difflib`` (mêmes tags ``replace``/``delete`` que la modernisation lexicale).
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
from cinoc.evaluation.analysis import WordErrorPayload
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run
from cinoc.evaluation.word_errors import WordErrorCollector, word_misses

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


class TestWordMisses:
    def test_replace_yields_produced_form(self) -> None:
        # « roi » remplacé par « roy » : un raté, forme produite verbatim.
        assert word_misses("le roi", "le roy") == [("roi", "roy")]

    def test_delete_yields_empty_set_symbol(self) -> None:
        # « grand » supprimé (ancré par « le »/« roi ») → forme produite ∅.
        assert word_misses("le grand roi", "le roi") == [("grand", "∅")]

    def test_inserted_hypothesis_word_is_not_a_miss(self) -> None:
        # Mot hyp en trop = hallucination, pas un raté GT (mesure centrée GT).
        assert word_misses("le roi", "le roi extra") == []

    def test_equal_words_are_not_missed(self) -> None:
        assert word_misses("le roi noble", "le roi noble") == []

    def test_unbalanced_replace_extra_gt_words_deleted(self) -> None:
        # GT « a b c » → hyp « x » : replace apparié 1-à-1 (a→x), b et c en trop → ∅.
        assert word_misses("a b c", "x") == [("a", "x"), ("b", "∅"), ("c", "∅")]


class TestCollectorMatrix:
    def test_universal_and_engine_specific_groups_hand_derived(self) -> None:
        # ref « le prologve du roi » sur 3 moteurs :
        #  alpha « le prologue du roi » → rate prologve (→prologue)
        #  beta  « le prologe du roy »  → rate prologve (→prologe) ET roi (→roy)
        #  gamma « le prolog du roi »   → rate prologve (→prolog)
        # prologve : raté par 3/3 → universal (total 3) ; roi : 1/3 → engine_specific.
        collector = WordErrorCollector()
        collector.observe("alpha", "d1", "le prologve du roi", "le prologue du roi")
        collector.observe("beta", "d1", "le prologve du roi", "le prologe du roy")
        collector.observe("gamma", "d1", "le prologve du roi", "le prolog du roi")
        analysis = collector.build("text")
        assert analysis is not None
        assert analysis.scope == "corpus" and analysis.view == "text"
        payload = analysis.payload
        assert isinstance(payload, WordErrorPayload)
        assert payload.pipelines == ("alpha", "beta", "gamma")
        # Tri (-total, mot) : prologve (3) avant roi (1).
        assert [w.word for w in payload.words] == ["prologve", "roi"]
        prologve, roi = payload.words
        assert prologve.total_errors == 3 and prologve.group == "universal"
        assert [(e.pipeline, e.count, e.variant) for e in prologve.per_engine] == [
            ("alpha", 1, "prologue"),
            ("beta", 1, "prologe"),
            ("gamma", 1, "prolog"),
        ]
        assert roi.total_errors == 1 and roi.group == "engine_specific"
        assert [(e.pipeline, e.count, e.variant) for e in roi.per_engine] == [
            ("beta", 1, "roy")
        ]

    def test_partial_group_when_subset_misses(self) -> None:
        # 3 moteurs, « roi » raté par alpha et gamma (pas beta) → partial (2/3).
        collector = WordErrorCollector()
        collector.observe("alpha", "d1", "le roi", "le roy")
        collector.observe("beta", "d1", "le roi", "le roi")
        collector.observe("gamma", "d1", "le roi", "le rey")
        analysis = collector.build("text")
        assert analysis is not None
        (word,) = analysis.payload.words
        assert word.word == "roi" and word.group == "partial"
        assert [e.pipeline for e in word.per_engine] == ["alpha", "gamma"]

    def test_dominant_variant_is_most_frequent_form(self) -> None:
        # alpha rate « roi » 3×, produisant roy/roy/rey → variante dominante = roy.
        collector = WordErrorCollector()
        for doc, hyp in (("d1", "roy"), ("d2", "roy"), ("d3", "rey")):
            collector.observe("alpha", doc, "roi", hyp)
        collector.observe("beta", "d1", "roi", "roi")  # beta produit du texte, 0 raté
        analysis = collector.build("text")
        assert analysis is not None
        (word,) = analysis.payload.words
        assert word.total_errors == 3
        (engine,) = word.per_engine
        assert engine.pipeline == "alpha" and engine.count == 3
        assert engine.variant == "roy"  # 2 roy > 1 rey

    def test_words_capped_to_top_50_by_total_then_alpha(self) -> None:
        # 55 mots ratés 2× chacun (alpha+beta) → cap 50, tri alpha → w00..w49.
        collector = WordErrorCollector()
        for i in range(55):
            word = f"w{i:02d}"
            collector.observe("alpha", f"d{i}", word, "zz")
            collector.observe("beta", f"d{i}", word, "zz")
        analysis = collector.build("text")
        assert analysis is not None
        words = analysis.payload.words
        assert len(words) == 50
        assert [w.word for w in words] == [f"w{i:02d}" for i in range(50)]
        assert all(w.total_errors == 2 and w.group == "universal" for w in words)


class TestCollectorNone:
    def test_single_pipeline_yields_none(self) -> None:
        collector = WordErrorCollector()
        collector.observe("alpha", "d1", "le roi", "le roy")
        assert collector.build("text") is None

    def test_two_pipelines_without_errors_yield_none(self) -> None:
        collector = WordErrorCollector()
        collector.observe("alpha", "d1", "le roi", "le roi")
        collector.observe("beta", "d1", "le roi", "le roi")
        assert collector.build("text") is None

    def test_empty_collector_yields_none(self) -> None:
        assert WordErrorCollector().build("text") is None


# --- Bout en bout via ``evaluate_run`` -------------------------------------

_TEXT_VIEW = EvaluationView(
    name="text",
    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
    metric_names=("cer",),
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _doc(doc_id: str, gt: Path) -> DocumentRef:
    return DocumentRef(
        id=doc_id,
        ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),),
    )


def _candidate(document_id: str, uri: Path) -> Artifact:
    return Artifact(
        id=f"{document_id}:precomputed:raw_text",
        document_id=document_id,
        type=ArtifactType.RAW_TEXT,
        uri=str(uri),
    )


def _registry() -> MetricRegistry:
    registry = MetricRegistry()
    register_default_metrics(registry)
    return registry


def _manifest(names: tuple[str, ...]) -> RunManifest:
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=tuple(
            PipelineSpec(name=n, initial_inputs=(ArtifactType.IMAGE,)) for n in names
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def _word_error_payload(analyses):
    for analysis in analyses:
        if isinstance(analysis.payload, WordErrorPayload):
            return analysis.payload
    return None


def test_word_errors_present_through_evaluate_run(tmp_path: Path) -> None:
    gt = _write(tmp_path / "d1.gt.txt", "le roi noble")
    a = _write(tmp_path / "d1.a.txt", "le roy noble")  # rate roi
    b = _write(tmp_path / "d1.b.txt", "le roi nobel")  # rate noble
    corpus = CorpusSpec(name="c", documents=(_doc("d1", gt),))
    outputs = {
        "a": {"d1": {ArtifactType.RAW_TEXT: _candidate("d1", a)}},
        "b": {"d1": {ArtifactType.RAW_TEXT: _candidate("d1", b)}},
    }
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(_TEXT_VIEW,), analyses="toutes"),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=_manifest(("a", "b")),
    )
    payload = _word_error_payload(result.analyses)
    assert payload is not None
    assert payload.pipelines == ("a", "b")
    by_word = {w.word: w for w in payload.words}
    assert set(by_word) == {"roi", "noble"}
    assert by_word["roi"].group == "engine_specific"
    assert by_word["noble"].group == "engine_specific"


def test_word_errors_absent_with_single_pipeline(tmp_path: Path) -> None:
    gt = _write(tmp_path / "d1.gt.txt", "le roi noble")
    a = _write(tmp_path / "d1.a.txt", "le roy noble")
    corpus = CorpusSpec(name="c", documents=(_doc("d1", gt),))
    outputs = {"a": {"d1": {ArtifactType.RAW_TEXT: _candidate("d1", a)}}}
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(_TEXT_VIEW,), analyses="toutes"),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=_manifest(("a",)),
    )
    assert _word_error_payload(result.analyses) is None
