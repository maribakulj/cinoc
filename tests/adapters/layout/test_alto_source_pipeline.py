"""``alto_source`` réglage ``pipeline`` : l'ALTO qu'un run Cinoc a écrit, et
lui seul (D-307)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout.alto_source import (
    AltoLayoutSource,
    alto_file_name,
    file_component,
)
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'
_ALTO = (
    f'<alto {_NS}><Layout><Page ID="P1" WIDTH="100" HEIGHT="50"><PrintSpace>'
    '<TextBlock ID="B1"><TextLine ID="L1"><String CONTENT="lu"/></TextLine>'
    "</TextBlock></PrintSpace></Page></Layout></alto>"
).encode()


def _image(path: Path) -> dict[ArtifactType, Artifact]:
    path.write_bytes(b"png")
    return {
        ArtifactType.IMAGE: Artifact(
            id="p:image", document_id="p", type=ArtifactType.IMAGE,
            uri=str(path), content_hash=compute_content_hash(b"png"),
        )
    }


def _run(module: AltoLayoutSource, image: Path, workspace: Path) -> object:
    return module.execute(
        _image(image), {},
        RunContext(document_id="p", code_version="t", pipeline_name="p",
                   workspace_uri=str(workspace)),
        RunControl(),
    )


def test_file_component_is_idempotent() -> None:
    nom = file_component("segmentation_puis_lecture · tesseract_layout → tesseract")
    assert nom == "segmentation_puis_lecture_tesseract_layout_tesseract"
    assert file_component(nom) == nom


def test_alto_file_name() -> None:
    assert alto_file_name("a/b.v2", "ocr · x") == "a_b.v2.ocr_x.alto.xml"


def test_with_a_pipeline_only_its_alto_is_read(tmp_path: Path) -> None:
    (tmp_path / "p.xml").write_bytes(_ALTO)  # l'ALTO d'un autre : pas un repli
    with pytest.raises(AdapterStepError, match="p.ocr.alto.xml"):
        _run(AltoLayoutSource(pipeline="ocr"), tmp_path / "p.png", tmp_path / "ws")
    (tmp_path / "p.ocr.alto.xml").write_bytes(_ALTO)
    sortie = _run(AltoLayoutSource(pipeline="ocr"), tmp_path / "p.png", tmp_path / "ws")
    assert ArtifactType.LAYOUT in sortie.artifacts  # type: ignore[attr-defined]


@pytest.mark.parametrize("nom", ["../x", "a/b", "ocr simple", "x.y"])
def test_a_name_that_is_not_a_file_component_is_refused(nom: str) -> None:
    with pytest.raises(AdapterStepError, match="pipeline"):
        AltoLayoutSource(pipeline=nom)
