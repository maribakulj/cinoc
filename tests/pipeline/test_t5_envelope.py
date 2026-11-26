"""Enveloppe T5 — pipeline hybride seg → reconnaissance par région → ALTO.

Les 3 briques ``precomputed_layout`` / ``precomputed_region`` / ``alto_assembler``
implémentent le contrat ``Module`` et sont **composées par une recette**
(``segmentation_puis_lecture``, export ALTO retenu — D-298 ; c'était le
planificateur hybride). Ce fichier garde (1) qu'elles restent enregistrées au
socle (anti-retrait), (2) que la recette produit la bonne composition seg →
fanout → assemblage, et (3) qu'elle **s'exécute de bout en bout** : le texte de
l'ALTO assemblé est celui reconnu par région.
"""

from __future__ import annotations

import json
from pathlib import Path

from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Region
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.representations import load_representation
from cinoc.pipeline.executor import PipelineExecutor

#: Les 3 briques de l'enveloppe hybride (cf. registry.register_default_modules).
T5_ENVELOPE = ("precomputed_layout", "precomputed_region", "alto_assembler")


def _registered_kinds() -> set[str]:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return set(registry.kinds())


def _hybrid(**choices: str) -> RunSpec:
    """La recette hybride, export ALTO retenu ; ``reco.source_label=eng`` pour
    le rejeu par région."""
    replay = choices.get("reco") == "precomputed_region"
    return plan_recipe_run(
        CorpusSpec(name="c", documents=()),
        (
            RecipeEntry(
                recipe="segmentation_puis_lecture",
                choices=choices,
                params={"reco": {"source_label": "eng"}} if replay else {},
                optional=("alto",),
            ),
        ),
        run_id="r",
    )


def test_t5_bricks_stay_registered() -> None:
    """Garde : les 3 briques de l'enveloppe hybride restent au socle.

    Leur retrait casserait la composition de la recette hybride — ce
    test échoue si on les déregistre par erreur.
    """
    assert set(T5_ENVELOPE) <= _registered_kinds()


def test_hybrid_planner_composes_the_three_bricks() -> None:
    """La recette (mode démo) fabrique seg → reco région (fanout) → texte, ALTO."""
    run_spec = _hybrid(seg="precomputed_layout", reco="precomputed_region")
    spec = run_spec.pipelines[0]
    assert tuple(s.id for s in spec.steps) == ("seg", "reco", "texte", "alto")
    segment, recognize, _texte, assemble = spec.steps
    assert segment.adapter_name == "precomputed_layout"
    assert segment.output_types == (ArtifactType.LAYOUT,)
    # Étage 2 : reconnaissance par région (fan-out couche 4), LAYOUT+IMAGE → LAYOUT.
    assert recognize.adapter_name == "precomputed_region:eng"
    assert recognize.fanout is True
    assert recognize.crop is False  # precomputed lit par region_id, aucun pixel
    assert recognize.input_types == (ArtifactType.LAYOUT, ArtifactType.IMAGE)
    assert recognize.output_types == (ArtifactType.LAYOUT,)
    assert recognize.inputs_from == {
        ArtifactType.LAYOUT: "seg",
        ArtifactType.IMAGE: "__initial__",
    }
    # Étage 3 : assemblage LAYOUT rempli → ALTO_XML.
    assert assemble.adapter_name == "alto_assembler:alto"
    assert assemble.output_types == (ArtifactType.ALTO_XML,)
    assert assemble.inputs_from == {ArtifactType.LAYOUT: "reco"}
    assert run_spec.adapter_kwargs["precomputed_region:eng"] == {
        "source_label": "eng"
    }


def test_hybrid_recipe_real_bricks_crop_each_block() -> None:
    """Un pipeline **réel** : pp_doclayout + tesseract par région (le crop est
    injecté par l'orchestrateur, cf. F-4c)."""
    run_spec = _hybrid(seg="pp_doclayout", reco="tesseract")
    segment, recognize, _texte, assemble = run_spec.pipelines[0].steps
    assert segment.adapter_name == "pp_doclayout:seg"
    assert recognize.adapter_name == "tesseract:reco"
    assert recognize.fanout is True
    assert recognize.crop is True  # OCR réel par bloc → découpe l'image
    assert assemble.adapter_name == "alto_assembler:alto"
    assert run_spec.adapter_kwargs["tesseract:reco"] == {"label": "reco"}


def _scene(tmp_path: Path, regions: dict[str, str]) -> Artifact:
    """Pose image + mise en page précalculée + textes par région ; renvoie l'IMAGE."""
    image = tmp_path / "doc1.png"
    image.write_bytes(b"\x89PNG stub")
    seg = CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(
                    Region(id="r1", region_type="text"),
                    Region(id="r2", region_type="text"),
                ),
                reading_order=("r1", "r2"),
            ),
        )
    )
    (tmp_path / "doc1.layout.json").write_bytes(
        seg.model_dump_json().encode("utf-8")
    )
    (tmp_path / "doc1.eng.regions.json").write_text(
        json.dumps(regions), encoding="utf-8"
    )
    return Artifact(
        id="doc1:init:image",
        document_id="doc1",
        type=ArtifactType.IMAGE,
        uri=str(image),
    )


def test_hybrid_planner_spec_runs_end_to_end(tmp_path: Path) -> None:
    """La spec de la recette s'exécute : l'ALTO assemblé porte le texte reconnu."""
    run_spec = _hybrid(seg="precomputed_layout", reco="precomputed_region")
    spec = run_spec.pipelines[0]
    registry = ModuleRegistry()
    register_default_modules(registry)
    modules = {
        step.adapter_name: registry.build(
            step.adapter_name, run_spec.adapter_kwargs.get(step.adapter_name, {})
        )
        for step in spec.steps
    }
    image = _scene(tmp_path, {"r1": "hello world", "r2": "second block"})
    pool = PipelineExecutor("t5-1.0").execute_document(
        spec,
        modules,
        {ArtifactType.IMAGE: image},
        document_id="doc1",
        workspace_uri=str(tmp_path),
    )
    alto = pool.artifacts[ArtifactType.ALTO_XML]
    assert alto.uri is not None
    assert Path(alto.uri).read_bytes().lstrip().startswith(b"<")
    # L'ALTO assemblé, rechargé en LAYOUT, porte le texte reconnu par région
    # dans l'ordre de lecture (texte assemblé = texte brut par région).
    hyp = load_representation(alto.uri, ArtifactType.LAYOUT)
    assert isinstance(hyp, CanonicalLayout)
    region_texts = [
        " ".join(line.text for line in region.lines)
        for page in hyp.pages
        for region in page.regions
    ]
    assert region_texts == ["hello world", "second block"]
