"""**Une seule politique de vues** (P5g 3, D-297) : un même pipeline est noté
sous les **mêmes** vues — mêmes noms, mêmes métriques, même convention —, et
deux pipelines qui produisent la même chose le sont aussi.

Depuis D-298 il n'y a plus qu'un constructeur (la file de recettes) : les tests
qui confrontaient le composeur, une recette et le planificateur de correction
sont devenus des tautologies et ont été retirés ; restent ceux qui disent ce que
la politique décide.

Avant, trois rapports différents pour un même pipeline : le composeur notait le
texte sous le profil ``standard`` (dix colonnes), les recettes et la correction
sous ``cer, wer`` ; la structure s'appelait « structure (mise en page) » ici,
« structure » là, avec trois listes de métriques ; et la normalisation, les
caractères exclus et le profil de métriques choisis à la page ne s'appliquaient
pas aux recettes. ``cinoc compare`` apparie par ``(pipeline, vue, métrique)`` :
deux noms de vue pour une même mesure, et la comparaison ne voit rien.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.run_spec import RunSpec

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'
_ALTO = (
    f'<alto {_NS}><Layout><Page ID="P1" WIDTH="100" HEIGHT="50"><PrintSpace>'
    '<TextBlock ID="B1"><TextLine ID="L1"><String CONTENT="texte"/></TextLine>'
    "</TextBlock></PrintSpace></Page></Layout></alto>"
)


def _corpus(tmp_path: Path, *types: ArtifactType) -> CorpusSpec:
    """Un document, une GT par type demandé ; le texte tient sur deux lignes
    (la vue ``texte (lignes)`` s'ajoute)."""
    contenus = {
        ArtifactType.RAW_TEXT: ("d.gt.txt", "le roi\ndort"),
        ArtifactType.LAYOUT: ("d.xml", _ALTO),
        ArtifactType.ENTITIES: ("d.ents.json", '{"entities": []}'),
        ArtifactType.REFERENCE_TEXT: ("d.ref.txt", "le roy dort"),
    }
    verites = []
    for t in types:
        nom, texte = contenus[t]
        (tmp_path / nom).write_text(texte, encoding="utf-8")
        verites.append(GroundTruthRef(type=t, uri=str(tmp_path / nom)))
    return CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="d",
                image_uri=str(tmp_path / "d.png"),
                ground_truths=tuple(verites),
            ),
        ),
    )


def _vues(spec: RunSpec) -> list[dict[str, object]]:
    return [v.model_dump(mode="json") for v in spec.evaluation.views]


def test_a_hybrid_and_a_layout_recipe_share_the_structure_view(
    tmp_path: Path,
) -> None:
    """Segmentation puis reconnaissance par bloc, avec ou sans prétraitement
    ni ordre de lecture : mêmes vues texte **et** structure."""
    corpus = _corpus(tmp_path, ArtifactType.RAW_TEXT, ArtifactType.LAYOUT)
    hybride = plan_recipe_run(
        corpus, (RecipeEntry(recipe="segmentation_puis_lecture"),), run_id="r"
    )
    recette = plan_recipe_run(
        corpus, (RecipeEntry(recipe="presse_ancienne"),), run_id="r"
    )
    assert _vues(recette) == _vues(hybride)
    assert "structure" in {v.name for v in recette.evaluation.views}


@pytest.mark.parametrize(
    ("gts", "attendues"),
    [
        pytest.param((ArtifactType.LAYOUT,), {"structure"}, id="alto-seul"),
        pytest.param(
            (ArtifactType.RAW_TEXT, ArtifactType.LAYOUT),
            {"texte", "texte (lignes)", "structure"},
            id="alto+texte",
        ),
        pytest.param((), {"texte"}, id="sans-gt"),
    ],
)
def test_the_correction_is_scored_where_its_corpus_can_judge_it(
    tmp_path: Path, gts: tuple[ArtifactType, ...], attendues: set[str]
) -> None:
    """La recette ``alto_corrige`` : la structure n'est notée que sur une GT
    ``LAYOUT``, le texte que sur une GT ``RAW_TEXT`` (seul repli : la vue texte
    d'un corpus sans aucune GT, exécutable et non noté)."""
    corpus = _corpus(tmp_path, *gts)
    recette = plan_recipe_run(corpus, (RecipeEntry(recipe="alto_corrige"),), run_id="r")
    assert {v.name for v in recette.evaluation.views} == attendues


def test_scoring_options_apply_to_recipes_and_correction(tmp_path: Path) -> None:
    """La normalisation, les caractères exclus et le profil de métriques
    choisis s'appliquent à **toutes** les entrées — la limite que la page
    affichait pour les recettes tombe."""
    from cinoc.app.evaluation_views import EvaluationOptions

    corpus = _corpus(tmp_path, ArtifactType.RAW_TEXT, ArtifactType.LAYOUT)
    options = EvaluationOptions(
        normalization="nfc", char_exclude=",;", metric_profile="essentiel"
    )
    recette = plan_recipe_run(
        corpus, (RecipeEntry(recipe="ocr_simple"),), run_id="r", options=options
    )
    (texte,) = (v for v in recette.evaluation.views if v.name == "texte")
    assert texte.normalization_profile == "nfc"
    assert texte.char_exclude == ",;"
    assert texte.metric_names == ("cer", "wer", "mer")

    correction = plan_recipe_run(
        corpus, (RecipeEntry(recipe="alto_corrige"),), run_id="r", options=options
    )
    (texte,) = (v for v in correction.evaluation.views if v.name == "texte")
    assert texte.normalization_profile == "nfc"
    assert texte.metric_names == ("cer", "wer", "mer")


def test_a_view_is_only_declared_when_it_can_score_something(
    tmp_path: Path,
) -> None:
    """Une vue sans candidat ou sans vérité terrain ne note rien : une vue vide
    vaut moins que pas de vue (la structure exige une sortie **et** une GT
    ``LAYOUT``)."""
    texte_seul = _corpus(tmp_path, ArtifactType.RAW_TEXT)
    recette = plan_recipe_run(
        texte_seul, (RecipeEntry(recipe="presse_ancienne"),), run_id="r"
    )
    assert "structure" not in {v.name for v in recette.evaluation.views}
    avec_layout = _corpus(tmp_path, ArtifactType.RAW_TEXT, ArtifactType.LAYOUT)
    ocr = plan_recipe_run(avec_layout, (RecipeEntry(recipe="ocr_simple"),), run_id="r")
    assert "structure" not in {v.name for v in ocr.evaluation.views}
