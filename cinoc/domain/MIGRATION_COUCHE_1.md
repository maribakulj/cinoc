# Plan de migration — Couche 1 (`domain/`) : Picarones → Cinoc

> **Statut** : plan validé, prêt à exécuter.
> **Périmètre** : uniquement la couche 1 (`domain/`). Les 7 autres couches feront l'objet de plans dédiés.
> **Source** : `Picarones/picarones/domain/` (15 fichiers, 2 401 LOC).
> **Cible** : `Cinoc/cinoc/domain/` (13 fichiers après décisions : `facts.py`
> et `module_protocol.py` non migrés en `domain`). Le contrat de module
> exécutable n'est **pas perdu** : il est construit en couche 4 (`pipeline`),
> voir D1.

---

## 1. Objectif

La couche `domain` est le **cœur typé** du système : elle ne contient que des
définitions de données (le « vocabulaire » du produit), sans aucune logique
métier, sans I/O, sans dépendance à un moteur externe. Elle n'importe que la
bibliothèque standard Python, `pydantic` et `pydantic_core`.

C'est la couche la plus saine de Picarones (~91 % à recopier tel quel). Ce plan
acte les suppressions décidées et liste, fichier par fichier, ce qui est porté,
nettoyé ou abandonné.

---

## 2. Décisions actées (ce qui change par rapport à Picarones)

