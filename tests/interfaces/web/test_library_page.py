"""Page « Bibliothèque » (S6 découverte) : rendu serveur, catalogues mockés."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from cinoc.adapters.corpus.htr_united import HTRUnitedCatalogue, HTRUnitedEntry
from cinoc.adapters.corpus.huggingface import HuggingFaceDataset
from cinoc.adapters.storage.history_store import HistoryStore
from cinoc.app.corpus_upload import CorpusStore
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.interfaces.web.app import _TEMPLATES_DIR, create_app
from cinoc.interfaces.web.routers.home import build_home_router

_HTR_REMOTE = HTRUnitedCatalogue(
    entries=(
        HTRUnitedEntry(
            id="cremma-medieval",
            title="CREMMA Medieval",
            url="https://github.com/HTR-United/cremma-medieval",
            description="Manuscrits médiévaux",
            languages=("fr", "la"),
        ),
    ),
    source="remote",
)
_HF = (
    HuggingFaceDataset(
        dataset_id="Teklia/NorHand",
        title="NorHand",
        description="",
        languages=("no",),
        downloads=1200,
        source="reference",
    ),
)


class _FakeHF:
    last_query: str | None = None

    def search(self, q: str = "", language: str | None = None, **_: object):
        _FakeHF.last_query = q
        return _HF


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    catalogue: HTRUnitedCatalogue = _HTR_REMOTE,
    corpus_store: CorpusStore | None = None,
    curated_author: str | None = None,
    public_mode: bool = False,
) -> TestClient:
    monkeypatch.setattr(
        "cinoc.interfaces.web.routers.home.fetch_catalogue", lambda: catalogue
    )
    monkeypatch.setattr(
        "cinoc.interfaces.web.routers.home.HuggingFaceCatalogue", _FakeHF
    )
    templates = Jinja2Templates(directory=_TEMPLATES_DIR)
    app = FastAPI()
    app.include_router(
        build_home_router(
            tmp_path / "reports",
            templates,
            statuses=lambda: (),
            segmenters=lambda: (),
            third_party=lambda: (),
            history_store=HistoryStore(tmp_path / "h.db"),
            corpus_store=corpus_store,
            curated_author=curated_author,
            public_mode=public_mode,
        )
    )
    return TestClient(app)


def test_library_caches_catalogue_across_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # F1 : deux chargements de /library ne refetchent pas le catalogue HTR-United
    # (cache TTL partagé par le routeur). Compteur sur fetch_catalogue.
    calls = {"n": 0}

    def counting_fetch() -> HTRUnitedCatalogue:
        calls["n"] += 1
        return _HTR_REMOTE

    monkeypatch.setattr(
        "cinoc.interfaces.web.routers.home.fetch_catalogue", counting_fetch
    )
    monkeypatch.setattr(
        "cinoc.interfaces.web.routers.home.HuggingFaceCatalogue", _FakeHF
    )
    templates = Jinja2Templates(directory=_TEMPLATES_DIR)
    app = FastAPI()
    app.include_router(
        build_home_router(
            tmp_path / "reports",
            templates,
            statuses=lambda: (),
            segmenters=lambda: (),
            third_party=lambda: (),
            history_store=HistoryStore(tmp_path / "h.db"),
        )
    )
    client = TestClient(app)
    assert client.get("/library").status_code == 200
    assert client.get("/library").status_code == 200
    assert calls["n"] == 1  # un seul fetch réseau pour deux chargements


def test_library_lists_both_catalogues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _client(tmp_path, monkeypatch).get("/library").text
    assert "CREMMA Medieval" in body  # HTR-United
    assert "Teklia/NorHand" in body  # HuggingFace


def test_library_demo_badge_when_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo = _client(tmp_path, monkeypatch, catalogue=HTRUnitedCatalogue.from_demo())
    assert "démonstration" in demo.get("/library").text
    # catalogue distant → pas de badge démo
    assert "démonstration" not in _client(tmp_path, monkeypatch).get("/library").text


def test_library_search_passes_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeHF.last_query = None
    body = _client(tmp_path, monkeypatch).get("/library?q=latin").text
    assert _FakeHF.last_query == "latin"  # la requête atteint la recherche HF
    assert 'value="latin"' in body  # et est réaffichée dans le formulaire


def test_library_links_corpus_js_and_active_nav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _client(tmp_path, monkeypatch).get("/library").text
    assert 'src="/static/js/corpus.js"' in body  # JS de préparation de corpus
    assert 'aria-current="page"' in body


def test_library_english(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = _client(tmp_path, monkeypatch).get("/library?lang=en").text
    assert "Library" in body and "Search" in body


def test_library_is_live_nav_link_from_home(tmp_path: Path) -> None:
    # L'accueil ne fait aucun appel réseau ; le lien Bibliothèque est vivant.
    client = TestClient(
        create_app(
            reports_dir=tmp_path / "r",
            uploads_dir=tmp_path / "u",
            rate_limit=1000,
        )
    )
    assert 'href="/library?lang=fr"' in client.get("/").text


def _seed_corpora(tmp_path: Path, *names: str) -> CorpusStore:
    store = CorpusStore(tmp_path / "corpora")
    for name in names:
        store.materialize(
            lambda dest, n=name: CorpusSpec(
                name=n, documents=(DocumentRef(id="d1", image_uri="a.png"),)
            )
        )
    return store


def test_library_lists_stored_corpora(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _seed_corpora(tmp_path, "Beta corpus", "Alpha corpus")
    body = _client(tmp_path, monkeypatch, corpus_store=store).get("/library").text
    assert "Alpha corpus" in body and "Beta corpus" in body
    # triés par nom : Alpha avant Beta
    assert body.index("Alpha corpus") < body.index("Beta corpus")


def test_library_corpora_empty_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _client(tmp_path, monkeypatch).get("/library").text
    assert "Aucun corpus local" in body


def test_library_has_upload_and_import_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _client(tmp_path, monkeypatch).get("/library").text
    assert 'id="corpus-file"' in body  # upload ZIP
    assert 'id="dropzone"' in body  # zone de glisser-déposer
    for source in ("iiif", "gallica", "escriptorium", "huggingface", "curated"):
        assert f'data-source-tab="{source}"' in body
    for source in ("iiif", "gallica", "escriptorium", "curated"):
        assert f'data-import-source="{source}"' in body
    assert 'data-import-source="huggingface"' in body
    for name in ("manifest_url", "ark", "base_url", "token", "repo_id", "revision"):
        assert f'name="{name}"' in body


def test_library_imports_hidden_in_public_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _client(tmp_path, monkeypatch, public_mode=True).get("/library").text
    assert 'id="import-source"' not in body  # fetch serveur → masqué en public
    assert 'id="corpus-file"' in body  # l'upload de fichier local reste


def test_corpus_js_syntax_is_valid() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent : vérification de syntaxe JS ignorée")
    js = Path(__file__).resolve().parents[3] / (
        "cinoc/interfaces/web/static/js/corpus.js"
    )
    result = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# --- Découverte des datasets curés du compte (CINOC_HF_AUTHOR) -----------------


def test_curated_datasets_listed_with_one_click_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cinoc.adapters.corpus.huggingface import CuratedDatasetRef

    monkeypatch.setattr(
        "cinoc.interfaces.web.routers.home.discover_curated",
        lambda author, **_: (
            CuratedDatasetRef(
                repo_id=f"{author}/Cinoc-Dresden",
                title=f"{author}/Cinoc-Dresden",
                revision="abc123def",
                last_modified="2026-06-01",
            ),
        ),
    )
    body = _client(tmp_path, monkeypatch, curated_author="me").get("/library").text
    # carte rendue + bouton d'import en un clic (repo_id + révision pinnée).
    assert "me/Cinoc-Dresden" in body
    assert 'data-repo-id="me/Cinoc-Dresden"' in body
    assert 'data-revision="abc123def"' in body


def test_no_curated_section_without_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(author: str, **_: object) -> object:
        raise AssertionError("aucune découverte sans compte configuré")

    monkeypatch.setattr(
        "cinoc.interfaces.web.routers.home.discover_curated", boom
    )
    body = _client(tmp_path, monkeypatch).get("/library").text
    assert "data-repo-id=" not in body  # pas de carte curée découverte
