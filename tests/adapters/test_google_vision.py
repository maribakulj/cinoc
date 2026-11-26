"""``GoogleVisionAdapter`` : contrat module + parsing REST sur **cassette HTTP**.

Pas de réseau : ``_invoke_google_vision`` reçoit un ``httpx.MockTransport`` qui
rejoue une réponse Vision **authentique** (forme officielle ``images:annotate``).
Les valeurs attendues sont **dérivées à la main** depuis la cassette par la règle
de parsing (``fullTextAnnotation.text`` strippé), jamais copiées d'une source.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from cinoc.adapters.ocr.google_vision import (
    GoogleVisionAdapter,
    _extract_text,
    _invoke_google_vision,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

#: Cassette : réponse Vision réelle (DOCUMENT_TEXT_DETECTION) d'une page à 2 lignes.
_CASSETTE = {
    "responses": [
        {
            "fullTextAnnotation": {"text": "Bonjour le monde\nseconde ligne\n"},
            "textAnnotations": [{"description": "Bonjour"}],
        }
    ]
}


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


# --- Contrat Module -----------------------------------------------------------


def test_satisfies_module_protocol() -> None:
    adapter = GoogleVisionAdapter(label="gv")
    assert isinstance(adapter, Module)
    assert adapter.name == "google_vision:gv"
    assert adapter.input_types == frozenset({ArtifactType.IMAGE})
    assert adapter.output_types == frozenset(
        {ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON}
    )


def test_rejects_bad_label() -> None:
    with pytest.raises(AdapterStepError):
        GoogleVisionAdapter(label="mauvais label")


def test_execute_writes_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", "k")
    monkeypatch.setattr(
        "cinoc.adapters.ocr.google_vision._invoke_google_vision",
        lambda **_: {"responses": [{"fullTextAnnotation": {"text": "texte reconnu"}}]},
    )
    out = GoogleVisionAdapter(label="gv").execute(
        {ArtifactType.IMAGE: _image(tmp_path)}, {}, _ctx(tmp_path), RunControl()
    )
    artifact = out.artifacts[ArtifactType.RAW_TEXT]
    assert artifact.uri is not None
    assert Path(artifact.uri).read_text(encoding="utf-8") == "texte reconnu"


def test_missing_key_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOOGLE_VISION_API_KEY", raising=False)
    with pytest.raises(AdapterStepError, match="GOOGLE_VISION_API_KEY"):
        GoogleVisionAdapter(label="gv").execute(
            {ArtifactType.IMAGE: _image(tmp_path)}, {}, _ctx(tmp_path), RunControl()
        )


def test_missing_image_raises(tmp_path: Path) -> None:
    with pytest.raises(AdapterStepError):
        GoogleVisionAdapter(label="gv").execute(
            {}, {}, _ctx(tmp_path), RunControl()
        )


# --- Parsing REST sur cassette (le vrai chemin httpx) -------------------------


def test_invoke_parses_full_text_and_builds_request(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.url.params.get("key")
        body = json.loads(request.content)
        seen["feature"] = body["requests"][0]["features"][0]["type"]
        seen["has_content"] = bool(body["requests"][0]["image"]["content"])
        return httpx.Response(200, json=_CASSETTE)

    text = _extract_text(_invoke_google_vision(
        image_path=str(image),
        deadline=Deadline.infinite(),
        api_key="test-key",
        transport=_transport(handler),
    ))
    # Valeur dérivée main : fullTextAnnotation.text strippé (2 lignes conservées).
    assert text == "Bonjour le monde\nseconde ligne"
    # Requête bien formée : endpoint annotate, clé en query, feature document, image.
    assert str(seen["path"]).endswith("/images:annotate")
    assert seen["key"] == "test-key"
    assert seen["feature"] == "DOCUMENT_TEXT_DETECTION"
    assert seen["has_content"] is True


def test_invoke_blank_page_returns_empty(tmp_path: Path) -> None:
    image = tmp_path / "blank.png"
    image.write_bytes(b"\x89PNG")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"responses": [{}]})

    text = _extract_text(_invoke_google_vision(
        image_path=str(image),
        deadline=Deadline.infinite(),
        api_key="k",
        transport=_transport(handler),
    ))
    assert text == ""


def test_invoke_api_error_raises(tmp_path: Path) -> None:
    image = tmp_path / "p.png"
    image.write_bytes(b"x")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"responses": [{"error": {"message": "quota dépassé"}}]}
        )

    with pytest.raises(AdapterStepError, match="quota dépassé"):
        _extract_text(_invoke_google_vision(
            image_path=str(image),
            deadline=Deadline.infinite(),
            api_key="k",
            transport=_transport(handler),
        ))


def test_invoke_http_status_error_raises(tmp_path: Path) -> None:
    image = tmp_path / "p.png"
    image.write_bytes(b"x")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "clé invalide"}})

    with pytest.raises(AdapterStepError, match="statut HTTP 403"):
        _extract_text(_invoke_google_vision(
            image_path=str(image),
            deadline=Deadline.infinite(),
            api_key="bad",
            transport=_transport(handler),
        ))