| # | Décision | Conséquence concrète |
|---|----------|----------------------|
| **D1** | **`BaseModule` : contrat unique de module, construit en couche 4 (pas en `domain`)** | L'extensibilité tierce est une exigence d'enveloppe → on construit **un seul contrat de module exécutable (`Protocol`)** implémenté directement (≠ le double contrat `BaseOCRAdapter`→`BaseModule` de Picarones). **Mais il vit en `pipeline` (couche 4)**, pas en `domain` : sa méthode `execute()` porte des concerns d'exécution (deadline, annulation via `RunControl`, couche 4) — un `Protocol` en `domain` qui les référencerait violerait le sens des dépendances. Donc `module_protocol.py` n'est **pas** recréé en `domain`. La couche 1 ne garde que le **déclaratif** : `PipelineStep` (qui nomme l'`adapter_name` + `input_types`/`output_types`) et `ArtifactType` suffisent à décrire un module dans une spec. Registre + découverte entry-points = couche `app`. |
| **D2** | **Supprimer entièrement le moteur narratif** | `facts.py` **non migré**. Cinoc n'aura pas de synthèse en prose : le rapport affichera les chiffres et tableaux bruts. Supprime aussi, en aval, toute la couche 7 `reports/narrative/` (hors périmètre de ce plan, mais acté). |
| **D3** | Purger le legacy résiduel des fichiers conservés | Voir §4 : `LEGACY_VALUE_ALIASES`, shim `pipeline_names` du `RunManifest`. |
| **D4** | Renommer la racine d'erreurs | `PicaronesError` → `CinocError` (et toute la hiérarchie reste). |
| **D5** | Nettoyer les commentaires historiques | Supprimer toutes les annotations de sprint (`S4`, `A14-S29`, `Phase 7.1`…) et les références au fichier inexistant `BACKLOG_POST_LIVRAISON.md`. |
| **D6** | Convention de nommage | Préférer `pipelines_involved` à `engines_involved` (le champ d'origine disparaît avec `facts`). |
| **D7** | `ArtifactType.LAYOUT` (type structurel unique) | Segmentation et structure transcrite = un seul type. Pas de `REGIONS` séparé : une segmentation est un `CanonicalLayout` à régions sans lignes. `CanonicalLayout` → `domain`, matérialisé à la **tranche segmentation** (pas en couche 2 : anti-spéculatif — cf. `formats/MIGRATION_COUCHE_2.md`, L10). |
| **D8** | **Ajouter `region_id` optionnel sur `Artifact`** | Permet de représenter « un artefact texte rattaché à une région ». Socle du fan-out par bloc (modèle b, **retenu**) : métriques par bloc + routage par type de bloc. `None` = artefact au niveau page. |
| **D9** | **Rapatrier `RunCancelledError` dans `errors.py`** | Seule erreur transverse mal placée (était en `pipeline/run_control.py`), sœur de `DeadlineExceeded`. Voir §4.3. Les autres types « domain » repérés ailleurs (`ProjectionReport`, `RunSpec`, `ConfidenceToken`) sont **différés** à la migration de leur couche propriétaire (backlog domain dans `CLAUDE.md`) — pas créés maintenant (anti-spéculatif). |

---

## 3. Inventaire source → cible

15 fichiers Picarones → **13 fichiers Cinoc** (`facts.py` et `module_protocol.py`
non migrés en `domain`). Les seuls ajouts de la couche 1 liés à la structure
sont `ArtifactType.LAYOUT` et `Artifact.region_id` (dans `artifacts.py`).

| # | Picarones (`domain/`) | → Cinoc (`domain/`) | Décision | Transformation |
|---|------------------------|----------------------|----------|----------------|
| 1 | `__init__.py` | `__init__.py` | **KEEP** | Retirer exports de `facts` et `module_protocol` ; supprimer annotations sprint |
| 2 | `_version_fallback.py` | `_version_fallback.py` | **KEEP** | `FALLBACK_VERSION = "0.1.0"` ; mettre à jour la docstring |
| 3 | `artifacts.py` | `artifacts.py` | **KEEP + purge + étendre** | Supprimer `LEGACY_VALUE_ALIASES` + les 3 alias `TEXT/ALTO/PAGE` (garder `_missing_()`) ; **ajouter `ArtifactType.LAYOUT` (D7) et le champ `region_id` (D8)** |
| 4 | `artifact_key.py` | `artifact_key.py` | **KEEP** | Recopier tel quel (purge réfs sprint) |
| 5 | `corpus.py` | `corpus.py` | **KEEP** | Supprimer réf. `BACKLOG_POST_LIVRAISON.md` + note « S10 » |
| 6 | `documents.py` | `documents.py` | **KEEP** | Recopier tel quel (conserver la défense path-traversal) |
| 7 | `provenance.py` | `provenance.py` | **KEEP** | Recopier (purge réfs sprint). À **réellement câbler** côté executor (couche 4) : 0 consommateur dans Picarones (provenance dormante) |
| 8 | `projection_spec.py` | `projection.py` *(renommé)* | **KEEP** | Recopier tel quel |
| 9 | `errors.py` | `errors.py` | **KEEP + rename + D9** | `PicaronesError` → `CinocError` ; purger note legacy `core` ; **ajouter `RunCancelledError`** (rapatriée de `pipeline/run_control.py`) |
| 10 | `pipeline_spec.py` | `pipeline.py` *(renommé)* | **KEEP** | Recopier tel quel (purge réfs sprint) |
| 11 | `evaluation_spec.py` | `evaluation.py` *(renommé)* | **KEEP** | Recopier ; purger réf. backlog + mention `compute_metrics (legacy)` |
| 12 | `module_protocol.py` | — | **DROP de `domain` (D1)** | Non migré en `domain`. Le contrat de module exécutable (`Protocol`) est construit en couche 4 (`pipeline`) — voir D1 |
| 13 | `run_manifest.py` | `run.py` *(renommé)* | **KEEP + purge** | Supprimer `pipeline_names` (computed_field) ET `_accept_legacy_pipeline_names` (~67 LOC de shim) |
| 14 | `facts.py` | — | **DROP (D2)** | Non migré |
| 15 | `deadline.py` | `deadline.py` | **KEEP** | Recopier tel quel (type exemplaire) |

> **Renommages (actés)** : `projection_spec.py`→`projection.py`,
> `pipeline_spec.py`→`pipeline.py`, `evaluation_spec.py`→`evaluation.py`,
> `run_manifest.py`→`run.py`. Nom = concept ; les suffixes `_spec`/`_manifest`
> étaient des béquilles de migration. `domain.pipeline` et `domain.evaluation`
> partagent le nom des couches `pipeline/`/`evaluation/` mais en sont distincts
> par le chemin d'import.

---

## 4. Détail des transformations par fichier

### 4.1 `artifacts.py` — purge des alias legacy
- **Conserver** : `ArtifactType` (10 valeurs canoniques), `compute_content_hash`, la classe `Artifact` (frozen, validators id/hash), `_missing_()` (accepte `"text"`/`"alto"`/`"page"` dans les YAML).
- **Supprimer** : le dict `LEGACY_VALUE_ALIASES` + le bloc de commentaire `expand_legacy_keys` (lignes ~133-150). Unique consommateur = `module_policy.py` (couche 3), lui-même destiné à être réécrit.
- **Supprimer** : les 3 attributs alias `TEXT`/`ALTO`/`PAGE` de l'enum. Migrer les call-sites vers les noms canoniques (`RAW_TEXT`/`ALTO_XML`/`PAGE_XML`). *(Hors couche 1 — à traiter quand on portera les couches consommatrices.)*

### 4.2 `run.py` (ex-`run_manifest.py`) — suppression du shim
- **Conserver** : tous les champs reproductibilité (`run_id`, `corpus_name`, `n_documents`, `pipeline_specs`, `adapter_kwargs`, `view_specs`, `code_version`, `started_at/completed_at`, `dependencies_lock`, `system_binaries_lock`, `metadata`), `duration_seconds`, `utcnow()`.
- **Supprimer** : le `computed_field` `pipeline_names` (lignes ~129-139) et le `model_validator` `_accept_legacy_pipeline_names` (lignes ~141-196). Pur shim de compatibilité JSON, sans consommateur une fois l'ancien `reports/html/render.py` abandonné.

### 4.3 `errors.py` — renommage de la racine + 1 rapatriement (D9)
- `PicaronesError` → **`CinocError`**. Conserver toutes les sous-classes : `ArtifactValidationError`, `ProjectionError`, `CorpusSpecError`, `AdapterStepError`, `DeadlineExceeded`.
- **Ajouter `RunCancelledError` (D9)** — rapatriée de `pipeline/run_control.py`. C'est une **erreur transverse** (levée par le runner, rattrapée ailleurs), sœur de `DeadlineExceeded` qui est déjà en domain. Forme triviale et stable → le seul type « venu d'une autre couche » qui s'intègre proprement dès la couche 1. *(L'objet `RunControl` lui-même reste en couche 4 : threading + état mutable.)*
- Conserver intégralement la docstring de `DeadlineExceeded` (elle porte un vrai contrat de comportement pour les adapters).
- Supprimer la note historique sur `picarones.core` (lignes ~26-30).

### 4.4 Fichiers recopiés sans changement fonctionnel
`artifact_key.py`, `documents.py`, `provenance.py`, `projection.py`,
`pipeline.py`, `evaluation.py`, `corpus.py`, `deadline.py`, `_version_fallback.py`.
Seules transformations : retrait des annotations de sprint et des références au
backlog inexistant. **Aucune logique ne change.**

### 4.5 `__init__.py` — agrégateur
- Retirer des imports/`__all__` tout ce qui vient de `facts` (`Fact`, `FactType`, `FactImportance`, `DetectorFn`, `DetectorRegistry`, `detect_all`) **et** de `module_protocol` (`BaseModule`).
- **Exporter** `ArtifactType.LAYOUT` (le `region_id` est un champ d'`Artifact`, déjà exporté).
- Adapter les chemins d'import aux fichiers renommés.
- Conserver la note expliquant pourquoi `RunResult` n'est PAS dans `domain` (il agrège des couches externes).

### 4.6 `module_protocol.py` — NON migré en `domain` (contrat déplacé en couche 4)
- Le contrat de module **n'est pas perdu**, mais il **ne vit pas en `domain`** :
  sa méthode `execute()` a besoin de la deadline et de l'annulation
  (`RunControl`, couche 4). Un `Protocol` en couche 1 qui les référencerait
  importerait vers l'extérieur → interdit.
- **Décision** : construire **un seul `Protocol` de module exécutable en couche 4
  (`pipeline`)** — `name`, `version` (reproductibilité), `input_types`,
  `output_types`, `execute(inputs, params, contexte d'exécution) → outputs`.
  Implémenté **directement** par chaque module (≠ double contrat de Picarones).
- **Au niveau couche 1**, rien à faire : `PipelineStep` (déclare `adapter_name`
  + `input_types`/`output_types`) et `ArtifactType` suffisent à **décrire** un
  module dans une spec. Registre + découverte entry-points = couche `app`.
- ⚠️ À traiter dans le **plan de la couche 4**, pas ici.

### 4.7 `artifacts.py` — extensions structure (D7/D8)
- `ArtifactType.LAYOUT` : type structurel unique (pas de `REGIONS` séparé).
- `region_id: str | None` sur `Artifact` : rattachement d'un artefact à une
  région ; `None` = niveau page.
- La classe `CanonicalLayout` (et ses parties) n'est **pas** créée en couche 1 :
  décidée en `domain`, matérialisée à la **tranche segmentation** (pas en couche 2 ;
  backlog domain dans `CLAUDE.md`).

---

## 5. Renommages transverses (à propager dans tout Cinoc)

| Picarones | Cinoc | Portée |
|-----------|--------|--------|
| `PicaronesError` | `CinocError` | Toute la base de code |
| `picarones.domain.*` | `cinoc.domain.*` | Tous les imports |
| `engines_involved` | `pipelines_involved` | Convention (le champ disparaît avec `facts`, mais la règle reste) |
| `code_version="1.0.0"` (placeholder de test) | constante de fixture unique, nommée et documentée à un seul endroit | Tests |

---

## 6. Ordre d'exécution

1. **Squelette** : créer `cinoc/domain/` (fait — ce dossier).
2. **Fichiers sans dépendance interne d'abord** (ordre topologique des imports) :
   `errors.py` → `_version_fallback.py` → `artifacts.py` → `provenance.py`
   → `artifact_key.py` → `documents.py` → `corpus.py` → `projection.py`
   → `evaluation.py` → `pipeline.py` → `deadline.py` → `run.py`.
3. **`__init__.py`** en dernier (il agrège tout).
4. **Tests** (voir §7) écrits en parallèle de chaque fichier.
5. **Vérification** : `mypy --strict cinoc/domain/`, `ruff check`, `pytest tests/domain tests/architecture`.

---

## 7. Tests indispensables (couche 1)

### Domain
- Validateurs Pydantic : `doc_id` rejette `..` et chemins absolus ; `PipelineStep.id` unique et alphanumérique ; `PipelineMode` est un `Literal` strict (rejette toute autre valeur).
- Hash déterministe : `ArtifactKey.hash_hex()` stable et reproductible ; `Artifact.content_hash` validé hex 64 chars ; `hash_hex()` retourne `None` si un input manque.
- `Deadline` : monotonic, `remaining_seconds` jamais négatif, sérialisation cross-process (`to_dict`/`from_dict`/pickle), immutabilité.
- `RunManifest` : round-trip JSON byte-stable **sans** le shim `pipeline_names`.
- `CinocError` : la hiérarchie attrape bien toutes les sous-classes.

### Architecture (à activer dès maintenant)
- `test_layer_dependencies` : `domain` n'importe que stdlib + `pydantic` + `pydantic_core`.
- `test_no_legacy_imports` : aucun import de `picarones`, aucun symbole `Fact*`/`BaseModule`.
- `test_single_version_source` : `FALLBACK_VERSION` == `pyproject.toml [tool.setuptools_scm]`.
- `test_no_broad_except` : pas de `except Exception: pass`.
- `test_no_side_effect_imports` : les `__init__.py` ne déclenchent aucun effet de bord.

---

## 8. DoD vivante (couche 1) — **autorité de détail** ; le `MIGRATION_PLAN.md` indexe

> **T8 (D-066)** : `+ usage.py` — `ResourceUsage` (durée wall-clock + jetons, `merged_with` somme `None`-tolérante) ; vocabulaire transversal consommé par la couche 4 (`StepOutput`) et la couche 3 (`RunResult.usage`). Preuve : `tests/evaluation/test_result.py::test_usage_channel_round_trips`.

> **T12 (D-070)** : `+ confidence.py` — `ConfidenceToken` (mot + confiance [0,1]), schéma du payload `CONFIDENCES`, créé avec son 1ᵉʳ consommateur (calibration couche 3). Backlog domain : dernière entrée cochée.

> **P5e 1 (D-275)** : `usage.py` gagne deux alias `Literal` — `UnitOutcome` (`ok` · `truncated` · `failed`) et `FailureReason` (`engine` · `infrastructure` · `unsupported` · `cancelled`), vocabulaire de l'issue d'une unité produite en couche 4 et transportée en couche 3 (aucune classe neuve) ; `evaluation.py` : `FailurePolicy` + `EvaluationSpec.failure_policy` (`exclude` par défaut, `max_error`) ; `run.py` : `RunManifest.failure_policy` (un agrégat ne se relit pas sans elle). Preuves : `tests/app/test_unit_outcome.py`, `tests/evaluation/test_result.py::test_v2_payload_still_loads_as_ok_units_without_expected`.

> **P5e 1b (D-276)** : `artifacts.py` gagne l'alias `StepArtifacts` (`{id d'étape: {type: artefact}}`, ordre d'exécution, entrées initiales sous `INITIAL_STEP_ID`) et `latest_by_type` (le pool = une lecture de `by_step`, partagée par les couches 3, 4 et 6 — la couche 4 ne peut importer que `domain`) ; `EvaluationView.target_step` (`None` = l'étape la plus aval qui produit un type candidat), omise du JSON quand `None` (sérialiseur *wrap*) ; `RunSpec` refuse au chargement une cible inconnue d'un pipeline du run et une étape visée qui **déclare** plusieurs types candidats (erreur `CinocError`, message nommant vue, étape, pipeline et étapes connues). Preuves : `tests/domain/test_run_spec.py`, `tests/app/test_step_target.py`.

> **P5f 3 (D-278)** : `ArtifactType.NATIVE_JSON` (réponse native brute d'un moteur distant, sidecar JSON ; enveloppes `{"regions": …}` pour un fan-out et `{"responses": …}` pour la correction structurée, documentées sur la valeur) et `native_json_bytes` (forme canonique : JSON UTF-8, clés triées, séparateurs compacts, `allow_nan=False`) — en `domain` parce que la couche 4 (fan-out) et la couche 5 (adaptateurs) écrivent le même payload, comme `compute_content_hash`. `EvaluationView` refuse `native_json` dans `candidate_types` (`CinocError` au chargement) : une réponse native n'est pas une sortie à noter. Preuves : `tests/evaluation/test_native_json_never_scored.py`, `tests/adapters/test_native_json.py::test_native_json_bytes_is_canonical`.

> **P5f 2 + 2b (D-279)** : `RunManifest` gagne `served_models` (`{adapter_name: (modèle servi, …)}` — une observation, hors de l'empreinte) et `unicode_version` (`unicodedata.unidata_version`, dont dépendent normalisation et métriques) ; `adapter_kwargs` y devient les réglages **effectifs** (ceux que hache l'empreinte de l'étape), `dependencies_lock` est enfin rempli, `system_binaries_lock` est celui de la clé (sondé avant la première page ; celui de l'archive hors ligne). `ProvenanceRecord.parameters_hash` est l'**empreinte de l'étape** (`pipeline.fingerprint.step_fingerprint` : brique, version du module, réglages effectifs — modèle, prompt, défauts, endpoint —, binaires), et non plus le seul haché de `step.params` ; `served_models` s'y ajoute, hors de `is_compatible_with`. Preuves : `tests/app/test_archive_rescore.py`.

> **S10b (D-282)** : les champs ensemblistes sérialisés **triés** en JSON — `EvaluationView.candidate_types` (par valeur) et `MetricSpec.tags` (`field_serializer(when_used="json")`) ; le mode Python garde le `frozenset`. Le format ne change pas (une liste), seul l'ordre devient stable : pas de version de schéma. Preuves : `tests/domain/test_evaluation.py::test_set_fields_serialize_sorted_whatever_the_hash_seed` (8 graines de hachage) · `tests/interfaces/test_run_determinism.py`.

> **P5e 7 (D-285)** : `EvaluationView.normalization_profile` vaut par défaut `DEFAULT_NORMALIZATION_PROFILE` = `"flat_text"` (constante de `domain/evaluation.py`, vérifiée contre `NORMALIZATION_PROFILES` par la couche 2) ; `None` **explicite** = comparaison brute — le sens qu'avait `null` dans un JSON antérieur, donc rien n'est relu faux. Le nom est toujours sérialisé : un `RunResult` dit sous quelle convention son chiffre a été calculé. — *preuve : `tests/domain/test_evaluation.py::test_view_without_profile_gets_the_default_and_null_means_raw`*

> **P5e 9 (D-289)** : `evaluation.py` gagne `MetricCategory` (`established` · `adapted` · `exploratory`) et `MetricUnit` (`character` · `word` · `character_trigram` · `line` · `region` · `entity` · `numeric_sequence` — ce que compte le **poids** de l'agrégat micro) ; `MetricSpec.category` et `MetricSpec.unit` sont **requis** : une métrique sans l'un ou l'autre n'est pas enregistrable. Consommateurs : le runner (famille de tests réduite aux établies), le rapport (classement, marques, fiche). Preuve : `tests/domain/test_evaluation.py::test_metric_spec_requires_category_and_unit`, `tests/reports/test_metric_cards.py`.

> **P5f 4 (D-291)** : `layout.py` — `Region.confidence: float | None` (∈ [0, 1], NaN et ∞ refusés, `None` par défaut ; un `CanonicalLayout` JSON antérieur se relit) : confiance **dans la région** (son existence, son étiquette), distincte de `Line.confidence` (son texte). Consommateurs : `adapters/layout/_base.to_canonical_layout` (score de détection, jeté jusque-là) et la projection Mistral OCR (`block_type_confidence_score`). Non affichée (le SVG de segmentation n'a pas de locale). Preuve : `tests/domain/test_region_confidence.py`.

> **P5f 5 + 7 (D-292)** : `usage.py` — `ResourceUsage.billed_pages` (pages facturées à la page, tentatives facturables comprises ; `None` = non compté, sommé par `merged_with`) ; `FailureReason` : `cancelled` couvre aussi le **délai propre d'une étape** (« arrêtée (délai) », D3 du pilote — aucun motif créé). `errors.py` — `AdapterStepError(…, billed=ResourceUsage | None)` : ce qu'une étape a fait facturer avant d'échouer (jetons d'une réponse refusée, page soumise) ; docstring de `DeadlineExceeded` : un délai d'étape dépassé en est un. *Preuve : `tests/adapters/test_resilience.py`, `tests/app/test_resumed_units.py`, `tests/evaluation/test_economics.py`.*

> **S22 fin (D-294, P5f 8)** : `usage.py` — `ResourceUsage.tokens_cache_read`, `.tokens_cache_write`, `.tokens_reasoning` : **parties** de `tokens_in` (désormais toute l'entrée, cache compris) et de `tokens_out` (toute la sortie, raisonnement compris) ; `None` = non rendu (jamais 0 supposé), sommés `None`-tolérants par `merged_with`. Champs additifs : une archive ou un JSON antérieur les lit `None`. Preuve : `tests/adapters/test_cache_reasoning_tokens.py::test_usage_sums_the_parts_and_keeps_none`, `tests/app/test_cache_tokens_archive.py`.

> Tri-état : `[x]` fait **+ preuve** · `[ ]` à faire · `[~]` différé/réserve + raison.
> Mise à jour dans le **même commit** que le code (règle d'or anti-dérive).
> **Statut couche 1 : ✅ vert** (vérifié 2026-05-31).

- [x] 13 fichiers dans `cinoc/domain/` ; `facts.py`/`module_protocol.py` **non** migrés. — *preuve : `ls cinoc/domain` ; `test_no_legacy_imports` (tokens `Fact`/`BaseModule` absents)*
- [x] `ArtifactType.LAYOUT` et `Artifact.region_id` présents. — *preuve : `cinoc/domain/artifacts.py:55,138`*
- [x] Contrat de module **reporté à la couche 4** (pas un livrable couche 1). — *preuve : `module_protocol.py` absent de `domain/`*
- [x] Aucune occurrence de `PicaronesError`/`BaseModule`/`Fact`/`LEGACY_VALUE_ALIASES`/`pipeline_names`/`BACKLOG_POST_LIVRAISON`. — *preuve : `tests/architecture/test_no_legacy_imports.py` vert*
- [x] Aucune annotation de sprint résiduelle. — *preuve : `grep -rE "Sprint|Phase [0-9]" cinoc/domain` vide*
- [x] `mypy --strict` vert sur `domain`. — *preuve : `mypy --strict -p cinoc.domain` → Success*
- [x] `ruff check` vert. — *preuve : `ruff check cinoc/` → All checks passed*
- [x] Tests domain + architecture verts. — *preuve : `pytest` 163 passed / 95 % cov*
- [x] Import sans effet de bord. — *preuve : `tests/architecture/test_no_side_effect_imports.py` vert*
- [~] **Réserve partiellement levée (T1)** : `MetricSpec`/`EvaluationView`/`EvaluationSpec` ont un consommateur (registre + runner couche 3) → **confirmés, gardés**. `ProjectionSpec` reste **sans consommateur** → différé à T2 (projections). — *cf. journal D-009.*
- [~] **Différé-par-design** : backlog domain (`RunSpec`/`ProjectionReport`/`ConfidenceToken`), `CanonicalLayout`. — *anti-spéculatif : créés à la tranche de leur 1ᵉʳ consommateur (§9).*
- [x] **Retraits sans consommateur** (S29b, D-303) : `ArtifactType.CANONICAL_DOCUMENT`, `READING_ORDER` (l'ordre de lecture vit dans `LayoutPage.reading_order`) et `ALIGNMENT` — réservés, jamais produits ni lus ; `Deadline.as_sdk_timeout` (les adaptateurs passent `request_timeout(deadline)`) ; `ProjectionSpec.is_identity`. — *preuve : `grep` sans autre occurrence que la définition ; suite verte*

---

## 9. Risques & points ouverts

- **Suppression des alias `TEXT/ALTO/PAGE`** : touche ~25 call-sites hors couche 1.
  La couche 1 peut être migrée sans attendre ; les call-sites seront corrigés
  lors du portage des couches consommatrices.
- **`RunSpec`** : vit aujourd'hui en couche 6 (`app/schemas/`). L'architecture cible
  le rapatrie dans `domain` (frère de `PipelineSpec`/`EvaluationSpec`). **Hors
  périmètre de ce plan** — à créer au moment de la couche 6, en séparant du loader YAML.
- **Backlog domain** : `ProjectionReport` (couche 3), `RunSpec` (couche 6),
  `ConfidenceToken` (différable) sont des types qui appartiennent à `domain` mais
  ne sont **pas** créés ici (anti-spéculatif : pas de consommateur en couche 1).
  Liste et critère d'appartenance dans `CLAUDE.md`.
- **`RunContext`** : ne PAS le placer en `domain`. Il fait paire avec `RunControl`
  (threading, couche 4) et c'est l'argument de `execute()` → **couche 4**. Noté
  ici pour éviter une future tentation de rapatriement.
