"""**Une seule politique de vues** (P5g 3, D-297) : un même pipeline, qu'il
vienne du composeur, d'une recette ou du planificateur de correction, est noté
sous les **mêmes** vues — mêmes noms, mêmes métriques, même convention.

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

from cinoc.app.correction_planning import plan_correction_run
from cinoc.app.recipes import RecipeEntry, plan_recipe_run
from cinoc.app.run_planning import Competitor, plan_benchmark_run
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


def _composeur(
    corpus: CorpusSpec, comp: Competitor, tmp_path: Path, **options: object
) -> RunSpec:
    return plan_benchmark_run((comp,), corpus, "r", **options)(tmp_path)  # type: ignore[arg-type]


_PAIRES = [
    pytest.param(
        Competitor(engine="tesseract"),
        RecipeEntry(recipe="ocr_simple"),
        id="ocr-seul",
    ),
    pytest.param(
        Competitor(engine="tesseract", mode="text_only", llm="ollama", model="m"),
        RecipeEntry(
            recipe="ocr_puis_llm",
            choices={"correction": "ollama"},
            params={"correction": {"model": "m"}},
        ),
        id="ocr-puis-llm",
    ),
    pytest.param(
        Competitor(engine="ollama", mode="zero_shot", model="m"),
        RecipeEntry(
            recipe="vlm_seul",
            choices={"vlm": "ollama"},
            params={"vlm": {"model": "m"}},
        ),
        id="vlm-seul",
    ),
]

_GTS = [
    pytest.param((ArtifactType.RAW_TEXT,), id="texte"),
    pytest.param((ArtifactType.RAW_TEXT, ArtifactType.REFERENCE_TEXT), id="ref"),
    pytest.param((), id="sans-gt"),
]


@pytest.mark.parametrize("gts", _GTS)
@pytest.mark.parametrize(("comp", "entree"), _PAIRES)
def test_composer_and_recipe_score_a_pipeline_under_the_same_views(
    tmp_path: Path,
    comp: Competitor,
    entree: RecipeEntry,
    gts: tuple[ArtifactType, ...],
) -> None:
    corpus = _corpus(tmp_path, *gts)
    composeur = _composeur(corpus, comp, tmp_path)
    recette = plan_recipe_run(corpus, (entree,), run_id="r")
    assert _vues(recette) == _vues(composeur)
    assert recette.evaluation.analyses == composeur.evaluation.analyses
    assert recette.metadata == composeur.metadata


def test_a_hybrid_and_a_layout_recipe_share_the_structure_view(
    tmp_path: Path,
) -> None:
    """Segmentation puis reconnaissance par bloc : mêmes vues texte **et**
    structure, par le composeur (concurrent hybride) et par une recette."""
    corpus = _corpus(tmp_path, ArtifactType.RAW_TEXT, ArtifactType.LAYOUT)
    composeur = _composeur(
        corpus,
        Competitor(engine="tesseract", segmenter="tesseract_layout"),
        tmp_path,
    )
    recette = plan_recipe_run(
        corpus, (RecipeEntry(recipe="presse_ancienne"),), run_id="r"
    )
    assert _vues(recette) == _vues(composeur)
    assert "structure" in {v.name for v in recette.evaluation.views}


@pytest.mark.parametrize(
    "gts",
    [
        pytest.param((ArtifactType.LAYOUT,), id="alto-seul"),
        pytest.param((ArtifactType.RAW_TEXT, ArtifactType.LAYOUT), id="alto+texte"),
        pytest.param((), id="sans-gt"),
    ],
)
def test_correction_and_its_recipe_score_under_the_same_views(
    tmp_path: Path, gts: tuple[ArtifactType, ...]
) -> None:
    """Le planificateur de correction et la recette ``alto_corrige`` décrivent
    le même pipeline : ALTO source → projection + correction structurée."""
    corpus = _corpus(tmp_path, *gts)
    correction = plan_correction_run(corpus, "r")
    recette = plan_recipe_run(
        corpus, (RecipeEntry(recipe="alto_corrige"),), run_id="r"
    )
    assert _vues(recette) == _vues(correction)
    assert recette.metadata == correction.metadata


def test_scoring_options_apply_to_recipes_and_correction(tmp_path: Path) -> None:
    """La normalisation, les caractères exclus et le profil de métriques
    choisis s'appliquent à **toutes** les entrées — la limite que la page
    affichait pour les recettes tombe."""
    from cinoc.app.evaluation_views import EvaluationOptions

    corpus = _corpus(tmp_path, ArtifactType.RAW_TEXT, ArtifactType.LAYOUT)
    options = EvaluationOptions(
        normalization="nfc", char_exclude=",;", metric_profile="essentiel"
    )
    composeur = plan_benchmark_run(
        (Competitor(engine="tesseract"),), corpus, "r", options=options
    )(tmp_path)
    recette = plan_recipe_run(
        corpus, (RecipeEntry(recipe="ocr_simple"),), run_id="r", options=options
    )
    assert _vues(recette) == _vues(composeur)
    (texte,) = (v for v in recette.evaluation.views if v.name == "texte")
    assert texte.normalization_profile == "nfc"
    assert texte.char_exclude == ",;"
    assert texte.metric_names == ("cer", "wer", "mer")

    correction = plan_correction_run(corpus, "r", options=options)
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
    ocr = _composeur(avec_layout, Competitor(engine="tesseract"), tmp_path)
    assert "structure" not in {v.name for v in ocr.evaluation.views}
