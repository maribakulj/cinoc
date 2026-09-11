"""Registre type-driven : sélection, idempotence, pas d'auto-peuplement."""

from __future__ import annotations

from cinoc.domain.artifacts import ArtifactType
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics


def test_default_metrics_registration_is_idempotent() -> None:
    registry = MetricRegistry()
    register_default_metrics(registry)
    register_default_metrics(registry)
    assert registry.names() == (
        "air",
        "bow_f1",
        "bow_precision",
        "bow_recall",
        "cer",
        "cer_diplo",
        "char_accuracy",
        "cmer",
        "del_rate",
        "diacritic_err",
        "fca",
        "hallucination",
        "ins_rate",
        "line_identity_cer",
        "line_identity_coverage",
        "mer",
        "mufi_err",
        "ner_f1",
        "numseq_strict",
        "numseq_value",
        "reading_order_coverage",
        "reading_order_tau",
        "region_cer",
        "region_detection",
        "searchability",
        "wer",
        "word_accuracy",
    )


def test_get_and_select_by_input_types() -> None:
    registry = MetricRegistry()
    register_default_metrics(registry)
    assert registry.document_metric("cer") is not None
    assert registry.document_metric("wer") is not None
    assert registry.document_metric("inconnue") is None
    selected = registry.for_input_types(
        ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT
    )
    assert {metric.name for metric in selected} == {
        "air",
        "bow_f1",
        "bow_precision",
        "bow_recall",
        "cer",
        "cer_diplo",
        "char_accuracy",
        "cmer",
        "del_rate",
        "diacritic_err",
        "fca",
        "hallucination",
        "ins_rate",
        "wer",
        "word_accuracy",
        "mer",
        "mufi_err",
        "numseq_strict",
        "numseq_value",
        "searchability",
    }
    layout_metrics = registry.for_input_types(
        ArtifactType.LAYOUT, ArtifactType.LAYOUT
    )
    assert {metric.name for metric in layout_metrics} == {
        "line_identity_cer",
        "line_identity_coverage",
        "reading_order_coverage",
        "reading_order_tau",
        "region_cer",
        "region_detection",
    }
    entity_metrics = registry.for_input_types(
        ArtifactType.ENTITIES, ArtifactType.ENTITIES
    )
    assert {metric.name for metric in entity_metrics} == {"ner_f1"}


def test_fresh_registry_is_empty() -> None:
    assert MetricRegistry().names() == ()


def test_cross_engine_metrics_registered() -> None:
    registry = MetricRegistry()
    register_default_metrics(registry)
    names = {metric.name for metric in registry.cross_engine_metrics()}
    assert "significance_p" in names


def test_fresh_registry_has_no_cross_engine_metrics() -> None:
    assert MetricRegistry().cross_engine_metrics() == ()
