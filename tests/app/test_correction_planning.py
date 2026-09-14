"""Décrire un run de correction structurée sans écrire de YAML à la main.

Le banc savait décrire trois formes de concurrent — un OCR à plat, une chaîne
OCR → LLM, un pipeline hybride. Aucune ne dit « prendre un ALTO **déjà là** et
le corriger ». La chaîne existait, mais il fallait l'écrire à la main, ce qui
n'est pas une façon d'utiliser un banc.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.correction_planning import corpus_from_alto, plan_correction_run
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.errors import CinocError

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'
_ALTO = (
    f'<alto {_NS}><Layout><Page ID="P1" WIDTH="100" HEIGHT="50"><PrintSpace>'
    '<TextBlock ID="B1"><TextLine ID="L1"><String CONTENT="texte"/></TextLine>'
    "</TextBlock></PrintSpace></Page></Layout></alto>"
).encode()


@pytest.fixture
def dossier(tmp_path: Path) -> Path:
    for nom in ("a", "b"):
        (tmp_path / f"{nom}.xml").write_bytes(_ALTO)
        (tmp_path / f"{nom}.png").write_bytes(b"pas une vraie image")
    return tmp_path


def test_a_corpus_pairs_each_alto_with_its_image(dossier: Path) -> None:
    corpus = corpus_from_alto(dossier)
    assert [d.id for d in corpus.documents] == ["a", "b"]
    assert corpus.documents[0].gt_for(ArtifactType.LAYOUT) is not None


def test_an_alto_without_its_image_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "seul.xml").write_bytes(_ALTO)
    with pytest.raises(CinocError, match="aucune paire"):
        corpus_from_alto(tmp_path)


def test_ocr_alto_declares_no_ground_truth(dossier: Path) -> None:
    """Un ALTO d'OCR n'est pas une référence.

    L'y déclarer ferait comparer le texte à lui-même — le zéro tautologique.
    Le paramètre existe pour que ce soit un choix visible, pas un défaut muet.
    """
    corpus = corpus_from_alto(dossier, ground_truth=False)
    assert corpus.documents[0].gt_for(ArtifactType.LAYOUT) is None
    spec = plan_correction_run(corpus, "r")
    assert [v.name for v in spec.evaluation.views] == ["texte"]


def test_ground_truth_adds_the_structure_view(dossier: Path) -> None:
    spec = plan_correction_run(corpus_from_alto(dossier), "r")
    noms = [v.name for v in spec.evaluation.views]
    assert noms == ["texte", "structure"]
    structure = spec.evaluation.views[1]
    assert "line_identity_cer" in structure.metric_names
    assert "line_identity_coverage" in structure.metric_names


def test_the_projection_reads_the_SOURCE_layout(dossier: Path) -> None:
    """``layout_to_text`` part du LAYOUT **source**, pas du corrigé.

    Le bilan de correction compare un ``RAW_TEXT`` à un ``CORRECTED_TEXT`` ;
    lui donner deux fois le texte d'arrivée n'aurait mesuré que le silence.
    """
    spec = plan_correction_run(corpus_from_alto(dossier), "r")
    etapes = {s.id: s for s in spec.pipelines[0].steps}
    assert etapes["brut"].inputs_from[ArtifactType.LAYOUT] == "source"
    assert etapes["corr"].inputs_from[ArtifactType.LAYOUT] == "source"


def test_the_corrector_declares_its_three_outputs(dossier: Path) -> None:
    spec = plan_correction_run(corpus_from_alto(dossier), "r")
    corr = next(s for s in spec.pipelines[0].steps if s.id == "corr")
    assert set(corr.output_types) == {
        ArtifactType.LAYOUT,
        ArtifactType.CORRECTED_TEXT,
        ArtifactType.DECISIONS,
    }


def test_the_sidecar_reaches_the_source(dossier: Path) -> None:
    spec = plan_correction_run(
        corpus_from_alto(dossier), "r", ocr_sidecar="/chemin/ocr.json"
    )
    assert spec.adapter_kwargs["alto_source"]["ocr_sidecar"] == "/chemin/ocr.json"


def test_no_sidecar_means_no_empty_option(dossier: Path) -> None:
    """Une option vide passée à l'adapter y serait indistinguable d'un chemin
    fautif : absente, elle dit clairement qu'aucun OCR n'a été fourni."""
    spec = plan_correction_run(corpus_from_alto(dossier), "r")
    assert "ocr_sidecar" not in spec.adapter_kwargs["alto_source"]


def test_ollama_without_a_model_is_refused(dossier: Path) -> None:
    """Refusé à la planification, pas au premier appel réseau — loin d'ici."""
    with pytest.raises(CinocError, match="model"):
        plan_correction_run(corpus_from_alto(dossier), "r", producer="ollama")


def test_an_unknown_producer_is_refused(dossier: Path) -> None:
    with pytest.raises(CinocError, match="producteur"):
        plan_correction_run(corpus_from_alto(dossier), "r", producer="devine")


def test_every_adapter_named_by_the_spec_can_be_built(dossier: Path) -> None:
    """La spec ne doit nommer que des modules que le registre sait construire —
    sinon l'erreur n'apparaît qu'à l'exécution, après le coût du corpus."""
    from cinoc.app.modules.registry import ModuleRegistry, register_default_modules

    spec = plan_correction_run(
        corpus_from_alto(dossier), "r", producer="ollama", model="m"
    )
    registry = ModuleRegistry()
    register_default_modules(registry)
    for etape in spec.pipelines[0].steps:
        module = registry.build(
            etape.adapter_name, spec.adapter_kwargs.get(etape.adapter_name, {})
        )
        assert set(etape.output_types) <= module.output_types, etape.id


def test_the_corrector_is_a_parameter_not_a_hardwired_name(dossier: Path) -> None:
    """**La couche qui planifie n'a pas à nommer un fournisseur.**

    Elle en propose un par défaut — c'est un service, pas une dépendance. Le
    jour où un second correcteur `LAYOUT → LAYOUT + CORRECTED_TEXT + DECISIONS`
    existe, cette fonction n'a rien à apprendre : l'appelant nomme le sien.

    Sans ce test, le nom reviendrait en dur à la première modification, et rien
    ne le signalerait.
    """
    from cinoc.app.correction_planning import DEFAULT_CORRECTOR, plan_correction_run

    corpus = corpus_from_alto(dossier)
    defaut = plan_correction_run(corpus, "r")
    autre = plan_correction_run(corpus, "r", corrector_kind="un_autre")

    noms_defaut = {e.adapter_name for p in defaut.pipelines for e in p.steps}
    noms_autre = {e.adapter_name for p in autre.pipelines for e in p.steps}
    assert any(n.startswith(f"{DEFAULT_CORRECTOR}:") for n in noms_defaut)
    assert any(n.startswith("un_autre:") for n in noms_autre)
    assert not any(n.startswith("saknussemm:") for n in noms_autre), (
        "le fournisseur par défaut ne doit pas survivre au choix de l'appelant."
    )
