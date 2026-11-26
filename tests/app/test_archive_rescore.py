"""Critère de P5f 2b : une archive se **re-note** sans réexécuter (S9, D-279).

Run 1 : trois pipelines sur deux pages — un VLM OpenAI et Mistral OCR servis par
cassette (``tests/adapters/_native_fakes.py``, seul le transport est faux), et
un OCR « local » factice qui enveloppe un binaire. L'archive (``--resume-dir``)
garde les sorties, les sidecars, les issues et les binaires.

Run 2 : la version du **code** change (une métrique corrigée) et la vue gagne
deux métriques. Plus de réseau ni de SDK, et l'OCR local est remplacé par un
module de même identité qui **lève** s'il est appelé : la relecture
(``offline=True``) re-note tout, à l'identique pour les métriques inchangées.

À l'inverse, une montée de version d'un **module du pipeline** ou de son
**binaire** invalide bien l'unité : ré-exécutée en reprise normale, refusée
(« archive incomplète ») hors ligne.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.orchestrator import ArchiveIncompleteError
from cinoc.app.resume import ResumeStore
from cinoc.app.run_planning import Competitor, plan_benchmark_run
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.economics import economics_analysis, load_pricing
from cinoc.evaluation.result import RunResult
from cinoc.pipeline.types import StepOutput
from tests.adapters._native_fakes import (
    cut_network,
    install_fake_http,
    install_fake_sdks,
    set_keys,
    wire,
)

_DOCS = ("folio_a", "folio_b")
_GT = "Le Petit Journal, 12 mars 1894. On annonce de Boulogne-sur-Mer."


@dataclass
class _Local:
    """État de l'OCR local factice : sa version, son binaire, ses appels."""

    version: str = "1.0"
    binary: str = "5.3.0"
    explode: bool = False
    fail: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)


class _LocalOCR:
    """OCR local factice : enveloppe un « binaire », compte ses appels, et lève
    s'il est appelé alors qu'il ne devrait pas l'être (``explode``)."""

    name = "localocr:fra"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def __init__(self, state: _Local) -> None:
        self._state = state

    @property
    def version(self) -> str:
        return self._state.version

    def system_binaries(self) -> dict[str, str]:
        return {"localocr": self._state.binary}

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        if self._state.explode:
            raise AssertionError("module de pipeline appelé pendant une relecture")
        self._state.calls.append(context.document_id)
        if context.document_id in self._state.fail:
            raise AdapterStepError("localocr : page illisible")
        text = _GT.replace("Journal", "Journa1")
        path = Path(context.workspace_uri) / f"{context.document_id}.local.txt"
        path.write_text(text, encoding="utf-8")
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:localocr:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(path),
                    content_hash=compute_content_hash(text.encode("utf-8")),
                )
            }
        )


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


def _spec(tmp_path: Path) -> RunSpec:
    planned = plan_benchmark_run(
        (
            Competitor(engine="openai", mode="zero_shot", model="gpt-4o-mini"),
            Competitor(engine="mistral_ocr"),
        ),
        _corpus(tmp_path / "corpus"),
        "s9",
    )(tmp_path)
    local = PipelineSpec(
        name="local",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr",
                kind="ocr",
                adapter_name="localocr:fra",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
        ),
    )
    return planned.model_copy(
        update={
            "pipelines": (*planned.pipelines, local),
            "adapter_kwargs": {**planned.adapter_kwargs, "localocr:fra": {"psm": 6}},
        }
    )


