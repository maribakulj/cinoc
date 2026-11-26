"""Critère de P5f 3 : un run cloud rejoué **hors ligne** depuis ses sidecars
donne les mêmes métriques.

Run 1 : huit pipelines distants (Mistral OCR, Azure DI, Google Vision, les
quatre VLM en zero-shot, une chaîne Mistral OCR → OpenAI), deux pages, servis
par cassette (``tests/adapters/_native_fakes.py`` : seul le transport est faux).
Le run garde ses sorties dans un dossier d'artefacts (``--resume-dir``).

Run 2 : **plus de réseau ni de SDK**. Chaque texte est reconstruit depuis le seul
sidecar ``NATIVE_JSON`` du run 1, par la fonction de conversion de l'adaptateur
qui l'a produit — ``_completion_from_*`` et les extracteurs, pas une copie —,
puis noté par ``precomputed``. Les métriques sont égales au run 1, page coupée
comprise (une unité ``truncated`` est notée sur sa sortie réelle).

Le sidecar traverse aussi le reste du run : ``by_step``, le puits d'artefacts
(lisible avant le nettoyage du workspace), le cache de reprise (persisté puis
rechargé) ; il n'entre pas dans le ``RunResult``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.llm.anthropic import _completion_from_message
from cinoc.adapters.llm.mistral import _completion_from_chat as mistral_completion
from cinoc.adapters.llm.ollama import _completion_from_chat as ollama_completion
from cinoc.adapters.llm.openai import _completion_from_chat as openai_completion
from cinoc.adapters.ocr.azure_di import _extract_text as azure_text
from cinoc.adapters.ocr.google_vision import _extract_text as google_text
from cinoc.adapters.ocr.mistral_ocr import _text_from_response
from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.orchestrator import PipelineOutputs
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.app.resume import ResumeStore, declared_inputs, unit_key
from cinoc.app.run_manifest import module_identities
from cinoc.domain.artifacts import ArtifactType, latest_by_type
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run import RunManifest
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.result import RunResult
from tests.adapters._native_fakes import (
    SECRET,
    cut_network,
    install_fake_http,
    install_fake_sdks,
    set_keys,
    wire,
)

_DOCS = ("folio_a", "folio_b")
_GT = (
    "Le Petit Journal, 12 mars 1894. — On annonce de Boulogne-sur-Mer "
    "qu'une partie de la falaise s'est effondrée hier soir, emportant "
    "deux maisons."
)

def _ocr(kind: str, **params: str) -> RecipeEntry:
    return RecipeEntry(
        recipe="ocr_simple", choices={"ocr": kind}, params={"ocr": params}
    )


def _vlm(kind: str, model: str) -> RecipeEntry:
    return RecipeEntry(
        recipe="vlm_seul", choices={"vlm": kind}, params={"vlm": {"model": model}}
    )


_ENTRIES = (
    _ocr("mistral_ocr", model="m"),
    _ocr("azure_di"),
    _ocr("google_vision"),
    _vlm("openai", "gpt-4o-mini"),
    _vlm("anthropic", "claude-haiku-4-5"),
    _vlm("mistral", "pixtral-12b"),
    _vlm("ollama", "qwen2.5vl:3b"),
    RecipeEntry(
        recipe="ocr_puis_llm",
        choices={"ocr": "mistral_ocr", "correction": "openai"},
        params={"ocr": {"model": "m"}, "correction": {"model": "gpt-4o-mini"}},
    ),
)

#: Réponses dans l'ordre où le run séquentiel les demande (pipeline × page ×
#: étape) : la chaîne, dernière, rappelle Mistral OCR puis OpenAI. Les pages
#: ``folio_b`` des VLM sont **coupées** au plafond de jetons.
_QUEUES: dict[str, tuple[tuple[str, str], ...]] = {
    "mistral_ocr": (("ocr", "folio_a"), ("ocr", "folio_b")) * 2,
    "azure_di": (("ocr", "folio_a"), ("ocr", "folio_b")),
    "google_vision": (("ocr", "folio_a"), ("ocr", "folio_b")),
    "openai": (("llm", "stop"), ("llm", "length"), ("llm", "stop"), ("llm", "stop")),
    "anthropic": (("llm", "end_turn"), ("llm", "max_tokens")),
    "mistral": (("llm", "stop"), ("llm", "length")),
    "ollama": (("llm", "stop"), ("llm", "length")),
}

#: Le sidecar → le texte, **par la fonction de l'adaptateur** qui l'a produit.
_READ: dict[str, Callable[[Any], str]] = {
    "mistral_ocr": _text_from_response,
    "azure_di": azure_text,
    "google_vision": google_text,
    "openai": lambda native: openai_completion(native).text,
    "anthropic": lambda native: _completion_from_message(native).text,
    "mistral": lambda native: mistral_completion(native).text,
    "ollama": lambda native: ollama_completion(native, "qwen2.5vl:3b").text,
}


def _queues() -> dict[str, Callable[[], dict[str, Any]]]:
    def serve(provider: str) -> Callable[[], dict[str, Any]]:
        file: Iterator[tuple[str, str]] = iter(_QUEUES[provider])

        def nxt() -> dict[str, Any]:
            family, scenario = next(file)
            return wire(family, provider, scenario)

        return nxt

    return {provider: serve(provider) for provider in _QUEUES}


def _corpus(folder: Path) -> CorpusSpec:
    folder.mkdir(parents=True, exist_ok=True)
    documents = []
    for doc in _DOCS:
        image = folder / f"{doc}.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + doc.encode())
        gt = folder / f"{doc}.gt.txt"
        gt.write_text(_GT, encoding="utf-8")
        documents.append(
            DocumentRef(
                id=doc,
                image_uri=str(image),
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            )
        )
    return CorpusSpec(name="petit-journal", documents=tuple(documents))


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


class _Run1:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        set_keys(monkeypatch)
        queues = _queues()
        install_fake_sdks(monkeypatch, queues)
        install_fake_http(monkeypatch, queues)
        self.archive = tmp_path / "archive"
        self.spec = plan_recipe_run(
            _corpus(tmp_path / "corpus"), _ENTRIES, run_id="s8"
        )
        self.sidecars_in_sink: dict[tuple[str, str, str], bytes] = {}
        self.result = run(
            self.spec,
            registry=_registry(),
            code_version="1.0",
            max_workers=1,
            resume_store=ResumeStore(self.archive),
            artifact_sink=self._sink,
        )

    def _sink(self, outputs: PipelineOutputs, _manifest: RunManifest) -> None:
        """Un puits lit le sidecar **avant** le nettoyage du workspace."""
        for pipeline, per_document in outputs.items():
            for document, by_step in per_document.items():
                for step, produits in by_step.items():
                    native = produits.get(ArtifactType.NATIVE_JSON)
                    if native is not None:
                        self.sidecars_in_sink[(pipeline, document, step)] = Path(
                            native.uri or ""
                        ).read_bytes()

    def archived_steps(self, pipeline: PipelineSpec, doc: DocumentRef) -> list[Any]:
        registry = _registry()
        modules = {
            step.adapter_name: registry.build(
                step.adapter_name, self.spec.adapter_kwargs.get(step.adapter_name, {})
            )
            for step in pipeline.steps
        }
        key = unit_key(
            pipeline=pipeline,
            identities=module_identities(self.spec, modules),
            document=doc,
            inputs=declared_inputs(pipeline, modules, doc),
        )
        assert key is not None
        index = json.loads((self.archive / key / "index.json").read_bytes())
        steps: list[Any] = index["steps"]
        # Un fichier archivé est nommé relativement à son unité (format 3).
        for entry in steps:
            for artifact in entry["artifacts"].values():
                if artifact.get("uri") and not Path(artifact["uri"]).is_absolute():
                    artifact["uri"] = str(self.archive / key / artifact["uri"])
        return steps


@pytest.fixture
def run1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Run1:
    return _Run1(tmp_path, monkeypatch)


def _replay_offline(run1: _Run1, folder: Path) -> RunSpec:
    """Run 2 : textes reconstruits des seuls sidecars, notés par ``precomputed``."""
    corpus = _corpus(folder)
    pipelines: list[PipelineSpec] = []
    kwargs: dict[str, dict[str, str | int | float | bool]] = {}
    for index, pipeline in enumerate(run1.spec.pipelines):
        label = f"r{index}"
        last = pipeline.steps[-1]
        kind = last.adapter_name.split(":", 1)[0]
        for doc in run1.spec.corpus.documents:
            (entry,) = (
                e for e in run1.archived_steps(pipeline, doc) if e["step"] == last.id
            )
            sidecar = Path(entry["artifacts"]["native_json"]["uri"])
            texte = _READ[kind](json.loads(sidecar.read_bytes()))
            (folder / f"{doc.id}.{label}.txt").write_text(texte, encoding="utf-8")
        name = f"precomputed:{label}"
        kwargs[name] = {"source_label": label}
        pipelines.append(
            PipelineSpec(
                name=pipeline.name,
                initial_inputs=(ArtifactType.IMAGE,),
                steps=(
                    PipelineStep(
                        id="replay",
                        kind="ocr",
                        adapter_name=name,
                        input_types=(ArtifactType.IMAGE,),
                        output_types=(ArtifactType.RAW_TEXT,),
                    ),
                ),
            )
        )
    return RunSpec(
        corpus=corpus,
        pipelines=tuple(pipelines),
        evaluation=run1.spec.evaluation,
        adapter_kwargs=kwargs,
    )


def _scores(result: RunResult) -> dict[str, Any]:
    return {
        "aggregates": {
            (p.pipeline, p.view): [s.model_dump() for s in p.aggregate]
            for p in result.pipelines
        },
        "documents": {
            (d.pipeline, d.view, d.document_id): [s.model_dump() for s in d.scores]
            for d in result.documents
        },
        "cross_engine": [s.model_dump() for s in result.cross_engine],
    }


def test_a_cloud_run_replayed_offline_from_its_sidecars_gives_the_same_metrics(
    run1: _Run1, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cut_network(monkeypatch)
    replay = _replay_offline(run1, tmp_path / "replay")
    result2 = run(replay, registry=_registry(), code_version="1.0", max_workers=1)

    assert _scores(result2) == _scores(run1.result)
    # Pas un accord par vacuité : des scores réels, différents d'un moteur à
    # l'autre, et les pages coupées sont notées (2/2) sur leur sortie réelle.
    cer = {
        p.pipeline: next(s for s in p.aggregate if s.metric == "cer")
        for p in run1.result.pipelines
    }
    assert len(cer) == 8 and all(s.value is not None for s in cer.values())
    assert len({round(s.value or 0, 6) for s in cer.values()}) > 3
    assert {s.support for s in cer.values()} == {2}
    assert [u.outcome for u in run1.result.usage].count("truncated") == 4


def test_the_sidecar_lives_in_the_artifacts_dir_and_nowhere_in_the_run_result(
    run1: _Run1,
) -> None:
    manifest = run1.result.manifest
    assert manifest.artifacts_dir == str(run1.archive)
    archived = sorted(p.name for p in run1.archive.rglob("*.native_json.json"))
    # Une réponse par appel utile : 7 pipelines × 2 pages + la chaîne × 2 étapes × 2.
    assert len(archived) == 7 * 2 + 2 * 2
    assert archived.count("ocr.native_json.json") == 4 * 2
    assert archived.count("correction.native_json.json") == 2
    dumped = run1.result.model_dump_json()
    assert "native_json" not in dumped
    assert "analyzeResult" not in dumped and "fullTextAnnotation" not in dumped
    for path in run1.archive.rglob("*"):
        if path.is_file():
            assert SECRET not in path.read_text("utf-8", "replace"), path
    assert SECRET not in dumped


def test_the_sidecar_travels_through_by_step_and_the_artifact_sink(run1: _Run1) -> None:
    """La chaîne garde la réponse de **chaque** étape ; le puits les lit toutes,
    et ce qu'il lit est ce que l'archive a gardé."""
    chaine = run1.spec.pipelines[-1]
    for doc in run1.spec.corpus.documents:
        for step in ("ocr", "correction"):
            lu = run1.sidecars_in_sink[(chaine.name, doc.id, step)]
            (entry,) = (
                e for e in run1.archived_steps(chaine, doc) if e["step"] == step
            )
            assert Path(entry["artifacts"]["native_json"]["uri"]).read_bytes() == lu
    assert len(run1.sidecars_in_sink) == 18


def test_the_resume_cache_reloads_the_sidecar_without_any_call(
    run1: _Run1, monkeypatch: pytest.MonkeyPatch
) -> None:
    cut_network(monkeypatch)
    captured: dict[tuple[str, str], Any] = {}

    def sink(outputs: PipelineOutputs, _manifest: RunManifest) -> None:
        for pipeline, per_document in outputs.items():
            for document, by_step in per_document.items():
                captured[(pipeline, document)] = by_step

    result = run(
        run1.spec,
        registry=_registry(),
        code_version="1.0",
        max_workers=1,
        resume_store=ResumeStore(run1.archive),
        artifact_sink=sink,
    )
    assert _scores(result) == _scores(run1.result)
    for (pipeline, document), by_step in captured.items():
        native = latest_by_type(by_step)[ArtifactType.NATIVE_JSON]
        assert native.uri is not None and Path(native.uri).is_relative_to(run1.archive)
        assert (pipeline, document, native.produced_by_step) in run1.sidecars_in_sink


def test_a_missing_sidecar_file_re_executes_the_unit(
    run1: _Run1, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cache ne rend pas une unité à qui manque sa réponse native : elle est
    incomplète, donc ré-exécutée (ici : refusée, le réseau est coupé)."""
    pipeline, doc = run1.spec.pipelines[0], run1.spec.corpus.documents[0]
    (entry,) = (e for e in run1.archived_steps(pipeline, doc) if e["step"] == "ocr")
    Path(entry["artifacts"]["native_json"]["uri"]).unlink()
    cut_network(monkeypatch)
    result = run(
        run1.spec,
        registry=_registry(),
        code_version="1.0",
        max_workers=1,
        resume_store=ResumeStore(run1.archive),
    )
    outcomes = {(u.pipeline, u.document_id): u.outcome for u in result.usage}
    assert outcomes[(pipeline.name, doc.id)] == "failed"
    assert list(outcomes.values()).count("failed") == 1
