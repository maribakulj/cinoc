"""``PipelineExecutor`` — résolution des entrées, estampillage, annulation."""

from __future__ import annotations

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import (
    AdapterStepError,
    CinocError,
    DeadlineExceeded,
    RunCancelledError,
)
from cinoc.domain.pipeline import INITIAL_STEP_ID, PipelineSpec, PipelineStep
from cinoc.domain.usage import ResourceUsage
from cinoc.pipeline.executor import (
    UNIT_FAILURES,
    PipelineExecutor,
    PipelineStepError,
    failure_reason,
)
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import DocumentExecution, StepOutput

CODE_VERSION = "test-1.0"


def _image() -> Artifact:
    return Artifact(
        id="doc1:init:image",
        document_id="doc1",
        type=ArtifactType.IMAGE,
        uri="img://doc1.png",
    )


class _EchoModule:
    """Module de test : IMAGE → RAW_TEXT."""

    name = "fake:echo"
    version = "0.1"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri="mem://raw",
                )
            }
        )


class _UpperModule:
    """Module de test : RAW_TEXT → CORRECTED_TEXT."""

    name = "fake:upper"
    version = "0.1"
    input_types = frozenset({ArtifactType.RAW_TEXT})
    output_types = frozenset({ArtifactType.CORRECTED_TEXT})

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        return StepOutput(
            artifacts={
                ArtifactType.CORRECTED_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:corrected",
                    document_id=context.document_id,
                    type=ArtifactType.CORRECTED_TEXT,
                    uri="mem://corrected",
                )
            }
        )


class _EmptyModule:
    """Module fautif : déclare RAW_TEXT mais ne produit rien."""

    name = "fake:empty"
    version = "0.1"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        return StepOutput(artifacts={})


def _ocr_step() -> PipelineStep:
    return PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="fake:echo",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )


def test_runs_single_step_and_stamps_provenance() -> None:
    spec = PipelineSpec(
        name="p1", initial_inputs=(ArtifactType.IMAGE,), steps=(_ocr_step(),)
    )
    ex = PipelineExecutor(CODE_VERSION)
    pool = ex.execute_document(
        spec, {"fake:echo": _EchoModule()}, {ArtifactType.IMAGE: _image()},
        document_id="doc1",
    )
    art = pool.artifacts[ArtifactType.RAW_TEXT]
    assert art.produced_by_step == "ocr"
    assert art.provenance is not None
    assert art.provenance.code_version == CODE_VERSION
    assert art.provenance.parameters_hash is not None


def test_two_steps_resolve_inputs_from() -> None:
    step2 = PipelineStep(
        id="llm",
        kind="post_correction",
        adapter_name="fake:upper",
        input_types=(ArtifactType.RAW_TEXT,),
        output_types=(ArtifactType.CORRECTED_TEXT,),
        inputs_from={ArtifactType.RAW_TEXT: "ocr"},
    )
    spec = PipelineSpec(
        name="p2", initial_inputs=(ArtifactType.IMAGE,), steps=(_ocr_step(), step2)
    )
    ex = PipelineExecutor(CODE_VERSION)
    pool = ex.execute_document(
        spec,
        {"fake:echo": _EchoModule(), "fake:upper": _UpperModule()},
        {ArtifactType.IMAGE: _image()},
        document_id="doc1",
    )
    assert ArtifactType.CORRECTED_TEXT in pool.artifacts


def test_missing_module_raises() -> None:
    spec = PipelineSpec(
        name="p1", initial_inputs=(ArtifactType.IMAGE,), steps=(_ocr_step(),)
    )
    ex = PipelineExecutor(CODE_VERSION)
    with pytest.raises(PipelineStepError):
        ex.execute_document(
            spec, {}, {ArtifactType.IMAGE: _image()}, document_id="doc1"
        )


def test_missing_input_raises() -> None:
    spec = PipelineSpec(
        name="p1", initial_inputs=(ArtifactType.IMAGE,), steps=(_ocr_step(),)
    )
    ex = PipelineExecutor(CODE_VERSION)
    with pytest.raises(PipelineStepError):
        ex.execute_document(
            spec, {"fake:echo": _EchoModule()}, {}, document_id="doc1"
        )


