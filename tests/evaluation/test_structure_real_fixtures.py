"""Câblage de l'axe **structure** sur données **réelles** (réflexe informativité).

Avant de s'appuyer sur ``region_cer``, on vérifie sur de vrais ALTO/PAGE (4
producteurs distincts : Gallica, Tesseract, Transkribus, eScriptorium) que :

1. les mappers portent fidèlement la **diversité réelle** (bbox vs polygone,
   mot vs ligne, imbrication, marginalia) dans le **même** modèle neutre ;
2. ``region_cer`` est **correct, non-trivial et non trompeur** sur ces layouts —
   0 sur identité, attribuable sur erreur localisée, pénalisant sur région
   manquante, et ``None`` (≠ faux 0/1) quand le niveau texte est absent ;
3. le tout traverse le **vrai runner** (``evaluate_run``), pas seulement la
   fonction métrique.

Donnée réelle : ``tests/formats/fixtures`` (mêmes fixtures producteurs que la
couche 2). L'hypothèse dégradée est une **perturbation contrôlée** d'une GT
réelle (marginalia mal lue / région omise) — un cas, pas un run d'OCR réel.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.layout import CanonicalLayout, Line
from cinoc.domain.run import RunManifest
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.layout import region_cer
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.representations import load_representation
from cinoc.evaluation.runner import evaluate_run
from tests.declared_specs import declared_pipeline

_FIXTURES = Path(__file__).resolve().parents[1] / "formats" / "fixtures"
_ESCRIPTORIUM = str(_FIXTURES / "escriptorium.page.xml")
FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _layout(name: str) -> CanonicalLayout:
    loaded = load_representation(str(_FIXTURES / name), ArtifactType.LAYOUT)
    assert isinstance(loaded, CanonicalLayout)
    return loaded


def _regions(layout: CanonicalLayout) -> tuple:
    return layout.pages[0].regions


# --- 1. fidélité réelle : 4 producteurs → un seul modèle neutre --------------


def test_gallica_alto_nesting_and_words_preserved() -> None:
    composed = _regions(_layout("gallica.alto.xml"))[0]
    assert composed.region_type == "article"
    assert composed.geometry is not None and composed.geometry.bbox is not None
    assert composed.regions[0].lines[0].text == "CHAPITRE PREMIER"
    assert len(composed.regions[0].lines[0].words) == 2  # ALTO = niveau mot


def test_tesseract_alto_single_block_with_words() -> None:
    region = _regions(_layout("tesseract.alto.xml"))[0]
    assert region.region_type == "text"
    assert tuple(w.text for w in region.lines[0].words) == ("Liberté", "égalité")


def test_transkribus_page_is_polygon_with_words() -> None:
    region = _regions(_layout("transkribus.page.xml"))[0]
    assert region.geometry is not None
    assert region.geometry.bbox is None and region.geometry.polygon  # PAGE = polygone
    # Les ``<Word>`` PAGE sont lus (D-273), polygone compris.
    words = region.lines[0].words
    assert tuple(w.text for w in words) == ("Nostre", "Seigneur")
    assert all(w.geometry is not None and w.geometry.polygon for w in words)


def test_escriptorium_page_separates_body_and_marginalia() -> None:
    main, margin = _regions(_layout("escriptorium.page.xml"))
    assert (main.id, margin.id) == ("main", "margin")
    assert margin.region_type == "marginalia"
    assert margin.lines[0].text == "nota"


# --- 2. region_cer correct / non-trivial / non trompeur sur réel -------------


def test_identical_real_layout_scores_zero_not_none() -> None:
    gt = _layout("escriptorium.page.xml")
    score = region_cer.fn(DocContext(document_id="d", reference=gt, hypothesis=gt))
    assert score is not None and score.value == 0.0  # applicable, pas None


def test_segmentation_only_real_layout_is_not_applicable() -> None:
    gt = _layout("escriptorium.page.xml")
    page = gt.pages[0]
    stripped = page.model_copy(
        update={
            "regions": tuple(
                r.model_copy(update={"lines": ()}) for r in page.regions
            )
        }
    )
    seg_only = CanonicalLayout(pages=(stripped,))
    # niveau texte absent → None, surtout PAS un faux 1.0.
    assert region_cer.fn(
        DocContext(document_id="d", reference=gt, hypothesis=seg_only)
    ) is None


def _degrade_margin(gt: CanonicalLayout, *, text: str | None) -> CanonicalLayout:
    """Hyp = GT réelle avec la marginalia mal lue (``text``) ou omise (``None``)."""
    page = gt.pages[0]
    main, margin = page.regions
    if text is None:
        regions = (main,)
    else:
        regions = (main, margin.model_copy(update={"lines": (Line(text=text),)}))
    return CanonicalLayout(pages=(page.model_copy(update={"regions": regions}),))


def test_localized_marginalia_error_is_attributable() -> None:
    gt = _layout("escriptorium.page.xml")
    hyp = _degrade_margin(gt, text="uota")  # "nota" → "uota" : 1 substitution
    score = region_cer.fn(DocContext(document_id="d", reference=gt, hypothesis=hyp))
    assert score is not None
    # 1 erreur sur 53 caractères de page (corps 49 + marginalia 4) : minuscule au
    # global, mais entièrement localisée dans une région de 4 caractères.
    assert score.value == pytest.approx(1 / 53)
    assert (score.stat.errors, score.stat.reference_length) == (1, 53)


def test_dropped_marginalia_region_is_penalized() -> None:
    gt = _layout("escriptorium.page.xml")
    hyp = _degrade_margin(gt, text=None)  # segmentation rate la marginalia
    score = region_cer.fn(DocContext(document_id="d", reference=gt, hypothesis=hyp))
    assert score is not None
    assert score.value == pytest.approx(4 / 53)  # "nota" entièrement supprimé


# --- 3. chemin complet : vrai runner sur GT PAGE réelle ----------------------


def test_region_cer_through_runner_on_real_gt(tmp_path: Path) -> None:
    gt = _layout("escriptorium.page.xml")
    hyp_path = tmp_path / "doc1.hyp.layout.json"
    hyp_path.write_bytes(_degrade_margin(gt, text="uota").model_dump_json().encode())
    doc = DocumentRef(
        id="doc1",
        ground_truths=(GroundTruthRef(type=ArtifactType.LAYOUT, uri=_ESCRIPTORIUM),),
    )
    outputs = {
        "seg": {
            "doc1": {
                "ocr": {
                    ArtifactType.LAYOUT: Artifact(
                        id="doc1:assemble:layout",
                        document_id="doc1",
                        type=ArtifactType.LAYOUT,
                        uri=str(hyp_path),
                    )
                }
            }
        }
    }
    registry = MetricRegistry()
    register_default_metrics(registry)
    result = evaluate_run(
        corpus=CorpusSpec(name="c", documents=(doc,)),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="structure",
                    candidate_types=frozenset({ArtifactType.LAYOUT}),
                    metric_names=("region_cer",),
                ),
            )
        ),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=1,
            pipeline_specs=(
                declared_pipeline("seg"),
            ),
            code_version="1.0",
            started_at=FIXED,
            completed_at=FIXED,
        ),
    )
    aggregate = result.principal_aggregate(result.pipelines[0])[0]
    assert aggregate.metric == "region_cer"
    assert aggregate.value == pytest.approx(1 / 53)
    assert aggregate.support == 1
