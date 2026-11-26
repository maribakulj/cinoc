"""Benchmark Cinoc sur **données réelles** : corpus BNL (presse historique
luxembourgeoise, **multilingue** allemand Fraktur + français), **5 pipelines** :
4 Tesseract — ``frk`` (Fraktur legacy) · ``deu`` (allemand) · ``fra`` (français)
· ``deu_latf`` (Fraktur LSTM « best ») — **et ``easyocr``** (deep-learning, autre
architecture : excellent en français, faible en Fraktur).

Déterministe en CI : la GT (extraite des ALTO v4 BNL) et les sorties OCR sont
**figées** dans ``tests/fixtures/reference_corpus/bnl_mini/`` ; on les rejoue via
l'adapter ``precomputed`` (ni Tesseract ni EasyOCR requis en CI). Le run est
construit **une seule fois** (fixture ``module``) — sinon 5 moteurs × 30 docs
seraient relancés à chaque test. Vérifie ce que le synthétique ne pouvait pas :
de **vraies** métriques **et** une **significativité inter-moteurs vivante**
(n≈30 ≥ plancher de puissance 6, ≠ démo n=3 → ``None``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cinoc.app import resolve_code_version
from cinoc.app import run as run_orchestrator
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.result import RunResult
from cinoc.reports import default_report_renderer

_FIXTURES = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "reference_corpus"
    / "bnl_mini"
)
#: Documents découverts depuis la fixture (la GT figée fait foi).
_DOC_IDS = tuple(
    sorted(p.name.removesuffix(".gt.txt") for p in _FIXTURES.glob("*.gt.txt"))
)
#: 5 pipelines : 4 Tesseract (langue + qualité de modèle) + EasyOCR (autre archi).
_ENGINES = ("frk", "deu", "fra", "deu_latf", "easyocr")


def _document(root: Path, doc_id: str) -> DocumentRef:
    return DocumentRef(
        id=doc_id,
        image_uri=str(root / f"{doc_id}.png"),  # absent, ignoré par precomputed
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT,
                uri=str(root / f"{doc_id}.gt.txt"),
            ),
        ),
    )


def _pipeline(label: str) -> PipelineSpec:
    return PipelineSpec(
        name=label,
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr",
                kind="ocr",
                adapter_name=f"precomputed:{label}",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
        ),
    )


def build_bnl_run_result(root: Path) -> RunResult:
    """Matérialise le corpus BNL figé dans ``root`` et exécute le run (precomputed)."""
    for doc_id in _DOC_IDS:
        for suffix in ("gt", *_ENGINES):
            name = f"{doc_id}.{suffix}.txt"
            shutil.copy(_FIXTURES / name, root / name)
    corpus = CorpusSpec(
        name="bnl_mini",
        documents=tuple(_document(root, doc_id) for doc_id in _DOC_IDS),
        metadata={"source": "BNL", "languages": "deu,fra", "script": "fraktur+antiqua"},
    )
    views = (
        EvaluationView(
            name="text",
            candidate_types=frozenset({ArtifactType.RAW_TEXT}),
            metric_names=(
                "cer",
                "cer_diplo",
                "diacritic_err",
                "del_rate",
                "ins_rate",
                "wer",
                "mer",
            ),
        ),
        EvaluationView(
            name="caseless",
            candidate_types=frozenset({ArtifactType.RAW_TEXT}),
            metric_names=("cer", "wer", "mer"),
            normalization_profile="caseless",
        ),
    )
    spec = RunSpec(
        corpus=corpus,
        pipelines=tuple(_pipeline(label) for label in _ENGINES),
        evaluation=EvaluationSpec(views=views),
        adapter_kwargs={
            f"precomputed:{label}": {"source_label": label} for label in _ENGINES
        },
        run_id="bnl",
    )
    registry = ModuleRegistry()
    register_default_modules(registry)
    return run_orchestrator(
        spec, registry=registry, code_version=resolve_code_version()
    )


@pytest.fixture(scope="module")
def bnl_result(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """Construit le run BNL une fois pour tout le module (5 moteurs × 30 docs)."""
    root = tmp_path_factory.mktemp("bnl_corpus")
    return build_bnl_run_result(root)


def test_bnl_real_metrics_are_plausible(bnl_result: RunResult) -> None:
    assert {p.pipeline for p in bnl_result.pipelines} == set(_ENGINES)
    assert {p.view for p in bnl_result.pipelines} == {"text", "caseless"}
    for pipeline in bnl_result.pipelines:
        scores = {s.metric: s.value for s in pipeline.aggregate}
        # cer_diplo, diacritic_err et le profil d'erreur (del_rate/ins_rate) ne sont
        # demandés que dans la vue brute « text » (cf. tests dédiés plus bas).
        expected = (
            {"cer", "cer_diplo", "diacritic_err", "del_rate", "ins_rate", "wer", "mer"}
            if pipeline.view == "text"
            else {"cer", "wer", "mer"}
        )
        assert set(scores) == expected
        # OCR réel (y compris moteur en mauvaise langue/écriture) : non nul, borné
        assert scores["cer"] is not None and 0.0 < scores["cer"] < 2.0
    # détail par-document peuplé : N docs × 5 moteurs × 2 vues
    assert len(bnl_result.documents) == len(_DOC_IDS) * len(_ENGINES) * 2


def test_bnl_insertion_rate_flags_easyocr_hallucination(bnl_result: RunResult) -> None:
    """Trouvaille figée : easyocr (pire CER, 0,50) insère le plus de mots parasites
    — ins_rate strictement supérieur à chaque autre moteur (il « hallucine »). Et
    l'invariant de décomposition del_rate + ins_rate ≤ wer tient pour chacun (le
    reste = substitutions). Vue « text »."""
    text = {
        p.pipeline: {s.metric: s.value for s in p.aggregate}
        for p in bnl_result.pipelines
        if p.view == "text"
    }
    easy = text["easyocr"]["ins_rate"]
    assert easy is not None
    for other in ("frk", "deu", "fra", "deu_latf"):
        assert easy > text[other]["ins_rate"]
    for scores in text.values():
        assert scores["del_rate"] + scores["ins_rate"] <= scores["wer"] + 1e-9


def test_bnl_diacritic_error_splits_germanic_vs_latin(bnl_result: RunResult) -> None:
    """Trouvaille figée (alignement caractère via rapidfuzz) : les modèles
    germaniques/Fraktur (frk, deu, deu_latf) butent sur les diacritiques (umlauts
    ä/ö/ü mal rendus vs GT précomposée, ~80 % d'erreur) là où le modèle français et
    easyocr les restituent bien (~10-14 %). Mesuré dans la vue « text »."""
    diac = {
        p.pipeline: {s.metric: s.value for s in p.aggregate}["diacritic_err"]
        for p in bnl_result.pipelines
        if p.view == "text"
    }
    for germanic in ("frk", "deu", "deu_latf"):
        assert diac[germanic] is not None and diac[germanic] > 0.5
    for latin in ("fra", "easyocr"):
        assert diac[latin] is not None and diac[latin] < 0.3


def test_bnl_cer_diplomatic_isolates_long_s(bnl_result: RunResult) -> None:
    """Trouvaille philologique réelle, figée : les modèles Fraktur (``frk``,
    ``deu_latf``) transcrivent le ſ long que la GT BNL a normalisé en ``s`` ; le
    CER brut les en « pénalise ». ``cer_diplo`` (repli ſ→s, des deux côtés)
    récupère cette part **purement typographique**. Les moteurs non-Fraktur
    (``deu``/``fra``/``easyocr``) n'émettent aucun ſ → aucun écart."""
    text = {
        p.pipeline: {s.metric: s.value for s in p.aggregate}
        for p in bnl_result.pipelines
        if p.view == "text"
    }
    for fraktur in ("frk", "deu_latf"):
        gap = text[fraktur]["cer"] - text[fraktur]["cer_diplo"]
        assert gap > 0.005, f"{fraktur} : écart ſ long attendu, vu {gap}"
    for antiqua in ("deu", "fra", "easyocr"):
        gap = text[antiqua]["cer"] - text[antiqua]["cer_diplo"]
        assert gap < 1e-6, f"{antiqua} : pas de ſ → aucun écart, vu {gap}"


def test_bnl_cross_engine_significance_is_live(bnl_result: RunResult) -> None:
    # n≈30 ≥ _MIN_SUPPORT=6 → le test omnibus CALCULE un p (≠ démo n=3 → tout None).
    sig = [s for s in bnl_result.cross_engine if s.metric.endswith("significance_p")]
    assert sig, "significativité inter-moteurs attendue dans cross_engine"
    assert any(s.value is not None for s in sig), (
        "n≈30 ≥ plancher 6 → au moins un p-value calculé (pas uniquement None)"
    )


def test_bnl_posthoc_shows_the_pair_that_differs(bnl_result: RunResult) -> None:
    """S11 (D-283) : 5 moteurs, mode rapide — le test est un **Friedman**, il
    tourne sans qu'on le demande, et le post-hoc nomme la **seule** paire que
    Nemenyi sépare en MER. Les anciens groupes disjoints ({fra, deu, frk,
    deu_latf} · {easyocr}) faisaient lire quatre paires là où il y en a une."""
    from cinoc.evaluation.analysis import InferencePayload

    payloads = {
        (a.view, a.payload.metric): a.payload
        for a in bnl_result.analyses
        if isinstance(a.payload, InferencePayload)
    }
    mer = payloads[("text", "mer")]
    assert mer.test == "friedman" and mer.family_size == 6
    assert mer.p_holm is not None and mer.p_holm < 0.05
    assert [(p.a, p.b) for p in mer.pairwise if p.significant] == [("easyocr", "fra")]
    assert len(mer.cd_groups) == 2 and set(mer.cd_groups[0]) & set(mer.cd_groups[1])
    assert all(payload.intervals == () for payload in payloads.values())
    html = default_report_renderer().render(bnl_result, title="Cinoc — BNL")
    assert "Friedman : p = " in html and "Wilcoxon :" not in html
    assert "paires significatives : easyocr – fra." in html


def test_bnl_report_is_octet_stable(bnl_result: RunResult) -> None:
    renderer = default_report_renderer()
    assert renderer.render(bnl_result, title="Cinoc — BNL") == renderer.render(
        bnl_result, title="Cinoc — BNL"
    )
