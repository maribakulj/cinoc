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
from cinoc.domain.layout import BBox, Geometry, LayoutPage, Region
from cinoc.pipeline.fanout import REGION_TYPE_PARAM, _fill_region
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
