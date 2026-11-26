"""Le fan-out dit au reconnaisseur **quelle classe de région** il est en train de lire.

Sans cette information, un reconnaisseur applique le même réglage à un pavé
d'article et à une publicité. NDNP-Open-OCR, lui, bascule de ``--psm 6`` à
``--psm 3`` selon la classe rendue par le segmenteur — c'est cette information
qui manquait pour le reproduire.

Le contrat du ``Module`` dit que ``params`` est **une copie mutable fournie par
le runner** : la renseigner est le rôle du fan-out. Ce qui serait un
détournement, c'est qu'un module écrive dedans.
"""

from __future__ import annotations

from typing import Any

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
from cinoc.pipeline.fanout import REGION_TYPE_PARAM, _fill_region, run_region_fanout
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext


class _Espion:
    """Reconnaisseur qui ne lit rien : il note ce qu'on lui a passé.

    Il lève ensuite, et le fan-out doit encaisser — une région non reconnue est
    ignorée avec un avertissement, pas une cause d'échec du run.
    """

    name = "espion"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def __init__(self) -> None:
        self.vus: list[Any] = []

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, Any],
        context: RunContext,
        control: RunControl,
    ) -> Any:
        self.vus.append(params.get(REGION_TYPE_PARAM))
        raise AdapterStepError("l'espion ne lit pas, il note.")


def _contexte(tmp_path: Any) -> RunContext:
    return RunContext(
        document_id="d",
        code_version="1.0",
        pipeline_name="p",
        workspace_uri=str(tmp_path),
    )


def _appel(tmp_path: Any, region_type: str | None) -> list[Any]:
    espion = _Espion()
    page = LayoutPage(width=100, height=100, regions=())
    region = Region(
        id="r1",
        region_type=region_type,
        geometry=Geometry(bbox=BBox(x=0, y=0, width=10, height=10)),
    )
    image = Artifact(
        id="i",
        document_id="d",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"),
        content_hash="0" * 64,
    )
    _fill_region(
        region, page, image, espion, _contexte(tmp_path), RunControl(), {}, None
    )
    return espion.vus


def test_the_region_class_reaches_the_recognizer(tmp_path: Any) -> None:
    assert _appel(tmp_path, "advertisement") == ["advertisement"]


def test_a_region_without_a_class_passes_an_empty_string(tmp_path: Any) -> None:
    """``None`` traverserait un paramètre typé ``ParamValue`` sans y avoir sa
    place ; la chaîne vide dit « pas de classe » sans mentir sur le type."""
    assert _appel(tmp_path, None) == [""]


def test_the_filled_layout_keeps_its_coordinate_unit(tmp_path: Any) -> None:
    """Un ALTO ``mm10`` relu reste en ``mm10`` une fois rempli : l'assemblage
    réécrit cette unité, il ne doit pas la recevoir réinitialisée en pixels."""
    layout = CanonicalLayout(
        pages=(LayoutPage(width=100, height=100, regions=()),),
        coordinate_unit="mm10",
    )
    image = Artifact(
        id="i",
        document_id="d",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"),
        content_hash="0" * 64,
    )
    rempli, _ = run_region_fanout(
        layout=layout,
        page_image=image,
        recognizer=_Espion(),
        context=_contexte(tmp_path),
        control=RunControl(),
    )
    assert rempli.coordinate_unit == "mm10"


def test_a_failing_region_does_not_abort_the_page(tmp_path: Any) -> None:
    """L'espion lève à chaque appel, et le fan-out doit malgré tout rendre la
    région — non reconnue, mais présente. Perdre la page entière parce qu'un
    bloc résiste serait pire que le bloc manquant."""
    espion = _Espion()
    page = LayoutPage(width=100, height=100, regions=())
    region = Region(
        id="r1",
        region_type="text",
        geometry=Geometry(bbox=BBox(x=0, y=0, width=10, height=10)),
    )
    image = Artifact(
        id="i",
        document_id="d",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"),
        content_hash="0" * 64,
    )
    rendue, usage = _fill_region(
        region, page, image, espion, _contexte(tmp_path), RunControl(), {}, None
    )
    assert rendue.id == "r1"
    assert rendue.lines == (), "aucune ligne n'a pu être lue."
    assert usage is None


# --------------------------------------------------------------------------- #
# Un reconnaisseur qui sait découper son bloc en lignes doit pouvoir le dire
# --------------------------------------------------------------------------- #


