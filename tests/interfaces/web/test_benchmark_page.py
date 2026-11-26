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
#: Le composeur : le catalogue de recettes (D-298).
_RECIPES_JS = _JS.with_name("recipes.js")


def _catalog(tmp_path: Path) -> dict[str, dict[str, object]]:
    """Le catalogue que la page lit, par nom de recette."""
    corps = _client(tmp_path).get("/api/recipes").json()
    return {r["name"]: r for r in corps["recipes"]}


def _brick(recipe: dict[str, object], step: str, kind: str) -> dict[str, object]:
    etape = next(e for e in recipe["steps"] if e["step"] == step)  # type: ignore[attr-defined]
    return next(b for b in etape["bricks"] if b["kind"] == kind)


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
    # Le composeur est le catalogue de recettes ; plus d'onglets (D-298).
    assert 'id="recipe-picker"' in body
    assert "data-mode=" not in body
    # upload + imports ne sont plus ici : déplacés dans la Bibliothèque
    assert 'id="corpus-file"' not in body
    assert 'id="import-source"' not in body


def test_ner_is_an_optional_step_the_page_can_retain(tmp_path: Path) -> None:
    """La case « NER » : une étape facultative de la recette, et son modèle
    spaCy dans les réglages de la brique ``ner`` ; le JS l'envoie dans
    ``optional``."""
    simple = _catalog(tmp_path)["ocr_simple"]
    ner = next(e for e in simple["steps"] if e["step"] == "ner")  # type: ignore[attr-defined]
    assert ner["optional"] is True
    assert any(p["name"] == "model" for p in ner["bricks"][0]["params"])
    js = _RECIPES_JS.read_text(encoding="utf-8")
    assert "data-optional" in js and "optional: optional" in js


def test_char_exclude_field_present_and_sent(tmp_path: Path) -> None:
    # 3c : champ « caractères à exclure » + le JS le met dans le payload du run.
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="char-exclude"' in body
    assert "cfg.char_exclude" in _JS.read_text(encoding="utf-8")


def test_metric_profile_selector_present_and_sent(tmp_path: Path) -> None:
    # 3c : sélecteur de profil de métriques rendu **serveur** (options du
    # catalogue, standard pré-sélectionné) + le JS le met dans le payload du run.
    body = _client(tmp_path).get("/benchmark").text
    assert 'id="metric-profile"' in body
    assert 'value="standard" selected' in body  # défaut historique coché
    assert 'value="philologie"' in body  # profil alternatif proposé
    assert "cfg.metric_profile" in _JS.read_text(encoding="utf-8")


def test_every_launch_carries_the_scoring_options() -> None:
    """Une seule politique de vues (D-297), un seul départ (D-298) : toute la
    file part par ``POST /api/runs`` avec les options de notation — il n'y a
    plus de route à part pour les recettes ni pour la correction."""
    js = _JS.read_text(encoding="utf-8")
    assert "withScoring({ entries:" in js
    assert '"/api/runs"' in js
    for morte in ('"/api/runs/recipe"', '"/api/runs/correction"'):
        assert morte not in js


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


def test_model_suggestions_come_from_the_provider(tmp_path: Path) -> None:
    """L'autocomplétion des modèles par fournisseur : le catalogue donne à
    chaque champ ``model`` d'une brique LLM/VLM l'adresse qui les liste, et le
    composeur la lit en direct (``datalist``)."""
    llm = _catalog(tmp_path)["ocr_puis_llm"]
    modele = next(
        p
        for p in _brick(llm, "correction", "ollama")["params"]  # type: ignore[attr-defined]
        if p["name"] == "model"
    )
    assert modele["models_url"] == "/api/models/ollama"
    js = _RECIPES_JS.read_text(encoding="utf-8")
    assert "models_url" in js and "datalist" in js


def test_an_ocr_engine_that_needs_a_model_asks_for_it(tmp_path: Path) -> None:
    """Kraken, PERO, Calamari, Mistral OCR exigent un modèle (D-268) : le champ
    est **requis**, affiché d'emblée — le gap 2c reste refermé."""
    simple = _catalog(tmp_path)["ocr_simple"]
    for kind in ("kraken", "pero", "calamari", "mistral_ocr"):
        params = _brick(simple, "ocr", kind)["params"]
        assert any(p["name"] == "model" and p["required"] for p in params), kind  # type: ignore[attr-defined]


