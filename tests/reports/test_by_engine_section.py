"""Section by-engine : comparaison ordonnée par CER (sans rang ordinal) +
dispersion par-document."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.comparison import ComparisonPayload, GlobalSupport
from cinoc.evaluation.result import (
    Analysis,
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.by_engine import EngineSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _agg(pipeline: str, cer: float) -> PipelineResult:
    return PipelineResult(
        pipeline=pipeline,
        view="text",
        conditional_aggregate=(MetricScore(metric="cer", value=cer, support=2),),
    )


def _doc(doc_id: str, pipeline: str, cer: float) -> RunDocumentResult:
    return RunDocumentResult(
        document_id=doc_id,
        pipeline=pipeline,
        view="text",
        scores=(MetricScore(metric="cer", value=cer, support=1),),
    )


def _result() -> RunResult:
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=2,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    return RunResult(
        manifest=manifest,
        pipelines=(_agg("slow", 0.30), _agg("fast", 0.10)),
        documents=(
            _doc("d1", "slow", 0.40),
            _doc("d2", "slow", 0.20),
            _doc("d1", "fast", 0.05),
            _doc("d2", "fast", 0.15),
        ),
        # Le tri est celui du support global publié (D7) : l'ordre du tableau le lit.
        analyses=(
            Analysis(
                scope="corpus",
                view="text",
                payload=ComparisonPayload(
                    metric="cer",
                    global_support=GlobalSupport(ranking=("fast", "slow")),
                ),
            ),
        ),
    )


def test_engines_ordered_by_cer_without_ordinal_rank() -> None:
    html = EngineSection().render(_result(), SectionContext())
    assert html is not None
    assert "Comparaison des moteurs" in html  # titre neutre (≠ « Classement »)
    assert "Classement" not in html  # plus de cadrage « verdict »
    # le plus bas CER (fast, 0.10) est listé avant le plus haut (slow, 0.30) —
    # un tri lisible, PAS un rang attribué.
    assert html.index("fast") < html.index("slow")
    # AUCUN rang ordinal : ni colonne « # », ni cellule .rank, ni 1/2 numérotés.
    assert "<th>#</th>" not in html
    assert 'class="rank"' not in html
    assert "n'est déclaré" in html  # neutralité affirmée dans la prose
    # dispersion de fast : min 0.05 · médiane 0.10 · max 0.15
    assert "0,050" in html and "0,150" in html
    # badge moteur présent, et la lettre suit l'ordre canonique (pas le tri) :
    # `slow` apparaît d'abord dans le run → A puis B, même si `fast` a un CER plus bas.
    assert 'class="eng-badge"' in html


def test_engine_name_is_clickable_link_to_its_profile() -> None:
    # Le NOM du moteur (cellule eng-cell) est un lien vers son profil drill-in
    # (#engine-N) — cliquer le moteur ouvre son analyse, pas seulement une flèche.
    html = EngineSection().render(_result(), SectionContext())
    assert html is not None
    # un lien par moteur, ancré sur le panneau profil (ordre canonique : A=fast? non,
    # fast/slow : « slow » apparaît d'abord dans pipelines → engine-0, fast → engine-1)
    assert '<td class="eng-cell"><a href="#engine-' in html
    assert html.count('<td class="eng-cell"><a href="#engine-') == 2
    # plus de colonne « flèche » résiduelle (le nom porte l'affordance)
    assert "eng-open" not in html and "eng-link" not in html


def test_table_is_sortable_with_def_headers() -> None:
    # Tables vivantes : table triable, en-têtes de métrique avec def au survol,
    # cellules porteuses de la clé de tri.
    html = EngineSection().render(_result(), SectionContext())
    assert html is not None
    assert 'class="data sortable"' in html
    assert "has-def" in html and "aria-sort" in html  # en-tête triable + def
    assert "data-sort=" in html  # cellules métriques porteuses de la valeur
    # Réordonner ≠ classer : la prose parle de tri, pas de rang attribué.
    assert "un tri, pas un rang attribué" in html


def test_air_and_hcpr_render_as_diagnostic_columns() -> None:
    # Scalaires archaïques affichés comme colonnes by_engine (avec leur valeur),
    # en-têtes porteurs de leur définition de glossaire — exploratoires, ils
    # sont au diagnostic, marqués, sans tri (D-289).
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    pipeline = PipelineResult(
        pipeline="eng",
        view="text",
        conditional_aggregate=(
            MetricScore(metric="cer", value=0.10, support=1),
            MetricScore(metric="air", value=0.25, support=1),
            MetricScore(metric="hcpr", value=0.80, support=1),
        ),
    )
    result = RunResult(
        manifest=manifest,
        pipelines=(pipeline,),
        documents=(_doc("d1", "eng", 0.10),),
    )
    html = EngineSection().render(result, SectionContext())
    assert html is not None
    ranking, diagnostic = html.split("<h3>Diagnostic</h3>")
    assert ">air" not in ranking and ">hcpr" not in ranking
    assert ">air<sup" in diagnostic and ">hcpr<sup" in diagnostic
    assert "exploratoire" in diagnostic and "sortable" not in diagnostic
    assert "0,2500" in html and "0,8000" in html  # valeurs rendues
    assert "Apport net" in html  # définition glossaire FR de air au survol


def test_renders_english_labels() -> None:
    html = EngineSection().render(_result(), SectionContext(lang="en"))
    assert html is not None
    # vue unique → titre sans suffixe de vue (pas de ressassage)
    assert "Engine comparison" in html and "(view:" not in html  # <h2>
    assert "Ranking" not in html  # plus de cadrage « verdict »
    assert "<th>Engine</th>" in html  # en-tête de colonne moteur
    assert "Ordered by" in html  # prose de tri
    assert "No winner is declared" in html  # neutralité affirmée
    assert 'title="Profile"' in html  # lien vers le profil moteur
    # Les libellés FR correspondants sont absents.
    assert "Comparaison des moteurs" not in html
    assert "<th>Moteur</th>" not in html
    assert "Ordonné par" not in html
    assert 'title="Profil"' not in html


def test_returns_none_without_pipelines() -> None:
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=0,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    empty = RunResult(manifest=manifest)
    assert EngineSection().render(empty, SectionContext()) is None
