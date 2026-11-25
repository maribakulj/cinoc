"""Orchestrateur : câblage de bout en bout (registre → executor → runner)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.llm._base import LLMCompletion
from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.orchestrator import OrchestrationError, PipelineOutputs
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Region
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run import RunManifest
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.result import RunResult

TEXT_VIEW = EvaluationView(
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
    return PipelineSpec(
        name=name, initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
    )


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def _spec(corpus: CorpusSpec) -> RunSpec:
    return RunSpec(
        corpus=corpus,
        pipelines=(_pipeline("eng", "eng"),),
        evaluation=EvaluationSpec(views=(TEXT_VIEW,)),
        adapter_kwargs={"precomputed:eng": {"source_label": "eng"}},
    )


def test_run_end_to_end(tmp_path: Path) -> None:
    (tmp_path / "doc1.eng.txt").write_text("abxd", encoding="utf-8")
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    document = DocumentRef(
        id="doc1",
        image_uri=str(tmp_path / "doc1.png"),
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "doc1.gt.txt")
            ),
        ),
    )
    result = run(
        _spec(CorpusSpec(name="c", documents=(document,))),
        registry=_registry(),
        code_version="1.0",
    )
    aggregate = result.pipelines[0].aggregate[0]
    assert aggregate.metric == "cer"
    assert aggregate.value == pytest.approx(0.25)  # 1 substitution / 4
    assert result.manifest.corpus_name == "c"
    assert result.manifest.n_documents == 1
    assert result.manifest.run_id.startswith("run-")
    assert result.manifest.adapter_kwargs == {
        "precomputed:eng": {"source_label": "eng"}
    }


def test_orchestrator_injects_real_block_cropper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'orchestrateur passe le cropper réel (couche 5) à l'exécuteur — sans lui,
    les étapes ``fanout`` du pipeline hybride ne pourraient pas découper les blocs.
    """
    from cinoc.adapters.layout.crop import crop_region
    from cinoc.pipeline.executor import PipelineExecutor

    captured: dict[str, object] = {}
    original = PipelineExecutor.execute_document

    def spy(self: PipelineExecutor, *args: object, **kwargs: object) -> object:
        captured["cropper"] = kwargs.get("cropper")
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(PipelineExecutor, "execute_document", spy)
    (tmp_path / "doc1.eng.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    document = DocumentRef(
        id="doc1",
        image_uri=str(tmp_path / "doc1.png"),
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "doc1.gt.txt")
            ),
        ),
    )
    run(
        _spec(CorpusSpec(name="c", documents=(document,))),
        registry=_registry(),
        code_version="1.0",
    )
    assert captured["cropper"] is crop_region


def test_missing_image_uri_raises(tmp_path: Path) -> None:
    corpus = CorpusSpec(name="c", documents=(DocumentRef(id="doc1"),))
    with pytest.raises(OrchestrationError):
        run(_spec(corpus), registry=_registry(), code_version="1.0")


def test_failing_competitor_does_not_abort_run(tmp_path: Path) -> None:
    # Un concurrent qui échoue (source absente → AdapterStepError) ne doit PAS
    # tuer le banc d'essai : l'autre concurrent reste exécuté et scoré, le run
    # produit bien un RunResult. (Régression : avant, une branche en échec —
    # ex. clé Mistral absente — faisait planter tout le run.)
    (tmp_path / "doc1.eng.txt").write_text("abxd", encoding="utf-8")
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    document = DocumentRef(
        id="doc1",
        image_uri=str(tmp_path / "doc1.png"),
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "doc1.gt.txt")
            ),
        ),
    )
    spec = RunSpec(
        corpus=CorpusSpec(name="c", documents=(document,)),
        pipelines=(_pipeline("ok", "eng"), _pipeline("ko", "absent")),
        evaluation=EvaluationSpec(views=(TEXT_VIEW,)),
        adapter_kwargs={
            "precomputed:eng": {"source_label": "eng"},
            "precomputed:absent": {"source_label": "absent"},  # source manquante
        },
    )
    result = run(spec, registry=_registry(), code_version="1.0")  # ne lève pas
    by_name = {p.pipeline: p for p in result.pipelines}
    assert by_name["ok"].aggregate[0].value == pytest.approx(0.25)  # scoré
    # « ko » a échoué : soit absent du rapport, soit présent mais non scoré.
    ko = by_name.get("ko")
    assert ko is None or not ko.aggregate or ko.aggregate[0].value is None


