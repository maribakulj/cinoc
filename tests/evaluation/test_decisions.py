"""Bilan des décisions : distinguer « refusé » de « rien à proposer ».

Un texte corrigé ne dit pas si une ligne est intacte parce qu'une garde l'a
protégée ou parce que rien n'a été proposé. Les deux rendent le **même**
artefact, et un correcteur prudent y ressemble trait pour trait à un correcteur
inerte. C'est cette confusion que le payload existe pour lever.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.evaluation.analysis import DecisionsPayload
from cinoc.evaluation.decisions import decisions_analysis


def _outputs(tmp_path: Path, *lignes: dict[str, object], pipeline: str = "p") -> dict:
    fichier = tmp_path / f"{pipeline}.decisions.json"
    fichier.write_text(
        json.dumps({"document_id": "doc1", "lines": list(lignes)}, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        pipeline: {
            "doc1": {
                ArtifactType.DECISIONS: Artifact(
                    id="a",
                    document_id="doc1",
                    type=ArtifactType.DECISIONS,
                    uri=str(fichier),
                )
            }
        }
    }


def _ligne(
    line_id: str,
    source: str,
    final: str,
    *,
    line_class: str,
    proposed: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """Une ligne du sidecar, avec **la classe que l'adaptateur déclare** : la
    couche d'évaluation la lit, elle ne la recalcule pas d'après les textes."""
    return {
        "document_id": "doc1",
        "page_id": "P1",
        "line_id": line_id,
        "status": "corrected" if final != source else "fallback",
        "line_class": line_class,
        "class_code": reason,
        "source_text": source,
        "final_text": final,
        "proposed_text": proposed,
        "reason_code": reason,
        "reason_detail": None,
    }


def _payload(analysis) -> DecisionsPayload:
    assert analysis is not None
    assert isinstance(analysis.payload, DecisionsPayload)
    return analysis.payload


def test_the_three_outcomes_are_told_apart(tmp_path: Path) -> None:
    """Corrigée, refusée, abstention — trois situations, pas deux."""
    outputs = _outputs(
        tmp_path,
        _ligne(
            "L1", "le ſoleil", "le soleil", proposed="le soleil", line_class="corrected"
        ),
        _ligne(
            "L2",
            "v'a rien",
            "v'a rien",
            proposed="n'a rien",
            reason="e1_context",
            line_class="refused",
        ),
        _ligne("L3", "rien à faire", "rien à faire", line_class="abstained"),
    )
    row = _payload(decisions_analysis("text", outputs)).pipelines[0]
    assert (
        row.n_lines,
        row.corrected,
        sum(r.n for r in row.refused),
        row.abstained,
    ) == (3, 1, 1, 1)


def test_a_refusal_without_a_code_is_still_a_refusal(tmp_path: Path) -> None:
    """Une proposition écartée sans motif nommé reste un refus.

    La compter comme « intacte » ferait disparaître un désaccord entre le
    modèle et l'application — précisément ce qu'on veut voir.
    """
    outputs = _outputs(
        tmp_path, _ligne("L1", "abc", "abc", proposed="abd", line_class="refused")
    )
    row = _payload(decisions_analysis("text", outputs)).pipelines[0]
    assert (sum(r.n for r in row.refused), row.abstained) == (1, 0)
    assert [r.code for r in row.refused] == ["sans_motif"]


def test_reasons_are_counted_and_ordered_by_weight(tmp_path: Path) -> None:
    outputs = _outputs(
        tmp_path,
        _ligne(
            "L1", "a", "a", proposed="b", reason="e5_boundary_word",
            line_class="refused",
        ),
        _ligne(
            "L2", "c", "c", proposed="d", reason="e1_context_line",
            line_class="refused",
        ),
        _ligne(
            "L3", "e", "e", proposed="f", reason="e1_context_line",
            line_class="refused",
        ),
    )
    row = _payload(decisions_analysis("text", outputs)).pipelines[0]
    assert {r.code: r.n for r in row.refused} == {
        "e1_context_line": 2,
        "e5_boundary_word": 1,
    }


def test_no_corrector_means_no_section(tmp_path: Path) -> None:
    """Absence ≠ section vide : sans décisions, la section n'existe pas."""
    outputs = {"p": {"doc1": {ArtifactType.RAW_TEXT: Artifact(
        id="a", document_id="doc1", type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "x")
    )}}}
    assert decisions_analysis("text", outputs) is None


