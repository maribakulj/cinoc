# Analyse — Couche 4 (`pipeline/`) : source Picarones → guide de portage Cinoc

> **Statut** : analyse de source figée. **Aucun code Cinoc écrit.** Les verdicts
> de portage sont marqués **« PROVISOIRE — à confirmer au build »**.
> **Méthode** : lecture intégrale du code par 4 sous-agents en parallèle +
> recoupement personnel des points décisifs (contrats `execute`, modèle
> d'annulation, composition runner/executor, absence de fan-out, consommateurs).
> **Source** : `Picarones/picarones/pipeline/` (15 fichiers, **3 454 LOC**), figée.
> **Cible** : `Cinoc/cinoc/pipeline/` (vide aujourd'hui : `__init__.py` seul).
> **Couches mergées non contredites** : `domain` (couche 1), `formats` (2),
> plan `evaluation` (3). Voir §2.5 pour les frontières héritées.

Le document a **deux parties** : **Partie 1 = analyse de la SOURCE (durable)** ;
**Partie 2 = idée de réorganisation cible (périssable, à confirmer à la tranche)**.
**Partie 3 = risques de transfert & dettes + détection.**

---

# PARTIE 1 — SOURCE Picarones (savoir durable)

## 1.1 Inventaire exact (15 fichiers, 3 454 LOC)

| # | Fichier | LOC | Famille |
|---|---------|----:|---------|
| 1 | `runner.py` | 630 | Moteur — orchestrateur multi-doc |
| 2 | `executor.py` | 574 | Moteur — exécuteur mono-doc |
| 3 | `planner.py` | 406 | Planification spec → plan |
| 4 | `llm_pipeline_builder.py` | 256 | Construction de specs OCR+LLM |
| 5 | `run_control.py` | 232 | Contrat — annulation runtime |
| 6 | `validation.py` | 218 | Validation statique de spec |
| 7 | `cache_helpers.py` | 189 | Cache via store (système réel) |
| 8 | `cache.py` | 154 | Cache in-memory (**mort**) |
| 9 | `types.py` | 152 | Contrat — `RunContext`/`StepResult`/`PipelineResult` |
| 10 | `llm_pipeline_config.py` | 136 | Container OCR+LLM |
| 11 | `__init__.py` | 132 | Façade de ré-export |
| 12 | `run_result.py` | 129 | Agrégats de run (`RunResult`) |
| 13 | `protocols.py` | 102 | Contrat — `StepExecutor` (module exécutable) |
| 14 | `cache_protocol.py` | 85 | Cache — ports (Protocols) |
| 15 | `yaml_io.py` | 59 | Round-trip YAML de `PipelineSpec` (**mort**) |

> ⚠️ Le `CLAUDE.md` de **Picarones** ne documente que 7 de ces 15 fichiers pour
> `pipeline/` (il omet le trio cache, `run_control`, `run_result`, `validation`,
> `yaml_io`) et affirme « plus aucun shim » — **factuellement faux** : shims
> survivants identifiés (§1.6). La doc source sous-décrit la couche : se fier au
> code, pas à elle.

## 1.2 Architecture réelle (le flux vivant, vérifié)

**Il n'y a pas deux moteurs concurrents.** `executor.py` = moteur ; `runner.py` =
orchestrateur qui l'**enveloppe par composition** (pas de redondance) :

```
app/services/builders.py:205-208   ← SEUL point de câblage
  PipelineExecutor(adapter_resolver, artifact_store=…)
  CorpusRunner(pipeline_executor, max_in_flight=…, timeout_seconds_per_doc=…)
        │
BenchmarkService.run (app)  →  CorpusRunner.run(spec, documents, …)   [N docs]
        │                         ├─ executor.plan(spec)            1×  (runner.py:246)
        │   ThreadPoolExecutor    └─ par doc, dans un thread :
        │   backpressure/timeout       executor.run_plan(plan, document, control)  (runner.py:510)
        │   cancel/agrégation               │
        │                                    └─ par step (séquentiel) :
        │                                         resolver(adapter_name) → StepExecutor
        │                                         adapter.execute(inputs, params, context, control)
        │                                         (cache: read/write via ArtifactCachePort)
```

- `runner.py:83` importe `PipelineExecutor` ; **jamais l'inverse**. Composition
  unidirectionnelle. Niveaux d'abstraction distincts → **zéro doublon**.
- **Aucun fan-out par région** : `grep region|bbox|polygon|fan.out picarones/pipeline/`
  → **vide**. Le seul fan-out est **par document** (un thread/doc dans `runner.py`).
  Le fan-out segmentation exigé par `CLAUDE.md` §3 **n'existe pas en source** :
  c'est du **net-new** (cf. §2.4 / Risque T2).

## 1.3 Surface de contrat consommée par l'extérieur (durable — façonne l'enveloppe)

Imports de `pipeline/*` depuis les couches externes (hors `tests/`). C'est ce que
Cinoc **doit** continuer d'offrir (sous une forme propre) :

| Consommateur (couche) | Symboles requis de `pipeline/` | Nature |
|---|---|---|
| `adapters/` 5 — OCR/LLM/VLM + `_httpx_helpers` | `StepExecutor` (implémenté), `RunControl`, `RunContext`, `RunCancelledError` | **Contrat de module** + annulation |
| `app/` 6 — `benchmark_service`, `run_orchestrator*`, `builders`, `factories`, `_benchmark_adapter_resolver`, `_orchestrator_partial` | `PipelineExecutor`, `CorpusRunner`, `PipelineSpec`/`PipelineStep` (re-exportés), `RunContext`, `PipelineResult`, `make_ocr_llm_pipeline_spec` | **Pilotage** du moteur |
| `reports/` 7 + `interfaces/web` 8 | `PipelineResult`, `RunResult` | **Lecture** des résultats |

> `adapters → pipeline` est un import **interne légal** (5 importe 4). Le contrat
> pivot est `StepExecutor.execute(inputs, params, context, control) → dict[ArtifactType, Artifact]`
> (`protocols.py:93-99`), implémenté **par duck-typing** (pas d'héritage) par
> `BaseOCRAdapter`/`BaseLLMAdapter`/`BaseVLMAdapter`.

## 1.4 Analyse document par document (rôle vérifié · deps · consommateurs · problèmes)

| Fichier | Rôle réel **vérifié dans le code** | Deps internes / externes | Consommateurs réels (hors `tests/`) | Bugs · mort · doublons |
|---|---|---|---|---|
| **`protocols.py`** | `StepExecutor` (`@runtime_checkable Protocol`) : `name`/`input_types`/`output_types` + `execute(inputs, params, context, control)→dict[ArtifactType,Artifact]` (`:93`). **C'est le contrat de module exécutable** (équivalent `BaseModule`). | `domain.artifacts`, `pipeline.run_control`, `pipeline.types` / `typing` | `executor.py:83,105`, resolver `app/_benchmark_adapter_resolver`, `run_orchestrator.py:367` | **Pas de `version`** (manque pour repro — cf. cache_helpers:99 `adapter_version=None`). `runtime_checkable` jamais utilisé en `isinstance` réel (la vérif passe par attributs). Docstring cite `raise_if_cancelled`/`is_cancelled` (méthodes mortes). |
| **`run_control.py`** | `RunControl` (mutable) : `cancel_event` (`threading.Event`) + `register_cancel_handle`/`trigger_cancel` (kill cross-thread, `Lock`) + `cancel_triggered`. `RunCancelledError(PicaronesError)` défini ici (`:194`). | `domain.errors` / `threading` | `RunControl` : **tous** les adapters, `executor`, `runner` ; `trigger_cancel` `runner.py:401,448` ; `register_cancel_handle` `_httpx_helpers.py:120` ; `RunCancelledError` `_httpx_helpers`, `ollama_adapter` | `_safely_invoke` `except Exception`+log (`:219`, conforme). **`raise_if_cancelled` + `is_cancelled` : 0 appel prod** (docstrings only). `CancelHandle` alias : ré-export quasi-mort. **`RunCancelledError` doit être en domain** (déjà fait couche 1, D9). |
| **`types.py`** | `RunContext` (frozen, **sérialisable**, porte `deadline: Deadline`) ; `StepResult` (`step_id`/`succeeded`/`duration_seconds`/`produced_artifacts:{type.value→id}`/`error`) ; `PipelineResult` (`step_results`/`succeeded`/`artifacts` plats). | `domain.artifacts`, `domain.deadline` / `pydantic` | `RunContext`/`PipelineResult` : adapters, `executor`, `runner`, `benchmark_service`, `_orchestrator_partial` (JSONL), reports | **`StepResult.token_confidences` N'EXISTE PAS** (prose fausse en `tesseract.py:144`). `step_result_by_id`/`artifacts_of_type` : **0 conso prod**. `artifacts_of_type(Any)` : typage laxiste. Aucun champ région. |
| **`executor.py`** | `PipelineExecutor` : `plan()` (sucre planner) + `run_plan(plan, document, …, control)` (canonique) + `_run_step` (résout inputs via **bindings explicites**, cache read/write, `adapter.execute`, valide outputs, filtre les types non déclarés). **Séquentiel, mono-doc, sans threading.** | `domain.{artifacts,documents,errors,pipeline_spec}`, `pipeline.{cache_helpers,cache_protocol,planner,protocols,run_control,types}` / `logging,time` | `runner.py:246,510` (**uniquement**) ; instancié `builders.py:205` | 2× `except Exception # noqa` → `StepResult` en échec + `logger.warning` (conforme). **`run(spec,…)` (sucre S7, `:199`) : code mort en prod.** Provenance **non câblée** (produit des ids, pas de `ProvenanceRecord`). **574 LOC > 400.** |
| **`runner.py`** | `CorpusRunner` : `ThreadPoolExecutor` + **backpressure** (`_occupancy < max_in_flight`) + **timeout depuis exécution réelle** (`started_at` posé par le worker) + **annulation** (queue→`fut.cancel`, in-flight→`control.trigger_cancel`) + **agrégation** (`DocumentOutcome`/`CorpusRunResult`). Ne ré-exécute **jamais** une étape. | `domain.*`, **`pipeline.executor`**, `pipeline.{run_control,types}` / `concurrent.futures,threading,time,pydantic` | `benchmark_service.py:55,161` ; instancié `builders.py:208` | État partagé **protégé par locks** (`started_at_lock`, `controls_lock`). **Fuite de threads zombies ASSUMÉE** (Python ne tue pas un thread ; `shutdown(wait=False, cancel_futures=True)`). 1 `except Exception # noqa`→outcome (conforme). **630 LOC > 400.** |
| **`planner.py`** | `PipelinePlanner.plan(spec)→ExecutionPlan` : `validate_spec` + `_resolve_steps` (bindings `(input_type, source_step_id)` ; `inputs_from` explicite sinon **dernier producteur**). `ExecutionPlan`/`ResolvedStep`/`StepInputBinding` (frozen). **Pas de tri topologique** : l'ordre de `spec.steps` est présupposé. | `domain.{artifacts,errors,pipeline_spec}`, **`evaluation.registry`**, `pipeline.validation` / `dataclasses` | chaîne vivante via `executor` seulement ; **aucun import app direct** | **`MetricJunction`+`_detect_junctions`+`metric_junctions`+`junctions_for_step` : morts** (registry jamais fourni en prod → `metric_junctions=()`). Couplage `pipeline→evaluation` **uniquement pour ce mort**. `available_adapters` : jamais alimenté → check `unknown_adapter` toujours sauté. |
| **`validation.py`** | `validate_spec(spec)→list[ValidationError]` (collecte tout, ne lève pas) : `empty_pipeline`/`duplicate_id`/`missing_input`/`inputs_from_unused`/`unknown_input_source`/`source_does_not_produce_type`. | `domain.{artifacts,pipeline_spec}` / `pydantic` | **`planner.py:287` uniquement** | `ValidationError` **homonyme** de `pydantic.ValidationError` (confusion). Couplage implicite : `_resolve_steps` indexe `latest_producer` **sans garde**, sûr seulement car `validate_spec` a tourné avant (`KeyError` sinon). Pas de détection de cycle. |
| **`cache_helpers.py`** | Système de cache **réel** : `compute_step_artifact_key`→`ArtifactKey` (domain) ; `read_cached_outputs` (miss complet si 1 output manque) ; `write_outputs_to_cache`. Métadonnées seulement (payload reste à `Artifact.uri`). | `domain.{artifact_key,artifacts}`, `pipeline.cache_protocol` / `logging,pathlib` | `executor.py:72-74,496,500,521,525` | **I/O disque dans couche 4** : `Path(stored.artifact.uri).exists()` (`:155`) — fuite d'I/O (devrait être au store). `logger.debug` sur miss (conforme). |
| **`cache_protocol.py`** | Ports d'inversion de dépendance : `ArtifactCachePort` (`get`/`put`/`__contains__`) + `CachedArtifactRef`. Permet à `pipeline` de ne pas importer `adapters`. | `domain.artifacts` / `typing` | `executor.py:76,162` (`isinstance`), `cache_helpers.py:59` | **Sur-découpage** : 85 LOC pour 2 Protocols consommés uniquement par `cache_helpers`+`executor`. Fusionnable. |
| **`cache.py`** | `ArtifactCache` in-memory (dict RAM) + clé SHA-256 **maison** (hashe `step.model_dump()` entier — **n'utilise PAS `ArtifactKey`**). | `domain.{artifacts,pipeline_spec}` / `hashlib,json` | **0 (hors tests).** Ré-export inerte `__init__.py:53,125`. La docstring `adapters/storage/__init__.py:19` qui prétend le ré-exposer est **fausse**. | **CODE MORT + doublon** du système `cache_helpers`. **2ᵉ algorithme de clé divergent** pour le même but. Docstring admet le non-branchement. |
| **`llm_pipeline_builder.py`** | `make_ocr_llm_pipeline_spec(mode, …)→PipelineSpec` : factory de spec déclarative (1 step VLM en `zero_shot` ; 2 steps OCR+LLM sinon ; IMAGE ajoutée en `text_and_image`). Logique pure. | `domain.{artifacts,errors,pipeline_spec}` / — | `app/_benchmark_adapter_resolver.py:33,195,206` | **Aucun modèle/prompt hardcodé** (littéraux `gpt-4o`/`claude` en docstrings only). `OCRLLMPipelineMode` = **alias redondant** de `domain.PipelineMode` (0 conso externe). Construit des specs → relève plutôt de `app`. |
| **`llm_pipeline_config.py`** | `OCRLLMPipelineConfig` (frozen) : container `(llm_adapter:Any, mode, ocr_adapter:Any?, prompt_template, …)` + validation (`__post_init__`) + marker `is_pipeline=True` (duck-typing). | `domain.pipeline_spec` (alias mode) / `dataclasses` | `interfaces/web/benchmark_utils.py:310,340` ; conso structurel `app/_benchmark_adapter_resolver` | Adapters typés **`Any`** → couplage caché (`.model`/`.name` ⇒ `AttributeError` possible). `name`/`ocr_engine` : **alias legacy de wiring**. `OCRLLMMode` : 3ᵉ alias redondant de `PipelineMode`. Glu app/interface, pas exécution. |
| **`run_result.py`** | `RunResult{manifest:RunManifest, document_results}` + `RunDocumentResult{pipeline_results, view_results}` + `ReportRenderer` (Callable). Agrégats applicatifs d'un run. **Placé en `pipeline/` pour contourner un import illégal `reports→app`** (Phase 5.1). | `domain.run_manifest`, `evaluation.views.base.ViewResult`, `pipeline.types` / `pathlib,pydantic` | `benchmark_service`, `run_orchestrator_execution`, reports `{html,json,csv}` | **Mal placé** : le plan couche 3 mergé (`MIGRATION_COUCHE_3.md` §8) situe `RunResult` en `evaluation/result.py`. Shim `app/results.py` le ré-exporte (3 call-sites). `pipeline_results_for` : 0 conso prod. |
| **`__init__.py`** | Façade : import **eager** de 9 sous-modules, 30 symboles dans `__all__`. | tout `pipeline/*` + `domain` (re-publie `PipelineSpec`/`PipelineStep`) | API publique du paquet | **Import eager lourd** : `from pipeline import PipelineSpec` tire `executor`/`runner`/`threading`/`evaluation` (effet de bord d'import à éliminer). Docstring **obsolète** (réfère `spec.py` inexistant, sprints S6-S12). |
| **`yaml_io.py`** | `dump_spec_to_yaml`/`load_spec_from_yaml` (round-trip `PipelineSpec` ↔ str, **en mémoire**). `yaml.safe_load`/`safe_dump`. | `domain.pipeline_spec`, `domain.errors` (lazy) / `yaml` | **0 (hors tests).** | **CODE MORT.** Doublon de pattern avec `app/schemas/run_spec.py` (loader plus riche pour `RunSpec`). Sécurité OK (`safe_*`, pas de lecture de chemin). |

## 1.5 Verdicts par fichier — **PROVISOIRE — à confirmer au build**

| Fichier | Verdict | Justification courte (vérifiée) |
|---|---|---|
| `protocols.py` | **GARDER + MODIFIER** | Contrat de module exigé en couche 4 (`CLAUDE.md` §3/§6). Ajouter **`version`** (repro → `RunManifest`). Renommer `StepExecutor`→`Module`. Nettoyer docstring (méthodes mortes). |
| `run_control.py` | **MODIFIER** | Garder `RunControl` (threading + handles). **Retirer `RunCancelledError`** (déjà en domain, D9) et l'importer. Retirer `raise_if_cancelled` (0 conso). `PicaronesError`→`CinocError`. |
| `types.py` | **MODIFIER** | Garder `RunContext`/`StepResult`/`PipelineResult`. Retirer `step_result_by_id`/`artifacts_of_type` (0 conso). **Ne pas** ajouter `token_confidences` (fantôme). Dimensionner pour résultats par-région (cf. §2.4). |
| `executor.py` | **GARDER + MODIFIER** | Vrai moteur mono-doc. Retirer `run()` (mort). **Câbler la provenance**. **Split** (>400 LOC). Trancher l'I/O cache (cf. `cache_helpers`). |
| `runner.py` | **GARDER + MODIFIER** | Vrai orchestrateur (threads/timeout/cancel/backpressure). **Split** (>400 LOC : sortir agrégation/outcome). Préserver la fuite-zombie **documentée**. |
| `planner.py` | **MODIFIER (dégraisser)** | Garder `plan`/`_resolve_steps`/`ExecutionPlan`/`ResolvedStep`/`StepInputBinding`. **Supprimer** la chaîne `MetricJunction`/`_detect_junctions` (morte → **supprime le couplage `pipeline→evaluation`**). |
| `validation.py` | **MODIFIER (fusionner)** | Conso unique = planner. **Fusionner dans `planner.py`**. Renommer `ValidationError`→`SpecError` (homonyme pydantic). Garder les 6 checks. |
| `cache_helpers.py` | **GARDER + MODIFIER** | Système réel (clé via `ArtifactKey`). **Pousser le `Path.exists()` dans le store** (sortir l'I/O de la couche 4). |
| `cache_protocol.py` | **GARDER (fusionner)** | Port d'inversion correct. **Fusionner** avec `cache_helpers` (un seul `cache.py`). |
| `cache.py` | **SUPPRIMER** | 0 conso, doublon mort, 2ᵉ algo de clé divergent. |
| `llm_pipeline_builder.py` | **CHANGER DE COUCHE → `app`** | Construit des specs depuis l'intention utilisateur (conso = resolver app). Couche 4 **exécute** des specs, ne les compose pas. Confirmer à la tranche OCR+LLM. |
| `llm_pipeline_config.py` | **CHANGER DE COUCHE → `app`** (ou supprimer) | Glu web/app, adapters `Any`, alias legacy. Pas de l'exécution. Confirmer à la tranche OCR+LLM. |
| `run_result.py` | **CHANGER DE COUCHE → `evaluation` (3)** | `RunResult` = contrat de sortie **evaluation** (`MIGRATION_COUCHE_3.md` §8). Placement Picarones = contournement d'import. `ReportRenderer`→`app`/`reports`. |
| `__init__.py` | **MODIFIER (amincir)** | `__init__` mince, **zéro effet de bord d'import** (`CLAUDE.md` §7). Pas de re-publication des types `domain`. |
| `yaml_io.py` | **SUPPRIMER** | 0 conso (« au cas où »). Trivial à recréer côté `app` si besoin réel. |

**Bilan portage** : 15 fichiers source → noyau couche 4 réécrit ≈ **6-8 fichiers**
(2 suppressions nettes, 3 changements de couche, le reste fusionné/dégraissé).

## 1.6 Constats transverses durables

- **Discipline `except` : globalement saine.** Aucun `except Exception: pass`. Les 4
  captures larges (`executor.py:379,403`, `runner.py:553`, `run_control.py:219`)
  sont `# noqa: BLE001`, **tracées** (`logger.warning`) et traduites en résultat
  d'échec. À préserver tel quel.
- **Concurrence saine, fuite assumée.** Tout le threading vit dans `runner.py`,
  état partagé sous locks. La fuite de threads (zombies) est un **choix documenté**
  (Python ne tue pas un thread), pas un bug — à porter consciemment.
- **Shims survivants** (contredit « plus aucun shim » du `CLAUDE.md` Picarones) :
  `app/results.py` (ré-export `RunResult`), `executor.run()` (sucre S7),
  alias `name`/`ocr_engine` de `OCRLLMPipelineConfig`, **triple alias** de
  `PipelineMode` (`OCRLLMPipelineMode`, `OCRLLMMode`).
- **Code mort net** : `cache.py`, `yaml_io.py`, chaîne `MetricJunction`,
  `available_adapters`, `raise_if_cancelled`/`is_cancelled`,
  `step_result_by_id`/`artifacts_of_type`, `pipeline_results_for`.
- **Provenance dormante** : `ProvenanceRecord` n'apparaît qu'en docstrings dans
  `pipeline/` ; le moteur produit des ids, **pas** de provenance. À câbler en
  couche 4 (`MIGRATION_COUCHE_1.md` §7).
- **Divergence doc/code** : `StepResult.token_confidences` est cité ailleurs mais
  **n'existe pas** ; les confidences voyagent par un `_OcrResultView` distinct.

---

# PARTIE 2 — RÉORGANISATION cible Cinoc (périssable — « à confirmer à la tranche »)

> Conforme à la discipline `CLAUDE.md` : deux axes · « pas de consommateur =
> supprimé » · budgets < 400 LOC · rupture nette zéro shim · narrative supprimé.
> **Rien ici n'est figé** : l'enveloppe se confirme au squelette ambulant ; la
> surface (fan-out, robustness, provenance) se remplit **tranche par tranche**.

## 2.1 Les deux axes appliqués à la couche 4

| Axe | Contenu couche 4 | Quand |
|---|---|---|
| **Enveloppe** (contrats, types pivots, points d'extension) | Contrat **`Module`** unique (`execute(inputs, params, context, control)` **+`version`**) ; split `RunContext`(sérialisable)/`RunControl`(runtime)/`Deadline`(domain) ; `StepResult`/`PipelineResult` **dimensionnés pour porter des résultats par-région** (`Artifact.region_id` existe déjà) ; `PipelineExecutor`(mono-doc)+`CorpusRunner`(N docs) ; `planner` à bindings explicites ; **port de cache** (inversion de dépendance). | **Maintenant** (squelette ambulant) |
| **Surface** (remplie incrémentalement, en budget, élaguée) | Fan-out par région (tranche **segmentation**) ; ré-exécution moteur de **robustness** (entrante de couche 3) ; câblage **provenance** ; adapters du starter pack (couche 5). | **Par tranche** |

## 2.2 Esquisse d'arborescence cible (à valider en codant)

| Fichier cible | Contenu | Source(s) Picarones |
|---|---|---|
| `module.py` | `Module` Protocol : `name`/`version`/`input_types`/`output_types`/`execute(...)` | `protocols.py` (+`version`) |
| `run_control.py` | `RunControl` (sans `RunCancelledError` → domain) | `run_control.py` dégraissé |
| `results.py` | `RunContext`, `StepResult`, `PipelineResult` (**pas** `RunResult`) | `types.py` dégraissé |
| `planner.py` | `PipelinePlanner`+`ExecutionPlan`+`ResolvedStep`+`StepInputBinding`+validation fusionnée (`SpecError`) | `planner.py`+`validation.py`, sans la chaîne métriques |
| `executor.py` | `PipelineExecutor` (mono-doc, provenance câblée) | `executor.py` sans `run()` |
| `runner.py` | `CorpusRunner` (threads/timeout/cancel/backpressure) | `runner.py` |
| `cache.py` | `ArtifactCachePort` + `compute_step_artifact_key`/read/write (I/O au store) | `cache_helpers.py`+`cache_protocol.py` fusionnés |
| `__init__.py` | **mince**, sans effet de bord, sans re-publier les types `domain` | `__init__.py` réécrit |

**Supprimés** : `cache.py` (in-memory), `yaml_io.py`.
**Changés de couche** : `run_result.py`→`evaluation` ; `llm_pipeline_builder.py`+`llm_pipeline_config.py`→`app`.
**Hors couche 4 (rappel)** : registre + découverte entry-points = **`app`** (`CLAUDE.md` §3).

## 2.3 Application des 5 garde-fous

1. **Rupture nette, zéro shim** → supprimer `app/results.py`, `executor.run()`,
   alias `name/ocr_engine`, triple alias `PipelineMode`. Un seul chemin.
2. **Budgets < 400 LOC** → `executor.py` (574) et `runner.py` (630) **doivent
   être splittés** le long de coutures naturelles (executor : exécution / cache ;
   runner : submit-poll / agrégation-outcome). Croissance « assumée » si justifiée.
3. **Pas de consommateur = supprimé** → applique les SUPPRESSIONS de §1.5/§1.6.
4. **Tests d'archi jour 1** → `no-side-effect-import` (`__init__` mince),
   `layer-deps` (pipeline n'importe que `domain`+stdlib+pydantic ; **plus
   `evaluation`** une fois la chaîne métriques retirée), `file-budgets`,
   `no-broad-except`.
5. **Une feature = entière, en budget, en élaguant** → fan-out, robustness,
   provenance : chacun à sa tranche, pas « au cas où » d'avance.

## 2.4 Ce que la couche 4 NE possède PAS (frontières héritées — à ne pas recréer)

- **`RunResult` ∉ couche 4.** Il vit en `evaluation/result.py` (couche 3 mergée,
  `MIGRATION_COUCHE_3.md` §8). Picarones le plaçait ici par contournement d'import.
  Une future session **ne doit pas** le recréer en `pipeline/`.
- **`CanonicalLayout` + fan-out par région ∉ maintenant.** Différés à la tranche
  segmentation (`CLAUDE.md` §3, `MIGRATION_COUCHE_2.md` L10, `MIGRATION_COUCHE_3.md`
  §10). L'enveloppe **réserve** la place (`region_id` sur `Artifact`,
  `PipelineResult` dimensionné), mais **rien n'est bâti** sans son consommateur.
- **Registre/factory/découverte ∉ couche 4.** En `app` (`CLAUDE.md` §3 brique 2-3).
  La couche 4 ne connaît que `AdapterResolver = Callable[[str], Module]`.
- **`RunCancelledError` ∉ couche 4.** En `domain/errors.py` (déjà mergé, D9).

## 2.5 Cohérence avec les couches mergées (vérifiée, aucune contradiction)

- `domain` fournit déjà tout l'amont : `Deadline` (API `infinite/in_seconds/is_expired/as_sdk_timeout/clamp_to_remaining/to_dict`), `ArtifactKey` (`input_hashes`/`adapter_name`/`adapter_version`/`code_version`/`hash_hex`), `Artifact.region_id`, `ArtifactType.{LAYOUT,RAW_TEXT,CORRECTED_TEXT}`, `RunManifest`, `PipelineSpec`/`PipelineStep`/`PipelineMode`/`INITIAL_STEP_ID`, erreurs (`RunCancelledError`/`DeadlineExceeded`/`AdapterStepError`).
- Le contrat `Module.execute(... context, control)` **place bien** deadline+annulation en couche 4 (raison du non-placement en domain, D1) — cohérent.

---

# PARTIE 3 — Risques de transfert & dettes potentielles (+ détection)

## 3.1 Risques de transfert

| # | Risque | Détection |
|---|---|---|
| **T1** | Recréer `RunResult` en `pipeline/` (placement Picarones trompeur) | Test d'archi : `pipeline/` ne définit pas `RunResult` ; `grep` ; revue de la frontière §2.4. |
| **T2** | Bâtir le **fan-out par région** d'office (spéculatif, sans consommateur) | Garde-fou « pas de consommateur = supprimé » ; aucun `CanonicalLayout` en couche 4 avant sa tranche. |
| **T3** | Porter la **provenance dormante** (moteur qui ne produit que des ids) | Test : après `run_plan`, chaque `Artifact` produit porte un `ProvenanceRecord` (code_version). |
| **T4** | Garder l'**I/O disque** (`Path(uri).exists()`) en couche 4 | Test d'archi « pas d'accès filesystem en `pipeline/` » ; pousser l'existence au store. |
| **T5** | Porter `StepExecutor` **sans `version`** (trou de reproductibilité) | Le `Module` Protocol exige `version` ; test `RunManifest` inclut les versions de modules. |
| **T6** | `__init__` à **import eager** (effet de bord, tire threading/evaluation) | Test `no-side-effect-import` ; `import cinoc.pipeline` ne doit pas charger le runtime. |
| **T7** | Reproduire la **fuite de threads** sans la maîtriser/documenter | Test : timeout → outcome immédiat + `shutdown(wait=False, cancel_futures=True)` ; commentaire explicite. |
| **T8** | Réintroduire `ValidationError` **homonyme** de pydantic | `grep` ; renommer `SpecError` ; mypy. |
| **T9** | Importer la **divergence `pipeline→evaluation`** via la chaîne métriques morte | Test `layer-deps` : `pipeline/` n'importe pas `evaluation` (après suppression `_detect_junctions`). |
| **T10** | Recréer `StepResult.token_confidences` (champ **fantôme**) | Déjà absent ; ne pas l'ajouter ; confidences = artefact/canal dédié. |

## 3.2 Dettes potentielles

| # | Dette | Détection / parade |
|---|---|---|
| **D1** | Couplage implicite `planner↔validation` (`latest_producer` sans garde, `KeyError` si validate sauté) | Fusionner les deux ; test sur spec invalide passée à `_resolve_steps`. |
| **D2** | **Pas de tri topologique réel** (ordre de `spec.steps` présupposé) | Décider : valider l'ordre **ou** trier ; test cycle/ordre inverse. |
| **D3** | `executor.py`/`runner.py` > 400 LOC | `test_file_budgets` ; split aux coutures. |
| **D4** | Couplage caché `Any` de `OCRLLMPipelineConfig` (si porté en `app`) | Typer contre `Module` ou supprimer ; mypy strict. |
| **D5** | Triple alias `PipelineMode` (dette déjà documentée en source) | N'utiliser que `domain.PipelineMode` ; `grep` des alias. |
| **D6** | Sur-découpage cache (3 fichiers → 1) | Revue ; un seul `cache.py`. |
| **D7** | `make_ocr_llm_pipeline_spec` recâblé hâtivement en couche 4 | Le traiter **à la tranche OCR+LLM**, côté `app`. |

---

# Synthèse pour la session de construction (3-5 points clés)

1. **Un moteur + un orchestrateur, pas deux moteurs.** Porter `PipelineExecutor`
   (mono-doc, séquentiel, cache, provenance à câbler) **enveloppé** par
   `CorpusRunner` (threads/timeout/cancel/backpressure). Composition stricte,
   point de câblage unique. Les deux > 400 LOC → **splitter**.
2. **Le contrat de module est le pivot de l'enveloppe.** `Module.execute(inputs,
   params, context, control) → dict[ArtifactType, Artifact]`, **+`version`**
   (manquant en source, exigé pour la repro). Implémenté en duck-typing par les
   adapters (couche 5). `RunContext`(sérialisable)/`RunControl`(runtime)/`Deadline`
   (domain) restent séparés.
3. **Le fan-out par région N'EXISTE PAS en source** — c'est du net-new, **différé
   à la tranche segmentation** avec `CanonicalLayout`. L'enveloppe réserve la place
   (`region_id`, `PipelineResult` dimensionné) ; **ne rien bâtir d'avance**.
4. **Suppressions/déplacements nets** : supprimer `cache.py`(mort) + `yaml_io.py`(mort) ;
   **déplacer** `run_result.py`→`evaluation`(3) et les 2 fichiers LLM→`app`(6) ;
   **dégraisser** `planner` (retirer la chaîne métriques morte → coupe le couplage
   `pipeline→evaluation`) et fusionner `validation`. 15 fichiers → ≈ 6-8.
5. **Garder la discipline saine de la source** (zéro `except: pass`, locks, fuite
   zombie assumée) ; **casser les shims** (`app/results.py`, `executor.run()`,
   alias `PipelineMode`/`ocr_engine`) ; **câbler la provenance** et **sortir l'I/O
   cache** vers le store. Tests d'archi (`layer-deps` sans `evaluation`,
   `no-side-effect-import`, `file-budgets`) dès le premier commit de code.

## DoD vivante (couche 4) — **autorité de détail** ; le `MIGRATION_PLAN.md` indexe

> **T8 (D-066)** : contrat `Module.execute` → **`StepOutput(artifacts, usage)`** (changement atomique, zéro double signature) ; l'exécuteur **mesure** la durée de chaque étape (monotonic, source unique), fusionne les jetons remontés, renvoie **`DocumentExecution(artifacts, usage)`** ; le fan-out somme les jetons des N régions. Preuves : `tests/pipeline/test_executor.py::test_usage_records_duration_and_tokens` · `::test_usage_sums_across_steps`.

> **P5e 1 (D-275)** : `DocumentExecution` porte l'**issue** de l'unité (`outcome` · `reason` · `message`, invariants : motif ⇔ `failed`, aucun artefact en échec ; `DocumentExecution.failed(...)`) ; `executor.UNIT_FAILURES` (les erreurs qui font échouer une unité sans arrêter le run) et `failure_reason(exc)` (motif lu sur la classe : `DeadlineExceeded` → `cancelled`, `PipelineStepError` → `unsupported`, autre `AdapterStepError` → `engine`). L'exécuteur continue de **lever** : l'orchestrateur convertit, la classification vit ici, à côté des erreurs qu'elle lit. Preuves : `tests/pipeline/test_executor.py::{test_failure_reason_is_read_on_the_error_class,test_document_execution_outcome_invariants,test_run_cancellation_is_not_a_unit_failure}`.

> **P5e 1b (D-276)** : `DocumentExecution` rend `by_step` (sorties de **chaque** étape, ordre d'exécution, entrées initiales sous `__initial__`) et `step_usage` (durée mesurée + jetons, par étape) ; `artifacts` (pool) et `usage` (somme) sont des propriétés **déduites** — l'exécuteur ne tient plus qu'une structure. `__initial__` dans `inputs_from` lit toujours le pool (dernière version du type : une recette `preprocess → ocr` passe l'image prétraitée), comportement conservé. Le fan-out n'avait rien à changer : sa sortie est estampillée par `_stamp` comme toute étape (`tests/pipeline/test_segmentation_pipeline.py`, `filled.produced_by_step == "recognize"`). Preuves : `tests/pipeline/test_executor.py::{test_two_steps_of_the_same_type_both_stay_observable,test_usage_is_kept_per_step_and_the_total_derives_from_it,test_document_execution_outcome_invariants}`.

> **P5e 2 (D-277)** : `StepOutput.truncation` (motif lisible, `None` = complète ou inconnue) — seul le module lit la réponse native, c'est donc lui qui déclare la coupure, comme ses jetons. L'exécuteur en fait l'issue de l'unité : `DocumentExecution(outcome="truncated", message="étape 'x' : …")`, **sorties gardées** (elles sont notées). Le fan-out ne l'avale pas : `run_region_fanout(truncations=…)` recueille une ligne par région coupée et `execute_region_fanout` la remonte dans son `StepOutput`. Preuves : `tests/pipeline/test_executor.py::{test_a_cut_step_marks_the_unit_truncated_and_keeps_its_output,test_a_complete_run_stays_ok}`, `tests/pipeline/test_fanout.py::test_a_cut_region_is_reported_not_swallowed`.

> Tri-état : `[x]` fait **+ preuve** · `[ ]` à faire · `[~]` différé/réserve + raison.
> Maj dans le **même commit** que le code. **Statut : ✅ T3** — `Module` Protocol + exécuteur (résolution DAG + estampille de provenance) + `RunControl`/`Deadline` + **annulation câblée** (ollama, T3) verts. **+ T5 squelette** : `fanout.py` (`run_region_fanout` — reconnaissance par région, échec partiel toléré, ordre de lecture préservé) ; le `Module` reste **inchangé** (1 artefact/type, le fan-out boucle dans l'orchestration). *preuve : `tests/pipeline/test_segmentation_skeleton.py`*. **+ T5 wiring déclaratif** : `execute_region_fanout` (persiste le LAYOUT rempli) + branche `step.fanout` dans `PipelineExecutor` → une `PipelineSpec` unique orchestre segment→fanout→assemblage. *preuve : `tests/pipeline/test_segmentation_pipeline.py`*

**Enveloppe (plein-scope dès T1) :**
- [x] `Module` Protocol unique : `name`/**`version`**/`input_types`/`output_types`/`execute(inputs,params,context,control)`. — *preuve : `precomputed` l'implémente (`isinstance(.., Module)` vert) ; `pipeline/protocols.py`*
- [x] Split `RunContext`(domain `Deadline`) / `RunControl`(runtime), câblés par l'exécuteur. — *preuve : `tests/pipeline/test_run_control.py` + `test_executor.py` verts.* `[~]` round-trip (dé)sérialisation `RunContext` : test dédié à ajouter.
- [x] **`RunControl.register_cancel_handle`** (interruption d'appel bloquant) — différé en T1 faute de consommateur (D-008), **livré en T3 avec son 1ᵉʳ vrai consommateur** (`ollama`). Thread-safe (`Lock`) : enregistrement et `trigger_cancel` synchronisés → handle ni perdu (course) ni appelé deux fois ; enregistrement *après* annulation = appel immédiat. Sondage coopératif (`raise_if_cancelled`) reste la **garantie** ; le handle est *best-effort*. — *preuve : `test_run_control` (fire-on-cancel · immédiat-si-déjà-annulé · once · ordre) ; consommateur réel `adapters/llm/ollama.py`*
- [x] `PipelineExecutor` mono-doc, **provenance estampillée** (`code_version` + `parameters_hash` + `produced_by_step`). — *preuve : `test_executor::test_runs_single_step_and_stamps_provenance`*
- [ ] `CorpusRunner` N-docs (threads/timeout/cancel/backpressure). — *T1 (app) / T2*
- [ ] `planner`+`validation` fusionnés (`SpecError`, pas d'homonyme pydantic) ; port de cache.

**Garde-fous (verts dès la 1ʳᵉ tranche) :**
- [x] `layer_dependencies` (`pipeline` → domain seulement, **pas** `evaluation`) · `no_side_effect_imports` (`__init__` mince) · `file_budgets` · `no_broad_except`. — *preuve : `test_pipeline_imports_are_allowed` + suite archi verte*

**Validation inter-couches :** `MIGRATION_PLAN.md` §3-T1 (module exécuté de bout en bout) + §3-T4 (un `cancel` interrompt réellement).

- [x] **fan-out par région (T5)** : `fanout.py` + `execute_region_fanout`, orchestré par `step.fanout` dans l'exécuteur ; assemblage `LAYOUT→ALTO_XML` livré (`AltoAssembler`, couche 5). **+ `RegionCropper`** injecté → **crop réel des blocs** (pipeline hybride seg→OCR par bloc ; la couche 4 calcule la boîte relative, PIL en couche 5). *preuve : `tests/adapters/layout/test_crop.py`, `tests/pipeline/test_hybrid_real_bnl.py` (live)*. Reste (épaississement) : routage par type de bloc, segmenteur **out-of-tree** (T6).
- [~] **Différé** : ré-exécution robustness (entrante couche 3). **Ne PAS recréer `RunResult` ici** (→ couche 3) ni `cache.py`/`yaml_io.py` (morts).

---

*Verdicts marqués « PROVISOIRE — à confirmer au build ». Partie 1 durable (source
figée) ; Partie 2 périssable (à confirmer à la tranche).*
