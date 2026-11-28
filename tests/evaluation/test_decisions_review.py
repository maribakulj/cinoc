"""Les demandes de relecture ne sont ni des refus ni des validations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import PipelineDecisions
from cinoc.evaluation.decisions import decisions_analysis
from cinoc.evaluation.result import RunResult
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.decisions import DecisionsSection
from tests.evaluation.test_decisions import _ligne, _outputs, _payload


def test_review_counts_lines_once_per_reason_and_keeps_every_detail(
    tmp_path: Path,
) -> None:
    first = _ligne("L1", "a", "b", line_class="review_required") | {
        "status": "review_required",
        "review_reasons": [
            {"code": "systematic_removal", "detail": "a"},
            {"code": "systematic_removal", "detail": "b"},
            {"code": "digits_changed", "detail": "1 → 2"},
        ],
    }
    # A hyphen partner can be referred without changing its own text.
    second = _ligne("L2", "c", "c", line_class="review_required") | {
        "status": "review_required",
        "review_reasons": [{"code": "systematic_removal", "detail": "c"}],
    }
    row = _payload(
        decisions_analysis("text", _outputs(tmp_path, first, second))
    ).pipelines[0]
    # Classes **disjointes** (§ 2.1 f) : une ligne à relire n'est pas comptée
    # corrigée, qu'elle ait changé ou non.
    assert (
        row.corrected,
        row.abstained,
        sum(r.n for r in row.refused),
        row.review_required,
    ) == (0, 0, 0, 2)
    assert {r.code: r.n for r in row.review_reasons} == {
        "systematic_removal": 2,
        "digits_changed": 1,
    }
    assert [r.detail for r in row.samples[0].review_reasons] == ["a", "b", "1 → 2"]
    assert len(row.samples) == 2


def test_a_bilan_of_the_old_shape_is_refused_not_read() -> None:
    """Les classes sont **déclarées** et disjointes : un bilan à l'ancienne
    forme (changées, intactes — reconstruites d'après les textes) n'est pas relu
    comme tel, il est refusé (rupture de schéma, v7)."""
    with pytest.raises(ValidationError):
        PipelineDecisions.model_validate(
            {
                "pipeline": "p",
                "n_lines": 1,
                "changed": 1,
                "refused": 0,
                "untouched": 0,
            }
        )


def test_review_count_does_not_depend_on_sample_limit_or_available_reasons(
    tmp_path: Path,
) -> None:
    lines = [
        _ligne(f"L{i}", "a", "b", line_class="review_required")
        | {"status": "review_required"}
        for i in range(41)
    ]
    row = _payload(decisions_analysis("text", _outputs(tmp_path, *lines))).pipelines[0]
    assert row.review_required == 41
    assert len(row.samples) == 40
    assert [(r.code, r.n) for r in row.review_reasons] == [("sans_motif", 41)]


def test_decision_counts_come_from_the_declared_classes_not_from_the_texts(
    tmp_path: Path,
) -> None:
    """Réécrit (N12, seconde revue : l'ancien test posait ``line_class`` à la main
    puis vérifiait que cette classe était comptée, ce qui est vrai de toute
    implémentation et ne prouve rien du texte). Les comptes viennent des classes
    **déclarées** par l'adaptateur (D6, § 2.1 f), jamais d'une comparaison de
    textes — qu'elle porte sur les textes complets ou sur l'extrait affiché
    (300 caractères). Chaque ligne a donc une classe que ses textes ne disent
    pas : l'une, intacte, est déclarée corrigée ; l'autre, modifiée, est déclarée
    abstention. Une lecture par les textes complets (``final != source``) donnerait
    deux corrigées et trois abstentions ; une lecture par l'extrait, qui coupe avant
    la différence, cinq abstentions."""
    prefix = "a" * 300
    row = _payload(
        decisions_analysis(
            "text",
            _outputs(
                tmp_path,
                _ligne(
                    "L1", prefix + "x", prefix + "x", proposed=prefix + "x",
                    line_class="corrected",
                ),
                _ligne(
                    "L2", prefix + "x", prefix + "y", proposed=prefix + "y",
                    line_class="abstained",
                ),
                _ligne(
                    "L3", prefix + "x", prefix + "x", proposed=prefix + "y",
                    line_class="refused", reason="too_different_from_source",
                ),
                _ligne(
                    "L4", prefix + "x", prefix + "x", proposed=None,
                    line_class="fallback", reason="all_attempts_exhausted",
                ),
                _ligne("L5", prefix + "x", prefix + "y", line_class="review_required"),
            ),
        )
    ).pipelines[0]
    assert (row.n_lines, row.corrected, row.review_required, row.abstained) == (
        5, 1, 1, 1,
    )
    assert [(r.code, r.n) for r in row.refused] == [("too_different_from_source", 1)]
    assert [(r.code, r.n) for r in row.fallback] == [("all_attempts_exhausted", 1)]
    # L'extrait montré est coupé à 300 caractères : il ne dit pas la différence,
    # et les comptes ci-dessus n'en dépendent pas.
    assert {s.source_text for s in row.samples} == {prefix}
    assert {s.final_text for s in row.samples} == {prefix}


def test_review_status_and_reasons_are_escaped_in_the_report(tmp_path: Path) -> None:
    malicious = "<script>alert(1)</script>"
    analysis = decisions_analysis(
        "text",
        _outputs(
            tmp_path,
            _ligne("L1", "a", "b", line_class="review_required")
            | {
                "status": malicious,
                "review_reasons": [{"code": malicious, "detail": malicious}],
            },
        ),
    )
    assert analysis is not None
    result = RunResult(
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=1,
            code_version="1.0",
            started_at=datetime(2026, 10, 7, tzinfo=UTC),
            completed_at=datetime(2026, 10, 7, tzinfo=UTC),
        ),
        analyses=(analysis,),
    )
    html = DecisionsSection().render(result, SectionContext(lang="fr"))
    assert html is not None
    assert malicious not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
