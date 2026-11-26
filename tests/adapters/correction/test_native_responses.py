"""La correction structurée garde les réponses natives de ses appels (P5f 3).

Ici la forme diffère des autres moteurs : ``saknussemm`` appelle le fournisseur
**plusieurs fois** par page (un lot de lignes par appel, une nouvelle tentative
après une réponse inexploitable), puis décide ligne à ligne. Le texte corrigé
n'est donc pas la lecture d'**une** réponse, mais ce que les gardes ont retenu de
toutes. Ce qui se garde, c'est chaque corps reçu, dans l'ordre d'appel — une
réponse rejetée aussi : elle a été payée, et c'est elle qui explique la
nouvelle tentative.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType, native_json_bytes
from cinoc.domain.errors import RunCancelledError
from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Line,
    Region,
)
from cinoc.domain.usage import ResourceUsage
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

pytest.importorskip("saknussemm")

from cinoc.adapters.layout.saknussemm_correct import SaknussemmCorrector  # noqa: E402

_SECRET = "sk-correction-NE-DOIT-PAS-FUIR"


def _layout() -> CanonicalLayout:
    lignes = ("le ſoleil", "ſur la mer")
    return CanonicalLayout(
        pages=(
            LayoutPage(
                width=600,
                height=400,
                regions=(
                    Region(
                        id="R1",
                        geometry=Geometry(bbox=BBox(x=0, y=0, width=600, height=400)),
                        lines=tuple(
                            Line(
                                id=f"L{i + 1}",
                                text=texte,
                                geometry=Geometry(
                                    bbox=BBox(x=0, y=20 * i, width=500, height=18)
                                ),
                            )
                            for i, texte in enumerate(lignes)
                        ),
                    ),
                ),
            ),
        )
    )


def _fake(bodies: list[dict[str, Any]], *, invalid_first: bool) -> Any:
    """``httpx.AsyncClient`` servi par un ``MockTransport`` : corrige le ``ſ``
    de chaque ligne demandée. Ollama répond **en flux** (morceaux NDJSON, comme
    le vrai serveur sous ``stream: true``) : le corps reconstitué doit être
    celui du mode non diffusé, au caractère près, dans le sidecar.

    ``invalid_first`` : la première réponse n'est pas du JSON — ``saknussemm``
    la rejette (erreur transitoire) et rappelle.
    """
    real = httpx.AsyncClient

    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        demande = json.loads(json.loads(request.content)["messages"][1]["content"])
        lignes = [
            {
                "line_id": ligne["line_id"],
                "corrected_text": ligne["ocr_text"].replace("ſ", "s"),
            }
            for ligne in demande["lines"]
        ]
        contenu = json.dumps({"lines": lignes})
        if invalid_first and not bodies:
            contenu = "pas du JSON"
        if "mistral" in url:
            body: dict[str, Any] = {
                "id": f"cmpl-{len(bodies)}",
                "object": "chat.completion",
                "model": "mistral-small-2506",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": contenu},
                    }
                ],
                "usage": {
                    "prompt_tokens": 40,
                    "completion_tokens": 12,
                    "prompt_tokens_details": {"cached_tokens": 8},
                },
            }
            bodies.append(body)
            return httpx.Response(200, json=body)
        body = {
            "model": "qwen2.5:3b",
            "created_at": "2026-11-26T09:00:00Z",
            "message": {"role": "assistant", "content": contenu},
            "done": True,
            "done_reason": "stop",
            "eval_count": 12,
        }
        bodies.append(body)
        moitie = len(contenu) // 2
        morceaux = [
            {"model": "qwen2.5:3b", "created_at": "t",
             "message": {"role": "assistant", "content": part}, "done": False}
            for part in (contenu[:moitie], contenu[moitie:])
        ] + [{**body, "message": {"role": "assistant", "content": ""}}]
        lignes_ndjson = "".join(json.dumps(m) + "\n" for m in morceaux)
        return httpx.Response(200, content=lignes_ndjson.encode())

    return lambda **kw: real(transport=httpx.MockTransport(handle), **kw)


def _execute(
    tmp_path: Path,
    module: SaknussemmCorrector,
    control: RunControl | None = None,
) -> StepOutput:
    source = tmp_path / "in.layout.json"
    source.write_text(_layout().model_dump_json(), encoding="utf-8")
    return module.execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a",
                document_id="doc1",
                type=ArtifactType.LAYOUT,
                uri=str(source),
                content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="doc1",
            code_version="1",
            pipeline_name="p",
            workspace_uri=str(tmp_path / "ws"),
        ),
        control or RunControl(),
    )


def _correct(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    producer: str,
    *,
    invalid_first: bool,
) -> tuple[dict[ArtifactType, Artifact], list[dict[str, Any]], SaknussemmCorrector]:
    bodies: list[dict[str, Any]] = []
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake(bodies, invalid_first=invalid_first)
    )
    monkeypatch.setenv("MISTRAL_API_KEY", _SECRET)
    module = SaknussemmCorrector(label="corr", producer=producer, model="m")
    out = _execute(tmp_path, module)
    return dict(out.artifacts), bodies, module


@pytest.mark.parametrize(
    ("producer", "attendu"),
    [
        # Ollama : ``eval_count`` seul dans le corps — l'entrée reste inconnue.
        ("ollama", ResourceUsage(tokens_out=24)),
        ("mistral", ResourceUsage(tokens_in=80, tokens_out=24, tokens_cache_read=16)),
    ],
)
def test_the_correction_reports_the_tokens_of_every_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    producer: str,
    attendu: ResourceUsage,
) -> None:
    """Rouge avant S29a : l'étape ne déclarait aucun jeton (``usage`` absent),
    et ``mistral_structured`` ne lisait que ``prompt_tokens`` /
    ``completion_tokens`` — le cache se perdait. Deux réponses (une rejetée,
    payée quand même), lues comme les adaptateurs du fournisseur."""
    bodies: list[dict[str, Any]] = []
    monkeypatch.setattr(httpx, "AsyncClient", _fake(bodies, invalid_first=True))
    monkeypatch.setenv("MISTRAL_API_KEY", _SECRET)
    module = SaknussemmCorrector(label="corr", producer=producer, model="m")
    assert _execute(tmp_path, module).usage == attendu


class _Silent(BaseHTTPRequestHandler):
    """Reçoit la demande puis se tait 10 s (un modèle qui encode sa page)."""

    release = threading.Event()

    def do_POST(self) -> None:  # noqa: N802 — API de http.server
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.release.wait(10)
        try:
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except OSError:
            return

    def log_message(self, *_: object) -> None: ...


def test_a_stop_cuts_the_ollama_correction_in_flight(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """« Arrêter » pendant la correction Ollama → ``RunCancelledError`` en
    moins de 2 s. Rouge avant S29a : l'appel attendait la réponse (10 s), puis
    ``saknussemm`` rejouait le 500 reçu."""
    if sys.platform == "win32":  # ``shutdown`` d'un autre fil : mesuré sous Linux
        request.applymarker(pytest.mark.xfail(strict=False))
    handler = type("Handler", (_Silent,), {"release": threading.Event()})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        module = SaknussemmCorrector(
            label="corr", producer="ollama", model="m",
            host=f"http://127.0.0.1:{httpd.server_address[1]}",
        )
        control = RunControl()
        threading.Timer(0.5, control.trigger_cancel).start()
        started = time.monotonic()
        with pytest.raises(RunCancelledError):
            _execute(tmp_path, module, control)
        assert time.monotonic() - started < 2.0
    finally:
        handler.release.set()
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.parametrize(
    ("producer", "servi"), [("ollama", "qwen2.5:3b"), ("mistral", "mistral-small-2506")]
)
def test_the_correction_declares_the_model_its_responses_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, producer: str, servi: str
) -> None:
    """Demandé ``m``, servi celui que chaque réponse nomme (S9)."""
    bodies: list[dict[str, Any]] = []
    monkeypatch.setattr(httpx, "AsyncClient", _fake(bodies, invalid_first=False))
    monkeypatch.setenv("MISTRAL_API_KEY", _SECRET)
    source = tmp_path / "in.layout.json"
    source.write_text(_layout().model_dump_json(), encoding="utf-8")
    out = SaknussemmCorrector(label="corr", producer=producer, model="m").execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a", document_id="doc1", type=ArtifactType.LAYOUT,
                uri=str(source), content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="doc1", code_version="1", pipeline_name="p",
            workspace_uri=str(tmp_path / "ws"),
        ),
        RunControl(),
    )
    assert out.served_models == (servi,)


@pytest.mark.parametrize("producer", ["ollama", "mistral"])
def test_every_response_is_kept_in_call_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, producer: str
) -> None:
    artifacts, bodies, module = _correct(
        tmp_path, monkeypatch, producer, invalid_first=True
    )
    assert ArtifactType.NATIVE_JSON in module.output_types
    corrige = Path(artifacts[ArtifactType.CORRECTED_TEXT].uri or "").read_text("utf-8")
    assert "soleil" in corrige and "ſ" not in corrige  # la correction a eu lieu
    assert len(bodies) == 2  # une réponse rejetée, puis la bonne
    data = Path(artifacts[ArtifactType.NATIVE_JSON].uri or "").read_bytes()
    assert data == native_json_bytes({"responses": bodies})
    assert json.loads(data)["responses"][0][
        "message" if producer == "ollama" else "choices"
    ]


@pytest.mark.parametrize("producer", ["ollama", "mistral"])
def test_no_key_reaches_the_correction_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, producer: str
) -> None:
    artifacts, _, _ = _correct(tmp_path, monkeypatch, producer, invalid_first=False)
    for path in (tmp_path / "ws").iterdir():
        assert _SECRET not in path.read_text("utf-8", "replace"), path.name
    assert "Authorization" not in Path(
        artifacts[ArtifactType.NATIVE_JSON].uri or ""
    ).read_text("utf-8")


def test_the_rules_producer_calls_nothing_and_publishes_no_native_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "in.layout.json"
    source.write_text(_layout().model_dump_json(), encoding="utf-8")
    module = SaknussemmCorrector(label="regles")
    out = module.execute(
        {
            ArtifactType.LAYOUT: Artifact(
                id="a",
                document_id="doc1",
                type=ArtifactType.LAYOUT,
                uri=str(source),
                content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="doc1",
            code_version="1",
            pipeline_name="p",
            workspace_uri=str(tmp_path / "ws"),
        ),
        RunControl(),
    )
    assert ArtifactType.NATIVE_JSON not in module.output_types
    assert ArtifactType.NATIVE_JSON not in out.artifacts
