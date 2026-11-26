"""Lanceur web : CSRF d'abord, démo, puis concurrents (gardes HTTP), mode public."""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.app.engines import EngineStatus, engine_statuses
from cinoc.app.evaluation_views import EvaluationOptions
from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.routers.runs import LaunchRequest
from cinoc.interfaces.web.security.csrf import CSRF_HEADER

_CSRF = {CSRF_HEADER: "1"}


def _client(tmp_path: Path, *, public_mode: bool = False) -> TestClient:
    return TestClient(
        create_app(reports_dir=tmp_path, rate_limit=1000, public_mode=public_mode)
    )


def _poll_until_terminal(
    client: TestClient, job_id: str, timeout: float = 30.0
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/runs/{job_id}").json()
        if body["state"] in {"done", "failed", "cancelled"}:
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} non terminé dans le délai")


# --- Sécurité d'abord (CSRF) -------------------------------------------------


def test_launch_request_accepts_char_exclude() -> None:
    # 3c : le DTO accepte char_exclude (sinon le formulaire tomberait en 422).
    req = LaunchRequest(char_exclude=",.;")
    assert req.char_exclude == ",.;"


def test_launch_request_accepts_metric_profile() -> None:
    # 3c : le DTO accepte metric_profile (le plan le résout ; inconnu → 422).
    req = LaunchRequest(metric_profile="philologie")
    assert req.metric_profile == "philologie"
    assert LaunchRequest().metric_profile is None  # absent par défaut (= standard)


def test_every_launch_takes_the_same_scoring_options() -> None:
    """Une seule politique de vues (D-297), une seule route (D-298) : toute
    file reçoit les options de notation sous les mêmes noms de champ."""
    choix = {"normalization": "nfc", "char_exclude": ",", "metric_profile": "essentiel"}
    attendu = EvaluationOptions(**choix)
    assert LaunchRequest(**choix).options() == attendu
    assert LaunchRequest(
        corpus_id="c", entries=({"recipe": "ocr_simple"},), **choix
    ).options() == attendu


