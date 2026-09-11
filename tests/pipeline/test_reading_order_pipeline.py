"""Bout-en-bout : le bon ordre de lecture fait baisser le taux d'erreur.

C'est la seule démonstration qui compte. Une métrique d'ordre qui ne se
traduirait par aucun gain sur le texte ne mesurerait qu'elle-même, et une étape
d'ordonnancement qui ne changerait pas le texte ne servirait à rien.

Le montage reproduit le cas de la presse ancienne — deux colonnes — que NDNP et
PP-Structure traitent tous deux par un module dédié.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.adapters.layout.reading_order import ReadingOrderModule
from cinoc.adapters.layout.to_text import LayoutToTextExtractor
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Line,
    Region,
)
from cinoc.evaluation.reading_order import kendall_distance
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

#: Une phrase coupée en six blocs, répartis sur deux colonnes.
COLONNE_GAUCHE = ["Il estoit une fois", "un roy de France", "qui aimoit fort"]
COLONNE_DROITE = ["les belles lettres", "et les faisoit", "imprimer a Paris"]
ATTENDU = " ".join(COLONNE_GAUCHE + COLONNE_DROITE)


def _bloc(nom: str, texte: str, x: int, y: int) -> Region:
    return Region(
        id=nom,
        region_type="text",
        geometry=Geometry(bbox=BBox(x=x, y=y, width=180, height=40)),
        lines=(Line(id=f"{nom}-l1", text=texte),),
    )


def _page() -> CanonicalLayout:
    blocs = []
    for i, texte in enumerate(COLONNE_GAUCHE):
        blocs.append(_bloc(f"G{i + 1}", texte, 20, 10 + i * 60))
    for i, texte in enumerate(COLONNE_DROITE):
        blocs.append(_bloc(f"D{i + 1}", texte, 260, 20 + i * 60))
    # Ordre déclaré volontairement entrelacé, comme le rendrait un segmenteur
    # qui n'a pas d'avis sur l'ordre de lecture.
    def _haut_gauche(region: Region) -> tuple[int, int]:
        assert region.geometry is not None and region.geometry.bbox is not None
        return (region.geometry.bbox.y, region.geometry.bbox.x)

    entrelace = tuple(b.id or "" for b in sorted(blocs, key=_haut_gauche))
    return CanonicalLayout(
        pages=(
            LayoutPage(
                width=460, height=220, regions=tuple(blocs), reading_order=entrelace
            ),
        )
    )


def _contexte(tmp_path: Path) -> RunContext:
    return RunContext(
        document_id="p1",
        workspace_uri=str(tmp_path),
        code_version="test",
        pipeline_name="p",
    )


def _projeter(layout: CanonicalLayout, tmp_path: Path, etiquette: str) -> str:
    source = tmp_path / f"{etiquette}.layout.json"
    source.write_bytes(layout.model_dump_json().encode("utf-8"))
    sortie = LayoutToTextExtractor(label=etiquette).execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a", document_id="p1", type=ArtifactType.LAYOUT, uri=str(source)
            )
        },
        {},
        _contexte(tmp_path),
        RunControl(),
    )
    produit = sortie.artifacts[ArtifactType.RAW_TEXT]
    assert produit.uri is not None
    return Path(produit.uri).read_text(encoding="utf-8")


def _cer(reference: str, hypothese: str) -> float:
    """Taux d'erreur par caractère, distance de Levenshtein sur les mots joints."""
    ref, hyp = reference.split(), hypothese.split()
    # Distance d'édition sur les mots : suffit à départager deux ordres, et
    # reste lisible dans le message d'échec.
    precedente = list(range(len(hyp) + 1))
    for i, mot_ref in enumerate(ref, 1):
        courante = [i]
        for j, mot_hyp in enumerate(hyp, 1):
            courante.append(
                min(
                    precedente[j] + 1,
                    courante[j - 1] + 1,
                    precedente[j - 1] + (mot_ref != mot_hyp),
                )
            )
        precedente = courante
    return precedente[-1] / max(1, len(ref))


def test_ordering_the_columns_lowers_the_error_rate(tmp_path: Path) -> None:
    page = _page()
    avant = _projeter(page, tmp_path, "brut")

    source = tmp_path / "in.layout.json"
    source.write_bytes(page.model_dump_json().encode("utf-8"))
    ordonnee_art = ReadingOrderModule(label="ro", strategy="columns").execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a", document_id="p1", type=ArtifactType.LAYOUT, uri=str(source)
            )
        },
        {},
        _contexte(tmp_path),
        RunControl(),
    ).artifacts[ArtifactType.LAYOUT]
    assert ordonnee_art.uri is not None
    ordonnee = CanonicalLayout.model_validate_json(
        Path(ordonnee_art.uri).read_bytes()
    )
    apres = _projeter(ordonnee, tmp_path, "ordonne")

    assert _cer(ATTENDU, avant) > 0.0, (
        "l'ordre entrelacé devrait justement produire un texte fautif — "
        "sinon ce test ne mesure rien"
    )
    # Comparaison sur la **suite des mots** : la projection sépare les blocs par
    # des retours à la ligne, et c'est l'ordre qu'on mesure, pas la ponctuation
    # d'assemblage.
    assert apres.split() == ATTENDU.split()
    assert _cer(ATTENDU, apres) == 0.0


def test_the_metric_attributes_the_fault_to_the_order(tmp_path: Path) -> None:
    """Et la métrique dédiée le dit **sans** passer par le texte.

    C'est sa raison d'être : le CER ne distingue pas une mauvaise lecture d'un
    mauvais ordre, celle-ci ne répond que de l'ordre.
    """
    page = _page()
    attendu = ["G1", "G2", "G3", "D1", "D2", "D3"]
    desordre = kendall_distance(attendu, list(page.pages[0].reading_order))
    assert desordre is not None and desordre > 0.0
    assert kendall_distance(attendu, attendu) == 0.0
