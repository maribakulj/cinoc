"""Un seul constructeur : tout ce que les onglets offraient, une recette l'offre.

S26 (D-298) retire le composeur à onglets (``run_planning``), le planificateur
hybride (``structure_planning.plan_hybrid_run``) et celui de la correction
(``correction_planning``) : chaque forme de run devient une recette, construite
par ``plan_recipe_run``. Ce fichier tient la **liste des capacités** que la
bascule devait préserver (``PLAN_UI_COMPOSEUR.md`` §7) — un test par capacité,
chacun construisant la spec **et** chaque brique avec ses réglages, sans rien
exécuter (``check_spec_settings``, la règle de ``cinoc run --check``).

Et la règle de nommage : un même pipeline porte le même nom par toute entrée.
"""

from __future__ import annotations

from typing import Any

import pytest

from cinoc.app.corpus_upload import GT_SOURCE_KEY
from cinoc.app.engines import providers_for_mode, segmenter_statuses
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.modules.registry import check_spec_settings
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run, recipe_entries
from cinoc.app.recipes import RecipeError
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CinocError
from cinoc.domain.run_spec import RunSpec

_CORPUS = CorpusSpec(
    name="c",
    documents=(
        DocumentRef(
            id="d",
            image_uri="d.png",
            ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri="d.txt"),),
        ),
    ),
)

#: Les moteurs OCR que l'onglet « OCR seul » proposait (``_OCR_ENGINES``).
_OCR = (
    "tesseract",
    "kraken",
    "pero",
    "calamari",
    "mistral_ocr",
    "google_vision",
    "azure_di",
)


def _plan(*entries: RecipeEntry, corpus: CorpusSpec = _CORPUS) -> RunSpec:
    spec = plan_recipe_run(corpus, entries, run_id="r")
    registre = ModuleRegistry()
    register_default_modules(registre)
    check_spec_settings(spec, registre)
    return spec


def _entry(recipe: str, **kwargs: Any) -> RecipeEntry:
    return RecipeEntry(recipe=recipe, **kwargs)


def _model(kind: str) -> dict[str, str]:
    """Le modèle requis d'un moteur qui en exige un (D-268 : aucun défaut)."""
    return {} if kind in {"tesseract", "google_vision", "azure_di"} else {"model": "m"}


# --- Onglet « OCR seul » -----------------------------------------------------


@pytest.mark.parametrize("ocr", _OCR)
def test_every_ocr_engine_of_the_old_tab_reads_the_page(ocr: str) -> None:
    spec = _plan(
        _entry("ocr_simple", choices={"ocr": ocr}, params={"ocr": _model(ocr)})
    )
    assert spec.pipelines[0].steps[0].adapter_name == f"{ocr}:ocr"


def test_tesseract_exports_its_alto_from_a_flat_read() -> None:
    """La case « Exporter l'ALTO » de l'OCR seul : le réglage ``alto`` de
    Tesseract, lu dans sa déclaration — le pli de réglages le montre."""
    spec = _plan(_entry("ocr_simple", params={"ocr": {"alto": True}}))
    assert spec.adapter_kwargs["tesseract:ocr"]["alto"] is True


# --- Onglets « OCR → LLM », « OCR → VLM », « VLM » ---------------------------


@pytest.mark.parametrize("llm", sorted(providers_for_mode("text_only")))
def test_ocr_then_llm_with_every_provider_and_a_free_prompt(llm: str) -> None:
    spec = _plan(
        _entry(
            "ocr_puis_llm",
            choices={"correction": llm},
            params={"correction": {"model": "m", "prompt": "Corrige."}},
        )
    )
    reglages = spec.adapter_kwargs[f"{llm}:correction"]
    assert (reglages["role"], reglages["prompt"]) == ("text_only", "Corrige.")


