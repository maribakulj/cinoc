"""``SaknussemmCorrector`` : corriger **dans** la mise en page.

La post-correction du banc était texte plat → texte plat : on aplatissait avant
de corriger, donc l'identité de ligne mourait avant que le modèle voie quoi que
ce soit. Ici elle survit, et l'appariement avant/après est **connu** au lieu
d'être deviné par un alignement de Levenshtein sur des listes de lignes.

Les tests utilisent le producteur ``rules`` : déterministe, hors ligne, aucune
dépendance réseau. Ce qui est vérifié est le **chemin**, pas la qualité d'un
modèle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout.saknussemm_correct import SaknussemmCorrector, _flatten
from cinoc.adapters.layout.to_text import LayoutToTextExtractor
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

saknussemm = pytest.importorskip("saknussemm")


def _layout(*texts: str) -> CanonicalLayout:
    return CanonicalLayout(
        pages=(
            LayoutPage(
                width=600,
                height=400,
                regions=(
                    Region(
                        id="R1",
                        geometry=Geometry(bbox=BBox(x=0, y=0, width=600, height=400)),
                        lines=tuple(
                            Line(
                                id=f"L{i + 1}",
                                text=text,
                                geometry=Geometry(
                                    bbox=BBox(x=10, y=20 * i, width=500, height=18)
                                ),
                            )
                            for i, text in enumerate(texts)
                        ),
                    ),
                ),
            ),
        )
    )


def _run(tmp_path: Path, layout: CanonicalLayout) -> dict[ArtifactType, Artifact]:
    src = tmp_path / "in.layout.json"
    src.write_bytes(layout.model_dump_json().encode("utf-8"))
    out = SaknussemmCorrector(label="regles").execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a",
                document_id="doc1",
                type=ArtifactType.LAYOUT,
                uri=str(src),
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
    return out.artifacts


def _lines(artifact: Artifact) -> list[Line]:
    layout = CanonicalLayout.model_validate_json(Path(artifact.uri).read_bytes())
    return [ln for p in layout.pages for r in p.regions for ln in r.lines]


def test_a_correction_actually_happens(tmp_path: Path) -> None:
    """**Contrôle de sensibilité, et il vient en premier.**

    Sans lui, « 0 ligne modifiée » ne distingue pas « rien à corriger » de
    « le module ne corrige rien ». Le ``ſ`` long est l'une des trois
    substitutions des règles françaises par défaut.
    """
    arts = _run(tmp_path, _layout("le ſoleil ſe lève"))
    assert _lines(arts[ArtifactType.LAYOUT])[0].text == "le soleil se lève"


def test_line_identity_survives_the_corrector(tmp_path: Path) -> None:
    """C'est la raison d'être de l'étape : l'appariement avant/après est connu."""
    arts = _run(tmp_path, _layout("le ſoleil", "brille", "ſur la mer"))
    assert [ln.id for ln in _lines(arts[ArtifactType.LAYOUT])] == ["L1", "L2", "L3"]


def test_geometry_is_kept_but_words_are_dropped_when_the_text_changed(
    tmp_path: Path,
) -> None:
    """Une ligne modifiée garde sa boîte et perd ses mots.

    La géométrie de la ligne décrit toujours la même bande d'image ; celle des
    mots décrivait des caractères qui ne sont plus là. Les garder ferait dire à
    l'artefact une position que rien ne soutient.
    """
    arts = _run(tmp_path, _layout("le ſoleil"))
    line = _lines(arts[ArtifactType.LAYOUT])[0]
    assert line.geometry is not None and line.geometry.bbox is not None
    assert line.words == ()


def test_an_untouched_line_is_returned_verbatim(tmp_path: Path) -> None:
    """Ce que la bibliothèque n'a pas décidé de changer ressort intact."""
    arts = _run(tmp_path, _layout("rien à corriger ici"))
    assert _lines(arts[ArtifactType.LAYOUT])[0].text == "rien à corriger ici"


def test_the_three_outputs_are_produced(tmp_path: Path) -> None:
    """``CORRECTED_TEXT`` fait fonctionner le bilan de correction existant
    **sans le modifier** ; ``DECISIONS`` porte ce qu'un texte corrigé ne peut
    pas dire — ce qui a été refusé, et pourquoi."""
    arts = _run(tmp_path, _layout("le ſoleil"))
    assert set(arts) == {
        ArtifactType.LAYOUT,
        ArtifactType.CORRECTED_TEXT,
        ArtifactType.DECISIONS,
    }
    text = Path(arts[ArtifactType.CORRECTED_TEXT].uri).read_text(encoding="utf-8")
    assert text == "le soleil"


