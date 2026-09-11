"""Deux correcteurs à la suite : le montage le plus courant, enfin exprimable.

« OCR → correcteur rapide → correcteur lent », ou « correction structurée puis
correction textuelle » : rien ne pouvait le décrire tant que seul ``RAW_TEXT``
entrait dans un correcteur, puisque le premier étage produit du
``CORRECTED_TEXT`` et que rien ne consommait ce type.

Le mode ``refine`` ferme la boucle. Les tests utilisent un faux fournisseur —
ce qui est vérifié est le **chaînage**, pas la qualité d'un modèle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.llm._base import llm_input_types, llm_output_type
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.pipeline import INITIAL_STEP_ID, PipelineSpec, PipelineStep


def test_refine_closes_the_text_loop() -> None:
    """Le seul mode dont l'entrée et la sortie sont du texte corrigé."""
    assert llm_input_types("refine") == frozenset({ArtifactType.CORRECTED_TEXT})
    assert llm_output_type("refine") == ArtifactType.CORRECTED_TEXT


def test_the_other_modes_are_unchanged() -> None:
    """Ajouter un mode ne doit rien déplacer chez les trois autres."""
    assert llm_input_types("text_only") == frozenset({ArtifactType.RAW_TEXT})
    assert llm_input_types("text_and_image") == frozenset(
        {ArtifactType.RAW_TEXT, ArtifactType.IMAGE}
    )
    assert llm_input_types("zero_shot") == frozenset({ArtifactType.IMAGE})
    assert llm_output_type("zero_shot") == ArtifactType.RAW_TEXT


def test_a_two_stage_chain_is_a_valid_spec() -> None:
    """La spec se déclare : OCR, puis un correcteur, puis un second sur sa sortie.

    C'est le test qui aurait été impossible à écrire avant : le troisième étage
    n'avait aucun type d'entrée disponible.
    """
    spec = PipelineSpec(
        name="ocr→corr→corr",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr",
                kind="ocr",
                adapter_name="precomputed:ocr",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
                inputs_from={ArtifactType.IMAGE: INITIAL_STEP_ID},
            ),
            PipelineStep(
                id="corr1",
                kind="post_correction",
                adapter_name="openai:rapide",
                input_types=(ArtifactType.RAW_TEXT,),
                output_types=(ArtifactType.CORRECTED_TEXT,),
                inputs_from={ArtifactType.RAW_TEXT: "ocr"},
            ),
            PipelineStep(
                id="corr2",
                kind="post_correction",
                adapter_name="openai:lent",
                input_types=(ArtifactType.CORRECTED_TEXT,),
                output_types=(ArtifactType.CORRECTED_TEXT,),
                # Explicitement la sortie du premier étage : le pool étant indexé
                # par type, ``CORRECTED_TEXT`` désignerait sinon la sortie la plus
                # récente — celle de cette étape même.
                inputs_from={ArtifactType.CORRECTED_TEXT: "corr1"},
            ),
        ),
    )
    assert [s.id for s in spec.steps] == ["ocr", "corr1", "corr2"]


def test_the_second_stage_reads_the_first_stage_output(tmp_path: Path) -> None:
    """Le point qui compte : l'étage 2 reprend le **corrigé**, pas le brut.

    Confondre les deux ferait re-corriger la sortie d'OCR au lieu de reprendre
    celle du correcteur précédent — l'erreur serait invisible dans le rapport,
    qui verrait deux corrections là où il n'y en aurait qu'une, faite deux fois.
    """
    from cinoc.adapters.llm._base import LLMCompletion, run_llm_step
    from cinoc.pipeline.run_control import RunControl
    from cinoc.pipeline.types import RunContext

    brut = tmp_path / "brut.txt"
    brut.write_text("le ſoleil", encoding="utf-8")
    corrige = tmp_path / "corrige.txt"
    corrige.write_text("le soleil", encoding="utf-8")

    vus: list[str] = []

    def _faux(prompt: str) -> LLMCompletion:
        vus.append(prompt)
        return LLMCompletion(text="le Soleil", tokens_in=1, tokens_out=1)

    run_llm_step(
        role="refine",
        label="etage2",
        name="faux:etage2",
        prompt="Corrige : {ocr_text}",
        inputs={
            ArtifactType.RAW_TEXT: Artifact(
                id="r", document_id="d", type=ArtifactType.RAW_TEXT, uri=str(brut)
            ),
            ArtifactType.CORRECTED_TEXT: Artifact(
                id="c",
                document_id="d",
                type=ArtifactType.CORRECTED_TEXT,
                uri=str(corrige),
            ),
        },
        context=RunContext(
            document_id="d",
            workspace_uri=str(tmp_path),
            code_version="t",
            pipeline_name="p",
        ),
        control=RunControl(),
        text_invoke=_faux,
        vision_invoke=None,
    )

    assert "le soleil" in vus[0], "l'étage 2 doit reprendre le texte corrigé"
    assert "ſoleil" not in vus[0], "l'étage 2 ne doit pas repartir du texte brut"


def test_refine_without_a_corrected_input_says_which_type_is_missing(
    tmp_path: Path,
) -> None:
    """Anti-silence : l'erreur nomme le type attendu, pas « entrée manquante »."""
    from cinoc.adapters.llm._base import LLMCompletion, run_llm_step
    from cinoc.domain.errors import AdapterStepError
    from cinoc.pipeline.run_control import RunControl
    from cinoc.pipeline.types import RunContext

    with pytest.raises(AdapterStepError, match="CORRECTED_TEXT"):
        run_llm_step(
            role="refine",
            label="e",
            name="faux:e",
            prompt="p",
            inputs={},
            context=RunContext(
                document_id="d",
                workspace_uri=str(tmp_path),
                code_version="t",
                pipeline_name="p",
            ),
            control=RunControl(),
            text_invoke=lambda _p: LLMCompletion(text="", tokens_in=0, tokens_out=0),
            vision_invoke=None,
        )
