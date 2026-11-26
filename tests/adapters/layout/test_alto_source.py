"""``AltoLayoutSource`` : faire entrer un ALTO existant sans l'aplatir.

Le banc savait produire une mise en page et savait en consommer une ; il ne
savait pas **lire celle qui accompagne déjà le corpus**. Un ALTO patrimonial ne
pouvait donc entrer qu'en texte plat — en y perdant l'identité de ligne, la
géométrie et la césure, c'est-à-dire tout ce qui distingue une mise en page
d'une chaîne de caractères.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout.alto_source import AltoLayoutSource
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'


def _alto(lines: str) -> bytes:
    return (
        f'<alto {_NS}><Layout><Page ID="P1" WIDTH="600" HEIGHT="400">'
        f'<PrintSpace><TextBlock ID="B1">{lines}</TextBlock>'
        f"</PrintSpace></Page></Layout></alto>"
    ).encode()


_ONE_LINE = _alto(
    '<TextLine ID="L1" HPOS="10" VPOS="20" WIDTH="300" HEIGHT="40">'
    '<String CONTENT="Bonjour" WC="0.9"/><SP/>'
    '<String CONTENT="tra" SUBS_TYPE="HypPart1" SUBS_CONTENT="travailleurs"/>'
    "<HYP/></TextLine>"
)


def _run(tmp_path: Path, *, alto: bytes = _ONE_LINE, stem: str = "page") -> Artifact:
    (tmp_path / f"{stem}.png").write_bytes(b"pas une vraie image")
    (tmp_path / f"{stem}.xml").write_bytes(alto)
    out = AltoLayoutSource().execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="img",
                document_id="doc1",
                type=ArtifactType.IMAGE,
                uri=str(tmp_path / f"{stem}.png"),
                content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="doc1",
            code_version="1.0",
            pipeline_name="p",
            workspace_uri=str(tmp_path / "ws"),
        ),
        RunControl(),
    )
    return out.artifacts[ArtifactType.LAYOUT]


def test_reads_the_alto_next_to_the_image(tmp_path: Path) -> None:
    art = _run(tmp_path)
    layout = CanonicalLayout.model_validate_json(Path(art.uri).read_bytes())
    line = layout.pages[0].regions[0].lines[0]

    assert line.id == "L1"  # l'identité, pas un rang
    assert line.text == "Bonjour tra-"  # SP et HYP compris
    assert line.geometry is not None and line.geometry.bbox is not None
    assert line.words[-1].subs_content == "travailleurs"


def test_line_confidence_survives(tmp_path: Path) -> None:
    """La confiance du moteur d'origine est une donnée, pas du décor : elle
    dit quelles lignes méritent qu'on les regarde."""
    art = _run(tmp_path)
    layout = CanonicalLayout.model_validate_json(Path(art.uri).read_bytes())
    assert layout.pages[0].regions[0].lines[0].words[0].confidence == 0.9


def test_missing_alto_names_what_it_looked_for(tmp_path: Path) -> None:
    (tmp_path / "seule.png").write_bytes(b"x")
    with pytest.raises(AdapterStepError, match="aucun ALTO"):
        AltoLayoutSource().execute(
            {
                ArtifactType.IMAGE: Artifact(
                    id="img",
                    document_id="d",
                    type=ArtifactType.IMAGE,
                    uri=str(tmp_path / "seule.png"),
                    content_hash="0" * 64,
                )
            },
            {},
            RunContext(document_id="d", code_version="1.0", pipeline_name="p"),
            RunControl(),
        )


def test_a_line_without_id_is_refused(tmp_path: Path) -> None:
    """Sans identifiant, une ligne n'a pas d'identité d'un artefact à l'autre.

    Refusé **ici** plutôt qu'en aval : l'étape suivante échouerait sur une
    cause qui n'est pas la sienne.
    """
    anonyme = _alto('<TextLine><String CONTENT="sans identifiant"/></TextLine>')
    with pytest.raises(AdapterStepError, match="sans attribut ID"):
        _run(tmp_path, alto=anonyme)


def test_a_line_without_id_inside_a_composed_block_is_refused(tmp_path: Path) -> None:
    """Le contrôle descendait d'un niveau seulement : la presse range ses
    articles en ``ComposedBlock``, et leurs lignes y échappaient (D-264)."""
    imbrique = (
        f'<alto {_NS}><Layout><Page ID="P1" WIDTH="600" HEIGHT="400"><PrintSpace>'
        '<ComposedBlock ID="C1"><TextBlock ID="B1">'
        '<TextLine><String CONTENT="sans identifiant"/></TextLine>'
        "</TextBlock></ComposedBlock></PrintSpace></Page></Layout></alto>"
    ).encode()
    with pytest.raises(AdapterStepError, match="1 ligne"):
        _run(tmp_path, alto=imbrique)


