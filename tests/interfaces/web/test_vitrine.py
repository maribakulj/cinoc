"""Vitrine : liste, rendu HTML d'un ``RunResult`` sauvé, accueil, sécurité chemins."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from cinoc.app.results import dump_run_result
from cinoc.domain.run import RunManifest, utcnow
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.catalog import available_reports


def _write_report(reports_dir: Path, name: str = "run1", *, metric: str = "") -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    manifest = RunManifest(
        run_id=name,
        corpus_name="c",
        n_documents=0,
        code_version="1.0",
        started_at=utcnow(),
        completed_at=utcnow(),
    )
    pipelines = (
        (
            PipelineResult(
                pipeline="p",
                view="text",
                conditional_aggregate=(
                    MetricScore(metric=metric, value=0.1, support=1),
                ),
            ),
        )
        if metric
        else ()
    )
    dump_run_result(
        RunResult(manifest=manifest, pipelines=pipelines), reports_dir / f"{name}.json"
    )


def _client(reports_dir: Path) -> TestClient:
    return TestClient(create_app(reports_dir=reports_dir))


def test_lists_reports_sorted(tmp_path: Path) -> None:
    # ``available_reports`` = la logique de listing, rendue côté serveur sur
    # l'accueil (plus d'endpoint JSON ``/api/reports`` : rendu serveur).
    _write_report(tmp_path, "run2")
    _write_report(tmp_path, "run1")
    assert available_reports(tmp_path) == ["run1", "run2"]


def test_missing_dir_lists_nothing(tmp_path: Path) -> None:
    assert available_reports(tmp_path / "absent") == []


def test_renders_report_as_html(tmp_path: Path) -> None:
    _write_report(tmp_path, "run1")
    resp = _client(tmp_path).get("/reports/run1")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert resp.text.startswith("<!DOCTYPE html>")


def test_unknown_report_is_404(tmp_path: Path) -> None:
    _write_report(tmp_path, "run1")
    assert _client(tmp_path).get("/reports/nope").status_code == 404


def test_report_glossary_french_by_default(tmp_path: Path) -> None:
    _write_report(tmp_path, "run1", metric="cer")
    body = _client(tmp_path).get("/reports/run1").text
    assert '<html lang="fr">' in body
    assert "<h2>Glossaire</h2>" in body


def test_report_glossary_english_via_lang(tmp_path: Path) -> None:
    _write_report(tmp_path, "run1", metric="cer")
    body = _client(tmp_path).get("/reports/run1?lang=en").text
    assert '<html lang="en">' in body
    assert "<h2>Glossary</h2>" in body


def test_path_traversal_is_blocked(tmp_path: Path) -> None:
    # une tentative de sortie du dossier ne doit JAMAIS réussir (jamais 200).
    resp = _client(tmp_path).get("/reports/..%2f..%2f..%2fetc%2fpasswd")
    assert resp.status_code != 200


def test_report_bundle_zip_downloads(tmp_path: Path) -> None:
    import io
    import zipfile

    _write_report(tmp_path, "run1")
    resp = _client(tmp_path).get("/reports/run1/bundle.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert 'filename="run1.zip"' in resp.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert "report.html" in archive.namelist()


def test_report_bundle_unknown_is_404(tmp_path: Path) -> None:
    assert _client(tmp_path).get("/reports/nope/bundle.zip").status_code == 404


def test_report_bundle_traversal_is_blocked(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/reports/..%2f..%2fsecret/bundle.zip")
    assert resp.status_code != 200


def test_alto_archive_404_without_export(tmp_path: Path) -> None:
    # Run sans export ALTO → l'endpoint répond 404 (pas d'archive vide).
    _write_report(tmp_path, "run1")
    assert _client(tmp_path).get("/reports/run1/alto.zip").status_code == 404


def test_alto_archive_downloads_when_present(tmp_path: Path) -> None:
    import io
    import zipfile

    from fastapi import FastAPI

    from cinoc.app.alto_store import AltoStore
    from cinoc.interfaces.web.routers.reports import build_reports_router

    _write_report(tmp_path, "run1")
    store = AltoStore(tmp_path / "alto")
    store.save("run1", "doc-a", "tesseract", b"<alto>A</alto>")
    app = FastAPI()
    app.include_router(build_reports_router(tmp_path, alto_store=store))
    resp = TestClient(app).get("/reports/run1/alto.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert 'filename="run1-alto.zip"' in resp.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        names = archive.namelist()
        assert names and all(n.endswith(".alto.xml") for n in names)
        assert archive.read(names[0]) == b"<alto>A</alto>"


def test_alto_archive_unknown_report_is_404(tmp_path: Path) -> None:
    from fastapi import FastAPI

    from cinoc.app.alto_store import AltoStore
    from cinoc.interfaces.web.routers.reports import build_reports_router

    app = FastAPI()
    app.include_router(
        build_reports_router(tmp_path, alto_store=AltoStore(tmp_path / "alto"))
    )
    assert TestClient(app).get("/reports/nope/alto.zip").status_code == 404


def test_home_lists_and_links_reports(tmp_path: Path) -> None:
    _write_report(tmp_path, "run1")
    resp = _client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert 'href="/reports/run1"' in resp.text
    # lien de téléchargement ZIP (saveur dossier) à côté de chaque rapport
    assert 'href="/reports/run1/bundle.zip"' in resp.text
    # pas d'export ALTO pour ce run → pas de lien ALTO mort
    assert "/reports/run1/alto.zip" not in resp.text


def test_home_empty_when_no_reports(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "aucun rapport" in resp.text
