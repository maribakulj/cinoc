"""Upload de corpus côté HTTP : CSRF, 201 + résumé, 422 sur archive hostile."""

from __future__ import annotations

import io
import random
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER

_CSRF = {CSRF_HEADER: "1"}
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(reports_dir=tmp_path / "rep", uploads_dir=tmp_path / "up",
                   rate_limit=1000)
    )


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, payload in entries.items():
            zf.writestr(name, payload)
    return buf.getvalue()


def _upload(client: TestClient, data: bytes, *, csrf: bool = True) -> object:
    headers = _CSRF if csrf else {}
    files = {"file": ("corpus.zip", data, "application/zip")}
    return client.post("/api/corpus", files=files, headers=headers)


def test_upload_without_csrf_is_403(tmp_path: Path) -> None:
    resp = _upload(_client(tmp_path), _zip({"a.png": _PNG}), csrf=False)
    assert resp.status_code == 403


def test_upload_ok_returns_summary(tmp_path: Path) -> None:
    client = _client(tmp_path)
    resp = _upload(client, _zip({"a.png": _PNG, "a.gt.txt": b"v", "b.png": _PNG}))
    assert resp.status_code == 201
    body = resp.json()
    assert body["n_documents"] == 2
    # la réponse de création EST le résumé (corpus_id + documents) — pas de GET.
    assert set(body["documents"]) == {"a", "b"}


def test_hostile_archive_is_422(tmp_path: Path) -> None:
    resp = _upload(_client(tmp_path), _zip({"../escape.png": _PNG}))
    assert resp.status_code == 422


def test_bad_zip_is_422(tmp_path: Path) -> None:
    resp = _upload(_client(tmp_path), b"not a zip")
    assert resp.status_code == 422


def test_stem_collision_is_422_not_500(tmp_path: Path) -> None:
    # archive « sûre mais bancale » (deux images de même radical) → 422, jamais 500.
    jpeg = b"\xff\xd8\xff" + b"\x00" * 32
    resp = _upload(_client(tmp_path), _zip({"a.png": _PNG, "a.jpg": jpeg}))
    assert resp.status_code == 422


def test_oversized_upload_is_413(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # plafond abaissé (≠ envoyer 200 Mo) : au-delà → 413 net, avant tout dézippage.
    monkeypatch.setattr("cinoc.app.corpus_upload.LOCAL_MAX_ZIP_BYTES", 64)
    resp = _upload(_client(tmp_path), b"x" * 256)
    assert resp.status_code == 413


def _over_public_cap() -> bytes:
    """Un ZIP **réel** de plus de 25 Mo, fabriqué à la volée : deux pages de
    13 Mo d'octets pseudo-aléatoires (incompressibles), rangées sans
    compression — rien de lourd n'est committé."""
    page = b"\x89PNG\r\n\x1a\n" + random.Random(0).randbytes(13 * 2**20)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("p1.png", page)
        zf.writestr("p2.png", page)
    data = buf.getvalue()
    assert len(data) > 25 * 2**20
    return data


def _client_in(tmp_path: Path, *, public_mode: bool) -> TestClient:
    return TestClient(
        create_app(reports_dir=tmp_path / "rep", uploads_dir=tmp_path / "up",
                   data_dir=tmp_path / "data", rate_limit=1000,
                   public_mode=public_mode)
    )


def test_a_local_server_accepts_an_archive_over_the_public_cap(tmp_path: Path) -> None:
    """Hors mode public, le dépôt web prend le plafond d'une archive locale (celui
    de ``cinoc corpus import zip``) : un corpus de 29 Mo ne se refuse plus à la
    page d'un serveur que son opérateur lance chez lui (D-310)."""
    resp = _upload(_client_in(tmp_path, public_mode=False), _over_public_cap())
    assert resp.status_code == 201, resp.text[:300]
    assert resp.json()["n_documents"] == 2


def test_a_public_server_refuses_it_and_names_its_cap(tmp_path: Path) -> None:
    resp = _upload(_client_in(tmp_path, public_mode=True), _over_public_cap())
    assert resp.status_code == 413
    assert "25 Mo" in resp.json()["detail"]
