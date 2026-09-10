"""Saveur **servie** : le rapport web ne porte plus ses images, il les nomme.

Trois saveurs coexistent, et celle-ci existe pour une raison précise. Le rapport
autonome inline ses vignettes en data-URI, ce qui le plafonne à quelques
centaines de documents : au-delà, les suivants perdent leur aperçu **en
silence**, et le HTML pèse des dizaines de mégaoctets. Sur un run de milliers de
pages — le cas que P4 vise — c'est inutilisable.

Servie, la page ne contient que des URL. Le navigateur ne charge que ce qu'il
affiche (les cartes portent ``loading="lazy"``, la galerie est paginée), donc il
n'y a plus de plafond à imposer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.app.demo import demo_run_spec, write_demo_corpus
from cinoc.interfaces.web.app import create_app

_PIL = pytest.importorskip("PIL", reason="vignettes réelles : extra [images]")


def _run_with_images(tmp_path: Path) -> tuple[TestClient, str]:
    """Un rapport sauvé dont les documents portent de **vraies** images."""
    from PIL import Image

    from cinoc.app.modules import ModuleRegistry, register_default_modules
    from cinoc.app.orchestrator import run as run_orchestrator
    from cinoc.app.results import dump_run_result

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir(parents=True)
    corpus = write_demo_corpus(corpus_dir)
    # Le corpus de démo écrit des PNG factices : on les remplace par des images
    # réellement décodables, sinon il n'y aurait rien à servir.
    for document in corpus.documents:
        if document.image_uri:
            Image.new("RGB", (120, 90), "white").save(document.image_uri)

    registry = ModuleRegistry()
    register_default_modules(registry)
    result = run_orchestrator(
        demo_run_spec(corpus, run_id="servi"), registry=registry, code_version="test"
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    dump_run_result(result, str(reports / "servi.json"))
    return TestClient(create_app(reports_dir=reports, rate_limit=1000)), "servi"


def test_the_page_carries_urls_not_bytes(tmp_path: Path) -> None:
    """Le signe distinctif de la saveur : aucune image inlinée dans le HTML."""
    client, name = _run_with_images(tmp_path)

    html = client.get(f"/reports/{name}").text

    assert f"/reports/{name}/image/" in html
    assert "data:image/jpeg;base64," not in html, (
        "la page servie ne doit pas inliner d'octets : c'est ce plafonnement-là "
        "qu'elle existe pour lever"
    )


def test_an_image_is_produced_on_demand(tmp_path: Path) -> None:
    client, name = _run_with_images(tmp_path)

    resp = client.get(f"/reports/{name}/image/folio_001")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content.startswith(b"\xff\xd8\xff")  # en-tête JPEG
    # Un run est immuable : ré-encoder la même vignette à chaque défilement
    # d'une galerie de milliers de cartes serait du gâchis pur.
    assert "immutable" in resp.headers["cache-control"]


def test_the_facsimile_is_larger_than_the_thumbnail(tmp_path: Path) -> None:
    """Deux tailles, une seule image : la galerie et le détail n'ont pas le
    même besoin, et servir la grande partout gâcherait la bande passante."""
    import io

    from PIL import Image

    client, name = _run_with_images(tmp_path)

    petite = client.get(f"/reports/{name}/image/folio_001").content
    grande = client.get(f"/reports/{name}/facsimile/folio_001").content

    with Image.open(io.BytesIO(petite)) as p, Image.open(io.BytesIO(grande)) as g:
        assert max(p.size) <= 280
        assert max(g.size) >= max(p.size)


def test_an_unknown_document_is_404(tmp_path: Path) -> None:
    """L'identifiant est une **clé de recherche**, pas un chemin : inventé, il
    ne désigne rien — il ne peut pas désigner autre chose."""
    client, name = _run_with_images(tmp_path)
    assert client.get(f"/reports/{name}/image/inexistant").status_code == 404


def test_a_traversal_attempt_finds_nothing(tmp_path: Path) -> None:
    client, name = _run_with_images(tmp_path)
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"\x89PNG\r\n\x1a\n")
    for tentative in ("../secret", "..%2Fsecret", "/etc/passwd"):
        resp = client.get(f"/reports/{name}/image/{tentative}")
        assert resp.status_code == 404, tentative


def test_an_unknown_report_is_404(tmp_path: Path) -> None:
    client, _ = _run_with_images(tmp_path)
    assert client.get("/reports/fantome/image/folio_001").status_code == 404


def test_the_downloadable_bundle_still_carries_its_images(tmp_path: Path) -> None:
    """La saveur **dossier** reste hors ligne : c'est sa raison d'être, et
    l'avoir remplacée par des URL l'aurait rendue inutilisable sans serveur."""
    import io as _io
    import zipfile

    client, name = _run_with_images(tmp_path)

    resp = client.get(f"/reports/{name}/bundle.zip")

    assert resp.status_code == 200
    with zipfile.ZipFile(_io.BytesIO(resp.content)) as archive:
        noms = archive.namelist()
        assert "report.html" in noms
        assert any(n.startswith("report-assets/") for n in noms), noms
        html = archive.read("report.html").decode("utf-8")
        assert "report-assets/" in html
        # Aucune **ressource** ne pointe un serveur (le mot « /reports/ »
        # apparaît par ailleurs dans un commentaire du script inliné, qui
        # documente son épinglage CSP — ce n'est pas un lien).
        assert 'src="/reports/' not in html
        assert 'href="/reports/' not in html


def test_no_cap_hides_documents(tmp_path: Path) -> None:
    """Aucun plafond : **tout** document porteur d'image a son href.

    C'est la promesse de la saveur. Le rapport autonome, lui, s'arrête à
    quelques centaines — sans le dire.
    """
    from cinoc.app.report_images import build_served_hrefs
    from cinoc.app.results import load_run_result

    client, name = _run_with_images(tmp_path)
    result = load_run_result(tmp_path / "reports" / "servi.json")
    porteurs = {d.document_id for d in result.documents if d.image_ref}

    hrefs = build_served_hrefs(result, lambda doc: f"/x/{doc}")

    assert set(hrefs) == porteurs
    assert json.dumps(hrefs)  # sérialisable, donc pas d'octets déguisés
