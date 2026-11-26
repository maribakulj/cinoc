"""L'issue d'une unité est produite par l'exécution et transportée (P5e 1, A3).

Contre-exemple reproduit sur ``examples/`` (D-261) : pero privé de sa sortie
pour ``folio_002`` obtenait **CER 0,0** sur 4 documents, contre 0,0145 quand il
répond et 0,1667 s'il rend une page vide — **échouer rapportait plus que
répondre**, et rien dans ``RunResult`` ne distinguait l'échec d'une absence.

Ces tests rejouent l'exemple livré sur une **copie** (jamais ``examples/``) et
verrouillent l'arbitrage A3 : l'unité en échec est exclue de la moyenne **et
affichée** (« n notés / n attendus » + motif), à l'écran et dans le JSON ; avec
``failure_policy: max_error``, elle est notée à l'erreur maximale.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from cinoc.app import run
from cinoc.app.loader import load_run_spec
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.result import MetricScore, RunResult
from cinoc.interfaces.cli import main
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput
from cinoc.reports.renderer import default_report_renderer

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def _example_copy(tmp_path: Path, *, pero_folio_002: str | None) -> Path:
    """Copie de ``examples/`` ; ``None`` retire la sortie de pero pour folio_002."""
    target = tmp_path / "examples"
    shutil.copytree(EXAMPLES, target)
    sortie = target / "corpus" / "folio_002.pero.txt"
    if pero_folio_002 is None:
        sortie.unlink()
    else:
        sortie.write_text(pero_folio_002, encoding="utf-8")
    return target / "config.yaml"


def _run(config: Path, **evaluation: object) -> RunResult:
    spec = load_run_spec(config)
    if evaluation:
        spec = spec.model_copy(
            update={"evaluation": spec.evaluation.model_copy(update=evaluation)}
        )
    return run(spec, registry=_registry(), code_version="test", max_workers=1)


def _agg(result: RunResult, pipeline: str, metric: str = "cer") -> MetricScore:
    for entry in result.pipelines:
        if entry.pipeline == pipeline and entry.view == "text":
            return next(s for s in entry.aggregate if s.metric == metric)
    raise AssertionError(pipeline)


def _doc(result: RunResult, pipeline: str, document: str) -> MetricScore:
    for entry in result.documents:
        if (entry.pipeline, entry.document_id, entry.view) == (
            pipeline,
            document,
            "text",
        ):
            return next(s for s in entry.scores if s.metric == "cer")
    raise AssertionError(document)


def test_failed_unit_is_recorded_with_its_reason(tmp_path: Path) -> None:
    result = _run(_example_copy(tmp_path, pero_folio_002=None))

    failed = [u for u in result.usage if u.outcome == "failed"]
    assert [(u.pipeline, u.document_id, u.reason) for u in failed] == [
        ("pero", "folio_002", "engine")
    ]
    assert "folio_002.pero.txt" in (failed[0].message or "")
    # Chaque unité a sa ligne, en échec comprise : 2 pipelines × 5 documents.
    assert len(result.usage) == 10
    assert result.schema_version == 4


def test_exclude_policy_shows_scored_over_expected(tmp_path: Path) -> None:
    result = _run(_example_copy(tmp_path, pero_folio_002=None))

    pero = _agg(result, "pero")
    assert (pero.value, pero.support, pero.expected) == (0.0, 4, 5)
    tesseract = _agg(result, "tesseract")
    assert (tesseract.support, tesseract.expected) == (5, 5)
    assert _doc(result, "pero", "folio_002").value is None
    assert result.manifest.failure_policy == "exclude"


def test_json_written_by_the_cli_carries_support_and_reason(tmp_path: Path) -> None:
    config = _example_copy(tmp_path, pero_folio_002=None)
    sortie = tmp_path / "r.json"
    assert main(["run", str(config), "-o", str(tmp_path / "r.html"),
                 "--json", str(sortie)]) == 0
    data = json.loads(sortie.read_text(encoding="utf-8"))
    cer = next(
        s
        for p in data["pipelines"]
        if p["pipeline"] == "pero" and p["view"] == "text"
        for s in p["aggregate"]
        if s["metric"] == "cer"
    )
    assert (cer["support"], cer["expected"]) == (4, 5)
    (unit,) = [u for u in data["usage"] if u["outcome"] == "failed"]
    assert (unit["pipeline"], unit["document_id"], unit["reason"]) == (
        "pero",
        "folio_002",
        "engine",
    )


@pytest.mark.parametrize(
    ("lang", "title", "reason", "rule"),
    [
        ("fr", "Unités en échec", "moteur", "exclues de la moyenne"),
        ("en", "Failed units", "engine", "left out of the mean"),
    ],
)
def test_html_shows_scored_over_expected_and_the_reason(
    tmp_path: Path, lang: str, title: str, reason: str, rule: str
) -> None:
    result = _run(_example_copy(tmp_path, pero_folio_002=None))
    html = default_report_renderer().render(result, lang=lang)

    assert "4/5" in html
    assert title in html
    assert f"<strong>{reason}</strong>" in html
    assert rule in html
    assert "folio_002.pero.txt" in html


def test_nothing_is_marked_when_every_unit_succeeds(tmp_path: Path) -> None:
    result = _run(_example_copy(tmp_path, pero_folio_002="x"))
    assert all(u.outcome == "ok" for u in result.usage)
    assert all(
        s.support == s.expected for p in result.pipelines for s in p.aggregate
    )
    html = default_report_renderer().render(result)
    assert "Unités en échec" not in html


def test_max_error_scores_the_failure_like_an_empty_page(tmp_path: Path) -> None:
    """``max_error`` : le CER du document en échec vaut 1, pondéré par sa
    référence — exactement le CER d'une page rendue vide (0,1667 à l'agrégat)."""
    failed = _run(
        _example_copy(tmp_path / "a", pero_folio_002=None), failure_policy="max_error"
    )
    empty = _run(_example_copy(tmp_path / "b", pero_folio_002=""))

    pero = _agg(failed, "pero")
    assert (pero.support, pero.expected) == (5, 5)
    assert pero.value == pytest.approx(_agg(empty, "pero").value)
    assert pero.value == pytest.approx(0.1667, abs=1e-4)
    assert _doc(failed, "pero", "folio_002").value == 1.0
    assert failed.manifest.failure_policy == "max_error"
    html = default_report_renderer().render(failed)
    assert "erreur maximale" in html


def test_max_error_is_zero_for_a_higher_is_better_metric(tmp_path: Path) -> None:
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("char_accuracy",),
    )
    result = _run(
        _example_copy(tmp_path, pero_folio_002=None),
        views=(view,),
        failure_policy="max_error",
    )
    entry = next(
        d
        for d in result.documents
        if (d.pipeline, d.document_id) == ("pero", "folio_002")
    )
    assert entry.scores[0].value == 0.0
    assert entry.scores[0].support is not None and entry.scores[0].support > 0


def test_a_failure_without_ground_truth_is_not_expected(tmp_path: Path) -> None:
    """Un échec sur un document **sans** vérité terrain ne manque à aucune
    moyenne : la métrique ne l'aurait pas noté de toute façon."""
    (tmp_path / "a.eng.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "a.gt.txt").write_text("abcd", encoding="utf-8")
    documents = (
        DocumentRef(
            id="a",
            image_uri=str(tmp_path / "a.png"),
            ground_truths=(
                GroundTruthRef(
                    type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "a.gt.txt")
                ),
            ),
        ),
        DocumentRef(id="b", image_uri=str(tmp_path / "b.png")),  # ni GT ni sortie
    )
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="precomputed:eng",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    spec = RunSpec(
        corpus=CorpusSpec(name="c", documents=documents),
        pipelines=(
            PipelineSpec(
                name="eng", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
            ),
        ),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="text",
                    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
                    metric_names=("cer",),
                ),
            )
        ),
        adapter_kwargs={"precomputed:eng": {"source_label": "eng"}},
    )
    result = run(spec, registry=_registry(), code_version="test")
    assert [u.outcome for u in result.usage] == ["ok", "failed"]
    cer = result.pipelines[0].aggregate[0]
    assert (cer.support, cer.expected) == (1, 1)


