"""P5f 4 — Mistral OCR sans perte : texte sans syntaxe markdown, blocs en ``LAYOUT``.

Cassette ``tests/fixtures/cassettes/ocr/mistral_ocr_4.json`` (**construite**
d'après le SDK mistralai 3.9.0 et la documentation « Basic OCR », à confirmer
sur une réponse réelle) : une même page rendue sans blocs (``markdown``,
``mistral-ocr-2512``) et avec (``blocs``, ``mistral-ocr-4-1``,
``confidence_scores_granularity='block'``), et sa vérité terrain.

Rouge prouvé sur l'ancien code (le markdown noté tel quel) : 8 échecs ; CER de la
page de la cassette 0,2836 (vue ``texte``) et 0,3060 (``texte (lignes)``) → 0 ;
``folio_b`` (cassette de S8) 0,2028 → 0,0210, ses trois ``ſ`` lus ``f``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.ocr._mistral_layout import layout_from_response
from cinoc.adapters.ocr.mistral_ocr import MistralOCRAdapter, _text_from_response
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.layout import BBox, CanonicalLayout
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.layout import (
    line_identity_cer,
    region_cer,
    region_detection,
)
from cinoc.evaluation.metrics.text import _edit_distance
from cinoc.formats.text import get_builtin_profile
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_CASSETTES = Path(__file__).resolve().parents[1] / "fixtures" / "cassettes" / "ocr"
_CASSETTE = json.loads((_CASSETTES / "mistral_ocr_4.json").read_text("utf-8"))
_S8 = json.loads((_CASSETTES / "mistral_ocr.json").read_text("utf-8"))
_GT: str = _CASSETTE["ground_truth"]


def _response(name: str) -> dict[str, Any]:
    return json.loads(json.dumps(_CASSETTE["responses"][name]))


def _cer(reference: str, hypothesis: str, profile: str = "flat_text") -> float:
    normalize = get_builtin_profile(profile).normalize
    ref = normalize(reference)
    return _edit_distance(ref, normalize(hypothesis)) / len(ref)


# --- Le texte noté ----------------------------------------------------------


@pytest.mark.parametrize("scenario", ["markdown", "blocs"])
def test_le_texte_note_est_la_page_sans_sa_syntaxe(scenario: str) -> None:
    texte = _text_from_response(_response(scenario))
    assert texte == _GT
    for syntaxe in ("#", "**", "|", "![", "](", "---"):
        assert syntaxe not in texte


@pytest.mark.parametrize("profile", ["flat_text", "keep_line_breaks"])
def test_cer_de_la_cassette_nul_sous_les_deux_vues(profile: str) -> None:
    assert _cer(_GT, _text_from_response(_response("markdown")), profile) == 0.0


def test_folio_b_n_est_plus_penalise_pour_sa_figure() -> None:
    """Cassette de S8 : la seule syntaxe est l'appel de figure ; il reste les
    trois ``ſ`` lus ``f``, les vraies erreurs du moteur."""
    gt = (
        "Le Petit Journal, 12 mars 1894. — On annonce de Boulogne-sur-Mer "
        "qu'une partie de la falaise s'est effondrée hier soir, emportant "
        "deux maisons."
    )
    texte = _text_from_response(_S8["responses"]["folio_b"])
    assert "img" not in texte
    assert _cer(gt, texte) == pytest.approx(3 / len(gt))


def test_pages_jointes_par_un_saut_de_ligne() -> None:
    native = {"pages": [{"markdown": "# Un"}, {"markdown": "**Deux**"}, "x"]}
    assert _text_from_response(native) == "Un\nDeux"


# --- La mise en page --------------------------------------------------------


def test_sans_bloc_pas_de_mise_en_page() -> None:
    """Images situées, texte sans boîte : rien qui fasse un ``LAYOUT`` honnête."""
    assert layout_from_response(_response("markdown")) is None
    assert layout_from_response({"pages": [{"markdown": "x", "blocks": []}]}) is None
    assert layout_from_response({"pages": "x"}) is None
    assert layout_from_response([]) is None


def test_un_bloc_une_region_dans_l_ordre_de_lecture() -> None:
    layout = layout_from_response(_response("blocs"))
    assert layout is not None
    (page,) = layout.pages
    assert (page.width, page.height) == (1700, 2200)
    assert [r.region_type for r in page.regions] == [
        "title", "text", "image", "text", "table", "list", "footer",
    ]
    assert page.reading_order == tuple(f"p0_b{n}" for n in range(1, 8))
    assert page.regions[0].geometry is not None
    assert page.regions[0].geometry.bbox == BBox(x=240, y=120, width=1220, height=100)
    assert layout.coordinate_unit == "pixel"


def test_lignes_de_contenu_sans_geometrie_ni_identifiant() -> None:
    layout = layout_from_response(_response("blocs"))
    assert layout is not None
    regions = layout.pages[0].regions
    assert [line.text for line in regions[4].lines] == [
        "Ville Pertes", "Boulogne 2 maisons", "Wimereux 1 grange",
    ]
    assert regions[2].lines == ()  # l'image n'a pas de texte
    for region in regions:
        for line in region.lines:
            assert (line.geometry, line.id, line.confidence) == (None, None, None)
    texte = "\n".join(line.text for r in regions for line in r.lines)
    assert texte == _GT


def test_confiance_de_region_est_celle_du_type_de_bloc() -> None:
    layout = layout_from_response(_response("blocs"))
    assert layout is not None
    assert [r.confidence for r in layout.pages[0].regions] == [
        0.9999, 0.9641, 0.9987, 0.9935, 0.9876, 0.942, 0.8812,
    ]


def test_aucune_geometrie_inventee() -> None:
    native = _response("blocs")
    blocs = native["pages"][0]["blocks"]
    del blocs[0]["top_left_x"]  # coin manquant
    blocs[1]["bottom_right_y"] = 100  # boîte inversée
    blocs[2]["top_left_x"] = 300.6  # sous le pixel : arrondi
    blocs[3]["confidence_scores"] = None
    blocs[4]["confidence_scores"]["block_type_confidence_score"] = 1.5
    native["pages"][0]["dimensions"] = None
    layout = layout_from_response(native)
    assert layout is not None
    (page,) = layout.pages
    assert (page.width, page.height) == (None, None)
    assert page.regions[0].geometry is None
    assert page.regions[1].geometry is None
    assert page.regions[0].lines[0].text == "LE PETIT JOURNAL"  # le texte reste
    assert page.regions[2].geometry is not None
    assert page.regions[2].geometry.bbox == BBox(x=301, y=320, width=1099, height=780)
    assert page.regions[3].confidence is None
    assert page.regions[4].confidence is None
    for region in page.regions:  # jamais de boîte pleine page fabriquée
        if region.geometry is not None and region.geometry.bbox is not None:
            assert region.geometry.bbox.width < 1700


def test_projection_deterministe() -> None:
    premier = layout_from_response(_response("blocs"))
    second = layout_from_response(_response("blocs"))
    assert premier is not None and second is not None
    assert premier.model_dump_json() == second.model_dump_json()


# --- L'adaptateur -----------------------------------------------------------


def _execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str) -> Any:
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(
        "cinoc.adapters.ocr.mistral_ocr._invoke_mistral_ocr",
        lambda **_: _response(scenario),
    )
    return MistralOCRAdapter(model="m", label="ocr").execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="d1:img", document_id="d1", type=ArtifactType.IMAGE, uri=str(image)
            )
        },
        {},
        RunContext(
            document_id="d1", code_version="t", pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )


def test_version_relevee_les_blocs_sont_demandes() -> None:
    """1.2 : le texte sans syntaxe ; 1.3 : la requête demande les blocs — le
    sidecar et le ``LAYOUT`` changent, une archive 1.2 est ré-exécutée."""
    assert MistralOCRAdapter(model="m", label="ocr").version == "1.3"


def test_la_requete_demande_les_blocs_et_le_layout_arrive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De bout en bout sous un SDK factice (seul le transport est faux) : la
    requête demande ``include_blocks`` et des confiances **par bloc**, la
    réponse de la cassette OCR 4 traverse ``sdk_native`` et devient un
    ``LAYOUT`` — S19 était dormant faute de cette demande (D-291)."""
    from tests.adapters._native_fakes import (  # noqa: PLC0415
        SdkResponse,
        install_fake_mistralai,
    )

    appels: list[dict[str, Any]] = []

    class _Mistral:
        def __init__(self, **_: Any) -> None:
            def process(**kwargs: Any) -> SdkResponse:
                appels.append(kwargs)
                return SdkResponse.model_validate(_response("blocs"))

            self.ocr = type("ocr", (), {"process": staticmethod(process)})()

    install_fake_mistralai(monkeypatch, _Mistral)
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    out = MistralOCRAdapter(model="m", label="ocr").execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="d1:img", document_id="d1", type=ArtifactType.IMAGE, uri=str(image)
            )
        },
        {},
        RunContext(
            document_id="d1", code_version="t", pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    (appel,) = appels
    assert appel["include_blocks"] is True
    assert appel["confidence_scores_granularity"] == "block"
    layout = CanonicalLayout.model_validate_json(
        Path(out.artifacts[ArtifactType.LAYOUT].uri).read_bytes()
    )
    assert layout == layout_from_response(_response("blocs"))
    assert len(layout.pages[0].regions) == 7


def test_adaptateur_publie_le_layout_depuis_le_corps_garde(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _execute(tmp_path, monkeypatch, "blocs")
    assert out.served_models == ("mistral-ocr-4-1",)
    texte = Path(out.artifacts[ArtifactType.RAW_TEXT].uri).read_text("utf-8")
    assert texte == _GT
    layout = CanonicalLayout.model_validate_json(
        Path(out.artifacts[ArtifactType.LAYOUT].uri).read_bytes()
    )
    # Relu depuis le sidecar, par la même fonction : la même mise en page.
    native = json.loads(Path(out.artifacts[ArtifactType.NATIVE_JSON].uri).read_bytes())
    assert layout_from_response(native) == layout


def test_adaptateur_sans_bloc_ne_publie_pas_de_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _execute(tmp_path, monkeypatch, "markdown")
    assert set(out.artifacts) == {ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON}
    assert out.served_models == ("mistral-ocr-2512",)


# --- Ce que les métriques de structure en lisent ---------------------------


def test_metriques_de_structure_sur_la_projection() -> None:
    """Contre une VT aux mêmes boîtes : détection et CER par région parfaits ;
    l'appariement de lignes par identifiant ne s'applique pas (aucun id)."""
    hypothese = layout_from_response(_response("blocs"))
    assert hypothese is not None
    page = hypothese.pages[0]
    reference = CanonicalLayout(
        pages=(
            page.model_copy(
                update={
                    "regions": tuple(
                        r.model_copy(
                            update={
                                "id": f"TextBlock_{n}",
                                "confidence": None,
                                "lines": tuple(
                                    line.model_copy(update={"id": f"l{n}_{k}"})
                                    for k, line in enumerate(r.lines)
                                ),
                            }
                        )
                        for n, r in enumerate(page.regions)
                    ),
                    "reading_order": (),
                }
            ),
        )
    )
    ctx = DocContext(document_id="d", reference=reference, hypothesis=hypothese)
    detection = region_detection.fn(ctx)
    cer = region_cer.fn(ctx)
    assert detection is not None and detection.value == 1.0
    assert cer is not None and cer.value == 0.0
    assert line_identity_cer.fn(ctx) is None


def test_en_fan_out_les_lignes_des_blocs_sont_greffees_a_la_region(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reconnaisseur par région : une réponse à blocs donne ses lignes de
    contenu (sans géométrie inventée) ; sans blocs, une ligne, comme avant."""
    from cinoc.domain.layout import Geometry, Region
    from cinoc.pipeline.fanout import _lignes_reconnues

    region = Region(
        id="r1", geometry=Geometry(bbox=BBox(x=100, y=50, width=1700, height=2200))
    )
    avec = _lignes_reconnues(_execute(tmp_path, monkeypatch, "blocs").artifacts, region)
    assert "\n".join(line.text for line in avec) == _GT
    assert all(line.geometry is None for line in avec)
    (tmp_path / "b").mkdir()
    sans = _execute(tmp_path / "b", monkeypatch, "markdown")
    (seule,) = _lignes_reconnues(sans.artifacts, region)
    assert seule.text == _GT
