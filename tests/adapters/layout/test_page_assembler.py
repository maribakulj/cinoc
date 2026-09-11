"""``PageAssembler`` : la sortie qui rentre dans l'outil de relecture.

Un benchmark n'a de valeur d'archive que si sa sortie est **ré-importable**.
ALTO l'était déjà ; PAGE manquait, alors que le parseur existait et que le type
``page_xml`` était réservé au domaine depuis l'origine sans que rien ne le
produise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout.page_assembler import PageAssembler
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
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext


def _layout_ecrit(tmp_path: Path) -> Path:
    layout = CanonicalLayout(
        pages=(
            LayoutPage(
                width=600,
                height=400,
                regions=(
                    Region(
                        id="R1",
                        region_type="paragraph",
                        geometry=Geometry(bbox=BBox(x=10, y=10, width=300, height=80)),
                        lines=(Line(id="L1", text="le soleil luisoit"),),
                    ),
                ),
                reading_order=("R1",),
            ),
        )
    )
    chemin = tmp_path / "in.layout.json"
    chemin.write_bytes(layout.model_dump_json().encode("utf-8"))
    return chemin


def _executer(tmp_path: Path) -> Path:
    sortie = PageAssembler().execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a",
                document_id="p1",
                type=ArtifactType.LAYOUT,
                uri=str(_layout_ecrit(tmp_path)),
            )
        },
        {},
        RunContext(
            document_id="p1",
            workspace_uri=str(tmp_path / "ws"),
            code_version="t",
            pipeline_name="p",
        ),
        RunControl(),
    )
    produit = sortie.artifacts[ArtifactType.PAGE_XML]
    assert produit.uri is not None
    return Path(produit.uri)


def test_it_produces_page_xml(tmp_path: Path) -> None:
    produit = _executer(tmp_path)
    assert produit.name.endswith(".page.xml")
    contenu = produit.read_text(encoding="utf-8")
    assert contenu.startswith("<PcGts")
    assert "primaresearch.org/PAGE" in contenu


def test_the_produced_file_reimports(tmp_path: Path) -> None:
    """La seule vérification qui compte pour un format d'archive."""
    from cinoc.formats.pagexml.layout_map import page_to_layout
    from cinoc.formats.pagexml.parser import parse_pagexml

    relu = page_to_layout(parse_pagexml(_executer(tmp_path).read_bytes()))
    assert relu.pages[0].regions[0].lines[0].text == "le soleil luisoit"
    assert relu.pages[0].reading_order == ("R1",)


def test_it_declares_the_reserved_type(tmp_path: Path) -> None:
    """``page_xml`` était réservé et mort : plus maintenant."""
    module = PageAssembler()
    assert module.output_types == frozenset({ArtifactType.PAGE_XML})


def test_a_missing_layout_says_so(tmp_path: Path) -> None:
    with pytest.raises(AdapterStepError, match="LAYOUT manquant"):
        PageAssembler().execute(
            {},
            {},
            RunContext(
                document_id="p1",
                workspace_uri=str(tmp_path),
                code_version="t",
                pipeline_name="p",
            ),
            RunControl(),
        )


def test_an_unreadable_layout_names_the_file(tmp_path: Path) -> None:
    casse = tmp_path / "casse.layout.json"
    casse.write_text("{ pas du json", encoding="utf-8")
    with pytest.raises(AdapterStepError, match="casse.layout.json"):
        PageAssembler().execute(
            {
                ArtifactType.LAYOUT: Artifact(
                    id="a",
                    document_id="p1",
                    type=ArtifactType.LAYOUT,
                    uri=str(casse),
                )
            },
            {},
            RunContext(
                document_id="p1",
                workspace_uri=str(tmp_path),
                code_version="t",
                pipeline_name="p",
            ),
            RunControl(),
        )
