"""P5f 6 (S21) — un endpoint OpenAI-compatible **par instance**.

Défauts reproduits d'abord sur le code d'avant :

- la cible ne se réglait que par ``OPENAI_BASE_URL``, une variable **du
  processus** : deux instances d'un même run (OpenAI distant, vLLM local) ne
  pouvaient pas viser deux serveurs ;
- la clé venait toujours d'``OPENAI_API_KEY`` — la clé OpenAI partait donc au
  serveur auto-hébergé ;
- le créneau réseau était celui du **fournisseur** (``"openai"``) : un serveur
  local lent bloquait les appels à OpenAI, et inversement.

Aucun réseau : un faux SDK ``openai`` note ses kwargs de construction.
"""

from __future__ import annotations

import sys
import threading
import types
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters._resilience import call_resilient, endpoint_slot_key, network_slot
from cinoc.adapters.llm.openai import OpenAIAdapter
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError, DeadlineExceeded
from cinoc.pipeline.fingerprint import ModuleIdentity, step_fingerprint
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext
from tests.adapters._native_fakes import SdkResponse, wire

_OPENAI_KEY = "sk-openai-NE-DOIT-PAS-PARTIR-AU-SERVEUR-LOCAL"
_LOCAL = "http://127.0.0.1:8000/v1"


def _install(monkeypatch: pytest.MonkeyPatch, seen: list[dict[str, Any]]) -> None:
    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            seen.append(kwargs)

            def create(**_: Any) -> SdkResponse:
                return SdkResponse.model_validate(wire("llm", "openai", "stop"))

            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=create)
            )

    class _Erreur(Exception):
        pass

    module = types.ModuleType("openai")
    module.OpenAI = _Client  # type: ignore[attr-defined]
    module.OpenAIError = _Erreur  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.setenv("OPENAI_API_KEY", _OPENAI_KEY)


def _ctx(tmp_path: Path) -> RunContext:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    return RunContext(
        document_id="d1",
        code_version="t",
        pipeline_name="p",
        workspace_uri=str(workspace),
    )


def _raw(tmp_path: Path) -> dict[ArtifactType, Artifact]:
    path = tmp_path / "ocr.txt"
    path.write_text("le texte ocr", encoding="utf-8")
    return {
        ArtifactType.RAW_TEXT: Artifact(
            id="d1:ocr:raw_text",
            document_id="d1",
            type=ArtifactType.RAW_TEXT,
            uri=str(path),
        )
    }


def _execute(adapter: OpenAIAdapter, tmp_path: Path) -> None:
    adapter.execute(_raw(tmp_path), {}, _ctx(tmp_path), RunControl())


# --------------------------------------------------------------------------- #
# La cible est une saisie de l'instance, pas une variable du processus
# --------------------------------------------------------------------------- #


def test_two_instances_reach_two_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []
    _install(monkeypatch, seen)
    _execute(OpenAIAdapter(label="distant"), tmp_path)
    _execute(OpenAIAdapter(label="local", base_url=_LOCAL), tmp_path)
    assert [kw["base_url"] for kw in seen] == ["https://api.openai.com/v1", _LOCAL]