class _Multiligne:
    """Reconnaisseur qui rend un **sous-layout**, pas une chaîne."""

    name = "multiligne"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.LAYOUT})

    def __init__(self, chemin: Any, layout: CanonicalLayout) -> None:
        self._chemin = chemin
        self._chemin.write_bytes(layout.model_dump_json().encode("utf-8"))

    def execute(self, inputs, params, context, control):  # type: ignore[no-untyped-def]
        from cinoc.pipeline.types import StepOutput

        return StepOutput(
            artifacts={
                ArtifactType.LAYOUT: Artifact(
                    id="sub",
                    document_id="d",
                    type=ArtifactType.LAYOUT,
                    uri=str(self._chemin),
                    content_hash="0" * 64,
                )
            }
        )


def _sous_layout(*textes: str) -> CanonicalLayout:
    from cinoc.domain.layout import Geometry

    return CanonicalLayout(
        pages=(
            LayoutPage(
                width=100,
                height=100,
                regions=(
                    Region(
                        id="bloc",
                        lines=tuple(
                            Line(
                                id=f"line_{i}",
                                text=t,
                                geometry=Geometry(
                                    bbox=BBox(x=5, y=10 * i, width=50, height=8)
                                ),
                            )
                            for i, t in enumerate(textes)
                        ),
                    ),
                ),
            ),
        )
    )


def _region_remplie(tmp_path: Any, *textes: str) -> Region:
    module = _Multiligne(tmp_path / "sub.json", _sous_layout(*textes))
    page = LayoutPage(width=200, height=200, regions=())
    region = Region(
        id="r1",
        region_type="text",
        geometry=Geometry(bbox=BBox(x=30, y=40, width=100, height=100)),
    )
    image = Artifact(
        id="i", document_id="d", type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"), content_hash="0" * 64,
    )
    remplie, _ = _fill_region(
        region, page, image, module, _contexte(tmp_path), RunControl(), {}, None
    )
    return remplie


def test_a_recognizer_that_returns_a_layout_yields_several_lines(
    tmp_path: Any,
) -> None:
    """**Le défaut que ce test ferme.**

    Le fan-out ne lisait que du texte plat, donc fabriquait *toujours* une ligne
    par région — non par choix, mais parce que le type ne permettait rien
    d'autre. Un ALTO de trois blocs sortait avec trois lignes pour une page qui
    en compte vingt : structurellement faux, illisible par un outil de
    relecture, et **invisible à toute métrique de texte**, puisque le contenu,
    lui, était juste.
    """
    remplie = _region_remplie(tmp_path, "première", "deuxième", "troisième")
    assert [ligne.text for ligne in remplie.lines] == [
        "première", "deuxième", "troisième"
    ]


def test_grafted_lines_are_moved_back_into_page_coordinates(tmp_path: Any) -> None:
    """Les coordonnées du sous-layout sont relatives à la **découpe**.

    Sans le décalage, les lignes de tous les blocs se superposeraient en haut à
    gauche de la page — un ALTO qui *semble* correct et place tout au même
    endroit.
    """
    remplie = _region_remplie(tmp_path, "a", "b")
    boites = [ligne.geometry.bbox for ligne in remplie.lines if ligne.geometry]
    assert [(b.x, b.y) for b in boites if b] == [(35, 40), (35, 50)], (
        "x doit valoir 5+30 et y 0+40 puis 10+40 — l'origine du bloc."
    )


def test_grafted_line_ids_are_namespaced_by_their_region(tmp_path: Any) -> None:
    """Le moteur numérote ses lignes à partir de zéro **dans chaque bloc**.

    Sans préfixe, deux lignes de blocs différents porteraient la même identité —
    et l'identité de ligne est précisément ce que la chaîne structurée existe
    pour préserver.
    """
    remplie = _region_remplie(tmp_path, "a", "b")
    assert [ligne.id for ligne in remplie.lines] == ["r1.line_0", "r1.line_1"]


def test_an_empty_sub_layout_leaves_the_region_without_lines(tmp_path: Any) -> None:
    """Un bloc illisible est un **fait**, pas une erreur. Inventer une ligne
    vide ferait croire à une lecture qui n'a pas eu lieu."""
    assert _region_remplie(tmp_path).lines == ()


