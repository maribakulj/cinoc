"""``cmer`` : valeurs dérivées à la main + parité ``jiwer.process_characters``.

``jiwer`` est l'oracle local de la formule (le scorer HIPE l'utilise lui-même,
SPEC_HIPE §4.1) ; le golden vs scorer épinglé vit dans ``test_hipe_golden``.
La statistique du document est (S, D, I, n_réf) **canoniques** (P1) : le
dénominateur H+S+D+I est ``n_réf + I`` ; sur un alignement sans ex æquo, ce
sont les comptes de jiwer.
"""

from __future__ import annotations

import pytest

from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.conformity import cmer
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics


def _obs(reference: str, hypothesis: str):
    return cmer.fn(
        DocContext(document_id="d", reference=reference, hypothesis=hypothesis)
    )


def _denominator(observation) -> int:
    """H+S+D+I = n_réf + I, lu dans la statistique."""
    return observation.stat.reference_length + observation.stat.insertions


@pytest.mark.parametrize(
    ("reference", "hypothesis", "value", "weight"),
    [
        ("abc", "abc", 0.0, 3),  # parfait
        ("abc", "abd", 1 / 3, 3),  # 1 substitution, H=2
        ("ab", "abxy", 2 / 4, 4),  # 2 insertions → dénominateur étendu
        ("xy", "", 1.0, 2),  # tout supprimé
        ("", "xy", 1.0, 2),  # tout inséré (le CER classique diverge ici)
        ("", "", None, 0),  # deux vides : indéfini (dénominateur nul)
    ],
)
def test_cmer_hand_values(
    reference: str, hypothesis: str, value: float | None, weight: int
) -> None:
    observation = _obs(reference, hypothesis)
    assert observation is not None
    if value is None:
        assert observation.value is None
    else:
        assert observation.value == pytest.approx(value)
    assert _denominator(observation) == weight


@pytest.mark.parametrize(
    ("reference", "hypothesis"),
    [("abc", "abd"), ("ab", "abxy"), ("chat", "chien"), ("", "xy")],
)
def test_cer_always_at_least_cmer(reference: str, hypothesis: str) -> None:
    """CER = edits/len(ref) ≥ cMER = edits/(len(ref)+I) — propriété SPEC §11."""
    observation = _obs(reference, hypothesis)
    assert observation is not None
    edits = observation.stat.edits
    cer = edits / len(reference) if reference else (1.0 if hypothesis else 0.0)
    assert cer >= observation.value - 1e-12


def _jiwer_mer(out) -> float:
    """MER depuis les **comptes** jiwer — (S+D+I)/(H+S+D+I), la formule §4.1.

    ``process_characters`` n'expose pas ``.mer`` : jiwer sert d'oracle pour
    l'**alignement** (H/S/D/I), la formule est la définition du scorer.
    """
    edits = out.substitutions + out.deletions + out.insertions
    total = out.hits + edits
    return edits / total if total else 0.0


def test_cmer_matches_jiwer_per_document() -> None:
    jiwer = pytest.importorskip("jiwer")
    pairs = [
        ("le chat dort", "le chien dort"),
        ("référence à l'été", "reference a l'ete"),
        ("abc", "abcdef"),
    ]
    for reference, hypothesis in pairs:
        out = jiwer.process_characters([reference], [hypothesis])
        observation = _obs(reference, hypothesis)
        assert observation is not None
        assert observation.value == pytest.approx(_jiwer_mer(out), abs=1e-12)
        assert _denominator(observation) == out.hits + out.substitutions + (
            out.deletions + out.insertions
        )


def test_cmer_micro_matches_jiwer_corpus() -> None:
    """Micro = Σ éditions / Σ (n_réf + I) : « somme des comptes puis ratio » (§4.1)."""
    jiwer = pytest.importorskip("jiwer")
    references = ["le chat dort", "abc", "un deux trois"]
    hypotheses = ["le chien dort", "abcdef", "un deux"]
    out = jiwer.process_characters(references, hypotheses)
    observations = [_obs(r, h) for r, h in zip(references, hypotheses, strict=True)]
    micro = sum(o.stat.edits for o in observations) / sum(
        _denominator(o) for o in observations
    )
    assert micro == pytest.approx(_jiwer_mer(out), abs=1e-12)


def test_cmer_in_default_registry() -> None:
    registry = MetricRegistry()
    register_default_metrics(registry)
    assert "cmer" in registry.names()
