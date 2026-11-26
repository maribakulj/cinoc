"""Section taxonomie : lecture seule, parts relatives, rendu déterministe."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    PipelineTaxonomy,
    TaxonomyCount,
    TaxonomyPayload,
)
from cinoc.evaluation.result import PipelineResult, RunResult
from cinoc.reports.section import Section, SectionContext
from cinoc.reports.sections.taxonomy import TaxonomySection, _class_label


def test_class_labels_rename_other_to_substitution() -> None:
    # « other » = vraies substitutions (misreads) → nommé « substitution », pas
    # un fourre-tout ; les autres clés techniques sont localisées.
    assert _class_label("other", "fr") == "substitution"
    assert _class_label("other", "en") == "substitution"
    assert _class_label("visual", "fr") == "confusion visuelle"
    assert _class_label("case", "fr") == "casse"
    assert _class_label("inconnu", "fr") == "inconnu"  # clé non répertoriée = brute

FIXED = datetime(2026, 6, 1, tzinfo=UTC)


def _result() -> RunResult:
    payload = TaxonomyPayload(
        classes=("case", "visual", "other"),
        pipelines=(
            PipelineTaxonomy(
                pipeline="tess",
                total_errors=4,
                counts=(
                    TaxonomyCount(label="visual", count=3),
                    TaxonomyCount(label="case", count=1),
                ),
            ),
        ),
    )
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=1,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )


def test_satisfies_section_protocol() -> None:
    section = TaxonomySection()
    assert isinstance(section, Section)
    assert section.name == "taxonomy"


def test_renders_composition_bar_and_legend() -> None:
    html = TaxonomySection().render(_result(), SectionContext())
    assert html is not None
    assert 'class="comp-bar"' in html  # barre empilée SVG
    assert 'class="comp-legend"' in html and 'class="comp-row"' in html
    # libellés lisibles : « visual » → « confusion visuelle », « case » → « casse »
    assert "confusion visuelle" in html and "75%" in html  # 3/4 dérivé à la main
    assert "casse" in html and "25%" in html
    assert html == TaxonomySection().render(_result(), SectionContext())


def test_without_payload_renders_nothing() -> None:
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=0,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    assert (
        TaxonomySection().render(RunResult(manifest=manifest), SectionContext())
        is None
    )


def _two_engine_result() -> RunResult:
    # tess : visuel-lourd (6/10) ; pero : segmentation-lourd (7/10). Valeurs main.
    payload = TaxonomyPayload(
        classes=("case", "visual", "segmentation"),
        pipelines=(
            PipelineTaxonomy(
                pipeline="tess",
                total_errors=10,
                counts=(
                    TaxonomyCount(label="visual", count=6),
                    TaxonomyCount(label="case", count=4),
                ),
            ),
            PipelineTaxonomy(
                pipeline="pero",
                total_errors=10,
                counts=(
                    TaxonomyCount(label="segmentation", count=7),
                    TaxonomyCount(label="case", count=3),
                ),
            ),
        ),
    )
    manifest = RunManifest(
        run_id="r", corpus_name="c", n_documents=1,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        pipelines=(
            PipelineResult(pipeline="tess", view="text"),
            PipelineResult(pipeline="pero", view="text"),
        ),
        analyses=(Analysis(scope="corpus", view="text", payload=payload),),
    )


def test_comparative_profile_compares_engines_per_class() -> None:
    html = TaxonomySection().render(_two_engine_result(), SectionContext(lang="fr"))
    assert html is not None
    assert "profil comparatif des moteurs" in html  # bloc #5 comparatif
    # Parts dérivées à la main : tess visuel 60 %, pero segmentation 70 %.
    assert "60%" in html and "70%" in html and "40%" in html and "30%" in html
    assert "segmentation" in html  # classe propre à pero, lue en ligne
    assert "·" in html  # classe absente chez un moteur (cellule vide)
    # Déterminisme bit-à-bit.
    assert html == TaxonomySection().render(_two_engine_result(), SectionContext("fr"))


def test_comparative_profile_is_bilingual_and_gated_on_two_engines() -> None:
    english = TaxonomySection().render(_two_engine_result(), SectionContext(lang="en"))
    assert english is not None and "comparative engine profile" in english
    # À 1 moteur, pas de comparaison → seule la barre empilée (pas de profil).
    assert "profil comparatif" not in (
        TaxonomySection().render(_result(), SectionContext()) or ""
    )


def test_renders_english_labels() -> None:
    # Sous lang="en", le titre/h3/prose de la section sont en anglais (le profil
    # comparatif est déjà couvert par le test bilingue ci-dessus).
    html = TaxonomySection().render(_result(), SectionContext(lang="en"))
    assert html is not None
    assert "Error taxonomy" in html  # <h2>
    assert "error composition" in html  # <h3>
    assert "Pure rule-based classification" in html  # prose
    # Les libellés FR correspondants sont absents.
    assert "Taxonomie des erreurs" not in html
    assert "composition des erreurs" not in html
    assert "Classification par règles pures" not in html


def test_prose_says_the_classes_partition_the_wer_edits() -> None:
    # D-286 : les omissions sont les suppressions du WER, en FR comme en EN.
    english = TaxonomySection().render(_result(), SectionContext(lang="en"))
    assert english is not None and "Each WER edit gets exactly one class" in english
    french = TaxonomySection().render(_result(), SectionContext(lang="fr"))
    assert french is not None and "Chaque édition du WER reçoit une classe" in french
