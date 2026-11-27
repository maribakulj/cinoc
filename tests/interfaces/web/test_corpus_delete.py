"""Suppression de corpus : ``CorpusStore.delete`` + ``DELETE /api/corpus/{id}``."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from cinoc.app.corpus_upload import CorpusStore
from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER

_CSRF = {CSRF_HEADER: "1"}
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.png", _PNG)
        zf.writestr("a.gt.txt", b"verite")
    return buf.getvalue()


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(reports_dir=tmp_path, rate_limit=1000))


def test_store_delete_removes_registry_and_folder(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path)
    corpus_id, _ = store.save("c", io.BytesIO(_zip_bytes()), max_zip_bytes=2**20)
    assert store.get(corpus_id) is not None
    assert (tmp_path / corpus_id).is_dir()
    assert store.delete(corpus_id) is True
    assert store.get(corpus_id) is None
    assert not (tmp_path / corpus_id).exists()
    assert store.delete(corpus_id) is False  # idempotent : déjà supprimé


def _upload(client: TestClient) -> str:
    files = {"file": ("c.zip", _zip_bytes(), "application/zip")}
    return client.post("/api/corpus", files=files, headers=_CSRF).json()["corpus_id"]


def test_delete_route_then_gone(tmp_path: Path) -> None:
    client = _client(tmp_path)
    corpus_id = _upload(client)  # 201 → le corpus existe
    resp = client.delete(f"/api/corpus/{corpus_id}", headers=_CSRF)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    # re-supprimer un corpus déjà parti → 404 (preuve qu'il a bien disparu).
    assert client.delete(f"/api/corpus/{corpus_id}", headers=_CSRF).status_code == 404


def test_delete_unknown_is_404(tmp_path: Path) -> None:
    resp = _client(tmp_path).delete("/api/corpus/nope", headers=_CSRF)
    assert resp.status_code == 404


def test_delete_without_csrf_is_403(tmp_path: Path) -> None:
    assert _client(tmp_path).delete("/api/corpus/whatever").status_code == 403
