"""``LayoutGapFiller`` : une région ratée par le détecteur ne doit pas disparaître.

C'est le défaut qu'aucune métrique de texte ne désigne. Un bloc non détecté
n'est pas *mal lu*, il est **absent** : le CER monte, et rien ne dit si la cause
est un OCR médiocre ou un pan de page jamais soumis. NDNP-Open-OCR croise donc
deux lectures — par régions et page entière — et c'est ce que cette brique fait.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout.gap_fill import (
    GAPFILL_SUFFIX,
    LayoutGapFiller,
    combler,
    couvert,
)
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


def _region(
    rid: str, x: int, y: int, w: int = 100, h: int = 50, texte: str = ""
) -> Region:
    return Region(
        id=rid,
        region_type="text",
        geometry=Geometry(bbox=BBox(x=x, y=y, width=w, height=h)),
        lines=(Line(id=f"{rid}:l1", text=texte),) if texte else (),
    )


def _layout(*regions: Region) -> CanonicalLayout:
    return CanonicalLayout(
        pages=(LayoutPage(width=800, height=1000, regions=regions),)
    )


def _regions(layout: CanonicalLayout) -> tuple[Region, ...]:
    return layout.pages[0].regions


# --------------------------------------------------------------------------- #
# Le cœur : ce qui manque est repris, ce qui est déjà lu ne l'est pas deux fois
# --------------------------------------------------------------------------- #


def test_a_block_the_detector_missed_is_recovered() -> None:
    """La raison d'être de la brique."""
    detecte = _layout(_region("r1", 0, 0, texte="en haut"))
    page_entiere = _layout(
        _region("f1", 0, 0, texte="en haut"), _region("f2", 0, 500, texte="oublié")
    )
    complete, rattrapes = combler(detecte, page_entiere, seuil=0.5)
    assert rattrapes == 1
    textes = [ln.text for r in _regions(complete) for ln in r.lines]
    assert textes == ["en haut", "oublié"]


def test_a_block_already_read_is_not_duplicated() -> None:
    """Sans ce contrôle, chaque page verrait son texte doublé."""
    detecte = _layout(_region("r1", 0, 0, texte="lu"))
    page_entiere = _layout(_region("f1", 0, 0, texte="lu aussi"))
    complete, rattrapes = combler(detecte, page_entiere, seuil=0.5)
    assert rattrapes == 0
    assert len(_regions(complete)) == 1


def test_the_fine_reading_wins_verbatim() -> None:
    """La première source fait autorité : son texte n'est jamais remplacé.

    L'inverse annulerait tout le travail par région — plus fin — au profit d'une
    lecture de page entière, et la chaîne n'aurait servi à rien.
    """
    detecte = _layout(_region("r1", 0, 0, texte="lecture fine"))
    page_entiere = _layout(_region("f1", 0, 0, texte="lecture grossière"))
    complete, _ = combler(detecte, page_entiere, seuil=0.5)
    assert _regions(complete)[0].lines[0].text == "lecture fine"


def test_a_recovered_block_is_marked() -> None:
    """Sans marque, le rapport ne peut pas dire quelle part du texte vient du
    rattrapage — donc pas dire si le détecteur mérite qu'on lui fasse confiance."""
    complete, _ = combler(
        _layout(_region("r1", 0, 0)), _layout(_region("f2", 0, 500)), seuil=0.5
    )
    ajoute = _regions(complete)[-1]
    assert ajoute.region_type is not None
    assert ajoute.region_type.endswith(GAPFILL_SUFFIX)
    assert ajoute.id.startswith("gapfill_")


# --------------------------------------------------------------------------- #
# Le seuil : jugé sur la surface du candidat, pas sur une intersection brute
# --------------------------------------------------------------------------- #


def test_a_slight_overlap_does_not_swallow_a_distinct_block() -> None:
    """Un entrefilet qui mord de quelques pixels sur sa voisine reste un bloc.

    Avec un simple test d'intersection non nulle, il serait jeté — et son texte
    perdu sans trace.
    """
    retenue = _region("r1", 0, 0, w=100, h=100)
    voisin = _region("f1", 95, 0, w=100, h=100)  # 5 % de recouvrement
    assert not couvert(voisin, (retenue,), 0.5)


def test_a_mostly_covered_block_is_a_duplicate() -> None:
    retenue = _region("r1", 0, 0, w=100, h=100)
    doublon = _region("f1", 10, 0, w=100, h=100)  # 90 % de recouvrement
    assert couvert(doublon, (retenue,), 0.5)


