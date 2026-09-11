"""``ReadingOrderModule`` : deux hypothèses sur la page, à départager.

Sur une page à une colonne, lire de haut en bas est le bon ordre. Sur deux
colonnes, c'est l'erreur classique — les lignes s'entrelacent et le texte devient
inexploitable. Les deux stratégies sont livrées ensemble **exprès** : une ligne
de base qu'on veut battre, et la méthode qui prétend la battre. Un banc n'a
d'intérêt que s'il peut trancher.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout.reading_order import (
    ReadingOrderModule,
    ordonner_colonnes,
    ordonner_topdown,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import BBox, CanonicalLayout, Geometry, LayoutPage, Region
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext


def _bloc(nom: str, x: int, y: int, largeur: int = 180, hauteur: int = 40) -> Region:
    return Region(
        id=nom,
        region_type="text",
        geometry=Geometry(bbox=BBox(x=x, y=y, width=largeur, height=hauteur)),
    )


def _deux_colonnes() -> list[Region]:
    """Deux colonnes de trois blocs, entrelacées verticalement."""
    return [
        _bloc("G1", 20, 10),
        _bloc("D1", 260, 20),
        _bloc("G2", 20, 70),
        _bloc("D2", 260, 80),
        _bloc("G3", 20, 130),
        _bloc("D3", 260, 140),
    ]


def test_topdown_interleaves_the_columns() -> None:
    """La ligne de base fait exactement la faute qu'on cherche à mesurer."""
    assert ordonner_topdown(_deux_colonnes()) == ["G1", "D1", "G2", "D2", "G3", "D3"]


def test_columns_reads_one_column_at_a_time() -> None:
    assert ordonner_colonnes(_deux_colonnes()) == ["G1", "G2", "G3", "D1", "D2", "D3"]


def test_a_single_column_page_gives_the_same_order_either_way() -> None:
    """Sur une page simple, la stratégie savante ne doit rien casser."""
    page = [_bloc("A", 20, 10), _bloc("B", 20, 70), _bloc("C", 20, 130)]
    assert ordonner_topdown(page) == ordonner_colonnes(page) == ["A", "B", "C"]


def test_a_wide_headline_joins_the_column_it_overlaps() -> None:
    """Une manchette large chevauche les deux colonnes : le recouvrement est
    **relatif** à la largeur du plus étroit, donc elle est rattachée, pas isolée
    dans une colonne à elle seule."""
    blocs = [_bloc("TITRE", 20, 0, largeur=420), *_deux_colonnes()]
    ordre = ordonner_colonnes(blocs)
    assert ordre[0] == "TITRE"
    assert len(ordre) == 7


def test_without_geometry_the_declared_order_is_kept() -> None:
    """On ne devine pas un ordre sans coordonnées."""
    nus = [Region(id="A", region_type="text"), Region(id="B", region_type="text")]
    assert ordonner_colonnes(nus) == ["A", "B"]


def _executer(strategie: str, tmp_path: Path) -> CanonicalLayout:
    layout = CanonicalLayout(
        pages=(LayoutPage(width=460, height=200, regions=tuple(_deux_colonnes())),)
    )
    source = tmp_path / "in.layout.json"
    source.write_bytes(layout.model_dump_json().encode("utf-8"))
    module = ReadingOrderModule(label="ro", strategy=strategie)
    sortie = module.execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a", document_id="d", type=ArtifactType.LAYOUT, uri=str(source)
            )
        },
        {},
        RunContext(
            document_id="d",
            workspace_uri=str(tmp_path),
            code_version="t",
            pipeline_name="p",
        ),
        RunControl(),
    )
    produit = sortie.artifacts[ArtifactType.LAYOUT]
    assert produit.uri is not None
    return CanonicalLayout.model_validate_json(Path(produit.uri).read_bytes())


def test_the_module_writes_the_order_into_the_layout(tmp_path: Path) -> None:
    ordonnee = _executer("columns", tmp_path)
    assert ordonnee.pages[0].reading_order == ("G1", "G2", "G3", "D1", "D2", "D3")


def test_the_module_changes_nothing_else(tmp_path: Path) -> None:
    """Ordonner n'est pas re-segmenter : les blocs et leur géométrie sont intacts."""
    ordonnee = _executer("columns", tmp_path)
    assert [r.id for r in ordonnee.pages[0].regions] == [
        r.id for r in _deux_colonnes()
    ]
    assert ordonnee.pages[0].regions[0].geometry == _deux_colonnes()[0].geometry


def test_the_two_strategies_produce_different_layouts(tmp_path: Path) -> None:
    """Sans quoi il n'y aurait rien à départager."""
    a = _executer("topdown", tmp_path).pages[0].reading_order
    b = _executer("columns", tmp_path).pages[0].reading_order
    assert a != b


def test_an_unknown_strategy_is_refused_at_construction() -> None:
    with pytest.raises(AdapterStepError, match="inconnue"):
        ReadingOrderModule(label="ro", strategy="devine")


def test_a_missing_layout_says_so(tmp_path: Path) -> None:
    module = ReadingOrderModule(label="ro")
    with pytest.raises(AdapterStepError, match="LAYOUT manquant"):
        module.execute(
            {},
            {},
            RunContext(
                document_id="d",
                workspace_uri=str(tmp_path),
                code_version="t",
                pipeline_name="p",
            ),
            RunControl(),
        )
