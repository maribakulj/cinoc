"""D18 du pilote (D-281), fermé en S22 (D-294) : un modèle Ollama est tracé par
le **digest** de ses poids, pas par son tag.

Un tag se réaffecte (``ollama pull qwen…:3b`` après une mise à jour amont) : le
même nom désigne alors d'autres poids. Le digest lu dans ``/api/tags`` entre au
manifeste (``system_binaries_lock``) et dans la **clé d'unité** — une archive
produite sous un autre digest est ré-exécutée, pas relue comme si c'était le
même modèle. C'est voulu : les archives Ollama antérieures à S22, sans digest,
sont ré-exécutées une fois.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from cinoc.adapters.llm.ollama import OllamaAdapter
from cinoc.app.resume import declared_inputs, unit_key
from cinoc.app.run_manifest import module_identities
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec

_TAGS = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "cassettes"
        / "models"
        / "ollama.json"
    ).read_text("utf-8")
)["responses"]["tags"]
_DIGEST = _TAGS["models"][0]["digest"]
_REAL_CLIENT = httpx.Client


def _serve(monkeypatch: pytest.MonkeyPatch, tags: dict[str, Any]) -> None:
    real = _REAL_CLIENT

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags", request.url
        return httpx.Response(200, json=tags)

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )


def test_the_digest_of_the_served_tag_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _TAGS)
    adapter = OllamaAdapter(label="o", model="qwen-test:3b")
    assert adapter.system_binaries() == {"ollama:qwen-test:3b": _DIGEST}


def test_a_name_without_tag_is_traced_as_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _TAGS)
    binaries = OllamaAdapter(label="o", model="texte-test").system_binaries()
    assert list(binaries) == ["ollama:texte-test:latest"]


def test_an_absent_model_or_a_silent_server_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _TAGS)
    assert OllamaAdapter(label="o", model="absent:1b").system_binaries() == {}
    real = _REAL_CLIENT

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé", request=request)

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(refuse), **kw)
    )
    assert OllamaAdapter(label="o", model="qwen-test:3b").system_binaries() == {}


def _key(tmp_path: Path) -> str:
    image = tmp_path / "d.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    step = PipelineStep(
        id="vlm",
        kind="transcription",
        adapter_name="ollama:o",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    pipeline = PipelineSpec(
        name="p", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
    )
    document = DocumentRef(id="d", image_uri=str(image))
    spec = RunSpec(
        corpus=CorpusSpec(name="c", documents=(document,)),
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="t", candidate_types=(ArtifactType.RAW_TEXT,), metric_names=()
                ),
            )
        ),
        adapter_kwargs={
            "ollama:o": {"label": "o", "model": "qwen-test:3b", "role": "zero_shot"}
        },
    )
    modules = {
        "ollama:o": OllamaAdapter(label="o", model="qwen-test:3b", role="zero_shot")
    }
    key = unit_key(
        pipeline=pipeline,
        identities=module_identities(spec, modules),
        document=document,
        inputs=declared_inputs(pipeline, modules, document),
    )
    assert key is not None
    return key


def test_another_digest_under_the_same_tag_is_another_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch, _TAGS)
    before = _key(tmp_path)
    assert _key(tmp_path) == before  # déterministe
    repulled = json.loads(json.dumps(_TAGS))
    repulled["models"][0]["digest"] = "f" * 64
    _serve(monkeypatch, repulled)
    assert _key(tmp_path) != before
