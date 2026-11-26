"""« Arrêter » un run lancé depuis la page : la route d'annulation (D-299).

Un banc lancé du web engage des appels facturés ; la page doit pouvoir
l'arrêter. La route passe par ``RunControl`` — l'annulation coopérative que la
CLI déclenche par Ctrl-C : le module en cours sonde le signal et rend la main,
aucun processus n'est tué. Un run arrêté n'écrit **pas** de rapport partiel.
"""

from __future__ import annotations

import io
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER

_CSRF = {CSRF_HEADER: "1"}
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            reports_dir=tmp_path / "reports",
            data_dir=tmp_path / "data",
            uploads_dir=tmp_path / "uploads",
            rate_limit=1000,
        )
    )


def _corpus(client: TestClient) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for doc in ("p1", "p2"):
            zf.writestr(f"{doc}.png", _PNG)
            zf.writestr(f"{doc}.gt.txt", "le soleil")
            zf.writestr(f"{doc}.ocr.txt", "le so1eil")
    reponse = client.post(
        "/api/corpus",
        files={"file": ("c.zip", buf.getvalue(), "application/zip")},
        headers=_CSRF,
    )
    assert reponse.status_code == 201, reponse.json()
    return str(reponse.json()["corpus_id"])


def _etat(client: TestClient, job_id: str, voulu: set[str]) -> dict:
    limite = time.time() + 30.0
    while time.time() < limite:
        corps = dict(client.get(f"/api/runs/{job_id}").json())
        if corps["state"] in voulu:
            return corps
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} : jamais {voulu}")


@pytest.fixture
def moteur_lent(monkeypatch: pytest.MonkeyPatch) -> threading.Event:
    """Le rejeu ``precomputed`` devient un moteur **lent** : il attend le signal
    d'annulation comme un appel réseau en vol, et le dit quand il démarre."""
    from cinoc.adapters.ocr.precomputed import PrecomputedTextAdapter

    demarre = threading.Event()

    def lent(self: object, inputs: object, params: object, context: object,
             control: object) -> object:
        demarre.set()
        assert hasattr(control, "wait") and hasattr(control, "raise_if_cancelled")
        control.wait(20.0)
        control.raise_if_cancelled()
        raise AssertionError("le moteur lent n'a pas été arrêté")

    monkeypatch.setattr(PrecomputedTextAdapter, "execute", lent)
    return demarre


def test_stopping_a_running_job_cancels_it_without_a_report(
    tmp_path: Path, moteur_lent: threading.Event
) -> None:
    client = _client(tmp_path)
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={
            "corpus_id": _corpus(client),
            "entries": [{"recipe": "ocr_simple", "choices": {"ocr": "precomputed"}}],
        },
    )
    assert reponse.status_code == 201, reponse.json()
    job_id = reponse.json()["job_id"]
    assert moteur_lent.wait(10.0), "le moteur n'a jamais démarré"

    arret = client.post(f"/api/runs/{job_id}/cancel", headers=_CSRF)

    assert arret.status_code == 200
    assert arret.json() == {"cancelled": True}
    job = _etat(client, job_id, {"done", "failed", "cancelled"})
    assert job["state"] == "cancelled"
    assert job.get("report_name") is None
    assert not list((tmp_path / "reports").glob("*.json"))
    # Un job fini ne se ré-annule pas : la page le dit (« déjà terminé »).
    again = client.post(f"/api/runs/{job_id}/cancel", headers=_CSRF)
    assert again.json() == {"cancelled": False}


def test_the_stop_button_calls_the_cancel_route(tmp_path: Path) -> None:
    """La page porte le bouton (FR/EN) et son script appelle la route."""
    script = (
        Path(__file__).resolve().parents[3]
        / "cinoc/interfaces/web/static/js/benchmark.js"
    ).read_text(encoding="utf-8")
    assert '"/cancel"' in script
    client = _client(tmp_path)
    fr = client.get("/benchmark").text
    en = client.get("/benchmark?lang=en").text
    assert 'id="run-stop"' in fr and ">Arrêter</button>" in fr
    assert ">Stop</button>" in en
    assert 'data-state-cancelled="Arrêté"' in fr
    assert 'data-state-cancelled="Stopped"' in en
