"""Sécurité HTTP de la vitrine : en-têtes (CSP stricte) + limiteur de débit."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.headers import (
    CONTENT_SECURITY_POLICY,
    SecurityHeadersMiddleware,
    get_csp_policy,
    is_huggingface_space,
)
from cinoc.interfaces.web.security.rate_limit import RateLimitMiddleware


def _client(tmp_path: Path, rate_limit: int = 60) -> TestClient:
    return TestClient(create_app(reports_dir=tmp_path, rate_limit=rate_limit))


def test_security_headers_present(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/health")
    assert resp.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"


def test_csp_is_strict() -> None:
    # default-src verrouillé ; scripts/connexions/styles/polices uniquement en self.
    assert "default-src 'none'" in CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
    # JS auto-hébergé : 'self' SEUL (ni inline ni origine tierce dans script-src)
    assert "script-src 'self';" in CONTENT_SECURITY_POLICY
    assert "script-src 'self' " not in CONTENT_SECURITY_POLICY
    assert "connect-src 'self'" in CONTENT_SECURITY_POLICY
    assert "form-action 'none'" in CONTENT_SECURITY_POLICY


def test_is_huggingface_space_reads_space_id(monkeypatch: pytest.MonkeyPatch) -> None:
    # SPACE_ID injecté par HF = marqueur de Space ; absent/blanc = local.
    monkeypatch.delenv("SPACE_ID", raising=False)
    assert is_huggingface_space() is False
    monkeypatch.setenv("SPACE_ID", "Ma-Ri-Ba-Ku/Cinoc")
    assert is_huggingface_space() is True
    monkeypatch.setenv("SPACE_ID", "   ")  # valeur blanche ⇒ pas un Space
    assert is_huggingface_space() is False


def test_headers_locked_without_space_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Hors Space : verrou total anti-cadrage ('none' + X-Frame-Options: DENY).
    monkeypatch.delenv("SPACE_ID", raising=False)
    resp = _client(tmp_path).get("/health")
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
    assert resp.headers["x-frame-options"] == "DENY"


def test_csp_relaxes_frame_ancestors_on_hf_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sur HF Space, la vitrine doit être embarquable dans l'iframe du Hub :
    # frame-ancestors ouvre huggingface.co / *.hf.space, sans 'none'.
    monkeypatch.setenv("SPACE_ID", "Ma-Ri-Ba-Ku/Cinoc")
    resp = _client(tmp_path).get("/health")
    csp = resp.headers["content-security-policy"]
    assert csp == get_csp_policy()
    assert "huggingface.co" in csp and "*.hf.space" in csp
    # le verrou 'none' ne doit plus s'appliquer à frame-ancestors
    assert "'none'" not in csp.split("frame-ancestors", 1)[1]
    # le reste de la CSP stricte est intact (aucune ressource externe tolérée)
    assert "default-src 'none'" in csp


def test_x_frame_options_omitted_on_hf_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # X-Frame-Options: DENY a priorité absolue sur frame-ancestors dans les
    # vieux navigateurs → il est omis en Space pour ne pas annuler l'embed.
    monkeypatch.setenv("SPACE_ID", "Ma-Ri-Ba-Ku/Cinoc")
    resp = _client(tmp_path).get("/health")
    assert "x-frame-options" not in resp.headers


def test_headers_on_html_report(tmp_path: Path) -> None:
    from cinoc.app.results import dump_run_result
    from cinoc.domain.run import RunManifest, utcnow
    from cinoc.evaluation.result import RunResult

    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=0,
        code_version="1.0",
        started_at=utcnow(),
        completed_at=utcnow(),
    )
    dump_run_result(RunResult(manifest=manifest), tmp_path / "r.json")
    client = _client(tmp_path)
    resp = client.get("/reports/r")
    assert resp.status_code == 200
    csp = resp.headers["content-security-policy"]
    # Réponse /reports/ : script-src autorise le hash de CHAQUE script statique
    # inliné du rapport (compare + report) — l'inline non hashé reste interdit.
    from cinoc.reports.embedded import EMBEDDED_SCRIPTS, script_hash

    for name in EMBEDDED_SCRIPTS:
        assert script_hash(name) in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    # Une autre route (accueil) n'a PAS ces hashes : la relaxe est ciblée /reports/.
    home_csp = client.get("/").headers["content-security-policy"]
    assert script_hash("compare.js") not in home_csp


def test_rate_limit_returns_429(tmp_path: Path) -> None:
    client = _client(tmp_path, rate_limit=3)
    statuses = [client.get("/health").status_code for _ in range(5)]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3:] == [429, 429]


def test_rate_limit_rejects_invalid_config() -> None:
    with pytest.raises(ValueError):
        create_app(rate_limit=0)


def test_rate_limit_middleware_guards_its_own_config() -> None:
    async def _noop(scope: object, receive: object, send: object) -> None:
        return None

    with pytest.raises(ValueError):
        RateLimitMiddleware(_noop, max_requests=0)  # type: ignore[arg-type]


def test_middlewares_pass_non_http_scope_through() -> None:
    # scope non-HTTP (lifespan/websocket) : traversée intacte, aucun en-tête,
    # aucun comptage de débit.
    seen: list[str] = []

    async def _app(scope: dict[str, object], receive: object, send: object) -> None:
        seen.append(str(scope["type"]))

    async def _noop_send(message: object) -> None:
        return None

    scope: dict[str, object] = {"type": "lifespan"}
    asyncio.run(SecurityHeadersMiddleware(_app)(scope, _noop_send, _noop_send))
    asyncio.run(RateLimitMiddleware(_app)(scope, _noop_send, _noop_send))
    assert seen == ["lifespan", "lifespan"]


def test_rate_limit_counts_unknown_client() -> None:
    # scope HTTP sans 'client' → IP 'unknown', toujours borné (pas de crash).
    sent: list[int] = []

    async def _app(scope: dict[str, object], receive: object, send: object) -> None:
        sent.append(200)

    async def _capture(message: dict[str, object]) -> None:
        if message["type"] == "http.response.start":
            sent.append(int(message["status"]))  # type: ignore[call-overload]

    mw = RateLimitMiddleware(_app, max_requests=1)
    scope: dict[str, object] = {"type": "http"}  # pas de 'client'
    asyncio.run(mw(scope, _capture, _capture))
    asyncio.run(mw(scope, _capture, _capture))
    assert 200 in sent and 429 in sent


def test_the_served_report_may_load_its_embedded_fonts() -> None:
    """Le rapport **autonome** embarque ses polices en ``data:`` (un seul
    fichier, aucun réseau) : servi sous ``/reports/``, ``font-src 'self'``
    les bloquait — neuf erreurs console, texte en police de repli (D-299, vu
    au navigateur). ``data:`` n'est ouvert **que** là ; la coquille garde ses
    polices auto-hébergées, en ``'self'`` seul."""
    assert "font-src 'self' data:;" in get_csp_policy("/reports/r")
    assert "font-src 'self';" in get_csp_policy("/benchmark")
    assert "font-src 'self';" in get_csp_policy("/api/runs")
    assert "font-src 'self';" in CONTENT_SECURITY_POLICY
