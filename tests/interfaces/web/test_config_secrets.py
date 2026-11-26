"""Un secret n'est pas un paramètre (``PLAN_UI_COMPOSEUR.md`` §9, D-299).

Le jeton du segmenteur distant traverse le formulaire : la page le saisit, la
file le porte jusqu'au lancement. Il ne doit **sortir** nulle part — ni dans
l'export de configuration (un fichier qu'on partage, qu'on versionne), ni dans
le ``RunResult``, le rapport, l'état du job, l'archive, les journaux, ni dans
un message de refus. À l'import, un secret retiré est **redemandé** : la file
le marque, le lanceur refuse tant qu'il n'est pas ressaisi — jamais deviné.

Défaut réel trouvé en S26 : l'export écrivait le jeton en clair, comme
l'ancien composeur avant lui.
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER

_CSRF = {CSRF_HEADER: "1"}
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
_JETON = "hf_NEPASFUIR_7c1e9a"


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            reports_dir=tmp_path / "reports",
            data_dir=tmp_path / "data",
            uploads_dir=tmp_path / "uploads",
            rate_limit=1000,
            public_mode=False,
        )
    )


def _entree(**params: object) -> dict[str, object]:
    return {
        "recipe": "segmentation_puis_lecture",
        "choices": {"seg": "remote_segmenter", "reco": "precomputed_region"},
        "params": {"seg": {"endpoint": "https://seg.example/detect", **params}},
    }


def _corpus(client: TestClient, racine: Path | None = None) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("p1.png", _PNG)
        zf.writestr("p1.gt.txt", "le soleil")
    reponse = client.post(
        "/api/corpus",
        files={"file": ("c.zip", buf.getvalue(), "application/zip")},
        headers=_CSRF,
    )
    assert reponse.status_code == 201, reponse.json()
    if racine is not None:
        # Ce que rejoue ``precomputed_region`` (sans lui : 422, D-299) ; un
        # dépôt web n'accepte pas de JSON, on le pose à côté de l'image.
        for image in (racine / "uploads").rglob("p1.png"):
            image.with_name("p1.reco.regions.json").write_text("{}")
    return str(reponse.json()["corpus_id"])


def _attendre(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    limite = time.time() + timeout
    while time.time() < limite:
        corps = client.get(f"/api/runs/{job_id}").json()
        if corps["state"] in {"done", "failed", "cancelled"}:
            return dict(corps)
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} non terminé dans le délai")


def test_the_config_export_never_carries_a_declared_secret(tmp_path: Path) -> None:
    """L'export passe par la forme canonique du serveur : le jeton en est
    retiré, et l'entrée dit lequel il faudra ressaisir."""
    reponse = _client(tmp_path).post(
        "/api/runs/config",
        headers=_CSRF,
        json={"entries": [_entree(token=_JETON, min_score=0.3)]},
    )
    assert reponse.status_code == 200, reponse.json()
    assert _JETON not in reponse.text
    entree = reponse.json()["config"]["entries"][0]
    assert entree["params"]["seg"] == {
        "endpoint": "https://seg.example/detect",
        "min_score": 0.3,
    }
    assert entree["withheld_secrets"] == ["seg.token"]


def test_an_entry_without_a_secret_is_exported_unchanged(tmp_path: Path) -> None:
    """Rien à retirer → rien à marquer : la forme canonique reste celle d'avant."""
    reponse = _client(tmp_path).post(
        "/api/runs/config", headers=_CSRF, json={"entries": [_entree()]}
    )
    assert reponse.status_code == 200
    assert "withheld_secrets" not in reponse.json()["config"]["entries"][0]


def test_a_withheld_secret_is_asked_again_never_guessed(tmp_path: Path) -> None:
    """Une entrée importée dont le jeton a été retiré ne se lance pas sans lui :
    le refus nomme l'étape et le réglage, il ne part pas sans jeton."""
    client = _client(tmp_path)
    entree = {**_entree(), "withheld_secrets": ["seg.token"]}
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={"corpus_id": _corpus(client), "entries": [entree]},
    )
    assert reponse.status_code == 422
    detail = reponse.json()["detail"]
    assert "token" in detail and "seg" in detail


def test_a_withheld_marker_on_an_unknown_setting_is_refused(tmp_path: Path) -> None:
    """Le marqueur ne peut nommer qu'un secret que la brique déclare."""
    client = _client(tmp_path)
    entree = {**_entree(), "withheld_secrets": ["seg.endpoint"]}
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={"corpus_id": _corpus(client), "entries": [entree]},
    )
    assert reponse.status_code == 422


def test_a_mistyped_secret_is_not_echoed_in_the_refusal(tmp_path: Path) -> None:
    """Un jeton mal typé est refusé (422) sans que sa valeur revienne."""
    client = _client(tmp_path)
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={"corpus_id": _corpus(client), "entries": [_entree(token=918273645)]},
    )
    assert reponse.status_code == 422
    assert "918273645" not in reponse.text


def _tout_le_disque(racine: Path) -> str:
    return "\n".join(
        f.read_bytes().decode("utf-8", "replace")
        for f in racine.rglob("*")
        if f.is_file()
    )


@pytest.mark.parametrize("echec", [False, True], ids=["reussi", "echoue"])
def test_a_remote_segmenter_token_leaves_no_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    echec: bool,
) -> None:
    """Le jeton part dans l'en-tête de l'appel — et nulle part ailleurs : ni le
    ``RunResult``, ni le rapport servi, ni l'état du job, ni l'archive, ni les
    journaux ; pas même quand l'endpoint le recopie dans son message d'erreur."""
    from cinoc.adapters.corpus._http import HttpFetchError

    envoyes: list[dict[str, str]] = []

    def faux_post(url: str, **kw: object) -> object:
        en_tetes = kw.get("headers")
        assert isinstance(en_tetes, dict)
        envoyes.append(en_tetes)
        if echec:
            raise HttpFetchError(f"401 : jeton {_JETON} refusé")
        return [
            {"label": "text", "score": 0.9,
             "box": {"xmin": 0, "ymin": 0, "xmax": 4, "ymax": 4}}
        ]

    monkeypatch.setattr("cinoc.adapters.layout.remote.post_json", faux_post)
    caplog.set_level(logging.DEBUG)
    client = _client(tmp_path)
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={
            "corpus_id": _corpus(client, tmp_path),
            "entries": [_entree(token=_JETON)],
        },
    )
    assert reponse.status_code == 201, reponse.json()
    job = _attendre(client, reponse.json()["job_id"])
    assert envoyes and envoyes[0]["Authorization"] == f"Bearer {_JETON}"
    assert job["state"] == "done", job
    assert _JETON not in client.get(f"/api/runs/{job['id']}").text
    assert _JETON not in client.get(f"/reports/{job['report_name']}").text
    assert _JETON not in _tout_le_disque(tmp_path)
    assert _JETON not in caplog.text