def test_archaic_list_binds_air_and_hcpr(tmp_path: Path) -> None:
    # Liste archaïque configurée : l'orchestrateur relie ``air`` et enregistre
    # ``hcpr`` sur la liste effective ; la vue les demande, le run les score.
    (tmp_path / "doc1.eng.txt").write_text("meſſe", encoding="utf-8")  # ſ conservé
    (tmp_path / "doc1.gt.txt").write_text("meſſe", encoding="utf-8")
    document = DocumentRef(
        id="doc1",
        image_uri=str(tmp_path / "doc1.png"),
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "doc1.gt.txt")
            ),
        ),
    )
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer", "air", "hcpr"),
    )
    spec = RunSpec(
        corpus=CorpusSpec(name="c", documents=(document,)),
        pipelines=(_pipeline("eng", "eng"),),
        evaluation=EvaluationSpec(views=(view,)),
        adapter_kwargs={"precomputed:eng": {"source_label": "eng"}},
        metadata={"archaic_list": "archaic_core", "archaic_list_hash": "abc123"},
    )
    result = run(spec, registry=_registry(), code_version="1.0")
    scores = {s.metric: s for s in result.pipelines[0].aggregate}
    # ſ recopié fidèlement : préservé (hcpr=1), aucun apport net (air=0).
    assert scores["hcpr"].value == pytest.approx(1.0)
    assert scores["air"].value == pytest.approx(0.0)
    assert result.manifest.metadata["archaic_list"] == "archaic_core"
    assert result.manifest.metadata["archaic_list_hash"] == "abc123"


# ── isolation des workspaces + provenance (corrections d'audit) ─────────────
def _ocr_llm_pipeline(name: str, ocr_label: str) -> PipelineSpec:
    return PipelineSpec(
        name=name,
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="ocr",
                kind="ocr",
                adapter_name=f"precomputed:{ocr_label}",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
            PipelineStep(
                id="llm",
                kind="post_correction",
                adapter_name="openai:gpt",  # PARTAGÉ par les deux pipelines
                input_types=(ArtifactType.RAW_TEXT,),
                output_types=(ArtifactType.CORRECTED_TEXT,),
                inputs_from={ArtifactType.RAW_TEXT: "ocr"},
            ),
        ),
    )


def _shared_writer_spec(tmp_path: Path) -> RunSpec:
    # OCR pré-calculé distinct par pipeline ; GT = la sortie attendue de A.
    (tmp_path / "d.gt.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "d.engA.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "d.engB.txt").write_text("beta", encoding="utf-8")
    document = DocumentRef(
        id="d",
        image_uri=str(tmp_path / "d.png"),
        ground_truths=(
            GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "d.gt.txt")),
        ),
    )
    view = EvaluationView(
        name="corrected",
        candidate_types=frozenset({ArtifactType.CORRECTED_TEXT}),
        metric_names=("cer",),
    )
    return RunSpec(
        corpus=CorpusSpec(name="c", documents=(document,)),
        pipelines=(_ocr_llm_pipeline("A", "engA"), _ocr_llm_pipeline("B", "engB")),
        evaluation=EvaluationSpec(views=(view,)),
        adapter_kwargs={
            "precomputed:engA": {"source_label": "engA"},
            "precomputed:engB": {"source_label": "engB"},
            "openai:gpt": {"label": "gpt"},
        },
        run_id="t",
    )


