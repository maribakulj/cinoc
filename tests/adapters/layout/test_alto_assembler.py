"""``AltoAssembler`` : assemblage LAYOUT rempli → ALTO_XML, puis bout-en-bout.

Ferme la boucle de segmentation : un ``CanonicalLayout`` rempli (sortie fan-out)
est assemblé en ALTO 4 déterministe, rechargé **comme layout** par l'évaluation
(`load_representation` détecte l'ALTO) et mesuré par ``region_cer``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout.assembler import AltoAssembler
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Line,
    Region,
)
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.layout import region_cer
from cinoc.evaluation.representations import load_representation
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.formats._xsd import alto_errors


def _filled(*regions: tuple[str, str]) -> CanonicalLayout:
    return CanonicalLayout(
        pages=(
            LayoutPage(
                regions=tuple(
                    Region(id=rid, lines=(Line(text=text),)) for rid, text in regions
                ),
                reading_order=tuple(rid for rid, _ in regions),
            ),
        )
    )


def _layout_artifact(tmp_path: Path, layout: CanonicalLayout) -> Artifact:
    path = tmp_path / "doc1.filled.layout.json"
    path.write_bytes(layout.model_dump_json().encode("utf-8"))
    return Artifact(
        id="doc1:fanout:layout",
        document_id="doc1",
        type=ArtifactType.LAYOUT,
        uri=str(path),
    )


def _context(tmp_path: Path) -> RunContext:
    return RunContext(
        document_id="doc1",
        code_version="1.0",
        pipeline_name="seg",
        workspace_uri=str(tmp_path),
    )


def test_assembles_alto_xml_artifact(tmp_path: Path) -> None:
    layout = _filled(("b1", "hello world"), ("b2", "second block"))
    out = AltoAssembler().execute(
        {ArtifactType.LAYOUT: _layout_artifact(tmp_path, layout)},
        {},
        _context(tmp_path),
        RunControl(),
    )
    artifact = out.artifacts[ArtifactType.ALTO_XML]
    assert artifact.type is ArtifactType.ALTO_XML
    assert artifact.uri is not None and artifact.content_hash is not None
    assert Path(artifact.uri).read_bytes().lstrip().startswith(b"<")


def test_assembled_alto_reloads_as_layout_and_scores(tmp_path: Path) -> None:
    # hyp : b2 a une faute (1 substitution) ; GT exacte.
    hyp = _filled(("b1", "hello world"), ("b2", "second blocX"))
    out = AltoAssembler().execute(
        {ArtifactType.LAYOUT: _layout_artifact(tmp_path, hyp)},
        {},
        _context(tmp_path),
        RunControl(),
    )
    alto_uri = out.artifacts[ArtifactType.ALTO_XML].uri
    assert alto_uri is not None
    # L'ALTO assemblé est rechargé COMME layout (sniff ALTO) et comparé à la GT.
    hyp_layout = load_representation(alto_uri, ArtifactType.LAYOUT)
    gt_layout = _filled(("b1", "hello world"), ("b2", "second block"))
    score = region_cer.fn(
        DocContext(document_id="doc1", reference=gt_layout, hypothesis=hyp_layout)
    )
    assert score is not None
    assert score.value == pytest.approx(1 / 23)  # 1 erreur / (11 + 12) chars


def test_assembler_rejects_missing_layout(tmp_path: Path) -> None:
    with pytest.raises(AdapterStepError, match="LAYOUT manquant"):
        AltoAssembler().execute({}, {}, _context(tmp_path), RunControl())


def test_segmenter_layout_assembles_into_valid_alto_4(tmp_path: Path) -> None:
    """La forme que livre le fan-out hybride : régions typées et géolocalisées,
    lignes reconnues sans géométrie ni mots, une région rattrapée marquée.
    Le XSD officiel ALTO 4.4 est l'oracle (A9)."""
    box = Geometry(bbox=BBox(x=10, y=20, width=300, height=40))
    layout = CanonicalLayout(
        pages=(
            LayoutPage(
                width=1240,
                height=1754,
                regions=(
                    Region(
                        id="r1",
                        region_type="title",
                        geometry=box,
                        lines=(Line(text="Chapitre premier"),),
                    ),
                    Region(id="r2", region_type="text+gapfill", geometry=box),
                    Region(id="r3", geometry=box, lines=(Line(text="corps"),)),
                ),
                reading_order=("r1", "r2", "r3"),
            ),
        )
    )
    out = AltoAssembler().execute(
        {ArtifactType.LAYOUT: _layout_artifact(tmp_path, layout)},
        {},
        _context(tmp_path),
        RunControl(),
    )
    uri = out.artifacts[ArtifactType.ALTO_XML].uri
    assert uri is not None
    data = Path(uri).read_bytes()
    assert alto_errors(data) == []
    assert b"<MeasurementUnit>pixel</MeasurementUnit>" in data
    reloaded = load_representation(uri, ArtifactType.LAYOUT)
    assert isinstance(reloaded, CanonicalLayout)
    assert [r.region_type for r in reloaded.pages[0].regions] == [
        "title",
        "text+gapfill",
        "text",
    ]