def _registry(state: _Local) -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    registry.register_builder("localocr", lambda _kwargs: _LocalOCR(state))
    return registry


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le réseau des fournisseurs, servi par cassette (file par fournisseur)."""
    set_keys(monkeypatch)
    files: dict[str, Iterator[tuple[str, str]]] = {
        "openai": iter((("llm", "stop"), ("llm", "length"))),
        "mistral_ocr": iter((("ocr", "folio_a"), ("ocr", "folio_b"))),
    }

    def serve(provider: str) -> Callable[[], dict[str, Any]]:
        def nxt() -> dict[str, Any]:
            family, scenario = next(files[provider])
            return wire(family, provider, scenario)

        return nxt

    queues = {provider: serve(provider) for provider in files}
    install_fake_sdks(monkeypatch, queues)
    install_fake_http(monkeypatch, queues)


def _scores(result: RunResult) -> dict[tuple[str, str, str], float | None]:
    return {
        (doc.pipeline, doc.document_id, score.metric): score.value
        for doc in result.documents
        for score in doc.scores
    }


def _outcomes(result: RunResult) -> dict[tuple[str, str], str]:
    return {(u.pipeline, u.document_id): u.outcome for u in result.usage}


def _with_more_metrics(spec: RunSpec) -> RunSpec:
    views = tuple(
        view.model_copy(
            update={"metric_names": (*view.metric_names, "del_rate", "ins_rate")}
        )
        for view in spec.evaluation.views
    )
    return spec.model_copy(
        update={"evaluation": spec.evaluation.model_copy(update={"views": views})}
    )


@pytest.fixture
def archived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[RunSpec, ResumeStore, RunResult, _Local]:
    """Run 1 : cassettes, archive dans ``tmp_path / "archive"``."""
    _serve(monkeypatch)
    state = _Local()
    spec = _spec(tmp_path)
    store = ResumeStore(tmp_path / "archive")
    first = run(
        spec,
        registry=_registry(state),
        code_version="1.0",
        resume_store=store,
        max_workers=1,
    )
    assert state.calls == list(_DOCS)
    return spec, store, first, state


# --------------------------------------------------------------------------- #
# Le critère de sortie
# --------------------------------------------------------------------------- #


def test_an_archive_is_rescored_after_a_metric_upgrade_without_running_anything(
    archived: tuple[RunSpec, ResumeStore, RunResult, _Local],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, store, first, state = archived
    cut_network(monkeypatch)
    state.explode = True
    second = run(
        _with_more_metrics(spec),
        registry=_registry(state),
        code_version="1.0.1",  # une métrique corrigée : le paquet change
        resume_store=store,
        offline=True,
    )
    before, after = _scores(first), _scores(second)
    assert before  # trois pipelines × deux pages, notés
    assert {k: after[k] for k in before} == before
    # Re-noté, pas relu : les métriques ajoutées sont calculées sur l'archive.
    added = {k for k in after if k[2] in ("del_rate", "ins_rate")}
    assert len(added) == 2 * len(_DOCS) * len(spec.pipelines)
    assert _outcomes(second) == _outcomes(first)
    assert ("openai (zero-shot)", "folio_b") in {
        k for k, v in _outcomes(second).items() if v == "truncated"
    }
    assert second.manifest.code_version == "1.0.1"
    assert second.manifest.served_models == first.manifest.served_models
    # Hors ligne, rien n'est sondé : les binaires sont ceux de l'archive.
    assert second.manifest.system_binaries_lock == {"localocr": "5.3.0"}


def test_a_code_upgrade_reuses_the_archive_in_a_normal_resume(
    archived: tuple[RunSpec, ResumeStore, RunResult, _Local],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ce qui faisait re-payer toute une campagne : la clé portait ``code_version``."""
    spec, store, first, state = archived
    cut_network(monkeypatch)
    state.explode = True
    second = run(
        spec, registry=_registry(state), code_version="2.0", resume_store=store
    )
    assert _scores(second) == _scores(first)


