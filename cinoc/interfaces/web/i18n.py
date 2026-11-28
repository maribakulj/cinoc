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
        "bench_desc": "Choisis des formes de pipeline (OCR, OCR→LLM, VLM, "
        "segmentation, correction d'ALTO) et compare-les sur un corpus, en un "
        "seul run. File vide : démonstration.",
        "bench_run": "Lancer le benchmark",
        "bench_launching": "Lancement…",
        "bench_status": "État",
        "bench_log": "Journal",
        "bench_idle": "Prêt.",
        "bench_net_error": "Erreur réseau.",
        # Arrêt d'un run (annulation coopérative) et ses états lisibles.
        "bench_stop": "Arrêter",
        "bench_stopping": "Arrêt demandé…",
        "bench_stop_late": "Déjà terminé",
        "bench_state_pending": "En attente",
        "bench_state_running": "En cours",
        "bench_state_done": "Terminé",
        "bench_state_failed": "Échoué",
        "bench_state_cancelled": "Arrêté",
        "bench_outcome_ok": "fait",
        "bench_outcome_truncated": "tronquée",
        "bench_outcome_partial": "partielle",
        "bench_outcome_failed": "échec",
        "bench_outcome_resumed": "relue de l'archive",
        "bench_cancelled_result": "Run arrêté à ta demande. Aucun rapport : un "
        "run interrompu n'en écrit pas de partiel, et les pages déjà lues ne "
        "sont pas gardées.",
        # Un secret retiré de la configuration exportée (D-299).
        "bench_secret_label": "à ressaisir (retiré de l'export)",
        "bench_secret_missing": "Un secret retiré de la configuration exportée "
        "est à ressaisir dans la file avant de lancer.",
        "bench_config_secrets": "Un ou plusieurs secrets sont à ressaisir "
        "dans la file.",
        # La porte « spec complète » (instance privée seulement, D-299).
        "bench_spec": "Spec complète (YAML)",
        "bench_spec_pick": "Déposer et lancer…",
        "bench_spec_hint": "Un RunSpec écrit à la main, comme pour « cinoc run "
        "spec.yaml » : tout le graphe, sur le corpus choisi plus haut (le corpus "
        "de la spec est ignoré). Lancé aussitôt, mêmes gardes que la file.",
        "bench_corpus": "Corpus",
        "bench_corpus_none": "aucun corpus (démo)",
        "bench_corpus_prepare": "Choisir dans la Bibliothèque",
        "bench_corpus_selected": "Corpus prêt à exécuter",
        "bench_corpus_select_hint": "Sélectionne un corpus préparé, ou reste "
        "en démonstration.",
        "bench_competitors": "Concurrents",
        "bench_queue_empty": "Aucune recette dans la file pour l'instant.",
        "bench_queue_title": "File prête à exécuter",
        "bench_queue_hint": "Chaque ligne résume un pipeline réellement lancé.",
        "bench_remove": "Retirer",
        "bench_recipe_pick": "Choisir une forme",
        "bench_recipe_add": "Ajouter à la file",
        "bench_recipe_fanout": "↳ une fois par bloc détecté",
        "bench_recipe_loading": "Chargement des recettes…",
        "bench_recipe_error": "Catalogue des recettes indisponible.",
        "bench_recipe_missing": "Réglage requis à remplir :",
        "bench_recipe_unrunnable": "Aucune brique disponible pour l'étape :",
        "bench_recipe_added": "Ajoutée à la file.",
        "bench_recipe_hint": "Une recette est une forme éprouvée, nommée par ce "
        "qu'elle cherche à savoir ; tu choisis ses briques et, au besoin, leurs "
        "réglages. Toutes les recettes de la file partent dans un seul run, "
        "notées sous les options ci-dessous.",
        "bench_recipe_settings": "Réglages",
        "bench_recipe_optional": "Ajouter :",
        "bench_recipe_default": "défaut :",
        "bench_recipe_models": "modèle(s) disponible(s) — clique pour choisir",
        "bench_recipe_models_none": "Liste des modèles indisponible.",
        "bench_recipe_no_corpus": "Une recette s'exécute sur un corpus : "
        "choisis-en un.",
        "bench_seg_preview": "Aperçu des régions",
        "bench_seg_preview_btn": "Prévisualiser la segmentation",
        "bench_seg_preview_hint": "Lance le segmenteur sur le corpus choisi et "
        "affiche les régions détectées (avant de lancer le benchmark).",
        "bench_seg_preview_no_corpus": "Choisis d'abord un corpus.",
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
        "bench_detailed": "Mode détaillé (toutes les analyses)",
        "bench_detailed_hint": "Calcule aussi les analyses : bilan de "
        "correction, décisions du correcteur, intervalles, taxonomie… Plus "
        "lent ; le mode rapide ne calcule que les métriques.",
        "bench_metric_profile": "Profil de métriques",
        "bench_metric_profile_hint": "Choisit les colonnes de classement du "
        "rapport ; n'allège pas la donnée collectée (sections inchangées).",
        "bench_config_io": "Configuration",
        "bench_config_export": "Exporter (JSON)",
        "bench_config_import": "Importer…",
        "bench_config_loaded": "Configuration chargée.",
        "bench_config_invalid": "Fichier de configuration invalide.",
        "bench_config_hint": "Sauvegarde l'état du formulaire (file de recettes "
        "+ options) en JSON ; rechargeable plus tard. Aucune persistance serveur. "
        "Un secret (jeton) n'y est jamais écrit : il est redemandé à l'import.",
        "bench_options": "Options",
        "bench_execute_desc": "Lance le run puis ouvre le rapport final ou la "
        "vue de segmentation.",
        "bench_norm_none": "(défaut : flat_text, blancs écrasés, "
        "+ vue « texte (lignes) »)",
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
        "seg_run_running": "Segmentation en cours…",
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
        "third_party_title": "Modules tiers",
        "third_party_desc": "Briques découvertes par entry-points "
        "(cinoc.modules), installées hors du dépôt. Un module qui ne se "
        "charge pas dit pourquoi.",
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
        "régressions signalées entre les deux derniers runs. Une série = un "
        "corpus, un profil de normalisation, un moteur et une vue : deux runs "
        "ne se comparent que sous les mêmes.",
        "history_stat_runs": "mesures",
        "history_trends_title": "Tendances",
        "history_trends_desc": "Évolution du CER par moteur au fil des runs "
        "(échelle locale). Pente par jour (moindres carrés) et rupture (test de "
        "Pettitt), chacune avec sa p : ces tests sont exploratoires — la p est "
        "un nombre publié tel quel, sans seuil ni décision, et la rupture est "
        "affichée dès que le test est calculable (au moins 3 runs, série non "
        "constante).",
        "history_slope": "pente/j",
        "history_exploratory": "exploratoire",
        "history_trend_untested": "aucun test à 2 runs",
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
        "history_col_corpus": "Corpus",
        "history_col_profile": "Profil",
        "history_raw_profile": "brut",
        "history_legacy": "Base d'historique au format antérieur : ses séries "
        "ne disent ni corpus ni profil de normalisation, elles ne sont pas "
        "affichées. Déplacez le fichier history.db pour en commencer une "
        "nouvelle.",
        "library_eyebrow": "Vitrine · bibliothèque",
        "library_title": "Bibliothèque de corpus",
        "library_desc": "Corpus locaux et catalogues distants — toute la matière "
        "en un seul endroit.",
        "library_search_button": "Rechercher",
        "library_demo_badge": "catalogue de démonstration (hors-ligne)",
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
        # {max_mb} : le plafond que le serveur applique (mode public ou non).
        "library_zip_meta": "ZIP · {max_mb} Mo au plus · paires auto-détectées",
        "library_zip_too_large": "Archive trop volumineuse : {max_mb} Mo au plus.",
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
        "bench_desc": "Pick pipeline shapes (OCR, OCR→LLM, VLM, segmentation, "
        "ALTO correction) and compare them on a corpus, in a single run. Empty "
        "queue: demonstration.",
        "bench_run": "Run the benchmark",
        "bench_launching": "Launching…",
        "bench_status": "Status",
        "bench_log": "Log",
        "bench_idle": "Ready.",
        "bench_net_error": "Network error.",
        "bench_stop": "Stop",
        "bench_stopping": "Stop requested…",
        "bench_stop_late": "Already finished",
        "bench_state_pending": "Pending",
        "bench_state_running": "Running",
        "bench_state_done": "Done",
        "bench_state_failed": "Failed",
        "bench_state_cancelled": "Stopped",
        "bench_outcome_ok": "done",
        "bench_outcome_truncated": "truncated",
        "bench_outcome_partial": "partial",
        "bench_outcome_failed": "failed",
        "bench_outcome_resumed": "read from the archive",
        "bench_cancelled_result": "Run stopped at your request. No report: an "
        "interrupted run writes no partial one, and pages already read are not "
        "kept.",
        "bench_secret_label": "re-enter (removed from the export)",
        "bench_secret_missing": "A secret removed from the exported configuration "
        "must be re-entered in the queue before launching.",
        "bench_config_secrets": "One or more secrets must be re-entered in the "
        "queue.",
        "bench_spec": "Full spec (YAML)",
        "bench_spec_pick": "Drop and run…",
        "bench_spec_hint": "A hand-written RunSpec, as for “cinoc run spec.yaml”: "
        "the whole graph, on the corpus chosen above (the spec's own corpus is "
        "ignored). Launched at once, under the queue's guards.",
        "bench_corpus": "Corpus",
        "bench_corpus_none": "no corpus (demo)",
        "bench_corpus_prepare": "Choose in the Library",
        "bench_corpus_selected": "Corpus ready to run",
        "bench_corpus_select_hint": "Select a prepared corpus, or stay in "
        "demonstration mode.",
        "bench_competitors": "Competitors",
        "bench_queue_empty": "No recipe in the queue yet.",
        "bench_queue_title": "Queue ready to run",
        "bench_queue_hint": "Each row summarizes one pipeline that will actually run.",
        "bench_remove": "Remove",
        "bench_recipe_pick": "Pick a shape",
        "bench_recipe_add": "Add to the queue",
        "bench_recipe_fanout": "↳ once per detected block",
        "bench_recipe_loading": "Loading recipes…",
        "bench_recipe_error": "Recipe catalogue unavailable.",
        "bench_recipe_missing": "Required setting to fill in:",
        "bench_recipe_unrunnable": "No brick available for the step:",
        "bench_recipe_added": "Added to the queue.",
        "bench_recipe_hint": "A recipe is a proven shape, named by what it asks; "
        "you pick its bricks and, if needed, their settings. Every recipe in the "
        "queue runs in a single run, scored under the options below.",
        "bench_recipe_settings": "Settings",
        "bench_recipe_optional": "Add:",
        "bench_recipe_default": "default:",
        "bench_recipe_models": "model(s) available — click to pick",
        "bench_recipe_models_none": "Model list unavailable.",
        "bench_recipe_no_corpus": "A recipe runs on a corpus: pick one.",
        "bench_seg_preview": "Region preview",
        "bench_seg_preview_btn": "Preview segmentation",
        "bench_seg_preview_hint": "Runs the segmenter on the chosen corpus and shows "
        "the detected regions (before launching the benchmark).",
        "bench_seg_preview_no_corpus": "Pick a corpus first.",
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
        "bench_config_hint": "Saves the form state (recipe queue + options) as "
        "JSON; reloadable later. No server persistence. A secret (token) is "
        "never written to it: it is asked again on import.",
        "bench_detailed": "Detailed mode (every analysis)",
        "bench_detailed_hint": "Also computes the analyses: correction "
        "balance, corrector decisions, intervals, taxonomy… Slower; the fast "
        "mode computes the metrics only.",
        "bench_metric_profile": "Metric profile",
        "bench_metric_profile_hint": "Picks the report's ranking columns; does not "
        "drop collected data (sections unchanged).",
        "bench_options": "Options",
        "bench_execute_desc": "Launch the run, then open the final report or "
        "segmentation view.",
        "bench_norm_none": "(default: flat_text, whitespace collapsed, "
        "+ “text (lines)” view)",
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
        "seg_run_running": "Segmenting…",
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
        "third_party_title": "Third-party modules",
        "third_party_desc": "Bricks discovered through entry-points "
        "(cinoc.modules), installed outside this repository. A module that "
        "fails to load says why.",
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
        "flagged between the two most recent runs. A series = one corpus, one "
        "normalisation profile, one engine and one view: two runs are only "
        "compared under the same ones.",
        "history_stat_runs": "records",
        "history_trends_title": "Trends",
        "history_trends_desc": "CER evolution per engine across runs "
        "(local scale). Slope per day (least squares) and change point "
        "(Pettitt test), each with its p: these tests are exploratory — the p "
        "is a number published as is, with no threshold and no decision, and "
        "the change point is shown as soon as the test can be computed (at "
        "least 3 runs, non-constant series).",
        "history_slope": "slope/day",
        "history_exploratory": "exploratory",
        "history_trend_untested": "no test with 2 runs",
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
        "history_col_corpus": "Corpus",
        "history_col_profile": "Profile",
        "history_raw_profile": "raw",
        "history_legacy": "History database in an earlier format: its series "
        "name neither corpus nor normalisation profile, so they are not "
        "shown. Move the history.db file aside to start a new one.",
        "library_eyebrow": "Showcase · library",
        "library_title": "Corpus library",
        "library_desc": "Local corpora and remote catalogues — all your material "
        "in one place.",
        "library_search_button": "Search",
        "library_demo_badge": "demo catalogue (offline)",
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
        "library_zip_meta": "ZIP · up to {max_mb} MB · pairs auto-detected",
        "library_zip_too_large": "Archive too large: {max_mb} MB at most.",
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
