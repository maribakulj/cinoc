"""``ReadingOrderModule`` : deux hypothèses sur la page, à départager.

Sur une page à une colonne, lire de haut en bas est le bon ordre. Sur deux
colonnes, c'est l'erreur classique — les lignes s'entrelacent et le texte devient
inexploitable. Les deux stratégies sont livrées ensemble **exprès** : une ligne
de base qu'on veut battre, et la méthode qui prétend la battre. Un banc n'a
d'intérêt que s'il peut trancher.
"""

from __future__ import annotations

import random
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


def _colonnes_sous(y: int, suffixe: str) -> list[Region]:
    """Deux colonnes de deux blocs à partir de ``y``, déclarées entrelacées."""
    return [
        _bloc(f"G{suffixe}1", 20, y),
        _bloc(f"D{suffixe}1", 260, y + 10),
        _bloc(f"G{suffixe}2", 20, y + 60),
        _bloc(f"D{suffixe}2", 260, y + 70),
    ]


def test_a_wide_headline_then_two_columns_reads_each_column_whole() -> None:
    """Critère S15 : un titre pleine largeur au-dessus de deux colonnes se lit
    titre, colonne gauche entière, colonne droite entière. L'ancien regroupement
    par recouvrement rattachait les deux colonnes au titre — une seule colonne,
    lue de haut en bas : ``T G1 D1 G2 D2``, l'entrelacement qu'on voulait
    éviter (audit D-264, défaut 12)."""
    blocs = [_bloc("T", 20, 0, largeur=420), *_colonnes_sous(60, "")]
    assert ordonner_colonnes(blocs) == ["T", "G1", "G2", "D1", "D2"]


def test_a_full_width_separator_closes_the_columns_above_it() -> None:
    """Le cas pour lequel Breuel (2002) ordonne sous contraintes : un bloc
    pleine largeur au milieu de la page sépare deux paires de colonnes. On lit
    les deux colonnes du haut, le bloc large, puis les deux du bas — jamais la
    colonne gauche du bas avant la droite du haut."""
    blocs = [
        _bloc("T", 20, 0, largeur=420),
        *_colonnes_sous(60, "h"),
        _bloc("S", 20, 200, largeur=420),
        *_colonnes_sous(260, "b"),
    ]
    assert ordonner_colonnes(blocs) == [
        "T", "Gh1", "Gh2", "Dh1", "Dh2", "S", "Gb1", "Gb2", "Db1", "Db2",
    ]


def test_the_order_does_not_depend_on_the_declared_order() -> None:
    """L'ordre calculé ne lit que la géométrie : déclarer les blocs autrement
    ne change rien."""
    blocs = [_bloc("T", 20, 0, largeur=420), *_colonnes_sous(60, "")]
    assert ordonner_colonnes(blocs) == ordonner_colonnes(list(reversed(blocs)))


def _kraken(boites: list[tuple[int, int, int, int]]) -> list[int]:
    """Transcription littérale de ``kraken.lib.segmentation._reading_order`` et
    ``topsort`` (kraken 7.2, Apache-2.0 ; tranches ``(y, x)``, écriture
    gauche → droite) : oracle indépendant de l'implémentation, écrit ici."""
    lines = [(slice(y, y + h), slice(x, x + w)) for x, y, w, h in boites]
    n = len(lines)
    order = [[0] * n for _ in range(n)]

    def separates(w: tuple[slice, slice], u: tuple[slice, slice],
                  v: tuple[slice, slice]) -> bool:
        if w == u or w == v:
            return False
        if w[0].stop < min(u[0].start, v[0].start):
            return False
        if w[0].start > max(u[0].stop, v[0].stop):
            return False
        return w[1].start < u[1].stop and w[1].stop > v[1].start

    for i, u in enumerate(lines):
        for j, v in enumerate(lines):
            if u[1].start < v[1].stop and u[1].stop > v[1].start:
                if u[0].start < v[0].start:
                    order[i][j] = 1
            elif not [w for w in lines if separates(w, u, v)]:
                if u[1].stop < v[1].start:
                    order[i][j] = 1
    visited = [False] * n
    out: list[int] = []

    def visit(k: int) -> None:
        if visited[k]:
            return
        visited[k] = True
        for line in (i for i in range(n) if order[i][k]):
            visit(line)
        out.append(k)

    for k in range(n):
        visit(k)
    return out


def test_columns_is_the_order_of_breuel_as_kraken_computes_it() -> None:
    """Parité avec kraken sur 500 pages tirées au hasard (graine fixe), blocs
    déclarés de haut en bas — l'ordre de visite que ``columns`` se donne."""
    rng = random.Random(2002)
    for _ in range(500):
        boites = sorted(
            {
                (rng.randint(0, 300), rng.randint(0, 300),
                 rng.randint(5, 200), rng.randint(5, 80))
                for _ in range(rng.randint(1, 12))
            },
            key=lambda b: (b[1], b[0]),
        )
        blocs = [
            _bloc(f"r{k}", x, y, largeur=w, hauteur=h)
            for k, (x, y, w, h) in enumerate(boites)
        ]
        assert ordonner_colonnes(blocs) == [f"r{k}" for k in _kraken(boites)]


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
