"""Séquences numériques : détecteurs et scalaires, valeurs dérivées à la main."""

from __future__ import annotations

import pytest

from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.structured_data import (
    detect_sequences,
    numseq_strict,
    numseq_value,
    sequence_counts,
)
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics


def _keys(text: str, category: str) -> list[str]:
    return [i.key for i in detect_sequences(text) if i.category == category]


def test_year_detection_bounds() -> None:
    assert _keys("en 1515 puis 2024", "year") == ["1515", "2024"]
    assert _keys("0999 et 2100 et 12345", "year") == []  # hors bornes / collé


def test_foliation_recto_verso_distinct() -> None:
    assert _keys("au fol. 12r", "foliation") == ["12r"]
    assert _keys("f. 12v", "foliation") == ["12v"]
    assert _keys("pp. 10-12", "foliation") == ["10-12"]
    assert _keys("12r tout seul", "foliation") == []  # marqueur requis


def test_currency_canonical_units() -> None:
    assert _keys("paya 3 livres", "currency") == ["3|livre"]
    assert _keys("soit 3 l. comptant", "currency") == ["3|livre"]
    assert _keys("2,5 écus", "currency") == ["2.5|écu"]


def test_regnal_roman_and_arabic() -> None:
    assert _keys("l'an III de la République", "regnal") == ["3"]
    assert _keys("en l'an 1793", "regnal") == ["1793"]
    assert _keys("an XIV", "regnal") == ["14"]
    assert _keys("an pluvieux", "regnal") == []  # pas un numéral


def test_counts_strict_versus_value() -> None:
    """« fol. 3r » → « fol 3r » : valeur préservée, forme perdue."""
    counts = sequence_counts("Paris, 1515, fol. 3r", "Paris 1515 fol 3r")
    assert counts["year"].n_total == 1
    assert (counts["year"].n_strict, counts["year"].n_value) == (1, 1)
    assert counts["foliation"].n_total == 1
    assert (counts["foliation"].n_strict, counts["foliation"].n_value) == (0, 1)
    assert counts["foliation"].lost == ()  # valeur préservée → pas perdue


def test_counts_lost_forms() -> None:
    counts = sequence_counts("daté de 1515", "daté de 1518")
    assert counts["year"].n_value == 0
    assert counts["year"].lost == ("1515",)


def _obs(metric, reference: str, hypothesis: str):
    return metric.fn(
        DocContext(document_id="d", reference=reference, hypothesis=hypothesis)
    )


def test_scalars_hand_values() -> None:
    reference = "Paris, 1515, fol. 3r"
    hypothesis = "Paris 1515 fol 3r"
    strict = _obs(numseq_strict, reference, hypothesis)
    value = _obs(numseq_value, reference, hypothesis)
    assert strict is not None and value is not None
    assert strict.value == pytest.approx(1 / 2)  # année oui, folio non
    assert value.value == pytest.approx(1.0)
    assert strict.stat.total == value.stat.total == 2


def test_scalars_not_applicable_without_signal() -> None:
    # GT sans séquence : proportion indéfinie (0/0), jamais un zéro.
    for metric in (numseq_strict, numseq_value):
        obs = _obs(metric, "bonjour le monde", "bonjour")
        assert obs.value is None and obs.stat.total == 0


def test_value_at_least_strict() -> None:
    pairs = [
        ("an III et 3 livres", "an 3 et 3 l."),
        ("fol. 12r en 1515", "f. 12r en 1515"),
    ]
    for reference, hypothesis in pairs:
        strict = _obs(numseq_strict, reference, hypothesis)
        value = _obs(numseq_value, reference, hypothesis)
        assert strict is not None and value is not None
        assert value.value >= strict.value


def test_registered_in_default_registry() -> None:
    registry = MetricRegistry()
    register_default_metrics(registry)
    assert "numseq_strict" in registry.names()
    assert "numseq_value" in registry.names()
