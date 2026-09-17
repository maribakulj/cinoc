"""Runner d'évaluation : agrégat + détail par-document, ``None`` si non applicable."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run import RunManifest
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.result import RunResult
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)
TEXT_VIEW = EvaluationView(
    name="text",
    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
    metric_names=("cer",),
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _doc(doc_id: str, gt: Path | None) -> DocumentRef:
    truths = ()
    if gt is not None:
        truths = (GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),)
    return DocumentRef(id=doc_id, ground_truths=truths)


def _candidate(document_id: str, uri: Path) -> Artifact:
    return Artifact(
        id=f"{document_id}:precomputed:raw_text",
        document_id=document_id,
        type=ArtifactType.RAW_TEXT,
        uri=str(uri),
    )


def _manifest(n: int) -> RunManifest:
    pipeline = PipelineSpec(name="eng", initial_inputs=(ArtifactType.IMAGE,))
    return RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=n,
        pipeline_specs=(pipeline,),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )


def _registry() -> MetricRegistry:
    registry = MetricRegistry()
    register_default_metrics(registry)
    return registry


def test_aggregate_and_per_document(tmp_path: Path) -> None:
    # doc1 : GT "abcd" vs "abxd" -> CER 1/4 ; doc2 : GT "ef" vs "ef" -> 0
    gt1 = _write(tmp_path / "doc1.gt.txt", "abcd")
    hyp1 = _write(tmp_path / "doc1.eng.txt", "abxd")
    gt2 = _write(tmp_path / "doc2.gt.txt", "ef")
    hyp2 = _write(tmp_path / "doc2.eng.txt", "ef")
    corpus = CorpusSpec(name="c", documents=(_doc("doc1", gt1), _doc("doc2", gt2)))
    outputs = {
        "eng": {
            "doc1": {ArtifactType.RAW_TEXT: _candidate("doc1", hyp1)},
            "doc2": {ArtifactType.RAW_TEXT: _candidate("doc2", hyp2)},
        }
    }
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(TEXT_VIEW,)),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=_manifest(2),
    )
    aggregate = result.pipelines[0].aggregate[0]
    assert aggregate.metric == "cer"
    assert aggregate.support == 2
    # micro = Σ erreurs / Σ longueurs = (1 + 0) / (4 + 2) = 1/6, PAS la moyenne
    # macro mean(0.25, 0.0) = 0.125 : un long document pèse plus (cf. _aggregate).
    assert aggregate.value == pytest.approx(1 / 6)
    assert len(result.documents) == 2
    # le détail par-document porte le poids (dénominateur) → macro reconstructible.
    doc1_cer = result.documents[0].scores[0]
    assert doc1_cer.value == pytest.approx(0.25)
    assert doc1_cer.support == 4  # longueur de la référence "abcd"


def test_missing_ground_truth_is_not_applicable(tmp_path: Path) -> None:
    hyp1 = _write(tmp_path / "doc1.eng.txt", "abc")
    corpus = CorpusSpec(name="c", documents=(_doc("doc1", None),))
    outputs = {"eng": {"doc1": {ArtifactType.RAW_TEXT: _candidate("doc1", hyp1)}}}
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(TEXT_VIEW,)),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=_manifest(1),
    )
    aggregate = result.pipelines[0].aggregate[0]
    assert aggregate.value is None
    assert aggregate.support == 0
    assert result.documents[0].scores[0].value is None


def test_normalization_profile_neutralises_case(tmp_path: Path) -> None:
    # vue "caseless" : "ABC DEF" (GT) vs "abc def" (hyp) → CER 0 (casse neutralisée)
    gt = _write(tmp_path / "doc1.gt.txt", "ABC DEF")
    hyp = _write(tmp_path / "doc1.eng.txt", "abc def")
    corpus = CorpusSpec(name="c", documents=(_doc("doc1", gt),))
    view = EvaluationView(
        name="caseless",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
        normalization_profile="caseless",
    )
    outputs = {"eng": {"doc1": {ArtifactType.RAW_TEXT: _candidate("doc1", hyp)}}}
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,)),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=_manifest(1),
    )
    assert result.pipelines[0].aggregate[0].value == 0.0


def test_unknown_normalization_profile_raises(tmp_path: Path) -> None:
    gt = _write(tmp_path / "doc1.gt.txt", "x")
    hyp = _write(tmp_path / "doc1.eng.txt", "x")
    corpus = CorpusSpec(name="c", documents=(_doc("doc1", gt),))
    view = EvaluationView(
        name="bad",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
        normalization_profile="does_not_exist",
    )
    outputs = {"eng": {"doc1": {ArtifactType.RAW_TEXT: _candidate("doc1", hyp)}}}
    with pytest.raises(EvaluationError):
        evaluate_run(
            corpus=corpus,
            evaluation=EvaluationSpec(views=(view,)),
            pipeline_outputs=outputs,
            registry=_registry(),
            manifest=_manifest(1),
        )


def test_candidate_precedence_prefers_corrected(tmp_path: Path) -> None:
    # Vue à 2 candidats : la précédence EXPLICITE choisit CORRECTED_TEXT (aval),
    # pas l'ordre alphabétique des valeurs d'enum.
    gt = _write(tmp_path / "d.gt.txt", "alpha")
    raw = _write(tmp_path / "d.raw.txt", "beta")  # CER > 0 si choisi
    corrected = _write(tmp_path / "d.corr.txt", "alpha")  # CER 0 si choisi
    corpus = CorpusSpec(name="c", documents=(_doc("d", gt),))
    view = EvaluationView(
        name="multi",
        candidate_types=frozenset(
            {ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT}
        ),
        metric_names=("cer",),
    )
    outputs = {
        "eng": {
            "d": {
                ArtifactType.RAW_TEXT: _candidate("d", raw),
                ArtifactType.CORRECTED_TEXT: Artifact(
                    id="d:llm:corrected_text",
                    document_id="d",
                    type=ArtifactType.CORRECTED_TEXT,
                    uri=str(corrected),
                ),
            }
        }
    }
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,)),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=_manifest(1),
    )
    assert result.pipelines[0].aggregate[0].value == 0.0  # CORRECTED choisi


def test_candidate_is_the_terminal_step_not_the_richest_type(tmp_path: Path) -> None:
    """Une correction **suivie** d'une remise en ordre : c'est la sortie finale
    qui est notée, pas l'intermédiaire corrigé.

    Défaut réel : un pipeline ``…→ correction VLM → ordre de lecture →
    projection`` publie un ``CORRECTED_TEXT`` au milieu et finit sur un
    ``RAW_TEXT``. La précédence par type notait le texte **d'avant** la remise en
    ordre — mêmes mots, mauvaise séquence.
    """
    gt = _write(tmp_path / "d.gt.txt", "alpha beta")
    corrigé = _write(tmp_path / "d.corr.txt", "beta alpha")  # mots justes, désordre
    final = _write(tmp_path / "d.raw.txt", "alpha beta")  # CER 0 si choisi
    corpus = CorpusSpec(name="c", documents=(_doc("d", gt),))
    view = EvaluationView(
        name="multi",
        candidate_types=frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT}),
        metric_names=("cer",),
    )
    pipeline = PipelineSpec(
        name="eng",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="corr",
                kind="correction",
                adapter_name="llm:x",
                input_types=(ArtifactType.RAW_TEXT,),
                output_types=(ArtifactType.CORRECTED_TEXT,),
            ),
            PipelineStep(
                id="txt",
                kind="projection",
                adapter_name="layout_to_text:x",
                input_types=(ArtifactType.LAYOUT,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
        ),
    )
    outputs = {
        "eng": {
            "d": {
                ArtifactType.CORRECTED_TEXT: Artifact(
                    id="d:corr:corrected_text",
                    document_id="d",
                    type=ArtifactType.CORRECTED_TEXT,
                    uri=str(corrigé),
                    produced_by_step="corr",
                ),
                ArtifactType.RAW_TEXT: Artifact(
                    id="d:txt:raw_text",
                    document_id="d",
                    type=ArtifactType.RAW_TEXT,
                    uri=str(final),
                    produced_by_step="txt",
                ),
            }
        }
    }
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(pipeline,),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,)),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=manifest,
    )
    # L'étape terminale est ``txt`` : c'est son RAW_TEXT qui est noté.
    assert result.pipelines[0].aggregate[0].value == 0.0


def test_candidate_falls_back_on_type_when_step_unknown(tmp_path: Path) -> None:
    """Sans ``produced_by_step`` exploitable (fan-out, entrées initiales), la
    précédence par type reste le repli — c'est le cas que verrouille le test
    ``test_candidate_precedence_prefers_corrected``, conservé tel quel."""
    gt = _write(tmp_path / "d.gt.txt", "alpha")
    raw = _write(tmp_path / "d.raw.txt", "beta")
    corrected = _write(tmp_path / "d.corr.txt", "alpha")
    corpus = CorpusSpec(name="c", documents=(_doc("d", gt),))
    view = EvaluationView(
        name="multi",
        candidate_types=frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT}),
        metric_names=("cer",),
    )
    # Étape déclarée au manifeste, mais artefacts sans étape : aucun n'est datable.
    outputs = {
        "eng": {
            "d": {
                ArtifactType.RAW_TEXT: _candidate("d", raw),
                ArtifactType.CORRECTED_TEXT: Artifact(
                    id="d:llm:corrected_text",
                    document_id="d",
                    type=ArtifactType.CORRECTED_TEXT,
                    uri=str(corrected),
                ),
            }
        }
    }
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,)),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=_manifest(1),
    )
    assert result.pipelines[0].aggregate[0].value == 0.0


def test_cross_engine_significance_written(tmp_path: Path) -> None:
    # 2 pipelines (a parfait, b avec erreurs) → RunResult.cross_engine peuplé
    gt1 = _write(tmp_path / "d1.gt.txt", "abcd")
    gt2 = _write(tmp_path / "d2.gt.txt", "abcd")
    a1 = _write(tmp_path / "d1.a.txt", "abcd")
    a2 = _write(tmp_path / "d2.a.txt", "abcd")
    b1 = _write(tmp_path / "d1.b.txt", "xbcd")
    b2 = _write(tmp_path / "d2.b.txt", "xycd")
    corpus = CorpusSpec(name="c", documents=(_doc("d1", gt1), _doc("d2", gt2)))
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=2,
        pipeline_specs=(
            PipelineSpec(name="a", initial_inputs=(ArtifactType.IMAGE,)),
            PipelineSpec(name="b", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    outputs = {
        "a": {
            "d1": {ArtifactType.RAW_TEXT: _candidate("d1", a1)},
            "d2": {ArtifactType.RAW_TEXT: _candidate("d2", a2)},
        },
        "b": {
            "d1": {ArtifactType.RAW_TEXT: _candidate("d1", b1)},
            "d2": {ArtifactType.RAW_TEXT: _candidate("d2", b2)},
        },
    }
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(TEXT_VIEW,)),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=manifest,
    )
    keys = {score.metric for score in result.cross_engine}
    assert "text:cer:significance_p" in keys


def test_inference_analyses_through_evaluate_run(tmp_path: Path) -> None:
    """≥6 docs × 3 pipelines → le runner produit le payload ``inference``."""
    gt_texts = ["abcdefgh", "ijklmnop", "qrstuvwx", "yzabcdef", "ghijklmn", "opqrstuv"]
    # alpha = parfait ; beta = 2 erreurs/doc ; gamma = 1 erreur/doc.
    documents = []
    outputs: dict[str, dict[str, dict[ArtifactType, Artifact]]] = {
        "alpha": {}, "beta": {}, "gamma": {},
    }
    for i, text in enumerate(gt_texts):
        doc_id = f"d{i}"
        gt = _write(tmp_path / f"{doc_id}.gt.txt", text)
        documents.append(_doc(doc_id, gt))
        for name, hyp in (
            ("alpha", text),
            ("beta", "XY" + text[2:]),
            ("gamma", "X" + text[1:]),
        ):
            path = _write(tmp_path / f"{doc_id}.{name}.txt", hyp)
            outputs[name][doc_id] = {
                ArtifactType.RAW_TEXT: _candidate(doc_id, path)
            }
    corpus = CorpusSpec(name="c", documents=tuple(documents))
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=6,
        pipeline_specs=tuple(
            PipelineSpec(name=n, initial_inputs=(ArtifactType.IMAGE,))
            for n in ("alpha", "beta", "gamma")
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(TEXT_VIEW,)),
        pipeline_outputs=outputs,
        registry=_registry(),
        manifest=manifest,
    )
    by_kind = {a.payload.kind: a for a in result.analyses}
    assert set(by_kind) == {
        "inference",
        "diagnostics",
        "taxonomy",
        "document_texts",
        "document_lines",
        "textual_fidelity",
        "inter_engine",
        "lines",
        "word_errors",
    }
    analysis = by_kind["inference"]
    assert analysis.view == "text" and analysis.scope == "corpus"
    payload = analysis.payload
    assert payload.kind == "inference" and payload.metric == "cer"
    # Le diagnostic voit les mêmes textes : beta (2 erreurs/doc) produit des
    # confusions X→i/j/q/y..., et les documents sont classés par CER moyen.
    diagnostics = by_kind["diagnostics"].payload
    assert diagnostics.confusions and diagnostics.hardest_documents
    assert diagnostics.worst_lines[0].cer > 0
    # Taxonomie : beta remplace les 2 premiers chars (« XY... » : substitution
    # résiduelle), gamma 1 char — classes comptées par règles pures.
    taxonomy = by_kind["taxonomy"].payload
    assert {row.pipeline for row in taxonomy.pipelines} == {"beta", "gamma"}
    assert all(row.total_errors > 0 for row in taxonomy.pipelines)
    # Inter-moteurs : alpha rattrape tous les tokens (oracle = parfait = 1.0,
    # gap nul) ; beta/gamma remplacent le seul mot de chaque doc → profils
    # taxonomy identiques ({other}) → divergence à 0, pas de paire max.
    inter_engine = by_kind["inter_engine"].payload
    comp = inter_engine.complementarity
    assert comp is not None and comp.n_documents == 6
    assert comp.best_engine == "alpha"
    assert comp.oracle_recall == 1.0 and comp.absolute_gap == 0.0
    divergence = inter_engine.taxonomy_divergence
    assert divergence is not None
    assert [(p.a, p.b) for p in divergence.pairs] == [("beta", "gamma")]
    assert divergence.pairs[0].divergence == 0.0
    assert divergence.max_pair is None
    # Lignes (vue sans profil → sauts de ligne préservés) : 1 ligne par doc,
    # CER ligne = CER doc — beta 2/8, gamma 1/8, alpha parfait.
    lines = by_kind["lines"].payload
    by_pipeline = {row.pipeline: row for row in lines.pipelines}
    assert set(by_pipeline) == {"alpha", "beta", "gamma"}
    assert all(row.line_count == 6 for row in lines.pipelines)
    assert by_pipeline["alpha"].mean_cer == 0.0
    assert by_pipeline["beta"].mean_cer == 0.25
    assert by_pipeline["gamma"].mean_cer == 0.125
    assert by_pipeline["beta"].gini == 0.0  # erreurs uniformes (0.25 partout)
    assert payload.n_documents == 6
    assert payload.critical_distance is not None  # 3 pipelines → post-hoc
    assert [r.pipeline for r in payload.mean_ranks] == ["alpha", "gamma", "beta"]
    # Carte des mots : alpha parfait → 0 raté ; beta et gamma ratent l'unique mot
    # de chaque doc → 6 mots, chacun « partial » (2 moteurs sur 3, total 2).
    word_errors = by_kind["word_errors"].payload
    assert word_errors.pipelines == ("alpha", "beta", "gamma")
    assert {w.word for w in word_errors.words} == set(gt_texts)
    assert all(
        w.group == "partial"
        and w.total_errors == 2
        and {e.pipeline for e in w.per_engine} == {"beta", "gamma"}
        for w in word_errors.words
    )
    # Round-trip JSON : le payload structuré survit tel quel.
    reloaded = RunResult.model_validate_json(result.model_dump_json())
    assert reloaded.analyses == result.analyses
