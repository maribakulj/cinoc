"""Runner parallèle (couche 6) : déterminisme (workers 1 vs N), isolation
d'échec sous threads, progression sans doublon, résolution des workers.

L'invariant clé (§12) : exécuter en parallèle ne change **rien** au résultat —
l'assemblage du ``RunResult`` est ordonné par le spec, pas par l'ordre
d'achèvement des threads. On le prouve en comparant la substance métrique d'un
run ``max_workers=1`` à celle d'un run ``max_workers=4`` (manifeste et durées
``usage`` exclus : ce sont des canaux **environnementaux**, comme les timestamps).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.orchestrator import _resolve_workers
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec

_TEXT_VIEW = EvaluationView(
    name="text",
    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
    metric_names=("cer",),
)


def _pipeline(name: str, label: str) -> PipelineSpec:
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name=f"precomputed:{label}",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    return PipelineSpec(name=name, initial_inputs=(ArtifactType.IMAGE,), steps=(step,))


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def _document(tmp_path: Path, index: int) -> DocumentRef:
    doc_id = f"doc{index:03d}"
    # OCR pré-calculé (déterministe, aucun binaire) lu à côté de l'image.
    (tmp_path / f"{doc_id}.engA.txt").write_text(f"abx{index}", encoding="utf-8")
    (tmp_path / f"{doc_id}.engB.txt").write_text(f"aby{index}", encoding="utf-8")
    (tmp_path / f"{doc_id}.gt.txt").write_text(f"abc{index}", encoding="utf-8")
    return DocumentRef(
        id=doc_id,
        image_uri=str(tmp_path / f"{doc_id}.png"),
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / f"{doc_id}.gt.txt")
            ),
        ),
    )


def _spec(tmp_path: Path, n_docs: int) -> RunSpec:
    documents = tuple(_document(tmp_path, i) for i in range(n_docs))
    return RunSpec(
        run_id="fixed-run",  # identité figée : seuls les timestamps varient
        corpus=CorpusSpec(name="c", documents=documents),
        pipelines=(_pipeline("A", "engA"), _pipeline("B", "engB")),
        evaluation=EvaluationSpec(views=(_TEXT_VIEW,)),
        adapter_kwargs={
            "precomputed:engA": {"source_label": "engA"},
            "precomputed:engB": {"source_label": "engB"},
        },
    )


def _substance(result: object) -> object:
    # Métriques + documents + croisements. On exclut les canaux
    # **environnementaux** (non déterministes par nature) : le manifeste
    # (timestamps), le canal ``usage`` (durées wall-clock) et l'analyse
    # ``economics`` (coût = f(durée machine) → fronts de Pareto qui basculent
    # sur le bruit). Ce qui reste est la substance métrique déterministe.
    dump = result.model_dump(mode="json", exclude={"manifest", "usage"})  # type: ignore[attr-defined]
    dump["analyses"] = [
        a for a in dump["analyses"] if a.get("payload", {}).get("kind") != "economics"
    ]
    return dump


def test_parallel_result_is_byte_identical_to_sequential(tmp_path: Path) -> None:
    spec = _spec(tmp_path, 8)
    seq = run(spec, registry=_registry(), code_version="1.0", max_workers=1)
    par = run(spec, registry=_registry(), code_version="1.0", max_workers=4)
    assert _substance(seq) == _substance(par)


def test_usage_records_ordered_by_spec_not_completion(tmp_path: Path) -> None:
    # Les unités s'achèvent dans un ordre quelconque, mais l'assemblage suit le
    # spec : pipeline-majeur, puis document — déterministe.
    par = run(
        _spec(tmp_path, 6), registry=_registry(), code_version="1.0", max_workers=4
    )
    order = [(u.pipeline, u.document_id) for u in par.usage]
    expected = [(p, f"doc{i:03d}") for p in ("A", "B") for i in range(6)]
    assert order == expected


def test_progress_ticks_once_per_unit(tmp_path: Path) -> None:
    calls: list[tuple[int, int]] = []
    run(
        _spec(tmp_path, 5),
        registry=_registry(),
        code_version="1.0",
        max_workers=4,
        on_progress=lambda unit: calls.append((unit.done, unit.total)),
    )
    total = 2 * 5
    assert len(calls) == total
    assert all(t == total for _, t in calls)
    # Compteur thread-safe : chaque valeur de 1..total émise exactement une fois.
    assert sorted(done for done, _ in calls) == list(range(1, total + 1))


def test_failure_isolation_under_parallel(tmp_path: Path) -> None:
    # Un pipeline dont la source pré-calculée est absente échoue par unité
    # (AdapterStepError) sans abattre le run, même sous threads.
    documents = []
    for i in range(4):
        doc_id = f"doc{i:03d}"
        (tmp_path / f"{doc_id}.ok.txt").write_text("abc", encoding="utf-8")
        (tmp_path / f"{doc_id}.gt.txt").write_text("abc", encoding="utf-8")
        documents.append(
            DocumentRef(
                id=doc_id,
                image_uri=str(tmp_path / f"{doc_id}.png"),
                ground_truths=(
                    GroundTruthRef(
                        type=ArtifactType.RAW_TEXT,
                        uri=str(tmp_path / f"{doc_id}.gt.txt"),
                    ),
                ),
            )
        )
    spec = RunSpec(
        run_id="x",
        corpus=CorpusSpec(name="c", documents=tuple(documents)),
        pipelines=(_pipeline("ok", "ok"), _pipeline("ko", "absent")),
        evaluation=EvaluationSpec(views=(_TEXT_VIEW,)),
        adapter_kwargs={
            "precomputed:ok": {"source_label": "ok"},
            "precomputed:absent": {"source_label": "absent"},  # source manquante
        },
    )
    result = run(spec, registry=_registry(), code_version="1.0", max_workers=4)
    by_name = {p.pipeline: p for p in result.pipelines}
    assert by_name["ok"].aggregate[0].value == pytest.approx(0.0)  # scoré, parfait
    ko = by_name.get("ko")
    assert ko is None or not ko.aggregate or ko.aggregate[0].value is None


def test_resolve_workers_clamps_and_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CINOC_MAX_WORKERS", raising=False)
    assert _resolve_workers(4, 10) == 4
    assert _resolve_workers(4, 2) == 2  # borné au nombre d'unités en attente
    assert _resolve_workers(0, 10) >= 1  # invalide → défaut CPU, jamais < 1
    assert _resolve_workers(None, 1) == 1  # une seule unité → un seul worker
    monkeypatch.setenv("CINOC_MAX_WORKERS", "3")
    assert _resolve_workers(None, 10) == 3  # variable d'environnement respectée
    monkeypatch.setenv("CINOC_MAX_WORKERS", "bogus")
    assert _resolve_workers(None, 10) >= 1  # env invalide → défaut, pas de crash