def test_undeclared_output_raises() -> None:
    bad = PipelineStep(
        id="bad",
        kind="ocr",
        adapter_name="fake:empty",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    spec = PipelineSpec(
        name="pbad", initial_inputs=(ArtifactType.IMAGE,), steps=(bad,)
    )
    ex = PipelineExecutor(CODE_VERSION)
    with pytest.raises(PipelineStepError):
        ex.execute_document(
            spec, {"fake:empty": _EmptyModule()}, {ArtifactType.IMAGE: _image()},
            document_id="doc1",
        )


def test_cancellation_raises_before_step() -> None:
    spec = PipelineSpec(
        name="p1", initial_inputs=(ArtifactType.IMAGE,), steps=(_ocr_step(),)
    )
    ex = PipelineExecutor(CODE_VERSION)
    control = RunControl()
    control.trigger_cancel()
    with pytest.raises(RunCancelledError):
        ex.execute_document(
            spec, {"fake:echo": _EchoModule()}, {ArtifactType.IMAGE: _image()},
            document_id="doc1", control=control,
        )


def test_empty_code_version_rejected() -> None:
    with pytest.raises(CinocError):
        PipelineExecutor("")


def test_threads_workspace_uri_to_context() -> None:
    captured: dict[str, str | None] = {}

    class _Capture:
        version = "1.0"
        input_types = frozenset({ArtifactType.IMAGE})
        output_types = frozenset({ArtifactType.RAW_TEXT})

        def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
            captured["workspace"] = context.workspace_uri
            return StepOutput(
                artifacts={
                    ArtifactType.RAW_TEXT: Artifact(
                        id=f"{context.document_id}:cap:raw_text",
                        document_id=context.document_id,
                        type=ArtifactType.RAW_TEXT,
                        uri="mem://x",
                    )
                }
            )

    spec = PipelineSpec(
        name="p", initial_inputs=(ArtifactType.IMAGE,), steps=(_ocr_step(),)
    )
    PipelineExecutor(CODE_VERSION).execute_document(
        spec,
        {"fake:echo": _Capture()},
        {ArtifactType.IMAGE: _image()},
        document_id="doc1",
        workspace_uri="/work",
    )
    assert captured["workspace"] == "/work"


class _TokenModule:
    """Module de test : IMAGE → RAW_TEXT, remonte des jetons (façon LLM)."""

    name = "fake:tokens"
    version = "0.1"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri="mem://raw",
                )
            },
            usage=ResourceUsage(tokens_in=120, tokens_out=30),
        )


def test_usage_records_duration_and_tokens() -> None:
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="fake:tokens",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    spec = PipelineSpec(name="p1", initial_inputs=(ArtifactType.IMAGE,), steps=(step,))
    execution = PipelineExecutor(CODE_VERSION).execute_document(
        spec, {"fake:tokens": _TokenModule()}, {ArtifactType.IMAGE: _image()},
        document_id="doc1",
    )
    # La durée est mesurée par l'exécuteur (source unique), les jetons remontent
    # du module ; les deux sont fusionnés dans le même ResourceUsage.
    assert execution.usage.duration_seconds is not None
    assert execution.usage.duration_seconds >= 0.0
    assert execution.usage.tokens_in == 120
    assert execution.usage.tokens_out == 30


def test_usage_sums_across_steps() -> None:
    step2 = PipelineStep(
        id="llm",
        kind="post_correction",
        adapter_name="fake:upper",
        input_types=(ArtifactType.RAW_TEXT,),
        output_types=(ArtifactType.CORRECTED_TEXT,),
        inputs_from={ArtifactType.RAW_TEXT: "ocr"},
    )
    step1 = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="fake:tokens",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    spec = PipelineSpec(
        name="p1", initial_inputs=(ArtifactType.IMAGE,), steps=(step1, step2)
    )
    execution = PipelineExecutor(CODE_VERSION).execute_document(
        spec,
        {"fake:tokens": _TokenModule(), "fake:upper": _UpperModule()},
        {ArtifactType.IMAGE: _image()},
        document_id="doc1",
    )
    # Étape sans jetons (module non-LLM) : les compteurs restent ceux de l'étape
    # LLM ; la durée cumule les deux étapes.
    assert execution.usage.tokens_in == 120
    assert execution.usage.tokens_out == 30
    assert execution.usage.duration_seconds is not None


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (AdapterStepError("le moteur a levé"), "engine"),
        # ``DeadlineExceeded`` hérite d'``AdapterStepError`` : une unité arrêtée
        # à expiration n'est pas un moteur en panne.
        (DeadlineExceeded("délai"), "cancelled"),
        (PipelineStepError("entrée introuvable"), "unsupported"),
    ],
)
def test_failure_reason_is_read_on_the_error_class(
    error: CinocError, reason: str
) -> None:
    assert isinstance(error, UNIT_FAILURES)
    assert failure_reason(error) == reason


def test_run_cancellation_is_not_a_unit_failure() -> None:
    # L'annulation arrête le run entier : elle n'est jamais l'issue d'une unité.
    assert not isinstance(RunCancelledError("stop"), UNIT_FAILURES)


