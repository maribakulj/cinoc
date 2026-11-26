"""``plan_evaluation`` : la politique de vues unique (D-285, D-297).

Une vue n'est déclarée que si un pipeline **produit** de quoi la noter **et** que
le corpus **porte** une vérité terrain qui le juge. GT manuelle ``RAW_TEXT`` →
vue ``texte`` (+ ``texte (lignes)``) ; référence ``REFERENCE_TEXT`` (OCR Gallica)
→ vue *référence* distincte, étiquetée dans son nom ; GT ``LAYOUT`` et sortie
``LAYOUT`` → ``structure`` ; aucune GT → vue ``texte`` seule (run exécutable,
non noté).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.evaluation_views import (
    DEFAULT_METRIC_PROFILE,
    METRIC_PROFILES,
    EvaluationOptions,
    EvaluationOptionsError,
    metric_profile_catalog,
    plan_evaluation,
)
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics


def _pipeline(*sorties: ArtifactType) -> PipelineSpec:
    return PipelineSpec(
        name="p",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="s",
                kind="ocr",
                adapter_name="tesseract:s",
                input_types=(ArtifactType.IMAGE,),
                output_types=sorties or (ArtifactType.RAW_TEXT,),
            ),
        ),
    )


def _views(
    corpus: CorpusSpec,
    *sorties: ArtifactType,
    options: EvaluationOptions | None = None,
) -> tuple[EvaluationView, ...]:
    return plan_evaluation((_pipeline(*sorties),), corpus, options).evaluation.views


def _corpus(*gt_types: ArtifactType) -> CorpusSpec:
    gts = tuple(GroundTruthRef(type=t, uri=f"/tmp/{t.value}.txt") for t in gt_types)
    doc = DocumentRef(id="d1", image_uri="/tmp/a.png", ground_truths=gts)
    return CorpusSpec(name="c", documents=(doc,))


def test_manual_gt_yields_text_view_only() -> None:
    views = _views(_corpus(ArtifactType.RAW_TEXT))
    assert [v.name for v in views] == ["texte"]


def test_reference_text_yields_distinct_reference_view() -> None:
    views = _views(_corpus(ArtifactType.REFERENCE_TEXT))
    assert len(views) == 1
    view = views[0]
    # nom auto-documenté (le rapport l'affiche tel quel) + projection opt-in
    assert "vérité-terrain" in view.name
    spec = view.projection_for(ArtifactType.REFERENCE_TEXT)
    assert spec is not None and spec.target_type == ArtifactType.RAW_TEXT


def test_both_gt_types_yield_both_views() -> None:
    views = _views(_corpus(ArtifactType.RAW_TEXT, ArtifactType.REFERENCE_TEXT))
    names = [v.name for v in views]
    assert names[0] == "texte"
    assert any("vérité-terrain" in n for n in names)


def test_no_gt_falls_back_to_text_view() -> None:
    views = _views(_corpus())
    assert [v.name for v in views] == ["texte"]


def test_layout_needs_an_output_and_a_ground_truth() -> None:
    """La structure se note sur une sortie ``LAYOUT`` **et** une GT ``LAYOUT`` :
    l'une sans l'autre ne donne qu'une vue vide."""
    layout = _corpus(ArtifactType.LAYOUT)
    (structure,) = _views(layout, ArtifactType.LAYOUT)
    assert structure.name == "structure"
    assert structure.candidate_types == frozenset({ArtifactType.LAYOUT})
    assert structure.metric_names == (
        "region_detection",
        "region_cer",
        "line_identity_cer",
        "line_identity_coverage",
        "reading_order_tau",
        "reading_order_coverage",
    )
    # Un OCR à plat sur un corpus à GT de mise en page : rien à noter en
    # structure, et pas de GT texte non plus → la vue texte de repli.
    assert [v.name for v in _views(layout)] == ["texte"]
    # Une segmentation sans GT de mise en page : aucune vue.
    assert _views(_corpus(), ArtifactType.LAYOUT) == ()


def test_entities_need_an_output_and_a_ground_truth() -> None:
    corpus = _corpus(ArtifactType.RAW_TEXT, ArtifactType.ENTITIES)
    views = _views(corpus, ArtifactType.RAW_TEXT, ArtifactType.ENTITIES)
    assert [v.name for v in views] == ["texte", "entites"]
    assert views[1].metric_names == ("ner_f1", "ner_f1_exact")
    assert [v.name for v in _views(corpus)] == ["texte"]


