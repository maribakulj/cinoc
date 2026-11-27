# Synthèse de conception : cinq contrats à remplacer (contre-expertise `04a1c17b`)

Ce document fait suite à `README.md`, `CONVENTIONS.md`, `BIBLIOTHEQUES.md` et `rapports/*.md` de ce dossier. Il ne corrige rien et n'écrit aucun code. Il ramène les 90 défauts confirmés (51 `valide`, 39 `discutable`) à cinq contrats fautifs. Pour chacun, il donne le contrat qui le remplace, les invariants qui jugeront la correction, l'ordre des corrections et la liste fermée de ce qui reste à arbitrer.

**Règles suivies** (consigne du mainteneur) :
- chaque cause remplace un contrat **existant**, en place ; aucune couche, aucun paquet, aucun plan nouveau ;
- bilan de lignes visé faible ou négatif ;
- bibliothèque mature d'abord ;
- tests avant correctifs ;
- une tranche est finie quand ses **invariants** sont établis, pas quand un compte de tests passe au vert.

---

## 1. Causes communes

### 1.1 Les cinq contrats

| # | Contrat fautif (actuel) | Pourquoi il produit plusieurs symptômes | Arbitrages servis | Tests V / D |
|---|---|---|---|---|
| **K1** | **L'observation est un ratio, pas des comptes.** `Observation(value, weight)` (`evaluation/metric.py:22`), agrégée par Σv·w/Σw (`runner.py:307-327` → `inference.py:166` `micro_ratio`) ; IC par pipeline sur les couples (v, w) (`inference.py:182-271`) ; `_error_rate` 0/1 sur dénominateur nul (`metrics/text.py:114`). | Aucun poids ne reconstruit un F1. Un dénominateur nul perd son numérateur (page blanche). Un plancher par page n'est pas un plancher du corpus. Rien ne vérifie que le poids est le dénominateur (τ). Tests et IC ne voient que des ratios, donc aucun Δ micro apparié, aucune grappe. **14 métriques sur 29** sont fausses pour cette seule raison. | **2**, **1** (micro/macro, apparié, grappes) | V 9 · D 10 (C01, C02×3, C03, C04, C05×2, C06 `ic_apparie`, C09) |
| **K2** | **La non-mesure n'a ni statut ni motif, et « attendu » dérive de l'échec d'exécution.** `MetricScore.value=None` (`evaluation/result.py:31-46`) ; `missed` incrémenté dans la seule branche `failed` (`runner.py:146-160`) ; `None` sans motif à cinq endroits (`_context_for` `runner.py:519-538`, `_project_side` `:555-575`, `region_cer` `metrics/layout.py:92`, fan-out `pipeline/fanout.py:230-235`, `EntityCategoryScore.support ≥ 1` `analysis.py:960`) ; support implicite et différent pour l'agrégat, l'IC et le test (`_aggregate`, `_intervals`, `omnibus_test` `inference.py:116-122`) ; `max_error` déduit de `higher_is_better` (`runner.py:409`). | `None` code six situations distinctes. Une unité réussie mais inexploitable sort des deux compteurs. Un pipeline non applicable vide les tests des autres. Un échec non aléatoire fait gagner. La valeur imputée à un échec dépend du signe de la métrique, pas de sa définition. | **3**, **8**, **1** (même support) | V 8 · D 6 (C06 `meme_documents`, C07, C08×2, C13×2) |
| **K3** | **L'étape n'est pas l'unité d'enregistrement.** L'issue est portée par l'unité (`DocumentExecution`, `pipeline/types.py:73-142`, avec « `failed` ⇒ aucun artefact » `:96-99` et `billed` qui remplace toute la consommation `:111-112`). L'exécuteur laisse sortir l'exception avec `by_step` (`executor.py:119-151`) et l'orchestrateur reconstruit un échec nu (`orchestrator.py:333-347`). Le workspace est par pipeline, pas par étape (`orchestrator.py:233-243` → `adapters/_workspace.py:23-28`). L'usage est par unité (`DocumentUsage`, `result.py:82`). La reprise est par unité (`resume.py:130`). Les analyses lisent le pool final (`runner.py:131-138`). | Un même manque, la coordonnée « étape », efface ensemble les artefacts, le coût, l'évaluabilité et la reprise de l'amont réussi. Il fait écraser le fichier d'une étape par une autre (même label), juger `correction`/`decisions` sur la dernière étape, et facturer le pipeline entier à une vue de préfixe. | **4**, **8** (opérationnel), **7** (provenance par unité) | V 13 · D 5 (C12×3, C18×2) |
| **K4** | **L'identité est déclarée, jamais calculée ni vérifiée ; le cache tient lieu d'archive.** `Artifact.content_hash` n'est relu nulle part (`resume.py:296-301`, `:316-324`, `representations.py:37`) ; l'empreinte d'étape hache une `version` saisie à la main (`pipeline/fingerprint.py:72`, engagement `:18`) ; `GroundTruthRef` n'a pas d'empreinte (`domain/documents.py:22-32`) ; le manifeste ne garde que `corpus_name`/`n_documents` (`domain/run.py:90-91`) ; l'empreinte d'image est calculée puis jetée (`resume.py:150-172`) ; `ResumeStore` porte « deux rôles pour un seul mécanisme » (`resume.py:205-219`) ; `_rebased` laisse passer les chemins absolus et suit les liens (`:187-200`) ; la relecture hors ligne télécharge (`orchestrator.py:246-268`). | Ce qui se déclare au lieu de se calculer ne se vérifie pas. Une sortie altérée, un index modifié, une GT remplacée ou une brique corrigée sans nouvelle version passent sans trace, et une reprise réécrit l'archive publiée. | **5**, **7**, **4** (intégrité des sorties) | V 9 · D 9 (C14×4, C15×3, C17×2) |
| **K5** | **La correspondance est une égalité de clé, pas un alignement global.** `correspondance` « id d'abord, en bloc » (`metrics/layout.py:232-265`, `:256`) et `_ordres` (`:372-392`) ; glouton dans l'ordre du fichier (`_greedy_pairs` `:172-195`) ; pages aplaties (`_detection_boxes` `:145`, `_identified_boxes` `:202`, `_region_texts` `:49`) ; deux projections `LAYOUT → texte` (`evaluation/projectors.py:30-67` contre `adapters/layout/to_text.py:31-86`) ; fan-out à image unique (`fanout.py:67,101`) ; calibration par multi-ensemble de mots (`calibration.py:126`). | Un id partagé (`r1…rN` des segmenteurs de Cinoc, `region_N` synthétisés), un mot répété ou une position dans le fichier tiennent lieu de preuve d'homologie. Le résultat dépend de l'ordre de sérialisation et de conventions de numérotation, et il apparie entre pages. | **6** | V 12 · D 5 (C10×2, C11×2, C16) |
| — | Hors contrat : **plan d'expérience** (aucun type « comparaison », `provenance_campagne.md`). | Décision de méthode, pas de code. | (C19) | D 4 (C19) |