def test_a_pipeline_module_upgrade_invalidates_its_unit(
    archived: tuple[RunSpec, ResumeStore, RunResult, _Local],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, store, _first, state = archived
    state.version = "1.1"
    with pytest.raises(ArchiveIncompleteError, match=r"local × folio_a"):
        run(
            spec,
            registry=_registry(state),
            code_version="1.0",
            resume_store=store,
            offline=True,
        )
    cut_network(monkeypatch)  # les unités cloud, elles, restent valides
    run(spec, registry=_registry(state), code_version="1.0", resume_store=store)
    assert state.calls == [*_DOCS, *_DOCS]


def test_a_system_binary_upgrade_invalidates_its_unit(
    archived: tuple[RunSpec, ResumeStore, RunResult, _Local],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une mise à jour de tesseract resservait les anciennes sorties sous un
    manifeste qui annonçait la nouvelle version."""
    spec, store, _first, state = archived
    cut_network(monkeypatch)
    state.binary = "5.4.1"
    second = run(
        spec, registry=_registry(state), code_version="1.0", resume_store=store
    )
    assert state.calls == [*_DOCS, *_DOCS]
    assert second.manifest.system_binaries_lock == {"localocr": "5.4.1"}


def test_offline_ignores_the_binaries_of_the_machine_that_rescores(
    archived: tuple[RunSpec, ResumeStore, RunResult, _Local],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un tiers qui re-note n'a pas à installer le même tesseract : rien ne tourne."""
    spec, store, first, state = archived
    cut_network(monkeypatch)
    state.binary = "9.9.9"
    state.explode = True
    second = run(
        spec, registry=_registry(state), code_version="1.0", resume_store=store,
        offline=True,
    )
    assert _scores(second) == _scores(first)
    assert second.manifest.system_binaries_lock == {"localocr": "5.3.0"}


# --------------------------------------------------------------------------- #
# Configuration lue dans l'environnement
# --------------------------------------------------------------------------- #


def test_an_endpoint_read_from_the_environment_enters_the_key_and_the_manifest(
    archived: tuple[RunSpec, ResumeStore, RunResult, _Local],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OPENAI_BASE_URL`` (le contournement vLLM) réutilisait en silence les
    sorties du modèle précédent : un autre endpoint est une autre unité."""
    spec, store, first, state = archived
    assert first.manifest.adapter_kwargs["openai:c0"]["base_url"] == (
        "https://api.openai.com/v1"
    )
    monkeypatch.setenv(
        "OPENAI_BASE_URL", "http://user:pw@vllm.local:8000/v1?token=abc"
    )
    with pytest.raises(ArchiveIncompleteError, match=r"openai \(zero-shot\)"):
        run(
            spec, registry=_registry(state), code_version="1.0", resume_store=store,
            offline=True,
        )
    _serve(monkeypatch)
    monkeypatch.setenv(
        "OPENAI_BASE_URL", "http://user:pw@vllm.local:8000/v1?token=abc"
    )
    second = run(
        spec, registry=_registry(state), code_version="1.0", resume_store=store
    )
    # Écrit sans identifiants ni jeton.
    assert second.manifest.adapter_kwargs["openai:c0"]["base_url"] == (
        "http://vllm.local:8000/v1"
    )
    assert "pw" not in second.model_dump_json()


# --------------------------------------------------------------------------- #
# Une seule empreinte
# --------------------------------------------------------------------------- #


def _archived_steps(store: ResumeStore) -> list[dict[str, Any]]:
    return [
        entry
        for index in sorted(store.base_dir.glob("*/index.json"))
        for entry in json.loads(index.read_bytes())["steps"]
    ]


def test_the_provenance_hash_covers_model_and_prompt_and_is_the_key_s_basis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``parameters_hash`` ne hachait que ``step.params`` : deux modèles, deux
    prompts donnaient la même provenance. Il est désormais l'empreinte de
    l'étape, et la clé d'unité en dérive."""
    hashes: dict[str, set[str]] = {}
    keys: dict[str, set[str]] = {}
    for variant, kwargs in {
        "base": {},
        "model": {"model": "gpt-4o"},
        "prompt": {"prompt": "Transcris."},
    }.items():
        _serve(monkeypatch)
        spec = _spec(tmp_path / variant)
        spec = spec.model_copy(
            update={
                "pipelines": spec.pipelines[:1],
                "adapter_kwargs": {
                    "openai:c0": {**spec.adapter_kwargs["openai:c0"], **kwargs}
                },
            }
        )
        store = ResumeStore(tmp_path / variant / "archive")
        run(spec, registry=_registry(_Local()), code_version="1.0",
            resume_store=store, max_workers=1)
        hashes[variant] = {
            artifact["provenance"]["parameters_hash"]
            for entry in _archived_steps(store)
            if entry["step"] == "vlm"
            for artifact in entry["artifacts"].values()
        }
        keys[variant] = {p.name for p in store.base_dir.iterdir() if p.is_dir()}
    assert all(len(h) == 1 for h in hashes.values())  # une empreinte par étape
    assert len(set.union(*hashes.values())) == 3
    assert len(set.union(*keys.values())) == 3 * len(_DOCS)


# --------------------------------------------------------------------------- #
# Ce que le manifeste écrit
# --------------------------------------------------------------------------- #


def test_the_manifest_names_the_served_model_unicode_and_dependencies(
    archived: tuple[RunSpec, ResumeStore, RunResult, _Local],
) -> None:
    _spec_, _store, first, _state = archived
    manifest = first.manifest
    # Demandé : l'alias ; servi : ce que le fournisseur a répondu.
    assert manifest.adapter_kwargs["openai:c0"]["model"] == "gpt-4o-mini"
    assert manifest.served_models == {
        "mistral_ocr:c1": ("mistral-ocr-2505",),
        "openai:c0": ("gpt-4o-mini-2024-07-18",),
    }
    assert manifest.unicode_version == unicodedata.unidata_version
    lock = manifest.dependencies_lock
    assert {"cinoc", "numpy", "scipy", "rapidfuzz", "lxml", "pydantic"} <= set(lock)
    assert lock["cinoc"]



def _economics(result: RunResult, pricing: dict[str, Any] | None = None) -> Any:
    series = {
        doc.pipeline: [] for doc in result.documents
    }
    for doc in result.documents:
        series[doc.pipeline].extend(s for s in doc.scores if s.metric == "cer")
    analysis = economics_analysis(
        "text", "cer", series, result.usage, result.manifest, pricing
    )
    assert analysis is not None
    return {row.pipeline: row for row in analysis.payload.pipelines}


def test_pricing_is_indexed_on_the_served_model(
    archived: tuple[RunSpec, ResumeStore, RunResult, _Local],
) -> None:
    """La table s'indexe sur le modèle **servi** ; absent de la table, le coût
    est inconnu et le dit — l'alias demandé ne le remplace pas."""
    _spec_, _store, first, _state = archived
    rows = _economics(first)
    assert rows["openai (zero-shot)"].cost_eur is None
    assert rows["openai (zero-shot)"].basis == (
        "tarif inconnu : openai/gpt-4o-mini-2024-07-18"
    )
    table = load_pricing()
    table["cloud_models"]["openai/gpt-4o-mini-2024-07-18"] = {
        "input_eur_per_mtok": 1000.0,
        "output_eur_per_mtok": 0.0,
    }
    priced = _economics(first, table)["openai (zero-shot)"]
    assert priced.basis == "machine+jetons"
    assert priced.cost_eur is not None and priced.cost_eur > 0.0
    # Modèle servi inconnu (réponse muette, JSON v3) : l'alias demandé.
    muet = first.model_copy(
        update={"manifest": first.manifest.model_copy(update={"served_models": {}})}
    )
    assert _economics(muet)["openai (zero-shot)"].basis == "machine+jetons"


# --------------------------------------------------------------------------- #
# Les unités en échec font partie de l'archive
# --------------------------------------------------------------------------- #


def test_a_failed_unit_is_archived_retried_normally_and_restored_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch)
    state = _Local(fail={"folio_b"})
    spec = _spec(tmp_path)
    store = ResumeStore(tmp_path / "archive")
    first = run(spec, registry=_registry(state), code_version="1.0",
                resume_store=store, max_workers=1)
    assert _outcomes(first)[("local", "folio_b")] == "failed"
    failed = [
        json.loads(index.read_bytes())
        for index in store.base_dir.glob("*/index.json")
        if json.loads(index.read_bytes())["outcome"] == "failed"
    ]
    assert [(f["reason"], f["message"]) for f in failed] == [
        ("engine", "localocr : page illisible")
    ]

    cut_network(monkeypatch)
    state.explode = True
    offline = run(spec, registry=_registry(state), code_version="1.0",
                  resume_store=store, offline=True)
    (unit,) = [u for u in offline.usage if u.outcome == "failed"]
    assert (unit.pipeline, unit.document_id, unit.reason) == (
        "local", "folio_b", "engine"
    )
    assert unit.message == "localocr : page illisible"

    state.explode = False
    state.fail = set()
    retried = run(spec, registry=_registry(state), code_version="1.0",
                  resume_store=store)
    assert state.calls == [*_DOCS, "folio_b"]  # l'échec, et lui seul, retenté
    assert _outcomes(retried)[("local", "folio_b")] == "ok"


def test_offline_requires_an_archive(tmp_path: Path) -> None:
    from cinoc.app.orchestrator import OrchestrationError

    with pytest.raises(OrchestrationError, match="archive"):
        run(_spec(tmp_path), registry=_registry(_Local()), code_version="1.0",
            offline=True)


# --------------------------------------------------------------------------- #
# Les deux transports
# --------------------------------------------------------------------------- #

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_cli_offline_rescores_and_fails_clearly_on_a_missing_unit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import shutil

    from cinoc.app.results import load_run_result
    from cinoc.interfaces.cli import main

    shutil.copytree(EXAMPLES, tmp_path / "examples")
    config = str(tmp_path / "examples" / "config.yaml")
    assert main(["run", config, "--resume-dir", str(tmp_path / "vide"), "--offline",
                 "-o", str(tmp_path / "x.html")]) == 1
    # L'exemple n'a pas d'images : une unité sans image n'est jamais archivée.
    assert "sans image lisible" in capsys.readouterr().err
    for gt in (tmp_path / "examples" / "corpus").glob("*.gt.txt"):
        stem = gt.name.removesuffix(".gt.txt")
        (gt.parent / f"{stem}.png").write_bytes(b"png:" + stem.encode())
    archive = tmp_path / "archive"
    base = ["run", config, "--resume-dir", str(archive), "-o", str(tmp_path / "r.html")]
    assert main([*base, "--json", str(tmp_path / "1.json")]) == 0
    assert main([*base, "--offline", "--json", str(tmp_path / "2.json")]) == 0
    first = load_run_result(tmp_path / "1.json")
    second = load_run_result(tmp_path / "2.json")
    assert _scores(second) == _scores(first)

    (victim, *_rest) = sorted(archive.glob("*/index.json"))
    victim.unlink()
    capsys.readouterr()
    assert main([*base, "--offline"]) == 1
    err = capsys.readouterr().err
    assert "1 unité(s) absente(s) de l'archive" in err
    assert "Rien n'a été exécuté" in err

    assert main(["run", config, "--offline"]) == 1
    assert "--offline" in capsys.readouterr().err


def test_a_web_job_keeps_its_archive_in_the_data_dir(tmp_path: Path) -> None:
    """Le web n'avait pas de dossier de reprise : les sidecars d'un run web
    mouraient avec le workspace du job."""
    from cinoc.adapters.storage import JobState, JobStore
    from cinoc.app.demo import demo_run_spec, write_demo_corpus
    from cinoc.app.jobs import JobRunner
    from cinoc.app.results import load_run_result

    def build(workspace: Path) -> RunSpec:
        corpus = write_demo_corpus(workspace)
        for document in corpus.documents:
            Path(document.image_uri or "").write_bytes(b"png:" + document.id.encode())
        return demo_run_spec(corpus, run_id="web-archive")

    registry = ModuleRegistry()
    register_default_modules(registry)
    runner = JobRunner(
        store=JobStore(),
        registry=registry,
        reports_dir=tmp_path / "reports",
        code_version="1.0",
        archive_dir=tmp_path / "archives",
    )
    job_id = runner.launch(build)
    assert runner.join(job_id, timeout=30)
    job = runner.store.get(job_id)
    assert job is not None and job.state is JobState.DONE
    result = load_run_result(tmp_path / "reports" / "web-archive.json")
    archive = tmp_path / "archives" / job_id
    assert result.manifest.artifacts_dir == str(archive)
    assert len(list(archive.glob("*/index.json"))) == 10  # 2 moteurs × 5 pages


def test_a_moved_archive_is_still_rescored_offline(
    archived: tuple[RunSpec, ResumeStore, RunResult, _Local],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L'archive se télécharge (P5h) : ses fichiers sont nommés relativement à
    leur unité, pas par le chemin absolu de la machine qui l'a produite."""
    import shutil

    spec, store, first, state = archived
    moved = tmp_path / "ailleurs" / "archive"
    shutil.move(str(store.base_dir), str(moved))
    cut_network(monkeypatch)
    state.explode = True
    second = run(
        spec, registry=_registry(state), code_version="1.0",
        resume_store=ResumeStore(moved), offline=True,
    )
    assert _scores(second) == _scores(first)
    assert second.manifest.artifacts_dir == str(moved)