def test_a_text_only_recognizer_still_yields_one_line(tmp_path: Any) -> None:
    """Le pendant : rien ne change pour un reconnaisseur qui ne sait rendre
    qu'une chaîne. Il n'a qu'un texte à donner, la région n'a qu'une ligne."""
    from cinoc.pipeline.types import StepOutput

    chemin = tmp_path / "t.txt"
    chemin.write_text("une seule", encoding="utf-8")

    class _Plat:
        name, version = "plat", "1.0"
        input_types = frozenset({ArtifactType.IMAGE})
        output_types = frozenset({ArtifactType.RAW_TEXT})

        def execute(self, inputs, params, context, control):  # type: ignore[no-untyped-def]
            return StepOutput(
                artifacts={
                    ArtifactType.RAW_TEXT: Artifact(
                        id="t", document_id="d", type=ArtifactType.RAW_TEXT,
                        uri=str(chemin), content_hash="0" * 64,
                    )
                }
            )

    page = LayoutPage(width=100, height=100, regions=())
    region = Region(
        id="r1", geometry=Geometry(bbox=BBox(x=0, y=0, width=10, height=10))
    )
    image = Artifact(
        id="i", document_id="d", type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"), content_hash="0" * 64,
    )
    remplie, _ = _fill_region(
        region, page, image, _Plat(), _contexte(tmp_path), RunControl(), {}, None
    )
    assert [ligne.id for ligne in remplie.lines] == ["r1.l1"]
    assert remplie.lines[0].text == "une seule"


def test_le_fanout_descend_dans_les_blocs_composes(tmp_path: Any) -> None:
    """Un bloc composé voit ses **enfants** océrisés, pas lui-même.

    Sans cette descente, le fan-out accrochait les lignes au parent tandis que la
    projection lit ``leaf_regions()`` — les enfants, restés vides. Le texte était
    océrisé puis jeté en silence. Le corpus d'essai, dépourvu de bloc composé, ne
    pouvait pas le révéler ; la presse réelle en est pleine.
    """
    espion = _Espion()
    page = LayoutPage(width=100, height=100, regions=())
    compose = Region(
        id="c1",
        region_type="composed",
        geometry=Geometry(bbox=BBox(x=0, y=0, width=40, height=40)),
        regions=(
            Region(
                id="c1_r1",
                region_type="text",
                geometry=Geometry(bbox=BBox(x=2, y=2, width=36, height=16)),
            ),
            Region(
                id="c1_r2",
                region_type="text",
                geometry=Geometry(bbox=BBox(x=2, y=20, width=36, height=16)),
            ),
        ),
    )
    image = Artifact(
        id="i",
        document_id="d",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"),
        content_hash="0" * 64,
    )
    rempli, _ = _fill_region(
        compose, page, image, espion, _contexte(tmp_path), RunControl(), {}, None
    )
    # Le reconnaisseur a vu les deux enfants, jamais le parent.
    assert espion.vus == ["text", "text"]
    feuilles = [r for r in rempli.regions]
    assert [r.id for r in feuilles] == ["c1_r1", "c1_r2"]
    assert not rempli.lines, "le parent ne doit pas porter de lignes"


def test_le_fanout_descend_dans_les_composes_imbriques(tmp_path: Any) -> None:
    """La descente vaut à **toute profondeur**, pas seulement au premier niveau.

    Le parseur ALTO annonce un ``ComposedBlock`` récursif : un composé peut en
    contenir un autre. Une descente qui ne traiterait qu'un niveau laisserait les
    feuilles profondes vides — le même texte perdu, une strate plus bas.
    """
    espion = _Espion()
    page = LayoutPage(width=100, height=100, regions=())
    arbre = Region(
        id="n1",
        region_type="composed",
        geometry=Geometry(bbox=BBox(x=0, y=0, width=100, height=100)),
        regions=(
            Region(
                id="n2",
                region_type="composed",
                geometry=Geometry(bbox=BBox(x=0, y=0, width=100, height=50)),
                regions=(
                    Region(
                        id="f1",
                        region_type="text",
                        geometry=Geometry(bbox=BBox(x=0, y=0, width=100, height=25)),
                    ),
                    Region(
                        id="f2",
                        region_type="text",
                        geometry=Geometry(bbox=BBox(x=0, y=25, width=100, height=25)),
                    ),
                ),
            ),
            Region(
                id="f3",
                region_type="text",
                geometry=Geometry(bbox=BBox(x=0, y=50, width=100, height=50)),
            ),
        ),
    )
    image = Artifact(
        id="i",
        document_id="d",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"),
        content_hash="0" * 64,
    )
    rempli, _ = _fill_region(
        arbre, page, image, espion, _contexte(tmp_path), RunControl(), {}, None
    )
    # Les trois feuilles ont été océrisées, à deux profondeurs différentes.
    assert espion.vus == ["text", "text", "text"]
    # Et aucun niveau intermédiaire ne retient de texte au passage.
    assert not rempli.lines
    assert not rempli.regions[0].lines