def test_the_decisions_say_what_happened_to_each_line(tmp_path: Path) -> None:
    """Une ligne intacte et une ligne corrigée sont **distinguables** ici.

    Dans le texte corrigé seul, elles ne le sont pas : c'est toute la raison
    d'être de cet artefact.
    """
    import json

    arts = _run(tmp_path, _layout("le ſoleil", "rien à corriger"))
    decisions = json.loads(
        Path(arts[ArtifactType.DECISIONS].uri).read_text(encoding="utf-8")
    )
    par_id = {ligne["line_id"]: ligne for ligne in decisions["lines"]}
    assert par_id["L1"]["source_text"] == "le ſoleil"
    assert par_id["L1"]["final_text"] == "le soleil"
    assert par_id["L2"]["source_text"] == par_id["L2"]["final_text"]
    assert {"status", "reason_code", "proposed_text"} <= set(par_id["L1"])


def test_flattening_matches_to_text_exactly(tmp_path: Path) -> None:
    """Deux conventions d'aplatissement différentes fausseraient la comparaison
    avant/après **sans rien casser de visible**.

    Une première version réécrivait la boucle et ajoutait une ligne vide par
    région sans texte — 41 de trop sur le corpus BnF, soit tout l'appariement
    décalé. La fonction de ``to_text`` est donc réutilisée, pas recopiée.
    """
    layout = CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(
                    Region(id="R1", lines=(Line(id="L1", text="du texte"),)),
                    Region(id="R2", lines=()),  # une illustration, par exemple
                    Region(id="R3", lines=(Line(id="L2", text="encore"),)),
                ),
            ),
        )
    )
    src = tmp_path / "l.json"
    src.write_bytes(layout.model_dump_json().encode("utf-8"))
    ref = LayoutToTextExtractor(label="x").execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a",
                document_id="d",
                type=ArtifactType.LAYOUT,
                uri=str(src),
                content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="d",
            code_version="1",
            pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    attendu = Path(ref.artifacts[ArtifactType.RAW_TEXT].uri).read_text(encoding="utf-8")
    assert _flatten(layout) == attendu


def test_a_line_without_id_is_refused(tmp_path: Path) -> None:
    """``(page, ligne)`` est une identité, pas un rang — la cause est nommée ici."""
    layout = CanonicalLayout(
        pages=(LayoutPage(regions=(Region(id="R1", lines=(Line(text="anonyme"),)),)),)
    )
    with pytest.raises(AdapterStepError, match="identité"):
        _run(tmp_path, layout)


def test_an_unknown_producer_is_refused_at_construction() -> None:
    with pytest.raises(AdapterStepError, match="producteur"):
        SaknussemmCorrector(label="x", producer="devine")


def test_ollama_without_a_model_is_refused_at_construction() -> None:
    """Un producteur réseau sans modèle échouerait au premier appel, loin d'ici."""
    with pytest.raises(AdapterStepError, match="model"):
        SaknussemmCorrector(label="x", producer="ollama")


def test_registered_under_its_own_kind() -> None:
    from cinoc.app.modules.registry import ModuleRegistry, register_default_modules

    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build("saknussemm:regles", {"label": "regles"})
    assert module.input_types == frozenset({ArtifactType.LAYOUT})
    assert module.output_types == frozenset(
        {
            ArtifactType.LAYOUT,
            ArtifactType.CORRECTED_TEXT,
            ArtifactType.DECISIONS,
        }
    )


# --------------------------------------------------------------------------- #
# Les producteurs Mistral, et le seul qui regarde le scan
#
# ``saknussemm`` livrait ``VisionEditProducer`` depuis le début ; ce dépôt ne
# câblait que ``rules`` et ``ollama``, donc la moitié vision de la bibliothèque
# était inatteignable depuis le banc. Ce qui suit verrouille le branchement, pas
# la qualité d'un modèle : aucun de ces tests n'appelle l'API.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("producteur", ["mistral", "mistral_vision"])
def test_a_mistral_producer_without_a_model_is_refused(producteur: str) -> None:
    """Comme ``ollama`` : sans modèle, l'échec arriverait au premier appel,
    après la traduction de tout un manifeste."""
    with pytest.raises(AdapterStepError, match="model"):
        SaknussemmCorrector(label="x", producer=producteur)


def test_only_the_vision_producer_asks_for_the_image() -> None:
    """Le contrat d'entrée **suit le producteur**.

    Exiger l'IMAGE partout refuserait des pipelines valides ; ne la déclarer
    nulle part la ferait arriver vide chez celui qui la découpe.
    """
    texte = SaknussemmCorrector(label="x", producer="rules")
    vision = SaknussemmCorrector(label="x", producer="mistral_vision", model="m")
    assert texte.input_types == frozenset({ArtifactType.LAYOUT})
    assert vision.input_types == frozenset(
        {ArtifactType.LAYOUT, ArtifactType.IMAGE}
    )
    # Les sorties, elles, ne changent pas : regarder l'image ne produit pas un
    # artefact de plus, seulement un meilleur texte.
    assert vision.output_types == texte.output_types


@pytest.mark.parametrize("echelle", [0.0, -1.0])
def test_a_non_positive_xml_scale_is_refused(echelle: float) -> None:
    """Une échelle nulle ou négative découperait hors de l'image — en silence."""
    with pytest.raises(AdapterStepError, match="xml_scale"):
        SaknussemmCorrector(
            label="x", producer="mistral_vision", model="m", xml_scale=echelle
        )