def test_free_and_curated_prompts_are_offered(tmp_path: Path) -> None:
    """Prompt libre (texte) ET prompts curés (choix) — l'utilisateur choisit ;
    le serveur refuse les deux à la fois."""
    vlm = _catalog(tmp_path)["vlm_seul"]
    params = {p["name"]: p for p in _brick(vlm, "vlm", "ollama")["params"]}  # type: ignore[attr-defined]
    assert params["prompt"]["choices"] == []
    assert "zero_shot_medieval_french" in params["prompt_name"]["choices"]
    assert "correction_medieval_french" in params["prompt_name"]["choices"]
    assert "textarea" in _RECIPES_JS.read_text(encoding="utf-8")


def test_tesseract_offers_its_alto_export(tmp_path: Path) -> None:
    """La case « Exporter l'ALTO » : le réglage ``alto`` de Tesseract, au pli
    de réglages ; l'hybride, lui, a son étape facultative ``alto``."""
    simple = _catalog(tmp_path)["ocr_simple"]
    alto = next(
        p
        for p in _brick(simple, "ocr", "tesseract")["params"]  # type: ignore[attr-defined]
        if p["name"] == "alto"
    )
    assert (alto["type"], alto["required"]) == ("bool", False)
    hybride = _catalog(tmp_path)["segmentation_puis_lecture"]
    etape = next(e for e in hybride["steps"] if e["step"] == "alto")  # type: ignore[attr-defined]
    assert etape["optional"] is True


def test_an_unavailable_brick_is_greyed_with_its_reason(tmp_path: Path) -> None:
    # Les moteurs cloud sans clé sont indisponibles ici → grisés, motif dit.
    simple = _catalog(tmp_path)["ocr_simple"]
    google = _brick(simple, "ocr", "google_vision")
    assert google["available"] is False and google["detail"]
    assert "opt.disabled = !brick.available" in _RECIPES_JS.read_text(encoding="utf-8")


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


@pytest.mark.parametrize("script", [_JS, _RECIPES_JS], ids=lambda p: p.name)
def test_benchmark_js_syntax_is_valid(script: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent : vérification de syntaxe JS ignorée")
    result = subprocess.run(
        [node, "--check", str(script)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# --- Intégration segmentation : hors du composeur principal --------------------


def _benchmark_body(
    tmp_path: Path,
    corpus_store: CorpusStore | None = None,
) -> str:
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates

    from cinoc.adapters.storage.history_store import HistoryStore
    from cinoc.interfaces.web.app import _TEMPLATES_DIR
    from cinoc.interfaces.web.routers.home import build_home_router

    app = FastAPI()
    app.include_router(
        build_home_router(
            tmp_path / "reports",
            Jinja2Templates(directory=_TEMPLATES_DIR),
            statuses=lambda: (),
            third_party=lambda: (),
            history_store=HistoryStore(tmp_path / "h.db"),
            corpus_store=corpus_store,
        )
    )
    return TestClient(app).get("/benchmark").text


def test_the_hybrid_is_a_recipe_with_its_region_preview(tmp_path: Path) -> None:
    # La segmentation N'A PAS de page dédiée : elle se compose comme la recette
    # **segmentation_puis_lecture** (segmenteur + reconnaisseur par bloc), et
    # l'aperçu des régions suit une recette qui segmente.
    body = _benchmark_body(tmp_path)
    assert 'id="seg-preview-box"' in body and 'id="seg-preview-btn"' in body
    hybride = _catalog(tmp_path)["segmentation_puis_lecture"]
    roles = [e["role"] for e in hybride["steps"]]  # type: ignore[attr-defined]
    assert roles[:2] == ["segmenter", "region_recognizer"]
    assert 'select[data-role="segmenter"]' in _JS.read_text(encoding="utf-8")


def test_the_page_no_longer_splits_recipes_from_composed_runs(tmp_path: Path) -> None:
    """« Une recette et un concurrent composé ne partagent pas un run » : la
    limite et son message tombent, il n'y a plus qu'une forme d'entrée."""
    for lang in ("fr", "en"):
        body = _client(tmp_path).get(f"/benchmark?lang={lang}").text
        assert "data-mixed" not in body and "data-recipes" not in body
    assert "mixed" not in _JS.read_text(encoding="utf-8")


def test_benchmark_corpus_select_lists_corpora(tmp_path: Path) -> None:
    from cinoc.domain.corpus import CorpusSpec
    from cinoc.domain.documents import DocumentRef

    store = CorpusStore(tmp_path / "corpora")
    store.materialize(
        lambda dest: CorpusSpec(
            name="Mon corpus", documents=(DocumentRef(id="d1", image_uri="a.png"),)
        )
    )
    body = _benchmark_body(tmp_path, corpus_store=store)
    assert 'id="corpus-select"' in body
    assert "Mon corpus" in body  # rendu comme option du <select>