def _corpus_with_gt(tmp_path: Path, text: str) -> CorpusSpec:
    gt = tmp_path / "d1.gt.txt"
    gt.write_text(text, encoding="utf-8")
    doc = DocumentRef(
        id="d1",
        image_uri=str(tmp_path / "a.png"),
        ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),),
    )
    return CorpusSpec(name="c", documents=(doc,))


def test_gt_with_lines_adds_the_lines_view(tmp_path: Path) -> None:
    """D-285 : sous le défaut à plat, la seconde vue garde les sauts de ligne —
    c'est elle qui porte l'analyse par ligne (et le chiffre de dinglehopper)."""
    views = _views(_corpus_with_gt(tmp_path, "le roi\ndort\n"))
    assert [(v.name, v.normalization_profile) for v in views] == [
        ("texte", "flat_text"),
        ("texte (lignes)", "keep_line_breaks"),
    ]
    assert views[1].metric_names == ("cer",)
    # D-289 : la FCA n'est plus d'aucune vue par défaut — 1 − CER à plat, et
    # sous « texte (lignes) » soit 1 − CER encore, soit ~0 pour qui fusionne.
    assert all("fca" not in v.metric_names for v in views)


def test_single_line_gt_keeps_one_view(tmp_path: Path) -> None:
    views = _views(_corpus_with_gt(tmp_path, "une seule ligne\n"))
    assert [v.name for v in views] == ["texte"]


def test_a_chosen_profile_gives_a_single_view(tmp_path: Path) -> None:
    """Un profil choisi remplace le défaut : l'utilisateur a dit sa convention."""
    views = _views(
        _corpus_with_gt(tmp_path, "le roi\ndort"),
        options=EvaluationOptions(normalization="nfc"),
    )
    assert [(v.name, v.normalization_profile) for v in views] == [("texte", "nfc")]


@pytest.mark.parametrize(
    ("options", "motif"),
    [
        (EvaluationOptions(normalization="bidon"), "normalisation inconnu"),
        (EvaluationOptions(metric_profile="bidon"), "métriques inconnu"),
        (EvaluationOptions(archaic_list="bidon"), "archaïque inconnue"),
    ],
)
def test_an_unknown_option_is_refused_by_name(
    options: EvaluationOptions, motif: str
) -> None:
    with pytest.raises(EvaluationOptionsError, match=motif):
        plan_evaluation((_pipeline(),), _corpus(ArtifactType.RAW_TEXT), options)


def test_the_archaic_list_is_always_written_to_the_manifest() -> None:
    """``air`` lit une liste même sans choix : le manifeste la nomme toujours."""
    plan = plan_evaluation((_pipeline(),), _corpus(ArtifactType.RAW_TEXT))
    assert plan.metadata["archaic_list"] == "archaic_core"
    assert len(plan.metadata["archaic_list_hash"]) == 64


def test_metric_profile_catalog_lists_standard_first() -> None:
    catalog = metric_profile_catalog()
    assert catalog[0]["name"] == DEFAULT_METRIC_PROFILE == "standard"
    names = {entry["name"] for entry in catalog}
    assert names == set(METRIC_PROFILES)  # toutes exposées, aucune fantôme
    for entry in catalog:
        assert entry["metrics"] == list(METRIC_PROFILES[entry["name"]])  # ordonné


def test_every_profiled_metric_is_registered() -> None:
    # Garde-fou anti-footgun : une métrique non enregistrée pour (RAW_TEXT,
    # RAW_TEXT) ferait lever le runner (``EvaluationError``) au moment du run.
    registry = MetricRegistry()
    register_default_metrics(registry)
    applicable = {
        m.name
        for m in registry.for_input_types(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT)
    }
    for name, metrics in METRIC_PROFILES.items():
        unknown = set(metrics) - applicable
        assert not unknown, f"profil {name!r} : métriques non enregistrées {unknown}"


def test_every_structure_metric_is_registered_for_layouts() -> None:
    registry = MetricRegistry()
    register_default_metrics(registry)
    applicable = {
        m.name
        for m in registry.for_input_types(ArtifactType.LAYOUT, ArtifactType.LAYOUT)
    }
    (structure,) = _views(_corpus(ArtifactType.LAYOUT), ArtifactType.LAYOUT)
    assert set(structure.metric_names) <= applicable