def test_the_process_environment_no_longer_redirects_an_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``OPENAI_BASE_URL`` visait **toutes** les instances : la cible d'une
    instance est sa saisie ; sans saisie, l'endpoint d'OpenAI."""
    seen: list[dict[str, Any]] = []
    _install(monkeypatch, seen)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://ailleurs.lan:9000/v1")
    adapter = OpenAIAdapter(label="distant")
    _execute(adapter, tmp_path)
    assert seen[0]["base_url"] == "https://api.openai.com/v1"
    assert adapter.effective_settings()["base_url"] == "https://api.openai.com/v1"


def test_the_endpoint_enters_the_settings_and_the_fingerprint() -> None:
    """Deux serveurs différents ne sont pas la même unité (reprise, provenance)."""
    a = OpenAIAdapter(label="x", base_url="http://127.0.0.1:8000/v1")
    b = OpenAIAdapter(label="x", base_url="http://127.0.0.1:8001/v1")
    assert a.effective_settings()["base_url"] == "http://127.0.0.1:8000/v1"
    from cinoc.domain.pipeline import PipelineStep

    step = PipelineStep(
        id="llm",
        kind="post_correction",
        adapter_name="openai:x",
        input_types=(ArtifactType.RAW_TEXT,),
        output_types=(ArtifactType.CORRECTED_TEXT,),
    )

    def fingerprint(adapter: OpenAIAdapter) -> str:
        return step_fingerprint(
            step,
            ModuleIdentity(
                version=adapter.version,
                settings=dict(adapter.effective_settings()),
                binaries={},
            ),
        )

    assert fingerprint(a) != fingerprint(b)


@pytest.mark.parametrize(
    ("url", "motif"),
    [
        ("ftp://127.0.0.1/v1", "http"),
        ("file:///etc/passwd", "http"),
        ("127.0.0.1:8000/v1", "http"),
        ("http:///v1", "hôte"),
        ("http://user:pw@127.0.0.1:8000/v1", "identifiants"),
        ("http://:pw@127.0.0.1:8000/v1", "identifiants"),
        ("http://127.0.0.1:8000/v1?token=abc", "query"),
        ("http://127.0.0.1:8000/v1#frag", "fragment"),
        ("http://127.0.0.1:99999/v1", "port"),
        ("", "http"),
    ],
)
def test_a_malformed_endpoint_is_refused_at_construction(url: str, motif: str) -> None:
    with pytest.raises(AdapterStepError, match=motif):
        OpenAIAdapter(label="x", base_url=url)


def test_a_non_string_endpoint_is_refused() -> None:
    with pytest.raises(AdapterStepError, match="base_url"):
        OpenAIAdapter(label="x", base_url=8000)


# --------------------------------------------------------------------------- #
# La clé : un nom de variable, jamais la valeur ; jamais celle d'OpenAI ailleurs
# --------------------------------------------------------------------------- #


def test_the_openai_key_never_goes_to_a_self_hosted_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []
    _install(monkeypatch, seen)
    _execute(OpenAIAdapter(label="local", base_url=_LOCAL), tmp_path)
    assert seen[0]["api_key"] != _OPENAI_KEY
    assert _OPENAI_KEY not in repr(seen)


def test_the_default_endpoint_keeps_openai_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []
    _install(monkeypatch, seen)
    _execute(OpenAIAdapter(label="distant"), tmp_path)
    assert seen[0]["api_key"] == _OPENAI_KEY


def test_api_key_env_names_the_variable_the_key_is_read_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []
    _install(monkeypatch, seen)
    monkeypatch.setenv("VLLM_API_KEY", "jeton-du-vllm")
    adapter = OpenAIAdapter(label="local", base_url=_LOCAL, api_key_env="VLLM_API_KEY")
    _execute(adapter, tmp_path)
    assert seen[0]["api_key"] == "jeton-du-vllm"
    # Le nom n'est pas un réglage de sortie, et la valeur n'entre nulle part.
    assert "jeton-du-vllm" not in repr(adapter.effective_settings())


def test_a_named_key_that_is_absent_is_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []
    _install(monkeypatch, seen)
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    adapter = OpenAIAdapter(label="local", base_url=_LOCAL, api_key_env="VLLM_API_KEY")
    with pytest.raises(AdapterStepError, match="VLLM_API_KEY"):
        _execute(adapter, tmp_path)
    assert seen == []  # aucun client construit, rien n'est parti


def test_the_default_key_absent_is_still_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, [])
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(AdapterStepError, match="OPENAI_API_KEY"):
        _execute(OpenAIAdapter(label="distant"), tmp_path)


@pytest.mark.parametrize(
    "name", ["", "sk-abc123", "MA CLE", "1KEY", "a" * 129, "KEY=VAL", 12]
)
def test_api_key_env_must_be_a_variable_name(name: object) -> None:
    with pytest.raises(AdapterStepError, match="api_key_env"):
        OpenAIAdapter(label="x", base_url=_LOCAL, api_key_env=name)


# --------------------------------------------------------------------------- #
# Le marqueur « auto-hébergé »
# --------------------------------------------------------------------------- #


def test_self_hosted_requires_a_custom_endpoint() -> None:
    """Déclarer « auto-hébergé » l'endpoint d'OpenAI serait un coût faux (0)."""
    with pytest.raises(AdapterStepError, match="self_hosted"):
        OpenAIAdapter(label="x", self_hosted=True)
    with pytest.raises(AdapterStepError, match="self_hosted"):
        OpenAIAdapter(label="x", base_url=_LOCAL, self_hosted="oui")
    OpenAIAdapter(label="x", base_url=_LOCAL, self_hosted=True)


def test_the_registry_passes_the_instance_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le constructeur du registre transmettait ``model``, ``role``… et
    **ignorait** tout autre réglage : ``base_url`` ne serait jamais arrivé."""
    seen: list[dict[str, Any]] = []
    _install(monkeypatch, seen)
    monkeypatch.setenv("VLLM_API_KEY", "jeton")
    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build(
        "openai:local",
        {
            "label": "local",
            "base_url": _LOCAL,
            "api_key_env": "VLLM_API_KEY",
            "self_hosted": True,
        },
    )
    assert isinstance(module, OpenAIAdapter)
    _execute(module, tmp_path)
    assert (seen[0]["base_url"], seen[0]["api_key"]) == (_LOCAL, "jeton")


