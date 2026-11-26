"""Corriger un ALTO **déjà là** : le corpus qu'on en lit, et la recette.

La correction structurée avait son planificateur ; c'est désormais la recette
``alto_corrige``, construite par la file comme toute autre (D-298). Ce fichier
tient ce qui lui est propre : lire un dossier d'ALTO en corpus, et la forme de la
chaîne — la projection lit la source, le correcteur déclare ses trois sorties,
le sidecar d'OCR atteint la source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.alto_corpus import corpus_from_alto
from cinoc.app.modules.registry import (
    ModuleRegistry,
    check_spec_settings,
    register_default_modules,
)
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.run_spec import RunSpec

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'
_ALTO = (
    f'<alto {_NS}><Layout><Page ID="P1" WIDTH="100" HEIGHT="50"><PrintSpace>'
    '<TextBlock ID="B1"><TextLine ID="L1"><String CONTENT="texte"/></TextLine>'
    "</TextBlock></PrintSpace></Page></Layout></alto>"
).encode()


def plan_correction(corpus: CorpusSpec, **params: object) -> RunSpec:
    """La recette ``alto_corrige`` — ``source.*`` et ``correction.*`` en réglages."""
    reglages: dict[str, dict[str, object]] = {}
    for cle, valeur in params.items():
        etape, _, nom = cle.partition("__")
        reglages.setdefault(etape, {})[nom] = valeur
    return plan_recipe_run(
        corpus,
        (RecipeEntry(recipe="alto_corrige", params=reglages),),  # type: ignore[arg-type]
        run_id="r",
    )


def _build(spec: RunSpec) -> None:
    registre = ModuleRegistry()
    register_default_modules(registre)
    check_spec_settings(spec, registre)


@pytest.fixture
def dossier(tmp_path: Path) -> Path:
    for nom in ("a", "b"):
        (tmp_path / f"{nom}.xml").write_bytes(_ALTO)
        (tmp_path / f"{nom}.png").write_bytes(b"pas une vraie image")
    return tmp_path


def test_a_corpus_pairs_each_alto_with_its_image(dossier: Path) -> None:
    corpus = corpus_from_alto(dossier)
    assert [d.id for d in corpus.documents] == ["a", "b"]
    # Sans sidecar, l'ALTO est le texte de départ, jamais sa propre vérité (D-307).
    assert corpus.documents[0].gt_for(ArtifactType.LAYOUT) is None


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
    spec = plan_correction(corpus)
    assert [v.name for v in spec.evaluation.views] == ["texte"]


def test_ground_truth_adds_the_structure_view(dossier: Path) -> None:
    """Un ALTO transcrit (le texte de départ venant d'un sidecar d'OCR) juge la
    structure ; il ne juge pas le texte à plat — la vue ``texte`` n'aurait
    aucune GT ``RAW_TEXT`` à lire, donc rien à noter."""
    spec = plan_correction(
        corpus_from_alto(dossier, ocr_sidecar="ocr.json"),
        source__ocr_sidecar="ocr.json",
    )
    noms = [v.name for v in spec.evaluation.views]
    assert noms == ["structure"]
    structure = spec.evaluation.views[0]
    assert "line_identity_cer" in structure.metric_names
    assert "line_identity_coverage" in structure.metric_names


def test_the_projection_reads_the_SOURCE_layout(dossier: Path) -> None:
    """``layout_to_text`` part du LAYOUT **source**, pas du corrigé.

    Le bilan de correction compare un ``RAW_TEXT`` à un ``CORRECTED_TEXT`` ;
    lui donner deux fois le texte d'arrivée n'aurait mesuré que le silence.
    """
    spec = plan_correction(corpus_from_alto(dossier))
    etapes = {s.id: s for s in spec.pipelines[0].steps}
    assert etapes["brut"].inputs_from[ArtifactType.LAYOUT] == "source"
    assert etapes["correction"].inputs_from[ArtifactType.LAYOUT] == "source"


def test_the_corrector_declares_its_three_outputs(dossier: Path) -> None:
    spec = plan_correction(corpus_from_alto(dossier))
    corr = next(s for s in spec.pipelines[0].steps if s.id == "correction")
    assert set(corr.output_types) == {
        ArtifactType.LAYOUT,
        ArtifactType.CORRECTED_TEXT,
        ArtifactType.DECISIONS,
    }


def test_the_sidecar_reaches_the_source(dossier: Path) -> None:
    spec = plan_correction(
        corpus_from_alto(dossier), source__ocr_sidecar="/chemin/ocr.json"
    )
    assert spec.adapter_kwargs["alto_source:source"]["ocr_sidecar"] == (
        "/chemin/ocr.json"
    )


def test_no_sidecar_means_no_empty_option(dossier: Path) -> None:
    """Une option vide passée à l'adapter y serait indistinguable d'un chemin
    fautif : absente, elle dit clairement qu'aucun OCR n'a été fourni."""
    spec = plan_correction(corpus_from_alto(dossier))
    assert "ocr_sidecar" not in spec.adapter_kwargs["alto_source:source"]


def test_ollama_without_a_model_is_refused(dossier: Path) -> None:
    """Refusé à la construction (``cinoc run --check``, le dépôt web), pas au
    premier appel réseau — loin d'ici."""
    with pytest.raises(CinocError, match="model"):
        _build(
            plan_correction(corpus_from_alto(dossier), correction__producer="ollama")
        )


def test_an_unknown_producer_is_refused(dossier: Path) -> None:
    with pytest.raises(CinocError, match="producer"):
        _build(
            plan_correction(corpus_from_alto(dossier), correction__producer="devine")
        )


def test_every_adapter_named_by_the_spec_can_be_built(dossier: Path) -> None:
    """La spec ne doit nommer que des modules que le registre sait construire —
    sinon l'erreur n'apparaît qu'à l'exécution, après le coût du corpus."""
    spec = plan_correction(
        corpus_from_alto(dossier), correction__producer="ollama", correction__model="m"
    )
    registry = ModuleRegistry()
    register_default_modules(registry)
    for etape in spec.pipelines[0].steps:
        module = registry.build(
            etape.adapter_name, spec.adapter_kwargs.get(etape.adapter_name, {})
        )
        assert set(etape.output_types) <= module.output_types, etape.id