def test_an_unknown_option_on_a_recipe_is_a_named_422(tmp_path: Path) -> None:
    client = _client(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("p.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        zf.writestr("p.gt.txt", "texte")
    depot = client.post(
        "/api/corpus",
        files={"file": ("c.zip", buf.getvalue(), "application/zip")},
        headers=_CSRF,
    )
    reponse = client.post(
        "/api/runs",
        headers=_CSRF,
        json={
            "corpus_id": depot.json()["corpus_id"],
            "entries": [{"recipe": "ocr_simple"}],
            "metric_profile": "bidon",
        },
    )
    assert reponse.status_code == 422
    assert "profil de métriques inconnu" in reponse.json()["detail"]


# --- Config save/load : POST /api/runs/config (validation stateless) ----------


def test_config_endpoint_echoes_canonical(tmp_path: Path) -> None:
    # A : la config du formulaire EST un LaunchRequest ; l'endpoint la valide et
    # la renvoie canonique (exclude_none) — round-trip pour l'import client.
    # La file **entière** voyage : depuis D-298 l'export porte les recettes (il
    # ne portait que les concurrents composés, et la page le disait).
    entree = {
        "recipe": "ocr_puis_llm",
        "choices": {"correction": "openai"},
        "params": {"correction": {"model": "m", "prompt": "Corrige."}},
        "optional": ["ner"],
    }
    cfg = {
        "entries": [entree],
        "corpus_id": "c1",
        "char_exclude": ",.;",
        "metric_profile": "philologie",
    }
    r = _client(tmp_path).post("/api/runs/config", headers=_CSRF, json=cfg)
    assert r.status_code == 200
    out = r.json()["config"]
    assert out["corpus_id"] == "c1"
    assert out["char_exclude"] == ",.;"
    assert out["metric_profile"] == "philologie"
    assert out["entries"] == [entree]
    # normalization non fournie (None) → absente de la forme canonique.
    assert "normalization" not in out


def test_config_endpoint_rejects_invalid(tmp_path: Path) -> None:
    # Champ inconnu → 422 (Pydantic extra="forbid") : un fichier malformé est
    # rejeté net, jamais repeuplé en silence.
    r = _client(tmp_path).post("/api/runs/config", headers=_CSRF, json={"bogus": 1})
    assert r.status_code == 422


def test_config_endpoint_requires_csrf(tmp_path: Path) -> None:
    # Écriture protégée comme la preview de normalisation (corps valide → on
    # prouve que c'est bien le CSRF qui refuse, pas la validation du corps).
    r = _client(tmp_path).post("/api/runs/config", json={"entries": []})
    assert r.status_code == 403


def test_post_without_csrf_is_403(tmp_path: Path) -> None:
    resp = _client(tmp_path).post("/api/runs")
    assert resp.status_code == 403


def test_cancel_without_csrf_is_403(tmp_path: Path) -> None:
    assert _client(tmp_path).post("/api/runs/whatever/cancel").status_code == 403


def test_csrf_header_allows_post(tmp_path: Path) -> None:
    # Sans corps → démonstration → 201.
    resp = _client(tmp_path).post("/api/runs", headers=_CSRF)
    assert resp.status_code == 201
    assert "job_id" in resp.json()


# --- Bout-en-bout démo : lancer → exécuter → résultat visible ----------------


def test_launch_runs_and_result_appears(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = client.post("/api/runs", headers=_CSRF).json()["job_id"]
    job = _poll_until_terminal(client, job_id)
    assert job["state"] == "done"
    name = job["report_name"]
    # le rapport produit est servable (preuve qu'il existe + est rendu)
    assert client.get(f"/reports/{name}").status_code == 200


def test_status_unknown_job_is_404(tmp_path: Path) -> None:
    assert _client(tmp_path).get("/api/runs/absent").status_code == 404


def test_cancel_unknown_job_is_404(tmp_path: Path) -> None:
    resp = _client(tmp_path).post("/api/runs/absent/cancel", headers=_CSRF)
    assert resp.status_code == 404


def test_public_mode_allows_local_demo(tmp_path: Path) -> None:
    client = _client(tmp_path, public_mode=True)
    resp = client.post("/api/runs", headers=_CSRF)
    assert resp.status_code == 201
    assert _poll_until_terminal(client, resp.json()["job_id"])["state"] == "done"


# --- La file : gardes HTTP ---------------------------------------------------

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _post(client: TestClient, body: dict) -> object:
    return client.post("/api/runs", headers=_CSRF, json=body)


def _upload_demo_corpus(client: TestClient) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.png", _PNG)
        zf.writestr("a.gt.txt", b"verite")
    files = {"file": ("c.zip", buf.getvalue(), "application/zip")}
    return client.post("/api/corpus", files=files, headers=_CSRF).json()["corpus_id"]


def _queue(client: TestClient, *entries: dict, **extra: object) -> object:
    """Poste une file sur un corpus déposé."""
    body = {"corpus_id": _upload_demo_corpus(client), "entries": list(entries)}
    return _post(client, {**body, **extra})


def _llm(recipe: str = "ocr_puis_llm", provider: str = "openai") -> dict:
    return {
        "recipe": recipe,
        "choices": {"correction": provider},
        "params": {"correction": {"model": "m"}},
    }


def test_unknown_recipe_is_422(tmp_path: Path) -> None:
    resp = _queue(_client(tmp_path), {"recipe": "bogus"})
    assert resp.status_code == 422
    assert "ocr_simple" in resp.json()["detail"]  # liste les connues


def test_brick_outside_its_role_is_422(tmp_path: Path) -> None:
    entree = {"recipe": "ocr_simple", "choices": {"ocr": "bogus"}}
    resp = _queue(_client(tmp_path), entree)
    assert resp.status_code == 422


def test_extra_field_on_request_is_422(tmp_path: Path) -> None:
    assert _post(_client(tmp_path), {"entries": [], "x": 1}).status_code == 422


def test_extra_field_on_entry_is_422(tmp_path: Path) -> None:
    resp = _queue(_client(tmp_path), {"recipe": "ocr_simple", "x": 1})
    assert resp.status_code == 422


def test_a_queue_needs_a_corpus(tmp_path: Path) -> None:
    resp = _post(_client(tmp_path), {"entries": [{"recipe": "ocr_simple"}]})
    assert resp.status_code == 422
    assert "corpus" in resp.json()["detail"]


def test_cloud_engine_without_key_is_409_when_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Hors mode public : un moteur cloud sans clé tombe en 409 (indisponible),
    # pas en 403. Avec sa clé, il serait autorisé (modèle « clé posée → marche »).
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    entree = {"recipe": "vlm_seul", "choices": {"vlm": "openai"},
              "params": {"vlm": {"model": "m"}}}
    resp = _queue(_client(tmp_path, public_mode=False), entree)
    assert resp.status_code == 409


def test_public_mode_blocks_cloud_engine_403(tmp_path: Path) -> None:
    # Mode public (Space exposé) : fail-closed. Un moteur cloud est refusé en 403
    # AVANT toute vérif de clé/dispo — jamais d'appel facturé sur une instance
    # publique, clé présente ou non. (≠ 409 « indisponible » du mode privé.)
    entree = {"recipe": "ocr_simple", "choices": {"ocr": "mistral_ocr"},
              "params": {"ocr": {"model": "m"}}}
    resp = _queue(_client(tmp_path, public_mode=True), entree)
    assert resp.status_code == 403


def test_public_mode_blocks_cloud_llm_in_chain_403(tmp_path: Path) -> None:
    # Le LLM d'une chaîne OCR→LLM est aussi une brique nommée : un LLM cloud y
    # est gated en mode public, même derrière un moteur OCR gratuit (tesseract).
    resp = _queue(_client(tmp_path, public_mode=True), _llm())
    assert resp.status_code == 403


def test_public_mode_keeps_the_local_bricks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Segmenter sur la machine, lire chaque bloc par Tesseract, projeter,
    assembler l'ALTO : rien n'appelle un service, rien n'exige de clé — le
    composeur le laissait passer en mode public, la recette aussi
    (``PUBLIC_BRICK_KINDS``). Binaire forcé absent : on atteint la sonde (409),
    preuve que le verrou public est franchi."""
    monkeypatch.setattr(
        "cinoc.interfaces.web.app.engine_statuses",
        lambda **kw: engine_statuses(has_binary=lambda _name: None, **kw),
    )
    entree = {"recipe": "segmentation_puis_lecture", "optional": ["alto"],
              "choices": {"reco": "tesseract"}}
    resp = _queue(_client(tmp_path, public_mode=True), entree)
    assert resp.status_code == 409


def test_public_mode_refuses_a_remote_segmenter(tmp_path: Path) -> None:
    """Le segmenteur distant posterait la page à l'adresse que donne le client :
    hors du socle public."""
    entree = {
        "recipe": "segmentation_puis_lecture",
        "choices": {"seg": "remote_segmenter"},
        "params": {"seg": {"endpoint": "https://seg.example"}},
    }
    resp = _queue(_client(tmp_path, public_mode=True), entree)
    assert resp.status_code == 403


def _force_tesseract_available(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub direct du provider : tesseract « disponible » sans dépendre de la
    # sonde réelle du binaire — absent en CI (run 409 au gate moteur avant
    # d'atteindre le gate NER). Isole bien le gate NER.
    monkeypatch.setattr(
        "cinoc.interfaces.web.app.engine_statuses",
        lambda **kw: (
            EngineStatus(
                kind="tesseract", label="Tesseract", available=True, detail="ok"
            ),
        ),
    )


def _patch_ner(monkeypatch: pytest.MonkeyPatch, *, available: bool) -> None:
    detail = (
        "prêt (spaCy installé)" if available else "spaCy non installé (extra [ner])"
    )
    monkeypatch.setattr(
        "cinoc.app.recipe_catalog.ner_status",
        lambda **kw: EngineStatus(
            kind="ner", label="NER (spaCy)", available=available, detail=detail
        ),
    )


def test_ner_requested_without_spacy_is_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Étape NER retenue mais spaCy absent → 409 AVANT le lancement (pas d'échec
    # d'étape en cours de run) : la sonde du catalogue, celle qui la grise.
    _force_tesseract_available(monkeypatch)
    _patch_ner(monkeypatch, available=False)
    resp = _queue(_client(tmp_path), {"recipe": "ocr_simple", "optional": ["ner"]})
    assert resp.status_code == 409
    assert "[ner]" in resp.json()["detail"]


def test_ner_requested_with_spacy_passes_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spaCy dispo → le gate NER passe (le run est lancé : 201).
    _force_tesseract_available(monkeypatch)
    _patch_ner(monkeypatch, available=True)
    resp = _queue(_client(tmp_path), {"recipe": "ocr_simple", "optional": ["ner"]})
    assert resp.status_code == 201


def test_public_mode_allows_free_tesseract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # tesseract est le socle gratuit offert publiquement : il PASSE le gate public
    # (pas de 403). Binaire forcé absent → il tombe sur la dispo (409), prouvant
    # qu'il a franchi le verrou public et atteint la vérification runtime.
    monkeypatch.setattr(
        "cinoc.interfaces.web.app.engine_statuses",
        lambda **kw: engine_statuses(has_binary=lambda _name: None, **kw),
    )
    resp = _queue(_client(tmp_path, public_mode=True), {"recipe": "ocr_simple"})
    assert resp.status_code == 409


def test_demo_with_corpus_is_422(tmp_path: Path) -> None:
    # aucune entrée (= démo) mais un corpus fourni → incohérent.
    client = _client(tmp_path)
    corpus_id = _upload_demo_corpus(client)
    assert _post(client, {"corpus_id": corpus_id}).status_code == 422


def test_unknown_corpus_is_404(tmp_path: Path) -> None:
    resp = _post(
        _client(tmp_path),
        {"entries": [{"recipe": "ocr_simple"}], "corpus_id": "nope"},
    )
    assert resp.status_code == 404


def test_unavailable_engine_is_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # binaire forcé absent → tesseract indisponible (déterministe).
    monkeypatch.setattr(
        "cinoc.interfaces.web.app.engine_statuses",
        lambda **kw: engine_statuses(has_binary=lambda _name: None, **kw),
    )
    resp = _queue(_client(tmp_path), {"recipe": "ocr_simple"})
    assert resp.status_code == 409


def test_unknown_normalization_is_422(tmp_path: Path) -> None:
    resp = _queue(
        _client(tmp_path), {"recipe": "ocr_simple"}, normalization="bogus"
    )
    assert resp.status_code == 422


def test_ocr_llm_chain_reaches_availability_not_preblocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # OCR→LLM n'est pas pré-bloqué. tesseract forcé dispo, openai indispo (pas
    # de clé/SDK en CI) → 409 sur openai : la chaîne atteint bien la garde de
    # disponibilité.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "cinoc.interfaces.web.app.engine_statuses",
        lambda **kw: engine_statuses(
            has_binary=lambda _name: "/usr/bin/tesseract",
            has_module=lambda _name: False,
            **kw,
        ),
    )
    resp = _queue(_client(tmp_path), _llm())
    assert resp.status_code == 409
    assert "openai" in resp.json()["detail"]


def test_a_recipe_and_another_shape_share_one_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La limite que la page affichait — « une recette et un concurrent composé
    ne partagent pas un run » — tombe : il n'y a plus qu'une forme d'entrée.
    OCR seul, segmentation puis lecture et presse ancienne : un run."""
    from cinoc.app import engines

    monkeypatch.setattr(
        "cinoc.interfaces.web.app.engine_statuses",
        lambda: engines.engine_statuses(
            has_binary=lambda _: "/bin/x", has_module=lambda _: True
        ),
    )
    monkeypatch.setattr(
        "cinoc.interfaces.web.app.segmenter_statuses",
        lambda: engines.segmenter_statuses(
            has_module=lambda _: True, has_binary=lambda _: "/bin/x"
        ),
    )
    client = _client(tmp_path)
    resp = _queue(
        client,
        {"recipe": "ocr_simple"},
        {"recipe": "segmentation_puis_lecture", "optional": ["alto"]},
        {"recipe": "presse_ancienne"},
    )
    assert resp.status_code == 201, resp.json()