def test_an_unreadable_sidecar_does_not_kill_the_run(tmp_path: Path) -> None:
    """Un sidecar illisible prive d'une lecture ; il ne fausse aucun score.

    Abattre un run entier pour ça échangerait une information manquante contre
    une mesure perdue.
    """
    casse = tmp_path / "casse.json"
    casse.write_text("{ ceci n'est pas du json", encoding="utf-8")
    outputs = {
        "p": {
            "doc1": {
                ArtifactType.DECISIONS: Artifact(
                    id="a",
                    document_id="doc1",
                    type=ArtifactType.DECISIONS,
                    uri=str(casse),
                )
            }
        }
    }
    row = _payload(decisions_analysis("text", outputs)).pipelines[0]
    assert row.n_lines == 0


def test_samples_are_capped(tmp_path: Path) -> None:
    """Un rapport n'est pas un journal : au-delà, on ne lit plus, on défile."""
    lignes = [
        _ligne(f"L{i}", f"a{i}", f"b{i}", proposed=f"b{i}", line_class="corrected")
        for i in range(80)
    ]
    row = _payload(decisions_analysis("text", _outputs(tmp_path, *lignes))).pipelines[0]
    assert row.corrected == 80
    assert len(row.samples) == 40


def test_the_section_renders_the_three_columns(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from cinoc.domain.run import RunManifest
    from cinoc.evaluation.result import RunResult
    from cinoc.reports.section import SectionContext
    from cinoc.reports.sections.decisions import DecisionsSection

    analysis = decisions_analysis(
        "text",
        _outputs(
            tmp_path,
            _ligne(
                "L1", "le ſoleil", "le soleil", proposed="le soleil",
                line_class="corrected",
            ),
            _ligne(
                "L2", "v'a", "v'a", proposed="n'a", reason="e1_context_line",
                line_class="refused",
            ),
        ),
    )
    assert analysis is not None
    result = RunResult(
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=1,
            code_version="1.0",
            started_at=datetime(2026, 8, 21, tzinfo=UTC),
            completed_at=datetime(2026, 8, 21, tzinfo=UTC),
        ),
        analyses=(analysis,),
    )
    html = DecisionsSection().render(result, SectionContext(lang="fr"))
    assert html is not None
    assert "Décisions du correcteur" in html
    assert "e1_context_line" in html
    # Le texte source est échappé, pas injecté brut.
    assert "le ſoleil" in html


def test_the_section_is_absent_without_decisions() -> None:
    from datetime import UTC, datetime

    from cinoc.domain.run import RunManifest
    from cinoc.evaluation.result import RunResult
    from cinoc.reports.section import SectionContext
    from cinoc.reports.sections.decisions import DecisionsSection

    result = RunResult(
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=1,
            code_version="1.0",
            started_at=datetime(2026, 8, 21, tzinfo=UTC),
            completed_at=datetime(2026, 8, 21, tzinfo=UTC),
        )
    )
    assert DecisionsSection().render(result, SectionContext(lang="fr")) is None


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_both_languages_render(tmp_path: Path, lang: str) -> None:
    from datetime import UTC, datetime

    from cinoc.domain.run import RunManifest
    from cinoc.evaluation.result import RunResult
    from cinoc.reports.section import SectionContext
    from cinoc.reports.sections.decisions import DecisionsSection

    analysis = decisions_analysis(
        "text",
        _outputs(
            tmp_path, _ligne("L1", "a", "b", proposed="b", line_class="corrected")
        ),
    )
    assert analysis is not None
    result = RunResult(
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=1,
            code_version="1.0",
            started_at=datetime(2026, 8, 21, tzinfo=UTC),
            completed_at=datetime(2026, 8, 21, tzinfo=UTC),
        ),
        analyses=(analysis,),
    )
    assert DecisionsSection().render(result, SectionContext(lang=lang)) is not None
