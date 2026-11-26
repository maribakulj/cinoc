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
from tests.formats._xsd import page_errors


def _layout_ecrit(tmp_path: Path, layout: CanonicalLayout | None = None) -> Path:
    layout = layout or CanonicalLayout(
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


def _executer(tmp_path: Path, layout: CanonicalLayout | None = None) -> Path:
    sortie = PageAssembler().execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a",
                document_id="p1",
                type=ArtifactType.LAYOUT,
                uri=str(_layout_ecrit(tmp_path, layout)),
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


def _hybride() -> CanonicalLayout:
    """La forme que livre le fan-out hybride : régions typées et géolocalisées
    par le segmenteur, une ligne reconnue **sans géométrie** par région, une
    région rattrapée marquée, une figure sans texte."""
    boite = Geometry(bbox=BBox(x=10, y=20, width=300, height=40))
    return CanonicalLayout(
        pages=(
            LayoutPage(
                width=1240,
                height=1754,
                regions=(
                    Region(
                        id="r1",
                        region_type="title",
                        geometry=boite,
                        lines=(Line(id="r1.l1", text="Chapitre premier"),),
                    ),
                    Region(id="r2", region_type="text+gapfill", geometry=boite),
                    Region(id="r3", region_type="figure", geometry=boite),
                    Region(
                        id="r4", geometry=boite, lines=(Line(id="r4.l1", text="corps"),)
                    ),
                ),
                reading_order=("r1", "r2", "r3", "r4"),
            ),
        )
    )


def test_hybrid_output_is_valid_page_2019(tmp_path: Path) -> None:
    """Le XSD officiel PAGE 2019 est l'oracle (A9) — sur le chemin réel."""
    from cinoc.formats.pagexml.layout_map import page_to_layout
    from cinoc.formats.pagexml.parser import parse_pagexml

    data = _executer(tmp_path, _hybride()).read_bytes()
    assert page_errors(data) == []
    relu = page_to_layout(parse_pagexml(data)).pages[0]
    assert [r.region_type for r in relu.regions] == [
        "title", "text+gapfill", "figure", "text"
    ]
    assert [ligne.id for r in relu.regions for ligne in r.lines] == ["r1.l1", "r4.l1"]
    assert all(ligne.geometry is None for r in relu.regions for ligne in r.lines)


@pytest.mark.parametrize(
    ("changement", "motif"),
    [({"coordinate_unit": "mm10"}, "pixel"), ({"pages": ()}, "une page")],
)
def test_an_unwritable_layout_fails_the_step(
    tmp_path: Path, changement: dict[str, object], motif: str
) -> None:
    """Un PAGE faux serait pire qu'aucun : l'étape échoue en disant pourquoi."""
    layout = _hybride().model_copy(update=changement)
    with pytest.raises(AdapterStepError, match=motif):
        _executer(tmp_path, layout)


def test_unknown_page_size_fails_the_step(tmp_path: Path) -> None:
    page = _hybride().pages[0].model_copy(update={"width": None})
    with pytest.raises(AdapterStepError, match="dimensions"):
        _executer(tmp_path, CanonicalLayout(pages=(page,)))