def _cer(result: RunResult, pipeline: str) -> float | None:
    (value,) = (
        score.value
        for pr in result.pipelines
        if pr.pipeline == pipeline
        for score in pr.aggregate
        if score.metric == "cer"
    )
    return value


def test_pipelines_sharing_a_writer_do_not_contaminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # LLM mocké : renvoie le texte OCR reçu (dernier segment du prompt) → la
    # sortie corrigée diffère par pipeline puisque l'OCR amont diffère.
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai",
        lambda *, model, prompt, deadline: LLMCompletion(prompt.rsplit("\n\n", 1)[-1]),
    )
    result = run(
        _shared_writer_spec(tmp_path), registry=_registry(), code_version="9.9"
    )
    # A corrige "alpha" == GT → CER 0 ; B corrige "beta" != GT → CER > 0. Sans
    # isolation par pipeline, B écraserait le fichier de A → CER de A faussement > 0.
    assert _cer(result, "A") == 0.0
    assert (_cer(result, "B") or 0.0) > 0.0


def test_manifest_captures_module_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai",
        lambda *, model, prompt, deadline: LLMCompletion("x"),
    )
    result = run(
        _shared_writer_spec(tmp_path), registry=_registry(), code_version="9.9"
    )
    # R-2 : la version déclarée de chaque module exécuté entre dans l'empreinte.
    assert result.manifest.module_versions == {
        "openai:gpt": "1.0",
        "precomputed:engA": "1.0",
        "precomputed:engB": "1.0",
    }
    # precomputed/openai n'enveloppent aucun binaire système → lock vide.
    assert result.manifest.system_binaries_lock == {}


def _tesseract_spec(corpus: CorpusSpec) -> RunSpec:
    """Pipeline 1 étape tesseract (IMAGE→RAW_TEXT) — moteur réel, OCR mocké."""
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="tesseract:fra",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    pipeline = PipelineSpec(
        name="tess", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
    )
    return RunSpec(
        corpus=corpus,
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=(TEXT_VIEW,)),
        adapter_kwargs={"tesseract:fra": {"label": "fra", "lang": "fra"}},
    )


def test_manifest_captures_tesseract_binary_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Déterminisme (§12) : la version du binaire tesseract atterrit dans le
    # manifeste via le hook de provenance `system_binaries()` (duck-typing).
    monkeypatch.setattr(
        "cinoc.adapters.ocr.tesseract._invoke_tesseract", lambda **_: "abcd"
    )
    monkeypatch.setattr(
        "cinoc.adapters.ocr.tesseract._invoke_tesseract_confidences", lambda **_: []
    )
    monkeypatch.setattr(
        "cinoc.adapters.ocr.tesseract.tesseract_binary_version",
        lambda: "tesseract 5.3.0",
    )
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    document = DocumentRef(
        id="doc1",
        image_uri=str(tmp_path / "doc1.png"),
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "doc1.gt.txt")
            ),
        ),
    )
    result = run(
        _tesseract_spec(CorpusSpec(name="c", documents=(document,))),
        registry=_registry(),
        code_version="1.0",
    )
    assert result.manifest.system_binaries_lock == {"tesseract": "tesseract 5.3.0"}


# --- Sink d'artefacts (LAYOUT → persistance, T2) -------------------------------

def _layout_spec(corpus: CorpusSpec) -> RunSpec:
    """Pipeline segmentation à 1 étape : ``precomputed_layout`` (IMAGE→LAYOUT)."""
    step = PipelineStep(
        id="seg", kind="layout", adapter_name="precomputed_layout",
        input_types=(ArtifactType.IMAGE,), output_types=(ArtifactType.LAYOUT,),
    )
    pipeline = PipelineSpec(
        name="seg", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
    )
    return RunSpec(
        corpus=corpus,
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=()),
    )


