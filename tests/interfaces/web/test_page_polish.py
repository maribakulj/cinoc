"""Les cosmétiques de la page relevés par le testeur simulé (S34b, n° 15).

Chacun est vérifié là où c'est mécanisable : un libellé anglais dans la page
française, l'apostrophe que la police d'accent dessine espacée, le ``.zip``
gardé dans le nom d'un corpus, des vignettes rognées, un journal de run sans
nom de document, des champs de réglages sans ``id`` ni ``name``.
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.i18n import strings_for
from cinoc.interfaces.web.security.csrf import CSRF_HEADER
from cinoc.reports._style import font_face_css

WEB = Path(__file__).resolve().parents[3] / "cinoc" / "interfaces" / "web"
REPORT_CSS = WEB.parents[1] / "reports" / "_assets" / "report.css"
_CSRF = {CSRF_HEADER: "1"}
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08"
    b"\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_no_english_eyebrow_in_the_french_page() -> None:
    fr, en = strings_for("fr"), strings_for("en")
    for key in (k for k in fr if k.endswith("_eyebrow")):
        assert fr[key] != en[key], key
    assert fr["library_eyebrow"] == "Vitrine · bibliothèque"


def _fluxisch_faces(css: str) -> list[str]:
    return [f for f in re.findall(r"@font-face\s*\{[^}]*\}", css) if "Fluxisch" in f]


def test_the_accent_font_never_draws_the_straight_apostrophe() -> None:
    """Fluxisch Else dessine ``'`` comme un accent espacé (« l ’ instant ») :
    l'apostrophe droite retombe sur la police suivante, page et rapport."""
    for css in ((WEB / "static" / "css" / "shell.css").read_text("utf-8"),
                font_face_css()):
        faces = _fluxisch_faces(css)
        assert faces
        for face in faces:
            assert "unicode-range:U+0000-0026,U+0028-10FFFF" in face.replace(" ", "")


def test_a_zip_named_corpus_loses_its_extension() -> None:
    from cinoc.app.corpus_upload import archive_corpus_name

    assert archive_corpus_name("pages.zip") == "pages"
    assert archive_corpus_name("Pages.ZIP") == "Pages"
    assert archive_corpus_name("dossier/lot 1.zip") == "lot 1"
    assert archive_corpus_name("") == ""


def test_the_uploaded_corpus_is_named_without_zip(tmp_path: Path) -> None:
    client = TestClient(create_app(reports_dir=tmp_path / "r",
                                   uploads_dir=tmp_path / "u", rate_limit=1000))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.png", _PNG)
        zf.writestr("a.gt.txt", "v")
    resp = client.post("/api/corpus", headers=_CSRF,
                       files={"file": ("pages.zip", buf.getvalue(), "application/zip")})
    assert resp.status_code == 201
    assert resp.json()["name"] == "pages"


def test_gallery_thumbnails_show_the_whole_page() -> None:
    """``object-fit:cover`` rognait une page large à gauche et à droite."""
    css = REPORT_CSS.read_text("utf-8")
    regle = re.search(r"\.doc-preview-img img\{([^}]*)\}", css)
    assert regle and "object-fit:contain" in regle.group(1)


def test_the_run_log_names_each_document(tmp_path: Path) -> None:
    """Le journal disait ``<heure> · running``, répété, sans document."""
    client = TestClient(create_app(reports_dir=tmp_path, rate_limit=1000))
    job_id = client.post("/api/runs", headers=_CSRF).json()["job_id"]
    deadline = time.time() + 30.0
    while client.get(f"/api/runs/{job_id}").json()["state"] not in {"done", "failed"}:
        assert time.time() < deadline
        time.sleep(0.02)
    datas = [
        json.loads(line[5:])
        for line in client.get(f"/api/runs/{job_id}/events").text.splitlines()
        if line.startswith("data:")
    ]
    unites = [d for d in datas if d.get("document_id")]
    assert unites, "aucun événement ne nomme son document"
    assert all(d["pipeline"] and d["outcome"] for d in unites)
    assert not datas[-1].get("document_id")  # l'état final n'est pas une unité
    js = (WEB / "static" / "js" / "benchmark.js").read_text("utf-8")
    assert "job.document_id" in js and "data-outcome-" in js
    page = client.get("/benchmark").text
    for issue in ("ok", "truncated", "failed", "resumed"):
        assert f'data-outcome-{issue}="' in page


def test_settings_fields_have_an_id_a_name_and_their_label() -> None:
    """Chrome signale tout champ sans ``id`` ni ``name`` ; un ``label for``
    les relie aussi pour un lecteur d'écran."""
    js = (WEB / "static" / "js" / "recipes.js").read_text("utf-8")
    corps = js[js.index("function renderParams"): js.index("function paramInput")]
    assert re.search(r"input\.id\s*=", corps)
    assert re.search(r"input\.name\s*=", corps)
    assert re.search(r"field\.htmlFor\s*=\s*input\.id", corps)
