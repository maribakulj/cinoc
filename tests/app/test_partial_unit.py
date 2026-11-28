"""Une unité **partielle** : déclarée par l'étape, portée par l'exécuteur, archivée.

L'étape déclare sa sortie incomplète (``StepOutput.partial``) et compte les
issues de ses lignes ; l'exécuteur le porte en ``UnitOutcome = partial`` avec le
nom de l'étape ; l'archive le garde. Une reprise normale la **retente** (sa part
manquante vient d'un incident d'exécution), la relecture hors ligne la restitue
telle qu'archivée (§ 2.1 e, f de ``CONTRATS.md``).
"""

from __future__ import annotations

from pathlib import Path

from cinoc.app.modules.registry import ModuleRegistry
from cinoc.app.orchestrator import run
from cinoc.app.resume import ResumeStore
from cinoc.domain.usage import LineOutcomes
from cinoc.pipeline.types import StepOutput
from tests.app.test_resume import _CountingOCR, _spec

_OUTCOMES = LineOutcomes(corrected=2, abstained=1, fallback={"chunk_error_absorbed": 3})


class _PartialOCR(_CountingOCR):
    """Un moteur dont l'étape déclare sa sortie incomplète."""

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        output = super().execute(inputs, params, context, control)
        return StepOutput(
            artifacts=output.artifacts,
            partial="3 ligne(s) en repli",
            line_outcomes=_OUTCOMES,
        )


def _registry(calls: list[str]) -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register_builder("counting", lambda kwargs: _PartialOCR(calls))
    return registry


def test_the_unit_is_partial_and_names_its_step(tmp_path: Path) -> None:
    calls: list[str] = []
    result = run(
        _spec(tmp_path), registry=_registry(calls), code_version="1.0", max_workers=1
    )
    (unit,) = result.usage
    assert unit.outcome == "partial" and unit.reason is None
    assert unit.step_issues == {"ocr": "partial"}
    assert unit.line_outcomes == _OUTCOMES
    (pipeline,) = result.pipelines
    assert pipeline.line_outcomes == _OUTCOMES
    (cer,) = (s for s in pipeline.aggregate if s.metric == "cer")
    # Non notée par défaut (R6), conservée à part, et comptée à la couverture.
    assert cer.value is None and cer.coverage == {"partial_output": 1}
    assert result.documents[0].scores[0].stat_partielle is not None


def test_a_normal_resume_retries_it_and_offline_restores_it(tmp_path: Path) -> None:
    calls: list[str] = []
    store = ResumeStore(tmp_path / "cache")
    spec = _spec(tmp_path)
    run(spec, registry=_registry(calls), code_version="1.0", resume_store=store)
    run(spec, registry=_registry(calls), code_version="1.0", resume_store=store)
    assert calls == ["d1", "d1"]  # la part manquante vient d'un incident : retentée
    replay = run(
        spec,
        registry=_registry(calls),
        code_version="1.0",
        resume_store=store,
        offline=True,
    )
    assert calls == ["d1", "d1"]  # hors ligne : rien ne s'exécute
    (unit,) = replay.usage
    assert unit.outcome == "partial" and unit.resumed
    assert unit.step_issues == {"ocr": "partial"}
    assert unit.line_outcomes == _OUTCOMES
