"""Chaînes bilingues FR/EN de la coquille web (couche 8).

Rendu **serveur**, pas de SPA : la langue est choisie par le paramètre de
requête ``?lang=`` (défaut ``fr``) et les chaînes sont injectées dans le
gabarit Jinja2. Pas d'état, pas d'effet de bord — un simple dictionnaire de
données (réf. ``design/js/i18n.jsx``, porté au strict besoin de la coquille).
"""

from __future__ import annotations

#: Langues servies. ``fr`` est la primaire (cf. spec) ; tout autre code retombe
#: dessus via :func:`normalize_lang`.
LANGUAGES: tuple[str, ...] = ("fr", "en")
DEFAULT_LANG = "fr"

_STRINGS: dict[str, dict[str, str]] = {
    "fr": {
        "nav_library": "Bibliothèque",
        "nav_benchmark": "Banc d'essai",
        "nav_reports": "Rapports",
        "nav_history": "Historique",
        "nav_engines": "Moteurs",
        "wordmark_sub": "OCR · HTR · VLM",
        "hero_eyebrow": "Vitrine · lecture seule",
        "hero_desc": "Rapports de benchmark déterministes — "
        "OCR / HTR / VLM sur corpus patrimoniaux.",
        "stat_reports": "rapports",
        "reports_title": "Rapports générés",
        "reports_desc": "Historique des benchmarks, rendus HTML autonomes.",
        "skip_to_content": "Aller au contenu",
        "bench_progress_label": "Progression du run",
        # NB : la sous-chaîne « aucun rapport » est attendue par les tests.
        "reports_empty": "aucun rapport disponible pour l'instant.",
        "open_report": "Ouvrir",
        "download_zip": "Télécharger (ZIP)",
        "download_alto": "Télécharger l'ALTO (ZIP)",
        # Banc d'essai (lanceur interactif)
        "bench_eyebrow": "Banc d'essai · comparer",
        "bench_title": "Banc d'essai",
        "bench_desc": "Compose des concurrents (OCR, OCR→LLM, VLM) et compare-les "
        "sur un corpus, en un seul run. Sans concurrent : démonstration.",
        "bench_run": "Lancer le benchmark",
        "bench_correction": "Post-correction structurée",
        "bench_correction_hint": "Corrige un corpus d'ALTO déjà là, **dans** sa "
        "mise en page : chaque ligne garde son identifiant, donc le rapport dit "
        "ce qui a été changé et ce que le correcteur a refusé de changer.",
        "bench_correction_producer": "Producteur de corrections",
        "bench_correction_rules": "Règles (déterministe, hors ligne)",
        "bench_correction_ollama": "Ollama (serveur local)",
        "bench_correction_model": "Modèle ollama",
        "bench_correction_model_ph": "ex. gemma4:e2b",
        "bench_correction_host": "Serveur ollama",
        "bench_correction_launch": "Corriger ce corpus",
        "bench_correction_no_corpus": "Choisis d'abord un corpus.",
        "bench_correction_gt_hint": "Le corpus doit porter une transcription à "
        "part (<nom>.gt.txt) à côté de son ALTO. Sans elle, la référence est "
        "extraite de l'ALTO lui-même : le correcteur partirait du texte auquel "
        "on le compare, et le score ne voudrait rien dire.",
        "bench_launching": "Lancement…",
        "bench_status": "État",
        "bench_log": "Journal",
        "bench_idle": "Prêt.",
        "bench_net_error": "Erreur réseau.",
        "bench_corpus": "Corpus",
        "bench_corpus_none": "aucun corpus (démo)",
        "bench_corpus_prepare": "Choisir dans la Bibliothèque",
        "bench_corpus_selected": "Corpus prêt à exécuter",
        "bench_corpus_select_hint": "Sélectionne un corpus préparé, ou reste "
        "en démonstration.",
        "bench_competitors": "Concurrents",
        "bench_add_competitor": "Ajouter un concurrent",
        "bench_queue_empty": "Aucun concurrent ajouté pour l'instant.",
        "bench_queue_title": "File prête à exécuter",
        "bench_queue_hint": "Chaque ligne résume un pipeline réellement lancé.",
        "bench_remove": "Retirer",
        "bench_mode": "Mode",
        "bench_mode_ocr": "OCR seul",
        "bench_mode_text": "OCR → LLM (texte)",
        "bench_mode_image": "OCR → LLM (image+texte)",
        "bench_mode_vlm": "VLM (zero-shot)",
        "bench_mode_hybrid": "Hybride (segmentation)",
        "bench_ocr_engine": "Moteur OCR",
        "bench_segmenter": "Segmenteur",
        "bench_segmenter_hint": "Détecte les régions en tête de pipeline ; le "
        "distant délègue à un endpoint HF (modèle changé via l'URL).",
        "bench_recognizer": "Reconnaisseur par bloc",
        "bench_recognizer_hint": "Moteur appliqué à chaque bloc découpé : un OCR "
        "réel, ou un VLM qui transcrit l'image du bloc (zero-shot). Texte assemblé "
        "scoré CER/WER comme un pipeline à plat.",
        "bench_seg_preview": "Aperçu des régions",
        "bench_seg_preview_btn": "Prévisualiser la segmentation",
        "bench_seg_preview_hint": "Lance le segmenteur sur le corpus choisi et "
        "affiche les régions détectées (avant de lancer le benchmark).",
        "bench_seg_preview_no_corpus": "Choisis d'abord un corpus.",
        "bench_llm": "LLM",
        "bench_vlm": "VLM",
        "bench_model": "Modèle",
        "bench_model_ph": "modèle (optionnel)",
        "bench_prompt": "Prompt",
        "bench_prompt_ph": "Vide = prompt par défaut. Pour la correction, inclus "
        "{ocr_text} là où le texte OCR doit être inséré (sinon il est ignoré).",
        "bench_prompt_curated_none": "— Prompt curé (par période) —",
        "bench_prompt_hint": "Choisis un prompt curé OU écris le tien ci-dessous "
        "(le texte libre est prioritaire).",
        "bench_ner": "Extraire les entités nommées (NER)",
        "bench_ner_model_ph": "modèle spaCy (défaut fr_core_news_sm)",
        "bench_ner_hint": "Ajoute une étape NER en fin de pipeline ; scorée "
        "(F1) si le corpus porte une vérité-terrain d'entités.",
        "bench_alto": "Exporter l'ALTO (XML)",
        "bench_alto_hint": "Tesseract uniquement : produit un ALTO XML par "
        "document (géométrie + texte), téléchargeable depuis le rapport — "
        "ré-importable dans eScriptorium ou Transkribus.",
        "bench_normalization": "Normalisation",
        "bench_norm_preview": "Aperçu de normalisation",
        "bench_norm_sample_ph": "Colle un échantillon de texte pour voir l'effet…",
        "bench_norm_custom": "Profil personnalisé (YAML) — prioritaire si rempli",
        "bench_norm_config_ph": "caseless: true\nexclude_chars: \",.;:\"",
        "bench_norm_preview_btn": "Aperçu",
        "bench_char_exclude": "Caractères à exclure",
        "bench_char_exclude_ph": "ex : ,.;:!? — exclus des deux côtés",
        "bench_char_exclude_hint": "Filtrés de la GT ET de l'hypothèse avant le "
        "calcul (ne mesure plus ces caractères).",
        "bench_metric_profile": "Profil de métriques",
        "bench_metric_profile_hint": "Choisit les colonnes de classement du "
        "rapport ; n'allège pas la donnée collectée (sections inchangées).",
        "bench_config_io": "Configuration",
        "bench_config_export": "Exporter (JSON)",
        "bench_config_import": "Importer…",
        "bench_config_loaded": "Configuration chargée.",
        "bench_config_invalid": "Fichier de configuration invalide.",
        "bench_config_hint": "Sauvegarde l'état du formulaire (concurrents + "
        "options) en JSON ; rechargeable plus tard. Aucune persistance serveur.",
        "bench_options": "Options",
        "bench_execute_desc": "Lance le run puis ouvre le rapport final ou la "
        "vue de segmentation.",
        "bench_norm_none": "(aucune)",
        "bench_error_422": "Configuration incomplète ou invalide.",
        "bench_error_404": "Corpus introuvable.",
        "bench_error_409": "Un moteur requis est indisponible.",
        "bench_error_403": "Action refusée dans ce mode.",
        "bench_error_fallback": "Erreur de lancement.",
        # Import de corpus distant
        "imp_btn": "Importer",
        "imp_manifest": "URL du manifeste IIIF",
        "imp_ark": "ARK Gallica (ark:/12148/…)",
        "imp_ocr": "Inclure l'OCR de référence",
        "imp_base": "URL de l'instance eScriptorium",
        "imp_token": "Token d'API",
        "imp_doc": "PK du document",
        "imp_layer": "Couche de transcription",
        "imp_limit": "Limite (pages)",
        "imp_name": "Nom (optionnel)",
        "imp_repo": "Dépôt HF (org/nom-du-dataset)",
        "imp_revision": "Révision (SHA — recommandé pour l'épinglage)",
        "imp_curated_hint": "Dataset de référence Cinoc publié sur HuggingFace : "
        "le manifeste et la vérité-terrain sont rapatriés ; les images restent "
        "des références distantes (IIIF statique servi par HF, épinglé à la "
        "révision), téléchargées automatiquement au moment du run.",
        # Aperçu de mise en page (panneau du lanceur) + reconnaisseur hybride :
        # vestiges utiles de l'ancienne page /segmentation, repris par le composeur.
        "seg_run_endpoint": "Endpoint (object-detection HF)",
        "seg_run_endpoint_ph": "https://…",
        "seg_run_token": "Jeton (optionnel)",
        "seg_run_running": "Segmentation en cours…",
        "hyb_run_vlm": "VLM, zero-shot",
        "open_report_full": "Ouvrir le rapport",
        "sys_version": "Version",
        "sys_mode": "Mode",
        "sys_mode_value": "local · interactif",
        "sys_active_job": "Tâche active",
        "sys_idle": "au repos",
        "sys_details": "Détails système",
        "sys_pipeline": "Pipeline",
        "sys_pipeline_ready": "moteurs prêts",
        "sys_open": "Système · détails",
        # Page « Moteurs »
        "engines_eyebrow": "Vitrine · moteurs",
        "engines_title": "Moteurs",
        "engines_desc": "Disponibilité runtime des moteurs du socle : binaire, SDK, "
        "clé d'API. Un moteur cloud est prêt dès que son SDK et sa clé sont là.",
        "stat_ready": "prêts",
        "engines_col_engine": "Moteur",
        "engines_col_status": "État",
        "engines_col_detail": "Détail",
        "engine_available": "disponible",
        "engine_unavailable": "indisponible",
        "history_eyebrow": "Vitrine · longitudinal",
        "history_title": "Historique",
        "history_desc": "Évolution des métriques par moteur au fil des runs ; "
        "régressions signalées entre les deux derniers runs.",
        "history_stat_runs": "mesures",
        "history_trends_title": "Tendances",
        "history_trends_desc": "Évolution du CER par moteur au fil des runs "
        "(échelle locale). Pente OLS par jour ; rupture signalée seulement si "
        "le test de Pettitt est significatif (p ≤ 0,05).",
        "history_slope": "pente/j",
        "history_rupture": "rupture dès",
        "history_regressions_title": "Régressions",
        "history_regressions_desc": "Métriques dégradées entre les deux runs les "
        "plus récents (plus bas = meilleur).",
        "history_no_regressions": "Aucune régression détectée.",
        "history_log_title": "Journal des mesures",
        "history_log_desc": "Chaque agrégat enregistré, du plus récent au plus ancien.",
        "history_empty": "Aucun run enregistré pour l'instant.",
        "history_col_run": "Run",
        "history_col_pipeline": "Moteur",
        "history_col_view": "Vue",
        "history_col_metric": "Métrique",
        "history_col_value": "Valeur",
        "history_col_change": "Évolution",
        "library_eyebrow": "VIEW · LIBRARY",
        "library_title": "Bibliothèque de corpus",
        "library_desc": "Corpus locaux et catalogues distants — toute la matière "
        "en un seul endroit.",
        "library_search_button": "Rechercher",
        "library_demo_badge": "catalogue de démonstration (hors-ligne)",
        "library_open": "ouvrir",
        "library_corpora_title": "Mes corpus",
        "library_local_title": "Corpus locaux",
        "library_corpora_desc": "Téléversés, importés depuis HTR-United / "
        "HuggingFace, ou pointés depuis le filesystem.",
        "library_corpora_empty": "Aucun corpus local. Importez-en un.",
        "library_corpora_cta": "Préparer un corpus",
        "library_corpora_manage": "Corpus enregistrés",
        "library_stat_local": "locaux",
        "library_stat_pages": "pages",
        "library_discover": "Découvrir",
        "library_discover_desc": "Explorer une source à la fois, puis importer "
        "ce qui est utile.",
        "library_remote_title": "Sources distantes",
        "library_catalogue": "catalogue",
        "library_manifest": "manifeste",
        "library_source_htr": "HTR-United",
        "library_source_hf": "HuggingFace",
        "library_source_iiif": "IIIF",
        "library_source_gallica": "Gallica",
        "library_source_escriptorium": "eScriptorium",
        "library_source_curated": "Cinoc curé",
        "library_curated_yours": "Vos datasets curés",
        "library_curated_yours_hint": "Datasets curés Cinoc détectés sur votre "
        "compte HuggingFace (tag cinoc-corpus) — importez-en un en un clic.",
        "library_curated_empty": "Aucun dataset curé détecté automatiquement. Sur "
        "un Space, vos datasets tagués cinoc-corpus apparaissent ici sans réglage ; "
        "en local, posez un jeton HF ou CINOC_HF_AUTHOR. Sinon, importez par "
        "identifiant ci-dessous.",
        "library_zip_meta": "ZIP · max 500 MB · paires auto-détectées",
        "library_ready": "prêt pour benchmark",
        "library_add_desc": "Téléversez un ZIP (glisser-déposer) ou importez "
        "depuis une source distante.",
        "library_drop_hint": "Glissez un .zip ici ou cliquez pour sélectionner",
        "library_doc_preview": "documents",
        "library_gt_preview": "vérités terrain",
        "library_source_label": "source",
        "library_language_label": "langue",
        "library_open_source": "Ouvrir la source",
        "library_import_source": "Importer depuis cette source",
        "library_search_hint_htr": "Filtrer le catalogue HTR-United",
        "library_search_hint_hf": "Filtrer les datasets HuggingFace",
        "library_use": "Utiliser",
        "library_delete": "Supprimer",
        "library_empty": "Aucun résultat.",
        "lang_label": "Langue",
    },
    "en": {
        "nav_library": "Library",
        "nav_benchmark": "Benchmark",
        "nav_reports": "Reports",
        "nav_history": "History",
        "nav_engines": "Engines",
        "wordmark_sub": "OCR · HTR · VLM",
        "hero_eyebrow": "Showcase · read-only",
        "hero_desc": "Deterministic benchmark reports — "
        "OCR / HTR / VLM on heritage corpora.",
        "stat_reports": "reports",
        "reports_title": "Generated reports",
        "reports_desc": "Benchmark history, standalone HTML renders.",
        "skip_to_content": "Skip to content",
        "bench_progress_label": "Run progress",
        "reports_empty": "no report available yet.",
        "open_report": "Open",
        "download_zip": "Download (ZIP)",
        "download_alto": "Download ALTO (ZIP)",
        "bench_eyebrow": "Benchmark · compare",
        "bench_title": "Benchmark",
        "bench_desc": "Compose competitors (OCR, OCR→LLM, VLM) and compare them "
        "on a corpus, in a single run. No competitor: demonstration.",
        "bench_run": "Run the benchmark",
        "bench_correction": "Structured post-correction",
        "bench_correction_hint": "Corrects an existing ALTO corpus *inside* its "
        "layout: every line keeps its identifier, so the report can say what was "
        "changed and what the corrector refused to change.",
        "bench_correction_producer": "Correction producer",
        "bench_correction_rules": "Rules (deterministic, offline)",
        "bench_correction_ollama": "Ollama (local server)",
        "bench_correction_model": "Ollama model",
        "bench_correction_model_ph": "e.g. gemma4:e2b",
        "bench_correction_host": "Ollama server",
        "bench_correction_launch": "Correct this corpus",
        "bench_correction_no_corpus": "Pick a corpus first.",
        "bench_correction_gt_hint": "The corpus must carry a separate "
        "transcription (<name>.gt.txt) beside its ALTO. Without one, the "
        "reference is extracted from the ALTO itself: the corrector would start "
        "from the very text it is scored against, and the score would be void.",
        "bench_launching": "Launching…",
        "bench_status": "Status",
        "bench_log": "Log",
        "bench_idle": "Ready.",
        "bench_net_error": "Network error.",
        "bench_corpus": "Corpus",
        "bench_corpus_none": "no corpus (demo)",
        "bench_corpus_prepare": "Choose in the Library",
        "bench_corpus_selected": "Corpus ready to run",
        "bench_corpus_select_hint": "Select a prepared corpus, or stay in "
        "demonstration mode.",
        "bench_competitors": "Competitors",
        "bench_add_competitor": "Add a competitor",
        "bench_queue_empty": "No competitor added yet.",
        "bench_queue_title": "Queue ready to run",
        "bench_queue_hint": "Each row summarizes one pipeline that will actually run.",
        "bench_remove": "Remove",
        "bench_mode": "Mode",
        "bench_mode_ocr": "OCR only",
        "bench_mode_text": "OCR → LLM (text)",
        "bench_mode_image": "OCR → LLM (image+text)",
        "bench_mode_vlm": "VLM (zero-shot)",
        "bench_mode_hybrid": "Hybrid (segmentation)",
        "bench_ocr_engine": "OCR engine",
        "bench_segmenter": "Segmenter",
        "bench_segmenter_hint": "Detects regions at the head of the pipeline; the "
        "remote one delegates to an HF endpoint (swap the model via the URL).",
        "bench_recognizer": "Per-block recognizer",
        "bench_recognizer_hint": "Engine applied to each cropped block: a real OCR, "
        "or a VLM transcribing the block image (zero-shot). Assembled text scored "
        "CER/WER like a flat pipeline.",
        "bench_seg_preview": "Region preview",
        "bench_seg_preview_btn": "Preview segmentation",
        "bench_seg_preview_hint": "Runs the segmenter on the chosen corpus and shows "
        "the detected regions (before launching the benchmark).",
        "bench_seg_preview_no_corpus": "Pick a corpus first.",
        "bench_llm": "LLM",
        "bench_vlm": "VLM",
        "bench_model": "Model",
        "bench_model_ph": "model (optional)",
        "bench_prompt": "Prompt",
        "bench_prompt_ph": "Empty = default prompt. For correction, include "
        "{ocr_text} where the OCR text should be inserted (else it is ignored).",
        "bench_prompt_curated_none": "— Curated prompt (by period) —",
        "bench_prompt_hint": "Pick a curated prompt OR write your own below "
        "(free text takes precedence).",
        "bench_ner": "Extract named entities (NER)",
        "bench_ner_model_ph": "spaCy model (default fr_core_news_sm)",
        "bench_ner_hint": "Adds a NER step at the end of the pipeline; scored "
        "(F1) if the corpus carries an entity ground truth.",
        "bench_alto": "Export ALTO (XML)",
        "bench_alto_hint": "Tesseract only: produces one ALTO XML per document "
        "(geometry + text), downloadable from the report — re-importable into "
        "eScriptorium or Transkribus.",
        "bench_normalization": "Normalization",
        "bench_norm_preview": "Normalization preview",
        "bench_norm_sample_ph": "Paste a text sample to see the effect…",
        "bench_norm_custom": "Custom profile (YAML) — takes precedence if filled",
        "bench_norm_config_ph": "caseless: true\nexclude_chars: \",.;:\"",
        "bench_norm_preview_btn": "Preview",
        "bench_char_exclude": "Characters to exclude",
        "bench_char_exclude_ph": "e.g. ,.;:!? — excluded on both sides",
        "bench_char_exclude_hint": "Filtered from GT AND hypothesis before scoring "
        "(those characters are no longer measured).",
        "bench_config_io": "Configuration",
        "bench_config_export": "Export (JSON)",
        "bench_config_import": "Import…",
        "bench_config_loaded": "Configuration loaded.",
        "bench_config_invalid": "Invalid configuration file.",
        "bench_config_hint": "Saves the form state (competitors + options) as "
        "JSON; reloadable later. No server persistence.",
        "bench_metric_profile": "Metric profile",
        "bench_metric_profile_hint": "Picks the report's ranking columns; does not "
        "drop collected data (sections unchanged).",
        "bench_options": "Options",
        "bench_execute_desc": "Launch the run, then open the final report or "
        "segmentation view.",
        "bench_norm_none": "(none)",
        "bench_error_422": "Incomplete or invalid configuration.",
        "bench_error_404": "Corpus not found.",
        "bench_error_409": "A required engine is unavailable.",
        "bench_error_403": "Action denied in this mode.",
        "bench_error_fallback": "Launch failed.",
        # Remote corpus import
        "imp_btn": "Import",
        "imp_manifest": "IIIF manifest URL",
        "imp_ark": "Gallica ARK (ark:/12148/…)",
        "imp_ocr": "Include reference OCR",
        "imp_base": "eScriptorium instance URL",
        "imp_token": "API token",
        "imp_doc": "Document PK",
        "imp_layer": "Transcription layer",
        "imp_limit": "Limit (pages)",
        "imp_name": "Name (optional)",
        "imp_repo": "HF repo (org/dataset-name)",
        "imp_revision": "Revision (SHA — recommended for pinning)",
        "imp_curated_hint": "Cinoc reference dataset published on HuggingFace: "
        "the manifest and ground truth are fetched; images stay as remote "
        "references (static IIIF served from HF, pinned to the revision), "
        "downloaded automatically at run time.",
        # Layout preview (launcher panel) + hybrid recognizer: useful remnants of
        # the old /segmentation page, reused by the benchmark composer.
        "seg_run_endpoint": "Endpoint (HF object-detection)",
        "seg_run_endpoint_ph": "https://…",
        "seg_run_token": "Token (optional)",
        "seg_run_running": "Segmenting…",
        "hyb_run_vlm": "VLM, zero-shot",
        "open_report_full": "Open the report",
        "sys_version": "Version",
        "sys_mode": "Mode",
        "sys_mode_value": "local · interactive",
        "sys_active_job": "Active job",
        "sys_idle": "idle",
        "sys_details": "System details",
        "sys_pipeline": "Pipeline",
        "sys_pipeline_ready": "engines ready",
        "sys_open": "System · details",
        "engines_eyebrow": "Showcase · engines",
        "engines_title": "Engines",
        "engines_desc": "Runtime availability of the built-in engines: binary, SDK, "
        "API key. A cloud engine is ready as soon as its SDK and key are present.",
        "stat_ready": "ready",
        "engines_col_engine": "Engine",
        "engines_col_status": "Status",
        "engines_col_detail": "Detail",
        "engine_available": "available",
        "engine_unavailable": "unavailable",
        "history_eyebrow": "Showcase · longitudinal",
        "history_title": "History",
        "history_desc": "Per-engine metric evolution across runs; regressions "
        "flagged between the two most recent runs.",
        "history_stat_runs": "records",
        "history_trends_title": "Trends",
        "history_trends_desc": "CER evolution per engine across runs "
        "(local scale). OLS slope per day; a change point is flagged only "
        "when the Pettitt test is significant (p ≤ 0.05).",
        "history_slope": "slope/day",
        "history_rupture": "change point at",
        "history_regressions_title": "Regressions",
        "history_regressions_desc": "Metrics that worsened between the two most "
        "recent runs (lower is better).",
        "history_no_regressions": "No regression detected.",
        "history_log_title": "Measurement log",
        "history_log_desc": "Every recorded aggregate, most recent first.",
        "history_empty": "No run recorded yet.",
        "history_col_run": "Run",
        "history_col_pipeline": "Engine",
        "history_col_view": "View",
        "history_col_metric": "Metric",
        "history_col_value": "Value",
        "history_col_change": "Change",
        "library_eyebrow": "VIEW · LIBRARY",
        "library_title": "Corpus library",
        "library_desc": "Local corpora and remote catalogues — all your material "
        "in one place.",
        "library_search_button": "Search",
        "library_demo_badge": "demo catalogue (offline)",
        "library_open": "open",
        "library_corpora_title": "My corpora",
        "library_local_title": "Local corpora",
        "library_corpora_desc": "Uploaded, imported from HTR-United / HuggingFace, "
        "or pointed from the filesystem.",
        "library_corpora_empty": "No local corpus. Import one.",
        "library_corpora_cta": "Prepare a corpus",
        "library_corpora_manage": "Stored corpora",
        "library_stat_local": "local",
        "library_stat_pages": "pages",
        "library_discover": "Discover",
        "library_discover_desc": "Explore one source at a time, then import only "
        "what matters.",
        "library_remote_title": "Remote sources",
        "library_catalogue": "catalogue",
        "library_manifest": "manifest",
        "library_source_htr": "HTR-United",
        "library_source_hf": "HuggingFace",
        "library_source_iiif": "IIIF",
        "library_source_gallica": "Gallica",
        "library_source_escriptorium": "eScriptorium",
        "library_source_curated": "Cinoc curated",
        "library_curated_yours": "Your curated datasets",
        "library_curated_yours_hint": "Cinoc curated datasets found on your "
        "HuggingFace account (cinoc-corpus tag) — import one in a click.",
        "library_curated_empty": "No curated dataset detected automatically. On a "
        "Space, your cinoc-corpus-tagged datasets appear here with no setup; locally, "
        "set an HF token or CINOC_HF_AUTHOR. Otherwise, import by id below.",
        "library_zip_meta": "ZIP · max 500 MB · pairs auto-detected",
        "library_ready": "ready for benchmark",
        "library_add_desc": "Upload a ZIP (drag-and-drop) or import from a "
        "remote source.",
        "library_drop_hint": "Drop a .zip here or click to select",
        "library_doc_preview": "documents",
        "library_gt_preview": "ground truths",
        "library_source_label": "source",
        "library_language_label": "language",
        "library_open_source": "Open source",
        "library_import_source": "Import from this source",
        "library_search_hint_htr": "Filter the HTR-United catalogue",
        "library_search_hint_hf": "Filter HuggingFace datasets",
        "library_use": "Use",
        "library_delete": "Delete",
        "library_empty": "No result.",
        "lang_label": "Language",
    },
}


def normalize_lang(raw: str | None) -> str:
    """Code de langue servi : ``raw`` s'il est connu, sinon le défaut FR."""
    return raw if raw in LANGUAGES else DEFAULT_LANG


def strings_for(lang: str) -> dict[str, str]:
    """Dictionnaire de chaînes pour ``lang`` (normalisé)."""
    return _STRINGS[normalize_lang(lang)]


__all__ = ["DEFAULT_LANG", "LANGUAGES", "normalize_lang", "strings_for"]