def test_document_execution_outcome_invariants() -> None:
    failed = DocumentExecution.failed("engine", "boom")
    assert (failed.outcome, failed.reason) == ("failed", "engine")
    assert failed.message == "boom"
    assert dict(failed.artifacts) == {}
    assert dict(failed.by_step) == {}
    assert DocumentExecution().outcome == "ok"
    with pytest.raises(CinocError):
        DocumentExecution(outcome="failed")
    with pytest.raises(CinocError):
        DocumentExecution(reason="engine")
    with pytest.raises(CinocError):
        DocumentExecution(
            by_step={"ocr": {ArtifactType.IMAGE: _image()}},
            outcome="failed",
            reason="engine",
        )


class _OtherEchoModule(_EchoModule):
    """Second OCR : même type de sortie que ``_EchoModule``, autre contenu."""

    name = "fake:echo2"

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri="mem://raw2",
                )
            },
            usage=ResourceUsage(tokens_in=7, tokens_out=3),
        )


def _two_ocr_execution() -> DocumentExecution:
    spec = PipelineSpec(
        name="p1",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr1",
                kind="ocr",
                adapter_name="fake:tokens",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
            PipelineStep(
                id="ocr2",
                kind="ocr",
                adapter_name="fake:echo2",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
        ),
    )
    return PipelineExecutor(CODE_VERSION).execute_document(
        spec,
        {"fake:tokens": _TokenModule(), "fake:echo2": _OtherEchoModule()},
        {ArtifactType.IMAGE: _image()},
        document_id="doc1",
    )


def test_two_steps_of_the_same_type_both_stay_observable() -> None:
    """Le défaut d'origine : deux étapes de même type s'écrasaient dans le pool,
    seul objet rendu. ``by_step`` les garde toutes deux, dans l'ordre."""
    execution = _two_ocr_execution()

    assert list(execution.by_step) == [INITIAL_STEP_ID, "ocr1", "ocr2"]
    assert execution.by_step["ocr1"][ArtifactType.RAW_TEXT].uri == "mem://raw"
    assert execution.by_step["ocr2"][ArtifactType.RAW_TEXT].uri == "mem://raw2"
    assert execution.by_step[INITIAL_STEP_ID] == {ArtifactType.IMAGE: _image()}
    # Le pool se **déduit** : dernier artefact par type, entrées initiales comprises.
    assert execution.artifacts[ArtifactType.RAW_TEXT].uri == "mem://raw2"
    assert execution.artifacts[ArtifactType.IMAGE] == _image()


def test_usage_is_kept_per_step_and_the_total_derives_from_it() -> None:
    execution = _two_ocr_execution()

    assert list(execution.step_usage) == ["ocr1", "ocr2"]
    assert execution.step_usage["ocr1"].tokens_in == 120
    assert execution.step_usage["ocr2"].tokens_in == 7
    assert execution.usage.tokens_in == 127
    assert execution.usage.tokens_out == 33
    durations = [u.duration_seconds for u in execution.step_usage.values()]
    assert all(d is not None for d in durations)
    assert execution.usage.duration_seconds == pytest.approx(
        sum(d for d in durations if d is not None)
    )


class _CutModule(_EchoModule):
    """Comme ``_EchoModule``, mais sa sortie est coupée (plafond de jetons)."""

    name = "fake:cut"

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        output = super().execute(inputs, params, context, control)
        return StepOutput(artifacts=output.artifacts, truncation="plafond atteint")


def test_a_cut_step_marks_the_unit_truncated_and_keeps_its_output() -> None:
    """P5e 2 : la coupure est une issue d'unité, produite ici, pas au rapport.

    L'unité **garde** ses sorties (une sortie coupée est une sortie réelle, qui
    sera notée) et le message nomme l'étape — c'est ce qu'il faut pour savoir
    laquelle relever.
    """
    step = PipelineStep(
        id="vlm",
        kind="ocr",
        adapter_name="fake:cut",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    spec = PipelineSpec(name="p", initial_inputs=(ArtifactType.IMAGE,), steps=(step,))
    execution = PipelineExecutor(CODE_VERSION).execute_document(
        spec, {"fake:cut": _CutModule()}, {ArtifactType.IMAGE: _image()},
        document_id="doc1",
    )
    assert execution.outcome == "truncated"
    assert execution.reason is None
    assert execution.message == "étape 'vlm' : plafond atteint"
    assert ArtifactType.RAW_TEXT in execution.artifacts


def test_a_complete_run_stays_ok() -> None:
    spec = PipelineSpec(
        name="p1", initial_inputs=(ArtifactType.IMAGE,), steps=(_ocr_step(),)
    )
    execution = PipelineExecutor(CODE_VERSION).execute_document(
        spec, {"fake:echo": _EchoModule()}, {ArtifactType.IMAGE: _image()},
        document_id="doc1",
    )
    assert (execution.outcome, execution.message) == ("ok", None)