def test_a_curated_prompt_reaches_the_llm_step() -> None:
    from cinoc.app.engines import curated_prompts

    nom = curated_prompts()[0]
    spec = _plan(
        _entry(
            "ocr_puis_llm",
            choices={"correction": "ollama"},
            params={"correction": {"model": "m", "prompt_name": nom}},
        )
    )
    assert spec.adapter_kwargs["ollama:correction"]["prompt_name"] == nom


@pytest.mark.parametrize("vlm", sorted(providers_for_mode("text_and_image")))
def test_ocr_then_vlm_sees_the_image(vlm: str) -> None:
    spec = _plan(
        _entry(
            "ocr_puis_vlm",
            choices={"ocr": "kraken", "correction": vlm},
            params={"ocr": {"model": "k"}, "correction": {"model": "m"}},
        )
    )
    etape = spec.pipelines[0].steps[1]
    assert set(etape.input_types) == {ArtifactType.RAW_TEXT, ArtifactType.IMAGE}


@pytest.mark.parametrize("vlm", sorted(providers_for_mode("zero_shot")))
def test_a_vision_model_reads_the_page(vlm: str) -> None:
    spec = _plan(
        _entry("vlm_seul", choices={"vlm": vlm}, params={"vlm": {"model": "m"}})
    )
    assert spec.adapter_kwargs[f"{vlm}:vlm"]["role"] == "zero_shot"


# --- Onglet « Hybride (segmentation) » ---------------------------------------


@pytest.mark.parametrize("segmenter", [s.kind for s in segmenter_statuses()])
def test_every_segmenter_the_page_proposed_heads_a_hybrid(segmenter: str) -> None:
    """Chaque segmenteur que proposait l'onglet hybride (``segmenter_statuses``)
    se construit en tête de ``segmentation_puis_lecture`` — l'adresse et le
    jeton du segmenteur distant compris."""
    reglages = (
        {"seg": {"endpoint": "https://seg.example", "token": "t"}}
        if segmenter == "remote_segmenter"
        else {}
    )
    spec = _plan(
        _entry("segmentation_puis_lecture", choices={"seg": segmenter}, params=reglages)
    )
    assert spec.pipelines[0].steps[0].adapter_name.split(":")[0] == segmenter


@pytest.mark.parametrize("reco", [*_OCR, *sorted(providers_for_mode("zero_shot"))])
def test_every_block_reader_of_the_old_tab_reads_by_region(reco: str) -> None:
    """Tout OCR, ou un VLM en transcription par bloc (``zero_shot`` posé)."""
    spec = _plan(
        _entry(
            "segmentation_puis_lecture",
            choices={"reco": reco},
            params={"reco": _model(reco)},
        )
    )
    etape = spec.pipelines[0].steps[1]
    assert etape.fanout and etape.crop
    if reco in providers_for_mode("zero_shot"):
        assert spec.adapter_kwargs[etape.adapter_name]["role"] == "zero_shot"


def test_a_hybrid_exports_its_assembled_alto() -> None:
    spec = _plan(_entry("segmentation_puis_lecture", optional=("alto",)))
    sorties = {t for etape in spec.pipelines[0].steps for t in etape.output_types}
    assert ArtifactType.ALTO_XML in sorties


# --- La case « NER » et son modèle -------------------------------------------


@pytest.mark.parametrize(
    ("recipe", "lu"),
    [
        ("ocr_simple", ArtifactType.RAW_TEXT),
        ("vlm_seul", ArtifactType.RAW_TEXT),
        ("segmentation_puis_lecture", ArtifactType.RAW_TEXT),
        ("ocr_puis_llm", ArtifactType.CORRECTED_TEXT),
        ("ocr_puis_vlm", ArtifactType.CORRECTED_TEXT),
    ],
)
def test_named_entities_read_the_most_finished_text(
    recipe: str, lu: ArtifactType
) -> None:
    modele = {"vlm": "vlm", "ocr_puis_llm": "correction", "ocr_puis_vlm": "correction"}
    reglages: dict[str, dict[str, str | int | float | bool]] = {
        "ner": {"model": "en_core_web_sm"}
    }
    for prefixe, etape in modele.items():
        if recipe.startswith(prefixe):
            reglages[etape] = {"model": "m"}
    spec = _plan(_entry(recipe, params=reglages, optional=("ner",)))
    ner = spec.pipelines[0].steps[-1]
    assert ner.input_types == (lu,)
    assert ner.output_types == (ArtifactType.ENTITIES,)
    assert spec.adapter_kwargs[ner.adapter_name]["model"] == "en_core_web_sm"


