# Plan de migration — Couche 3 (`evaluation/`) : Picarones → Cinoc

> Statut : **plan acté**, implémentation à venir. Lecture seule du code Picarones.
> Ce document fige les **contrats transverses** (enveloppe) ; le **remplissage**
> suit des tranches verticales (cf. §2). Aligné sur `CLAUDE.md` (deux axes,
> tranches, narrative supprimé, `CanonicalLayout` différé).

---

## 1. Objectif & périmètre

La couche 3 calcule des **métriques** sur les sorties des pipelines (OCR/HTR/VLM,
OCR+LLM) face à une vérité-terrain, et produit un **`RunResult`** sérialisable +
les données du rapport. **Migration complète** (pas un MVP réduit) : on conserve
toutes les vraies métriques ; on ne supprime que le **mort / doublon / mal placé**.

Dépend des couches mergées : **domain** (`ArtifactType` dont `LAYOUT`, `Artifact`,
`EvaluationView`/`MetricSpec`/`EvaluationSpec`, `RunManifest`, `Corpus`/`Document`)
et **formats** (ALTO/PAGE riches, `_geometry`, `text/normalization`).

Ne fait **ni I/O, ni rendu, ni exécution de moteur** : ce qui violerait ça sort
vers `adapters/` / `reports/` / `pipeline/`.

---

## 2. Principe directeur — deux axes, tranches verticales

Rappel `CLAUDE.md` §2/§4. **Deux axes strictement séparés** :

| Axe | Quand | Ici |
|---|---|---|
| **Enveloppe** (contrats, types pivots, points d'extension) | **Dimensionnée plein-scope, maintenant** | registre type-driven, `RunResult`, deux formes de métriques, `Protocol Section` du rapport, slot `ArtifactType.LAYOUT` |
| **Surface** (métriques, sections, importeurs) | **Incrémentale, minimale, élaguée** | une métrique/section à la fois, dans un budget |

**Tranches verticales** (≠ « finir la couche 3 horizontalement ») : couches 1-2
faites horizontalement (stables) ; couche 3+ par **squelettes ambulants** fins de
pleine profondeur. La **première tranche** prouve que l'enveloppe tient avant d'y
verser des features.

**Cas particulier du rapport (cadre vs contenu)** : le **cadre** conceptuel
(`Protocol Section` unique, consommation directe du `RunResult`, un seul format)
est conçu **plein-scope dès maintenant** ; le **contenu** (nombre de sections,
visualisations) grossit **au rythme des métriques** qui l'alimentent. Construire
toutes les sections d'avance = bâtir du rapport **en avance sur ses données** =
l'accrétion qui a alourdi Picarones. Le HTML basique du squelette **n'est pas
jetable** : c'est la première section vraie, sur le cadre définitif.

---

## 3. Noyau verrouillé (enveloppe, plein-scope maintenant)

1. **Registre unique type-driven.** Suppression des 4 systèmes parallèles de
   Picarones (hooks `①`, registre module-level `③`, `@register_lever` `④`) ;
   reste le **registre instanciable** (`②`), sélection **100 % par `input_types`**.
2. **Deux formes de métriques** : **par-document** `(ref, hyp)` et **inter-moteurs**
   `(EngineReports)`. Agrégation par-moteur **générique** (scalaires) +
   **agrégateur custom co-localisé pour les structs** (dict — pas un cas rare).
3. **`DocContext` / `CrossEngineContext`** : sac d'entrées **extensible** par forme.
4. **Fiche + fonction co-localisées** ; **décorateur pur** (construit un `Metric`,
   ne mute aucun global) + **collecte explicite par sous-paquet**.
5. **Sécurité scientifique obligatoire** (dette C) : `safe_ratio`/`safe_mean`
   (rendent `None` sur vide) ; agrégation **exclut `None`** + **expose le *support***.
6. **`scipy` en dépendance dure** (Wilcoxon/Friedman/OLS validés).
7. **`shapely` confiné** (`evaluation/geometry.py`), invoqué **seulement pour les
   polygones**, **dégradable** (`backend="shapely"` → repli bbox + warning).
   **Ajouté avec la tranche structure** (§10), pas maintenant.
8. **Persistance** : `schema_version` sur le **document `RunResult`** (rapport/compare)
   + **store longitudinal en lignes *tidy*** (additif). Complémentaires (§8).
9. **Déterminisme bit-à-bit** ; **clés de sortie stables** (renommer un fichier =
   libre ; renommer une clé de métrique = interdit, contrat dur avec rapports/JS).

---

## 4. Première tranche = squelette ambulant (axe texte)

Le premier pas n'est **pas** le `CanonicalLayout` — c'est un **squelette fin de
pleine profondeur** sur l'axe texte (`CLAUDE.md` §4) :

```
corpus pré-calculé (texte) → 1 CER → RunResult → HTML basique (1 section) → CLI `demo`
```

Il **exerce l'enveloppe complète** (registre, `RunResult`, runner, `Protocol Section`)
avec **une seule métrique scalaire** (CER). Aucun `CanonicalLayout`, aucun shapely,
aucune structure. Objectif : prouver que les contrats s'emboîtent de bout en bout.
Puis on **épaissit l'axe texte** (WER/MER, profils, stats scipy, cross_engine,
compare) avant d'ouvrir l'axe structure.

---

## 5. Le registre (contrat — enveloppe)

- **`domain/evaluation.py:MetricSpec`** = contrat de type **minimal** (`name`,
  `input_types`, `description`, `higher_is_better`) — déjà présent.
- **La couche 3 enrichit** (métadonnées opérationnelles, hors domain) : `level`/forme,
  `profiles`, `tags`, `requires`, `backend`, `unit`, `cost_hint`, `spec_version` —
  **chacune avec un lecteur nommé**. Co-localisée avec la fonction.
- **Signatures** : `fn(ctx: DocContext) -> …` et `fn(ctx: CrossEngineContext) -> …`.
  Séparation **garantie par les signatures**, pas par une police AST.
- **Profils** (`profiles.py`) : liste nommée **ou** sélecteur de tags simple
  (`rapide`, `avancé`, …). Pas d'algèbre. Vocabulaire de tags petit et validé.

---

## 6. Le runner (deux passes)

