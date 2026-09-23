"""Page « Banc d'essai » (TU2.f) : rendu serveur + JS auto-hébergé + CSP ouverte.

Le comportement *navigateur* (fetch + EventSource) n'est pas exécutable en CI
(pas de navigateur) ; on vérifie ici la **surface serveur** : la page existe au
design, lie son JS, la nav est vivante, le JS est servi et sa **syntaxe valide**
(``node --check``), et la CSP autorise bien ``script-src``/``connect-src 'self'``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.app.corpus_upload import CorpusStore
from cinoc.interfaces.web.app import create_app

_JS = Path(__file__).resolve().parents[3] / (
    "cinoc/interfaces/web/static/js/benchmark.js"
)


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(reports_dir=tmp_path, rate_limit=1000))


def test_benchmark_page_renders_with_launcher(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/benchmark")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert 'id="launch"' in body  # le bouton de lancement
    assert 'src="/static/js/benchmark.js"' in body  # le JS est lié
    assert "Lancer le benchmark" in body  # libellé du lanceur (FR par défaut)


def test_benchmark_has_corpus_and_composer_controls(tmp_path: Path) -> None:
    # Le corpus est SÉLECTIONNÉ ici (préparé dans la Bibliothèque), pas téléversé.
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="corpus-select"' in body  # <select> de corpus existants
    assert 'id="queue-list"' in body  # file de concurrents rendue côté client
    assert 'id="queue-row-tpl"' in body  # gabarit de ligne de file
    assert 'data-mode="ocr_only"' in body  # sélecteur de mode par onglets
    # moteurs câblés présents dans le catalogue (par rôle) ; precomputed = démo, exclu.
    for label in ("Tesseract", "OpenAI", "Ollama"):
        assert label in body
    # upload + imports ne sont plus ici : déplacés dans la Bibliothèque
    assert 'id="corpus-file"' not in body
    assert 'id="import-source"' not in body


def test_ner_toggle_present_and_sent(tmp_path: Path) -> None:
    # Case « NER » du composeur rendue serveur + le JS la met dans le payload du
    # concurrent (et porte le modèle spaCy optionnel).
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="draft-ner"' in body
    assert 'id="draft-ner-model"' in body
    js = _JS.read_text(encoding="utf-8")
    assert "entry.ner = true" in js
    assert "ner_model" in js


def test_char_exclude_field_present_and_sent(tmp_path: Path) -> None:
    # 3c : champ « caractères à exclure » + le JS le met dans le payload du run.
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="char-exclude"' in body
    assert "payload.char_exclude" in _JS.read_text(encoding="utf-8")


def test_metric_profile_selector_present_and_sent(tmp_path: Path) -> None:
    # 3c : sélecteur de profil de métriques rendu **serveur** (options du
    # catalogue, standard pré-sélectionné) + le JS le met dans le payload du run.
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="metric-profile"' in body
    assert 'value="standard" selected' in body  # défaut historique coché
    assert 'value="philologie"' in body  # profil alternatif proposé
    assert "payload.metric_profile" in _JS.read_text(encoding="utf-8")


def test_config_io_controls_present_and_wired(tmp_path: Path) -> None:
    # A : export/import de la config du formulaire (save/load JSON). L'import
    # valide côté serveur (/api/runs/config) avant de repeupler.
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="config-export"' in body  # bouton d'export (download blob)
    assert 'id="config-import"' in body  # input fichier d'import
    js = _JS.read_text(encoding="utf-8")
    assert "/api/runs/config" in js  # le JS valide la config déposée
    assert "cinoc-config.json" in js  # nom du fichier exporté


def test_normalization_preview_widget_and_api_wired(tmp_path: Path) -> None:
    # 3c : aperçu de normalisation (échantillon + config custom) + le JS poste à l'API.
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="norm-sample"' in body  # échantillon
    assert 'id="norm-config"' in body  # config YAML custom (sans persistance)
    assert 'id="norm-preview-btn"' in body and 'id="norm-result"' in body
    assert "/api/normalization/preview" in _JS.read_text(encoding="utf-8")


def test_model_suggestions_datalist_and_api_wired(tmp_path: Path) -> None:
    # 3c : datalist canonique (peuplée via /api/models) + le JS interroge l'API.
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="api-model-list"' in body  # cible des suggestions openai/anthropic
    assert "/api/models/" in _JS.read_text(encoding="utf-8")  # le JS la consomme


def test_model_field_shown_in_ocr_only_mode(tmp_path: Path) -> None:
    # 3c : le champ « Modèle » est désormais visible aussi en OCR seul (pour
    # kraken/pero/calamari/mistral_ocr qui exigent un modèle) — gap 2c refermé.
    body = _client(tmp_path).get("/benchmark").text
    assert 'data-show="ocr_only text_only text_and_image zero_shot hybrid"' in body
    assert 'id="draft-model"' in body


def test_benchmark_exposes_prompt_inputs(tmp_path: Path) -> None:
    # Prompt libre (textarea) ET prompts curés (select) — l'utilisateur choisit.
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="draft-prompt"' in body  # textarea : écrire son propre prompt
    assert 'id="draft-prompt-curated"' in body  # select : prompts curés par période
    assert "correction_medieval_french" in body  # noms rendus serveur (dynamiques)
    assert "zero_shot_medieval_french" in body


def test_benchmark_engine_select_disables_unavailable(tmp_path: Path) -> None:
    # tesseract indisponible ici (ni binaire ni pytesseract) → option disabled.
    body = _client(tmp_path).get("/benchmark").text
    # l'option précomputed (toujours dispo) n'est pas désactivée ; au moins une l'est
    assert "disabled" in body


def test_nav_links_benchmark_and_reports(tmp_path: Path) -> None:
    # depuis l'accueil, « Banc d'essai » est un lien vivant (plus un placeholder)
    home = _client(tmp_path).get("/").text
    assert 'href="/benchmark?lang=fr"' in home
    # depuis le banc d'essai, « Rapports » reste accessible
    bench = _client(tmp_path).get("/benchmark").text
    assert 'href="/?lang=fr"' in bench
    assert 'aria-current="page"' in bench  # l'onglet courant est marqué


def test_benchmark_english(tmp_path: Path) -> None:
    body = _client(tmp_path).get("/benchmark?lang=en").text
    assert "Run the benchmark" in body


def test_skip_link_and_landmark_present(tmp_path: Path) -> None:
    # Lien d'évitement clavier + cible de saut (a11y).
    body = _client(tmp_path).get("/benchmark").text
    assert 'class="skip-link"' in body
    assert 'href="#main-content"' in body
    assert 'id="main-content"' in body
    assert "Aller au contenu" in body  # libellé FR
    en = _client(tmp_path).get("/benchmark?lang=en").text
    assert "Skip to content" in en


def test_run_progress_has_progressbar_role(tmp_path: Path) -> None:
    # La barre de progression annonce sa valeur aux lecteurs d'écran.
    body = _client(tmp_path).get("/benchmark").text
    assert 'role="progressbar"' in body
    assert 'aria-valuemin="0"' in body
    assert 'aria-valuemax="100"' in body
    assert 'aria-valuenow="0"' in body
    assert 'role="status"' in body  # la zone enveloppe est une live-region


def test_js_asset_is_served(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/static/js/benchmark.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


def test_csp_allows_self_script_and_connect(tmp_path: Path) -> None:
    csp = _client(tmp_path).get("/benchmark").headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "connect-src 'self'" in csp


def test_benchmark_js_syntax_is_valid() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent : vérification de syntaxe JS ignorée")
    result = subprocess.run(
        [node, "--check", str(_JS)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# --- Intégration segmentation : hors du composeur principal --------------------

def _benchmark_body(
    tmp_path: Path,
    segmenter_available: bool,
    corpus_store: CorpusStore | None = None,
) -> str:
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates

    from cinoc.adapters.storage.history_store import HistoryStore
    from cinoc.app.engines import EngineStatus
    from cinoc.interfaces.web.app import _TEMPLATES_DIR
    from cinoc.interfaces.web.routers.home import build_home_router

    detail = "ok" if segmenter_available else "PaddleX absent (extra [segment])"
    status = EngineStatus(
        kind="pp_doclayout",
        label="PP-DocLayout",
        available=segmenter_available,
        detail=detail,
    )
    app = FastAPI()
    app.include_router(
        build_home_router(
            tmp_path / "reports",
            Jinja2Templates(directory=_TEMPLATES_DIR),
            statuses=lambda: (),
            segmenters=lambda: (status,),
            third_party=lambda: (),
            history_store=HistoryStore(tmp_path / "h.db"),
            corpus_store=corpus_store,
        )
    )
    return TestClient(app).get("/benchmark").text


def test_hybrid_mode_exposed_in_benchmark_composer(tmp_path: Path) -> None:
    # La segmentation N'A PLUS de page dédiée : elle se compose comme un mode
    # **Hybride** du Banc d'essai (segmenteur + reconnaisseur par bloc).
    body = _benchmark_body(tmp_path, segmenter_available=True)
    assert 'data-mode="hybrid"' in body
    assert 'id="draft-segmenter"' in body
    assert 'id="draft-recognizer"' in body
    assert "PP-DocLayout" in body  # le segmenteur du socle est listé dans le mode


def test_benchmark_corpus_select_lists_corpora(tmp_path: Path) -> None:
    from cinoc.domain.corpus import CorpusSpec
    from cinoc.domain.documents import DocumentRef

    store = CorpusStore(tmp_path / "corpora")
    store.materialize(
        lambda dest: CorpusSpec(
            name="Mon corpus", documents=(DocumentRef(id="d1", image_uri="a.png"),)
        )
    )
    body = _benchmark_body(tmp_path, segmenter_available=False, corpus_store=store)
    assert 'id="corpus-select"' in body
    assert "Mon corpus" in body  # rendu comme option du <select>