def test_an_optional_step_left_out_takes_no_setting() -> None:
    """Un réglage pour une étape facultative non retenue serait ignoré en
    silence : refusé, nommé."""
    with pytest.raises(RecipeError, match="non retenues"):
        _plan(_entry("ocr_simple", params={"ner": {"model": "x"}}))


# --- Le panneau « Post-correction structurée » -------------------------------


def _alto_corpus(*, derived: bool) -> CorpusSpec:
    return CorpusSpec(
        name="a",
        documents=(
            DocumentRef(
                id="p",
                image_uri="p.png",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri="p.gt.txt"),
                ),
                metadata={GT_SOURCE_KEY: "layout"} if derived else {},
            ),
        ),
    )


@pytest.mark.parametrize("producer", ["rules", "ollama"])
def test_an_existing_alto_is_corrected_by_the_recipe(producer: str) -> None:
    reglages: dict[str, str | int | float | bool] = {"producer": producer}
    if producer == "ollama":
        reglages |= {"model": "qwen2.5:3b", "host": "http://localhost:11434"}
    spec = _plan(
        _entry("alto_corrige", params={"correction": reglages}),
        corpus=_alto_corpus(derived=False),
    )
    assert spec.adapter_kwargs["saknussemm:correction"]["producer"] == producer


def test_correcting_the_alto_its_ground_truth_comes_from_is_refused() -> None:
    """Le refus qui compte : sans lui, le correcteur part du texte auquel on le
    compare et le CER vaut zéro par construction. Il vaut pour toute entrée."""
    with pytest.raises(RecipeError, match="vérité terrain"):
        _plan(_entry("alto_corrige"), corpus=_alto_corpus(derived=True))
    # Lire l'OCR d'ailleurs lève le piège.
    _plan(
        _entry("alto_corrige", params={"source": {"ocr_sidecar": "ocr.json"}}),
        corpus=_alto_corpus(derived=True),
    )


# --- Un même pipeline, un même nom ------------------------------------------


def test_the_cli_and_the_page_name_a_pipeline_alike() -> None:
    """``cinoc run --recipe ocr_simple`` et la page qui choisit Tesseract sans
    rien régler : le même pipeline, donc le même nom — ``cinoc compare`` les
    apparie (D-297 n'appariait aucune ligne entre composeur et recette)."""
    cli = plan_recipe_run(_CORPUS, recipe_entries(["ocr_simple"]), run_id="r")
    page = plan_recipe_run(
        _CORPUS, (_entry("ocr_simple", choices={"ocr": "tesseract"}),), run_id="r"
    )
    assert cli.pipelines[0].name == page.pipelines[0].name == "ocr_simple · tesseract"


def test_one_recipe_under_two_engines_gets_two_names() -> None:
    """« ``ocr_simple`` » et « ``ocr_simple #2`` » ne disaient pas lequel était
    Kraken ; le nom porte désormais la brique, et le modèle."""
    spec = _plan(
        _entry("ocr_simple"),
        _entry("ocr_simple", choices={"ocr": "kraken"}, params={"ocr": {"model": "k"}}),
    )
    assert [p.name for p in spec.pipelines] == [
        "ocr_simple · tesseract",
        "ocr_simple · kraken (k)",
    ]


