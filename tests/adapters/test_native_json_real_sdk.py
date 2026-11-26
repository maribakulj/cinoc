"""Le sidecar ``NATIVE_JSON`` sous les **vrais** SDK (extras), transport factice.

``tests/adapters/test_native_json.py`` prouve le chemin sur des SDK factices ; ce
fichier-ci prouve l'hypothèse dont il dépend — que ``model_dump`` d'une réponse
de SDK est **le corps reçu**, sans l'identifiant de requête que le SDK range en
attribut privé (``_request_id``, ``_workspace_id``). Le transport rend la cassette
et un en-tête d'identifiant **qui contient la clé** : il ne doit atteindre aucun
fichier. Ignoré sans l'extra (``pip install 'cinoc[openai]'`` etc.) ; aucun réseau.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType, native_json_bytes
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.adapters._native_fakes import SECRET, wire


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: str,
    module: Module,
) -> dict[ArtifactType, Artifact]:
    monkeypatch.setenv(env, SECRET)
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nx")
    out = module.execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="p:i", document_id="p", type=ArtifactType.IMAGE, uri=str(image)
            )
        },
        {},
        RunContext(
            document_id="p",
            code_version="t",
            pipeline_name="x",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    return dict(out.artifacts)


def _check(
    tmp_path: Path,
    artifacts: dict[ArtifactType, Artifact],
    body: dict[str, Any],
    seen: list[dict[str, str]],
    read: Callable[[Any], str],
) -> None:
    assert any(SECRET in value for headers in seen for value in headers.values())
    data = Path(artifacts[ArtifactType.NATIVE_JSON].uri or "").read_bytes()
    assert data == native_json_bytes(body)
    for path in tmp_path.iterdir():
        assert SECRET not in path.read_text("utf-8", "replace"), path.name
    texte = next(
        a
        for t, a in artifacts.items()
        if t in (ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT)
    )
    assert read(json.loads(data)) == Path(texte.uri or "").read_text("utf-8")


def _handler(module: Any, body: dict[str, Any], seen: list[dict[str, str]]) -> Any:
    def handle(request: Any) -> Any:
        seen.append(dict(request.headers))
        return module.Response(
            200, json=body, headers={"x-request-id": f"req_{SECRET}"}
        )

    return module.MockTransport(handle)


def test_openai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    openai = pytest.importorskip("openai")
    import httpx

    from cinoc.adapters.llm.openai import OpenAIAdapter, _completion_from_chat

    body, seen = wire("llm", "openai", "stop"), []
    monkeypatch.setattr(
        openai,
        "OpenAI",
        functools.partial(
            openai.OpenAI,
            http_client=httpx.Client(transport=_handler(httpx, body, seen)),
            max_retries=0,
        ),
    )
    module = OpenAIAdapter(model="m", label="o", role="zero_shot")
    artifacts = _run(tmp_path, monkeypatch, "OPENAI_API_KEY", module)
    _check(tmp_path, artifacts, body, seen, lambda n: _completion_from_chat(n).text)


def test_anthropic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    anthropic = pytest.importorskip("anthropic")
    # anthropic 2.x transporte par ``httpx2`` et refuse un client ``httpx``.
    httpx2 = pytest.importorskip("httpx2")

    from cinoc.adapters.llm.anthropic import AnthropicAdapter, _completion_from_message

    body, seen = wire("llm", "anthropic", "end_turn"), []
    monkeypatch.setattr(
        anthropic,
        "Anthropic",
        functools.partial(
            anthropic.Anthropic,
            http_client=httpx2.Client(transport=_handler(httpx2, body, seen)),
            max_retries=0,
        ),
    )
    module = AnthropicAdapter(model="m", label="c", role="zero_shot")
    artifacts = _run(tmp_path, monkeypatch, "ANTHROPIC_API_KEY", module)
    _check(tmp_path, artifacts, body, seen, lambda n: _completion_from_message(n).text)


@pytest.mark.parametrize("ocr", [False, True], ids=["chat", "ocr"])
def test_mistralai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ocr: bool) -> None:
    # mistralai 3.x : le client vit dans ``mistralai.client`` et transporte par
    # ``httpx2`` (``client=`` en exige un).
    mistralai = pytest.importorskip("mistralai.client")
    httpx2 = pytest.importorskip("httpx2")

    from cinoc.adapters.llm.mistral import MistralAdapter, _completion_from_chat
    from cinoc.adapters.ocr.mistral_ocr import MistralOCRAdapter, _text_from_response

    body = (
        wire("ocr", "mistral_ocr", "folio_b") if ocr else wire("llm", "mistral", "stop")
    )
    seen: list[dict[str, str]] = []
    monkeypatch.setattr(
        mistralai,
        "Mistral",
        functools.partial(
            mistralai.Mistral,
            client=httpx2.Client(transport=_handler(httpx2, body, seen)),
        ),
    )
    module: Module = (
        MistralOCRAdapter(model="m", label="m")
        if ocr
        else MistralAdapter(model="m", label="p", role="zero_shot")
    )
    read: Callable[[Any], str] = (
        _text_from_response if ocr else (lambda n: _completion_from_chat(n).text)
    )
    artifacts = _run(tmp_path, monkeypatch, "MISTRAL_API_KEY", module)
    _check(tmp_path, artifacts, body, seen, read)


def test_mistral_ocr_blocks_reach_the_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sous le vrai SDK 3.x : la requête **porte** ``include_blocks`` et la
    granularité ``block``, et la réponse OCR 4 de la cassette garde ses blocs et
    leurs confiances au décodage — la 1.x les retirait (D-291) —, donc le
    sidecar les garde et le ``LAYOUT`` est publié."""
    mistralai = pytest.importorskip("mistralai.client")
    httpx2 = pytest.importorskip("httpx2")

    from cinoc.adapters.ocr._mistral_layout import layout_from_response
    from cinoc.adapters.ocr.mistral_ocr import MistralOCRAdapter
    from cinoc.domain.layout import CanonicalLayout

    body = wire("ocr", "mistral_ocr_4", "blocs")
    requests: list[Any] = []

    def handle(request: Any) -> Any:
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=body)

    monkeypatch.setattr(
        mistralai,
        "Mistral",
        functools.partial(
            mistralai.Mistral,
            client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        ),
    )
    module = MistralOCRAdapter(model="m", label="m")
    artifacts = _run(tmp_path, monkeypatch, "MISTRAL_API_KEY", module)
    (sent,) = requests
    assert sent["include_blocks"] is True
    assert sent["confidence_scores_granularity"] == "block"
    sidecar = Path(artifacts[ArtifactType.NATIVE_JSON].uri or "")
    native = json.loads(sidecar.read_bytes())
    assert native == body  # blocs et confiances gardés au décodage
    layout = CanonicalLayout.model_validate_json(
        Path(artifacts[ArtifactType.LAYOUT].uri or "").read_bytes()
    )
    assert layout == layout_from_response(body)
    assert [r.confidence for r in layout.pages[0].regions][0] is not None
