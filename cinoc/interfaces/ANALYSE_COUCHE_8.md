# ANALYSE_COUCHE_8.md — `interfaces/` (Picarones → Cinoc)

> **Type** : session d'ANALYSE (guide de portage **durable**). **Aucun code Cinoc écrit.**
> **Couche** : 8 = `interfaces` (la plus externe) dans
> `domain(1) ← formats(2) ← evaluation(3) ← pipeline(4) ← adapters(5) ← app(6) ← reports(7) ← interfaces(8)`.
> **Source gelée** : `../Picarones/picarones/interfaces/` — **42 fichiers Python / 8 931 LOC**, + assets (**2 483 LOC JS**, **1 432 LOC CSS**, **1 201 LOC templates HTML/J2**) ≈ **5 116 LOC d'assets**.
> **Couches amont** : `domain`+`formats` mergées (code) ; `evaluation`(MIG-3), `pipeline`(ANA-4), `adapters`(ANA-5), `app`(ANA-6), `reports`(ANA-7) en analyses/plans.
> **Méthode** : 4 sous-agents d'exploration en parallèle (CLI · cœur web/state · sécurité · routers) **+ recoupement personnel des points décisifs dans le code** (surface CLI, accroche narrative, chaîne `RunResult→BenchmarkResult→ReportGenerator`, doublon job store, ré-import sécurité, pattern de création de l'app, mode public, couplage importeurs→adapters).
> **Partie 1 = durable** (source figée). **Partie 2 = périssable** (« à confirmer à la tranche »). Verdicts **PROVISOIRE — à confirmer au build**.

---

## PARTIE 0 — Vérification anti-contradiction (obligatoire)

Aucune conclusion ne contredit `CLAUDE.md` ni une couche mergée/planifiée. L'analyse **confirme dans le code** cinq décisions déjà actées :

| Décision actée (où) | Confirmé dans le code Picarones (preuve) |
|---|---|
| **Workflows CLI réduits à `run/report/compare/demo/serve`** (`CLAUDE.md` §8.4) | 14 commandes réelles : `metrics/engines/info/report/demo` (`cli/__init__.py:136-326`) + `run/diagnose/economics/edition/compare` (`_workflows.py:132-792`) + `robustness/import/history/serve`. `diagnose/economics/edition` = 3 profils figés délégant à `_run_workflow` (`_workflows.py:644/711/764`) — exactement les 3 nommés à supprimer. |
| **7 modules `security_*` → un package `security/`** (`CLAUDE.md` §8.5) | 6 modules web (`security.py`+`security_{paths,csp,public_mode,uploads,rate_limit}.py`, 955 LOC) + le foyer `app/services/path_security.py` (454, couche 6). `security.py` est déjà un **hub de ré-export** (« dégonflage god-module P1.2 », `security.py:39-46`). |
| **Double format supprimé : `RunResult→BenchmarkResult` disparaît** (`CLAUDE.md` §8.1 ; ANA-6 L62-65 ; ANA-7 §1.2) | CLI **et** web font `run_result_to_benchmark_result()` → `ReportGenerator` legacy : `benchmark_utils.py:546,558` ; `_workflows.py:86,599` ; `cli/__init__.py:311,403`. Conversion présente **uniquement** pour nourrir le générateur Jinja2 legacy. |
| **Moteur narratif SUPPRIMÉ** (`CLAUDE.md` §6) | `routers/synthesis.py:101 from picarones.reports.narrative import build_synthesis` (appelé `:103`), router monté `app.py:253`, section template `_view_benchmark.html:387` + `web-app.js:1204`. 1 router + 1 route + 1 encart UI à couper. |
| **DTO web = transport, couche 8** (backlog domain ; CLAUDE.md §6) | `web/models.py` = 9 DTO Pydantic de transport (`:246,301,…`). N'importe que `domain.pipeline_spec.PipelineMode` (`:75`). Place couche 8 confirmée. |

**Deux AFFINEMENTS (clarifications, PAS des contradictions)** :

1. **Job store + SSE** : ANA-6 (§1.6, §2.2) place le store en `adapters/storage` (couche 5) et note `job_runner→adapters.storage.JobStore`. **Le code montre que le web utilise en réalité `web/jobs.py`** (avec table `job_events` + reprise SSE `Last-Event-ID`), tandis que la réécriture `adapters/storage/job_store.py` **a abandonné le SSE** et n'est consommée que par `app/services/job_runner.py`, lui-même **jamais importé par le web** (mort de bout en bout). → Le store canonique Cinoc (en `adapters/storage`) **doit reprendre la capacité d'événements/SSE** que la réécriture actuelle a perdue. (Cohérent avec ANA-6, complète juste le contrat.)
2. **Package sécurité réparti par couche** : ANA-6 §2.2 place `path_security` en `app/security/` (partagé CLI/jobs/web). §8.5 demande « un package `security/` » pour le cluster web. Pas de conflit : **validation de chemin = `app/security` (couche 6, partagée)** ; **sécurité HTTP (CSRF/CSP/rate-limit/uploads/mode public) = un package `security/` en `interfaces` (couche 8)**, qui *importe* la validation de chemin. La validation de chemin n'existe **qu'une fois** dans la source (`app/services/path_security.py`), `security_paths.py:20-28` ne fait que la ré-exporter — donc pas de dédoublonnage à faire, juste un regroupement.

---

# PARTIE 1 — ANALYSE DE LA SOURCE PICARONES (durable)

## 1.1 Inventaire exact (42 py / 8 931 LOC + 5 116 LOC d'assets)

| Cluster | Fichiers | LOC | Rôle global vérifié |
|---|---:|---:|---|
| **A. CLI** (`cli/`) | 7 | **2 018** | Groupe Click + 14 commandes ; pont vers `app.services` (orchestration) et `reports.html` (rendu). Point d'entrée console. |
| **B. Cœur web** (`web/` racine) | 12 | **3 434** | App FastAPI singleton, état partagé, DTO, worker de benchmark threadé, job store SQLite, utilitaires corpus/engines/observabilité. |
| **C. Sécurité web** (`web/security*`) | 6 | **955** | CSRF, CSP, rate-limit, quotas upload, mode public, racines de chemins. |
| **D. Routers** (`web/routers/`) | 15 | **2 500** | 14 routers montés / **39 handlers de route** (~35 routes distinctes) = surface HTTP du produit. |
| **Headers** | 2 | 24 | `interfaces/__init__.py`(23, docstring) + `web/__init__.py`(1). |
| **Assets** | — | **5 116** | `web-app.js`(2 483, SPA de pilotage) · `picarones.css`(1 432) · 8 templates J2 (1 201, dont `_view_benchmark`(403)/`_view_import`(374)). |

**Fichiers > 400 LOC** (budget Cinoc, 5 sur 42) : `_workflows.py`(882), `benchmark_utils.py`(615), `jobs.py`(541), `models.py`(419), `cli/__init__.py`(475). Côté assets : `web-app.js`(2 483) et `picarones.css`(1 432) explosent tout budget.

## 1.2 Couplages inter-couches & consommateurs réels (grep hors `tests/`)

**`interfaces/` est une FEUILLE du graphe d'import** (couche 8) : **0 module interne ne l'importe**. Son unique consommateur fonctionnel est **`picarones/__main__.py:10`** (`from picarones.interfaces.cli import cli`) + l'entry-point console `pyproject.toml:141` (`picarones = picarones.interfaces.cli:cli`). Le serveur web est lancé par `cli/_serve.py:70` via `uvicorn.run("picarones.interfaces.web.app:app", …)` (chaîne d'import string, **pas** de factory).

**`interfaces/` importe** (orientation **respectée** : que des couches internes — toutes légales) :

| Vers | Symboles principaux | Cluster |
|---|---|---|
| `domain` | `pipeline_spec.PipelineMode`, `errors` | B (models) |
| `formats` | `text.normalization.NormalizationProfile` | A (`_normalization_arg`), D (`normalization`) |
| `evaluation` | `corpus.load_corpus_from_directory`, `metrics.{text,normalization,history,robustness}`, `synthetic` | A, B, D (`history`,`normalization`) |
| `pipeline` | `llm_pipeline_config.OCRLLMPipelineConfig` | B (benchmark_utils) |
| `adapters` | `ocr.factory.ocr_adapter_from_name`, `llm.*`, **`corpus.{iiif,gallica,escriptorium,htr_united,huggingface}`**, `corpus._http.validate_http_url` | A, B, D (importeurs) |
| `app` | **`services.{RunOrchestrator, prepare_preset_args, run_result_to_benchmark_result}`**, `services.path_security.*` | A (`_workflows`), B (benchmark_utils, _path_helpers), C (security_paths) |
| `reports` | **`html.generator.ReportGenerator`**, `html.comparison.{compare_benchmarks,…}`, **`narrative.build_synthesis`** | A, B, D (synthesis) |

> **Pattern consommateur clé (la dette à éliminer)** : le seul flux « lancer un run » (`benchmark_utils.run_benchmark_thread_v2` `:516-560` ; `_workflows._run_orchestrator_for_cli` `:25-92`) fait **`prepare_preset_args → execute_preset → run_result_to_benchmark_result → ReportGenerator(BenchmarkResult)`**. En Cinoc (format unique `RunResult`, reports le lit direct, ANA-7) **la conversion ET le générateur Jinja2 legacy disparaissent** : interfaces appellera `evaluation/runner` (→`RunResult`) puis le `ReportRenderer` (lit `RunResult`).

