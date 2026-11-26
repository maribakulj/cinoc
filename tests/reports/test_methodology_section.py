"""Section méthodologie & reproductibilité : appendice toujours visible."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import (
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.reports.section import Section, SectionContext
from cinoc.reports.sections.methodology import MethodologySection

FIXED = datetime(2026, 6, 1, tzinfo=UTC)


def _manifest(**kw: object) -> RunManifest:
    base: dict[str, object] = dict(
        run_id="r", corpus_name="BNL-presse", n_documents=3,
        code_version="0.9.0", started_at=FIXED, completed_at=FIXED,
    )
    base.update(kw)
    return RunManifest(**base)  # type: ignore[arg-type]


def _result(manifest: RunManifest, *, docs: int = 0) -> RunResult:
    pipelines = (
        PipelineResult(
            pipeline="tesseract", view="text",
            aggregate=(MetricScore(metric="cer", value=0.2, support=docs or 1),),
        ),
    )
    documents = tuple(
        RunDocumentResult(
            document_id=f"d{i}", pipeline="tesseract", view="text",
            scores=(MetricScore(metric="cer", value=0.2, support=1),),
        )
        for i in range(docs)
    )
    return RunResult(manifest=manifest, pipelines=pipelines, documents=documents)


def test_satisfies_protocol_and_always_renders() -> None:
    section = MethodologySection()
    assert isinstance(section, Section)
    html = section.render(_result(_manifest()), SectionContext())
    assert html is not None  # toujours présent (le manifeste existe toujours)


def test_shows_corpus_engines_metrics_date_version() -> None:
    html = MethodologySection().render(_result(_manifest()), SectionContext())
    assert html is not None
    assert "Méthodologie & reproductibilité" in html
    assert "BNL-presse" in html  # corpus
    assert "tesseract" in html  # moteur
    assert "cer" in html  # métrique calculée
    assert "2026-06-01" in html  # date
    assert "0.9.0" in html  # version du code
    # convention anti-zéro explicitée
    assert "jamais interprétée comme zéro" in html


def test_evaluated_count_shown_when_differs_from_corpus_size() -> None:
    # corpus = 3, 2 documents réellement notés → « évalués : 2 » affiché
    html = MethodologySection().render(_result(_manifest(), docs=2), SectionContext())
    assert html is not None
    assert "évalués : 2" in html


def test_view_metadata_normalisation_ignored_dims_warnings() -> None:
    view = EvaluationView(
        name="text",
        description="Texte brut projeté",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        normalization_profile="presse_xixe",
        char_exclude="¤",
        metric_names=("cer", "wer"),
        ignored_dimensions=("mise en page", "couleur"),
        warnings=("OCR seul, pas de structure",),
    )
    html = MethodologySection().render(
        _result(_manifest(view_specs=(view,))), SectionContext()
    )
    assert html is not None
    assert "Vues d" in html  # « Vues d'évaluation »
    assert "presse_xixe" in html  # profil de normalisation
    assert "¤" in html  # caractères exclus
    assert "mise en page" in html  # ce que la comparaison ne dit pas
    assert "OCR seul, pas de structure" in html  # avertissement


def test_environment_locks_in_details_when_present_absent_otherwise() -> None:
    rich = _manifest(
        system_binaries_lock={"tesseract": "5.3.4"},
        dependencies_lock={"jiwer": "3.0.4"},
        module_versions={"tesseract:fra": "1.0"},
    )
    html = MethodologySection().render(_result(rich), SectionContext())
    assert html is not None
    assert "<details>" in html and "5.3.4" in html and "jiwer" in html
    # manifeste nu → pas de bloc environnement ni <details>
    bare = MethodologySection().render(_result(_manifest()), SectionContext())
    assert bare is not None and "<details>" not in bare


def test_escapes_and_is_deterministic() -> None:
    m = _manifest(corpus_name="<corpus>")
    html = MethodologySection().render(_result(m), SectionContext())
    assert html is not None
    assert "<corpus>" not in html and "&lt;corpus&gt;" in html
    assert html == MethodologySection().render(_result(m), SectionContext())


def test_english_labels() -> None:
    html = MethodologySection().render(
        _result(_manifest()), SectionContext(lang="en")
    )
    assert html is not None
    assert "Methodology & reproducibility" in html
    assert "Méthodologie" not in html


def test_served_models_and_unicode_database_are_shown_in_both_languages() -> None:
    """Le modèle **servi** et la base Unicode (S9) rejoignent les verrous."""
    manifest = _manifest(
        served_models={"openai:c0": ("gpt-4o-mini-2024-07-18",)},
        unicode_version="15.1.0",
    )
    fr = MethodologySection().render(_result(manifest), SectionContext())
    en = MethodologySection().render(_result(manifest), SectionContext(lang="en"))
    assert fr is not None and en is not None
    assert "Modèles servis" in fr and "Base Unicode" in fr
    assert "Served models" in en and "Unicode database" in en
    for html in (fr, en):
        assert "gpt-4o-mini-2024-07-18" in html and "15.1.0" in html


def test_conventions_say_the_aggregate_is_micro_in_both_languages() -> None:
    """Pilote (D6) : la méthodologie disait « macro-moyennes par document »
    alors que l'agrégat affiché est le ratio micro Σ erreurs / Σ longueurs."""
    french = MethodologySection().render(_result(_manifest()), SectionContext())
    english = MethodologySection().render(
        _result(_manifest()), SectionContext(lang="en")
    )
    assert french is not None and english is not None
    assert "macro-moyennes par document" not in french
    assert "Les agrégats par moteur sont <b>micro</b>" in french
    assert "Σ erreurs / Σ longueurs de référence" in french
    assert "bootstrap de ce même ratio" in french
    assert "macro-averages unless" not in english
    assert "Per-engine aggregates are <b>micro</b>" in english
    assert "Σ errors / Σ reference lengths" in english
    assert "bootstrap of that same ratio" in english


