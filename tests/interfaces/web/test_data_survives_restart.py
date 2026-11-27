"""Un corpus déposé et un rapport du serveur survivent au redémarrage (D-307).

Parcours du testeur extérieur : ZIP déposé dans la Bibliothèque, run lancé,
serveur arrêté puis relancé → « Aucun corpus local. Importez-en un. » ; les
données restaient orphelines dans ``/tmp/cinoc-data-*`` et
``/tmp/cinoc-uploads-*``. Ici, deux applications successives **sans aucun
réglage** — ce que fait ``cinoc serve`` relancé.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.png", _PNG)
        zf.writestr("a.gt.txt", "vérité")
    return buf.getvalue()


def _app(tmp_path: Path, *, public: bool = False) -> TestClient:
    # Aucun ``data_dir`` ni ``uploads_dir`` : le défaut de ``cinoc serve``.
    return TestClient(
        create_app(reports_dir=tmp_path / "rep", rate_limit=1000, public_mode=public)
    )


def _depose(client: TestClient) -> str:
    depot = client.post(
        "/api/corpus",
        files={"file": ("pages-zip-du-testeur.zip", _zip(), "application/zip")},
        headers={CSRF_HEADER: "1"},
    )
    assert depot.status_code == 201
    return str(depot.json()["corpus_id"])


def test_a_deposited_corpus_is_still_there_after_a_restart(tmp_path: Path) -> None:
    _depose(_app(tmp_path))
    relance = _app(tmp_path)
    assert "pages-zip-du-testeur" in relance.get("/benchmark").text
    # Sous le dossier de données, pas dans un temporaire orphelin.
    from cinoc.app.data_dir import user_data_dir

    assert any(user_data_dir().rglob("a.gt.txt"))


def test_a_server_report_is_still_served_after_a_restart(tmp_path: Path) -> None:
    from cinoc.app.data_dir import user_data_dir
    from cinoc.app.demo import demo_run_spec, write_demo_corpus
    from cinoc.app.modules import ModuleRegistry, register_default_modules
    from cinoc.app.orchestrator import run as run_orchestrator
    from cinoc.app.results import dump_run_result

    _app(tmp_path)
    registry = ModuleRegistry()
    register_default_modules(registry)
    (tmp_path / "demo").mkdir()
    corpus = write_demo_corpus(tmp_path / "demo")
    result = run_orchestrator(
        demo_run_spec(corpus, run_id="web-run"), registry=registry, code_version="t"
    )
    # Là où le lanceur écrit le ``RunResult`` d'un run de la page.
    dump_run_result(result, str(user_data_dir() / "web-run.json"))
    relance = _app(tmp_path)
    assert relance.get("/reports/web-run").status_code == 200


def test_public_mode_keeps_nothing_across_restarts(tmp_path: Path) -> None:
    _depose(_app(tmp_path, public=True))
    relance = _app(tmp_path, public=True)
    assert "pages-zip-du-testeur" not in relance.get("/benchmark").text
    from cinoc.app.data_dir import user_data_dir

    assert not user_data_dir().exists()


# --------------------------------------------------------------------------- #
# Un dossier de données qui dure ne doit pas figer les rapports déposés
# --------------------------------------------------------------------------- #


def test_a_deposited_report_is_refreshed_and_forgotten_across_restarts(
    tmp_path: Path,
) -> None:
    """Le dossier de données durait (D-307) ; la copie d'un rapport déposé
    (``--reports-dir``) ne doit pas durer avec lui. Relancé après un nouveau
    ``cinoc run --json``, le serveur servait l'ancienne copie (une graine
    présente n'était jamais réécrite) ; un rapport retiré du dépôt restait
    listé, d'une session à l'autre et d'un dépôt à l'autre."""
    from cinoc.interfaces.web.catalog import seed_reports

    depot, donnees = tmp_path / "depot", tmp_path / "donnees"
    depot.mkdir()
    (depot / "a.json").write_text('{"v": 1}', encoding="utf-8")
    (depot / "b.json").write_text('{"v": 1}', encoding="utf-8")
    seed_reports(depot, donnees)
    (donnees / "web-run.json").write_text('{"run": 1}', encoding="utf-8")

    (depot / "a.json").write_text('{"v": 2}', encoding="utf-8")  # relancé
    (depot / "b.json").unlink()  # retiré du dépôt
    seed_reports(depot, donnees)

    assert (donnees / "a.json").read_text(encoding="utf-8") == '{"v": 2}'
    assert not (donnees / "b.json").exists()
    # Un run du serveur n'est pas une graine : il reste.
    assert (donnees / "web-run.json").read_text(encoding="utf-8") == '{"run": 1}'
