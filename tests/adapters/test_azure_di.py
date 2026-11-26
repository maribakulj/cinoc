"""``AzureDocIntelAdapter`` : contrat module + flux async REST sur **cassette HTTP**.

Pas de réseau ni d'attente : ``_invoke_azure_di`` reçoit un ``httpx.MockTransport``
(rejoue le flux ``202`` + ``Operation-Location`` → sonde ``succeeded``) et un
``sleep`` no-op. Les valeurs attendues sont **dérivées à la main** depuis la
cassette (``analyzeResult.content`` strippé).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from cinoc.adapters.ocr.azure_di import (
    AzureDocIntelAdapter,
    _extract_text,
    _invoke_azure_di,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_ENDPOINT = "https://res.cognitiveservices.azure.com"
_OP_URL = f"{_ENDPOINT}/documentintelligence/operations/abc123?api-version=2024-11-30"
#: Cassette : réponse Read réelle (texte complet d'une page à 2 lignes).
_RESULT = {
    "status": "succeeded",
    "analyzeResult": {"content": "Bonjour le monde\nseconde ligne", "pages": [{}]},
}


def _nosleep(_seconds: float) -> None:
    """Sonde déterministe : aucune attente réelle entre les polls."""


def _ctx(workspace: Path) -> RunContext:
    return RunContext(
        document_id="d1", code_version="t", pipeline_name="p",
        workspace_uri=str(workspace),
    )


def _image(tmp_path: Path) -> Artifact:
    path = tmp_path / "page.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake-image-bytes")
    return Artifact(
        id="d1:img", document_id="d1", type=ArtifactType.IMAGE, uri=str(path)
    )


def _transport(handler: object) -> httpx.MockTransport:
    return httpx.MockTransport(handler)  # type: ignore[arg-type]


def _set_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", _ENDPOINT)
    monkeypatch.setenv("AZURE_DOC_INTEL_KEY", "secret")


# --- Contrat Module -----------------------------------------------------------


def test_satisfies_module_protocol() -> None:
    adapter = AzureDocIntelAdapter(label="az")
    assert isinstance(adapter, Module)
    assert adapter.name == "azure_di:az"
    assert adapter.input_types == frozenset({ArtifactType.IMAGE})
    assert adapter.output_types == frozenset(
        {ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON, ArtifactType.CONFIDENCES}
    )


def test_rejects_bad_label() -> None:
    with pytest.raises(AdapterStepError):
        AzureDocIntelAdapter(label="mauvais label")


def test_execute_writes_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_creds(monkeypatch)
    monkeypatch.setattr(
        "cinoc.adapters.ocr.azure_di._invoke_azure_di",
        lambda **_: {
            "status": "succeeded",
            "analyzeResult": {"content": "texte reconnu"},
        },
    )
    out = AzureDocIntelAdapter(label="az").execute(
        {ArtifactType.IMAGE: _image(tmp_path)}, {}, _ctx(tmp_path), RunControl()
    )
    artifact = out.artifacts[ArtifactType.RAW_TEXT]
    assert artifact.uri is not None
    assert Path(artifact.uri).read_text(encoding="utf-8") == "texte reconnu"


def test_missing_endpoint_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_DOC_INTEL_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_DOC_INTEL_KEY", "k")
    with pytest.raises(AdapterStepError, match="AZURE_DOC_INTEL_ENDPOINT"):
        AzureDocIntelAdapter(label="az").execute(
            {ArtifactType.IMAGE: _image(tmp_path)}, {}, _ctx(tmp_path), RunControl()
        )


def test_missing_key_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", _ENDPOINT)
    monkeypatch.delenv("AZURE_DOC_INTEL_KEY", raising=False)
    with pytest.raises(AdapterStepError, match="AZURE_DOC_INTEL_KEY"):
        AzureDocIntelAdapter(label="az").execute(
            {ArtifactType.IMAGE: _image(tmp_path)}, {}, _ctx(tmp_path), RunControl()
        )


def test_missing_image_raises(tmp_path: Path) -> None:
    with pytest.raises(AdapterStepError):
        AzureDocIntelAdapter(label="az").execute(
            {}, {}, _ctx(tmp_path), RunControl()
        )


# --- Flux async REST sur cassette (POST 202 → sonde succeeded) ----------------


def _image_file(tmp_path: Path) -> str:
    path = tmp_path / "page.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return str(path)


def test_invoke_submits_then_polls_and_extracts(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen["post_path"] = request.url.path
            seen["api"] = request.url.params.get("api-version")
            seen["key"] = request.headers.get("Ocp-Apim-Subscription-Key")
            body = json.loads(request.content)
            seen["has_source"] = bool(body.get("base64Source"))
            return httpx.Response(202, headers={"operation-location": _OP_URL})
        seen["get_url"] = str(request.url)
        return httpx.Response(200, json=_RESULT)

    text = _extract_text(_invoke_azure_di(
        endpoint=_ENDPOINT,
        image_path=_image_file(tmp_path),
        deadline=Deadline.infinite(),
        key="secret",
        transport=_transport(handler),
        sleep=_nosleep,
    ))
    # Valeur dérivée main : analyzeResult.content strippé.
    assert text == "Bonjour le monde\nseconde ligne"
    assert str(seen["post_path"]).endswith("/documentModels/prebuilt-read:analyze")
    assert seen["api"] == "2024-11-30"
    assert seen["key"] == "secret"
    assert seen["has_source"] is True
    assert seen["get_url"] == _OP_URL


def test_invoke_polls_until_succeeded(tmp_path: Path) -> None:
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, headers={"operation-location": _OP_URL})
        state["polls"] += 1
        if state["polls"] < 3:
            return httpx.Response(200, json={"status": "running"})
        return httpx.Response(200, json=_RESULT)

    text = _extract_text(_invoke_azure_di(
        endpoint=_ENDPOINT,
        image_path=_image_file(tmp_path),
        deadline=Deadline.infinite(),
        key="k",
        transport=_transport(handler),
        sleep=_nosleep,
    ))
    assert text == "Bonjour le monde\nseconde ligne"
    assert state["polls"] == 3  # 2× running puis succeeded


def test_invoke_failed_status_raises(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, headers={"operation-location": _OP_URL})
        return httpx.Response(200, json={"status": "failed"})

    with pytest.raises(AdapterStepError, match="failed"):
        _extract_text(_invoke_azure_di(
            endpoint=_ENDPOINT,
            image_path=_image_file(tmp_path),
            deadline=Deadline.infinite(),
            key="k",
            transport=_transport(handler),
            sleep=_nosleep,
        ))


def test_invoke_missing_operation_location_raises(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(202)  # pas d'en-tête Operation-Location

    with pytest.raises(AdapterStepError, match="Operation-Location"):
        _extract_text(_invoke_azure_di(
            endpoint=_ENDPOINT,
            image_path=_image_file(tmp_path),
            deadline=Deadline.infinite(),
            key="k",
            transport=_transport(handler),
            sleep=_nosleep,
        ))


def test_invoke_submit_http_error_raises(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "clé invalide"}})

    with pytest.raises(AdapterStepError, match="statut HTTP 401"):
        _extract_text(_invoke_azure_di(
            endpoint=_ENDPOINT,
            image_path=_image_file(tmp_path),
            deadline=Deadline.infinite(),
            key="bad",
            transport=_transport(handler),
            sleep=_nosleep,
        ))


def test_invoke_blank_page_returns_empty(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, headers={"operation-location": _OP_URL})
        return httpx.Response(200, json={"status": "succeeded", "analyzeResult": {}})

    text = _extract_text(_invoke_azure_di(
        endpoint=_ENDPOINT,
        image_path=_image_file(tmp_path),
        deadline=Deadline.infinite(),
        key="k",
        transport=_transport(handler),
        sleep=_nosleep,
    ))
    assert text == ""
