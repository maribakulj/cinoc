"""Un rapport **déposé** relit ses images contre son dossier de dépôt (D-282, D-305).

Reste de S10b : depuis D5, ``cinoc run`` écrit les références d'image
**relatives** au dossier de la spec (``corpus/folio_001.png``) — aucun chemin
de la machine ne fuit. Mais la vitrine relisait **tout** rapport contre le
dossier des corpus déposés par la page : un ``RunResult`` produit par la CLI
puis servi par ``cinoc serve --reports-dir`` retombait sur l'aperçu
synthétique (les absolus d'avant D5 marchaient, sur la même machine).

La racine d'un rapport déposé est **son dossier de dépôt** ; celle d'un run
lancé depuis la page reste le dossier des corpus déposés. Dans les deux cas,
la relecture est confinée : ni ``..``, ni un absolu qui sort de la racine
n'atteint un fichier.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.interfaces.cli import main
from cinoc.interfaces.web.app import create_app

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"

_PIL = pytest.importorskip("PIL.Image", reason="vignettes réelles : extra [images]")


def _project(tmp_path: Path) -> Path:
    """L'exemple livré, avec de vraies images à côté de ses sorties figées."""
    projet = tmp_path / "projet"
    shutil.copytree(EXAMPLES, projet)
    for gt in (projet / "corpus").glob("*.gt.txt"):
        stem = gt.name.split(".")[0]
        _PIL.new("RGB", (120, 90), "white").save(projet / "corpus" / f"{stem}.png")
    return projet


def _client(reports: Path, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            reports_dir=reports,
            data_dir=tmp_path / "donnees",
            uploads_dir=tmp_path / "depots",
            rate_limit=1000,
        )
    )


def test_a_cli_report_served_from_its_folder_finds_its_images(tmp_path: Path) -> None:
    """Le parcours exact : ``cinoc run --json`` à côté de la spec, puis
    ``cinoc serve --reports-dir`` sur ce dossier."""
    projet = _project(tmp_path)
    assert main(["run", str(projet / "config.yaml"), "-o", str(tmp_path / "r.html"),
                 "--json", str(projet / "exemple.json")]) == 0
    refs = {d["image_ref"] for d in json.loads(
        (projet / "exemple.json").read_text(encoding="utf-8"))["documents"]}
    assert refs == {f"corpus/{d}.png" for d in (
        "folio_001", "folio_002", "folio_003", "imprime_001", "imprime_002")}

    client = _client(projet, tmp_path)
    html = client.get("/reports/exemple").text
    assert "/reports/exemple/image/folio_001" in html

    image = client.get("/reports/exemple/image/folio_001")
    assert image.status_code == 200, "l'image du rapport déposé est introuvable"
    assert image.content.startswith(b"\xff\xd8\xff")
    assert client.get("/reports/exemple/facsimile/folio_001").status_code == 200


def _baked(reports: Path, name: str, image_ref: str) -> None:
    """Un rapport déposé d'un seul document, dont l'image est ``image_ref``."""
    gabarit = json.loads(
        (Path(__file__).resolve().parents[3] / "deploy" / "reports"
         / "demonstration.json").read_text(encoding="utf-8")
    )
    premier = gabarit["documents"][0]["document_id"]
    for document in gabarit["documents"]:
        ref = image_ref if document["document_id"] == premier else None
        document["image_ref"] = ref
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{name}.json").write_text(json.dumps(gabarit), encoding="utf-8")


def _first_document(reports: Path, name: str) -> str:
    data = json.loads((reports / f"{name}.json").read_text(encoding="utf-8"))
    return str(data["documents"][0]["document_id"])


@pytest.mark.parametrize("ref", ["../secret.png", "corpus/../../secret.png"])
def test_a_relative_ref_never_leaves_the_deposit_folder(
    tmp_path: Path, ref: str
) -> None:
    reports = tmp_path / "rapports"
    _PIL.new("RGB", (40, 30), "red").save(tmp_path / "secret.png")
    _baked(reports, "fuite", ref)
    client = _client(reports, tmp_path)
    doc = _first_document(reports, "fuite")

    assert client.get(f"/reports/fuite/image/{doc}").status_code == 404
    assert f"/reports/fuite/image/{doc}" not in client.get("/reports/fuite").text


def test_an_absolute_ref_outside_the_root_is_not_served(tmp_path: Path) -> None:
    """Un JSON déposé ne fait pas lire au serveur un fichier de son choix —
    ni en vignette, ni dans le bundle téléchargeable."""
    import io
    import zipfile

    reports = tmp_path / "rapports"
    secret = tmp_path / "ailleurs" / "secret.png"
    secret.parent.mkdir()
    _PIL.new("RGB", (40, 30), "red").save(secret)
    _baked(reports, "absolu", str(secret.resolve()))
    client = _client(reports, tmp_path)
    doc = _first_document(reports, "absolu")

    assert client.get(f"/reports/absolu/image/{doc}").status_code == 404
    bundle = client.get("/reports/absolu/bundle.zip")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert not [n for n in archive.namelist() if n.startswith("report-assets/")]


def test_an_absolute_ref_inside_the_root_is_still_served(tmp_path: Path) -> None:
    reports = tmp_path / "rapports"
    reports.mkdir()
    image = reports / "corpus" / "p.png"
    image.parent.mkdir()
    _PIL.new("RGB", (40, 30), "white").save(image)
    _baked(reports, "interne", str(image.resolve()))
    client = _client(reports, tmp_path)
    doc = _first_document(reports, "interne")

    assert client.get(f"/reports/interne/image/{doc}").status_code == 200


def test_a_server_run_still_reads_against_the_uploaded_corpora(tmp_path: Path) -> None:
    """Un rapport que le serveur a écrit (absent du dossier de dépôt, ou
    réécrit par un run homonyme) se relit contre les corpus déposés."""
    reports = tmp_path / "rapports"
    reports.mkdir()
    depots = tmp_path / "depots"
    (depots / "c1").mkdir(parents=True)
    _PIL.new("RGB", (40, 30), "white").save(depots / "c1" / "p.png")
    donnees = tmp_path / "donnees"
    _baked(donnees, "web-run", "c1/p.png")
    # Un rapport déposé homonyme, que le run du serveur a remplacé dans le
    # dossier de données : ce n'est plus la graine, il ne se relit plus contre
    # le dossier de dépôt.
    _baked(donnees, "homonyme", "c1/p.png")
    _baked(reports, "homonyme", "autre/p.png")
    client = _client(reports, tmp_path)

    for name in ("web-run", "homonyme"):
        doc = _first_document(donnees, name)
        assert client.get(f"/reports/{name}/image/{doc}").status_code == 200, name
