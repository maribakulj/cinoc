"""Lanceur web de la **post-correction structurée** : ses cinq gardes.

`cinoc correct` existait depuis août 2026 sans surface web (dette
`correction-web`, `D-228`). Ce qui se joue ici n'est pas seulement d'exposer une
route : c'est de la rendre **incapable de mentir**.

Le piège est silencieux. Un corpus déposé en images + ALTO, sans transcription à
part, voit sa vérité terrain **dérivée de cet ALTO** — c'est-à-dire du texte dont
part le correcteur. Le comparer à lui-même donne un CER nul pour la sortie brute
et n'impute au correcteur que ses propres changements : le rapport conclurait
« corriger dégrade », quel que soit le correcteur. La route refuse ce corpus.
"""

from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER

_CSRF = {CSRF_HEADER: "1"}
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'
_ALTO = (
    f'<alto {_NS}><Layout><Page ID="P1" WIDTH="600" HEIGHT="400"><PrintSpace>'
    '<TextBlock ID="B1">'
    '<TextLine ID="L1" HPOS="10" VPOS="10" WIDTH="300" HEIGHT="30">'
    '<String CONTENT="le" WC="0.9"/><SP/><String CONTENT="ſoleil"/></TextLine>'
    "</TextBlock></PrintSpace></Page></Layout></alto>"
).encode()

_a_saknussemm = importlib.util.find_spec("saknussemm") is not None


def _client(tmp_path: Path, *, public_mode: bool = False) -> TestClient:
    return TestClient(
        create_app(reports_dir=tmp_path, rate_limit=1000, public_mode=public_mode)
    )


def _upload(client: TestClient, *, transcription: bool) -> str:
    """Dépose un corpus ALTO+image, avec ou sans transcription **à part**."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.png", _PNG)
        zf.writestr("a.xml", _ALTO)
        if transcription:
            zf.writestr("a.gt.txt", "le soleil")
    files = {"file": ("c.zip", buf.getvalue(), "application/zip")}
    return client.post("/api/corpus", files=files, headers=_CSRF).json()["corpus_id"]


def _post(client: TestClient, body: dict) -> object:
    return client.post("/api/runs/correction", headers=_CSRF, json=body)


def test_write_is_csrf_protected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    resp = client.post("/api/runs/correction", json={"corpus_id": "x"})
    assert resp.status_code == 403


def test_public_mode_refuses_the_correction(tmp_path: Path) -> None:
    """Le producteur utile parle à un LLM local, qu'un Space exposé n'a pas."""
    client = _client(tmp_path, public_mode=True)
    resp = _post(client, {"corpus_id": "peu-importe"})
    assert resp.status_code == 403
    assert "public" in resp.json()["detail"]


def test_an_unknown_corpus_is_404(tmp_path: Path) -> None:
    resp = _post(_client(tmp_path), {"corpus_id": "inexistant"})
    # 409 si la lib manque sur la machine de test : la garde de dispo passe
    # avant celle du corpus, et c'est voulu (on ne cherche pas un corpus pour
    # une capacité indisponible).
    assert resp.status_code in {404, 409}


@pytest.mark.skipif(not _a_saknussemm, reason="extra [saknussemm] absent")
def test_a_ground_truth_derived_from_the_alto_is_refused(tmp_path: Path) -> None:
    """**Le refus qui compte.** Sans lui, le banc publierait un verdict inversé."""
    client = _client(tmp_path)
    corpus_id = _upload(client, transcription=False)

    resp = _post(client, {"corpus_id": corpus_id})

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "propre ALTO" in detail
    # Et il dit quoi faire, sinon le refus n'est qu'un mur.
    assert ".gt.txt" in detail


@pytest.mark.skipif(not _a_saknussemm, reason="extra [saknussemm] absent")
def test_a_corpus_with_its_own_transcription_is_accepted(tmp_path: Path) -> None:
    """Une transcription **à part** : là, il y a quelque chose à mesurer."""
    client = _client(tmp_path)
    corpus_id = _upload(client, transcription=True)

    resp = _post(client, {"corpus_id": corpus_id, "producer": "rules"})

    assert resp.status_code == 201, resp.json()
    assert resp.json()["job_id"]


@pytest.mark.skipif(not _a_saknussemm, reason="extra [saknussemm] absent")
def test_ollama_without_a_model_is_422(tmp_path: Path) -> None:
    """Le planificateur l'exige ; la route le traduit au lieu de laisser passer."""
    client = _client(tmp_path)
    corpus_id = _upload(client, transcription=True)

    resp = _post(client, {"corpus_id": corpus_id, "producer": "ollama"})

    assert resp.status_code == 422
    assert "model" in resp.json()["detail"]


@pytest.mark.skipif(not _a_saknussemm, reason="extra [saknussemm] absent")
def test_an_unknown_producer_is_422(tmp_path: Path) -> None:
    client = _client(tmp_path)
    corpus_id = _upload(client, transcription=True)

    resp = _post(client, {"corpus_id": corpus_id, "producer": "magique"})

    assert resp.status_code == 422


def test_the_library_absence_is_named_before_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """409 **avant** le lancement, pas un échec d'étape en plein run."""
    from cinoc.app import engines
    from cinoc.app.engines import EngineStatus

    monkeypatch.setattr(
        engines,
        "correction_status",
        lambda **_: EngineStatus(
            kind="saknussemm", label="x", available=False, detail="absent"
        ),
    )
    monkeypatch.setattr(
        "cinoc.interfaces.web.app.correction_status",
        lambda: EngineStatus(
            kind="saknussemm", label="x", available=False, detail="absent"
        ),
    )
    resp = _post(_client(tmp_path), {"corpus_id": "x"})
    assert resp.status_code == 409
    assert "saknussemm" in resp.json()["detail"]