# --------------------------------------------------------------------------- #
# Un créneau réseau par serveur, pas par fournisseur
# --------------------------------------------------------------------------- #


def test_the_slot_key_is_the_server() -> None:
    assert endpoint_slot_key("http://127.0.0.1:8000/v1") == "127.0.0.1:8000"
    assert endpoint_slot_key("http://LOCALHOST/v1") == "localhost:80"
    assert endpoint_slot_key("https://api.openai.com/v1") == "api.openai.com:443"
    # Même serveur par deux chemins : même créneau.
    assert endpoint_slot_key("http://127.0.0.1:11434/v1") == endpoint_slot_key(
        "http://127.0.0.1:11434"
    )


def test_two_servers_do_not_block_each_other(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINOC_NETWORK_CONCURRENCY", "1")
    busy = "http://s21-lent.lan:8000/v1"
    slot = network_slot(endpoint_slot_key(busy))
    slot.acquire()
    try:
        # Un autre serveur du même fournisseur passe…
        assert (
            call_resilient(
                "openai",
                lambda: "ok",
                endpoint="http://s21-rapide.lan:8000/v1",
                deadline=Deadline.in_seconds(1.0),
            )
            == "ok"
        )
        # … le même serveur attend son créneau.
        with pytest.raises(DeadlineExceeded, match="créneau"):
            call_resilient(
                "openai",
                lambda: "ok",
                endpoint=busy,
                deadline=Deadline.in_seconds(0.05),
            )
    finally:
        slot.release()


def test_the_adapter_takes_the_slot_of_its_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, [])
    monkeypatch.setenv("CINOC_NETWORK_CONCURRENCY", "1")
    slot = network_slot(endpoint_slot_key("http://s21-occupe.lan:8000/v1"))
    slot.acquire()
    done = threading.Event()
    try:
        # Le serveur occupé ne retient pas une instance qui en vise un autre.
        libre = OpenAIAdapter(label="b", base_url="http://s21-libre.lan:8000/v1")
        _execute(libre, tmp_path)
        done.set()
        with pytest.raises(AdapterStepError, match="créneau"):
            _execute(
                OpenAIAdapter(
                    label="a", base_url="http://s21-occupe.lan:8000/v1", timeout=0.05
                ),
                tmp_path,
            )
    finally:
        slot.release()
    assert done.is_set()
