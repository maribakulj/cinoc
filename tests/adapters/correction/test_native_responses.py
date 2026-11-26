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
from pathlib import Path
from typing import Any

import httpx
import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType, native_json_bytes
from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Line,
    Region,
)
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

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


def _fake(bodies: list[dict[str, Any]], *, invalid_first: bool) -> type:
    """Faux ``httpx.AsyncClient`` : corrige le ``ſ`` de chaque ligne demandée.

    ``invalid_first`` : la première réponse n'est pas du JSON — ``saknussemm``
    la rejette (erreur transitoire) et rappelle.
    """

    class _Fake:
        def __init__(self, **_: Any) -> None: ...

        async def __aenter__(self) -> _Fake:
            return self

        async def __aexit__(self, *_: object) -> bool:
            return False

        async def post(
            self,
            url: str,
            json: Any = None,
            headers: Any = None,  # noqa: A002
        ) -> httpx.Response:
            import json as j

            demande = j.loads(json["messages"][1]["content"])
            lignes = [
                {
                    "line_id": ligne["line_id"],
                    "corrected_text": ligne["ocr_text"].replace("ſ", "s"),
                }
                for ligne in demande["lines"]
            ]
            contenu = j.dumps({"lines": lignes})
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
                    "usage": {"prompt_tokens": 40, "completion_tokens": 12},
                }
            else:
                body = {
                    "model": "qwen2.5:3b",
                    "created_at": "2026-11-26T09:00:00Z",
                    "message": {"role": "assistant", "content": contenu},
                    "done": True,
                    "done_reason": "stop",
                    "eval_count": 12,
                }
            bodies.append(body)
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    return _Fake


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
    source = tmp_path / "in.layout.json"
    source.write_text(_layout().model_dump_json(), encoding="utf-8")
    module = SaknussemmCorrector(label="corr", producer=producer, model="m")
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
    return dict(out.artifacts), bodies, module


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