def test_fanout_line_ids_survive_both_exports(tmp_path: Any) -> None:
    """Les identifiants que forge le fan-out sont des ``xsd:ID`` (``NCName``).

    Ils joignaient région et ligne par ``:``, interdit dans un ``NCName`` : tout
    ALTO assemblé depuis un fan-out échouait au XSD, et l'écrivain PAGE aurait
    dû les renommer — perdant l'identité de ligne que la chaîne structurée
    existe pour préserver (D-273). Les deux chemins : greffe d'un sous-layout,
    et ligne unique d'un reconnaisseur à texte plat.
    """
    from cinoc.formats.alto.layout_map import layout_to_alto
    from cinoc.formats.alto.writer import write_alto
    from cinoc.formats.pagexml.layout_map import layout_to_page, page_to_layout
    from cinoc.formats.pagexml.parser import parse_pagexml
    from cinoc.formats.pagexml.writer import write_pagexml
    from tests.formats._xsd import alto_errors, page_errors

    greffee = _region_remplie(tmp_path, "a", "b")
    plate = greffee.model_copy(
        update={"id": "r2", "lines": (Line(id=_fanout_line_id(tmp_path), text="c"),)}
    )
    layout = CanonicalLayout(
        pages=(
            LayoutPage(
                width=200, height=200, regions=(greffee, plate),
                reading_order=("r1", "r2"),
            ),
        )
    )
    ids = [ligne.id for region in layout.pages[0].regions for ligne in region.lines]
    assert alto_errors(write_alto(layout_to_alto(layout))) == []
    page_xml = write_pagexml(layout_to_page(layout))
    assert page_errors(page_xml) == []
    relu = page_to_layout(parse_pagexml(page_xml))
    assert [ligne.id for r in relu.pages[0].regions for ligne in r.lines] == ids


def _fanout_line_id(tmp_path: Any) -> str | None:
    """L'identifiant que donne le fan-out à la ligne d'un reconnaisseur plat."""
    from cinoc.pipeline.types import StepOutput

    chemin = tmp_path / "plat.txt"
    chemin.write_text("c", encoding="utf-8")

    class _Plat:
        name, version = "plat", "1.0"
        input_types = frozenset({ArtifactType.IMAGE})
        output_types = frozenset({ArtifactType.RAW_TEXT})

        def execute(self, inputs, params, context, control):  # type: ignore[no-untyped-def]
            return StepOutput(
                artifacts={
                    ArtifactType.RAW_TEXT: Artifact(
                        id="t", document_id="d", type=ArtifactType.RAW_TEXT,
                        uri=str(chemin), content_hash="0" * 64,
                    )
                }
            )

    region = Region(
        id="r2", geometry=Geometry(bbox=BBox(x=0, y=0, width=10, height=10))
    )
    image = Artifact(
        id="i", document_id="d", type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"), content_hash="0" * 64,
    )
    remplie, _ = _fill_region(
        region, LayoutPage(width=100, height=100), image, _Plat(),
        _contexte(tmp_path), RunControl(), {}, None,
    )
    return remplie.lines[0].id


class _Coupe:
    """Reconnaisseur dont chaque réponse est coupée (un VLM au plafond)."""

    name = "coupe"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def __init__(self, tmp_path: Any) -> None:
        self._dir = tmp_path

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, Any],
        context: RunContext,
        control: RunControl,
    ) -> Any:
        from cinoc.pipeline.types import StepOutput

        region = inputs[ArtifactType.IMAGE].region_id
        sortie = self._dir / f"{region}.txt"
        sortie.write_text("le début d'un", encoding="utf-8")
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"t:{region}",
                    document_id="d",
                    type=ArtifactType.RAW_TEXT,
                    uri=str(sortie),
                )
            },
            truncation="plafond atteint",
        )


def test_a_cut_region_is_reported_not_swallowed(tmp_path: Any) -> None:
    """Le fan-out somme déjà les jetons des N appels ; il doit aussi rendre la
    coupure de chacun, sinon un VLM par bloc tronqué passerait pour complet."""
    regions = tuple(
        Region(
            id=f"r{i}",
            region_type="text",
            geometry=Geometry(bbox=BBox(x=0, y=0, width=10, height=10)),
        )
        for i in (1, 2)
    )
    layout = CanonicalLayout(
        pages=(LayoutPage(width=100, height=100, regions=regions),)
    )
    image = Artifact(
        id="i",
        document_id="d",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"),
        content_hash="0" * 64,
    )
    coupures: list[str] = []
    rempli, _ = run_region_fanout(
        layout=layout,
        page_image=image,
        recognizer=_Coupe(tmp_path),
        context=_contexte(tmp_path),
        control=RunControl(),
        truncations=coupures,
    )
    assert coupures == [
        "région 'r1' : plafond atteint",
        "région 'r2' : plafond atteint",
    ]
    # La sortie coupée est gardée : c'est une lecture réelle, signalée.
    assert all(r.lines for r in rempli.pages[0].regions)


