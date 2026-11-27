"""Contre-expertise — multipage et identifiants synthétisés (couche 3).

``CanonicalLayout`` porte plusieurs pages (ALTO multi-``<Page>``) ; les
métriques de structure aplatissent toutes les pages en une seule liste de
boîtes **relatives** et un seul dictionnaire ``{id: texte}``. Les identifiants
manquants sont synthétisés ``region_0``, ``region_1``… dans l'ordre du fichier
(``formats/_region_ids.py``), donc **identiques** entre deux ALTO sans ``ID``.
"""

from __future__ import annotations

import pytest

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
    reading_order_tau,
    region_cer,
    region_detection,
)
from cinoc.formats.layout_xml import parse_layout_xml

W = H = 128


def _reg(rid: str, y: int, text: str | None = None) -> Region:
    lines = (Line(id=f"{rid}.l1", text=text),) if text is not None else ()
    return Region(
        id=rid,
        geometry=Geometry(bbox=BBox(x=0, y=y, width=128, height=60)),
        lines=lines,
    )


def _page(*regions: Region) -> LayoutPage:
    return LayoutPage(
        width=W, height=H, regions=regions, reading_order=tuple(r.id for r in regions)
    )


def _value(metric, ref, hyp):
    obs = metric.fn(DocContext(document_id="d", reference=ref, hypothesis=hyp))
    return None if obs is None else obs.value


def _weight(metric, ref, hyp):
    obs = metric.fn(DocContext(document_id="d", reference=ref, hypothesis=hyp))
    return None if obs is None else obs.weight


@pytest.mark.valide
def test_multipage_detection__pas_d_appariement_entre_pages() -> None:
    """VT : p1 bloc en haut, p2 bloc en bas ; hypothèse : p1 bloc en bas, p2 bloc en
    haut. Aucune région n'est retrouvée sur sa page : F1 attendu 0."""
    ref = CanonicalLayout(pages=(_page(_reg("a", 0)), _page(_reg("b", 64))))
    hyp = CanonicalLayout(pages=(_page(_reg("x", 64)), _page(_reg("y", 0))))
    assert _value(region_detection, ref, hyp) == pytest.approx(0.0)


@pytest.mark.valide
def test_multipage_mise_en_page_repetee__region_cer_nul_pour_une_hypothese_parfaite() -> None:
    """Deux pages de même gabarit (un bloc en haut), identifiants étrangers,
    transcription parfaite : CER par région attendu 0 (chaque page avec elle-même)."""
    ref = CanonicalLayout(pages=(_page(_reg("p1_r1", 0, "alpha")), _page(_reg("p2_r1", 0, "beta"))))
    hyp = CanonicalLayout(pages=(_page(_reg("b1", 0, "alpha")), _page(_reg("b2", 0, "beta"))))
    assert _value(region_detection, ref, hyp) == pytest.approx(1.0)
    assert _value(region_cer, ref, hyp) == pytest.approx(0.0)
    assert _value(reading_order_tau, ref, hyp) in (None, pytest.approx(0.0))


@pytest.mark.valide
def test_multipage_ids_locaux_a_la_page__toutes_les_regions_comptent() -> None:
    """Ids locaux à la page (``r1`` sur p1 et p2, que le domaine n'interdit pas) ;
    l'hypothèse se trompe entièrement sur p1 (« XXXXX » pour « alpha ») et réussit
    p2. Attendu : CER par région 5/9 sur un poids de 9 caractères."""
    ref = CanonicalLayout(pages=(_page(_reg("r1", 0, "alpha")), _page(_reg("r1", 0, "beta"))))
    hyp = CanonicalLayout(pages=(_page(_reg("r1", 0, "XXXXX")), _page(_reg("r1", 0, "beta"))))
    assert _weight(region_cer, ref, hyp) == 9
    assert _value(region_cer, ref, hyp) == pytest.approx(5 / 9)


def _alto(*blocks: tuple[int, str]) -> bytes:
    """ALTO v4 **sans attribut ID** : un TextBlock pleine hauteur par (HPOS, mot)."""
    body = "".join(
        f'<TextBlock HPOS="{x}" VPOS="0" WIDTH="60" HEIGHT="128">'
        f'<TextLine HPOS="{x}" VPOS="0" WIDTH="60" HEIGHT="20">'
        f'<String CONTENT="{mot}" HPOS="{x}" VPOS="0" WIDTH="60" HEIGHT="20"/>'
        "</TextLine></TextBlock>"
        for x, mot in blocks
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">'
        '<Layout><Page ID="P1" WIDTH="128" HEIGHT="128" PHYSICAL_IMG_NR="1">'
        f'<PrintSpace HPOS="0" VPOS="0" WIDTH="128" HEIGHT="128">{body}</PrintSpace>'
        "</Page></Layout></alto>"
    ).encode()


@pytest.mark.valide
def test_alto_sans_id__appariement_par_geometrie_et_ordre_inverse_detecte() -> None:
    """Deux colonnes. VT (sans ID) : gauche « alpha » puis droite « beta ». Sortie
    (sans ID) : droite « beta » d'abord, puis gauche « alpha » — texte parfait, ordre
    de lecture inversé. Les deux reçoivent ``region_0``/``region_1`` : attendu CER par
    région 0 (géométrie) et tau 1,0 (inversion réelle)."""
    ref = parse_layout_xml(_alto((0, "alpha"), (64, "beta")))
    hyp = parse_layout_xml(_alto((64, "beta"), (0, "alpha")))
    assert [r.id for r in ref.pages[0].regions] == ["region_0", "region_1"]
    assert [r.id for r in hyp.pages[0].regions] == ["region_0", "region_1"]
    assert _value(region_detection, ref, hyp) == pytest.approx(1.0)
    assert _value(region_cer, ref, hyp) == pytest.approx(0.0)
    assert _value(reading_order_tau, ref, hyp) == pytest.approx(1.0)
