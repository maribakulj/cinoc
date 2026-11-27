"""Contre-expertise — appariement des régions (couche 3, ``metrics/layout.py``).

Affirmation 4 du mainteneur : l'appariement IoU est **glouton** et peut rendre
moins que l'optimum global ; l'ordre des régions, des identifiants identiques
mais non homologues ou partiellement partagés, et le multipage faussent les
métriques de structure.

Référence indépendante : ``scipy.optimize.linear_sum_assignment`` sur la même
matrice d'IoU (seuil 0,5 inclusif, comme Cinoc), en maximisant (a) le nombre de
paires au-dessus du seuil — le critère que compte ``region_detection`` — et
(b) la somme des IoU au-dessus du seuil. Les IoU de référence sont calculées à
la main dans le test, pas par Cinoc.

Toutes les pages font 128 × 128 et les boîtes occupent toute la hauteur : les
coordonnées relatives sont dyadiques (exactes en flottant), l'IoU se réduit à
une IoU d'intervalles en *x*, vérifiable à la main.
"""

from __future__ import annotations

from itertools import permutations

import numpy as np
import pytest
from scipy.optimize import linear_sum_assignment

from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Line,
    Region,
)
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.layout import (
    correspondance,
    reading_order_coverage,
    reading_order_tau,
    region_cer,
    region_detection,
)

W = H = 128
THRESHOLD = 0.5


def _reg(rid: str, x: int, w: int, text: str | None = None, y: int = 0, h: int = H) -> Region:
    lines = (Line(id=f"{rid}.l1", text=text),) if text is not None else ()
    return Region(
        id=rid,
        geometry=Geometry(bbox=BBox(x=x, y=y, width=w, height=h)),
        lines=lines,
    )


def _layout(*regions: Region, order: tuple[str, ...] | None = None) -> CanonicalLayout:
    return CanonicalLayout(
        pages=(
            LayoutPage(
                width=W,
                height=H,
                regions=regions,
                reading_order=order if order is not None else tuple(r.id for r in regions),
            ),
        )
    )


def _value(metric, ref: CanonicalLayout, hyp: CanonicalLayout) -> float | None:
    obs = metric.fn(DocContext(document_id="d", reference=ref, hypothesis=hyp))
    return None if obs is None else obs.value


def _iou_1d(a: tuple[int, int], b: tuple[int, int]) -> float:
    """IoU d'intervalles [x0, x1] — boîtes pleine hauteur (calcul indépendant)."""
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union


def _optimal_f1(ref: list[tuple[int, int]], hyp: list[tuple[int, int]]) -> tuple[float, float]:
    """F1 optimal (scipy) : (max-cardinalité, max-somme-IoU), seuil inclusif."""
    iou = np.array([[_iou_1d(r, h) for h in hyp] for r in ref])
    ok = iou >= THRESHOLD
    # (a) cardinalité maximale des paires au-dessus du seuil
    rows, cols = linear_sum_assignment(ok.astype(float), maximize=True)
    tp_card = int(ok[rows, cols].sum())
    # (b) somme maximale des IoU au-dessus du seuil
    rows, cols = linear_sum_assignment(np.where(ok, iou, 0.0), maximize=True)
    tp_sum = int(ok[rows, cols].sum())

    def f1(tp: int) -> float:
        p, r = tp / len(hyp), tp / len(ref)
        return 2 * p * r / (p + r) if p + r else 0.0

    return f1(tp_card), f1(tp_sum)


# --- contre-exemple minimal (2 réf × 2 hyp) ---------------------------------
# A=[0,10], B=[2,12] (réf, chevauchantes) ; X=[1,11], Y=[-3,7] (hyp).
# IoU(A,X)=9/11≈0,818  IoU(A,Y)=7/13≈0,538  IoU(B,X)=9/11≈0,818  IoU(B,Y)=5/15≈0,333
# Glouton (réf dans l'ordre A, B) : A prend X (meilleure), B n'a plus que Y (<0,5).
# Optimum : A↔Y, B↔X → 2 paires.
A, B = (0, 10), (2, 12)
X, Y = (1, 11), (-3, 7)


def _box(rid: str, iv: tuple[int, int], text: str | None = None) -> Region:
    return _reg(rid, iv[0], iv[1] - iv[0], text)


def test_glouton_vs_optimal__la_detection_atteint_l_optimum_global() -> None:
    """2 réf × 2 hyp où le glouton n'apparie qu'une paire : le F1 doit valoir
    l'optimum de ``linear_sum_assignment`` (1,0), pas 0,5."""
    assert _iou_1d(A, X) == pytest.approx(9 / 11)
    assert _iou_1d(A, Y) == pytest.approx(7 / 13)
    assert _iou_1d(B, X) == pytest.approx(9 / 11)
    assert _iou_1d(B, Y) == pytest.approx(1 / 3)
    f1_card, f1_sum = _optimal_f1([A, B], [X, Y])
    assert f1_card == f1_sum == pytest.approx(1.0)
    ref = _layout(_box("A", A), _box("B", B))
    hyp = _layout(_box("X", X), _box("Y", Y))
    assert _value(region_detection, ref, hyp) == pytest.approx(f1_card)


def test_glouton_vs_optimal__region_cer_suit_l_appariement_optimal() -> None:
    """Même géométrie, identifiants étrangers, textes parfaits sous l'appariement
    optimal (A↔Y, B↔X) : le CER par région doit valoir 0."""
    ref = _layout(_box("A", A, "alpha"), _box("B", B, "beta"))
    hyp = _layout(_box("X", X, "beta"), _box("Y", Y, "alpha"))
    assert correspondance(ref, hyp) == {"A": "Y", "B": "X"}
    assert _value(region_cer, ref, hyp) == pytest.approx(0.0)


