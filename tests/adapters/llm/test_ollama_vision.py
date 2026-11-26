"""L'adapter ollama connaît les trois modes, dont la vision.

Il était **``text_only`` en dur**, alors que le planificateur lui passait déjà
un ``role`` : choisir « OCR → VLM » avec un modèle local produisait un run
**texte, en silence**. L'étape déclarait `IMAGE` en entrée, l'adapter ne la
lisait pas, et rien ne le disait — ni erreur, ni avertissement, juste un
résultat qui ressemble à une correction vision et n'en est pas.

Des poids locaux figés sont **plus** reproductibles qu'un instantané d'API
susceptible d'être déprécié : un modèle vision installé en local devrait
pouvoir concourir.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.llm.ollama import OllamaAdapter
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_MODES = ("text_only", "text_and_image", "zero_shot")


def test_each_mode_declares_the_types_it_actually_consumes() -> None:
    attendu = {
        "text_only": ({ArtifactType.RAW_TEXT}, {ArtifactType.CORRECTED_TEXT}),
        "text_and_image": (
            {ArtifactType.RAW_TEXT, ArtifactType.IMAGE},
            {ArtifactType.CORRECTED_TEXT},
        ),
        "zero_shot": ({ArtifactType.IMAGE}, {ArtifactType.RAW_TEXT}),
    }
    for mode in _MODES:
        adapter = OllamaAdapter(label="x", model="m", role=mode)
        entrees, sorties = attendu[mode]
        assert adapter.input_types == frozenset(entrees), mode
        assert adapter.output_types == frozenset(
            {*sorties, ArtifactType.NATIVE_JSON}
        ), mode


def test_every_mode_is_still_a_module() -> None:
    for mode in _MODES:
        assert isinstance(OllamaAdapter(label="x", model="m", role=mode), Module)


def test_an_unknown_mode_is_refused() -> None:
    with pytest.raises(AdapterStepError):
        OllamaAdapter(label="x", model="m", role="devine")


def test_the_image_travels_in_the_images_array(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le format d'ollama n'est **pas** celui d'OpenAI.

    L'image est du base64 **nu** dans un tableau ``images`` du message : pas
    d'URI ``data:``, pas de type de média. Une ``data:`` passée telle quelle est
    ignorée en silence, et le modèle répond sans avoir rien vu — une réponse
    plausible, donc indétectable sans ce test.
    """
    envoye: dict[str, Any] = {}

    class _Reponse:
        def raise_for_status(self) -> None: ...

        def json(self) -> dict[str, Any]:
            return {
                "message": {"content": "texte transcrit"},
                "prompt_eval_count": 3,
                "eval_count": 5,
            }

    class _Client:
        def __init__(self, **_: Any) -> None: ...

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_: object) -> None: ...

        def close(self) -> None: ...

        def post(self, url: str, json: dict[str, Any]) -> _Reponse:  # noqa: A002
            envoye["url"] = url
            envoye["payload"] = json
            return _Reponse()

    import httpx

    monkeypatch.setattr(httpx, "Client", _Client)

    octets = b"\x89PNG\r\n\x1a\n de faux pixels"
    image = tmp_path / "page.png"
    image.write_bytes(octets)

    adapter = OllamaAdapter(label="x", model="m", role="zero_shot")
    adapter.execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="i",
                document_id="d",
                type=ArtifactType.IMAGE,
                uri=str(image),
                content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="d",
            code_version="1",
            pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )

    message = envoye["payload"]["messages"][0]
    assert message["images"] == [base64.b64encode(octets).decode()]
    assert "data:" not in json.dumps(message["images"])
    assert envoye["url"].endswith("/api/chat")


def test_text_only_sends_no_images_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une clé ``images`` vide n'est pas neutre pour tous les modèles : absente
    en mode texte, pas présente-et-vide."""
    envoye: dict[str, Any] = {}

    class _Reponse:
        def raise_for_status(self) -> None: ...

        def json(self) -> dict[str, Any]:
            return {"message": {"content": "corrigé"}}

    class _Client:
        def __init__(self, **_: Any) -> None: ...

        def close(self) -> None: ...

        def post(self, url: str, json: dict[str, Any]) -> _Reponse:  # noqa: A002
            envoye["payload"] = json
            return _Reponse()

    import httpx

    monkeypatch.setattr(httpx, "Client", _Client)

    source = tmp_path / "brut.txt"
    source.write_text("du texte à corriger", encoding="utf-8")
    OllamaAdapter(label="x", model="m", role="text_only").execute(
        {
            ArtifactType.RAW_TEXT: Artifact(
                id="t",
                document_id="d",
                type=ArtifactType.RAW_TEXT,
                uri=str(source),
                content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="d",
            code_version="1",
            pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    assert "images" not in envoye["payload"]["messages"][0]


def test_the_registry_passes_the_mode_through() -> None:
    """Le planificateur envoyait déjà un ``role`` ; il était perdu en route."""
    from cinoc.app.modules.registry import ModuleRegistry, register_default_modules

    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build(
        "ollama:vlm", {"label": "vlm", "model": "m", "role": "zero_shot"}
    )
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert module.output_types == frozenset(
        {ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON}
    )
