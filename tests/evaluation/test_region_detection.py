"""``region_detection`` — F1 de segmentation par IoU de boîte (coords relatives).

Vérifie : appariement exact, **neutralisation des unités** (mm10 ALTO vs pixels),
sous-détection, décalage au-delà du seuil, boîte dérivée d'un polygone (PAGE),
non-applicabilité (pas de géométrie), et applicabilité sur **géométrie réelle**
(extrait ABBYY BnL).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Region,
)
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.layout import region_detection
from cinoc.evaluation.representations import load_representation

_EXCERPT = (
    Path(__file__).resolve().parents[1]
    / "fixtures" / "reference_corpus" / "bnl_waeschfra"
    / "waeschfra_p2_excerpt.alto.xml"
)


def _box_region(rid: str, x: int, y: int, w: int, h: int) -> Region:
    return Region(id=rid, geometry=Geometry(bbox=BBox(x=x, y=y, width=w, height=h)))


def _page(width: int, height: int, *regions: Region) -> CanonicalLayout:
    return CanonicalLayout(
        pages=(LayoutPage(width=width, height=height, regions=regions),)
    )


def _score(ref: CanonicalLayout, hyp: CanonicalLayout) -> object:
    return region_detection.fn(
        DocContext(document_id="d", reference=ref, hypothesis=hyp)
    )


_R1 = _box_region("r1", 0, 0, 40, 40)
_R2 = _box_region("r2", 0, 50, 40, 40)


def test_perfect_match_is_f1_one() -> None:
    layout = _page(100, 100, _R1, _R2)
    score = _score(layout, layout)
    assert score is not None and score.value == pytest.approx(1.0)
    assert (score.stat.tp, score.stat.fp, score.stat.fn) == (2, 0, 0)


def test_relative_coords_neutralize_units() -> None:
    # même mise en page, page 10× plus grande (≈ unités différentes) → F1 = 1.
    ref = _page(100, 100, _R1, _R2)
    hyp = _page(
        1000, 1000,
        _box_region("a", 0, 0, 400, 400),
        _box_region("b", 0, 500, 400, 400),
    )
    score = _score(ref, hyp)
    assert score is not None and score.value == pytest.approx(1.0)


def test_under_detection_lowers_recall() -> None:
    # 2 régions de référence, 1 seule détectée → P=1, R=0.5, F1=2/3.
    score = _score(_page(100, 100, _R1, _R2), _page(100, 100, _R1))
    assert score is not None
    assert score.value == pytest.approx(2 / 3)


def test_shifted_region_beyond_threshold_not_matched() -> None:
    shifted = _box_region("r1", 20, 20, 40, 40)  # IoU ≈ 0.14 < 0.5
    score = _score(_page(100, 100, _R1), _page(100, 100, shifted))
    assert score is not None and score.value == 0.0


def test_polygon_only_region_yields_box() -> None:
    poly = Region(
        id="p1",
        geometry=Geometry(polygon=((0, 0), (40, 0), (40, 40), (0, 40))),
    )
    score = _score(_page(100, 100, _R1), _page(100, 100, poly))
    assert score is not None and score.value == pytest.approx(1.0)


def test_no_geometry_is_not_applicable() -> None:
    plain = CanonicalLayout(pages=(LayoutPage(width=100, height=100, regions=(
        Region(id="r1"),
    )),))
    assert _score(plain, plain) is None


def test_no_page_dimensions_is_not_applicable() -> None:
    # géométrie présente mais page sans dimensions → normalisation impossible.
    no_dims = CanonicalLayout(pages=(LayoutPage(regions=(_R1,)),))
    assert _score(no_dims, no_dims) is None


def test_real_abbyy_geometry_self_match() -> None:
    excerpt = load_representation(str(_EXCERPT), ArtifactType.LAYOUT)
    assert isinstance(excerpt, CanonicalLayout)
    score = region_detection.fn(
        DocContext(document_id="bnl", reference=excerpt, hypothesis=excerpt)
    )
    assert score is not None
    assert score.value == pytest.approx(1.0)  # géométrie réelle, applicable
    assert score.stat.tp >= 1 and score.stat.fp == score.stat.fn == 0