Totaux : V 9 + 8 + 13 + 9 + 12 = **51** ; D 10 + 6 + 5 + 9 + 5 + 4 = **39**.

### 1.2 Recoupements : les arbitrages ne sont pas des causes

| Arbitrage | K1 | K2 | K3 | K4 | K5 | Lecture |
|---|---|---|---|---|---|---|
| 1 Estimandes, tests appariés, grappes | ● | ◐ | | | | Le micro et le Δ apparié sont des fonctions des comptes (K1). « Même support » est une règle de statut (K2). |
| 2 Statistiques suffisantes, finalisation | ● | | | | | |
| 3 Non-mesure typée | ○ | ● | ○ | | | x/0 est une non-validité (K1 la fait apparaître). « Étape amont en échec » est une non-exécution (K3 la fournit). |
| 4 Par étape, isolation, intégrité | | | ● | ◐ | | L'isolation est un dossier par étape (K3). L'intégrité est l'empreinte vérifiée (K4). |
| 5 Archive scellée ≠ cache | | | ○ | ● | | L'archive scelle des enregistrements d'étape (K3). |
| 6 Appariement par page, géométrie, méthodes globales | ○ | | | | ● | Les comptes de détection (tp, fp, fn, fusions, scissions) sont des comptes K1. |
| 7 Empreintes automatiques, identité des données, distant inconnu | | | ◐ | ● | | La provenance par unité vient de K3, l'empreinte calculée de K4. |
| 8 Conditionnel, couverture, support commun, opérationnel ; pas de `max_error` universel | ○ | ● | ◐ | | | Couverture et support : K2. Coût de préfixe : K3. Valeur « page vide » : celle que la métrique calcule sur ses comptes (K1). |

● = cause principale ; ◐ = contribue ; ○ = fournit un ingrédient.

Ainsi, **3 et 8 n'appellent aucun contrat propre** : ce sont K1 + K2. **4, 5 et 7** se partagent l'enregistrement d'étape (K3) et son empreinte vérifiée (K4) : un seul objet, `StepRecord`, est produit, adressé, vérifié et archivé.

Tests à cheval sur deux causes :
- `a5_*` : K3 (même fichier pour deux étapes) puis K4 (empreinte jamais relue) ;
- C01 : K1 (numérateur perdu) et K2 (statut « référence vide ») ;
- C12 `la_reprise` : K3 (préfixe) et K4 (clé) ;
- C18 : K3 (par unité) et K4 (servi ou inconnu) ;
- NER label absent : K2 (catégorie sans GT = rappel indéfini) et K1 (comptes).

### 1.3 Défauts hors des cinq contrats (pour mémoire)

| Défaut | Rattachement |
|---|---|
| SIGINT : `ThreadPoolExecutor.__exit__` attend la file ; des unités sont payées mais non archivées | invariant §12 « annulation coopérative » violé ; traité en tranche 3 (archivage par étape à la fin de chaque étape), voir N9 |
| saknussemm : délai codé en dur, unité `ok` alors que toutes ses lignes sont en repli | réglage opérationnel déclaré (K4) + issue `partial` (K2/K3) |
| `dependencies_lock` = métadonnées d'installation (`pytesseract` y figure encore) | K4 (empreinte `RECORD` par distribution) |
| Ligne de layout avec des `\n` (fan-out → saknussemm) | corrigé dans `aba0fe7`, gelé (arbitrage 9) |

---

## 2. Contrats simplifiés

Pseudo-signatures (pas du code). « Supprime » vise des symboles de la copie `04a1c17b`. Les lignes sont des **ordres de grandeur (±50 %)**, mesurés sur l'étendue des fonctions visées.

### K1 — Comptes additifs et finalisation par métrique

```
Counts = Mapping[str, int]                       # statistiques suffisantes, clés fixées par la métrique
DocumentMetric(spec, fn: DocContext -> Counts | None, finalize: Counts -> float | None)
  valeur page  = finalize(counts_d)
  micro corpus = finalize(Σ_d counts_d)          # même fonction : page et corpus
  macro corpus = moyenne des finalize(counts_d) définies
finaliseurs partagés : ratio(num, den) · f1(tp, fp, fn) · exactitude(err, n) = max(0, 1 − err/n)
MetricScore(par doc) : + counts            MetricScore(agrégat) : value = micro, + macro, + n_macro
InferencePayload     : + estimand ∈ {micro, macro}, + delta, + IC apparié du Δ ; le Wilcoxon/Friedman y est étiqueté « macro »
Δ micro apparié      = scipy.stats.bootstrap(paired=True) / permutation_test(permutation_type="samples")
                       sur les tableaux de comptes (documents triés par id) ; grappes = mêmes appels sur les comptes sommés par grappe
```