def test_two_models_of_one_vlm_are_told_apart_by_name() -> None:
    spec = _plan(
        _entry("vlm_seul", choices={"vlm": "ollama"}, params={"vlm": {"model": "a"}}),
        _entry("vlm_seul", choices={"vlm": "ollama"}, params={"vlm": {"model": "b"}}),
    )
    assert [p.name for p in spec.pipelines] == [
        "vlm_seul · ollama (a)",
        "vlm_seul · ollama (b)",
    ]


def test_a_retained_optional_step_shows_in_the_name() -> None:
    spec = _plan(_entry("segmentation_puis_lecture", optional=("alto",)))
    assert spec.pipelines[0].name == (
        "segmentation_puis_lecture · tesseract_layout → tesseract_layout + alto"
    )


def test_what_stays_identical_is_numbered_in_the_run() -> None:
    """Mêmes briques, mêmes modèles, un autre prompt : le nom ne départage pas,
    le rang dans le run le fait."""
    spec = _plan(
        _entry(
            "vlm_seul",
            choices={"vlm": "ollama"},
            params={"vlm": {"model": "a", "prompt": "x"}},
        ),
        _entry(
            "vlm_seul",
            choices={"vlm": "ollama"},
            params={"vlm": {"model": "a", "prompt": "y"}},
        ),
    )
    assert [p.name for p in spec.pipelines] == [
        "vlm_seul · ollama (a)",
        "vlm_seul · ollama (a) #2",
    ]


def test_the_correction_is_named_by_its_recipe() -> None:
    """``alto→rules`` était le nom d'un planificateur à part ; la correction est
    une recette, elle porte son nom — et son modèle quand elle en a un."""
    corpus = _alto_corpus(derived=False)
    regles = _plan(_entry("alto_corrige"), corpus=corpus)
    modele = _plan(
        _entry(
            "alto_corrige", params={"correction": {"producer": "ollama", "model": "q"}}
        ),
        corpus=corpus,
    )
    assert regles.pipelines[0].name == "alto_corrige"
    assert modele.pipelines[0].name == "alto_corrige · saknussemm (q)"


# --- Ce que le composeur refusait, la construction le refuse ------------------


def test_a_free_and_a_curated_prompt_together_are_refused() -> None:
    from cinoc.app.engines import curated_prompts

    with pytest.raises(CinocError, match="prompt"):
        _plan(
            _entry(
                "vlm_seul",
                choices={"vlm": "ollama"},
                params={
                    "vlm": {
                        "model": "m",
                        "prompt": "x",
                        "prompt_name": curated_prompts()[0],
                    }
                },
            )
        )


def test_an_unknown_curated_prompt_is_refused() -> None:
    with pytest.raises(CinocError, match="cinoc list prompts"):
        _plan(
            _entry(
                "vlm_seul",
                choices={"vlm": "ollama"},
                params={"vlm": {"model": "m", "prompt_name": "inexistant"}},
            )
        )


def test_a_remote_segmenter_without_its_address_is_refused() -> None:
    with pytest.raises(CinocError, match="endpoint"):
        _plan(_entry("segmentation_puis_lecture", choices={"seg": "remote_segmenter"}))


def test_the_entity_view_follows_the_optional_step() -> None:
    """La vue *entités* n'existe que si l'étape NER est retenue **et** que le
    corpus porte une GT d'entités (la politique de D-297)."""
    corpus = CorpusSpec(
        name="e",
        documents=(
            DocumentRef(
                id="d",
                image_uri="d.png",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri="d.txt"),
                    GroundTruthRef(type=ArtifactType.ENTITIES, uri="d.json"),
                ),
            ),
        ),
    )
    sans = _plan(_entry("ocr_simple"), corpus=corpus)
    avec = _plan(_entry("ocr_simple", optional=("ner",)), corpus=corpus)
    assert "entites" not in {v.name for v in sans.evaluation.views}
    assert "entites" in {v.name for v in avec.evaluation.views}