def test_coverage_accumulates_across_several_regions() -> None:
    """Un bandeau couvert par **deux** colonnes est couvert, même si aucune ne
    le couvre seule. Juger région par région le laisserait passer.

    Les largeurs évitent la moitié exacte : à 50/50 le premier bloc atteindrait
    déjà le seuil (la comparaison est un « au moins »), et le test ne prouverait
    plus l'accumulation qu'il vise.
    """
    gauche = _region("r1", 0, 0, w=40, h=100)
    droite = _region("r2", 60, 0, w=40, h=100)
    bandeau = _region("f1", 0, 0, w=100, h=100)
    assert not couvert(bandeau, (gauche,), 0.5), "40 % seul reste sous le seuil"
    assert couvert(bandeau, (gauche, droite), 0.5), "80 % à deux le dépasse"


def test_exactly_the_threshold_counts_as_covered() -> None:
    """La convention est « au moins » : la moitié pile est un doublon.

    Le dire dans un test plutôt que dans un commentaire, parce que c'est le
    genre de borne qu'on inverse sans s'en apercevoir.
    """
    moitie = _region("r1", 0, 0, w=50, h=100)
    bandeau = _region("f1", 0, 0, w=100, h=100)
    assert couvert(bandeau, (moitie,), 0.5)


def test_a_block_without_geometry_is_left_out() -> None:
    """On ne sait pas où il est : l'ajouter dupliquerait du texte à une position
    inventée, et le placer au hasard vaut moins que de s'abstenir."""
    anonyme = Region(id="f1", region_type="text", lines=(Line(id="x", text="?"),))
    assert couvert(anonyme, (), 0.5)


def test_a_recovered_block_shields_the_next_candidate() -> None:
    """Deux blocs de secours qui se recouvrent ne doivent pas entrer tous les
    deux : le premier ajouté compte comme déjà lu pour le suivant."""
    complete, rattrapes = combler(
        _layout(_region("r1", 0, 0)),
        _layout(_region("f1", 0, 500), _region("f2", 5, 505)),
        seuil=0.5,
    )
    assert rattrapes == 1


# --------------------------------------------------------------------------- #
# Le contrat de fusion
# --------------------------------------------------------------------------- #


def _merge(tmp_path: Path, a: CanonicalLayout, b: CanonicalLayout) -> CanonicalLayout:
    chemins = []
    for nom, layout in (("regions", a), ("pleine", b)):
        p = tmp_path / f"{nom}.json"
        p.write_bytes(layout.model_dump_json().encode("utf-8"))
        chemins.append(
            Artifact(
                id=nom,
                document_id="d",
                type=ArtifactType.LAYOUT,
                uri=str(p),
                content_hash="0" * 64,
            )
        )
    out = LayoutGapFiller(label="g").execute_merge(
        {"regions": chemins[0], "pleine": chemins[1]},
        {},
        RunContext(
            document_id="d",
            code_version="1.0",
            pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    uri = out.artifacts[ArtifactType.LAYOUT].uri
    assert uri is not None
    return CanonicalLayout.model_validate_json(Path(uri).read_bytes())


def test_the_merge_runs_end_to_end(tmp_path: Path) -> None:
    complete = _merge(
        tmp_path,
        _layout(_region("r1", 0, 0, texte="fin")),
        _layout(
            _region("f1", 0, 0, texte="gros"),
            _region("f2", 0, 600, texte="repris"),
        ),
    )
    assert [ln.text for r in _regions(complete) for ln in r.lines] == ["fin", "repris"]


def test_exactly_two_sources_are_required(tmp_path: Path) -> None:
    """Trois lectures ne diraient pas laquelle fait autorité."""
    artefact = Artifact(
        id="a", document_id="d", type=ArtifactType.LAYOUT,
        uri=str(tmp_path / "x.json"), content_hash="0" * 64,
    )
    with pytest.raises(AdapterStepError, match="deux sources"):
        LayoutGapFiller(label="g").execute_merge(
            {"une": artefact},
            {},
            RunContext(
                document_id="d", code_version="1.0", pipeline_name="p",
                workspace_uri=str(tmp_path),
            ),
            RunControl(),
        )


@pytest.mark.parametrize("recouvrement", [0.0, -0.1, 1.5])
def test_an_out_of_range_overlap_is_refused(recouvrement: float) -> None:
    """Zéro compris : deux blocs qui se frôlent d'un pixel s'annuleraient."""
    with pytest.raises(AdapterStepError, match="overlap"):
        LayoutGapFiller(label="g", overlap=recouvrement)


def test_registered_as_a_merging_brick() -> None:
    from cinoc.app.modules.registry import ModuleRegistry, register_default_modules

    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build("gap_fill:g", {"label": "g"})
    assert hasattr(module, "execute_merge"), (
        "une brique de fusion doit exposer execute_merge, sinon l'exécuteur la "
        "refuse au moment du run."
    )
    assert module.input_types == frozenset({ArtifactType.LAYOUT})