def test_view_profile_is_named_and_defined_text_views_only() -> None:
    """D-285 : nom et définition du profil d'une vue texte ; rien pour une vue
    structure (le profil n'y prépare rien, la ligne mentirait)."""
    texte = EvaluationView(
        name="texte", candidate_types=frozenset({ArtifactType.RAW_TEXT})
    )
    structure = EvaluationView(
        name="structure", candidate_types=frozenset({ArtifactType.LAYOUT})
    )
    manifest = _manifest(view_specs=(texte, structure))
    fr = MethodologySection().render(_result(manifest), SectionContext())
    en = MethodologySection().render(_result(manifest), SectionContext(lang="en"))
    assert fr is not None and en is not None
    assert fr.count(">Normalisation<") == 1
    assert "<code>flat_text</code> : NFC, invisibles retirés" in fr
    assert "<code>flat_text</code>: NFC, invisible characters removed" in en
    # La convention par défaut et la comparaison brute sont dites.
    assert "<code>normalization_profile: null</code>" in fr


def test_conventions_follow_the_failure_policy_in_both_languages() -> None:
    """Reste de S12 (D-284) : « un document non produit par un moteur est omis
    de ses agrégats » était écrit quelle que soit la politique — faux sous
    ``failure_policy: max_error``, où l'unité en échec est notée à l'erreur
    maximale. La phrase suit désormais la politique du run."""
    for policy, fr_rule, en_rule in (
        (
            "exclude",
            "est <b>exclu</b> de ses agrégats",
            "is <b>left out</b> of its aggregates",
        ),
        (
            "max_error",
            "est noté à l’<b>erreur maximale</b>",
            "is scored at the <b>maximum error</b>",
        ),
    ):
        manifest = _manifest(failure_policy=policy)
        french = MethodologySection().render(_result(manifest), SectionContext())
        english = MethodologySection().render(
            _result(manifest), SectionContext(lang="en")
        )
        assert french is not None and english is not None
        assert "omis de ses agrégats" not in french
        assert "omitted from its aggregates" not in english
        assert fr_rule in french, policy
        assert en_rule in english, policy
        assert f"<code>failure_policy: {policy}</code>" in french
        assert f"<code>failure_policy: {policy}</code>" in english