def _layout_scene(tmp_path: Path) -> CorpusSpec:
    layout = CanonicalLayout(
        pages=(LayoutPage(regions=(Region(id="r1", region_type="text"),)),)
    )
    (tmp_path / "doc1.png").write_bytes(b"\x89PNG stub")
    (tmp_path / "doc1.layout.json").write_bytes(
        layout.model_dump_json().encode("utf-8")
    )
    document = DocumentRef(id="doc1", image_uri=str(tmp_path / "doc1.png"))
    return CorpusSpec(name="c", documents=(document,))


def test_artifact_sink_receives_readable_layout(tmp_path: Path) -> None:
    seen: list[tuple[str, str]] = []

    def sink(outputs: PipelineOutputs, manifest: RunManifest) -> None:
        for pipeline_name, per_doc in outputs.items():
            for doc_id, artifacts in per_doc.items():
                art = artifacts.get(ArtifactType.LAYOUT)
                assert art is not None and art.uri is not None
                # URI lisible PENDANT le run (avant nettoyage du workspace)
                got = CanonicalLayout.model_validate_json(Path(art.uri).read_bytes())
                assert got.pages[0].regions[0].id == "r1"
                seen.append((pipeline_name, doc_id))

    run(
        _layout_spec(_layout_scene(tmp_path)),
        registry=_registry(),
        code_version="1.0",
        artifact_sink=sink,
    )
    assert seen == [("seg", "doc1")]


def test_run_without_sink_still_succeeds(tmp_path: Path) -> None:
    # Le sink est optionnel : un run sans sink produit son RunResult normalement.
    result = run(
        _layout_spec(_layout_scene(tmp_path)),
        registry=_registry(),
        code_version="1.0",
    )
    assert result.manifest.corpus_name == "c"


def test_run_result_carries_sorted_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "cinoc.adapters.llm.openai._invoke_openai",
        lambda *, model, prompt, deadline: LLMCompletion("x", 11, 7),
    )
    result = run(
        _shared_writer_spec(tmp_path), registry=_registry(), code_version="9.9"
    )
    # Une entrée par (pipeline x document), triée (pipeline, document_id).
    keys = [(u.pipeline, u.document_id) for u in result.usage]
    assert keys == sorted(keys)
    assert len(result.usage) == len(
        {(u.pipeline, u.document_id) for u in result.usage}
    )
    # Les jetons du LLM mocké remontent jusqu'au RunResult.
    assert all(u.usage.tokens_in == 11 for u in result.usage)
    assert all(u.usage.tokens_out == 7 for u in result.usage)
    assert all(
        u.usage.duration_seconds is not None and u.usage.duration_seconds >= 0.0
        for u in result.usage
    )


def test_a_secret_kwarg_never_leaves_the_run(tmp_path: Path) -> None:
    """Un jeton passé à un module ne sort ni dans le JSON ni dans le rapport.

    Défaut réel (D-260) : le jeton du segmenteur distant entrait dans
    ``adapter_kwargs``, que le manifeste recopiait et que la section
    « composition » affichait en clair. Le manifeste garde le fait qu'un
    secret a été fourni, jamais sa valeur.
    """
    from cinoc.reports.renderer import default_report_renderer

    (tmp_path / "doc1.eng.txt").write_text("abxd", encoding="utf-8")
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    document = DocumentRef(
        id="doc1",
        image_uri=str(tmp_path / "doc1.png"),
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "doc1.gt.txt")
            ),
        ),
    )
    secret = "hf_NEPASFUIRxyz123"
    spec = RunSpec(
        corpus=CorpusSpec(name="c", documents=(document,)),
        pipelines=(_pipeline("eng", "eng"),),
        evaluation=EvaluationSpec(views=(TEXT_VIEW,)),
        adapter_kwargs={"precomputed:eng": {"source_label": "eng", "token": secret}},
    )
    result = run(spec, registry=_registry(), code_version="test")

    assert result.manifest.adapter_kwargs["precomputed:eng"]["token"] == "<secret>"
    assert secret not in result.model_dump_json()
    assert secret not in default_report_renderer().render(result)