| | |
|---|---|
| **Supprime ou fusionne** | `Observation` ; `micro_ratio`, `micro_ratio_ci`, `bootstrap_batch`, `_intervals` (`inference.py`, ~75 l.) ; `_aggregate` (21) ; `_error_rate` (5) ; F1 par document dans `ner.py`, `bow.py` et `layout.py` (~15) ; les 29 `return Observation(…)` deviennent des `return {…}` (réécrits, sans gain de lignes). **≈ −120 / +85, net ≈ −35** (dont `runner.py`, à 598/600 LOC, qui doit baisser). |
| **Bibliothèques** | `scipy.stats` (déjà là) ; `rapidfuzz.editops` (déjà là) pour S/D/I. Oracles en `dev` : jiwer (CER/WER/MER), nervaluate (NER micro), scipy. Rejetés : méthode delta (fausse d'un facteur 4 sur Simpson), jiwer en production. |
| **Couche** | `evaluation` (3) seulement. `MetricSpec` (domain) ne change pas : le calcul reste hors domain. |
| **Ne fait pas** | Pas de bornes ni de « pire valeur » déclarées dans `MetricSpec` (aucun consommateur, puisque K2 n'impute plus rien par défaut). Pas de registre d'estimandes. Pas de rééchantillonnage maison. Aucune nouvelle métrique. |

### K2 — Statut typé, couverture, support commun

```
MeasureStatus = Literal["measured",       # valeur définie
                        "not_applicable", # applicabilité : pas de GT du type, métrique hors vue — hors des attendus
                        "unavailable",    # disponibilité : GT illisible, sortie absente / sans contenu / incompatible
                        "undefined",      # validité : x/0 (référence vide), niveau absent de l'hypothèse
                        "not_executed"]   # exécution : étape cible ou amont en échec, annulée
MetricScore : + status, + reason (code)   # validateur : value is None ⇔ status ≠ "measured" ; reason ⇔ status ≠ "measured"
attendus(pipeline, métrique)  = #{d : status_d ≠ not_applicable}        # indépendant de l'issue d'exécution
couverture                    = n measured / n attendus
support_commun(vue, métrique) = ∩ des documents measured des pipelines comparés (un seul calcul : tableau comparé, Δ, test)
FailurePolicy = Literal["exclude", "empty_page"]   # max_error retiré ; empty_page = sensibilité nommée, valeur = finalize(fn(réf, hypothèse vide))
UnitOutcome  += "partial"                          # sous-appels en échec (régions d'un fan-out, lignes en repli)
validation avant exécution : GT et image lisibles et hachées, pont de projection présent pour chaque (vue × pipeline)
```

| | |
|---|---|
| **Supprime ou fusionne** | `missed` et la branche `failed` d'`evaluate_run` (~15) ; `_expects` fondu dans `attendus` ; règle `worst` et `_score_failed` réduits au cas `empty_page` (~43 → 12) ; motif faux `insufficient_support` quand un pipeline est hors vue ; `support ≥ 1` d'`EntityCategoryScore`. **≈ −60 / +75, net ≈ +15.** |
| **Bibliothèques** | Aucune (rien de mature : ∞, 0, −1 ou `zero_division` selon l'outil). Méthode de fairlearn `MetricFrame` pour le conditionnel par strate : même finalisation sur des comptes groupés, ~0 ligne de plus. |
| **Couche** | `MeasureStatus` en `evaluation/result.py` (3) : seuls l'évaluation et les rapports s'en servent (voir N6). `partial` en `domain/usage.py`, où vit déjà `UnitOutcome`. Validation préalable en `app` (6). |
| **Ne fait pas** | Pas d'imputation par défaut. Pas quatre champs d'axe : une seule énumération dont chaque valeur nomme un axe. Pas de courbes risque-couverture. Pas de fairlearn. |

### K3 — Enregistrement par étape

```
StepRecord(step_id, outcome ∈ {ok, truncated, partial, failed}, reason, message,
           artifacts: Mapping[ArtifactType, Artifact], usage: ResourceUsage,
           served_models: tuple[str, ...] | None,   # None = non rendu par le fournisseur (« inconnu » pour un module distant)
           fingerprint, prefix_key)
DocumentExecution(steps: tuple[StepRecord, ...])   # issue, usage et pool déduits ; un échec = le dernier record, l'amont reste
RunContext.workspace_uri = <ws>/<pipeline>/<step_id>/   # isolation physique sans changer la signature d'un adaptateur
DocumentUsage : + steps: tuple[StepUsage(step_id, outcome, reason, usage, served_models, code_version)]
prefix_key(k) = H(prefix_key(k−1), step_fingerprint(step_k), empreintes des unit_inputs de l'étape k) ;  prefix_key(0) = H(document_id, image_sha256)
correction / decisions / economics : (vue, étape notée, étape d'entrée déclarée par inputs_from), jamais le pool
```

| | |
|---|---|
| **Supprime ou fusionne** | `billed`, `DocumentExecution.failed`, invariant « échec ⇒ pas d'artefact » (~35) ; reconstruction de l'échec dans l'orchestrateur (~20) ; `pools` (8) et `_two_stage_pipelines`/`_text_of` sur le pool (~20) ; `unit_key` (45) remplacé par `prefix_key` ; saut `if not entries: continue` d'`economics` ; `RunManifest.served_models` stocké (devient dérivé des records). **≈ −135 / +115, net ≈ −20.** |
| **Bibliothèques** | Stdlib. Modèle de données de Provenance Run Crate (une `ControlAction` par étape, `actionStatus`, `error`) comme **forme de référence**, sans dépendance. |
| **Couche** | `StepRecord` en `pipeline` (4), à la place de `DocumentExecution`. Clés en `app` (6). Consommateurs en `evaluation` (3). |
| **Ne fait pas** | Pas d'ordonnanceur ni de DAG. Pas de reprise à l'intérieur d'une étape (région). Pas de record « sautée » : l'absence suffit, lue `not_executed` par K2. Pas de coût par région. |

### K4 — Identité calculée et vérifiée ; cache et archive séparés

```
Artifact.content_hash : obligatoire dès qu'une uri existe ; calculé par l'exécuteur, jamais déclaré par le module
read_verified(artifact) -> bytes        # point de lecture unique (évaluation, cache, archive) ; écart => CorruptedArtifactError
BlobStore(racine) : put(fichier) -> sha256 (écriture atomique, lecture seule, lien dur si même FS) ; get(sha) -> chemin vérifié
Cache   = BlobStore + index mutable {prefix_key: StepRecord}                    # réécrit, retenté
Archive = bag BagIt scellé : data/objects/<sha>, data/ground_truth/<sha>, data/spec.json, data/run_result.json
          relecture = bagit.Bag(p).validate() + refus de tout lien (lstat) + refus de fetch.txt ; jamais réécrite ;
          identité d'unité lue dans les records archivés (empreinte d'image), sans le corpus ni le réseau
GroundTruthRef.content_sha256, DocumentRef.image_sha256   # remplis au chargement (= la validation préalable de K2)
RunManifest.corpus : CorpusSpec avec empreintes           # remplace corpus_name / n_documents
ModuleIdentity : version, settings effectifs (prompt, température, max_tokens envoyés), binaries,
                 library {distribution: version, sha256 du RECORD}, weights_revision, source_sha256
```

| | |
|---|---|
| **Supprime ou fusionne** | `_rebased` (14) ; `_store_image` (~22, remplacé par le `BlobStore`) ; `binaries.json` et `record_binaries`/`recorded_binaries` (~35 : les binaires sont dans chaque record) ; rôle d'archive du `ResumeStore` et validation structurelle de `load` (~30) ; téléchargement hors ligne (~10). **≈ −110 / +170, net ≈ +60.** Archive, vérification et empreinte des sources sont des capacités nouvelles. **+60** si RO-Crate (H6). |
| **Bibliothèques** | `bagit` (LoC, un fichier, 0 dépendance, domaine public) pour valider et écrire (H1). `hashlib`, `importlib.metadata` (`RECORD`). Méthode du cache DVC/git (adressage par contenu, lecture seule, liens durs). Méthode joblib/Snakemake pour l'empreinte des sources (~40 l.). |
| **Couche** | Champs d'empreinte en `domain` (1 : ce sont des types purs, des références et non du contenu). Identité en `pipeline` (4). `BlobStore` et archive en `app` (6), ce qui bute sur la liste blanche de `app` (H1). |
| **Ne fait pas** | Pas d'OCFL (versions), pas de signature. Pas de `fetch.txt` dans une archive scellée. Pas de `rfc8785` tant que seul Cinoc recalcule. Pas de W3C PROV. Octets d'image facultatifs (licence) : l'empreinte suffit à re-noter. RO-Crate seulement si H6. |

### K5 — Appariement global par page, projection unique

```
apparier(réf, hyp, seuil) -> paires      # linear_sum_assignment sur l'IoU seuillée, page par page ;
                                         # ex æquo départagés par id commun, puis par ordre géométrique canonique
DetectionCounts(tp, fp, fn, fusions, scissions)   # comptes K1 ; fusions/scissions par IoGT/IoDT ≥ 0,5 (méthode PRImA / ocrd-segment-evaluate)
region_cer, reading_order_*, line_identity_* : mêmes paires, par page ; τ = Σ discordantes / Σ paires (C03-A)
formats.layout_text(layout) : seule projection LAYOUT → texte, qui respecte reading_order imbriqué ; séparateur unique ;
                              utilisée par evaluation.projectors ET adapters.layout.to_text
fan-out : refus typé d'un layout multipage accompagné d'une seule image (C16-C)
calibration : jeton juste ⇔ bloc « equal » d'un alignement de séquences (rapidfuzz opcodes), si C11-B
```

| | |
|---|---|
| **Supprime ou fusionne** | `_greedy_pairs`, `_true_positives` (26) ; `correspondance` « id d'abord » et `_ids_partages` (44) ; branche « id » de `_ordres` (~10) ; `_detection_boxes` et `_identified_boxes` fusionnés (−17) ; `_region_texts` global (7) ; deux projections (`projectors.py` 34 + `to_text.py` 52) remplacées par une seule ; `_judge` par multi-ensemble (12). **≈ −200 / +80, net ≈ −120** (+30 si fusions/scissions, N7). |
| **Bibliothèques** | `scipy.optimize.linear_sum_assignment` (déjà importé par `metrics/flexible.py:50`). IoU des boîtes : les 6 lignes maison restent. Rejetés : `pycocotools` (glouton par score), `shapely` (H2). |
| **Couche** | Appariement en `evaluation` (3). Projection en `formats` (2), seule couche que l'évaluation (3) et les adaptateurs (5) peuvent importer tous deux (précédent : `formats/_region_ids.py`). Refus de fan-out en `pipeline` (4). |
| **Ne fait pas** | Pas d'IoU polygonale. Pas de profils pondérés PRImA par scénario. Pas d'espace de noms d'identifiants : l'id n'est jamais primaire en 1.0 (N8). Pas d'alignement par ligne pour la calibration (il demanderait une position dans `ConfidenceToken`). |

### Bilan net estimé (code produit)

| K1 | K2 | K3 | K4 | K5 | **Total** |
|---|---|---|---|---|---|
| −35 | +15 | −20 | +60 | −120 | **≈ −100** (≈ −10 avec RO-Crate et fusions/scissions) |

Les tests de propriété ajoutés (~300 lignes de test) ne comptent pas. Les tests existants qui figent un défaut sont supprimés ou inversés dans le commit du correctif (§ 4.2).

---

## 3. Invariants

Vérification :
- **P** = test de propriété. `hypothesis` est la bonne réutilisation : il réduit le contre-exemple au minimum. Il serait ajouté à l'extra `dev` seulement, avec un profil déterministe en `tests/conftest.py` (`derandomize=True`, `database=None`, `deadline=None`, `max_examples` borné pour `check-fast`). Les tests vivraient à côté de leur couche (`tests/evaluation/test_proprietes_*.py`…), sans arbre nouveau.
- **O** = oracle externe.
- **A** = test adversarial ciblé.

« Manquant » = aucun test adversarial ne le couvre encore : il faut l'écrire **avant** la correction.

### Scientifiques

| # | Invariant | Vérification | Subsume |
|---|---|---|---|
| S1 | Pour toute métrique enregistrée, l'agrégat micro vaut `finalize(Σ comptes)`, et la valeur page vaut `finalize(comptes page)` avec la même fonction. Un corpus d'un seul document a pour agrégat la valeur de ce document. | P sur les 29 métriques du registre ; O jiwer (CER/WER/MER), nervaluate (micro-F1 NER), calcul à la main (F1 régions, τ par paires, exactitudes) | `reference_vide[cer, wer, ins_rate]`, `ner_f1×2`, `ner_f1…sans_entite`, `region_detection`, `bow_f1`, C02×3, C03 ; verts `taux_additifs…jiwer`, `preservation…` |
| S2 | Toute grandeur publiée (agrégat, IC, p) est **invariante par permutation de l'ordre des documents** dans la spec. | P | **Manquant, et violé aujourd'hui.** Vérifié hors test : sur 8 documents, inverser leur ordre fait passer l'IC de `micro_ratio_ci` de [0,0953 ; 0,7596] à [0,1032 ; 0,7403], parce que le tirage suit l'ordre de la spec. Correctif dans K1 : trier par id avant de rééchantillonner. |
| S3 | Les métriques de structure sont invariantes par permutation des régions de référence et d'hypothèse, et par renommage des ids sans filiation démontrée. L'appariement se fait à l'intérieur de chaque page. | P (permutations et renommages aléatoires) ; O `linear_sum_assignment` | C10×2, `ordre_des_regions_de_reference`, `egalite_d_iou`, `ids_identiques_non_homologues`, `ids_partiellement_partages`, `alto_sans_id`, `multipage×3` |
| S4 | **Monotonie face à l'invention.** Ajouter à l'hypothèse du texte, des entités, des régions ou des lignes sans vis-à-vis dans la référence ne rend jamais une métrique meilleure, ni au document ni au corpus. Un pipeline qui invente sur une page blanche est classé derrière un pipeline muet. | P (ajouts aléatoires, toutes métriques) | `reference_vide*`, `pipeline_qui_hallucine`, `ner…faux_positifs`, C04 (sous C04-A) ; vert `metriques_a_denominateur_hypothese` ; **manquant** : région fantôme sur une région de référence sans texte (`layout.py:116`) |
| S5 | Le test et l'IC publiés portent **sur l'estimande affiché et sur le même support** : le micro va avec la permutation ou le bootstrap apparié des comptes, le macro avec Wilcoxon/Friedman. Le payload nomme l'estimande et le sens du Δ. Le support du test est celui du Δ. | O `scipy.stats.permutation_test` et `bootstrap` ; A Simpson | C05×2, C06×2, C01 `nentre_pas` |
| S6 | Toute comparaison se fait sur le support commun. Chaque agrégat est publié conditionnel, avec sa couverture. Aucun classement ne met en regard des agrégats de supports différents. Rien n'est imputé par défaut. La sensibilité « page vide » vaut `finalize(fn(réf, hypothèse vide))` et porte ce nom. | A | C07, C08×2, `max_error…deplace_lagregat` |
| S7 | Avec des grappes déclarées, l'IC rééchantillonne des grappes : les mêmes pages groupées de deux façons donnent deux IC ; groupées en singletons, l'IC par grappe égale l'IC par document ; sous le seuil, l'IC est « non estimable ». | P (singletons) ; A | C09 |
| S8 | **n attendus** = nombre de documents dont la VT applicable existe, indépendamment de l'issue d'exécution et de la sortie ; n mesurés ≤ n attendus. Toute non-mesure a un statut de `MeasureStatus` ≠ `measured` et un motif, et jamais un `None` nu (validateur). | P (pannes aléatoires par unité et par étape) ; A | `artefact_sans_contenu`, `artefact…absent_du_disque`, `fanout_entierement_en_echec`, `sortie_incompatible`, `reference_vide_nest_pas_comptee` (T1), `ner_payload…label_absent`, C13×2 ; **manquants** : troncature d'une étape aval sous une vue amont complète, unité saknussemm en repli total |
| S9 | Ajouter un pipeline au run ne change ni les agrégats, ni les IC, ni les p brutes des autres paires. Seule change la taille de la famille de Holm, qui est publiée. | P | `pipeline_non_applicable…` (cas particulier) ; **manquant** dans sa forme générale |
| S10 | La valeur d'une vue, analyses comprises (correction, décisions, économie), ne dépend que de la sortie de son étape cible, de l'entrée déclarée de cette étape et de la VT. | A | `correction×3`, `decisions×2`, C12 `economie`, `a5…chaque_vue_notee` |
| S11 | La sortie d'une étape ne dépend que de ses entrées (empreintes) et de son identité : sources, bibliothèque enveloppée, réglages effectifs envoyés, révision des poids, binaires. Changer l'une d'elles change l'empreinte ; changer la version du paquet ou un réglage opérationnel ne la change pas. | A (reformulés, § 4.1) | C17×2, `saknussemm…version_de_la_bibliotheque`, `poids_du_scoreur_qe` ; verts `digest_ollama`, `reprise_autres_binaires` |
| S12 | Changer un octet d'une image ou d'une VT change l'empreinte du corpus publiée dans le `RunResult`. Re-noter contre une autre VT est signalé. | A ; P (octet aléatoire) | `identite_gt×4`, `identite_image` |
| S13 | Relire une archive vérifiée redonne **exactement** les mêmes comptes et le même `RunResult`, hors horodatages. | P (aller-retour) | `a5_relecture_offline` ; vert `a7_temoin_relecture_intacte` |
| S14 | Une archive altérée est refusée avant toute note : octet d'une sortie, d'un index, d'une image, d'une VT ou de la spec, lien symbolique, chemin absolu, `fetch.txt`. | O `bagit.Bag.validate` ; A | C14 (3 sur 4), `a7_uri_absolue`, `a7_lien_symbolique`, `a5_archive__empreinte` |
| S15 | Provenance attribuée par unité et par étape : modèle servi, ou « inconnu » pour un module distant qui ne le rend pas ; `code_version` et dépendances de production. Aucune union n'est présentée comme l'attribut d'une unité. | A | C18×2 ; **manquant** : module distant qui ne rend pas le modèle servi |
| S16 | Une seule projection `LAYOUT → texte`. Un candidat identique à la référence a un CER nul sous toute vue, ordre imbriqué compris. | P (layouts imbriqués aléatoires) | `deux_projections×3`, `ordre_de_lecture_imbrique` |

### Fonctionnels

| # | Invariant | Vérification | Subsume |
|---|---|---|---|
| F1 | **Isolation physique.** Deux étapes d'une unité ne partagent jamais un fichier, et `sha256(fichier) = content_hash` à l'écriture comme à chaque lecture. | A ; garde dans l'exécuteur | `a5×5` (dont le socle Tesseract → redressement) |
| F2 | **Conservation de l'amont réussi.** Un échec à l'étape k garde les artefacts, coûts, issues et l'évaluabilité des étapes avant k. La facture de l'étape fautive est comptée, et un pipeline tout en échec garde la sienne. | A | `echec_partiel×5` (V + C12) ; **inverse** le vert `le_type_interdit_bien_les_artefacts_dune_unite_failed` ; **manquant** : chemin annulation et délai |
| F3 | **Reprise par préfixe.** Une reprise n'exécute que les étapes dont la clé de préfixe est absente ou en échec. | A ; P (nombre d'appels = étapes manquantes) | C12 `la_reprise` |
| F4 | La relecture d'une archive ne télécharge rien et ne lit pas le corpus d'origine. Une unité archivée intacte n'est jamais déclarée `failed` pour une cause extérieure à l'archive. | A (réseau déjà refusé par `tests/conftest.py`, D-303) | C15×3 |
| F5 | Une reprise n'écrit jamais dans une archive scellée. Deux archives qui mutualisent un blob par lien dur restent valides chacune. | A ; O `bagit` | C14 `archive_publiee` ; **manquant** : mutualisation (essayée dans `libs-try`, absente de la suite) |
| F6 | **Refus avant de payer.** Une VT ou une image référencée illisible, une vue sans pont de projection pour un pipeline, un layout multipage à image unique en fan-out : tous sont refusés avant le premier appel de moteur. | A | C13 `gt…avant_de_payer`, `sortie_incompatible`, C16 |
| F7 | **Parité** : chaque capacité nouvelle (sceller et vérifier une archive) est une fonction `app`, avec ses faces déclarées dans `test_web_cli_parity`. | garde existante (tables) | **manquant** : entrées de table à ajouter, rouges d'abord |

**23 invariants** (16 scientifiques, 7 fonctionnels).

---

## 4. Tests à reformuler, à inverser, à écrire

### 4.1 Reformulations (avant toute correction)

Ce sont le test valide touché par la tension T1 et les 8 tests discutables dont l'attendu change sous l'arbitrage.

| Test | Conv. | Attendu reformulé (une phrase) |
|---|---|---|
| `applicabilite…::reference_vide_nest_pas_comptee_notee` (**valide**) | T1 | Le micro de A vaut 12/120 = 0,100 (pages blanches au numérateur) ; 12 documents contribuent au micro et 6 au macro, et les 6 pages blanches portent `undefined/empty_reference`. |
| `test_omnibus__meme_sens_que_le_cer_micro_affiche` | C05 | Le test publié pour l'estimande micro va dans le sens du Δ micro ou n'est pas significatif (ici p = 1). Le Wilcoxon, s'il est publié, est étiqueté « macro (effet par document) » et va dans le sens du macro. |
| `test_omnibus__p_du_ratio_micro_par_permutation_appariee` | C05 | La p corrigée du test **micro** est ≥ α et égale à la permutation exacte de scipy (1,0) ; l'assertion ne lit plus le champ du Wilcoxon. |
| `intervalles__meme_documents_que_le_test` | C06 | L'IC apparié du Δ porte exactement sur les cas complets du test (mêmes ids). Les IC marginaux peuvent garder leur support propre, étiquetés « conditionnels », avec leur couverture. |
| `echec_non_aleatoire__classement_sur_documents_communs` | C07 | Sur le support commun, B (0,040) est devant A (0,050). Aucun classement ne met A devant B à partir d'agrégats de supports différents, et la couverture 7/8 de A est publiée. |
| `max_error__un_echec_ne_note_jamais_mieux_quune_reponse` | C08 | Aucune règle n'impute une « erreur maximale ». Par défaut l'échec n'est pas noté (couverture 2/3). Sous la sensibilité « page vide », il vaut la valeur que la métrique donne à une hypothèse vide (CER 1,0), sous ce nom. |
| `bootstrap__grappes_documentaires_declarables` | C09 | Test de comportement, et non plus de noms de champ : la même liste de pages groupée de deux façons donne deux IC ; groupée en singletons, l'IC égale l'IC par document. |
| `version_manuelle__brique_modifiee_sans_relever_sa_version_reexecutee` | C17 | Deux modules de **sources** différentes, de même nom et de même version déclarée, donnent deux empreintes d'étape, donc le second est exécuté. La correction n'est plus simulée par un attribut d'instance. |
| `identite_saknussemm__prompt_et_temperature_envoyes_au_llm_sont_traces` | C17 | L'empreinte change quand le prompt ou la température effectivement envoyés changent, et ne change pas pour un réglage opérationnel. On teste un comportement, pas des noms de clés. |

### 4.2 Tests existants qui figent un défaut

Ils sont à inverser ou supprimer **dans le commit du correctif** (rupture nette, §5.1).

| Test | Défaut figé | Tranche |
|---|---|---|
| `tests/evaluation/test_metrics_text.py::test_cer_weight_is_reference_length` | page blanche hors du micro | 1 |
| `tests/evaluation/test_micro_interval.py::test_zero_weight_documents_weigh_nothing` | idem pour l'IC | 1 |
| `tests/app/test_unit_outcome.py::test_max_error_is_zero_for_a_higher_is_better_metric`, `::test_max_error_scores_the_failure_like_an_empty_page` | `max_error` déduit du signe ; la seconde devient le test de la sensibilité `empty_page` | 2 |
| `tests/adversarial/applicabilite_echecs/…::le_type_interdit_bien_les_artefacts_dune_unite_failed` (vert) | « échec ⇒ aucun artefact » | 3 |
| `tests/evaluation/test_appariement_geometrique.py::test_identifiants_partages_inchanges` | id prioritaire « pour que rien ne bouge » | 5 |
| `tests/evaluation/test_calibration.py::test_analysis_scores_tokens_against_reference_multiset` | multi-ensemble (D-068), si C11-B | 5 |

Restent valides : `test_code_version_change_keeps_the_cache` (la version du paquet reste hors de l'empreinte, S11) ; `test_omnibus_drops_incomplete_documents` ; `test_a_failing_region_does_not_abort_the_page`, à compléter par le statut `partial`.

### 4.3 Tests adversariaux manquants (à écrire rouges d'abord)

S2 (ordre des documents) · S4 (région fantôme sur une référence sans texte) · S8 (troncature aval sous une vue amont ; saknussemm en repli total) · S9 (ajout d'un pipeline, forme générale) · S15 (distant sans modèle servi) · F2 (annulation et délai) · F5 (mutualisation par lien dur) · F7 (entrées de parité). Les tests de propriété P de S1, S3, S4, S8, S13, S16 et F3 sont à écrire en même temps.

---

## 5. Ordre des tranches

Chaque tranche ne dépend que des précédentes. Le premier commit d'une tranche ne contient que des tests (reformulés, manquants, propriétés), et ils doivent être rouges pour la bonne raison. La tranche 5 ne dépend que des tranches 1 et 2 : elle peut être avancée.

| Tranche | Invariants visés | Tests prérequis (rouges) | Contrats touchés | Suppressions | Critère de fin |
|---|---|---|---|---|---|
| **1 · Comptes** (K1) | S1, S2, S4 (texte, NER), S5, S7 | T1, C05×2, C09 reformulés ; P de S1/S2/S4 ; C01-C04 et C06 `ic_apparie` existants | `Observation` → `Counts` + `finalize` ; `MetricScore` (+ counts, macro) ; `InferencePayload` (+ estimande, Δ, IC apparié) | `Observation`, `micro_ratio(_ci)`, `_intervals`, `_error_rate` ; § 4.2 tranche 1 | S1 établi sur les 29 métriques contre les oracles ; S2/S5/S7 établis. **Prévisions vérifiées** en re-notant les deux `RunResult` commités depuis leur archive : CER/WER micro BNL et Dresden **inchangés** (aucune page blanche), `char_accuracy` Dresden E5 de 0,3125 à 0,000, Δ apparié E5−E0 BNL [−0,041 ; −0,010]. |
| **2 · Statut et support** (K2) | S6, S8, S9, F6 | C07, C08, C06 `meme_documents` reformulés ; tests manquants S8/S9 | `MeasureStatus` + motif ; attendus ; support commun ; `FailurePolicy` (`empty_page`) ; `UnitOutcome.partial` ; validation avant exécution | `missed`, règle `worst`, `max_error` ; § 4.2 tranche 2 | S6/S8/S9/F6 établis. Dresden E5 publié 1,8614 « conditionnel 4/10 », comparé à E0 sur le seul support commun. Amendement CLAUDE.md §3 « niveau absent » (N1) dans le même commit. |
| **3 · Étape** (K3) | S10, S15, F1 (isolation), F2, F3 | C12×3 (fixture `economie` réécrite avec un usage par étape), C18×2 ; `a5×5`, correction et décisions existants ; F2 annulation | `StepRecord`, `DocumentExecution`, workspace par étape, `DocumentUsage.steps`, `prefix_key`, entrées des analyses | `billed`, `failed()`, `pools`, `unit_key`, `_two_stage_pipelines`, `served_models` stocké ; § 4.2 tranche 3 | S10/S15/F1/F2/F3 établis. Socle `tesseract → deskew → tesseract` : chaque vue garde sa lecture (CER ≈ 0,015 avant redressement). |
| **4 · Identité et archive** (K4) | S11, S12, S13, S14, F1 (empreinte), F4, F5, F7 | C14×4 reciblés sur le lecteur d'archive, C15×3, C17×2 reformulés ; S15 distant ; F5 ; F7 | `content_hash` calculé + `read_verified` ; `BlobStore` ; archive BagIt ; empreintes GT et image ; `ModuleIdentity` enrichie | `_rebased`, `_store_image`, `binaries.json`, rôle d'archive du `ResumeStore`, téléchargement hors ligne | S11-S14/F4/F5/F7 établis. Une archive de campagne scellée est validée par `bagit` et re-notée hors ligne, réseau et corpus retirés, à l'identique (S13). |
| **5 · Correspondance** (K5) | S3, S16 (+ S1 pour la détection) | C10×2, C11×2 (si tranché), C16 ; P de S3/S16 ; 12 valides existants | `apparier` (hongrois, par page), `DetectionCounts`, `formats.layout_text`, refus de fan-out, alignement de calibration | `_greedy_pairs`, `correspondance` « id d'abord », `_ids_partages`, une des deux projections ; § 4.2 tranche 5 | S3/S16 établis par propriété et contre `linear_sum_assignment`. CER par région E1/E3/E4 re-notés. |

---

## 6. Ce qui reste à arbitrer (liste fermée)

### 6.1 Conventions ouvertes (4)

| | Question | Recommandation |
|---|---|---|
| C04 | Lignes fantômes dans `line_identity_cer` | A : insertions comptées, cohérent avec D-288 et S4 |
| C11 | Jugement d'un jeton pour la calibration | B : alignement LCS, ou C avec un départage « maximiser les correspondances » déclaré |
| C16 | Layout multipage avec une seule image en fan-out | C : refus typé en 1.0 (F6) ; A (une image par page) ensuite |
| C19 | Plan d'expérience de la campagne | Témoin `seg → tesseract:reco → lecture → mistral:correction` obligatoire ; `max_tokens` : aligner (A) ou montrer sur S31 qu'il ne limite pas (C) |

### 6.2 Conventions tranchées en partie (6)

| | Choix résiduel | Recommandation |
|---|---|---|
| C01 | Page blanche dans le macro et le test par document | A : incluse au micro et à son test apparié, statut `undefined`, exclue du macro et du Wilcoxon |
| C02 | Plancher des exactitudes | A : plancher au corpus ; macro publié à part |
| C03 | Statistique nommée τ | A : Σ discordantes / Σ paires ; macro à part ; la mesure par bloc sous un autre nom |
| C09 | Méthode des grappes et seuil | B : bootstrap par grappe ; « non estimable » sous un seuil **à chiffrer** (BNL : 5 grappes, dont un singleton) |
| C17 | Empreinte des sources contre réglages déclarés | B + D (sources + réglages effectifs, version de bibliothèque, révision des poids), garde CI en filet pour le first-party (voir N3) |
| C18 | Provenance par unité | A : attribution par unité ; l'union devient un résumé dérivé |

### 6.3 Heurts avec `CLAUDE.md` (BIBLIOTHEQUES.md § 3)

| | Heurt | Recommandation |
|---|---|---|
| H1 | `bagit` hors de la liste blanche `app` ; `rfc8785` hors de `pipeline` | Ajouter `bagit` en base et à `LAYERS["app"]` : un fichier, 0 dépendance, et c'est ce que la consigne demande de réutiliser. Pas de `rfc8785` tant que seul Cinoc recalcule les empreintes. |
| H2 | IoU polygonale (`shapely`) contre liste blanche et déterminisme | Rester en boîtes (aucun consommateur ne demande de polygones), limite écrite. Jamais en extra avec repli : la métrique dépendrait du paquet installé. |
| H3 | Tirages scipy dépendants de la version | Accepter « mêmes octets à versions égales » (c'est déjà le cas du rééchantillonneur numpy actuel, NEP 19) ; le manifeste trace scipy et numpy ; ordre canonique des documents (S2). |
| H4 | « Aucun téléchargement » contre D-094 (images par référence IIIF) | Empreinte d'image obligatoire, octets facultatifs selon la licence. La re-notation n'a besoin que des empreintes, donc aucun trou ni `fetch.txt`. La réexécution reste hors du rôle de l'archive. |
| H5 | Parité web/CLI pour les capacités d'archive | Une fonction `app` par capacité. Le scellement devient une option d'une commande existante (`cinoc run`), et la vérification est implicite à chaque relecture `--offline`. Aucun verbe nouveau ; route web `front-absent` déclarée. |
| H6 | Provenance Run Crate complet contre « pas de consommateur » | BagIt maintenant. Le descripteur RO-Crate (Process Run Crate, plus une `ControlAction` par `StepRecord`) n'est écrit que si un dépôt (Zenodo, HF) est nommé comme consommateur à la publication. |
| H7 | `rng=` absent avant scipy 1.15 | Relever le plancher à `scipy>=1.15` (disponible sur 3.11). |
| H8 | `roc-validator` résout le contexte JSON-LD par le réseau | Sans objet si H6 est différé ; sinon contexte local dans le job `oracle`. |

### 6.4 Questions nouvelles nées de cette synthèse

| | Question | Recommandation |
|---|---|---|
| N1 | CLAUDE.md §3 « niveau absent → métrique non applicable (`None`) » contredit K2 | Amender : niveau absent de la **VT** → `not_applicable` ; niveau absent de l'**hypothèse** → `undefined`, ou texte vide noté, plus `partial`. |
| N2 | `RunResult` v6 : `support` par document cède la place à `counts`, alors que les clés sont un « contrat dur » (§12) | Clés conservées, champs additifs. Un JSON antérieur portant `inference` est refusé et re-noté depuis son archive (précédent v4 → v5). |
| N3 | Empreinte des sources : dans la clé de cache, ou seulement enregistrée + garde CI (tension T5) ? | Dans la clé, restreinte à la fermeture du module dans `cinoc.adapters` ou au `RECORD` d'un plugin installé ; fermeture complète enregistrée ; installation éditable signalée « empreinte non garantie ». Coût : une modification d'adaptateur fait réexécuter ses unités. |
| N4 | Famille de Holm et pipelines identiques page à page (E1/E3/E4 : Friedman 0,029 contre 0,051) | Fusionner, sous déclaration, les pipelines aux sorties identiques (mêmes empreintes) avant de former la famille. |
| N5 | Ordre canonique des documents pour le rééchantillonnage (S2) | Tri par id de document. |
| N6 | `MeasureStatus` en `domain` (BIBLIOTHEQUES) ou en `evaluation` | `evaluation` : aucun consommateur hors des couches 3 et 7. |
| N7 | Fusions et scissions (arbitrage 6 « examiner ») : comptes publiés en 1.0 ? | Oui, comme comptes de détection (~30 l.), sans profils pondérés. |
| N8 | Quand un id prouve-t-il la filiation ? | Jamais en 1.0 : il ne sert qu'à départager. Un lien d'empreinte vers la VT ne sera ajouté que pour un consommateur réel (reconnaissance sur segmentation VT). |
| N9 | SIGINT (invariant §12 violé, hors des neuf arbitrages) | Le traiter en tranche 3 : archiver chaque `StepRecord` dès la fin de son étape (reprend l'idée du correctif gelé, arbitrage 9), et arrêter la file à l'annulation. |
| N10 | Archives S30/S31 au format `ResumeStore` | Script ponctuel de conversion **hors produit** (`campaigns/`, supprimé après usage) plutôt qu'un shim, ou réexécution des parties gratuites. |
| N11 | Séparateur de blocs de la projection unique (K5) | `\n`, celui de la couche 5, qui a produit les sorties de campagne. |
| N12 | `hypothesis` en extra `dev` | Oui, avec un profil déterministe (§ 3). |