def test_ordre_des_regions_de_reference__la_detection_n_en_depend_pas() -> None:
    """Permuter les régions de la **référence** (même ensemble) ne doit pas
    changer le F1 ; le glouton parcourt la référence dans l'ordre du fichier."""
    hyp = _layout(_box("X", X), _box("Y", Y))
    valeurs = {
        _value(region_detection, _layout(*(_box(n, iv) for n, iv in perm)), hyp)
        for perm in permutations((("A", A), ("B", B)))
    }
    assert len(valeurs) == 1, valeurs


def test_ordre_des_regions_hypothese__la_detection_n_en_depend_pas_hors_egalites() -> None:
    """Permuter les régions de l'**hypothèse** sans IoU égales : F1 inchangé
    (ici, réfutation partielle : seul l'ordre de la référence compte)."""
    ref = _layout(_box("A", A), _box("B", B))
    valeurs = {
        _value(region_detection, ref, _layout(*(_box(n, iv) for n, iv in perm)))
        for perm in permutations((("X", X), ("Y", Y)))
    }
    assert len(valeurs) == 1, valeurs


def test_ordre_des_regions_hypothese__egalite_d_iou_sans_effet_d_ordre() -> None:
    """A a la même IoU (9/11, exacte en dyadique) avec X=[1,11] et Y=[-1,9] ; B=[4,14]
    ne recouvre que X au seuil. Permuter l'hypothèse ne doit pas changer le F1
    (optimum : A↔Y, B↔X = 1,0)."""
    a, b = (0, 10), (4, 14)
    x, y = (1, 11), (-1, 9)
    assert _iou_1d(a, x) == _iou_1d(a, y) == pytest.approx(9 / 11)
    assert _iou_1d(b, x) == pytest.approx(7 / 13)
    assert _iou_1d(b, y) == pytest.approx(1 / 3)
    ref = _layout(_box("a", a), _box("b", b))
    f1 = {
        tuple(n for n, _ in perm): _value(
            region_detection, ref, _layout(*(_box(n, iv) for n, iv in perm))
        )
        for perm in permutations((("x", x), ("y", y)))
    }
    assert list(f1.values()) == [pytest.approx(1.0)] * 2, f1


# --- ordre de lecture : permutation de l'hypothèse ---------------------------

def _trois(ids: tuple[str, str, str], textes=("alpha", "beta", "gamma")) -> list[Region]:
    # boîtes disjointes côte à côte : [0,40], [42,82], [84,124]
    return [_reg(rid, 42 * i, 40, t) for i, (rid, t) in enumerate(zip(ids, textes))]


def test_permutation_regions_hypothese__detection_inchangee_ordre_de_lecture_mesure() -> None:
    """Hypothèse = mêmes régions déclarées dans un autre ordre, ordre de lecture
    explicitement inversé : détection 1,0 inchangée, tau = 1,0 (inversion totale)."""
    ref = _layout(*_trois(("r1", "r2", "r3")))
    regs = _trois(("b1", "b2", "b3"))
    hyp = _layout(regs[2], regs[0], regs[1], order=("b3", "b2", "b1"))
    assert _value(region_detection, ref, hyp) == pytest.approx(1.0)
    assert _value(region_cer, ref, hyp) == pytest.approx(0.0)
    assert _value(reading_order_tau, ref, hyp) == pytest.approx(1.0)


# --- identifiants identiques mais non homologues ----------------------------

def test_ids_identiques_non_homologues__appariement_par_geometrie() -> None:
    """VT r1=haut « alpha », r2=bas « beta » ; un détecteur numérote r1=bas « beta »,
    r2=haut « alpha » (même page, transcription parfaite, ordre de lecture identique
    haut→bas). Attendu : CER par région 0, tau 0."""
    ref = _layout(
        _reg("r1", 0, 128, "alpha", y=0, h=60),
        _reg("r2", 0, 128, "beta", y=64, h=60),
        order=("r1", "r2"),
    )
    hyp = _layout(
        _reg("r1", 0, 128, "beta", y=64, h=60),
        _reg("r2", 0, 128, "alpha", y=0, h=60),
        order=("r2", "r1"),  # haut puis bas, comme la VT
    )
    assert _value(region_detection, ref, hyp) == pytest.approx(1.0)
    assert _value(region_cer, ref, hyp) == pytest.approx(0.0)
    assert _value(reading_order_tau, ref, hyp) == pytest.approx(0.0)


def test_ids_partiellement_partages__la_region_non_nommee_reste_appariee() -> None:
    """VT {r1 haut, r2 bas} ; hypothèse {r1 haut, x9 bas}, textes parfaits. Un seul id
    commun suffit à désactiver la géométrie : attendu CER par région 0, couverture
    d'ordre 1,0, tau 0."""
    ref = _layout(
        _reg("r1", 0, 128, "alpha", y=0, h=60),
        _reg("r2", 0, 128, "beta", y=64, h=60),
    )
    hyp = _layout(
        _reg("r1", 0, 128, "alpha", y=0, h=60),
        _reg("x9", 0, 128, "beta", y=64, h=60),
    )
    assert _value(region_cer, ref, hyp) == pytest.approx(0.0)
    assert _value(reading_order_coverage, ref, hyp) == pytest.approx(1.0)
    assert _value(reading_order_tau, ref, hyp) == pytest.approx(0.0)


def test_ids_partages_homologues__identite_exacte_conservee() -> None:
    """Témoin (réfutation) : quand les ids partagés **sont** homologues, l'appariement
    par id rend le bon score (CER par région 0, tau 0)."""
    ref = _layout(*_trois(("r1", "r2", "r3")))
    assert _value(region_cer, ref, ref) == pytest.approx(0.0)
    assert _value(reading_order_tau, ref, ref) == pytest.approx(0.0)