`evaluation/runner.py` (+ logique de calcul **rapatriée** de `app/services/_benchmark_*` —
l'app *appelle*, ne *calcule* plus) :
1. **Par-document** : `select(input_types)` → `DocumentMetric` sur `DocContext` ;
   `None` = non applicable (skip).
2. **Agrégation par-moteur** : générique (scalaires) + **custom (structs)** ;
   `None` exclu ; **support** calculé.
3. **Inter-moteurs** : `CrossEngineMetric` sur `CrossEngineContext` → **écrit dans `RunResult`**.

---

## 7. Défenses (sécurité scientifique, dette C)

Couches : `input_types` (gratuit) · `safe_*` (vide → `None`) · préconditions
`requires` (le runner saute) · **test générique** d'entrées dégénérées · **golden**
sur fixtures réelles **ALTO + PAGE + texte** · agrégation `None`-exclu + support ·
revue. Risque **présent dès l'axe texte** (ratios sur vide) → `safe_*` jour 1 ;
amplifié à l'axe structure (mélange ALTO/PAGE).

---

## 8. Résultat & persistance

- **`evaluation/result.py:RunResult`** (ex-`benchmark_result`, dégonflé) = contrat
  de sortie unique, **dimensionné plein-scope** (porte taxonomy/NER/structure dès
  sa conception, même si la 1ʳᵉ tranche n'écrit qu'un CER), avec **`schema_version`** + upcaster.
- **cross_engine écrit dans le `RunResult`** ; le rapport ne fait que lire.
- **Store longitudinal *tidy*** (lignes `(run, moteur, métrique, valeur, spec_version)`),
  en `adapters/storage` (I/O hors couche 3). Ajout de métrique = additif.
- **Réconciliation note couche 2** : « le jeu de champs fait foi » = même esprit que
  le tidy pour les **ajouts** ; `schema_version` couvre les **changements structurels**
  du document. Ne pas laisser « pas de version » déborder sur le document `RunResult`.
- **Rapport interactif (what-if) — QUESTION OUVERTE, à trancher à sa tranche (tardive)** :
  un rapport **filtrable** (ex. « exclure les docs hallucinés » → recalculer les agrégats)
  est une feature **tardive, sans consommateur aujourd'hui** → on **ne fige pas son mécanisme
  ici** (`CLAUDE.md` §9 : ne pas figer une forme avant son consommateur). Constat utile :
  `RunResult` **porte déjà les résultats par-doc** (`RunDocumentResult`) → **aucun changement
  d'enveloppe forcé maintenant**. Deux mécanismes à départager **à la tranche** :
  **(a, recommandé)** le **runner pré-calcule** les agrégats des états what-if pertinents
  (p. ex. via des `EvaluationView` dédiées) → le rapport **sélectionne**, ne calcule jamais
  (invariant « le rapport ne recalcule jamais » respecté à la lettre ; marche pour générique
  *et* custom) ; **(b)** ré-agrégation côté client sur les valeurs par-doc (continu, mais 2ᵉ
  implémentation à golden-tester, limitée aux agrégateurs simples). *(Soulevé par
  `reports/ANALYSE_COUCHE_7.md` §2.7 ; décision au build, pas ici.)*

---

## 9. Le rapport — cadre plein-scope, contenu incrémental

- **Cadre (maintenant)** : un **`Protocol Section` typé unique**, consommant le
  `RunResult` **directement** (pas de data-layer qui ré-agrège — anti-pattern
  Picarones), un seul format, budgets.
- **Contenu (incrémental)** : 1 section au squelette (overview/engines/CER) ;
  on **ajoute des sections à côté** au rythme des métriques (documents, crosses,
  structure…). Jamais de section en avance sur sa donnée.
- **Pas de `reports/narrative/`** (supprimé, `CLAUDE.md` §6) : chiffres et tableaux
  bruts, aucune prose générée.
- **Interactivité (what-if) = sélection, jamais re-mesure** (cf. §8, **question ouverte**) :
  si un rapport filtrable est construit (tranche tardive), il **sélectionne** une vue/projection
  ou ré-agrège un sous-ensemble — **jamais** une re-mesure côté client ; l'**inférentiel**
  (Wilcoxon/IC) reste gelé sur le corpus complet. **Mécanisme tranché à sa tranche**
  (candidat = projections pré-calculées par le runner).

---

## 10. `CanonicalLayout` & axe structure — ENVELOPPE, matérialisés à la 1ʳᵉ tranche structure

**Différé, par discipline** (`CLAUDE.md` §3/§6) — *pas le premier pas*.

- **Réservé maintenant (enveloppe)** : `ArtifactType.LAYOUT` existe + `region_id`
  optionnel sur `Artifact`. Le registre (générique sur les types) et le `RunResult`
  (générique sur les métriques) **accueillent déjà** une métrique `(LAYOUT, LAYOUT)`
  dès que des artefacts `LAYOUT` existeront — **sans** connaître les champs du type.
- **Matérialisé plus tard** : le **type concret** `CanonicalLayout` (en `domain`)
  + les **mappers** `alto/page → layout` (formats) + le projecteur `layout → text`
  + les **métriques structurelles** (`region_detection`, `line_detection`,
  `reading_order`, `geometry_coverage`) + **shapely** — tout ça naît à la
  **première tranche *structure***.
- **Déclencheur = la première tranche structure**, qui peut être l'**évaluation
  structurelle** (couche 3 : mappers + métriques, sur des sorties ALTO/PAGE de
  n'importe quel pipeline) **ou** la **segmentation** (couche 4), selon laquelle on
  construit en premier. Le type **vit en `domain`** dans les deux cas ; « couche 4 »
  est un raccourci pour « la tranche où son premier consommateur apparaît ».
- **Pourquoi pas maintenant** : un type sans consommateur = code mort + champs figés
  **avant** son consommateur = spéculatif (garde-fou *« pas de consommateur =
  supprimé »*). Le différer est **plus sûr**, pas moins.

**Esquisse cible** (à *confirmer* avec le consommateur, **ne pas figer maintenant**) :
sur-ensemble fidèle des types couche 2 — `Geometry{bbox?, polygon?, baseline?}`,
`Word` optionnel (+ hyphénation), `Line{text, words?, geometry?}`,
`Region{region_type?, kind(text|generic), regions(imbrication)}`, `ReadingOrder`
**en arbre** (mappe le PAGE ; ALTO = groupe plat = ordre des blocs), `LayoutPage`,
`CanonicalLayout{pages, source_format}` + `has_word_level`. **Bonne nouvelle couche 2** :
l'ALTO de Cinoc porte déjà `baseline` + `block_type` → métriques structurelles
applicables sur ALTO aussi (pas systématiquement `None`).

---

## 11. Inventaire source → cible (Picarones `evaluation/`, 93 fichiers)

**Supprimés** — 4 registres + plomberie (`metric_hooks`, `builtin_hooks`,
`builtin_metrics`, `metric_registry`, 4×`*_hooks`), doublon (`search`), morts
(`equivalence_profile`, `alto_metrics`, `cost_projection`, `ner_backends`,
`difficulty`, `module_policy`), `normalization` (consolidé en `formats/text`),
**`levers`** (4ᵉ registre, synthèse type-narrative → **abandonné**, narrative supprimé).
⚠️ Supprimer une métrique n'est pas local : nettoyer ses références côté reports/JS/CSV
(ex. clé `difficulty_score`).

**Changés de couche** — `history` (SQLite) → `adapters/storage` ; `cdd_render` (SVG),
`worst_lines` → `reports` ; ré-exécution moteur de `robustness` → `pipeline`.

**Modifiés** — renommages (`benchmark_result`→`result`, `evaluation_engine`→`runner`,
`_diff_utils`→`diff`), splits >400 LOC (`modern_archives`, `roman_numerals`,
`numerical_sequences`, `inter_engine`), structure réécrite sur `LAYOUT`
(`layout`→`region_detection`, `reading_order`, `alto_structural`→`geometry_coverage`),
dédoublonnage (`searchability` absorbe `search`), `reliability`→`multirun_stability`.

**Gardés** — noyau métier (CER/WER, philologie, inter-moteurs, économie, image,
longitudinal) ; **clés de sortie inchangées**.

**Nouveaux** — `profiles.py`, `metrics/_helpers.py` (`safe_*`) [axe texte] ;
`geometry.py`, `structure/region_detection.py`, `structure/line_detection.py`,
`projectors/layout.py`, `gt_types.py` [tranche structure].

**Organisation cible** : `metrics/{text, philology/, structure/, cross_engine/,
economics/, image/, longitudinal/}`, `statistics/`, `views/`, `projectors/`.

---

## 12. Risques de transfert Picarones → Cinoc

1. `reading_order` sans source (Picarones) → **résolu couche 2** (arbre `ReadingOrder`
   côté PAGE ; ALTO = ordre de bloc → groupe plat dans le mapper).
2. **Agrégateurs custom** (confusion/taxonomie/calibration) — pas des moyennes (§6).
3. **Clés de sortie = contrat dur** avec reports/JS/compare.
4. `benchmark_result`→`RunResult` : ~30 consommateurs — beaucoup meurent (shim,
   workflows), migrer reports + web + compare **en bloc**.
5. Consolidation `normalization` : **sans danger** (l'eval n'en définissait aucun).

---

## 13. Explicitement laissé au codage (sous test)

Intérieur des métriques ; contenu des profils + vocabulaire de tags ; liste des
métriques structurelles PAGE-natives ; découpes des fichiers >400 LOC ; coutures
(pré-passe stats corpus → `DocContext` pour `rare_tokens` ; alimentation historique
→ longitudinal/`baseline_comparison`) ; champs concrets du `CanonicalLayout` (§10).

---

## 14. Tests & budgets

- **Architecture** : étendre la whitelist `evaluation/` (**+scipy** ; **+rapidfuzz**
  (T7) ; **+numpy/PIL** (4d.1 — numpy maths garanti via scipy, PIL décodage extra
  `[images]`) ; **+shapely/jiwer au fil des tranches qui les introduisent**) ;
  `no-side-effect-import` (décorateur = valeur pure) ; `file-budgets`.
- **Golden** : `RunResult` canonique ; **ALTO+PAGE+texte** à la tranche structure ;
  déterminisme bit-à-bit.
- **Sécurité** : test générique d'entrées dégénérées ; CER/WER vs `jiwer` ;
  round-trip de fidélité format→`LAYOUT` (à la tranche structure).

---

## 15. Ordre d'implémentation (tranches verticales)

1. **Squelette texte** : corpus pré-calculé → CER → `RunResult` (plein-scope) →
   HTML basique (1 section, cadre `Protocol Section`) → CLI `demo`. Registre +
   `DocContext` + `runner` (1 métrique) + `safe_*`.
2. **Épaissir l'axe texte** : WER/MER + portage du noyau texte (clés stables),
   `profiles`, statistiques (**scipy**), `cross_engine` (écriture `RunResult`), `compare`.
3. **Tranche structure** : `CanonicalLayout` (domain) + mappers `alto/page→layout`
   + projecteur `layout→text` + **shapely**/`geometry.py` + `region_detection`/
   `line_detection`/`reading_order`/`geometry_coverage` + golden ALTO/PAGE.
4. **Store longitudinal *tidy*** (via `adapters/storage`) + reste des métriques
   (philologie, économie, image, longitudinal) — une par une, en budget.

---

## DoD vivante (couche 3) — **autorité de détail** ; le `MIGRATION_PLAN.md` indexe

> Tri-état : `[x]` fait **+ preuve** · `[ ]` à faire · `[~]` différé/réserve + raison.
> Maj dans le **même commit** que le code. **Statut : ✅ T2** — `RunResult` plein-scope + registre type-driven + runner verts ; **CER/WER/MER** (parité jiwer) + profils de normalisation + stats `scipy` + `cross_engine` **livrés**. **+ T5 structure** : `region_cer` `(LAYOUT,LAYOUT)` + **`region_detection`** (F1 IoU de boîte, coords relatives — neutralise mm10/px ; **sans shapely**) + loader `LAYOUT` (JSON/ALTO/PAGE) + **projecteur `layout_to_text`** avec **exécution `ProjectionSpec`** dans le runner (un LAYOUT noté par les métriques texte ; réserve §9 `ProjectionSpec` levée ; vrai benchmark BNL ABBYY-vs-Tesseract en test `live`, F1 détection 0.35@0.5). — *preuves : `tests/evaluation/test_projection.py`, `…/test_projection_real_bnl.py`, `…/test_region_detection.py`*. **+ T7 philologie `mufi_err`** (`metrics/philology.py`) : taux d'erreur sur les caractères MUFI/médiévaux (PUA + Latin Extended-D + `ſ`/`þ`/ligatures), même alignement `rapidfuzz` que `diacritic_err`, `None` si la réf n'en porte aucun ; ajouté au socle → registre = `cer, cer_diplo, del_rate, diacritic_err, ins_rate, mer, mufi_err, region_cer, region_detection, wer`. — *preuves : `tests/evaluation/test_metrics_philology.py`, `…/test_registry.py`*. Reste : IoU polygonal exact (shapely, si consommateur) ; familles riches (NER/taxonomy) additives.
>
> **T8 (D-066)** : `RunResult` **v2** — `+ usage: tuple[DocumentUsage, ...]` (ressources par pipeline × document, triées, hors vues) ; `schema_version=2`, un JSON v1 sans `usage` se recharge. Le **contrat « analyses »** (canal unique typé pour le non-scalaire, 3 règles dures) est gravé dans la docstring de `result.py` ; le champ est **né en T9** avec `inference` (D-067). Preuves : `tests/evaluation/test_result.py::{test_usage_channel_round_trips,test_v1_payload_without_usage_still_loads}`.
>
> **T9 (D-067)** : `+ inference.py` (Nemenyi post-hoc + bootstrap percentile, stdlib pur, plancher partagé `MIN_SUPPORT`) `+ analysis.py` (canal E2 : `Analysis` + `InferencePayload`) ; le runner produit une analyse par (vue × métrique) applicable, sur les mêmes séries que `significance_p`. Parité numérique prouvée contre la source Picarones. Preuves : `tests/evaluation/test_inference.py` · `test_runner.py::test_inference_analyses_through_evaluate_run`.
>
> **T10 (D-068)** : `+ economics.py` + `pricing.json` (donnée datée packagée) — coût machine+jetons depuis les mesures E1, débit effectif, coût marginal, `pareto_front` ; payload `economics` = 2ᵉ membre de l'union `analyses` (discriminateur `kind` activé). Tests **dérivés à la main** (règle PLAN_PARITE §5.8b). Preuves : `tests/evaluation/test_economics.py`.
>
> **T11 (D-069)** : `+ metrics/diagnostics.py` (`searchability`, `hallucination` — registre = 12 métriques, vue `text` par défaut enrichie) `+ diagnostics.py` (collecteur branché au scoring : confusions, pires lignes, documents difficiles → 3ᵉ payload `analyses`). Preuves : `tests/evaluation/test_diagnostics.py`.
>
> **T12 (D-070)** : `+ calibration.py` — ECE/MCE (Guo 2017) + bins depuis les sidecars `CONFIDENCES` ; payload `calibration` = 4ᵉ membre de l'union. ECE/MCE en payload, pas en scalaire (la calibration qualifie, ne classe pas). Preuves : `tests/evaluation/test_calibration.py` (dérivés à la main).
>
> **T13 (D-071)** : `+ taxonomy.py` — 8 classes par règles pures (priorité segmentation→case→diacritic→ligature→visual→résiduel), 5ᵉ payload `analyses` ; classes à données externes élaguées (hapax/oov/abréviations). Preuves : `tests/evaluation/test_taxonomy.py`.
>
> **4g.1 (D-115)** : conformité HIPE (SPEC_HIPE) — profils `hipe`/`heritage` (couche 2, levier `non_word_to_space`) · `+ metrics/conformity.py` (**`cmer`** = MER caractère via `rapidfuzz.editops`, micro natif par `Observation(weight=H+S+D+I)`) · `+ conformity.py` (**post-passe cross-vues** : lit les résultats des vues raw/hipe/heritage déjà calculés — zéro re-scoring) → **7ᵉ payload `hipe`** (micro/macro §4.1 + `delta_norm`/`delta_heritage` + `n_missing` exposé) · section `conformity` (noms du scorer à la frontière ; `mer` ≡ wMER, pas de clé jumelle) · export JSONL via `artifact_sink` (`cinoc run --hipe-jsonl`, R-1.8 : sortie absente → `""` + warning) · glossaire `cmer` FR/EN. Oracle : parité **comptes jiwer** à chaque CI + golden vendoré skip-gaté (extra dédié `hipe-oracle`, Python ≥ 3.12). `[~]` réserves : fixture golden à vendorer · matérialisation R-1.8 dans les métriques → 4g.2. Preuves : `tests/formats/text/test_hipe_profiles.py` · `tests/evaluation/{test_metrics_conformity,test_conformity,test_hipe_golden}.py` · `tests/reports/test_conformity_section.py` · `tests/app/test_hipe_export.py`.
>
> **4g.2 (D-116)** : bilan de correction — `prepare_text` extrait vers `representations` (une seule définition « préparé comme au scoring ») · `+ correction.py` : analyse **par vue** des pipelines **2 étages** (une extraction GT/brut/corrigé) → **8ᵉ payload `correction`** : triplet de non-régression (égalités strictes) + `pref` + catastrophique (Δ > 0.10) · pcis §4.2 (clamp à q_brut nul, macro + médiane + \|pcis\|>1) · CCR/change_ratio/length_ratio + `overedited` · `char_ins_ratio` + `hallucination_heavy` · **absorption** multiset (ex-4e) · **sur-normalisation** positionnelle (ex-4c — tue le bug de clés fantômes C7 par construction) · éditions consécutives (R-2.6) · pires régressions ; seuils portés par le payload. **R-1.8 levée** : étage absent matérialisé vide + warning + `n_missing_*` (la réserve 4g.1). Section `correction`. Mono-étage → payload absent (≠ zéro muet). `[~]` réserve : **procédure `hallucination`** — machinerie complète, exécution sur runs réels avant 1.0 (critères a/b, SPEC §8). Preuves : `tests/evaluation/test_correction.py` (témoin entièrement dérivé à la main) · `tests/reports/test_correction_section.py`.
>
> **4a (D-117)** : données structurées — `+ metrics/structured_data.py` (détecteurs conservateurs : années 1000-2099, foliotation recto/verso **distincts**, montants, régnal — *roman* → 4b, helper `_roman_to_int` minimal absorbé à 4b) · scalaires **`numseq_strict`/`numseq_value`** (lentilles forme exacte / équivalence, multiset, `value ≥ strict`, adaptatifs `None` sans signal), registre = 15 métriques (**retirés de la vue par défaut → opt-in, D-130** : adaptatifs = colonnes vides sur corpus sans séquences ; la section `structured_data` reste, elle, affichée car le collecteur est indépendant de `metric_names`) · `+ structured_data.py` (collecteur, pattern taxonomy) → **9ᵉ payload `structured_data`** (pipeline × catégorie présente, formes perdues cap 12) · section `structured_data` · glossaire FR/EN. **`readability`/Flesch abandonné — acté** (D-117 ; couvert par 4g.2 + `hcpr`/`air`). Preuves : `tests/evaluation/{test_metrics_structured_data,test_structured_data}.py` (valeurs main : « fol. 3r »→« fol 3r » = valeur sans forme) · `tests/reports/test_structured_data_section.py`.
>
> **4b.1 (D-118)** : philologie/abréviations — `+ markers.py` (moteur containment+expansion **multiset**, réutilisable par famille ; table Capelli/MUFI **11 signes** en constante, `ñ` exclu, combinants NFC) ; `MarkerCollector` (pattern taxonomy) → **10ᵉ payload `philology`** (pipeline × famille × signe : strict/expansion). **Réparation R3** : développements en **mot entier** (`\b…\b`, toutes longueurs — `per` ≠ « permettre »). **Payload-only** (pas de scalaire registre : éviterait une colonne `None` sur corpus modernes ; la section adaptative est le consommateur). Section `philology` (nouvelle). `[~]` ouvert : familles early_modern (positionnel) / modern_archives (containment, table YAML si budget) / **roman 5 statuts (R1)** / **`air` (net-new HIPE) + `hcpr`** — sous-tranches suivantes. Expansion = borne optimiste documentée. Preuves : `tests/evaluation/test_markers.py` (R3 + multiset, valeurs main) · `tests/reports/test_philology_section.py`.

> **4b.2 (D-119)** : philologie/imprimé ancien — `markers.py` gagne une **stratégie `positional`** (déclarée par `MarkerFamily.strategy`) à côté de `containment` : un marqueur est *préservé* si toutes ses positions GT tombent dans un opcode `equal` de `Levenshtein.opcodes` (cohérent CER). Famille `EARLY_MODERN` (**5 catégories** : ligatures / long_s / dotless_i / ampersand / nasal_tildes — caractères vérifiés source), graphies **pré-composées** seules, **NFC** avant détection (décomposé voyelle+U+0303 → pré-composé, compté pareil) ; `ñ` **inclus** ici (≠ famille scribale D-118). `MarkerCollector` dispatche par stratégie ; **payload `philology` réutilisé sans rupture** (`n_strict == n_expansion == n_préservé`, un seul score — documenté). Section `philology` **étendue** : bloc positionnel (colonne « préservé » + libellés catégories) distinct du bloc containment. **Payload-only** (pas de scalaire registre — `early_modern_pres` afficherait `None` sur corpus modernes). **Pas de branche morte** (seules 2 stratégies utilisées) ; **pas de glossaire** (aucun scalaire affiché). `[~]` reste ouvert : modern_archives / **roman (R1)** / **`air`+`hcpr`**. Preuves : `tests/evaluation/test_markers.py` (positionnel sub/NFC/per-catégorie + mix de stratégies, valeurs main) · `tests/reports/test_philology_section.py` (bloc positionnel).

> **4b.3 (D-120)** : philologie/archives modernes — nouveau module **`archives.py`** : 9 catégories (~70 marqueurs : civilité/ordinaux/monnaies/administratif/état civil/ponctuation typo/latin moderne/biblio/adresse) en **constantes de module**, détection **regex bornée** (frontière après point — `M.` ≠ `M.A.`, `arr.` ≠ « arracher » ; `\b` pour l'alnum ; littéral pour l'Unicode) + **greedy plus-long-gagne** (`S.A.R.` avant `S.`). `markers.py` gagne une **3ᵉ stratégie `archival`** déléguant à `archives.py` ; famille `MODERN_ARCHIVES` (`markers` = clés d'affichage = catégories). **Containment MULTISET** (`Σ min(occ. GT, occ. hyp)`) — divergence **assumée** de la source (présence-par-occurrence qui n'enregistrait pas un `Mme`→`Mlle`), aligné sur 4b.1. Payload `philology` **réutilisé** (par catégorie : strict/expansion). Section étendue : bloc containment **par catégorie** (en-tête « catégorie » + libellés). **Module séparé** = isole le regex + tient le budget (markers 336 / archives 260 LOC, < 600). **Payload-only**, **pas de glossaire**, **pas de branche morte** (3 stratégies utilisées). `[~]` reste ouvert : **roman (R1)** / **`air`+`hcpr`**. Preuves : `tests/evaluation/test_archives.py` (frontières/multiset/greedy/ordinaux, valeurs main + end-to-end) · `tests/reports/test_philology_section.py` (bloc archives).

> **4b.4 (D-121)** : philologie/numéraux romains — nouveau module **`roman.py`** : parseur soustractif **validé** (rejette `IL`/`IIIII`/`VV`, accepte `IIII` médiéval), `j` final (`viij`→`viii`), détection greedy + **classification 5 statuts** (`strict_preserved`/`case_changed`/`j_dropped`/`converted_to_arabic`/`lost`). `RomanNumeralsCollector` (pattern taxonomy) → **11ᵉ payload `roman` dédié** (≠ `philology` : le 5-statuts ne se mappe pas sur strict/expansion). Section `philology` étendue (bloc romain). **R1 FERMÉE** : romain compté **une seule fois** (ici) ; `numseq` sans catégorie roman depuis D-117 ; **helper régnal absorbé** — `metrics/structured_data.py` importe `roman.roman_to_int` (source unique). **R2** : `min_length=2`. Scores strict/valeur **dérivés** des statuts (pas de double comptage). **Payload-only**, **pas de glossaire**. **Budget** : `analysis.py` → 636 LOC (hub union discriminée) → entrée `test_file_budgets` justifiée (731). `[~]` reste ouvert : **`air`+`hcpr`** (dernier de 4b). Preuves : `tests/evaluation/test_roman.py` (parseur/5 statuts/R1 single-count/R2, valeurs main + end-to-end) · `tests/reports/test_philology_section.py` (bloc romain).

> **4c (D-123)** : fidélité textuelle (réduit) — `+ textual_fidelity.py` : fonctions pures (`tokenize` Unicode lowercasé · `corpus_frequencies`/`rare_tokens` ≤ 2 = hapax+dis legomena · `rare_recall_counts` multiset · `modernization_counts` via `difflib.SequenceMatcher(autojunk=False)`) + **`TextualFidelityCollector`** (pattern taxonomy, `observe(pipeline, doc_id, ref, hyp)`). **Résout la « pré-passe corpus »** : la rareté est corpus-wide → calculée à `build()` sur les GT collectées (dédupliquées par document), **après** la passe, zéro relecture, zéro mécanique runner. → **12ᵉ payload `textual_fidelity`** (par pipeline : `n_rare_reference`/`n_rare_recalled`/`rare_recall` (None si GT sans rare) + `missed` cap 20 ; `modernization` top 20 tokens réécrits, variantes cap 5, `∅`=supprimé). Section `textual_fidelity` (rappel rare + table de modernisation, prose pédagogique). **R6 — câblage homogène** : un seul canal (collecteur), zéro calcul en couche rapport (≠ Picarones `extra_metrics.py` orphelin). **Abandons actés** : `equivalence_profile` (C4 — couvert profils couche 2/D-089) · `searchability_hooks` (déjà livré T11, `missed_tokens` sans consommateur). `over_normalization` **déplacé en 4g.2** (déjà livré). **Payload-only**, **pas de scalaire** (tout est structure corpus-niveau ; un `rare_token_recall` par-doc exigerait le set rare avant la passe 1 — différé jusqu'à un consommateur historique/classement) → **pas de glossaire** (précédent 4b ; pédagogie en prose ; la note provisoire §4c « + rare_token_recall » écartée : entrée orpheline sans scalaire). Pur stdlib (re/difflib/Counter). Preuves : `tests/evaluation/test_textual_fidelity.py` (rareté/recall multiset/modernisation + collecteur end-to-end, valeurs main : corpus 3 docs `le`2/`roi`3/`charles`2/`louis`1/`est`1) · `tests/reports/test_textual_fidelity_section.py`.

> **4b.5 (D-122)** : philologie/archaïsmes `air`+`hcpr` — **4b TERMINÉE**. Premier de 4b à porter des **scalaires au registre** (≠ payload-only 4b.1-4b.4) : `air`/`hcpr` rejoignent `mufi_err`/`diacritic_err` en colonnes `by_engine` (avec glossaire FR/EN). `+ preservation.py` : **moteur partagé** `preservation_counts` factorisé hors `mufi_err`/`diacritic_err` (refactorés sans changer de valeur — **parité bit-à-bit** par `test_preservation` + les tests pinnés existants). `+ archaic.py` : listes nommées **package-data** (`ARCHAIC_LISTS`, défaut `archaic_core` Q4 trans-langue : `ſ ꝛ ⁊ ꝑ ꝓ ꝗ ꝙ ꝯ ꝝ ꝫ ꝭ þ ð ȝ` + marque suscrite `U+0364` pour `aͤ/oͤ/uͤ` ; `œ æ ß ç`/accents modernes **exclus** — langue-relatifs), **empreinte SHA-256** déterministe, `resolve_archaic_list` fail-closed. **`air`** (apport net, *plus bas = mieux*) = part des archaïsmes de la **sortie** insérés (position non couverte par un opcode `equal`) ; **dénominateur tranché = occurrences de la liste dans la sortie** → borné [0,1], `None` si la sortie n'en porte aucun ; **actif par défaut** (vue `text`, registre = 16 métriques). **`hcpr`** (préservation, *plus haut = mieux*) = `(n_total−n_wrong)/n_total` sur le moteur partagé ; **visible seulement sur liste configurée** (`archaic_list` → `plan_benchmark_run` ajoute la colonne + l'orchestrateur relie la métrique sur `metadata["archaic_list"]`) — **anti-colonne-jumelle** de `mufi_err` (sans config : `air` seul, pas de `hcpr`). **Reproductibilité** : nom + empreinte de la liste au `RunManifest.metadata` (toujours pour `air`) + au rapport. **Pipelines 2 étages** : `air`/`hcpr` notent le candidat aval (`CORRECTED_TEXT` préféré) — la sur-historicisation du correcteur est captée là où elle se produit. Démo : `pero` rend « Froiſſart » (ſ inséré) où la GT écrit « Froissart » → `air` réel non nul. **Pas de payload** (scalaires) → `analysis.py` intact. `[~]` reste au build : listes curées additionnelles (`archaic_de`…) **livrées avec leur consommateur** (enveloppe `ARCHAIC_LISTS` prête, surface = `archaic_core` seul, axe 2). Preuves : `tests/evaluation/{test_archaic,test_preservation}.py` (air/hcpr/empreinte, valeurs main + parité) · `tests/app/{test_run_planning,test_orchestrator}.py` (opt-in hcpr, liaison, manifeste) · `tests/reports/test_by_engine_section.py` (colonnes air/hcpr) · `tests/reports/test_glossary.py`.

> **4e.1 (D-124)** : inter-moteurs — `+ inter_engine.py` : **`jensen_shannon_divergence`** en **bits** (`math.log2` stdlib, lissage ε=1e-12, `M=(P+Q)/2`, clamp [0,1]) + **`InterEngineCollector`** (pattern taxonomy ; `observe` ne retient que des `Counter` de tokens — **`tokenize` de `textual_fidelity` réutilisé**, une seule définition de token dans la couche). (1) **Complémentarité/oracle** : `oracle_recall` = bag-of-words **multiset** `Σ_token max_moteur(min(occ. GT, occ. moteur)) / Σ occ. GT` — **borne supérieure optimiste** (ordre ignoré), documentée dans la section (anti-surinterprétation) ; oracle vs meilleur seul (`absolute_gap`, `relative_gap` clampé, tie-break lexicographique), `per_engine_recall`, `per_document` (plus forts écarts, **cap 20** explicite — source 50). (2) **Divergence taxonomique** : `build(view, taxonomy_analysis)` = **post-passe cross-payload** (pattern `conformity`) qui lit les **comptages taxonomy déjà collectés** de la même vue — **zéro re-classification** ; matrice triangle supérieur (a < b) + `max_pair` (`None` si toutes nulles). → **13ᵉ payload `inter_engine`** (chaque bloc `None` si préalable manquant — < 2 pipelines, GT sans token, taxonomy absente — jamais un zéro muet). **Section `cross_engine` étendue** (blocs complémentarité + divergence ; gate élargi : payload seul suffit). **🔶 R10 réparée** : GT sans token → doc exclu / corpus vide → bloc absent (**jamais 1.0**, ≠ source `inter_engine.py:201`), tests dédiés (vide, ponctuation seule, mixte). **Abandons actés** : `incremental_comparison` (C2 — slots hors enveloppe, cas 180-pipelines inexistant) · `pairwise_disagreement_rate`/`kl_divergence` (zéro consommateur). **Payload-only, pas de scalaire** (qualifie l'ensemble, ne classe pas) → **pas de glossaire** (précédent 4b/4c). Budget `analysis.py` relevé (801 → 920, justifié). `[~]` restent : **4e.2 lines** · **4e.3 longitudinal/Pettitt** (sessions séparées). Preuves : `tests/evaluation/test_inter_engine.py` (JSD valeurs main log2(1.5) · oracle multiset main · R10 · cap · tie-break) · `tests/evaluation/test_runner.py` (set exact des kinds + payload end-to-end) · `tests/reports/test_cross_engine_section.py` (blocs + borne documentée).

> **4e.2 (D-125)** : distribution du CER par ligne — `+ lines.py` : **alignement F15 porté tel quel** (`Levenshtein.opcodes` sur les **listes de lignes** avant tout CER — une ligne insérée/supprimée ne décale plus les suivantes ; ligne GT sans correspondance → CER **1.0** ; lignes hyp en trop **ignorées**, distribution indexée GT ; limite fusion/scission ≈ sub+del documentée) · CER ligne NFC+strip **plafonné 1.0** · percentiles p50/p75/p90/p95/p99 (interpolation linéaire) · **Gini** clampé [0,1] (somme nulle → 0.0) · **taux catastrophiques** seuils 0.30/0.50/1.00 **inclusifs ≥** (le `>` strict de la source laissait le seuil 1.00 **mort** : CER plafonné à 1.0 ne le dépasse jamais) · **heatmap positionnelle 10 bins** par position relative (poolable multi-docs ; tranche vide → `None`). `LinesCollector` (pattern taxonomy) → **14ᵉ payload `lines`**, agrégat **micro** (lignes du corpus **poolées** par pipeline — ≠ source qui moyennait des stats par document, divergence assumée alignée sur la convention maison). **Applicabilité par sonde comportementale** : `newline_preserved(view)` = survie de `\n` à `prepare_text("a\nb")` — couvre profils à plat (`flat_text`/`hipe`/`heritage`), levier `\W→espace` et `char_exclude` ; vue à plat → payload **absent** (l'alternative « représentation brute » de l'analyse écartée au build : chiffres incohérents avec la vue + plomberie de textes bruts — absence honnête > nombre trompeur). Section `lines` (distribution + heatmap), onglet **engines** (rows = pipelines ; « bloc de diagnostics » écarté) ; **réparation au passage** : `textual_fidelity` (4c) manquait aux tables onglet/libellé du renderer (rendue en « trailer » hors onglets) → ajoutée. **`worst_lines` non porté** (couvert T11, acté). **Payload-only, pas de scalaire** → **pas de glossaire** (précédent 4b/4c/4e.1 ; note provisoire « gini si affiché » écartée — pédagogie en prose). Budget : `analysis.py` 873/920, sous budget. `[~]` reste : **4e.3 longitudinal/Pettitt** (session séparée). Preuves : `tests/evaluation/test_lines.py` (fixture canonique 5 lignes CER [0, .2, .4, .6, 1] — percentiles posés main, Gini 24/55, seuil inclusif, F15 délétion/insertion, pooling, sonde par profil) · `tests/evaluation/test_runner.py` (set exact des kinds + valeurs end-to-end) · `tests/reports/test_lines_section.py`.

> **4e.3 (D-126)** : longitudinal raffiné — **4e réduit TERMINÉ**. `+ longitudinal.py` : **fonctions pures, PAS un payload `RunResult`** (multi-runs). **`linear_trend`** = OLS closed-form porté tel quel (pur stdlib, pente **par jour**, origine x = premier point → intercept lisible ; conventions documentées : série constante → R² = 1.0 — constance testée sur les **valeurs**, pas sur `syy` flottant ; `None` si < 2 points ou horodatages identiques). **`pettitt`** (**R11**) = vrai test de rupture (Pettitt 1979, rangs) : `U_t = Σ_{i≤t}Σ_{j>t} sgn(x_j−x_i)` en balayage **incrémental O(n²)**, `K = max|U_t|` (égalité → plus petite frontière), `p ≈ 2·exp(−6K²/(n³+n²))` clampée ≤ 1, **`significant` seulement si p ≤ 0.05** — le max-diff de la source (qui « trouvait » toujours, filtré par un seuil arbitraire 0.01) **n'est pas porté** ; preuve aux tests : Δ=0.4 sur n=6 → p≈0.29, NON significatif. Entrées **déjà parsées** (`datetime`/`float`) — le parsing multi-formats à skip silencieux de la source non porté. **Consommateur** : `app/history.series_insight` (couche 6 — `fromisoformat` strict, illisible → warning + ligne écartée, naïf → UTC, tri interne, `rupture_run_id` = premier run du nouveau régime) → cartes tendance `/history` (pente/j + R² ; « rupture dès <run> · Δ (p=…) » **seulement si significative**) + i18n FR/EN. **CLI `history` non créée** (CLAUDE §8.4 fige les commandes — prime sur la note d'analyse). `compute_corpus_longitudinal` non porté (boucle de présentation, la page itère déjà). Lève le différé D-042 (`evaluation/longitudinal.py`). Preuves : `tests/evaluation/test_longitudinal.py` (OLS valeurs main 0.05/0.15/0.25 + **parité scipy.linregress** ; Pettitt valeurs main K=36/p≈0.0314 et K=9/p≈0.2907 + recoupement double-somme directe + invariance monotone + clamp) · `tests/app/test_history.py` (tri, skip journalisé, r07) · `tests/interfaces/web/test_history_trends.py` (pente affichée ; rupture seulement si significative).

> **4f (D-127)** : entités nommées (NER) avec **R14** — verticale autonome (couches 3/5/6/7). `+ evaluation/ner.py` : `Entity`/`EntitySet` (le format embarque **le texte des offsets** `{"text","entities"}` → reprojection auto-suffisante ; la **liste nue** de la source abandonnée car R14 l'exige) · `parse_entities` (**erreur typée** si malformé — anti-silence) · **R14** `build_position_map`+`remap_entities` (alignement caractère `rapidfuzz.opcodes` GT↔OCR → spans hypothèse reprojetés en coords GT **avant** l'IoU ; sans quoi le F1 mesure le profil ins/del de l'OCR, pas la survie des entités) · `align_entities` (glouton IoU décroissant, labels casefold, déterministe) · `compute_ner` + `EntitiesCollector` (pattern taxonomy) → **15ᵉ payload `ner`** (global + par catégorie + manquées/hallucinées cap 20). `+ metrics/ner.py` : scalaire **`ner_f1`** jonction `(ENTITIES, ENTITIES)` (micro `Observation(f1, weight=n entités GT)`, `None` si GT sans entité ; registre = 17 métriques). Loader `load_representation(uri, ENTITIES)` → `EntitySet`. Runner : `_score_document` expose le **contexte entités** (3-uplet avec le texte) → le collecteur l'observe sans recharger ; payload absent si la vue ne déclare pas `ner_f1` (set exact des kinds de `test_runner` inchangé). `+ adapters/ner/spacy_extractor.py` : Module `RAW_TEXT|CORRECTED_TEXT → ENTITIES`, spaCy lazy (extra `[ner]`), mapping PERSON→PER/GPE→LOC, **fail-closed** (SDK/modèle absent → `AdapterStepError`, **jamais `[]`** — tue le silence source ; versions au `RunManifest` via `system_binaries()` best-effort). Builder `ner` au `ModuleRegistry`. Section `reports/sections/ner.py` (onglet engines, caveat « mesure conjointe OCR + extracteur »). Glossaire `ner_f1` FR/EN. **Différé (surface)** : planification d'une étape NER vivante (`Competitor.ner` + 422 au plan) + formulaire web + sonde moteurs — l'**anti-silence est tenue sans le 422** (l'adapter lève à l'exécution, l'orchestrateur isole). `worst`/`hipe` multi-profils source non portés (un extracteur de réf suffit, seam Module couvre les tiers). Budget `analysis.py` 942/1083. Preuves : `tests/evaluation/test_ner.py` (IoU/R14/PRF/collecteur valeurs main) · `tests/evaluation/test_ner_runner.py` (scalaire+payload+R14 via `evaluate_run`) · `tests/adapters/ner/test_spacy_extractor.py` (Module via faux spaCy + fail-closed) · `tests/app/test_module_registry.py` (builder) · `tests/reports/test_ner_section.py` · `tests/reports/test_glossary.py`.

> **4d.1 (D-128)** : qualité d'image — sous-tranche de **4d** (dernière famille de P2). **4d.2 robustesse ABANDONNÉE (D-129)** — décision produit renversant le verdict GARDER (dégradations synthétiques de validité douteuse, coût re-OCR disproportionné, seule feature à exiger la couche 6 + la tension CLI §8.4, résilience réelle = strates du dataset P3) → **4d = 4d.1 seul ; P2 (métriques) TERMINÉE.** `+ evaluation/image_quality.py` : maths **numpy pures** (testables sur matrices construites à la main, sans PIL) — `laplacian_sharpness` (variance du laplacien 3×3 / **500**, plafonnée 1) · `gradient_noise` (médiane des \|∇\| / **30** ; la source la nomme « MAD » par abus — c'est la médiane de \|∇\|) · `michelson_contrast` ((p95−p5)/(p95+p5)) · `estimate_rotation` (balayage projection **±5°** pas 1°, **heuristique** bornée, < 20 px → 0) · `composite_quality` (**0.40**·netteté + **0.30**·contraste + **0.20**·(1−bruit) + **0.10**·max(0,1−\|rot\|/**10**)) · `quality_tier` (**≥ 0.70** good · **≥ 0.40** medium). `image_quality_analysis(view, corpus)` décode via PIL (best-effort). → **16ᵉ payload `image_quality`** = **scope corpus, par document** — **1ᵉʳ payload non-pipeline** : la qualité d'une image ne dépend NI du moteur NI de la vue → calculée **une seule fois**, hors boucle des vues, rattachée à la 1ʳᵉ vue (comme `conformity` à `hipe` ; par-vue produirait N payloads identiques + N relectures). Section `image_quality` (onglet **documents**, table par document + agrégats + prose). **R8 — chaque constante documentée comme convention éditoriale** (500, 30, poids, ±10°, paliers, ±5°, percentiles 5/95) avec sa lecture, **sans autorité scientifique**. **R9 — pas de mock** (`generate_mock_quality_scores` non porté) : la démo reste **octet-stable par construction** (corpus démo sans `.png` réel → analyse `None`, comme `structured_data` sur corpus moderne — aucune neutralisation ajoutée). **Un seul chemin de mesure** : numpy (garanti via `scipy`) pour les maths, PIL **seulement pour décoder** (extra `[images]`, absent → `None` + warning unique) — le fallback PIL-seul de la source (nombres divergents) **abandonné**. **Adaptatif** : sans image locale lisible → `None` (distantes `://` / manquantes / non décodables → exclues + warning, jamais une mesure fabriquée). **Abandon `image_predictive` acté** (C3 : re-pondération des mêmes features sans pouvoir prédictif, nom mensonger) ; **`robustness_projection` confirmé, formellement acté à 4d.2**. **Whitelist** `EVAL_ALLOWED_EXT` += `numpy`,`PIL`. **Payload-only, pas de scalaire registre → pas de glossaire** (précédent 4b/4c/4e ; pédagogie en prose). Budget `analysis.py` 996/1083. Preuves : `tests/evaluation/test_image_quality.py` (maths valeurs main : tache 4×4 → laplacien [-40,10,10,0]/var 425/netteté 0.85 · bruit 0 · bimodale → contraste 1/3 · composite/paliers · gris plat 16×16 → 0.30/poor de bout en bout via `evaluate_run` · adaptativité None · PIL absent · un seul payload multi-vues) · `tests/reports/test_image_quality_section.py`.

> **G1 (D-131)** : carte des mots — **axe graphiques didactiques** (premier graphique ; le **seul** du catalogue à exiger un calcul nouveau, cf. `cinoc/reports/ANALYSE_GRAPHIQUES_DIDACTIQUES.md` §1). `+ evaluation/word_errors.py` : `word_misses(ref, hyp)` réutilise **`textual_fidelity.tokenize`** (une seule définition de token dans la couche) + `difflib.SequenceMatcher(autojunk=False)` — un mot GT est **raté** sur les tags `replace`/`delete` (forme produite = mot hyp aligné, ou `∅` supprimé ; `insert` = hallucination, **pas** un raté GT) · **`WordErrorCollector`** (pattern `inter_engine` : `observe(pipeline, doc_id, ref, hyp)` ; `build(view)` cross-tabule sur les pipelines **observés**). → **17ᵉ payload `word_errors`** : par mot GT, `per_engine` **creux** (seuls les moteurs qui ratent), `total_errors`, **signature de regroupement** `universal` (tous les pipelines observés ratent — la *matière*) / `engine_specific` (un seul — le *moteur*) / `partial` (sous-ensemble) ; `pipelines` = base du croisement (≥ 2) ; **cap 50** mots (tri `(-total, mot)`) ; **`None` si < 2 pipelines ou aucune erreur** (jamais une carte vide). **Enveloppe pour #2/#3** : `EngineWordError.variant` porte la **forme produite dominante** (verbatim, collectée à la même passe) — dimensionnée pour le graphe « mot → variante » (#3) et le recouvrement (#2), **non rendus en G1 mais rendus à D-132** (#2 recouvrement façon UpSet + #3 forme produite par moteur — **couche 7 seule, payload inchangé** ; la réserve « collectée mais non rendue » est ainsi levée). **Couche 7** : `reports/svg.py::word_engine_heatmap` (heatmap déterministe `num()`, octet-stable, **mots échappés** anti-XSS, `aria-hidden` — compagnon visuel) + CSS `.wmap-*` + `reports/sections/word_errors.py` (matrice mots×moteurs + regroupements, mots **verbatim**, prose **FR/EN** d'office, `requires=()`, onglet **crosses**), enregistré au renderer (label + tab + instanciation). **Honnêteté** : appariement **dépendant de la normalisation de la vue** (GT/hyp préparés identiquement en amont par le runner) ; **fusion/scission** de mots = limite de l'alignement (apparie 1-à-1, le reste → `∅`) ; mots et variantes **verbatim** (rien d'inventé — D-094). **Payload-only, pas de scalaire → pas de glossaire** (précédent 4b/4c/4e ; pédagogie en prose). Pas de nouvelle dépendance (stdlib `difflib`/`Counter`). Budget `analysis.py` 1056/1083. Preuves : `tests/evaluation/test_word_errors.py` (alignement replace/delete/insert · matrice universal/engine_specific/partial · variante dominante · cap 50 · `None` — valeurs main + bout en bout via `evaluate_run`) · `tests/reports/test_word_errors_section.py` (mots verbatim · FR/EN · déterminisme bit-à-bit · variante #3 non rendue) · `tests/reports/test_svg.py` (heatmap markup/comptes/teinte/échappement/déterminisme).

> **P5e 1 (D-275)** : `RunResult` **v3** — `DocumentUsage` est l'enregistrement **de chaque unité**, échecs compris (`outcome` · `reason` · `message`, validateur motif ⇔ `failed`) ; `MetricScore.expected` (agrégat : notés + unités en échec dont la vérité terrain alimente la métrique) ; un JSON v2 se recharge (`ok`, `expected=None`). Runner : politique A3 lue dans `EvaluationSpec.failure_policy` — `exclude` (tout `None`) ou `max_error` (1 pour un taux d'erreur, 0 pour un score, poids = celui que la métrique donne à la référence face à une sortie vide ; `None` si elle ne sait pas peser) ; une unité en échec n'alimente aucun collecteur. Économie : une unité en échec ne compte plus comme page traitée. Tests statistiques inchangés (cas complets), leur support est affiché à part. Preuves : `tests/app/test_unit_outcome.py`, `tests/evaluation/test_result.py`, `tests/evaluation/test_economics.py::test_failed_unit_is_not_counted_as_a_processed_page`.

> **P5f 2 (D-279)** : `RunResult` **v4** — le manifeste porte `served_models`, `unicode_version` et les réglages effectifs ; un JSON v3 se recharge (champs vides). Économie : la table s'indexe sur le modèle **servi** quand le manifeste le connaît (plusieurs servis pour un module → « non ventilable »), sur le modèle demandé sinon ; un servi absent de la table rend le coût inconnu et le dit (`tarif inconnu : openai/gpt-4o-mini-2024-07-18`) — l'alias ne le remplace pas. Preuves : `tests/app/test_archive_rescore.py::test_pricing_is_indexed_on_the_served_model`.

> **P5f 2, correctif (D-280)** : un servi absent de la table qui est **exactement** l'alias demandé suivi d'un suffixe de date — `-AAAA-MM-JJ` (attesté : SDK openai 3.59, `gpt-4o-mini` / `gpt-4o-mini-2024-07-18`) ou `-AAAAMMJJ` (attesté : SDK anthropic 2.14, `claude-haiku-4-5` / `claude-haiku-4-5-20251001`), date valide — prend le tarif de l'alias, et `basis` le dit (`machine+jetons — tarif de l'alias demandé : openai/gpt-4o-mini pour gpt-4o-mini-2024-07-18`). Jamais par préfixe : `gpt-4o` demandé et `gpt-4o-mini-2024-07-18` servi restent « tarif inconnu », comme `gpt-4o-mini-search-preview-2025-03-11` (un autre modèle du SDK). **Non retenu** : `mistral-small-latest` → `mistral-small-2506` — seule la cassette, synthétique, le sert ; le SDK mistralai 1.12.4 montre une réponse qui reprend l'alias (`extra/tests/test_struct_chat.py`), et `-AAMM` remplace `-latest` au lieu de le suivre. Un servi présent dans la table garde son propre tarif. Preuves : `tests/evaluation/test_economics.py::{test_a_dated_snapshot_of_the_requested_alias_takes_the_alias_price,test_a_snapshot_of_another_alias_stays_unknown,test_only_a_date_suffix_falls_back_to_the_alias,test_a_served_model_listed_in_the_table_keeps_its_own_price,test_mistral_latest_to_yymm_is_not_taken_for_a_snapshot}`, `tests/app/test_archive_rescore.py::test_pricing_is_indexed_on_the_served_model`.

> **P5e 1b (D-276)** : `PipelineOutputs` = `{pipeline: {document: by_step}}`. `_candidate_for` note l'étape `view.target_step`, ou à défaut la plus aval de `by_step` qui produit un type candidat ; `_CANDIDATE_PRECEDENCE` et `_step_ranks` supprimés (plus aucune sortie réelle sans étape : entrées initiales = l'image, fan-out estampillé) ; plusieurs types candidats dans la même étape → `EvaluationError` au lieu d'un choix implicite. `_TEXT_LIKE` reste (identité de représentation texte, sortie vide de `max_error`) : il ne servait pas qu'à la précédence. Calibration, correction et décisions lisent le **pool** (`latest_by_type`), comme avant. `RunResult` reste v3 : le seul champ neuf (`target_step` des `view_specs`) n'est écrit que s'il est posé. Preuves : `tests/evaluation/test_runner.py::{test_target_step_scores_an_upstream_step,test_candidate_is_the_most_downstream_step,test_one_step_publishing_two_candidate_types_is_refused}`.

> **P5e 3, 4, 6 (D-283)** : `RunResult` **v5** — `inference.py` réécrit autour de scipy : `omnibus_test` (Wilcoxon signé-rangs à 2, Friedman au-delà, cas complets, `MIN_SUPPORT` = 6 ; sinon motif `single_pipeline` · `insufficient_support` · `no_difference`), source **unique** du scalaire `significance_p` (`metrics/stats.py` n'en est plus qu'une lecture) ; `holm_adjusted` (famille = tests calculés du run entier) ; `nemenyi_critical_value` = `studentized_range.ppf(1 − α, k, ∞)/√2` (table et extrapolation supprimées) ; rangs par `rankdata` ; post-hoc seulement si Friedman rejeté **après** Holm ; `cd_groups` = barres CD maximales qui se chevauchent (remplace `tied_groups`, disjoints). `InferencePayload` gagne `test`, `not_computed`, `p_value`, `p_holm`, `family_size`, perd `q_alpha_extrapolated`, et un validateur refuse les états incohérents (post-hoc sans rejet, p sans test). Le runner collecte les séries de toutes les vues et produit les payloads **toujours** (mode rapide compris) ; l'IC bootstrap reste à l'analyse `inference`. Un JSON v4 sans payload `inference` se recharge ; avec, il est refusé. Preuves : `tests/evaluation/test_inference.py`, `tests/evaluation/test_inference_scipy_parity.py` (5 005 tirages, marqué `slow`, dans la suite), `tests/evaluation/test_result.py::test_v4_inference_payload_is_refused_not_misread`, `tests/interfaces/test_real_corpus_bnl.py::test_bnl_posthoc_shows_the_pair_that_differs`.

> **P5e 5 + P5g 6 bootstrap (D-284)** : `RunResult` **v5 conservée** (non publiée) — l'IC d'un pipeline est celui de l'agrégat **affiché**. `inference.micro_ratio` = Σ(v·w)/Σw, seule définition, lue par le runner (`_aggregate`, octets inchangés) et par l'IC (son point) ; `micro_ratio_ci` rééchantillonne les **documents** de poids non nul avec remise (`default_rng(42).integers(0, n, (lot, n))`, lots de ≤ 2²⁰ indices, `N_RESAMPLES` = 2 000), recalcule le ratio, quantiles percentile à interpolation linéaire — vectorisé numpy, plus de `random` stdlib. Toutes les métriques par document rendent `Observation(value, weight)` et s'agrègent par ce même ratio pondéré (taux d'erreur : Σ erreurs / Σ dénominateurs ; F1, τ, couvertures : moyenne pondérée par leur support) : chacune reçoit l'IC de ce qu'elle affiche. `InferenceEntry` = (vue, métrique, valeurs, poids) ; `PipelineInterval.mean` → `value` (un payload qui porte `mean` est refusé par `extra="forbid"`), `n_documents` = documents de poids non nul. Preuves : `tests/evaluation/test_micro_interval.py` (point dans son IC sur un corpus déséquilibré — rouge prouvé sur l'ancien code — et sur 1 000 corpus tirés ; égalité à `scipy.stats.bootstrap` à 1e-12 pour n = 2 à 3 000, plusieurs lots ; golden figé à l'octet, vert sous Python 3.11 et 3.13 ; poids nuls sans effet).

> **P5e 7 (D-285)** : `RunResult` **v5 conservée**. (1) Une vue sans profil note sous `flat_text` (couche 1/2) ; `representations.view_profile` est la seule résolution du profil (scoring, analyses, rapport). (2) **Une seule définition du CER de ligne** : `lines.line_cer` = la formule de `cer` sur des lignes **déjà préparées par la vue**, sans NFC ni `strip` à elle ; `diagnostics.line_cers` (pires lignes) la réutilise — l'appariement y reste positionnel, F15 relève de S14. Les **pires lignes** sont, comme la distribution par ligne, absentes d'une vue qui écrase les sauts de ligne (`newline_preserved`). (3) **Calibration** : GT et jetons préparés par `prepare_text` de la vue (un « é » NFD du moteur = le « é » NFC de la GT : ECE 0,1 au lieu de 0,9 sur le cas de test) ; jeton vidé par la vue non jugé ; confiances de l'**étape notée** (`runner._scored_step`, la même sélection que le candidat : `target_step`, sinon la plus aval) — `PipelineCalibration.step` **requis**, un payload d'avant est refusé ; bins [b/10 ; (b+1)/10[, dernier fermé, documentés (D9 du pilote : l'ECE 0,1234 de Tesseract ne s'affiche plus sous la chaîne Tesseract → LLM). (4) **Parité cas par cas** : `tests/evaluation/test_normalization_parity.py`, dix cas (NFC/NFD, bords, NBSP, tiret conditionnel, espace zéro, `\n` contre espace, espaces multiples, tabulation, apostrophe) × cinq conventions (`texte`, `texte (lignes)`, brute, jiwer 4.0.0, dinglehopper 0.11.0) — jiwer recalculé en CI, dinglehopper figé et recalculé quand il est installé (10/10 vérifiés dans un environnement séparé). — *preuve : `test_calibration.py`, `test_lines.py`, `test_runner.py::test_inference_analyses_through_evaluate_run`, `test_result.py::test_calibration_row_without_its_step_is_refused_not_misread`*

> **P5e 11a (D-286)** : **un seul alignement** — `evaluation/_alignment.py` porte `opcodes` (Levenshtein optimal `rapidfuzz`, éléments codés en entiers par ordre d'apparition : indépendant de `PYTHONHASHSEED`, mêmes S/D/I que jiwer), `alignment` (mêmes blocs et comptes, blocs aux côtés inégaux réappariés par ressemblance — somme minimale des distances normalisées, à égalité l'appariement de `rapidfuzz` ; plafond 200 000 cases), `aligned_to_reference` (départage `rapidfuzz` brut : lignes F15, mots de la correction) et `char_substitutions` (S de l'alignement caractère). `difflib` sort de la couche 3 : taxonomie, hallucinations (runs d'insertion), mots manqués et modernisation (`textual_fidelity.token_fates`, une passe pour les deux) passent par `alignment` ; `char_confusions` = `Counter(char_substitutions)` (somme = S du CER ; plus d'empan `_EMPAN_MAX`, plus d'alignement à deux niveaux) ; `diagnostics.line_cers` apparie par F15 comme `lines.aligned_line_cers` ; `metrics/text._align` (WER, MER, taux D/I) et `correction` lisent le même module. Taxonomie : blocs d'éditions entre deux mots égaux, fusion/scission au niveau du bloc (`max(n, m)`), sinon D → `lacuna`, I → `insertion`, S classée ; **lacunes = D − D des fusions/scissions, total = S + D + I** ; `I→l` vivant (table visuelle appliquée sur la casse d'origine **et** en minuscules ; `O→o`, mort, retiré). — *preuve : `tests/evaluation/test_alignment.py` (contre `jiwer.process_words` : cas construits, 300 aléatoires, 150 couples `bnl_mini` ; rouge prouvé sur `difflib` — 17 échecs ; hallucinations brouillée / après mot mal lu ; confusions = S du CER ; pires lignes F15 ; trois graines de hachage → mêmes octets), `test_diagnostics.py::test_char_confusions_counts_what_the_cer_counts_on_unrelated_spans`*

> **P5e 11b (D-287)** : (1) **tendance** — `longitudinal.linear_trend` = `scipy.stats.linregress` (l'OLS maison, même pente à 4e-12, est retiré) ; `TrendResult` gagne `p_value` (test bilatéral de pente nulle ; `None` à 2 points, zéro degré de liberté), `alpha` (0,05) et `significant` (p ≤ α) ; série constante → pente 0, **R² 0** (et non plus 1), p = 1 — ce que rend `linregress` quand il ne tombe pas sur `nan`. (2) **`roman.py` strict** — `_is_plausible_roman` = grammaire des chiffres (`M{0,4}(CM|CD|D?C{0,4})(XC|XL|L?X{0,4})(IX|IV|V?I{0,4})` : canonique + additif médiéval `IIII`/`VIIII`/`XXXX`/`CCCC`/`MMMM`) ; `IIV`, `IXI`, `VIV`, `XIIX` refusés. La détection de mots (`ci`, `dix`) reste à P5e 8. (3) `_alignment.opcodes` sert aussi le diff surligné du rapport (couche 7). — *preuve : `test_longitudinal.py` (`test_a_slope_carries_its_test` p = 0,1864 non significative, `test_two_points_give_a_slope_but_no_test`, constante sur 12 couples valeur × longueur, parité `linregress` p comprise), `test_roman.py` (3 999 formes canoniques ; 19 607 chaînes de ≤ 5 lettres : toute forme acceptée est canonique ou additive et vaut sa canonique ; 18 formes mal formées refusées — rouge prouvé)*

> **P5e 8 (D-288)** : des noms qui ne promettent pas plus. (1) **`hallucination` → `unanchored_trigrams`** (`metrics/diagnostics.py`), même calcul — aveugle à une page dupliquée (0,021 pour un CER de 1,01, `test_unanchored_trigrams_is_blind_to_a_duplicated_page`) ; zéro alias : un score d'avant garde sa clé et se relit tel quel (nom libre) ; `PipelineCorrection.n_hallucination_heavy` → **`n_heavy_insertion`** (un payload d'avant est refusé, `extra="forbid"`). (2) **`searchability`** : tolérance selon la longueur, échelle `AUTO` de Lucene/Elasticsearch (0 / 1 / 2 éditions sous 3, de 3 à 5, au-delà — `SPEC_HIPE.md` §10) ; un bruit de mots de deux lettres faisait 0,6. (3) **`ner_f1_exact`** : appariement de `ner_f1`, forme écrite lue aux offsets d'origine de la sortie, un apparié mal écrit compte FN + FP (`NerCounts.tp_exact`) ; la mention « convention CoNLL/HIPE » du seuil IoU 0,5 est retirée. (4) **`region_cer`** compte le texte des régions fantômes (de l'hypothèse sans vis-à-vis) en insertions. (5) **`fca` limitée**, dite au module : 0 dès que les lignes sont fusionnées, 1 − CER sous `flat_text`. (6) **`roman.detect_roman_numerals`** lit le contexte : un fragment soudé par un tiret à un mot (« ci-devant », « dix- huit ») n'est pas un nombre, deux numéraux joints (« XIV-XV ») si ; une forme lexicale (`_LEXICAL_FORMS` : `ci`, `dix`, `li`, `MM`, `cm`…) ne l'est que dans le cadre de points médiéval (`.dix.`). `RunResult` **v5 conservée**. — *preuve : `test_diagnostics.py` (AUTO, bruit 0,6 → 0), `test_ner.py::TestExactName`, `test_appariement_geometrique.py::test_les_regions_fantomes_comptent_leur_texte`, `test_metrics_flexible.py` (deux limites), `test_roman.py` (6 détections → 0 sur la GT des 37 pages BNL), `test_correction.py`, `test_registry.py` — rouge prouvé sur le code d'avant*

> **P5e 9 (D-289)** : chaque `@document_metric` déclare `category` et `unit` (paramètres requis de `metric.document_metric`) — 4 établies (`cer`, `wer`, `mer`, `cmer`), 16 adaptées, 9 exploratoires, table au D-289 ; `registry.established(names)` filtre les établies, `registry.metric_specs()` donne la fiche de chaque métrique du socle (`hcpr` compris, relié à la liste par défaut) à qui n'exécute rien. Le runner ne teste que les établies : `_inference_entries` et `_cross_engine_scores` passent par `registry.established` — la famille de Holm de D-283 ne compte plus les adaptées ni les exploratoires (pilote, profil `standard` d'avant : 13 tests → 5 ; Holm du CER 0,0783 → 0,0261). Preuve : `tests/evaluation/test_runner.py::test_only_established_metrics_are_tested`, `tests/reports/test_metric_cards.py` (catégorie, unité, fiche ; unité = ce que compte le poids, sur échantillons comptés à la main).

> **P5e 10 (D-290)** : oracles externes **exécutés** en CI, job `oracle` (extra `oracle` + dinglehopper 0.11.0 et ocrd 3.13.3 en `--no-deps`, marqueur `oracle`, sautés ailleurs) — aucun calcul de la couche changé. (1) **Golden dinglehopper** sur `bnl_mini` (150 couples, vue `texte (lignes)`) : une chaîne d'écarts nommés tombe sur dinglehopper 150/150 — CER : espaces multiples d'une ligne (30 couples), invisibles (0), `normalize_sbb` (87 : `’`/`'`, `⸗`, `—`, `==`), graphèmes (0) ; WER : invisibles (0), `normalize_sbb` (74), mots UAX #29 sans ponctuation (122) ; le côté Cinoc de la chaîne est recalculé dans la suite ordinaire. (2) **`roman` 5.2** contre `roman.py` : 4 999 canoniques, 137 256 chaînes de ≤ 6 lettres — 87 acceptées par Cinoc seul (additif médiéval, valeur de la canonique), 0 par `roman` seul. Aucune adaptée ne passe établie (aucun oracle pour `cer_diplo`, `bow_*`, `searchability`, `del_rate`/`ins_rate`). — *preuve : `tests/evaluation/test_dinglehopper_golden.py`, `tests/evaluation/test_roman_oracle.py`, `test_normalization_parity.py::test_dinglehopper_column` (marqué `oracle`) ; job simulé : 178 tests exécutés, 0 sauté*

**Enveloppe (plein-scope dès T1) :**
- [x] `RunResult` (`evaluation/result.py`) dimensionné plein-scope (scalaires texte/structure/NER/taxonomy + par-doc + `schema_version` ; clés stables ; `cross_engine` réservé). — *preuve : `test_result` (sérialisation déterministe) + `evaluate_run` le produit*
- [x] Registre **type-driven** unique (sélection par `input_types`) ; 0 ancien registre. — *preuve : `test_registry::test_get_and_select_by_input_types` + `test_no_forbidden_tokens` vert*
- [x] `DocContext` + runner (par-document → **agrégat micro** `Σerreurs/Σpoids` = la métrique au niveau corpus, `None`-exclu + support ; macro reconstructible depuis le détail par-doc). Les métriques renvoient `Observation(value, weight)` ; `weight` = dénominateur. — *preuve : `test_runner` (micro `1/6` ≠ macro `0.125` ; poids par-doc = 4 ; GT absente → `None`)* — **corrigé à l'audit T3** (était macro non pondéré + `safe_mean` supprimé).
- [x] `CrossEngineContext` + passe inter-moteurs (`cross_engine` écrit dans `RunResult`) ; **Wilcoxon/Friedman** avec **plancher de puissance** `_MIN_SUPPORT=6` (sous lui → `None`, pas un faux verdict) + filet `ValueError→None`. — *preuve : `test_metrics_stats` (significatif/égaux/sous-plancher) + `test_runner::test_cross_engine_significance_written`* — *(T2 ; durci à l'audit T3)*

**Garde-fous :**
- [x] `layer_dependencies` (`evaluation` → domain+formats ; `scipy` whitelisté) · `no_side_effect_imports` (décorateur **pur**, registre non auto-peuplé) · `file_budgets`. — *preuve : `test_evaluation_imports_are_allowed` + `test_fresh_registry_is_empty` + suite archi verte*
- [~] **`no-orphan métrique↔section`** : à la 1ʳᵉ section (couche 7, T1).

**Validation inter-couches :** voir `MIGRATION_PLAN.md` §3-T1 (1 CER → `RunResult` → HTML déterministe de bout en bout).

- [x] **WER/MER** (impl maison déterministe + **parité jiwer**, 15 cas) au socle texte. — *preuve : `test_metrics_text` (valeurs main) + `test_metrics_parity` (vs jiwer)*
- [x] **Profils de normalisation** (`normalization_profile`/`char_exclude`) honorés par le runner (couche 2 `formats/text`), symétriques GT/hyp ; **1 chargement par signature**. — *preuve : `test_runner` (caseless→0 ; profil inconnu→erreur) ; démo : vue `francais_medieval`*
- [x] **`cross_engine` + stats** : passe inter-moteurs (`CrossEngineContext`) → `RunResult.cross_engine` (clés `vue:métrique:test`) ; significativité **Wilcoxon/Friedman** (`scipy`). — *preuve : `test_metrics_stats` + `test_runner` (`text:cer:significance_p`)*
- [~] **Surface encore différée** : `compare` + sections engines/cross (T2.f) ; structure (T5) ; longitudinal/philologie/taxo/économie (T7).

---

*Référence : décisions actées en session de conception couche 3, réconciliées avec
`CLAUDE.md`. Enveloppe (contrats §3,§5-9) plein-scope maintenant ; surface remplie
par tranches (§15). Le reste émerge sous test (§13).*