def test_registered_under_its_own_kind() -> None:
    """Le module est résolvable par le registre, comme n'importe quelle brique."""
    from cinoc.app.modules.registry import ModuleRegistry, register_default_modules

    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build("alto_source", {})
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert module.output_types == frozenset({ArtifactType.LAYOUT})


# --- OCR dégradé en entrée ---------------------------------------------------


_SIDECAR = {
    "ocr": {
        "page.xml": {"L1": "Bonjour tra-", "L2": "lecture d'OCR"},
    }
}


def _alto_deux_lignes() -> bytes:
    return _alto(
        '<TextLine ID="L1" HPOS="10" VPOS="20" WIDTH="300" HEIGHT="40">'
        '<String CONTENT="Bonjour" WC="0.9"/><SP/>'
        '<String CONTENT="tra" SUBS_TYPE="HypPart1" SUBS_CONTENT="travailleurs"/>'
        "<HYP/></TextLine>"
        '<TextLine ID="L2" HPOS="10" VPOS="70" WIDTH="300" HEIGHT="40">'
        '<String CONTENT="vérité"/><SP/><String CONTENT="terrain"/></TextLine>'
    )


def _run_avec_sidecar(tmp_path: Path, sidecar: dict) -> CanonicalLayout:
    import json

    (tmp_path / "page.png").write_bytes(b"pas une vraie image")
    (tmp_path / "page.xml").write_bytes(_alto_deux_lignes())
    chemin = tmp_path / "ocr.json"
    chemin.write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
    out = AltoLayoutSource(ocr_sidecar=str(chemin)).execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="img",
                document_id="doc1",
                type=ArtifactType.IMAGE,
                uri=str(tmp_path / "page.png"),
                content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="doc1",
            code_version="1.0",
            pipeline_name="p",
            workspace_uri=str(tmp_path / "ws"),
        ),
        RunControl(),
    )
    return CanonicalLayout.model_validate_json(
        Path(out.artifacts[ArtifactType.LAYOUT].uri).read_bytes()
    )


def test_the_ocr_reading_replaces_the_text_and_nothing_else(tmp_path: Path) -> None:
    """Sans ça, un corpus à vérité terrain fait entrer sa **propre référence**
    dans le banc : le correcteur n'a rien à corriger et le CER vaut zéro par
    construction. Un zéro tautologique ressemble à un excellent résultat, ce qui
    en fait le plus trompeur de tous.
    """
    lignes = [
        ligne
        for page in _run_avec_sidecar(tmp_path, _SIDECAR).pages
        for region in page.regions
        for ligne in region.lines
    ]
    assert [ligne.text for ligne in lignes] == ["Bonjour tra-", "lecture d'OCR"]
    # L'identité et la géométrie viennent toujours de l'ALTO.
    assert [ligne.id for ligne in lignes] == ["L1", "L2"]
    assert lignes[0].geometry is not None


def test_an_empty_reading_is_a_reading(tmp_path: Path) -> None:
    """Le moteur n'a rien reconnu : c'est un résultat d'OCR, pas une absence.

    Garder le texte d'ALTO créditerait le moteur d'une ligne qu'il n'a **pas
    lue** — exactement la contamination trouvée le 2026-08-21 sur la campagne
    du 14 août, où six lignes vides avaient repris la vérité terrain.
    """
    layout = _run_avec_sidecar(
        tmp_path, {"ocr": {"page.xml": {"L1": "", "L2": "lu"}}}
    )
    textes = [
        ligne.text
        for page in layout.pages
        for region in page.regions
        for ligne in region.lines
    ]
    assert textes == ["", "lu"]


def test_a_line_absent_from_the_sidecar_keeps_its_alto_text(tmp_path: Path) -> None:
    """Absent ≠ vide : une ligne que le sidecar ne mentionne pas n'a pas été
    soumise au moteur, elle garde donc son texte."""
    layout = _run_avec_sidecar(tmp_path, {"ocr": {"page.xml": {"L1": "lu"}}})
    textes = [
        ligne.text
        for page in layout.pages
        for region in page.regions
        for ligne in region.lines
    ]
    assert textes == ["lu", "vérité terrain"]


def test_a_sidecar_matching_nothing_is_refused(tmp_path: Path) -> None:
    """Un sidecar qui ne touche aucune ligne est presque toujours un mauvais
    appariement de clés, pas un OCR parfait. Le taire publierait un CER nul en
    croyant mesurer une correction."""
    with pytest.raises(AdapterStepError, match="ne couvre aucune"):
        _run_avec_sidecar(tmp_path, {"ocr": {"page.xml": {"INCONNUE": "x"}}})


def test_an_unknown_file_is_named(tmp_path: Path) -> None:
    with pytest.raises(AdapterStepError, match="ne connaît pas"):
        _run_avec_sidecar(tmp_path, {"ocr": {"autre.xml": {"L1": "x"}}})