class _Distant:
    """Reconnaisseur distant : texte + réponse native, **au même chemin** pour
    chaque région (comme un adaptateur réel, qui nomme ses fichiers par page)."""

    name = "distant"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON})

    def __init__(self, tmp_path: Any) -> None:
        self._dir = tmp_path

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, Any],
        context: RunContext,
        control: RunControl,
    ) -> Any:
        from cinoc.domain.artifacts import native_json_bytes
        from cinoc.pipeline.types import StepOutput

        region = inputs[ArtifactType.IMAGE].region_id
        if region == "r2":
            raise AdapterStepError("région illisible")
        texte = self._dir / "page.distant.txt"
        texte.write_text(f"texte de {region}", encoding="utf-8")
        native = self._dir / "page.distant.native.json"
        native.write_bytes(native_json_bytes({"id": f"rep-{region}", "n": 1}))
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"t:{region}", document_id="d",
                    type=ArtifactType.RAW_TEXT, uri=str(texte),
                ),
                ArtifactType.NATIVE_JSON: Artifact(
                    id=f"n:{region}", document_id="d",
                    type=ArtifactType.NATIVE_JSON, uri=str(native),
                ),
            }
        )


def test_the_fanout_keeps_the_native_response_of_every_region(tmp_path: Any) -> None:
    """Un appel par région : le sidecar de l'étape les garde **tous**, dans
    l'ordre de lecture, chacun rattaché à sa région — la sortie du reconnaisseur
    n'était lue que pour son texte, et la réponse de chaque bloc se perdait."""
    import json
    from pathlib import Path

    from cinoc.domain.artifacts import native_json_bytes
    from cinoc.pipeline.fanout import execute_region_fanout

    regions = tuple(
        Region(
            id=f"r{i}",
            geometry=Geometry(bbox=BBox(x=0, y=0, width=10, height=10)),
        )
        for i in (1, 2, 3)
    )
    layout = CanonicalLayout(
        pages=(LayoutPage(width=100, height=100, regions=regions),)
    )
    source = tmp_path / "seg.layout.json"
    source.write_text(layout.model_dump_json(), encoding="utf-8")
    sortie = execute_region_fanout(
        layout_artifact=Artifact(
            id="l", document_id="d", type=ArtifactType.LAYOUT, uri=str(source)
        ),
        page_image=Artifact(
            id="i", document_id="d", type=ArtifactType.IMAGE,
            uri=str(tmp_path / "p.png"),
        ),
        recognizer=_Distant(tmp_path),
        context=_contexte(tmp_path),
        control=RunControl(),
    )
    native = sortie.artifacts[ArtifactType.NATIVE_JSON]
    data = Path(native.uri or "").read_bytes()
    # r2 a échoué : rien à garder pour elle, et rien d'inventé.
    attendu = {
        "regions": [
            {"region_id": "r1", "response": {"id": "rep-r1", "n": 1}},
            {"region_id": "r3", "response": {"id": "rep-r3", "n": 1}},
        ]
    }
    assert json.loads(data) == attendu
    assert data == native_json_bytes(attendu)


def test_a_fanout_without_native_responses_publishes_none(tmp_path: Any) -> None:
    from cinoc.pipeline.fanout import execute_region_fanout

    region = Region(
        id="r1", geometry=Geometry(bbox=BBox(x=0, y=0, width=10, height=10))
    )
    layout = CanonicalLayout(
        pages=(LayoutPage(width=100, height=100, regions=(region,)),)
    )
    source = tmp_path / "seg.layout.json"
    source.write_text(layout.model_dump_json(), encoding="utf-8")
    sortie = execute_region_fanout(
        layout_artifact=Artifact(
            id="l", document_id="d", type=ArtifactType.LAYOUT, uri=str(source)
        ),
        page_image=Artifact(
            id="i", document_id="d", type=ArtifactType.IMAGE,
            uri=str(tmp_path / "p.png"),
        ),
        recognizer=_Coupe(tmp_path),
        context=_contexte(tmp_path),
        control=RunControl(),
    )
    assert set(sortie.artifacts) == {ArtifactType.LAYOUT}