class _LeakyEngine:
    """Moteur qui cite son jeton et son workspace dans son erreur."""

    name = "leaky"
    version = "1"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def __init__(self, token: str) -> None:
        self._token = token

    def execute(
        self,
        inputs: Mapping[ArtifactType, Artifact],
        params: Mapping[str, object],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        raise AdapterStepError(
            f"GET https://api.example/ocr?token={self._token} a échoué "
            f"(trace dans {context.workspace_uri}/dump.json)"
        )


def _leaky_spec(tmp_path: Path, secret: str) -> RunSpec:
    (tmp_path / "a.gt.txt").write_text("abcd", encoding="utf-8")
    document = DocumentRef(
        id="a",
        image_uri=str(tmp_path / "a.png"),
        ground_truths=(
            GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "a.gt.txt")),
        ),
    )
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="leaky",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    return RunSpec(
        run_id="fixe",
        corpus=CorpusSpec(name="c", documents=(document,)),
        pipelines=(
            PipelineSpec(
                name="eng", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
            ),
        ),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="text",
                    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
                    metric_names=("cer",),
                ),
            )
        ),
        adapter_kwargs={"leaky": {"token": secret}},
    )


def test_failure_message_carries_no_secret_and_no_temporary_path(
    tmp_path: Path,
) -> None:
    secret = "sk_NEPASFUIR_42"
    registry = ModuleRegistry()
    registry.register_builder(
        "leaky", lambda kwargs: _LeakyEngine(str(kwargs["token"]))  # type: ignore[arg-type,return-value]
    )
    spec = _leaky_spec(tmp_path, secret)
    first = run(spec, registry=registry, code_version="test")
    second = run(spec, registry=registry, code_version="test")

    (unit,) = first.usage
    assert unit.outcome == "failed" and unit.reason == "engine"
    message = unit.message or ""
    assert secret not in message and "token=<secret>" in message
    assert "<workspace>/pipeline0/dump.json" in message
    assert "cinoc-run-" not in message
    assert secret not in first.model_dump_json()
    # Le message ne dépend pas du dossier temporaire : l'issue est déterministe.
    assert first.usage == second.usage