## 1.3 Les dettes centrales (vérifiées dans le code)

| # | Dette | Preuve |
|---|---|---|
| **D-α** | **Conversion double-format à la frontière** (cf. 1.2). CLI + web la portent tous deux. | `benchmark_utils.py:546,558` ; `_workflows.py:86,599` ; `cli/__init__.py:311,403` |
| **D-β** | **Deux frontends distincts à ne pas confondre** : (1) le **rapport généré** (couche 7, Jinja2 + 3 423 JS) ; (2) la **SPA de pilotage** (couche 8 : `web-app.js` 2 483 + `picarones.css` 1 432 + 8 templates) servie par `home.py:53 GET /`. La couche 8 = la SPA de pilotage (lancer/suivre/importer), pas le rapport. | `home.py:41-57` ; `static/web-app.js` ; `templates/base.html.j2` |
| **D-γ** | **Doublon de job store** : `web/jobs.py`(541, SQLite + SSE) **utilisé** vs `adapters/storage/job_store.py`(489, sans SSE) **mort côté web**. Deux SQLite *en plus* : `jobs.sqlite` (jobs) vs history DB (couche 3). | `state.py:27,138` (web→jobs.py) ; `adapters/storage/job_store.py:1-8` (« legacy exposé jusqu'au S46 ») ; `job_runner.py:55` seul consommateur de l'adapter |
| **D-δ** | **Effets de bord à l'import** : `app = FastAPI(...)` + 14 `include_router` exécutés à l'import (`app.py:139-261`) ; `JOB_STORE = get_default_store()` **ouvre/crée SQLite à l'import** (`state.py:138`) ; `RATE_LIMITER`/`JOBS_SEMAPHORE` instanciés à l'import (`:132,135`). Viole `no-side-effect-imports` (§7). | `app.py:139` ; `state.py:132-138` |
| **D-ε** | **Surface HTTP large** : 14 routers / 39 handlers, dont importeurs exotiques (iiif/gallica/escriptorium/htr-united/hf), narratif, longitudinal, endpoints orphelins front. | `app.py:248-261` ; carte §1.5-D |
| **D-ζ** | **DTO couplés par copie** : `models.py:390` recopie la regex `RunSpec._DOTTED_PATH_RE` au lieu de l'importer → drift. `NormalizationProfileId`(`:56`) = `Literal` de 11 profils **codés en dur** (doit lire le registre canonique). | `models.py:56,390` |

## 1.4 Constats transverses durables (vérifiés, file:line)

| # | Constat | Preuve |
|---|---|---|
| **A** | **Couplage de couche SAIN** : interfaces = feuille, n'importe que des couches internes ; imports lourds **paresseux** (dans le corps des fonctions) pour passer le test d'archi. | `cli/__init__.py:386-389` ; imports dans les handlers |
| **B** | **Importeurs réseau délégués à `adapters.corpus` (couche 5)** — routers iiif/gallica/escriptorium/importers appellent `IIIFImporter`/`GallicaClient`/`EScriptoriumClient`/`HTRUnited`/`HuggingFace` + `validate_http_url` (SSRF). **Aucun fetch réimplémenté** sauf `engines.py:8` (`urllib` direct → API providers, listing modèles). | `routers/iiif.py:81` ; `gallica.py:97` ; `escriptorium.py:69` ; `importers.py:30,111` ; `engines.py:117-120` |
| **C** | **Sécurité bien factorisée, zéro duplication de logique** — 1 protection = 1 fichier ; la validation de chemin n'existe qu'une fois (`app/services/path_security.py`), `security_paths.py:20-28` la ré-exporte. Plusieurs callers court-circuitent le ré-export et importent `app.services.path_security` en direct (`_path_helpers.py:36`, `benchmark_utils.py:368`). | `security.py:48-87` (hub) ; `security_paths.py:17-28` |
| **D** | **Mode public = barrière d'exécution de code tiers in-process** (§3) : bloque OCR/LLM cloud + **NER `entity_extractor` dynamique** (allowlist fail-closed tous modes), confine le FS. **Pas** un read-only total (upload reste permis). Le gadget réel : `_resolve_entity_extractor` (`app/.../legacy.py:106` import, `:292` appel). | `security_public_mode.py:31,78-111` ; `security_paths.py:45-46` |
| **E** | **Annulation §12 partielle** : le web passe `cancel_event` (`benchmark_utils.py:536`) + vérifie `job.status=="cancelled"` entre docs (`:415,485,554`), mais l'orchestrateur l'**ignore hors `partial_dir`** (ANA-6 §1.5 R7). Pas de `Deadline`/`RunControl` réel. | `benchmark_utils.py:536` ; `state.py:172` (`_cancel_event`) |
| **F** | **`except Exception` = 28 occurrences**, mais **aucun `: pass` nu** (tous `raise`/`HTTPException`/`logger.warning`). Seule survivance : `routers/normalization.py:109 except OSError: pass` (cleanup temp `# pragma: no cover`). `no-broad-except` (§7) les signalera tout de même. | grep ; `normalization.py:109` |
| **G** | **Sécurité HTTP réelle et testée** : CSRF double-submit+HMAC (`security.py:285-397`), CSP+headers durcis (`security_csp.py:88`), rate-limit maison in-memory (`security_rate_limit.py:47`, **pas slowapi**), quotas+Pillow streamés (`security_uploads.py`), confinement chemins partout. Fail-fast démarrage (`check_deployment_coherence`/`validate_csrf_config`). | cf. cluster C |
| **H** | **Fragilités sécurité notables** : CSP `'unsafe-inline'` script+style (~30 `onclick` inline, `security_csp.py:59-60`) ; rotation CSRF documentée mais non implémentée (`security.py:389`) ; secret CSRF runtime non partagé multi-worker ; rate-limit non distribué + fuite mémoire lente des IP inactives ; **asymétrie rate-limit** (iiif/gallica/escriptorium bornés, importers/engines NON). | `security_csp.py:59` ; `security.py:389` ; `security_rate_limit.py:51-70` |
| **I** | **Doc/réfs périmées massives** : « 11 routers » (`app.py:14,23`, `routers/__init__.py`) vs 14 réels ; `POST /api/benchmark/start` supprimé mais cité (`__init__.py:18`) ; `measurements.normalization` (paquet **supprimé**, `models.py:66`) ; `run_benchmark_thread`/`_JOBS`/`BaseOCREngine` (symboles disparus) ; 3 conseils utilisateur morts CLI (`--save-history`, `info --normalization-profiles`, sous-groupe `pipeline`) ; annotations `Sprint S/Phase` omniprésentes ; `_b3_final_options` docstring mensongère (`_workflows.py:407`). | `app.py:14` ; `models.py:66` ; `_history.py:126` ; `_normalization_arg.py:77` ; `_robustness.py:193-199` |

## 1.5 Verdicts par fichier — **PROVISOIRE — à confirmer au build**

> Légende : **G** garder (concept ~tel quel) · **M** modifier (concept gardé, forme revue/dégonflée/splittée) · **C** changer de couche · **S** supprimer · **I** incrémental (rebâti à la tranche qui le consomme, pas avant).
> Principe directeur : l'**enveloppe** (app factory, contrat de sortie, sécurité, contrat de commande) est plein-scope **maintenant** ; la **surface** (commandes/routes/SPA) grossit **par tranches**. La plupart des routers/commandes ne sont **pas portés** : ils sont **rebâtis incrémentalement** quand leur tranche arrive.

### Cluster A — CLI (2 018 LOC)
| Fichier | LOC | Rôle réel vérifié | Verdict PROVISOIRE + raison |
|---|---:|---|---|
| `cli/__init__.py` | 475 | groupe Click racine (`:128`) + commandes `metrics/engines/info/report/demo` + helpers (`_setup_logging`, `_engine_from_name`, catalogue moteurs) | **M** — garder le groupe racine + `report`/`demo` (cœur 5) ; `metrics/engines/info` = introspection **hors 5** → démarrer **non portées** (pas de conso = supprimé), réintroduire si besoin réel ; purger sprints, source de version unique (§7), split <400 |
| `cli/_workflows.py` | 882 | `run`(`:132`) + `diagnose/economics/edition`(profils figés) + `compare`(`:792`) + la **chaîne de conversion** (`_run_orchestrator_for_cli` `:25`) | **M+S (split)** — **garder `run`+`compare`** ; **SUPPRIMER `diagnose/economics/edition`** (§8.4) ; la conversion `→BenchmarkResult` **disparaît** (appeler `ReportRenderer(RunResult)`) ; tuer `_b3_final_options` (menteur) + dédup options ; split <400 |
| `cli/_serve.py` | 75 | commande `serve` → `uvicorn.run(".../app:app")` (`:70`) | **G (concept)** — garder `serve` ; **lancer via factory `create_app()`** (pas de singleton module-level) ; warning sur `--host 0.0.0.0` |
| `cli/_normalization_arg.py` | 96 | helper `resolve_normalization_profile` (id builtin OU YAML), conso par `run` | **G (concept)** — utile à `run` ; corriger le conseil mort (`info --normalization-profiles`) ; **lire le registre canonique** (couche 2/3), pas une liste figée |
| `cli/_imports.py` | 120 | groupe `import` + sous-commande `import iiif` | **I** — hors cœur 5 ; import corpus = surface → rebâti à la **tranche importeurs**, pas avant |
| `cli/_history.py` | 171 | commande `history` → `evaluation.metrics.history` | **I** — hors cœur 5 ; longitudinal → tranche dédiée (store tidy `adapters/storage`) |
| `cli/_robustness.py` | 199 | commande `robustness` (images dégradées) | **I/S** — hors cœur 5 ; commentaires fantômes (sous-groupe `pipeline` inexistant) **non portés** |

### Cluster B — cœur web (3 434 LOC)
| Fichier | LOC | Rôle réel vérifié | Verdict PROVISOIRE + raison |
|---|---:|---|---|
| `web/app.py` | 261 | singleton `FastAPI`(`:139`) + lifespan + 4 middlewares + 14 routers | **M** — **factory `create_app()`** (zéro effet de bord à l'import, §7) ; ne monter que les routers de la tranche courante ; **drop `synthesis`** ; <400 |
| `web/state.py` | 337 | singletons (`RATE_LIMITER`/`JOBS_SEMAPHORE`/**`JOB_STORE`**), dataclass `BenchmarkJob`, registre `JOBS`+lock | **M** — **pas de `JOB_STORE` au niveau module** (§7) ; `BenchmarkJob`/annulation → brancher **`RunControl`/`Deadline`** (§12) ; le store descend en `adapters/storage` (couche 5) |
| `web/models.py` | 419 | 9 DTO Pydantic de transport HTTP | **G (concept « DTO web ») + M** — transport en couche 8 (backlog) ; **ne pas dupliquer `RunSpec`** (importer types/regex canoniques, ANA-6) ; DTO d'importeurs exotiques → à leur tranche ; corriger `measurements` ; profils via registre |
| `web/jobs.py` | 541 | job store SQLite **+ SSE/`job_events`** (`:80-92`) ; `get_default_store` (`:525`) | **C → `adapters/storage` (couche 5)** — store unique ; **conserver la capacité événements/SSE** que la réécriture actuelle a perdue (affinement §0) |
| `web/benchmark_utils.py` | 615 | `run_benchmark_thread_v2` = worker threadé + **site de conversion** (`:516-560`) | **M (éviscérer)** — garder le **worker** (jobs `serve`) ; supprimer `→BenchmarkResult` + `ReportGenerator` legacy ; appeler `evaluation/runner`(RunResult) + `ReportRenderer` ; brancher annulation réelle ; split <400 |
| `web/corpus_utils.py` | 362 | `flatten_zip_to_dir`(anti-bombe) + `analyze_corpus_dir` | **M/recoupe ANA-6** — défenses ZIP partagées avec `app.corpus_service` (couche 6, `app`/`adapters/corpus` à confirmer) ; web **appelle**, ne réimplémente pas ; <400 |
| `web/engine_utils.py` | 238 | statut moteurs + listing modèles (helpers) | **M** — statut moteurs = **introspection du registre** (couche app) ; listing modèles via réseau = surface optionnelle |
| `web/observability.py` | 212 | logging JSON + `/metrics` Prometheus | **M/I** — garder un logging structuré **mince** ; `/metrics` opt-in → tranche ops |
| `web/maintenance.py` | 207 | tâche de maintenance (nettoyage disque) | **I/S** — hors cœur ; rebâti si un consommateur réel l'exige |
| `web/_path_helpers.py` | 101 | wrappers `validated_user_output_dir/path` sur `app.path_security` | **M/absorber** — wrappers fins ; utiliser `app/security` directement |
| `web/_import_guards.py` | 84 | garde-fous import (mode public : caps résolution/pages) | **M** — replier dans le package sécurité (mode public) ; surface liée à la tranche importeurs |
| `web/config_utils.py` | 57 | schéma/migration de la config UI client | **I/S** — persistance config UI = surface ; pas de consommateur cœur |

### Cluster C — sécurité web (955 LOC) → **UN package `security/` en couche 8** (§8.5)
| Fichier | LOC | Rôle réel vérifié | Verdict PROVISOIRE + raison |
|---|---:|---|---|
| `web/security.py` | 397 | hub de ré-export + **CSRF** (double-submit+HMAC, `:285-397`) + fail-fast déploiement | **M (split)** — drop la **façade de ré-export** ; **CSRF → module dédié** du package ; implémenter la rotation (doc≠code `:389`) ; résoudre le secret multi-worker |
| `web/security_public_mode.py` | 122 | mode public : allowlists moteurs/LLM/**NER dynamique** | **G (ENVELOPPE)** — porter **fidèlement** ; c'est la barrière « code tiers in-process » (§3) → **liée au registre de modules** (couche app) |
| `web/security_csp.py` | 112 | middleware CSP + headers durcis | **G** — porter ; viser à **retirer `'unsafe-inline'`** (supprimer les `onclick` inline avec la refonte SPA) |
| `web/security_uploads.py` | 137 | quotas (unitaire/total) + validation Pillow streamée | **G** — porter ; surface liée à la tranche upload |
| `web/security_paths.py` | 101 | racines autorisées + **ré-export** validation chemin (depuis `app`) | **M** — garder le calcul des **racines** (HTTP) ; importer la **validation** depuis `app/security` directement (drop le shim de ré-export) |
| `web/security_rate_limit.py` | 86 | `RateLimiter` maison + concurrence | **G (concept)** — porter ; corriger la fuite mémoire IP inactives ; documenter la limite multi-worker (ou store partagé) |

### Cluster D — routers (2 500 LOC) → **rebâtis par tranches**
| Router | LOC | Routes (méthode/chemin) | Couche appelée | Verdict PROVISOIRE |
|---|---:|---|---|---|
| `benchmark.py` | 288 | `POST /api/benchmark/run` · `GET …/status` · `POST …/cancel` · `GET …/stream`(SSE) | app(6)→eval/pipeline ; reports(7) | **G (CŒUR)** — `run` HTTP ; SSE gardé ; brancher `RunControl` ; conversion éviscérée |
| `corpus.py` | 293 | browse/upload/uploads/image/delete | corpus_utils + security | **G (CŒUR `serve`)** — très défensif ; <400 |
| `home.py` | 57 | `GET /` (SPA shell) | jinja2 + state | **G (minimal)** — shell de pilotage **mince** (pas la lourde SPA) |
| `reports.py` | 114 | `GET /api/reports` · `GET /reports/{f}` | security (racines) | **G** — listing/service du HTML généré |
| `system.py` | 218 | health/status/csrf/metrics/lang | security + state | **M** — garder health/status/csrf ; **drop lang(×2)+metrics orphelins** (tranche ops) ; <400 |
| `engines.py` | 348 | `GET /api/engines` · `GET /api/models/{provider}` | engine_utils + **urllib direct** | **M** — `engines` = introspection registre ; **modèles via réseau = surface** ; rate-limit manquant ; <400 |
| `normalization.py` | 120 | profils + preview | eval(3)/formats(2) | **M** — garder `profiles` (registre) ; **drop `preview` orphelin** |
| `config.py` | 75 | save/load config UI | config_utils | **I/S** — surface confort UI |
| `synthesis.py` | 110 | `GET …/synthesis_preview` | **`reports.narrative`** | **S** — narratif supprimé (§6) : router+route+encart UI |
| `history.py` | 262 | runs/curve/engines/corpora/regressions | **`evaluation.metrics.history`(3)** | **I** — longitudinal → tranche dédiée (SQLite séparée) |
| `importers.py` | 139 | htr-united + huggingface (4 routes) | adapters.corpus(5) | **I** — tranche importeurs |
| `iiif.py` | 159 | preview + import | adapters.corpus.iiif(5) | **I** — tranche importeurs |
| `gallica.py` | 182 | search + import | adapters.corpus.gallica(5) | **I** — tranche importeurs |
| `escriptorium.py` | 115 | import | adapters.corpus.escriptorium(5) | **I** — tranche importeurs |
| `routers/__init__.py` | 20 | doc | — | **M** — mince, doc vraie |

### Assets (5 116 LOC)
| Asset | LOC | Verdict PROVISOIRE + raison |
|---|---:|---|
| `static/web-app.js` | 2 483 | **S majoritaire / rebâtir minimal** — SPA de pilotage (routing/i18n/charts client). Garder un **panneau de pilotage mince** pour `serve` ; pas de routeur SPA lourd. *(périssable)* |
| `static/picarones.css` | 1 432 | **M** — style mince (tableaux/formulaires) ; <400 par fichier si splitté |
| `templates/*.j2` (8) | 1 201 | **M/S** — garder un `base` + 1-2 partials du flux `run` ; les vues import/history/engines → à leur tranche |

---

# PARTIE 2 — RÉORGANISATION CIBLE Cinoc (périssable — « à confirmer à la tranche »)

> ⚠️ Périssable : le contact du code amont (evaluation/pipeline/adapters/app non encore implémentés) corrigera ces formes. **On ne construit PAS `interfaces` de haut en bas** : l'**enveloppe** (factory, contrat de commande, sécurité, contrat de sortie) naît au squelette ambulant ; les **commandes/routes** se remplissent **une par tranche**.

## 2.1 Rôle d'`interfaces` en Cinoc & les deux axes

`interfaces` est une **couche de transport mince** : parse arguments/requêtes → appelle un service `app` → retourne une réponse. **Aucun calcul, aucune orchestration, aucune conversion de format.** C'est la frontière la plus externe (in-process pour les modules tiers → la sécurité y est une exigence d'enveloppe).

| Axe | Contenu `interfaces` | Quand |
|---|---|---|
| **Enveloppe (plein-scope, maintenant)** | **factory `create_app()`** (zéro effet de bord) ; **contrat de commande CLI** (le groupe + les 5 verbes nommés) ; **package `security/` HTTP** (CSRF/CSP/rate-limit/uploads/**mode public**) importé sur l'enveloppe ; **DTO de transport** typés ; SSE + annulation coopérative branchées sur `RunControl` | conçu au squelette |
| **Surface (incrémentale, élaguée)** | quelles commandes effectives (`demo`→`run`→`compare`→`serve`/`report`) ; quels routers (benchmark/corpus/reports/home d'abord) ; quels importeurs ; la SPA de pilotage ; longitudinal/observabilité | une tranche à la fois |

**Whitelist CLI (§8.4)** : `run`, `report`, `compare`, `demo`, `serve`. Tout le reste (`diagnose/economics/edition/robustness/import/history/metrics/engines/info`) = **non porté d'office** ; réintroduit seulement si une tranche lui donne un consommateur réel.

## 2.2 Où va chaque concept Picarones (table de transfert)

| Concept Picarones (`interfaces`) | Destination Cinoc | Note |
|---|---|---|
| groupe CLI + `run/report/compare/demo/serve` | **`interfaces/cli`** | 5 verbes ; lazy-imports conservés (archi) |
| `diagnose/economics/edition` (profils figés) | **SUPPRIMÉ** | §8.4 |
| `_run_orchestrator_for_cli` + `run_benchmark_thread_v2` (chaîne conversion) | **`interfaces`** appelle **`app.orchestrator`** → **`evaluation/runner`** (RunResult) + **`ReportRenderer`** | la conversion `→BenchmarkResult` + `ReportGenerator` legacy **disparaissent** |
| `web/app.py` (singleton) | **`interfaces/web/app.py`** : **`create_app()`** | zéro effet de bord à l'import |
| `web/jobs.py` (SQLite **+ SSE**) | **`adapters/storage`** (couche 5) | store unique ; **garder les événements/SSE** ; web l'appelle |
| `web/state.BenchmarkJob` + annulation | **`interfaces/web`** | brancher **`RunControl`/`Deadline`** (couche 4, §12) |
| `web/models.py` (DTO transport) | **`interfaces/web`** | ne pas dupliquer `RunSpec` (réf. canonique) |
| `security_*` (CSRF/CSP/rate-limit/uploads/mode public) | **`interfaces/web/security/`** (UN package) | §8.5 |
| `security_paths` (validation chemin) | **`app/security/`** (couche 6, déjà décidé ANA-6) | interfaces l'**importe** |
| `corpus_utils` (ZIP/analyse) | **`app`** ou **`adapters/corpus`** | recoupe ANA-6 (à confirmer) |
| importeurs (iiif/gallica/escriptorium/htr/hf) | **adapters.corpus(5)** appelés par routers minces | à la **tranche importeurs** |
| `routers/synthesis` + narratif | **SUPPRIMÉ** | §6 |
| `routers/history` + `cli history` | **tranche longitudinale** (store tidy `adapters/storage`) | différé |
| SPA `web-app.js`/CSS/templates | **panneau de pilotage mince** | surface, périssable |
| docs/réfs périmées, sprints, conseils morts, doublons | **SUPPRIMÉ** | §7-8 |

## 2.3 Esquisse d'arborescence cible (à confirmer en codant)

```
cinoc/interfaces/
├── __init__.py            mince, docstring vraie, zéro effet de bord
├── cli/
│   ├── __init__.py        groupe Click racine (zéro import lourd à l'import)
│   ├── run.py             run (+ helper d'appel à app.orchestrator)
│   ├── report.py          report / compare (lit RunResult, ReportRenderer)
│   ├── demo.py            demo (squelette : corpus pré-calculé → RunResult → HTML)
│   └── serve.py           serve → uvicorn.run(create_app())   [factory, pas singleton]
└── web/
    ├── app.py             create_app() : monte routers de la tranche, middlewares sécurité
    ├── models.py          DTO de transport (réf. types canoniques, pas de copie)
    ├── jobs.py(?)         coquille SSE qui parle au JobStore d'adapters/storage
    ├── security/          __init__ · csrf.py · csp.py · rate_limit.py · uploads.py · public_mode.py
    └── routers/           benchmark.py · corpus.py · reports.py · home.py (squelette)
```
*(Tous < 400 LOC. Pas de `JOB_STORE` au niveau module, pas de façade de ré-export, pas de `synthesis`, pas d'importeurs avant leur tranche, SPA minimale.)*

## 2.4 Apparition par tranches (≠ couche complète)

| Tranche (cf. ANA-6 §2.4, MIG-3 §15) | Ce que `interfaces` matérialise alors |
|---|---|
| **1. Squelette `demo`** (corpus pré-calculé → 1 CER → `RunResult` → HTML) | `create_app()` minimal + **commande `demo`** + 1 route (`reports`/`home`) sur le **contrat de sortie définitif** (RunResult→ReportRenderer). Prouve que la coquille de transport tient, **sans conversion ni serveur complet**. |
| **2. Épaississement texte** (`run`, `compare`) | commandes `run`/`compare` ; loader spec ; sécurité chemins via `app/security` |
| **3. `serve`** | `create_app()` complet + routers `benchmark`(SSE)/`corpus` + **package `security/`** (CSRF/CSP/rate-limit/uploads/**mode public**) + **annulation `RunControl`** + JobStore (adapters/storage) + panneau de pilotage mince |
| **4. importeurs / longitudinal / observabilité** | routers iiif/gallica/escriptorium/importers (→adapters), `history`, `/metrics` — **chacun à sa tranche, avec un consommateur réel** |

## 2.5 Les 5 garde-fous appliqués

1. **Rupture nette, zéro shim** : 1 seul format (`RunResult`) ; **pas** de `run_result_to_benchmark_result`, **pas** de `ReportGenerator` Jinja2 legacy, **pas** de façade de ré-export sécurité, **pas** de `web/jobs.py` parallèle à `adapters/storage`.
2. **Budgets < 400** : `_workflows`(882)/`benchmark_utils`(615)/`jobs`(541)/`cli/__init__`(475)/`models`(419) **doivent** être splittés ; `web-app.js`/CSS refondus minces.
3. **Pas de consommateur = supprimé** : `diagnose/economics/edition`, `synthesis`, importeurs exotiques, endpoints orphelins (`lang`,`metrics`,`history/curve`,`normalization/preview`), conseils CLI morts → **non créés** tant qu'une tranche ne les réclame.
4. **Tests d'archi jour 1** : `layer-deps` (interfaces n'importe que des couches internes) ; **`no-side-effect-imports`** (pas de `app=FastAPI()` ni `JOB_STORE` au niveau module → **factory**) ; `file-budgets` ; `no-broad-except` (les 28 `except Exception` → `logger.warning` ciblés) ; **tests sécurité obligatoires** (CSRF/CSP/path-traversal/upload/mode public).
5. **Une commande/route = entière, en budget, en élaguant** : ajoutée avec sa tranche, testée, sans annotation de sprint ni doc périmée.

---

# PARTIE 3 — RISQUES DE TRANSFERT & DETTES (+ détection)

| # | Risque / dette | Détection | Désamorçage |
|---|---|---|---|
| **R1** | **Reporter la conversion `RunResult→BenchmarkResult`** « le temps de migrer » (CLI ou web) | `test_no_legacy_imports` (interdire `run_result_to_benchmark_result`, `benchmark_result`, `html.generator`) ; revue : tout handler lit `RunResult` | interfaces appelle `evaluation/runner` + `ReportRenderer` direct ; conversion **inexistante** |
| **R2** | **Effet de bord à l'import** (`app=FastAPI()` + 14 routers + `JOB_STORE=get_default_store()` au niveau module) | **`test_no_side_effect_imports`** (importer `interfaces.web.app` n'ouvre aucune SQLite, ne monte rien) | **`create_app()`** factory ; store injecté ; singletons créés dans la factory |
| **R3** | **Reconstruire la lourde SPA** (2 483 JS + routeur client + charts client) — « rapport-application » côté pilotage | revue : panneau mince ; pas de routeur SPA ; pas de charting client | shell HTML minimal ; le **rapport** (couche 7) reste un document factuel SVG-serveur (ANA-7 R5) |
| **R4** | **Surface CLI/HTTP recopiée en bloc** (14 commandes / 14 routers d'office) | « pas de conso = supprimé » ; whitelist 5 verbes (§8.4) ; chaque route a une tranche | 1 commande/route par tranche ; importeurs/longitudinal différés |
| **R5** | **Sécurité affaiblie au portage** (CSRF/CSP/path-traversal/upload/mode public) | tests obligatoires : token CSRF manquant → 403 ; `..`/symlink → rejet ; zip-bomb/octet-nul → échec ; moteur cloud en mode public → `PermissionError`→403 | porter le package `security/` **fidèlement, testé d'abord** ; corriger rotation CSRF + secret multi-worker |
| **R6** | **Exécution de code tiers non bornée** : `entity_extractor`/plugins in-process sans allowlist (le mode public est la barrière, §3) | revue : allowlist **fail-closed** ; le registre de modules (couche app) impose `version` + provenance | porter `assert_*_allowed` ; **mode public ⇒ in-process tiers verrouillé** ; pas de dotted-path arbitraire |
| **R7** | **Annulation/timeout fantômes** (Picarones passe `cancel_event` mais l'orchestrateur l'ignore hors `partial_dir`) | test : un `cancel` **interrompt** réellement un job en cours ; un `Deadline` dépassé stoppe | brancher **`RunControl`/`Deadline`** (couche 4) de bout en bout (job worker → runner) |
| **R8** | **Perdre le SSE en consolidant le job store** (la réécriture `adapters/storage` a abandonné `job_events`/`Last-Event-ID`) | golden SSE : reprise `Last-Event-ID` rejoue les events `seq>last` ; test reconnexion | le JobStore canonique (couche 5) **porte les événements** ; web = coquille SSE mince |
| **R9** | **DTO couplés par copie** (regex `RunSpec`, liste de profils figée) → drift | test : DTO référence les types/registres canoniques ; pas de `Literal` codé en dur de profils | importer `PipelineMode`/regex/registre normalisation depuis les couches sources |
| **R10** | **`except Exception` recopiés** (28 occurrences) | **`test_no_broad_except`** ; grep `except Exception`/`except: pass` | `logger.warning("[module] dégradé : %s", e)` ciblé (§7) ; supprimer `normalization.py:109 except OSError: pass` |
| **R11** | **Budgets explosés** (`_workflows`/`benchmark_utils`/`jobs`/`cli/__init__`/`models`) | `test_file_budgets` strict | splitter dès l'écriture (1 verbe/fichier, 1 protection/fichier) |
| **R12** | **Doc/réfs périmées recopiées** (« 11 routers », `start`, `measurements`, sprints, conseils morts) | grep anti-narration ; `test_no_legacy_imports` | « garder le pourquoi, jeter la datation » ; docstrings vraies au moment du port |
| **R13** | **Mauvais placement sécurité** : dupliquer la validation de chemin en `interfaces` au lieu de l'importer d'`app/security` | `test_layer_deps` + revue : 1 seule implémentation de `validated_path` | sécurité HTTP en couche 8 ; validation chemin en couche 6, **importée** (§0 affinement 2) |
| **R14** | **Asymétrie/oubli de rate-limit** sur routes réseau (importers/engines non bornés dans la source) | revue : toute route déclenchant du réseau sortant passe par le limiteur | rate-limit homogène ; réseau provider (engines) borné + limité |
| **R15** | **Réintroduire un singleton `app`** par confort uvicorn (`"...:app"`) | `test_no_side_effect_imports` ; `serve` appelle `create_app()` | uvicorn reçoit la factory (`--factory` / callable), jamais un module-level `app` |

---

## Résumé pour la future session de CONSTRUCTION (3-5 points)

1. **`interfaces` = transport mince, et une FEUILLE** : 0 consommateur interne, 1 seul point d'entrée (`__main__`/console-script). Elle **n'orchestre pas, ne calcule pas, ne convertit pas** : elle appelle `app`, qui appelle `evaluation/pipeline`. **La chaîne `prepare_preset_args → run_result_to_benchmark_result → ReportGenerator` (présente identiquement en CLI ET web) DISPARAÎT** : on appelle `evaluation/runner`(→`RunResult`) puis le `ReportRenderer` qui lit `RunResult` direct (cohérent ANA-6/ANA-7).
2. **L'ENVELOPPE à figer au squelette, plein-scope** : (a) **`create_app()` factory** — zéro effet de bord à l'import (aujourd'hui `app=FastAPI()` + 14 routers + `JOB_STORE=get_default_store()` ouvrent SQLite à l'import → interdit §7) ; (b) **contrat de commande** = les 5 verbes `run/report/compare/demo/serve` (§8.4), le reste non porté ; (c) **package `security/` HTTP** en couche 8 (CSRF/CSP/rate-limit/uploads/**mode public**) qui **importe** la validation de chemin d'`app/security` (couche 6, ANA-6) — pas de duplication ; (d) **annulation `RunControl`/`Deadline`** + **SSE** branchés réellement.
3. **Surface incrémentale, jamais d'avance** : tranche 1 (`demo`) = `create_app()` minimal + commande `demo` + route `reports`/`home` sur le contrat de sortie définitif. Puis `run`/`compare`, puis `serve` (benchmark SSE + corpus + sécurité complète), puis **importeurs/longitudinal à leur tranche** (iiif/gallica/escriptorium/htr/hf délèguent déjà proprement à `adapters.corpus` couche 5 — couplage sain à préserver).
4. **Suppressions nettes** : `synthesis.py` + narratif (§6) ; `diagnose/economics/edition` (§8.4) ; le doublon `web/jobs.py` (→ `adapters/storage` **en gardant le SSE/events** que la réécriture actuelle a perdu) ; la façade de ré-export `security.py` ; la lourde SPA de pilotage (panneau mince) ; endpoints orphelins + conseils CLI morts + docs périmées (« 11 routers », `start`, `measurements`).
5. **Invariants à porter fidèlement et tester EN PREMIER** : sécurité HTTP (CSRF/CSP/path-traversal/upload) **et** la barrière d'exécution **code tiers in-process** = le **mode public** (allowlist fail-closed moteurs/LLM/NER, §3) ; annulation/timeout coopératifs réels (§12) ; déterminisme du rendu (le HTML vient de `RunResult`, pas d'un état serveur). Budgets <400, zéro effet de bord à l'import, `no-broad-except`.

## DoD vivante (couche 8) — **autorité de détail** ; le `MIGRATION_PLAN.md` indexe

> **S7.a (D-074)** : CLI `run --csv` + sous-commande `history` (série/régressions) ; `GET /api/normalization/profiles` dynamique. Preuves : `tests/interfaces/test_cli_history.py` · `web/test_engines_api.py`.

> **P5e 1 (D-275)** : la démo ne vide plus `usage` — elle en neutralise les durées et **garde les issues** (une issue est une donnée du run, pas une mesure d'environnement). Preuve : `tests/interfaces/test_cli_demo.py` (golden octet-stable).

> **P5e 1b (D-276)** : `cinoc run --check` affiche « (étape notée : <id>) » après une vue ciblée ; une cible inconnue est refusée au chargement (`Erreur : …`, code 1, rien exécuté). Preuves : `tests/app/test_step_target.py::{test_check_shows_the_scored_step,test_cli_refuses_an_unknown_target_before_running}`.

> **P5f 3 (D-278)** : l'aide de `cinoc run --resume-dir` dit que ce dossier est aussi le dossier d'artefacts du run, où survivent les réponses natives des moteurs distants. Aucune route ni commande neuve (la relecture d'un sidecar n'a pas de consommateur produit avant S9/S19).

> **P5f 2b (D-279)** : `cinoc run --resume-dir <archive> --offline` — re-note sans aucun appel de moteur ; une unité absente fait échouer la commande (code 1, message qui nomme les unités) ; `--offline` sans `--resume-dir` est refusé. Parité : capacité **CLI seule, motivée** dans `test_web_cli_parity.py` (une archive est un dossier de qui re-note ; le web garde celle de chacun de ses runs — `create_app` passe `archive_dir=<data_dir>/archives` au `JobRunner` — mais n'en reçoit ni n'en sert). Preuves : `tests/app/test_archive_rescore.py::{test_cli_offline_rescores_and_fails_clearly_on_a_missing_unit,test_a_web_job_keeps_its_archive_in_the_data_dir}`.

> **S10b (D-282)** : `cinoc run` finit par un **bilan** des unités (« Bilan : n unité(s), aucune en échec. » sur stdout, ou « Bilan : n unité(s) en échec / N (motif : k) — le rapport les liste. » sur stderr) et sort en **3** si au moins une unité a échoué (rapport écrit), **0** sinon, **1** si le run n'a pas pu se faire — dit par `cinoc run --help`. `cinoc corpus import` dit que les chemins de `corpus.yaml` sont relatifs à **son** dossier. La CLI passe le dossier de la spec (`run`) ou des ALTO (`correct`) comme racine des chemins du `RunResult` et du rapport ; le web, le dossier des corpus déposés (`JobRunner` et routeur des rapports). Preuves : `tests/interfaces/test_cli_run.py::test_run_command_ends_with_a_unit_tally` · `tests/app/test_unit_outcome.py::test_json_written_by_the_cli_carries_support_and_reason` · `tests/interfaces/test_cli_corpus.py` · `tests/interfaces/web/test_served_report_images.py::test_a_relative_image_ref_is_read_against_the_uploads_root`.

> **P5e 11b (D-287)** : `/history` — chaque carte de tendance donne la p-value de la pente et dit « significative (p ≤ 0,05) » / « non significative », ou « aucun test à 2 runs » (EN : *significant* / *not significant* / *no test with 2 runs*) ; la description de section dit qu'une pente n'est une tendance que si elle est significative. — *preuve : `tests/interfaces/web/test_history_trends.py` (p = 0,186 non significative FR et EN, pente nette significative, 2 runs sans test — rouge prouvé)*

> **P5e 8 (D-288)** : `/history` et `cinoc history` — une série = (corpus, profil de normalisation, pipeline, vue) : une carte par série, qui nomme corpus et profil (« brut » / « raw » pour `null`) ; colonnes Corpus et Profil aux régressions et au journal ; une base d'avant la clé est refusée et la page le dit (FR/EN). La CLI imprime chaque série sous son en-tête `[corpus … | profil … | pipeline | vue]` et ses régressions avec leur corpus et profil, en ASCII (« -> », « delta » : « → » et « Δ » levaient `UnicodeEncodeError` sous une console cp1252). — *preuve : `test_cli_history.py::test_regressions_print_under_a_cp1252_console`, `test_history_trends.py::test_a_trend_never_spans_two_corpora_or_two_profiles`, `…::test_legacy_database_is_refused_and_said`, `test_cli_history.py::test_series_are_printed_apart_by_corpus_and_profile` (rouge prouvé)*

> **Reste de S10b (D-292)** : `_run_summary.unit_summary` (+ `EXIT_UNITS_FAILED`), sorti de `cli.py`, appelé par `cinoc run` **et** `cinoc correct` — une fonction, pas une copie ; `correct` sort en 3 avec le même bilan quand une unité échoue. *Preuve : `tests/interfaces/test_correction_command.py`.*

> **P5f 6 (D-293)** : `routers/runs._garder` appelle `check_endpoint_settings` pour chaque `adapter_kwargs` (403) : `base_url` hors `CINOC_MODEL_HOSTS`, `api_key_env`, toute cible en mode public. La route de correction garde `check_model_host`. Aucune route ni face CLI neuve (réglages de spec). *Preuve : `tests/interfaces/web/test_runs_spec.py` (6 nouveaux), `test_runs_correction.py`.*

> **S22a (D-294)** : `routers/runs._garder` juge la disponibilité **étape par étape** par `instance_status` (409 qui nomme la cause, 422 sur réglage illisible) — une instance auto-hébergée sans clé n'est plus refusée (`test_runs_spec::test_a_self_hosted_openai_instance_needs_no_openai_key`).

> **S22b (D-294)** : `/api/models/{provider}` sert `available_models` (quatre fournisseurs, aucune cible du client, `unavailable` ; mode public : aucun fournisseur interrogé) ; `benchmark.js` une seule voie pour tous, libellé vision/déprécié déclaré ; datalists serveur retirées ; champ « Modèle du moteur OCR » (`ocr_model`) ; `_garder` : `check_spec_models` (422) après les 403 ; CLI `list models [--host]`, `run --check` vérifie les modèles en direct (refus si absent, note si injoignable), `run` refuse une spec sans modèle.
>
> **S23 (D-295)** : `cinoc run --check` et `cinoc run` appellent `check_spec_settings` ; `routers/runs._garder` aussi (422 qui nomme le réglage) ; `cinoc list engines <brique>` décrit les réglages déclarés (type, défaut, bornes, choix, secret, hors empreinte) ; `cinoc list prompts` dit où poser `prompt_name`.
>
> **S24 (D-296)** : dette `recettes-web` **fermée** — `static/js/recipes.js` (onglet « Recette » du banc, cartes radio au clavier, une ligne par étape) lit `GET /api/recipes` (catalogue avec disponibilité, mode public compris) ; l'entrée rejoint la file de `benchmark.js` (`window.cinocQueue`), qui lance par `POST /api/runs/recipe` (`entries`, 1 à 16). Mélanger recette et concurrent composé est refusé par la page (tranche 6) ; l'export de config dit que les recettes n'y entrent pas. Table `FRONT` : les deux routes → `page:` ; reste `spec-web`, `annulation-web`.
>
> **S25 (D-297)** : `cinoc run CORPUS --recipe NOM [--brick …] [--set …]` (`_recipe_spec.spec_loader`, ~70 lignes, aucune logique : `load_corpus_spec` + `recipe_entries` + `plan_recipe_run`, puis le `cinoc run` habituel — `--check`, contrôle des réglages, archive) ; options de recette ou de notation sans `--recipe` refusées, nommées ; `--normalization`/`--char-exclude`/`--metric-profile` sur `run --recipe` et `correct`. Web : `ScoringFields` (mêmes champs pour `LaunchRequest`, `RecipeRequest`, `CorrectionRequest`) ; `benchmark.js` part toujours par `withScoring` (790 → 786) ; l'indice « les options ne s'appliquent pas aux recettes » retiré (FR/EN). — *preuve : `tests/interfaces/test_cli_recipe.py` (CLI et page → `cinoc compare` apparie tout, écart nul), `tests/interfaces/web/test_runs.py::test_every_launch_takes_the_same_scoring_options`, `test_benchmark_page.py::test_every_launch_carries_the_scoring_options`*
>
> **S26 (D-298)** : **la page n'a plus d'onglets** — le catalogue de recettes est le composeur (`recipes.js` 213 → 325 : pli « Réglages » généré des déclarations, étapes facultatives à cocher, modèles en `datalist` lus en direct, `describe` pour la file) ; `benchmark.js` 786 → 407 (sort de `ASSET_BUDGETS`), `benchmark.html` 387 → 221, 45 chaînes i18n mortes retirées, 5 ajoutées (FR/EN). **Une route de lancement** : `POST /api/runs` prend `entries` (vide : démonstration) ; `/api/runs/recipe` et `/api/runs/correction` **supprimées** ; `/api/runs/config` valide et rend la file entière (l'export porte les recettes). `routers/runs.py` 599 → 386 : une sonde (`statuses` = `brick_statuses`, celle du catalogue) au lieu de quatre (`segmenters`, `ner_available`, `correction_available`) ; `_garder` pour toute file (mode public sur `PUBLIC_BRICK_KINDS`). `home.py` ne rend plus de catalogue moteur. CLI : `cinoc run --recipe … --with ÉTAPE` ; `cinoc hybrid` (sans `--label`, `--lang` au défaut du moteur) et `cinoc correct` construisent leur recette par `plan_recipe_run`. Parité : `correct` → `web:POST /api/runs` ; `FRONT` sans les deux routes retirées. — *preuves : `tests/interfaces/web/test_runs.py`, `test_runs_correction.py`, `test_runs_recipe.py`, `test_benchmark_page.py`, `tests/guardrails/test_web_cli_parity.py`, `tests/interfaces/test_cli_recipe.py`, `test_cli_hybrid.py` ; navigateur (D-298)*

> **S27 (D-299)** : **un secret ne sort pas d'un export** — `POST /api/runs/config` rend la file par `exportable_entries` (secrets retirés et nommés, `withheld_secrets`) ; l'export de la page passe par elle (plus de blob client brut) ; l'import redemande chaque secret dans la file (`recipes.js` `secretFields`, champ masqué, `aria-invalid`), « Lancer » refuse tant qu'il manque. **Arrêter** : `#run-stop` (FR/EN, `data-stopping`/`data-late`) → `POST /api/runs/{id}/cancel` ; états du job traduits (`data-state-*`, `role=status`) ; message « arrêté, aucun rapport ». **Spec complète** : zone de dépôt `#spec-file` (instance privée seulement) → `POST /api/runs/spec`, refusée en 403 en mode public. `_garder` appelle `check_replay_sources` (422). `security/headers` : `font-src 'self' data:` sous `/reports/` seulement. Coquille 390 px (`minmax(0, 1fr)`). CLI : `cinoc corpus standardize` (`_corpus_command.add_standardize_parser`/`run_corpus_standardize`). Aperçu des régions déplacé dans `recipes.js` ; `benchmark.js` partage `postJson`. Parité : `DETTES` vide, `FRONT` : cancel et spec → `benchmark.js`, segmentation → `recipes.js`. — *preuves : `tests/interfaces/web/test_config_secrets.py`, `test_runs_cancel.py`, `test_runs_spec.py` (porte fermée en public, bombe d'alias, zone sur la page), `test_runs_recipe.py::test_a_replay_brick_without_its_files_is_refused_before_launch`, `test_web_security.py::test_the_served_report_may_load_its_embedded_fonts`, `tests/interfaces/test_cli_corpus_standardize.py`, `tests/guardrails/test_web_cli_parity.py` ; navigateur (D-299)*

> Tri-état : `[x]` fait **+ preuve** · `[ ]` à faire · `[~]` différé/réserve + raison.
> Maj dans le **même commit** que le code. **Statut : 🔨 T4f (TU2.a→d faites)** — vitrine + sécurité HTTP + **`serve`** + packaging Docker/Space (read-only) [T4e] ; **lanceur (TU2.a)** : `POST/GET/cancel /api/runs` → `JobRunner` (couche 6, thread + annulation) → `JobStore` (couche 5) → `RunResult` écrit, **CSRF** ; **Moteurs (TU2.b)** : `GET /api/engines` (dispo/indispo, sondes injectables) ; **upload corpus (TU2.c)** : `POST/GET /api/corpus` → `CorpusStore`+`extract_corpus_zip` (ingestion durcie : anti-traversal/anti-bombe/quotas/dédup/magic bytes) ; **sélection moteur + gardes HTTP (TU2.d)** : `POST /api/runs {engine, corpus_id}` → 422 inconnu · **403 cloud en mode public** · 422 LLM autonome · 404 corpus · 409 indispo · build `precomputed`(démo)/`tesseract`(sur corpus) ; **SSE (TU2.e)** : `GET /api/runs/{id}/events` + reprise `Last-Event-ID` (R-10 levé) ; **page « Banc d'essai » (TU2.f.1)** : `GET /benchmark` (base Jinja partagée `base.html` + `home.html`/`benchmark.html`) + **JS auto-hébergé** (`static/js/benchmark.js`, vanilla) qui lance la démo (`fetch` POST + CSRF) et suit la progression en **EventSource (SSE)** → lien rapport ; **CSP ouverte** à `script-src 'self'` + `connect-src 'self'` (1ᵉʳ consommateur navigateur). **page « Moteurs » (S2.2a)** : `GET /engines` — **100 % rendu serveur**, table d'état lue côté serveur (`app.engines`), nav vivante. **UI upload/sélection (S2.2b)** : `/benchmark` rend un `<select>` moteur **côté serveur** (options testables, indispo désactivées) + input fichier ; `benchmark.js` fait l'upload (`POST /api/corpus`, multipart+CSRF) puis lance `POST /api/runs {engine, corpus_id}` (messages d'erreur serveur 403/409/404/422 affichés). **S2 complet.** **S6.a importeurs distants** : `POST /api/corpus/import/{iiif,escriptorium,gallica}` (JSON DTO strict, **CSRF**) → helper `_materialize(builder)` → `CorpusStore.materialize` (couche 6, registre **agnostique de la source** — les 3 importeurs partagent le même seam) → corpus **immédiatement run-sélectionnable** (`GET /api/corpus/{id}`). **Gate mode public = 403** (fetch d'URL côté serveur = surface SSRF, comme les moteurs cloud) ; `SsrfError`/`HttpFetchError`/`CorpusImportError`/`GallicaArkError`→422. Token eScriptorium dans le corps (Space privé), jamais journalisé. — *preuves : `tests/interfaces/web/test_corpus_import_api.py` (par importeur : ok+sélectionnable · mode public 403 · erreur source 422 · corps invalide 422 ; **+** Gallica ARK malformé → 422 par le vrai chemin, sans réseau ; sans CSRF 403)*. **S6 Historique** : `HistoryStore` SQLite par app (sous `catalog_dir`), alimenté par le `JobRunner` après chaque run terminé (**best-effort** : un échec d'écriture ne fait pas échouer le run) ; `build_history_router` expose `GET /api/history/series` (chronologie pipeline/vue/métrique) + `GET /api/history/regressions` (dégradation 2 derniers runs) — **lecture seule** (pas de CSRF, pas de réseau → rien à gater). — *preuves : `tests/app/test_history_recording.py` (run démo réel → enregistré → requêtable ; historique optionnel), `tests/interfaces/web/test_history_api.py` (série chronologique · régression · `view` requis 422 · monté dans `create_app`)*. **page « Historique » (S6)** : `GET /history` — **100 % rendu serveur** (aucun JS), section Régressions (par (vue,métrique) enregistrée) + Journal des mesures (le plus récent d'abord, via `HistoryStore.all_records`), nav vivante, FR/EN ; `home.py` gagne `history_store`. — *preuves : `tests/interfaces/web/test_history_page.py` (journal trié récent→ancien · régression `0.10→0.15` affichée · 0 `<script>` + nav active · EN · vide via `create_app` · lien vivant depuis l'accueil)*. **page « Bibliothèque » (S6 découverte)** : `GET /library` — **100 % rendu serveur** (aucun JS), formulaire de recherche (`?q=`), section HTR-United (`fetch_catalogue` → réseau + repli démo `is_demo` badge) + section HuggingFace (`HuggingFaceCatalogue().search` réf + API best-effort), liens externes `rel=noopener`, FR/EN. *Découverte best-effort, jamais bloquante hors-ligne ; cache des catalogues = incrémental.* — *preuves : `tests/interfaces/web/test_library_page.py` (HTR+HF listés · badge démo · requête transmise à la recherche + réaffichée · 0 `<script>` + nav active · EN · lien vivant accueil)*. Reste S6 : form UI imports au design + segmentation-UI. Reste aussi : **S3** persistance · run tesseract réel (test `live`) · déploiement HF. ⚠️ JS navigateur **non testé en CI** (pas de navigateur) : vérifs serveur + `node --check` + API sous-jacentes testées ; rendu/interaction à confirmer au déploiement.

**Enveloppe :**
- [x] **Contrat de commande CLI** (`argparse`, D-007) — verbes **`demo`** + **`run`** (YAML → orchestrateur → rapport) câblés, console-script `cinoc`. — *preuve : `test_cli_demo` + `test_cli_run` (bout en bout)*
- [x] **`compare`** (2 RunResult JSON → deltas `B − A`) + **`run --json`** (export du RunResult). — *preuve : `test_cli_compare` + `test_results_io` (round-trip)*
- [x] **`serve`** (commande) — uvicorn reçoit la **factory** (`...app:create_app`, `factory=True`), jamais un app de module ; uvicorn = **import paresseux** (extra `[serve]` absent → message clair + code 1) ; **avertissement** si `--host` ≠ local (exposition réseau) ; `--reports-dir` → `CINOC_REPORTS_DIR`. — *preuve : `test_cli_serve` (factory ; warning `0.0.0.0` ; env ; extra manquant)*
- [ ] `report` (rendre un JSON sauvé en CLI) — différé (la vitrine web couvre le besoin de rendu).
- [x] **Vitrine web** (« montrer les rapports sans clés ») : `GET /api/reports` (liste triée) · `GET /reports/{name}` (rend le `RunResult` sauvé en HTML **à la demande** — format unique, rendu déterministe) · `GET /` (accueil **mince**, pas de SPA). **Sécurité chemins** via `validated_path` (couche 6) : traversal → 404 sans fuite. Routeurs = **fonctions builder**. — *preuve : `test_vitrine` (liste/rendu/404/traversal/accueil) + `no_side_effect_imports`*
- [x] **`create_app()` factory** — zéro effet de bord à l'import : `FastAPI()` construit **dans** la factory (jamais au niveau module), routers à venir = **fonctions builder** (`APIRouter()` interdit au module par le gate). Deps `fastapi`/`uvicorn` en **extra `[serve]`** (CLI reste léger). — *preuve : `tests/interfaces/web/test_app.py` (factory ≠ singleton ; `/health`→200) + `no_side_effect_imports` vert* `[~]` `JOB_STORE` module-level : N/A tant que le store n'existe pas (T4d).
- [x] **Package `security/`** (couche 8, **un** package ≠ 7 modules épars) — **CSP stricte** (`default-src 'none'` ; seul `style-src 'unsafe-inline'` car le rapport n'a que du CSS inline, zéro script — vérifié) + en-têtes durcis (nosniff/DENY/no-referrer/COOP) + **rate-limit** en mémoire par IP (purge des IP expirées → pas de fuite, dette H corrigée). Middlewares ASGI montés par la factory. — *preuve : `test_web_security` (CSP stricte ; en-têtes sur `/health` ET sur le rapport ; 429 au dépassement ; non-HTTP traversé ; config invalide rejetée)*
- [~] **CSRF / quotas upload / mode public** : différés à **T4f** (le lanceur BYO-key) — **0 consommateur** tant que la vitrine est en lecture seule (GET only), pas de mutation à protéger. SSE + annulation `RunControl`/`Deadline` = T4d.
- [x] **Packaging Space (Docker, lecture seule)** — `deploy/` : `Dockerfile` (python:3.11-slim, **non-root**, port **7860**, n'installe que cœur + `[serve]` — **aucun moteur**), `requirements.txt` (épinglé, vérifié couvrant cœur+serve par test anti-dérive), `README_SPACE.md` (`sdk: docker`), dossier `reports/` baké via `CINOC_REPORTS_DIR`. **Boot sans aucun secret/clé.** — *preuve : `test_packaging` (artefacts + cohérence deps + non-root + pas de moteur) ; smoke-test servi : `CINOC_REPORTS_DIR` → liste+rendu HTML+CSP.* `[~]` **build Docker non vérifié ici** (pas de démon dans le sandbox) ; runtime servi vérifié.
- [~] **Duplicable BYO-key** (clés par secrets/env, déblocage **fail-closed** du lanceur) : avec le lanceur (T4f). La vitrine, elle, est déjà **dupliquable telle quelle** (aucun secret).

**Garde-fous :**
- [x] `no_side_effect_imports` (la CLI construit tout dans `main`) · `layer_dependencies` (interfaces → couches internes) · `file_budgets`. — *preuve : `test_interfaces_imports_are_allowed` + suite archi*
- [ ] `no_broad_except` · **tests sécurité** (CSRF→403, `..`/symlink→rejet, zip-bomb→échec, cloud en mode public→403) · **hygiène des clés = invariant testé** (mémoire-seule, jamais loggée/persistée/rendue, même en mode dupliqué). — *T4*

**Validation inter-couches :** `MIGRATION_PLAN.md` §3 — `demo` bout-en-bout **sans serveur** (T1) · `serve` avec sécurité complète + un `cancel` qui interrompt réellement + reprise SSE `Last-Event-ID` (T4).

- [~] **Supprimé** : `synthesis`+narratif · `diagnose/economics/edition` · doublon `web/jobs.py` (→ `adapters/storage`, **SSE conservé**) · façade ré-export `security.py` · SPA lourde (→ panneau mince) · docs périmées (« 11 routers », `start`, `measurements`). **Convention (D-003/L7)** : le *flux de run* passe par `app`, pas `evaluation`/`reports` en direct.
- [x] **S28b (D-301)** : gabarits rendus sous **`StrictUndefined`** (une clé i18n mal orthographiée lève au lieu de rendre `''`) ; garde-fou `test_i18n_strict` : chaque page rend dans les deux langues, FR et EN ont les mêmes clés, toute clé lue existe, aucune n'est orpheline (`library_open` retirée) ; `cinoc compare --lang`.
- [x] **S29b (D-303)** : l'image de segmentation servie annonce le type de `formats/images.py` (`.webp`, `.jp2` compris ; binaire opaque hors table) ; **aucun test de page ne joint le réseau public** — `/library` interrogeait HTR-United et Hugging Face en direct dans `test_i18n_strict`, servis désormais hors ligne (relevé par `tests/conftest.py`). — *preuves : `tests/interfaces/web/test_i18n_strict.py`, `tests/guardrails/test_no_public_network.py`*
- [x] **S30 (D-304)** : `cinoc run --repeat N --resume-dir D` archive chaque répétition à part (`D/repetition-<k>`, l'exclusion levée) ; `cinoc corpus import zip` passe le plafond local (`LOCAL_MAX_ZIP_BYTES`) — transport mince, la règle vit en `app`. — *preuves : `tests/interfaces/test_cli_repeat_archive.py`, `tests/interfaces/test_cli_corpus.py`*
- [x] **S33 (D-305)** : un rapport **déposé** (`--reports-dir`) relit ses images contre son dossier de dépôt (`catalog.report_image_root` : graine reconnue à l'identité d'octets avec la copie servie), un run du serveur contre les corpus déposés ; chaque route qui lit une image (vignette, fac-similé, `bundle.zip`) passe par `_load` et `confine_image_refs`. Parcours d'une personne extérieure exécutés sur la **roue installée** par `tests/installed/` (job `install-bare` : base, puis `[serve,images,saknussemm]`). — *preuve : rouge sur la roue de `6316b80` (image 404), vert sur celle de S33*
- [x] **S34a (D-307)** : `cinoc serve` (`_serve_command.py`) résout le dossier de données une fois, le transmet par `CINOC_DATA_DIR` et l'affiche ; corpus déposés et exports ALTO sous ce dossier hors mode public (`create_app`), temporaires en mode public. — *preuve : `test_serve_says_where_its_data_lives`, `test_data_survives_restart`*
- [x] **S34a (D-307)** : `catalog.seed_reports` note ses graines (`.graines`, nom + empreinte) et retire au lancement suivant celles restées intactes avant de recopier le dépôt — un dossier de données qui dure ne fige ni un rapport relancé ni un rapport retiré. — *preuve : `test_a_deposited_report_is_refreshed_and_forgotten_across_restarts`*
- [x] **S34a (D-307)** : `cinoc correct --pipeline` (sous-parseur dans `_correction_command.py`) dit avant le run ce que mesurent les chiffres ; parcours 3 installé sans copie ni renommage. — *preuve : `tests/interfaces/test_correction_command.py`, `tests/installed/test_journeys.py::test_an_existing_alto_is_corrected`*
- [x] **S34b (D-308)** : `--lang fr|en` du rapport partagé par `demo`, `run` et `compare` (`_add_report_lang`) ; `cinoc compare` avertit sur stderr d'une paire composée autrement ; la fourchette de `--repeat` nomme sa vue et dit où elle vit ; `console_safe` (cp1252) partagé ; `corpus search` dit qu'il ne télécharge rien ; l'aide de `hybrid` lue sur les rôles de la recette ; page : surtitre traduit, journal `[k/N] pipeline · document — issue`, champs de réglages `id`/`name`/`label for`, case *Mode détaillé*. — *preuve : `test_cinoc_compare_warns_on_the_console`, `test_demo_speaks_english_on_request`, `test_each_range_names_its_view_and_where_it_lives`, `test_hybrid_help_lists_the_bricks_the_recipe_offers`, `tests/interfaces/web/test_page_polish.py`*
- [x] **S34a (D-307)** : `cinoc list engines <brique>` affiche consomme → produit (lu sur les rôles de recette), les réglages requis avec leur ligne `adapter_kwargs` ; un rôle de recette nomme ses briques, un nom inconnu reçoit le plus proche (`closest_hint`). La spec « noter un ALTO » du guide est exécutée (arbre et roue installée). — *preuve : `tests/app/test_module_params.py`, `tests/interfaces/test_guide_score_alto.py`, `test_a_bare_install_scores_an_existing_alto`*
- [x] **S34a (D-307)** : `cinoc run`, `correct`, `hybrid` impriment une ligne par unité terminée sur la sortie d'erreur (`_run_summary.print_progress`). — *preuve : `tests/interfaces/test_cli_progress.py`*
- [x] **S35 (D-310)** : `POST /api/corpus` lit le plafond du déploiement (`upload_zip_limit`, une fois à la construction du routeur) — un ZIP de plus de 25 Mo passe hors mode public, `413` au plafond nommé en mode public ; la route est synchrone (dézipper ne fige pas la boucle) et passe à la couche 6 le fichier temporaire où l'analyseur multipart a versé le dépôt, sans le relire en mémoire. `/library` dit le plafond effectif (`library_zip_meta`, il annonçait « 500 MB ») et `corpus.js` affiche, sur un `413`, `library_zip_too_large` dans la langue de la page. — *preuve : `tests/interfaces/web/test_corpus_api.py::test_a_local_server_accepts_an_archive_over_the_public_cap`, `::test_a_public_server_refuses_it_and_names_its_cap`, `tests/interfaces/web/test_library_page.py::test_library_shows_the_effective_archive_cap`*

---

*Tous les verdicts de la Partie 1.5 sont **PROVISOIRE — à confirmer au build** : le contact du code amont (evaluation/pipeline/adapters/app non encore implémentés) prévaut.*

---

## Mise à jour D-065 (réconciliation post-audit) — supersède les détails de page ci-dessus

Suite à l'audit de migration (et à une **dette de doc admise** : le code a d'abord
été poussé sans mettre à jour cette DoD), **décision produit** : la Bibliothèque
est le **hub de préparation des corpus**, pas un écran de découverte. Les détails
de page de la DoD ci-dessus sont donc **dépassés sur ces points** :

- **upload ZIP (glisser-déposer) + imports IIIF/Gallica/eScriptorium/HF** :
  déplacés de `/benchmark` vers **`/library`** (`static/js/corpus.js`) — **renverse
  D-059** et « UI upload/sélection sur `/benchmark` » (TU2.f.2 de l'ancienne spec UX du Space, retirée de l'arbre — D-309).
- **`/library` n'est plus « 0 JS »** : elle porte `corpus.js` + une section
  « Mes corpus » (`CorpusStore.list_corpora`) ; le **Banc d'essai sélectionne**
  un corpus existant (`<select>`), il ne téléverse plus.
- **Couche 8 = transport mince** : la construction de specs vit en
  `app/run_planning.py` (`plan_benchmark_run`/`plan_segmentation_run`), plus dans les
  routeurs (garde-fou `tests/guardrails/test_interfaces_thin.py`).
- **Stockage runtime** : historique + rapports de run via `app/data_dir`
  (inscriptible, ≠ dossier baké) ; pages dégradées (réseau/SQLite) — `tests/guardrails/`.

Détail complet : `MIGRATION_PLAN.md` **D-065**. Limites assumées : interaction
navigateur non testée en CI ; `/data` non gué sur `SPACE_ID` ; déploiement non
encore aligné — au backlog.

> **Refonte des contrats, tranche 1b (D-313)** : `/history` n'écrit plus « significative (p ≤ 0,05) » ni « non significative » : la p de la pente est publiée comme un nombre, étiquetée *exploratoire* ; la rupture de Pettitt s'affiche dès que le test est calculable, avec sa p et la même étiquette (`history_exploratory`, FR/EN), sans filtre sur la significativité. Le bilan `cinoc` compte les unités partielles. Preuves : `tests/interfaces/web/test_history_trends.py`.