def test_vision_without_an_api_key_names_the_missing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Échouer ici, pas à la première ligne : la cause reste lisible."""
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    module = SaknussemmCorrector(label="x", producer="mistral_vision", model="m")
    with pytest.raises(AdapterStepError, match="MISTRAL_API_KEY"):
        module._build_producer()


def test_vision_without_an_image_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un pipeline qui oublie de brancher l'IMAGE doit s'entendre le dire ici,
    pas planter dans le découpeur de la bibliothèque."""
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    module = SaknussemmCorrector(label="x", producer="mistral_vision", model="m")
    with pytest.raises(AdapterStepError, match="IMAGE"):
        module._page_images({}, ["P_0001"])


def test_the_image_asset_carries_the_page_and_the_scale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'échelle est **portée**, pas devinée.

    Les pages ALTO de la BNL ne déclarent ni ``WIDTH`` ni ``HEIGHT`` : aucune
    comparaison avec la taille réelle du scan ne pourrait retrouver le facteur
    ``mm10`` → pixels. Une échelle fausse découpe à côté et le modèle corrige
    la mauvaise ligne, sans que rien ne le signale.
    """
    pytest.importorskip("PIL")
    from PIL import Image

    scan = tmp_path / "p.png"
    Image.new("L", (60, 40), 255).save(scan)
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    module = SaknussemmCorrector(
        label="x", producer="mistral_vision", model="m", xml_scale=1.1811
    )
    assets = module._page_images(
        {
            ArtifactType.IMAGE: Artifact(
                id="i",
                document_id="doc1",
                type=ArtifactType.IMAGE,
                uri=str(scan),
                content_hash="0" * 64,
            )
        },
        ["P_0001", "P_0002"],
    )
    assert set(assets) == {"P_0001", "P_0002"}
    # ``require_page_images`` exige que l'asset nomme sa propre page : un scan
    # rangé sous la mauvaise page est le bug silencieux que ce contrat évite.
    assert [a.page_id for a in assets.values()] == ["P_0001", "P_0002"]
    asset = assets["P_0001"]
    assert (asset.transform.scale_x, asset.transform.scale_y) == (1.1811, 1.1811)
    assert (asset.pixel_width, asset.pixel_height) == (60, 40)
    assert asset.sha256 is not None, "la provenance ancre la reproductibilité."


def test_the_default_scale_is_the_native_resolution() -> None:
    """1,0 = « l'OCR a tourné sur les pixels du scan », le cas courant."""
    module = SaknussemmCorrector(label="x", producer="mistral_vision", model="m")
    assert module._xml_scale == 1.0


# --------------------------------------------------------------------------- #
# Le routage par score de qualité — une économie, donc un opt-in explicite
# --------------------------------------------------------------------------- #


def test_routing_is_off_by_default() -> None:
    """Sans scoreur, chaque ligne part au producteur, exactement comme avant.

    C'est le défaut conservateur de ``saknussemm`` : allumer le routage change
    ce que le run **facture**, ça ne peut pas arriver par surprise.
    """
    module = SaknussemmCorrector(label="x")
    assert module._build_qe() == (None, None)


def test_an_unknown_qe_scorer_is_refused() -> None:
    with pytest.raises(AdapterStepError, match="scoreur QE"):
        SaknussemmCorrector(label="x", qe="devine")


def test_thresholds_without_a_scorer_are_refused() -> None:
    """Le défaut qu'on ne verrait pas autrement.

    Des seuils sans scoreur ne routent rien : le run coûterait le prix plein
    pendant que l'utilisateur croit avoir activé l'économie. Rien dans le
    rapport ne distinguerait ce cas d'un routage qui n'aurait rien sauté.
    """
    with pytest.raises(AdapterStepError, match="seuils de routage"):
        SaknussemmCorrector(label="x", qe_skip=0.2)


@pytest.mark.parametrize("nom", ["heuristic", "dalembert"])
def test_a_named_scorer_yields_a_scorer_and_a_policy(nom: str) -> None:
    """Le scoreur **informe**, la politique **décide** : deux objets distincts.

    ``dalembert`` est construit sans charger le moindre poids — le modèle
    n'arrive qu'au premier appel. Sans ça, nommer un scoreur coûterait 500 Mo
    avant même de savoir si le run démarre.
    """
    if nom == "dalembert":
        pytest.importorskip("transformers")
    module = SaknussemmCorrector(label="x", qe=nom, qe_skip=0.2, qe_escalate=0.8)
    scoreur, politique = module._build_qe()
    assert scoreur is not None and hasattr(scoreur, "needs_correction")
    assert (politique.skip_at_or_below, politique.escalate_at_or_above) == (0.2, 0.8)


def test_crossing_thresholds_are_refused_by_the_library() -> None:
    """Une bande qui se recouvre n'a pas d'étage LLM. ``saknussemm`` le refuse ;
    ce test dit qu'on ne le contourne pas en chemin."""
    module = SaknussemmCorrector(
        label="x", qe="heuristic", qe_skip=0.8, qe_escalate=0.2
    )
    with pytest.raises(ValueError, match="escalate"):
        module._build_qe()