def test_statistical_tests_use_complete_cases_and_say_so(tmp_path: Path) -> None:
    """Le support d'un test apparié n'est pas celui d'un agrégat : sous
    ``exclude``, le document en échec d'un moteur sort des **cas complets** de
    tous (7 → 6), alors que l'autre moteur reste noté sur 7. Les trois nombres
    sont dans le résultat, chacun à sa place."""
    from cinoc.evaluation.analysis import InferencePayload

    documents = []
    for i in range(7):
        (tmp_path / f"d{i}.gt.txt").write_text("abcdefgh", encoding="utf-8")
        (tmp_path / f"d{i}.a.txt").write_text("abcdefgx"[: 8 - i % 3], encoding="utf-8")
        if i != 3:  # b n'a pas de sortie pour d3 : unité en échec
            (tmp_path / f"d{i}.b.txt").write_text("abcdxfgh", encoding="utf-8")
        documents.append(
            DocumentRef(
                id=f"d{i}",
                image_uri=str(tmp_path / f"d{i}.png"),
                ground_truths=(
                    GroundTruthRef(
                        type=ArtifactType.RAW_TEXT, uri=str(tmp_path / f"d{i}.gt.txt")
                    ),
                ),
            )
        )

    def pipeline(label: str) -> PipelineSpec:
        step = PipelineStep(
            id="ocr",
            kind="ocr",
            adapter_name=f"precomputed:{label}",
            input_types=(ArtifactType.IMAGE,),
            output_types=(ArtifactType.RAW_TEXT,),
        )
        return PipelineSpec(
            name=label, initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
        )

    spec = RunSpec(
        corpus=CorpusSpec(name="c", documents=tuple(documents)),
        pipelines=(pipeline("a"), pipeline("b")),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="text",
                    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
                    metric_names=("cer",),
                ),
            ),
            analyses=("inference",),
        ),
        adapter_kwargs={
            "precomputed:a": {"source_label": "a"},
            "precomputed:b": {"source_label": "b"},
        },
    )
    result = run(spec, registry=_registry(), code_version="test")

    by_name = {p.pipeline: p.aggregate[0] for p in result.pipelines}
    assert (by_name["a"].support, by_name["a"].expected) == (7, 7)
    assert (by_name["b"].support, by_name["b"].expected) == (6, 7)
    (payload,) = [
        a.payload for a in result.analyses if isinstance(a.payload, InferencePayload)
    ]
    assert payload.n_documents == 6  # cas complets
    assert {i.pipeline: i.n_documents for i in payload.intervals} == {"a": 7, "b": 6}
    (significance,) = result.cross_engine
    assert significance.support == 6


def test_redacted_workspace_path_is_the_same_on_every_platform() -> None:
    """Sous Windows le chemin sous le workspace garde ``\\`` : le message
    nettoyé doit être identique à celui d'un run Linux (déterminisme)."""
    from cinoc.app.orchestrator import _redact

    windows = _redact(
        r"échec (trace dans D:\tmp\cinoc-run-x\pipeline0\dump.json)",
        (),
        r"D:\tmp\cinoc-run-x",
    )
    linux = _redact(
        "échec (trace dans /tmp/cinoc-run-x/pipeline0/dump.json)",
        (),
        "/tmp/cinoc-run-x",
    )
    assert windows == linux == "échec (trace dans <workspace>/pipeline0/dump.json)"
