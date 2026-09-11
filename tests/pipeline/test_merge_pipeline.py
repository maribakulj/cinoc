"""Bout-en-bout : trois OCR imparfaits, une fusion meilleure qu'aucun d'eux.

C'est la seule démonstration qui compte. Une fusion qui ne ferait pas mieux que
son meilleur votant ne mériterait pas d'exister, et un banc qui ne saurait pas
le vérifier ne mériterait pas qu'on lui confie la question.

Le run passe par le **vrai exécuteur** : ce qui est prouvé, c'est que le contrat
de fusion se compose avec le reste, pas seulement que la fonction de vote est
juste.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.pipeline import INITIAL_STEP_ID, PipelineSpec, PipelineStep
from cinoc.pipeline.executor import PipelineExecutor

#: La vérité, et trois lectures qui se trompent **chacune ailleurs**.
VERITE = "le soleil luisoit sur la ville"
LECTURES = {
    "a": "le soleil luiſoit sur la ville",
    "b": "le solcil luisoit sur la ville",
    "c": "le soleil luisoit sur la villc",
}


def _corpus(tmp_path: Path) -> Path:
    """Une image factice et trois transcriptions pré-calculées à côté."""
    image = tmp_path / "p1.png"
    image.write_bytes(b"\x89PNG stub")
    for source, texte in LECTURES.items():
        (tmp_path / f"p1.{source}.txt").write_text(texte, encoding="utf-8")
    return image


def _spec() -> PipelineSpec:
    etapes = [
        PipelineStep(
            id=f"ocr_{source}",
            kind="ocr",
            adapter_name=f"precomputed:{source}",
            input_types=(ArtifactType.IMAGE,),
            output_types=(ArtifactType.RAW_TEXT,),
            inputs_from={ArtifactType.IMAGE: INITIAL_STEP_ID},
        )
        for source in sorted(LECTURES)
    ]
    etapes.append(
        PipelineStep(
            id="fusion",
            kind="merge",
            adapter_name="vote:fusion",
            input_types=(ArtifactType.RAW_TEXT,),
            output_types=(ArtifactType.RAW_TEXT,),
            merge_from=tuple(f"ocr_{s}" for s in sorted(LECTURES)),
        )
    )
    return PipelineSpec(
        name="trois OCR → vote",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=tuple(etapes),
    )


def _distance(reference: str, hypothese: str) -> int:
    """Nombre de mots faux — suffisant pour départager, lisible en cas d'échec."""
    return sum(
        1
        for r, h in zip(reference.split(), hypothese.split(), strict=False)
        if r != h
    )


def test_the_vote_beats_every_single_engine(tmp_path: Path) -> None:
    image = _corpus(tmp_path)
    registre = ModuleRegistry()
    register_default_modules(registre)
    modules = {
        f"precomputed:{s}": registre.build(f"precomputed:{s}", {"source_label": s})
        for s in sorted(LECTURES)
    }
    modules["vote:fusion"] = registre.build("vote:fusion", {"label": "fusion"})

    execution = PipelineExecutor(code_version="test").execute_document(
        _spec(),
        modules,
        document_id="p1",
        initial_inputs={
            ArtifactType.IMAGE: Artifact(
                id="i", document_id="p1", type=ArtifactType.IMAGE, uri=str(image)
            )
        },
        workspace_uri=str(tmp_path / "ws"),
    )

    produit = execution.artifacts[ArtifactType.RAW_TEXT]
    assert produit.uri is not None
    fusionne = Path(produit.uri).read_text(encoding="utf-8")

    # Chacun se trompe une fois ; la fusion ne se trompe pas du tout.
    for source, lecture in LECTURES.items():
        assert _distance(VERITE, lecture) == 1, f"{source} devrait avoir une faute"
    assert fusionne == VERITE
    assert _distance(VERITE, fusionne) == 0


def test_a_non_merging_brick_in_a_merge_step_is_named(tmp_path: Path) -> None:
    """Anti-silence : déclarer ``merge_from`` sur une brique ordinaire doit dire
    laquelle, et pourquoi — pas échouer sur un attribut manquant."""
    import pytest

    from cinoc.pipeline.executor import PipelineStepError

    image = _corpus(tmp_path)
    registre = ModuleRegistry()
    register_default_modules(registre)
    spec = PipelineSpec(
        name="mauvaise brique",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr_a",
                kind="ocr",
                adapter_name="precomputed:a",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
                inputs_from={ArtifactType.IMAGE: INITIAL_STEP_ID},
            ),
            PipelineStep(
                id="ocr_b",
                kind="ocr",
                adapter_name="precomputed:b",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
                inputs_from={ArtifactType.IMAGE: INITIAL_STEP_ID},
            ),
            PipelineStep(
                id="fusion",
                kind="merge",
                adapter_name="precomputed:a",  # pas une brique de fusion
                input_types=(ArtifactType.RAW_TEXT,),
                output_types=(ArtifactType.RAW_TEXT,),
                merge_from=("ocr_a", "ocr_b"),
            ),
        ),
    )
    modules = {
        "precomputed:a": registre.build("precomputed:a", {"source_label": "a"}),
        "precomputed:b": registre.build("precomputed:b", {"source_label": "b"}),
    }
    with pytest.raises(PipelineStepError, match="brique de fusion"):
        PipelineExecutor(code_version="test").execute_document(
            spec,
            modules,
            document_id="p1",
            initial_inputs={
                ArtifactType.IMAGE: Artifact(
                    id="i", document_id="p1", type=ArtifactType.IMAGE, uri=str(image)
                )
            },
            workspace_uri=str(tmp_path / "ws2"),
        )
