# ANALYSE_COUCHE_6.md — `app` (Picarones → Cinoc)

> **Type** : session d'ANALYSE (guide de portage durable). **Aucun code Cinoc écrit.**
> **Couche 6 = `app`** (orchestration applicative) dans
> `domain(1) ← formats(2) ← evaluation(3) ← pipeline(4) ← adapters(5) ← app(6) ← reports(7) ← interfaces(8)`.
> **Source figée** : `Picarones/picarones/app/` — **27 fichiers, 6 648 LOC**.
> **Méthode** : 4 sous-agents d'exploration en parallèle (un par cluster), synthèse + recoupement
> personnel des points décisifs dans le code (couplages inter-couches, sécurité, code mort, shim).
> **Deux natures de savoir** (CLAUDE.md §9) : **Partie 1** = analyse source (durable) ;
> **Partie 2** = réorg cible (périssable, « à confirmer à la tranche »). Verdicts **PROVISOIRES**.

---

## PARTIE 0 — Vérification anti-contradiction (obligatoire)

Aucune conclusion ne contredit `CLAUDE.md` ni une couche mergée (domain ✅, formats ✅ ; evaluation = plan). Au contraire, l'analyse **confirme** trois décisions déjà actées ailleurs :

| Décision actée (où) | Confirmé dans le code Picarones |
|---|---|
| `RunSpec`/`StepSpec` → `domain`, **séparés du loader YAML** (backlog domain ; couche 1 §9) | `run_spec.py` mêle effectivement type déclaratif + loader YAML + résolution dotted-path → split nécessaire |
| `_benchmark_*` : double format `BenchmarkResult↔RunResult` supprimé + calcul rapatrié en `evaluation/runner` (CLAUDE.md §8.1 ; couche 3 §6,§11,§12-4) | `_benchmark_converter` calcule (compute_metrics, hooks, aggregate) ; `_benchmark_ner` calcule du NER ; les deux vivent à tort en `app/` |
| Persistance / store → `adapters/storage` (couche 3 §8) | `benchmark_service.persist()` écrit du JSONL ; `job_runner` parle à `adapters.storage.JobStore` |
| Registre + factory + **découverte entry-points en `app`** (CLAUDE.md §3) | `registry_service.bootstrap_default_registries()` + `resolve_adapter_class()` + `_resolve_entity_extractor()` = les **germes** (mais enregistrement codé en dur, **pas** d'entry-points) |

**Nuance importante à ne pas violer** (CLAUDE.md §3) : le **seul** point d'extension tiers = les **briques de pipeline**. Métriques, projecteurs, importeurs restent **internes**. Or `registry_service` mélange aujourd'hui registre de **métriques** (interne) et résolution d'**adapters** (extensible) — à scinder en cible.

---

# PARTIE 1 — ANALYSE DE LA SOURCE PICARONES (durable)

## 1.1 Inventaire par cluster (27 fichiers / 6 648 LOC)

| Cluster | Fichiers | LOC | Rôle global vérifié |
|---|---|---|---|
| **A. Colonne vertébrale + API** | `__init__.py`(27), `results.py`(24), `services/__init__.py`(96), `schemas/__init__.py`(49), `schemas/run_spec.py`(559) | **755** | Headers de paquet, façades de re-export, DTO YAML + loader |
| **B. Shim double-format `_benchmark_*`** | `_benchmark_adapter_resolver.py`(313), `_benchmark_conversions.py`(255), `_benchmark_converter.py`(236), `_benchmark_helpers.py`(266), `_benchmark_ner.py`(189), `_benchmark_persistence.py`(55), `benchmark_service.py`(407) | **1 721** | Conversion `RunResult`↔`BenchmarkResult` (legacy) + calcul de métriques mal placé + runner v2 |
| **C. Orchestration / jobs / reprise** | `run_orchestrator.py`(500), `run_orchestrator_execution.py`(310), `run_orchestrator_helpers/{__init__(55),builders(241),factories(119),legacy(308),loaders(43)}`, `_orchestrator_partial.py`(256), `job_runner.py`(267), `partial_store.py`(360) | **2 459** | `RunOrchestrator`, exécution asynchrone, reprise partielle (fingerprint SHA-256) |
| **D. Services transverses** | `path_security.py`(454), `corpus_service.py`(541), `registry_service.py`(327), `python_helpers.py`(277), `dependencies.py`(114) | **1 713** | Sécurité chemins (invariant §12), import ZIP corpus, bootstrap registres, bridge Python, capture deps |

**5 fichiers > 400 LOC** (budget Cinoc) : `run_spec`(559), `corpus_service`(541), `run_orchestrator`(500), `path_security`(454), `benchmark_service`(407).

## 1.2 Couplages inter-couches & consommateurs réels

**`app/` importe** (orientation **respectée** : que des couches internes ; **jamais** `reports/` ni `interfaces/`) :

| Vers | Symboles principaux | Cluster qui couple |
|---|---|---|
| `domain` | errors, artifacts (ArtifactType/Artifact), corpus (CorpusSpec), documents (DocumentRef/GroundTruthRef), pipeline_spec, evaluation_spec, run_manifest | tous |
| `evaluation` | **benchmark_result, metric_hooks, metric_result, metrics.{text,ner,over_normalization,search,alto_structural}, views, projectors, registry, corpus** | **B** (calcul/shim) + **D** (registry_service) |
| `pipeline` | runner.CorpusRunner, types.{PipelineResult,RunContext}, run_result.RunResult, llm_pipeline_builder | B, C |
| `formats` | alto.parser.parse_alto, text.normalization.get_builtin_profile | C (loaders), legacy |
| `adapters` | storage.JobStore, ocr.base.BaseOCRAdapter, corpus._fallback_log | B, C |

**Qui consomme `app/`** (grep hors `tests/`) — seulement **2 frontières** (sain) :

| Consommateur | Importe | Usage |
|---|---|---|
| `picarones/__init__.py` (API top-level) | `RunSpec`, `RunSpecLoadError`, `load_run_spec_from_yaml`, `RunOrchestrator`, `OrchestrationResult`, `prepare_preset_args`, `run_result_to_benchmark_result` | API publique + ⚠️ auto-déclenche `register_default_metrics()` à l'import (effet de bord) |
| `interfaces/cli/_workflows.py` | `RunOrchestrator`, `prepare_preset_args`, `run_result_to_benchmark_result` | `prepare → execute_preset → convertir en BenchmarkResult` |
| `interfaces/web/{benchmark_utils,_path_helpers,security_paths}.py` | `path_security.*`, `RunOrchestrator`, `prepare_preset_args`, `run_result_to_benchmark_result` | endpoints `/api/benchmark/start`, sandbox chemins |

> **Pattern consommateur clé** : CLI et web font tous deux
> `RunResult → run_result_to_benchmark_result() → BenchmarkResult` **parce que les renderers
> (couche 7) consomment `BenchmarkResult`, pas `RunResult`**. C'est la racine du double format.
> En Cinoc (format unique `RunResult`, reports le lit direct) **cette conversion disparaît entièrement**.

## 1.3 La dette centrale : double format de sortie + god-module éclaté

- Picarones produit **deux** formats : `RunResult` (couche 4, `pipeline/run_result.py`) **et** `BenchmarkResult` (couche 3, `evaluation/benchmark_result.py`). Le cluster B est presque entièrement le **pont** entre les deux.
- Historique vérifié : un god-module **`benchmark_runner.py` (~1 700 LOC)** a été éclaté en `_benchmark_*` lors d'une « Phase 6 audit code-quality ». **`benchmark_runner.py` n'existe plus** — toutes les docstrings qui le citent (≈ 15 fichiers) sont **périmées**. Idem `report_service.py` (cité, inexistant).
- Réconciliation du « ~1 570 LOC de shim » (CLAUDE.md §8.1) : shim strict ≈ `_benchmark_converter`(236) + `_benchmark_helpers`(266) + `_benchmark_persistence`(55) + ~½ `_benchmark_conversions`(255) + ~½ `_benchmark_adapter_resolver`(313) ≈ **950–1 000 LOC**, + le pont `run_orchestrator_helpers/legacy.py`(308) + le mort `partial_store.py`(360, legacy) → **~1 600 LOC de code legacy/shim/double-format** au total. ✅ cohérent.

## 1.4 Code mort & doc morte confirmés (recoupés dans le code)

| Élément | Preuve | Note |
|---|---|---|
| **`partial_store.py` : `_load_partial`, `_save_partial_line`, `_delete_partial`, `partial_path_for_engine`** | **0 consommateur hors-tests** ; servaient `run_benchmark_via_service` | ⚠️ ~½ du fichier est **mort** depuis la suppression de cette fonction |
| **`run_benchmark_via_service`** | **aucun `def`** dans `picarones/` ; ne subsistent que docstrings/commentaires (dont l'avis de dépréciation de `__init__.py`) | fonction **supprimée** mais « fantôme » partout en prose |
| Réfs à **`benchmark_runner.py`** (~15 fichiers) | `find` → inexistant | doc morte (god-module éclaté) |
| Réfs à **`_benchmark_execution.py`** (factories/builders) | inexistant | pattern copié-commenté, pas importé |
| Réf à **`report_service.py`** (`services/__init__` docstring) | inexistant | doc morte |
| `run_orchestrator._build_pipelines`/`_load_corpus` (staticmethods l.472-494) | wrappers qui ne délèguent qu'aux fonctions globales | conservés **pour un test** uniquement |

## 1.5 Bugs / fragilités notables (vérifiés)

| Fichier | Problème | Gravité |
|---|---|---|
| `run_orchestrator.py` | `progress_callback`/`cancel_event` **acceptés mais ignorés** sur le chemin `bench.run()` (consommés seulement si `partial_dir`) — le caller croit son callback branché | moyen (silencieux) |
| `run_orchestrator_execution.py` | appelle `BenchmarkService._evaluate_document_in_views()` (**privée**) pour recalculer les vues des docs repris | fragile (couplage privé) |
| `factories.py` | `counter_state` (lock+dict) partagé par closure ; OK seulement si chaque run a une factory fraîche | risque multithread |
| `partial_store.py` / `_orchestrator_partial.py` | fingerprint = path+size+mtime (pas de hash de contenu) → ne détecte pas une modif d'image à id constant | acceptable (documenté) |
| `run_spec.py` | 9 champs « Phase B » (`char_exclude`, `normalization_profile`, `partial_dir`, `entity_extractor`, `profile`, `output_json`, `timeout_seconds_per_doc`, `max_in_flight`, `poll_interval_seconds`) **validés mais à demi-consommés** (migration B1→B2.x inachevée) | dette de migration |
| `python_helpers.py` | `_dummy_pipeline_yaml()` = pipeline **bidon** juste pour satisfaire `RunSpec.pipelines (min_len=1)` en mode preset ; `adapter_kwargs` vide → `RunManifest` non reproductible sans le code Python | hack |
| `picarones/__init__.py` | `register_default_metrics()` **auto-déclenché à l'import** | anti-pattern (interdit Cinoc §7) |

## 1.6 Verdicts par fichier — **PROVISOIRES — à confirmer au build**

> Légende : **GARDER** (concept à reporter ~tel quel) · **MODIFIER** (concept gardé, forme à revoir/dégonfler/splitter) · **DÉPLACER** (change de couche) · **SUPPRIMER**.
> Le verdict décrit l'intention **pour le port Cinoc** ; les faits (rôle/conso) sont, eux, durables.

### Cluster A — colonne vertébrale (755 LOC)
| Fichier | LOC | Rôle réel vérifié | Verdict PROVISOIRE + raison |
|---|---|---|---|
| `__init__.py` | 27 | header paquet, `__all__` vide, sans effet de bord | **GARDER** — réécrire docstring, purger « 6 P0 du S1 » |
| `results.py` | 24 | **shim** re-export `RunResult/RunDocumentResult/ReportRenderer` ← `pipeline/run_result` | **SUPPRIMER** — en Cinoc `RunResult` vit en `evaluation/result.py`, reports le lit direct (zéro shim §5.1) |
| `services/__init__.py` | 96 | façade re-export (dont le converter `run_result_to_benchmark_result`) | **MODIFIER** — `__init__` mince §7 ; ne pas ré-exporter de shim |
| `schemas/__init__.py` | 49 | façade re-export `run_spec` | **MODIFIER/fusionner** avec le split ci-dessous |
| `schemas/run_spec.py` | 559 | `RunSpec`/`StepSpec`/`PipelineSpecYaml` (DTO YAML, 7 validators) + `load_run_spec_from_yaml` + `resolve_adapter_class` (importlib dotted-path) + `CANONICAL_VIEW_NAMES` | **DÉPLACER (split)** — type déclaratif `RunSpec`/`StepSpec` → **`domain`** (backlog confirmé) ; **loader YAML + `resolve_adapter_class`** → restent **`app`** ; **purger les 9 champs Phase B** (implémenter pour de vrai ou retirer) ; budget <400 |

### Cluster B — shim double-format (1 721 LOC)
| Fichier | LOC | Rôle réel vérifié | Verdict PROVISOIRE + raison |
|---|---|---|---|
| `benchmark_service.py` | 407 | **runner v2 propre** : orchestre `CorpusRunner`(4) + `view_executor`(3), assemble `RunResult`, persiste JSONL ; 0 import `_benchmark_*` | **MODIFIER (split)** — *pas « garder tel quel »* : assemblage `RunResult` + éval vues → **`evaluation/runner`** (3) ; persistance JSONL → **`adapters/storage`** (5) ; il ne reste en `app` qu'une coquille d'orchestration mince |
| `_benchmark_converter.py` | 236 | cœur du shim `RunResult→BenchmarkResult` ; **calcule** CER/WER + hooks + agrégation | **SUPPRIMER** — double format éliminé ; le calcul est déjà en `evaluation/`, juste appelé d'ici |
| `_benchmark_helpers.py` | 266 | extracteurs de texte + fingerprint pour le converter | **SUPPRIMER** — récupérer au plus 1-2 extracteurs `Artifact→texte` utiles → `pipeline`/`evaluation` |
| `_benchmark_persistence.py` | 55 | `asdict(BenchmarkResult)→JSON` | **SUPPRIMER** — pas de `BenchmarkResult` ; persistance `RunResult` → `adapters/storage` |
| `_benchmark_ner.py` | 189 | **calcule** NER (`compute_ner_metrics`) puis l'attache au `BenchmarkResult` | **DÉPLACER → `evaluation`** — le NER est une métrique (couche 3) |
| `_benchmark_conversions.py` | 255 | `Corpus`(3, chargé) → `CorpusSpec`(1, déclaratif) + `Document→DocumentRef` ; `_safe_doc_id` (normalisation) | **MODIFIER** — pont qui dépend du modèle corpus Cinoc (à confirmer) ; **garder la normalisation `doc_id`** (utile, réutilisée par NER + corpus_service) |
| `_benchmark_adapter_resolver.py` | 313 | `engine(BaseOCRAdapter / OCRLLMPipelineConfig) → PipelineSpec` + `build_adapter_resolver` (`name→StepExecutor`) | **MODIFIER** — le **resolver `name→executor` = germe du registre/factory** (garder, → registre `app`) ; la conversion `engine→spec` legacy disparaît (en Cinoc on déclare `PipelineSpec` direct) |

### Cluster C — orchestration / jobs / reprise (2 459 LOC)
| Fichier | LOC | Rôle réel vérifié | Verdict PROVISOIRE + raison |
|---|---|---|---|
| `run_orchestrator.py` | 500 | `RunOrchestrator.execute()` **et** `execute_preset()` → `OrchestrationResult` ; orchestre vraiment (corpus→registres→pipelines→service) | **MODIFIER** — concept d'orchestrateur `app` à **garder** ; dégonfler : fusionner `execute`/`execute_preset` (le 2ᵉ existe pour les engines en mémoire legacy), retirer la persistance `output_json` legacy + les callbacks « acceptés-ignorés » ; budget <400 |
| `run_orchestrator_execution.py` | 310 | `execute_with_partial()` (reprise par pipeline) ; recalcule les vues via méthode **privée** du service | **MODIFIER/différer** — feature réelle mais couplage fragile ; à reconcevoir proprement **à la tranche reprise** (≠ MVP) |
| `run_orchestrator_helpers/__init__.py` | 55 | re-export pour préserver l'API historique | **SUPPRIMER** — pas d'API historique à préserver (zéro shim) |
| `…/builders.py` | 241 | `_load_corpus`/`_build_pipelines`/`_build_views`/`_build_benchmark_service` | **MODIFIER** — helpers d'assemblage à **garder** mais replier dans l'orchestrateur/registre |
| `…/factories.py` | 119 | `_default_gt_factory`/`_default_inputs_factory`/`_make_context_factory` (closure progress, thread-safe) | **GARDER (concept)** — frontière « doc → artefacts » + `RunContext` par doc |
| `…/legacy.py` | 308 | pont `BenchmarkResult` : `_PipelineEngineProxy`, `_resolve_entity_extractor` (dotted-path→callable NER), `_persist_legacy_benchmark_json` | **SUPPRIMER** — `BenchmarkResult` disparu ; **garder le concept** `_resolve_entity_extractor` = résolution de module tiers (→ entry-points `app`) |
| `…/loaders.py` | 43 | `_filesystem_payload_loader` (disque→payload ALTO/texte) + `_kwargs_signature` | **GARDER (concept)** — chargement payload = I/O (`app` ou `adapters/storage`) |
| `_orchestrator_partial.py` | 256 | reprise **par pipeline** (fingerprint, load/append/delete/filter) ; système **vivant** | **MODIFIER** — devenir le **seul** mécanisme de reprise (différer à sa tranche) |
| `job_runner.py` | 267 | `JobRunner` thread daemon + `JobStore` ; annulation **best-effort non branchée** | **GARDER (concept)** pour `serve` — mais brancher une vraie annulation via `Deadline`/`RunControl` (couche 4, invariant §12) ; couple à `adapters/storage` |
| `partial_store.py` | 360 | reprise **par engine** (legacy) ; **~½ mort** ; seuls `compute_run_fingerprint`+`_partial_path` vivants | **SUPPRIMER** — garder seulement le **concept fingerprint**, fusionné dans le mécanisme partial unique |

### Cluster D — services transverses (1 713 LOC)
| Fichier | LOC | Rôle réel vérifié | Verdict PROVISOIRE + raison |
|---|---|---|---|
| `path_security.py` | 454 | **invariant §12** : `validated_path` (resolve+`is_relative_to`), `WorkspaceManager` (sandbox/session, anti-symlink post-mkdir), `safe_report_name`, `validated_prompt_filename` | **GARDER** — porter **fidèlement** (→ package `security/` §8.5) ; dédupliquer `prompt_filename`/`report_name`, moderniser (`is_relative_to` natif 3.11), splitter <400 |
| `corpus_service.py` | 541 | import ZIP sandboxé (anti zip-bomb/traversal/symlink) + appariement image/GT (`.gt.alto.xml`…) → `CorpusSpec` | **GARDER/DÉPLACER ?** — défenses à garder ; place à confirmer (`app` vs `adapters/corpus` qui porte déjà IIIF/Gallica/…) ; splitter <400 (extraction · catalogage · appariement) |
| `registry_service.py` | 327 | `bootstrap_default_registries()` (boucle **codée en dur** sur métriques+projecteurs), `RegistriesBundle` ; **pas** d'entry-points | **MODIFIER (scinder)** — registre **métriques/projecteurs** = interne (couche 3) ; registre **modules de pipeline** + **découverte entry-points** (`cinoc.modules`) + `register()` = couche `app` (CLAUDE.md §3) |
| `python_helpers.py` | 277 | `prepare_preset_args`/`PresetArgs` : bridge engines-en-mémoire→`RunSpec` ; `_dummy_pipeline_yaml` (hack) | **SUPPRIMER/reconcevoir** — existe pour les objets engine legacy ; en Cinoc on déclare `PipelineSpec` direct ; si une API Python est voulue, la rebâtir proprement |
| `dependencies.py` | 114 | `capture_dependencies_lock` + `capture_system_binaries_lock` → `RunManifest` (reproductibilité §12) ; pur, stateless | **GARDER** — invariant repro ; étendre la table binaires au-delà de Tesseract (starter pack) ; place `app` vs `adapters` à confirmer |

---

# PARTIE 2 — RÉORGANISATION CIBLE Cinoc (périssable — à confirmer à la tranche)

> ⚠️ Périssable. Le contact du code amont (evaluation/pipeline/adapters non encore mergés) corrigera ces formes.
> **On ne construit PAS la couche `app` de haut en bas** : elle **apparaît par tranches verticales**, au fur et à mesure que `interfaces` en a besoin.

## 2.1 Rôle d'`app` en Cinoc = **coquille mince** (les deux axes, CLAUDE.md §2)

`app` orchestre, **ne calcule jamais** (« l'app appelle, ne calcule plus »). Elle :
1. charge/valide une spec (`RunSpec`) et résout les modules par nom ;
2. appelle `pipeline`(4) puis `evaluation`(3) ; l'assemblage de `RunResult` est fait **par `evaluation`** ;
3. délègue la persistance à `adapters/storage`(5) et le rendu à `reports`(7, via callable injecté) ;
4. applique les invariants transverses : **sécurité chemins** (§12), **reproductibilité** (deps/binaires → `RunManifest`), **annulation/timeout** (`Deadline`/`RunControl`).

| Axe | Contenu `app` | Quand |
|---|---|---|
| **Enveloppe (plein-scope, maintenant)** | contrat d'orchestration ; **registre de modules + factory + découverte entry-points** (`cinoc.modules`) + `register()` ; `RunSpec` (en `domain`) + loader YAML (en `app`) ; sécurité chemins | conçu d'office |
| **Surface (incrémentale, élaguée)** | quels workflows CLI (`run/report/compare/demo/serve`), quels importeurs branchés, le job-runner web, la reprise partielle | une tranche à la fois |

## 2.2 Où va chaque concept Picarones (table de transfert)

| Concept Picarones (app) | Destination Cinoc | Note |
|---|---|---|
| `RunSpec`/`StepSpec` (déclaratif) | **`domain`** (couche 1) | frère de `PipelineSpec`/`EvaluationSpec` ; backlog confirmé |
| `load_run_spec_from_yaml` + `resolve_adapter_class` | **`app`** (loader/résolution = I/O + import dynamique) | « séparer du loader YAML » |
| `RunOrchestrator` (mince) + builders/factories | **`app`** | un seul `execute`, pas de `execute_preset` |
| assemblage `RunResult` + éval vues (`benchmark_service`) | **`evaluation/runner`** (couche 3) | RunResult = sortie d'évaluation |
| persistance JSONL / store longitudinal | **`adapters/storage`** (couche 5) | tidy store (couche 3 §8) |
| `_benchmark_ner` (calcul NER) | **`evaluation/metrics`** (couche 3) | NER = métrique |
| `path_security` | **`app/security/`** (package, §8.5) | invariant §12, port fidèle |
| `corpus_service` (import ZIP + appariement) | **`app`** ou **`adapters/corpus`** | à confirmer (adapters/corpus porte déjà les importeurs) |
| `dependencies` (capture deps/binaires) | **`app`** (ou `adapters`) | reproductibilité |
| `registry_service` (modules de pipeline) | **`app`** (+ entry-points) | seul point d'extension tiers |
| `job_runner` | **`app`** | pour `serve` ; annulation réelle via `RunControl` |
| `_orchestrator_partial` (reprise) | **`app`** (1 seul système) | à la tranche reprise |
| `results.py`, `legacy.py`, `_benchmark_{converter,helpers,persistence}`, `partial_store` (mort), `python_helpers` (preset), `…helpers/__init__` re-export | **SUPPRIMÉ** | shim/double-format/legacy/mort |

## 2.3 Esquisse d'arborescence cible (à confirmer)

```
cinoc/app/
├── __init__.py            mince, zéro effet de bord (pas de register_* auto)
├── orchestrator.py        RunOrchestrator unique → appelle pipeline + evaluation, assemble via eval
├── spec_loader.py         load_run_spec_from_yaml + resolve dotted-path/entry-point (RunSpec vit en domain)
├── modules/               registre + factory + découverte entry-points (cinoc.modules) + register()
├── security/              validated_path, WorkspaceManager, safe_* (invariant §12)
├── corpus_import.py       (?) import ZIP + appariement image/GT → CorpusSpec  [ou adapters/corpus]
├── reproducibility.py     (?) capture deps + binaires → RunManifest            [ou adapters]
└── jobs.py                JobRunner (serve) + annulation coopérative
```
*(Tous < 400 LOC ; `corpus_import`/`reproducibility` peut-être en `adapters` — décidé à la tranche.)*

## 2.4 Apparition par tranches (≠ couche complète)

| Tranche (cf. couche 3 §15) | Ce que `app` matérialise alors |
|---|---|
| **1. Squelette `demo`** (corpus pré-calculé → CER → RunResult → HTML → CLI) | orchestrateur **minimal** + registre de modules (1 module `precomputed`) + `RunSpec` minimal. Prouve que la coquille tient. |
| **2. Épaississement texte** (`run`, profils, `compare`) | loader YAML complet, sécurité chemins, capture repro, plus de modules au registre |
| **3. `serve`** | `JobRunner` + sandbox session + annulation |
| **4. reprise partielle** | mécanisme partial unique (fingerprint), si justifié par un consommateur réel |

---

# PARTIE 3 — RISQUES DE TRANSFERT & DETTES (comment détecter / désamorcer)

| # | Risque / dette | Détection | Désamorçage |
|---|---|---|---|
| **R1** | **Réintroduire le double format** en gardant un `BenchmarkResult` ou un converter « le temps de migrer » | test `no-legacy-imports` (interdire `benchmark_result`, `run_result_to_benchmark_result`) ; 1 seul type de sortie | tout consommateur lit `RunResult` direct ; **reports + web + compare migrés en bloc** (couche 3 §12-4 : ~30 conso) |
| **R2** | **Calcul qui reste en `app`** (NER, hooks, agrégation) | `test_layer_dependencies` : `app` n'importe **pas** `evaluation/metrics*` pour calculer ; revue « app appelle, ne calcule pas » | NER/hooks/agrégation → `evaluation/runner` |
| **R3** | **Mélanger registre interne (métriques) et registre extensible (modules)** → ouvrir une prise de trop | revue : entry-points `cinoc.modules` **uniquement** pour briques de pipeline (CLAUDE.md §3) | deux registres distincts ; métriques/projecteurs non pluggables |
| **R4** | **Sécurité chemins affaiblie au portage** (path-traversal/symlink/zip-bomb) | tests obligatoires : `..`, chemin absolu, symlink, zip-bomb, octet nul **doivent échouer** ; `validated_path` partout | porter `path_security` + `corpus_service._extract_safely` **fidèlement**, tester d'abord |
| **R5** | **Champs de spec à demi-câblés** (les 9 « Phase B ») recopiés tels quels | revue : tout champ `RunSpec` a un consommateur réel en CI (« pas de conso = supprimé ») | n'ajouter un champ que quand sa tranche le consomme |
| **R6** | **Reproductibilité perdue** (mode preset Picarones perdait `adapter_kwargs`) | golden `RunManifest` byte-stable ; test : run reproductible **depuis le manifest seul** | pas de chemin « engines en mémoire » ; toute brique déclare `version` (§3) |
| **R7** | **Annulation/timeout fantômes** (Picarones : callbacks acceptés-ignorés, cancel best-effort) | test : un `Deadline` dépassé **interrompt** ; annulation observable | brancher `Deadline`/`RunControl` (couche 4) dès `job_runner` |
| **R8** | **Doc/commentaires périmés recopiés** (`benchmark_runner.py`, `report_service.py`, `run_benchmark_via_service`, sprints S/A/Phase) | grep anti-narration ; `test_no_legacy_imports` | « garder le pourquoi, jeter la datation » (couche 2 MIG-3) |
| **R9** | **Code mort transféré** (½ `partial_store`, staticmethods test-only, `_dummy_pipeline_yaml`) | couverture CI ; « pas de conso = supprimé » | ne pas porter ; reprise = 1 seul système |
| **R10** | **Budgets explosés** (5 fichiers >400) | `test_file_budgets` strict | splitter dès l'écriture (orchestrateur / sécurité / corpus) |
| **R11** | **Effet de bord à l'import** (`register_default_metrics()` auto) | `test_no_side_effect_imports` | enregistrement **explicite, idempotent, testable** (§7) |

---

## Résumé pour la future session de CONSTRUCTION (3–5 points)

1. **`app` = coquille d'orchestration mince qui NE CALCULE PAS.** Elle appelle `pipeline`(4) puis `evaluation`(3) ; l'assemblage de `RunResult` se fait **dans `evaluation/runner`**, la persistance dans **`adapters/storage`**. Le seul « gros » runner sain de Picarones (`benchmark_service.py`) se **scinde** entre ces couches — ce n'est pas un « garder tel quel ».
2. **Tout le cluster `_benchmark_*` + `results.py` + `legacy.py` + ½ `partial_store` + `python_helpers`(preset) = SUPPRIMÉ** : c'est le double format `BenchmarkResult↔RunResult` (+ un god-module éclaté, + une fonction `run_benchmark_via_service` déjà morte qui laisse du code orphelin). En Cinoc, `RunResult` est unique et **les reports le lisent direct** → la conversion n'existe plus. Le **NER** part en `evaluation` (c'est une métrique).
3. **Deux germes d'enveloppe à concevoir plein-scope, sans les remplir** : (a) `RunSpec`/`StepSpec` **en `domain`** + loader YAML/résolution **en `app`** (split « séparer du loader ») ; (b) **registre de modules de pipeline + factory + découverte entry-points** (`cinoc.modules`) — **uniquement** pour les briques de pipeline, jamais les métriques/importeurs.
4. **Invariants à porter fidèlement et à tester EN PREMIER** : sécurité chemins (`validated_path`/`WorkspaceManager`/anti zip-bomb-traversal-symlink, §12), reproductibilité (`dependencies` → `RunManifest`), annulation coopérative (`Deadline`/`RunControl` — Picarones ne la branche pas vraiment, à corriger).
5. **Ne pas bâtir `app` en bloc** : elle naît par tranches. Tranche 1 (`demo`) = orchestrateur minimal + registre (1 module `precomputed`) + `RunSpec` minimal — juste assez pour prouver que la coquille tient. Budgets <400, zéro shim, zéro effet de bord à l'import, zéro champ de spec sans consommateur.

## DoD vivante (couche 6) — **autorité de détail** ; le `MIGRATION_PLAN.md` indexe

> **T8 (D-066)** : l'orchestrateur collecte un `DocumentUsage` par (pipeline × document) réussi et le passe à `evaluate_run` → `RunResult.usage` trié (déterministe). Preuve : `tests/app/test_orchestrator.py::test_run_result_carries_sorted_usage`.

> **T14 (D-072)** : builders `kraken`/`mistral_ocr` + sondes `engine_statuses` (SDK/clé) + `_OCR_ENGINES` étendu — matrice CLI/web alignée. Preuves : `tests/app/test_module_registry.py` · `test_engines.py`.

> **T15 (D-073)** : `+ resume.py` (`ResumeStore` + `unit_key`) — cache d'exécution par empreinte, branché à l'orchestrateur (`resume_store=`) et à la CLI (`run --resume-dir`) ; évaluation toujours recalculée. Preuves : `tests/app/test_resume.py`.

> **P5e 1 (D-275)** : l'orchestrateur garde une `DocumentExecution` **par unité**, échecs compris (plus de `results[unit] = {}`) : exception d'unité → `DocumentExecution.failed(failure_reason(exc), message)`, image distante injoignable → motif `infrastructure` ; une `DocumentUsage` émise pour chaque unité ; message caviardé (`_redact` : valeurs secrètes d'`adapter_kwargs` → `<secret>`, workspace temporaire → `<workspace>` pour le déterminisme, 1 000 caractères au plus), y compris dans le `logger.warning` ; `failure_policy` recopiée au manifeste. Seules les unités réussies vont au cache de reprise. Preuves : `tests/app/test_unit_outcome.py`, `tests/app/test_remote_images.py::test_unreachable_remote_image_fails_unit_not_run`.

> **P5e 1b (D-276)** : l'orchestrateur passe `execution.by_step` au runner et aux puits d'artefacts ; les exports (`write_alto_files`, `write_layout_files`, JSONL HIPE, `JobRunner._persist_artifacts`) lisent le pool par `latest_by_type`. Cache de reprise **format 2** (`resume.CACHE_FORMAT`) : une entrée par étape (sorties + consommation), dans l'ordre d'exécution, fichiers nommés `<étape>.<type><suffixe>` (deux étapes de même type ne s'écrasent plus) ; `load`/`save` prennent et rendent une `DocumentExecution`. Un index du format 1 (pool + usage agrégé) est **invalidé**, pas converti — l'unité est ré-exécutée puis réécrite (la sortie écrasée d'une étape amont n'y est plus ; la reconstruire serait inventer). La clé d'unité ne change pas. Preuves : `tests/app/test_step_target.py::{test_resume_cache_keeps_every_step,test_resume_cache_of_the_previous_format_is_re_executed}`, `tests/app/test_manifeste_artefacts.py`.

> **P5e 2 + P5f 1 (D-277)** : le manifeste écrit dans `adapter_kwargs` les réglages **effectifs** d'un module (hook `inference_settings()`, duck-typé comme `system_binaries()`), défauts compris ; les builders `openai`/`anthropic`/`mistral`/`ollama` transmettent `temperature`, `top_p`, `seed`, `max_tokens` (+ `num_ctx` pour ollama) sans les interpréter. L'orchestrateur caviarde et borne le message d'une unité `truncated` comme celui d'un échec. Le cache de reprise garde l'issue (`outcome`, `message`) au format 2 : une unité tronquée n'est pas rejouée (elle se couperait et se paierait à l'identique) et se relit `truncated` ; une entrée sans ce champ est `ok`. Preuves : `tests/adapters/llm/test_inference_settings.py::test_the_manifest_carries_the_effective_settings_defaults_included`, `tests/app/test_resume.py::test_a_truncated_unit_is_reloaded_as_truncated`.

> **P5f 3 (D-278)** : le sidecar `NATIVE_JSON` traverse l'orchestrateur sans code neuf — `by_step` → puits d'artefacts (URI lisible avant le nettoyage du workspace) → cache de reprise format 2 (`<étape>.native_json.json`, rechargé avec son étape ; fichier disparu → unité ré-exécutée) — et n'entre pas dans le `RunResult` (aucune référence non plus : rien ne la lit). **Où il vit après le run** : dans `RunManifest.artifacts_dir`, c'est-à-dire le dossier de reprise (`--resume-dir`) ; sans lui, il disparaît avec le workspace comme toute sortie (le web, qui n'a pas de dossier de reprise, ne le garde donc pas). Preuves : `tests/app/test_native_replay.py` (critère de sortie : run cloud sur cassette, run 2 hors ligne depuis les seuls sidecars par les fonctions des adaptateurs → mêmes scores ; archive, puits, cache, absence de secret).

> **P5f 2 + 2b (D-279)** : `run_manifest.py` (extrait de l'orchestrateur, budget) — `module_identities` (une lecture par run, **avant** la première page : saisie sans secret + `effective_settings()`, `system_binaries()` sondés ici ou repris de l'archive hors ligne), `served_models` (lus dans la provenance, unités rechargées comprises), `build_manifest` (réglages, versions et binaires **de l'identité**, `dependencies_lock`, `unicode_version`) ; les secrets (`SECRET_KWARGS`) y vivent. `versioning.dependencies_lock()` : `cinoc` et ses `Requires-Dist` installés (base + extras d'exécution, sans `dev` ni `hipe-oracle`) — aucune liste tenue à la main. `resume.py` **format 3** : `unit_key(pipeline, identities, document)` = haché du format, de la forme du pipeline, des **empreintes d'étape** et de l'image — plus de `code_version` ; unités **en échec** archivées (issue, motif, message), ré-exécutées en reprise normale, restituées hors ligne (`load(failures=True)`) ; fichiers nommés **relativement** à leur unité (l'archive se déplace et se télécharge : chemins absolus = toutes les unités « absentes » ailleurs) ; `binaries.json` = binaires sous lesquels l'archive a été produite. Orchestrateur : `run(offline=True)` exige une archive, ne construit que l'identité, refuse une unité absente (`ArchiveIncompleteError`, qui nomme les unités et la cause possible). `JobRunner(archive_dir=…)` : une archive **par job** (`<data_dir>/archives/<job_id>`), pas un cache partagé (sorties `precomputed` périmées, visiteurs d'une instance publique). Preuves : `tests/app/test_archive_rescore.py` (critère de sortie + 12 cas), `tests/app/test_resume.py`.

> **P5f 2b, correctif (D-280)** : la clé d'unité hache aussi le **contenu des fichiers d'entrée** que chaque module déclare lire pour l'unité — `resume.declared_inputs(pipeline, modules, document)` lit le hook facultatif `unit_inputs(document)` (duck-typé, hors du `Module` Protocol, comme `system_binaries`/`effective_settings`) ; `unit_key(…, inputs=…, digests=…)` y ajoute, par étape, `[nom du fichier, SHA-256 | "absent" | "illisible"]` — le **nom**, pas le dossier (l'archive et son corpus se déplacent), haché une fois par run (`digests`). Une sortie pré-calculée corrigée sous la même image est ré-exécutée ; hors ligne, l'unité est absente de l'archive et `ArchiveIncompleteError` cite désormais « un fichier d'entrée lu par un module a changé, est apparu ou a disparu ». Format d'index inchangé (3) ; les clés, elles, changent toutes : une archive S9 n'est plus atteinte (non publiée). L'archive web reste **par job** : des deux raisons de D-279, la première (sorties `precomputed` périmées) tombe, la seconde (deux visiteurs d'une instance publique) suffit. Preuves : `tests/app/test_unit_inputs.py` (réécriture → CER 0,25 → 0,0 ; inchangé → servi, hors ligne compris ; disparition/apparition → refus hors ligne).

> **S10b (D-282)** : `app/portable_paths.py` — `orchestrator.run(paths_root=…)` écrit le `RunResult` **sans chemin absolu local** : `image_ref` relatif à la racine comme la spec l'écrit (hors racine → `None`), `artifacts_dir` relatif ou réduit à son nom, chemins cités par un message d'échec rendus relatifs (séparateurs `\`/`/`, redoublés par `repr` compris). `report_images` relit ces références contre `image_root`, **confinées** (`validated_path`) ; un absolu (JSON antérieur) passe tel quel. `loader.dump_corpus_spec` écrit identifiants et nom entre guillemets ; une GT introuvable dit contre quel dossier elle a été cherchée. Preuves : `tests/app/test_portable_paths.py` · `tests/app/test_jobs.py::test_web_result_carries_no_server_path` · `tests/app/test_loader.py`.

> **P5e 7 (D-285)** : `app/text_views.py` — vues texte par défaut des planificateurs (benchmark web `_views_for_corpus`, recettes `default_evaluation(pipeline, corpus)`, correction structurée) : `texte` sous le profil par défaut, plus `texte (lignes)` (`keep_line_breaks`, CER seul) quand une GT `RAW_TEXT` tient sur plusieurs lignes ; un profil **choisi** donne une seule vue. La vue du lanceur web et de la démo passe de `text` à `texte` (comme recettes et correction), `cinoc history --view` aussi ; la vue *référence* reçoit le défaut au lieu d'un `None` (qui serait devenu la comparaison brute). — *preuve : `tests/interfaces/web/test_views_for_corpus.py`*

> **P5e 8 (D-288)** : `app/history.records_from_run` écrit le profil de chaque vue (lu dans `manifest.view_specs`) ; une vue absente du manifeste n'est pas enregistrée (avertissement) plutôt que rangée sous un profil deviné. `run_planning` : profil `standard` → `unanchored_trigrams` (ex-`hallucination`) ; vue NER (lanceur et recettes) → `ner_f1` + `ner_f1_exact`. — *preuve : `test_history.py::test_records_carry_the_view_profile_and_keep_series_apart`, `…::test_view_missing_from_manifest_is_not_recorded_under_a_guess`, `test_history_recording.py` (la démo enregistre sous `flat_text`), `test_run_planning.py`*

> **P5e 9 (D-289)** : profil `standard` sans exploratoire ni `fca` : `cer`, `cmer`, `char_accuracy`, `word_accuracy`, `wer`, `mer`, `bow_*`, `searchability` (`unanchored_trigrams`, `air`, `fca` restent au registre, une spec les nomme) ; une liste archaïque configurée ajoute `air` **et** `hcpr`. `texte (lignes)` reste au CER seul. Preuve : `tests/app/test_run_planning.py::test_metric_profile_default_is_standard_and_byte_identical`, `test_archaic_metrics_are_opt_in`, `tests/interfaces/web/test_views_for_corpus.py::test_gt_with_lines_adds_the_lines_view`.

> **P5f 7 (D-292)** : `orchestrator.run` marque `DocumentUsage.resumed` pour une unité relue de l'archive (D10) et transmet `exc.billed` à `DocumentExecution.failed` ; `resume.py` archive cette consommation (`billed`, champ additif, format inchangé) et la relit hors ligne. `modules/registry.py` : `timeout` saisi transmis aux sept moteurs distants (`_timeout_saisi`, et `_INFERENCE_KEYS`). *Preuve : `tests/app/test_resumed_units.py`, `tests/adapters/test_remote_call_bounds.py::test_the_timeout_is_set_by_the_spec`.*

> **P5f 6 (D-293)** : `security.check_ollama_host` → **`check_model_host`**, liste `CINOC_OLLAMA_HOSTS` → **`CINOC_MODEL_HOSTS`** (renommage atomique, aucun alias) : une seule liste pour le `host` d'ollama et le `base_url` OpenAI-compatible ; messages sans l'URL refusée. `check_endpoint_settings(réglages, public_mode=)` — la règle des transports HTTP en couche `app` : mode public → aucune cible (`host`, `base_url`, `api_key_env`), `api_key_env` refusé par HTTP, `host`/`base_url` contre la liste. Le filtre d'adresses publiques de `adapters/corpus/_http` n'est pas réutilisé (un serveur auto-hébergé est une adresse privée). `modules/registry._build_openai` transmet `base_url`, `api_key_env`, `self_hosted` (le constructeur les ignorait). *Preuve : `tests/app/test_security.py`, `tests/app/test_self_hosted_run.py` (critère), `tests/app/test_archive_rescore.py`.*

> **S22a (D-294)** : `engines.instance_status(statut, réglages)` — disponibilité **par instance** : une instance `openai` à `base_url` sans `api_key_env` n'exige pas `OPENAI_API_KEY` ; tout autre moteur garde l'état du moteur.

> **S22b (D-294)** : `models.py` réécrit — `available_models` (en direct, raison si illisible), `ModelListing.offers` (alias, `:latest`), `check_spec_models(live=)` (`ModelChoiceError`), `missing_model_message` ; `_CANONICAL` et `engines.installed_*_models` supprimés ; registre `_required_model` (aucun défaut) ; `run_planning.Competitor.ocr_model` + refus d'un concurrent sans modèle (budget 760 → 775) ; `pricing.json` `default_models` → `token_kinds`.
>
> **S23 (D-295)** : `modules/params.py` (`check_settings` : inconnu nommé + nom proche, requis, type, choix, bornes ; `ModuleSettingsError`) ; `modules/registry.py` réécrit (694 → 281 lignes, sort de la table des budgets) : `_SOCLE` (`kind`, classe déclarante, builder), builders **directs** `Classe(**réglages)` vérifiés d'avance, `_llm` résout `prompt_name` (`prompts.resolve_prompt`, partagé avec `run_planning`), `declared_params(kind)`, `socle_params`, `check_spec_settings` (construit chaque brique d'une spec, refuse des réglages qu'aucune étape n'emploie) ; un module tiers est contrôlé sur sa classe une fois construit, pas du tout sans déclaration. `run_manifest` : exploitation hors identité hachée, secrets déclarés masqués (`SECRET_KWARGS` reste le filet des non-déclarés). `recipes` : rôles `zero_shot` et `text_and_image` (`Role.mode`), recettes `vlm_seul` et `ocr_puis_vlm` ; le libellé et le mode ne sont posés que sur une brique qui les déclare. `run_planning` : ne passe à un OCR que ce qu'il déclare (`lang` ni à Google, ni à Azure, ni à Mistral OCR).

> Tri-état : `[x]` fait **+ preuve** · `[ ]` à faire · `[~]` différé/réserve + raison.
> Maj dans le **même commit** que le code. **Statut : ✅ T2** — orchestrateur (+ **workspace** par run) + registre/factory + `RunSpec` + **loader YAML** + **sécurité chemins** verts. **+ T6 découverte entry-points** : `discover_plugins` (groupe `cinoc.modules`, builder tiers enregistré comme le socle ; **fail-closed mode public** ; câblé CLI + web). **Prouvé de bout en bout** : loader injecté + **vrai `EntryPoint`** (résolution dotted-path) + **paquet réellement pip-installé auto-découvert** (`importlib.metadata`, test `slow` isolé). — *preuves : `tests/app/test_plugin_discovery.py`, `tests/app/test_plugin_install.py` + plugins de réf. `tests/fixtures/sample_segmenter_plugin.py` & `…/sample_plugin_pkg/`*. **+ T7 `history.py`** : trait d'union `RunResult`→`HistoryStore` — `records_from_run` aplatit les agrégats par pipeline/vue en `HistoryRecord` (métriques `None` écartées), `record_run` persiste. La connaissance de la forme `RunResult` vit **ici** (couche 6), pas dans le store (couche 5 = persistance pure). — *preuves : `tests/app/test_history.py`*. **Câblage auto livré (S6, D-046)** : `JobRunner` prend un `history_store` optionnel et appelle `record_run` après chaque run terminé (best-effort, comme `publish`) → **différé D-042 levé** ; `create_app` instancie un `HistoryStore` sous `catalog_dir`. — *preuves : `tests/app/test_history_recording.py`*. Différé : reprise partielle, deps-lock (hors CI).

**Enveloppe :**
- [x] `app` = **coquille mince qui NE CALCULE PAS** (appelle pipeline puis `evaluate_run` ; l'assemblage métrique vit en `evaluation`). — *preuve : `test_app_imports_are_allowed` ; l'orchestrateur délègue, n'importe aucune `evaluation.metrics*`*
- [x] **Registre + factory** (`name→Module` via builder enregistré, convention `<kind>:<label>`) — socle en dur, **seul** point d'extension. — *preuve : `test_module_registry` (build `precomputed` ; kind inconnu ; kwargs incohérents)*
- [ ] Découverte **entry-points `cinoc.modules`** + `register()` tiers. — *T6*
- [x] `RunSpec` → `domain` (compose `PipelineSpec` **directement**, sans `StepSpec` — D-010) ; orchestrateur assemble `RunManifest` (`adapter_kwargs` capturés). — *preuve : `test_run_spec` + `test_orchestrator`*
- [x] **loader YAML** (`RunSpec.model_validate`, `extra="forbid"`) + **sécurité chemins** (`validated_path` : rejet `..`/absolu-hors-base/octet-nul/symlink, §12 ; **GT `must_exist=True`** → erreur typée au chargement, pas d'`OSError` opaque en run) — **pas** de `resolve_adapter_class` (le registre résout `name→Module`, D-010). — *preuve : `test_loader` (+ GT manquante rejetée) + `test_security`*
- [x] **Isolation des workspaces par pipeline** (sous-dossier dédié) : deux pipelines partageant un `adapter_name` **écrivain** (ex. `openai:gpt`) n'écrasent plus mutuellement leur sortie → zéro contamination inter-pipelines. — *preuve : `test_orchestrator::test_pipelines_sharing_a_writer_do_not_contaminate`* — **corrigé à l'audit T3.**
- [x] **`RunManifest.module_versions`** : version déclarée de chaque module exécuté capturée (R-2). — *preuve : `test_orchestrator::test_manifest_captures_module_versions`.* `[~]` deps/binaires lock (`dependencies_lock`/`system_binaries_lock`, dont version **binaire** tesseract) : capture live, **différée** (hors CI).

**Garde-fous :**
- [x] `no_side_effect_imports` (**pas de `register_default_*()` auto** ni singleton module-level ; `register_default_modules`/`metrics` explicites) · `file_budgets` · `layer_dependencies`. — *preuve : suite archi verte*

**Validation par tranche :** `MIGRATION_PLAN.md` §3 — orchestrateur minimal + registre 1 module + `RunSpec` minimal (T1) · sécurité chemins testée d'abord + repro (T2) · entry-points + plugin (T6).

- [~] **Supprimé** : tout `_benchmark_*` (double format) · `results.py`/`legacy.py` (shim) · ½ `partial_store` mort · `python_helpers` (preset). **Différé** : reprise partielle (1 seul mécanisme, à sa tranche).

---

*(Tous les verdicts ci-dessus sont **PROVISOIRES — à confirmer au build** ; le contact du code amont non encore mergé prévaut.)*
