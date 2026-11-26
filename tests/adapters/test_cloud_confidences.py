"""P5f 5 (S20) — Azure et Google émettent ``CONFIDENCES`` depuis leurs mots.

Les deux réponses portent une confiance **par mot** (Azure DI :
``analyzeResult.pages[].words[].confidence`` ; Google Vision :
``fullTextAnnotation.pages[].blocks[].paragraphs[].words[].confidence``, le texte
du mot étant ses ``symbols``) ; le code n'en gardait que le texte, et les deux
moteurs étaient absents de la calibration. Même forme que le sidecar de
Tesseract (``ConfidenceToken``, D-070) ; lue sur le **corps** de la réponse,
donc identique à l'exécution et à la relecture du sidecar ``NATIVE_JSON``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.ocr.azure_di import AzureDocIntelAdapter
from cinoc.adapters.ocr.azure_di import _confidences as azure_confidences
from cinoc.adapters.ocr.google_vision import GoogleVisionAdapter
from cinoc.adapters.ocr.google_vision import _confidences as google_confidences
from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.run_planning import Competitor, plan_benchmark_run
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.evaluation.analysis import CalibrationPayload
from cinoc.evaluation.calibration import load_confidence_tokens
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.adapters._native_fakes import install_fake_http, set_keys, wire


def _tokens(pairs: list[tuple[str, float]]) -> list[ConfidenceToken]:
    return [ConfidenceToken(text=t, confidence=c) for t, c in pairs]


def test_azure_words_become_confidence_tokens() -> None:
    assert azure_confidences(wire("ocr", "azure_di", "folio_a")) == _tokens(
        [("Le", 0.995), ("Petit", 0.993)]
    )


def test_google_words_are_their_symbols_and_keep_their_confidence() -> None:
    """La virgule n'a pas de ``confidence`` : elle n'en reçoit pas (ni 0, ni
    celle du paragraphe)."""
    assert google_confidences(wire("ocr", "google_vision", "folio_mots")) == _tokens(
        [("Le", 0.99), ("Petit", 0.98), ("Journa1", 0.62), ("12", 0.97)]
    )


def test_a_response_without_words_has_no_token() -> None:
    assert google_confidences(wire("ocr", "google_vision", "folio_a")) == []
    assert azure_confidences({"analyzeResult": {"pages": [{}]}}) == []


@pytest.mark.parametrize("value", [1.5, -0.1, "haute", None, float("nan")])
def test_a_confidence_outside_0_1_is_not_a_confidence(value: object) -> None:
    body = {
        "analyzeResult": {
            "pages": [{"words": [{"content": "mot", "confidence": value}]}]
        }
    }
    assert azure_confidences(body) == []


@pytest.mark.parametrize(
    ("build", "env", "family", "scenario"),
    [
        (lambda: AzureDocIntelAdapter(label="a"), "azure_di", "ocr", "folio_a"),
        (lambda: GoogleVisionAdapter(label="v"), "google_vision", "ocr", "folio_mots"),
    ],
)
def test_the_adapter_publishes_the_sidecar(
    build: Callable[[], Any],
    env: str,
    family: str,
    scenario: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_keys(monkeypatch)
    install_fake_http(monkeypatch, {env: lambda: wire(family, env, scenario)})
    adapter = build()
    assert ArtifactType.CONFIDENCES in adapter.output_types
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfaux")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    output = adapter.execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="d:img", document_id="d", type=ArtifactType.IMAGE, uri=str(image)
            )
        },
        {},
        RunContext(
            document_id="d", code_version="t", pipeline_name="p",
            workspace_uri=str(workspace),
        ),
        RunControl(),
    )
    sidecar = output.artifacts[ArtifactType.CONFIDENCES]
    native = wire(family, env, scenario)
    expected = (
        azure_confidences(native) if env == "azure_di" else google_confidences(native)
    )
    assert expected and load_confidence_tokens(sidecar) == expected


def test_both_cloud_engines_enter_the_calibration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De bout en bout : un run Azure + Google rend une ligne de calibration par
    moteur (avant : aucune — seuls Tesseract et kraken en avaient)."""
    set_keys(monkeypatch)
    queues: dict[str, Iterator[str]] = {
        "azure_di": iter(("folio_a", "folio_b")),
        "google_vision": iter(("folio_mots", "folio_mots")),
    }

    def serve(provider: str) -> Callable[[], dict[str, Any]]:
        return lambda: wire("ocr", provider, next(queues[provider]))

    install_fake_http(monkeypatch, {p: serve(p) for p in queues})
    folder = tmp_path / "corpus"
    folder.mkdir()
    documents = []
    for doc in ("folio_a", "folio_b"):
        (folder / f"{doc}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + doc.encode())
        gt = folder / f"{doc}.gt.txt"
        gt.write_text("Le Petit Journal, 12 mars 1894.", encoding="utf-8")
        documents.append(
            DocumentRef(
                id=doc,
                image_uri=str(folder / f"{doc}.png"),
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            )
        )
    spec = plan_benchmark_run(
        (Competitor(engine="azure_di"), Competitor(engine="google_vision")),
        CorpusSpec(name="pj", documents=tuple(documents)),
        "s20",
    )(tmp_path)
    spec = spec.model_copy(
        update={
            "evaluation": spec.evaluation.model_copy(update={"analyses": "toutes"})
        }
    )
    registry = ModuleRegistry()
    register_default_modules(registry)
    result = run(spec, registry=registry, code_version="t", max_workers=1)
    rows = [
        row
        for analysis in result.analyses
        if isinstance(analysis.payload, CalibrationPayload)
        for row in analysis.payload.pipelines
    ]
    engines = {row.pipeline.split("_", 1)[0] for row in rows}
    assert {"azure", "google"} <= engines, [row.pipeline for row in rows]
