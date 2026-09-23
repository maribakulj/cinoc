"""Apparier les régions par géométrie quand les identifiants diffèrent.

Cinq des six métriques de structure appariaient les blocs **par identifiant**.
Deux systèmes différents n'en partagent jamais : la BnF numérote ``r_10_1``, un
détecteur ``r1``. Ces métriques étaient donc muettes ou — pire — fausses dès
qu'on comparait autre chose qu'un pipeline à lui-même.
"""

from __future__ import annotations

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
)


def _region(rid: str, x: int, texte: str) -> Region:
    return Region(
        id=rid,
        geometry=Geometry(bbox=BBox(x=x, y=0, width=90, height=40)),
        lines=(Line(id=f"{rid}:l1", text=texte),),
    )


def _page(ids: tuple[str, ...], textes: tuple[str, ...], ordre: tuple[str, ...]):
    regions = tuple(
        _region(rid, 100 * i, texte)
        for i, (rid, texte) in enumerate(zip(ids, textes, strict=True))
    )
    return CanonicalLayout(
        pages=(LayoutPage(width=1000, height=100, regions=regions,
                          reading_order=ordre),)
    )


def _ctx(ref: CanonicalLayout, hyp: CanonicalLayout) -> DocContext:
    return DocContext(document_id="d", reference=ref, hypothesis=hyp)


VT = _page(("r_1", "r_2", "r_3"), ("alpha", "beta", "gamma"), ("r_1", "r_2", "r_3"))


def test_identifiants_etrangers_apparies_par_geometrie() -> None:
    """Le cas qui motive tout : mêmes boîtes, mêmes textes, autres noms."""
    autre = _page(("b0", "b1", "b2"), ("alpha", "beta", "gamma"), ("b0", "b1", "b2"))
    assert correspondance(VT, autre) == {"r_1": "b0", "r_2": "b1", "r_3": "b2"}


def test_une_transcription_parfaite_ne_vaut_plus_le_pire_score() -> None:
    """``region_cer`` annonçait 1,0 — le pire possible — pour un texte exact."""
    autre = _page(("b0", "b1", "b2"), ("alpha", "beta", "gamma"), ("b0", "b1", "b2"))
    observation = region_cer.fn(_ctx(VT, autre))
    assert observation is not None
    assert observation.value == 0.0


def test_les_erreurs_reelles_restent_comptees() -> None:
    """L'appariement ne doit pas *pardonner* : seul le nom change, pas le texte."""
    autre = _page(("b0", "b1", "b2"), ("alpha", "XXXX", "gamma"), ("b0", "b1", "b2"))
    observation = region_cer.fn(_ctx(VT, autre))
    assert observation is not None
    assert observation.value > 0.0


def test_ordre_de_lecture_mesurable_entre_systemes() -> None:
    """``reading_order_tau`` rendait ``None`` : moins de deux blocs communs."""
    inverse = _page(("b0", "b1", "b2"), ("alpha", "beta", "gamma"),
                    ("b2", "b1", "b0"))
    tau = reading_order_tau.fn(_ctx(VT, inverse))
    assert tau is not None
    assert tau.value == 1.0  # ordre exactement inverse
    couverture = reading_order_coverage.fn(_ctx(VT, inverse))
    assert couverture is not None
    assert couverture.value == 1.0


def test_identifiants_partages_inchanges() -> None:
    """Aucune valeur déjà publiée ne doit bouger : l'identifiant reste prioritaire.

    Il est **exact**, il ne dépend d'aucun seuil, et la géométrie ne sert qu'en
    dernier recours.
    """
    assert correspondance(VT, VT) == {"r_1": "r_1", "r_2": "r_2", "r_3": "r_3"}
    observation = region_cer.fn(_ctx(VT, VT))
    assert observation is not None
    assert observation.value == 0.0


def test_un_ordre_citant_une_region_inexistante_n_est_pas_filtre() -> None:
    """Cas réel : la VT BnF cite 34 identifiants qui n'existent pas comme région.

    Les écarter changerait une couverture déjà publiée — on ne touche donc à
    rien quand les identifiants sont partagés.
    """
    bancal = CanonicalLayout(
        pages=(LayoutPage(
            width=1000, height=100,
            regions=VT.pages[0].regions,
            reading_order=("r_1", "r_2", "r_3", "fantome"),
        ),)
    )
    couverture = reading_order_coverage.fn(_ctx(bancal, bancal))
    assert couverture is not None
    assert couverture.value == 1.0


def test_sans_geometrie_aucun_appariement_invente() -> None:
    """Rien ne relie deux systèmes sans boîtes : dire « non applicable » est
    la seule réponse honnête."""
    nue = CanonicalLayout(
        pages=(LayoutPage(
            width=1000, height=100,
            regions=(Region(id="b0", lines=(Line(id="b0:l1", text="alpha"),)),),
            reading_order=("b0",),
        ),)
    )
    assert correspondance(VT, nue) == {}
