# SPEC v1.2 — Métriques HIPE-compatibles dans Cinoc (famille 4g)

> **Statut** : v1.2 — 2026-06-11. Remplace les v1.0/v1.1 (2026-06-10) qui ciblaient
> Picarones : **la cible est Cinoc** (Picarones gèle après la 1.0,
> `PLAN_FIN_MIGRATION.md` §5b) et la décision de dépendance est **inversée** (§5).
> Arbitrage produit **« plan A »** : la famille livre **avant la 1.0**, intégrée à
> l'Étape 4 sous le nom **4g** (sous-tranches 4g.1/4g.2) — la 1.0 revendique la
> conformité. Réconciliation métrique-par-métrique :
> [`cinoc/evaluation/ANALYSE_ETAPE_4.md`](cinoc/evaluation/ANALYSE_ETAPE_4.md)
> (§0 C9-C10, bloc « Arbitrages actés », §4g).
> Épistémique (`CLAUDE.md` §9) : l'enveloppe ci-dessous est durable ; chaque détail
> de surface est **PROVISOIRE — à confirmer au build**.
>
> `PLAN_FIN_MIGRATION.md` n'est **pas** modifié par ce document : l'insertion de 4g
> dans la table Étape 4 se réconcilie **au premier commit 4g** (rituel du roll-up +
> entrée journal D-0xx), pas dans une session d'analyse.
>
> **Post-D-109 (même jour)** : la route v1 est passée à **6 phases (P0→P5)** et
> l'Étape 4 s'appelle désormais **P2** (« ex-étape 4 », parallélisable après P0 —
> **P0 livrée** : strates + référence image). 4g s'insère donc **en tête de P2** ;
> l'arbitrage plan A (« avant la 1.0 » = avant P5) est inchangé. Vérifié contre
> `main` (D-094→D-114) : aucune contradiction ; amendements folds → strates
> (§3.6, §6).

**Références** : HIPE-OCRepair 2026 (page Evaluation + scorer officiel
`hipe-ocrepair-scorer` v0.9.9, MIT) · OCR-D eval spec · Levchenko 2025
(arXiv:2510.06743 — HCPR, AIR, contamination, stabilité) · Koynov 2025 (FedCSIS —
CCR, change ratio, éditions consécutives) · CEV (arXiv:2604.06160 — JSD
distributionnelle) · Kanerva et al. 2025 (RESOURCEFUL — écarts entre folds).

---

## 1. Problème (inchangé v1.1, reformulé Cinoc)

1. **CER non borné** : un VLM qui hallucine produit un CER > 100 % — la comparaison
   moteurs classiques vs génératifs est faussée au moment où c'est la mission du banc.
   (Le `cer` Cinoc n'est volontairement pas tronqué — c'est un signal — mais il
   manque la métrique **bornée** comparable : le MER caractère.)
2. **Non-régression invisible** : un agrégat masque un correcteur qui améliore 60 %
   des pages et en détruit 20 %. Cinoc a les pires lignes (payload `diagnostics`),
   pas le **triplet par document** ni le taux de régression catastrophique.
3. **Altération éditoriale non mesurée dans les deux sens** : modernisation (perte de
   formes historiques) ET sur-historicisation (insertion d'archaïsmes — documentée
   chez les VLM récents). Le CER ne distingue pas *lire* de *réécrire*.
4. **Interopérabilité** : produire des scores nommés et calculés à l'identique du
   scorer HIPE-OCRepair = argument de crédibilité direct (README 1.0, JOSS, papiers)
   + position face au leaderboard public.

## 2. Objectifs

| # | Objectif | Mesure de succès |
|---|---|---|
| O1 | Scores conformes au scorer officiel — **scores ponctuels** | Golden CI : écart ≤ 1e-9 vs scorer épinglé, sur le corpus d'exemple du repo officiel (bootstrap désactivé) |
| O2 | Régressions par document visibles | Triplet improvement/regression/no-change + taux catastrophique par run |
| O3 | Texte halluciné + ampleur d'intervention quantifiés | char_ins_ratio + CCR/change_ratio/length_ratio par unité et agrégés |
| O4 | Altération historique bidirectionnelle | HCPR + AIR (→ **famille 4b**, §9) + deltas de normalisation entre vues |
| O5 | Pas de dégradation perfs | Une seule passe `rapidfuzz.editops` par paire de textes et par vue, comptes partagés entre cmer / ratio d'insertions / éditions consécutives |

## 3. Non-objectifs (explicites)

1. Métriques de layout dédiées (la JSD distributionnelle R-2.5 capte l'essentiel ;
   décomposition CEV complète = T3 non engagée).
2. Entity preservation F1 → **famille 4f** (chantier NER séparé, déjà planifié).
3. Lexique de formes historiques valides (overcorrection *lexicale* = recherche).
4. **IC bootstrap bit-identiques au scorer** : les IC utilisent le **bootstrap
   maison T9** (percentile, graine fixe, stdlib) — la conformité O1 ne porte que
   sur les scores ponctuels (c'est aussi le périmètre du golden v1.1). Reproduire
   les tirages numpy du scorer serait de la dette pure.
5. Participation à la compétition (fenêtre close) ; le leaderboard HF =
   consommateur opportuniste de l'**export JSONL** (§7.4), pas une contrainte.
6. **Stabilité inter-répliques (R-2.7)** : différée d'**enveloppe** — la notion
   de réplique n'existe pas dans `RunResult` ; tranche dédiée, aucun champ créé
   d'avance. **Folds/pondération (R-2.4)** *(amendé post-P0, D-110/D-111)* : le
   canal existe désormais — `DocumentRef.metadata["stratum"]` →
   `RunDocumentResult.stratum` ; les folds HIPE se mappent sur les **strates**.
   Reste hors périmètre 4g la seule mécanique d'agrégation/pondération par
   strate (consommateur « CER par strate » prévu par D-109), à réévaluer à sa
   tranche.

## 4. Faits vérifiés sur le scorer officiel (v0.9.9 — source : code)

Conservés de la v1.1 (ils conditionnent l'implémentation et le golden) :

- **4.1 Formules** : `MER = (S+D+I)/(H+S+D+I)` via `jiwer.process_characters` /
  `process_words`. Micro = somme des comptes puis ratio ; macro = moyenne des
  scores unitaires.
- **4.2 `pcis` non borné** : `q = 1 − MER`, `pcis = (q_sys − q_hyp)/q_hyp` ;
  si `q_hyp == 0` → `clamp(q_sys, −1, 1)`. Une bonne correction d'un OCR très
  mauvais → pcis arbitrairement grand, la macro peut être dominée par quelques
  documents. → médiane + comptage `|pcis|>1` (§8).
- **4.3 Normalisation `norm()`** : lowercase ; mappings `ß→ss`, `ꝛ→r`, `œ→oe`,
  `æ→ae`, `aͤ→ä`, `oͤ→ö`, `uͤ→ü` ; suppression des césures DTA (`—\n`, `¬\n`) ;
  tout non-`\w` → espace ; underscores → espaces ; compactage. **Elle détruit des
  distinctions patrimoniales (œ/oe, æ/ae)** → double profil (§7.2).
- **4.4 Bootstrap** : 10 000 resamples, IC percentile [2.5, 97.5],
  **`np.random.seed(42)` global à l'init** — effet de bord d'état RNG process-wide
  (un des motifs du §5).
- **4.5 Stratification** : par `primary_dataset_name`, moyenne non pondérée des folds.
- **4.6 Sorties absentes** : hypothèse manquante/malformée/`"None"` → scorée comme
  chaîne vide (erreur maximale) + warning.
- **4.7 Empaquetage** : MIT, `jiwer>=3.0`, `numpy>=1.24`, `jsonschema>=4.0`,
  **`requires-python >= 3.12`** — incompatible avec la matrice CI Cinoc (3.11 + 3.12)
  en dépendance runtime.
- **4.8 Format d'entrée** : JSONL par unité — `document_metadata{document_id,
  primary_dataset_name,…}`, `ground_truth{transcription_unit}`,
  `ocr_hypothesis{transcription_unit}`, `ocr_postcorrection_output{transcription_unit}` ;
  schéma JSON embarqué.

## 5. Architecture — implémenter in-tree, le scorer en ORACLE DE TEST (décision inversée vs v1.1)

**Décision** : les 8 métriques officielles + `norm()` sont **implémentées dans
Cinoc** (couches 2/3) ; `hipe-ocrepair-scorer` est **épinglé en dépendance de
test** (extra `dev`) et sert d'**oracle golden** : à chaque CI, le corpus d'exemple
officiel est scoré par les deux chemins, échec si divergence > 1e-9 (scores
ponctuels). Le golden tourne sur le job **3.12** de la matrice, `skipif` explicite
ailleurs (jamais un faux vert).

**Pourquoi l'inversion** (la v1.1 disait « dépendre, pas réimplémenter ») :

1. `requires-python >= 3.12` casserait le support 3.11 (matrice CI) ou créerait une
   métrique qui existe selon la version de Python (irreproductibilité inter-env).
2. `np.random.seed(42)` **global** à l'init = effet de bord interdit par les
   garde-fous (no-side-effects) ; un wrapper save/restore serait de la dette.
3. Scorer = implémentation **et** oracle → validation circulaire ; en oracle de
   test, deux implémentations indépendantes se confrontent — un écart sur montée
   de version est un **signal traité consciemment** (version épinglée).
4. Performance : le scorer refait ses alignements jiwer (il ne peut pas partager
   les nôtres — contredit O5) ; in-tree, une passe `rapidfuzz.editops` alimente
   cmer + ratio d'insertions + éditions consécutives.
5. **C'est le pattern maison déjà amorti** : `text.py:8-9` — « jiwer sert d'oracle
   de parité (tests, dépendance dev), jamais importé par le code de production » ;
   idem T9 (Nemenyi/bootstrap stdlib, parité prouvée). Zéro catégorie de dette
   nouvelle.
6. L'interop leaderboard n'exige pas le scorer en runtime : on soumet le **JSONL
   des sorties** (§4.8) et le leaderboard score lui-même → ce qu'il faut, c'est
   l'**export** (§7.4).

**Coût possédé** : ~200 LOC (8 formules triviales + `norm()`). La pièce sensible
est `norm()` (sémantique `\w` Unicode, ordre des mappings, césures DTA) — c'est
pour elle que le golden 1e-9 + les tests de sensibilité Unicode existent (§11).

**Placement par couches** :

| Pièce | Couche | Détail |
|---|---|---|
| Profils `hipe` + `heritage` | **2** (`formats/text`) | donnée (12 → 14 profils) — pas de la surface exécutable (CLAUDE.md §8.8) |
| Scalaire `cmer` | **3** (registre) | comptes H/S/D/I caractère via `rapidfuzz.editops` (la plein-matrice maison de `_align` serait trop chère au caractère) |
| `ConformityPayload` + `CorrectionPayload` | **3** (`analysis.py`) | membres de l'union `analyses` (frozen, `extra="forbid"`) — **pas de dict ouvert** (le « dict ouvert » §10 v1.1 est rejeté : cf. bugs de clés fantômes C6/C7 d'ANALYSE_ETAPE_4) |
| Sections conformité / correction | **7** (`reports/sections`) | lecture seule ; mention du profil sur chaque nombre |
| Export JSONL HIPE | **6** (`app`) | le JSONL porte les **textes** (GT/raw/system), pas les scores → il faut corpus + `pipeline_outputs`, que seule l'app détient ; flag CLI `cinoc run --hipe-jsonl` |
| Golden + property tests | tests | extra dev `hipe-ocrepair-scorer==0.9.9` épinglé ; job CI 3.12 |

**Mapping des noms** : les clés internes restent au style maison (`cer`, `mer`,
`cmer` — contrat dur) ; les noms HIPE (`cmer_micro`, `wmer_macro`,
`pref_score_cmer_macro`…) sont produits **à la frontière** (section conformité +
export), depuis une table unique (Annexe A). `mer` existant ≡ wMER (même formule,
niveau mot — vérifié) : **aucune clé jumelle au registre**.

## 6. Modèle de données (mappé sur l'existant)

- **Unité de transcription = le document Cinoc** (la page) — répond Q3 v1.1 ;
  l'unité est inscrite au rapport (l'interprétation micro/macro en dépend).
- `ground_truth` = GT de la vue ; `ocr_raw` = artefact `RAW_TEXT` de l'étage 1 ;
  `system_output` = candidat aval (`CORRECTED_TEXT` si présent, sinon `RAW_TEXT`).
  Mode dégradé : pipeline mono-étage → les mesures avant/après (pref, pcis,
  triplet, CCR) sont **absentes du payload avec mention** — jamais un zéro muet.
- Niveaux de sortie : `corpus` = payloads ; `folds` = **strates** (`stratum` par
  document depuis P0/D-110 — l'agrégation par strate reste différée, §3.6) ;
  **aucun agrégat sans son détail** est déjà tenu par `RunResult.documents` ;
  `units` = `RunDocumentResult` existant + champs du payload (drapeaux par
  document capés/échantillonnés).

## 7. Exigences — 4g.1 « conformité » (P0) — **livrée (D-115, 2026-06-12)**

> Amendements de build (D-115) : extra **`hipe-oracle` dédié** (≠ `dev` : le
> scorer exige Python ≥ 3.12, l'inclure dans dev casserait l'installation
> 3.11) ; golden **vendoré** (fixture `tests/fixtures/hipe_golden/` générée une
> fois sur poste 3.12, test skip-gaté avec message tant qu'absente) ; parité de
> formule prouvée à chaque CI par les **comptes** `jiwer.process_characters` ;
> `heritage` **recompose** les umlauts décomposés (sinon `\W→espace`, fidèle au
> scorer, détruirait la marque combinante isolée) — le delta isole œ/æ/ꝛ.

### 7.1 Les 8 métriques officielles (R-1.1)
`cmer` (nouvelle clé registre) + `mer`≡wMER existant, micro + macro par vue ;
pref/pcis par pipeline 2 étages (calculés dans le payload, pas au registre — ils
exigent la paire raw/system). Noms HIPE à la frontière (Annexe A).
- [~] Golden 1e-9 vs scorer épinglé : **infra livrée** (`test_hipe_golden`,
  skip-gaté) ; fixture officielle à vendorer (réserve ouverte au DoD) ; parité
  jiwer (comptes) verte à chaque CI.
- [x] Les noms exportés sont identiques caractère pour caractère à ceux du
  scorer (section `conformity` + JSONL §4.8 — `tests/reports/test_conformity_section.py`).

### 7.2 Deux profils de normalisation (R-1.6)
- `hipe` : copie exacte de `norm()` (§4.3) ; `heritage` : lowercase + ponctuation +
  espaces **sans** mappings historiques (vérifier au build s'il se compose depuis
  `caseless`/`no_punctuation` existants) ; le score `raw` = vue de comparaison brute (`normalization_profile: null` explicite ; une vue qui n'en nomme aucun reçoit `flat_text` depuis D-285).
- Les deltas sont des **différences entre vues** (aucune mécanique nouvelle) :
  `delta_norm = cmer_raw − cmer_hipe` ; `delta_heritage = cmer_heritage − cmer_hipe`.
- [x] Chaque nombre publié mentionne son profil (vues nommées dans le payload,
  rappelées par la section — `tests/evaluation/test_conformity.py`).

### 7.3 Sémantique des sorties manquantes (R-1.8)
Dans **cette famille**, sortie absente → matérialisée `""` (erreur maximale) +
warning — alignement §4.6. Partout ailleurs, `None` = non applicable (convention
Cinoc). **Double convention documentée côte à côte** ; docs dégénérés (réf vide,
sortie absente) inclus dans le golden.

### 7.4 Export JSONL HIPE
- [x] `cinoc run --hipe-jsonl out.jsonl` produit le format §4.8 — un fichier
  par pipeline, R-1.8 appliqué (`tests/app/test_hipe_export.py`) ; la validation
  contre le schéma embarqué du scorer se vendorise avec le golden (réserve).

### 7.5 CER/WER classiques (R-1.2) — déjà satisfaite
`cer`/`wer` livrés, dénominateur = référence, non tronqués (> 1.0 possible).
- [x] Le rapport documente la différence cer/cmer (entrée glossaire `cmer` FR/EN).

## 8. Exigences — 4g.2 « bilan de correction » (P0/P1) — **livrée (D-116, 2026-06-12)**

> Amendements de build (D-116) : les **pires régressions** vivent dans le
> `CorrectionPayload` (`worst_regressions`, top 10 par Δ) — le
> `DiagnosticsPayload` livré reste **intact** (on ne modifie pas un payload
> expédié pour un tri) ; pas d'entrées de glossaire `pref`/`pcis`/`ccr` (le
> panneau est gaté sur les clés **scalaires** du résultat — entrées orphelines
> sinon ; la pédagogie vit dans la prose de la section). `prepare_text` extrait
> vers `representations` : une seule définition de « préparé comme au scoring ».
> Preuves : `tests/evaluation/test_correction.py` (témoin dérivé à la main),
> `tests/reports/test_correction_section.py`.

Toutes dans `CorrectionPayload`, calculées sur **une** extraction avant/après
(`pipeline_outputs`, pattern `calibration_analysis`) :

- **R-1.4 Triplet** `improvement/regression/no_change` (signe de `delta_cmer` par
  doc, mêmes égalités strictes que le pref officiel) — [ ] cohérence automatique
  `pref == improvement − regression` ; jamais le pref seul.
- **R-2.3 Régression catastrophique** : part des docs avec `delta_cmer > 0.10`
  (configurable, inscrit au rapport) + drapeau par doc.
- **R-1.9 CCR / change_ratio / length_ratio** (Koynov 2025) : CCR = MER(raw↔system) ;
  `change_ratio = CCR / cmer_raw` (drapeau `overedited` > 2.0) ;
  `length_ratio = len(system)/len(GT)`.
- **R-1.3 char_ins_ratio** `= I/(H+S+D+I)` caractère (dérivé des comptes cmer,
  pas un 3ᵉ alignement) + drapeau `hallucination_heavy` (> 0.10). N'altère pas
  `ins_rate`/`del_rate` existants (niveau **mot**, dénominateur réf — cousins,
  pas doublons ; documenté au glossaire).
- **R-2.2 pcis avec garde-fous** : pcis officiel + `pcis_median` + comptage
  `|pcis| > 1` + note automatique si moyenne/médiane divergent (> 2×).
- **R-2.6 Éditions consécutives** : distribution des longueurs de séquences
  d'éditions adjacentes (médiane, max, part des éditions en séquences > 20) —
  éditions dispersées = corrections ponctuelles ; longues séquences = réécriture.
- **Absorbés** : `error_absorption` (ex-4e — multiset GT-fondé : corrigées/
  introduites/conservées) et `over_normalization` (ex-4c — positionnel GT-fondé :
  mots OCR-justes dégradés par le LLM). Trois angles, un payload, une extraction.
- **Worst-pages (R-1.5)** : extension du `DiagnosticsPayload` existant (T11) —
  tri par `delta_cmer` et `ccr` (consommateur déjà livré).
- **Procédure `hallucination`** (arbitrage 2026-06-11, décision avant 1.0) : sur
  2-3 runs réels (OCR seul · OCR+LLM modernisant · zero-shot), (a) le trigramme
  flagge-t-il un document que (char_ins_ratio + part d'éditions groupées) ne
  flagge pas ? (b) faux positifs sur GT diplomatique + LLM modernisant ? Aucun
  signal unique → retrait de la clé ; sinon conservation avec caveat documenté.
  **État (D-116)** : la machinerie de comparaison est complète
  (`char_ins_ratio` + `edit_run_share` livrés) — **reste l'exécution sur runs
  réels**, réserve ouverte au DoD, à faire avant le gel des clés (1.0).

## 9. Reporté hors 4g (mappé sur les autres familles)

| Exigence v1.1 | Destination | Note |
|---|---|---|
| R-1.7 HCPR/AIR | **famille 4b** (philologie) | **Q4 actée (2026-06-11, D1-D5)** : une seule liste, archaïque uniquement, pour HCPR **et** AIR. Défaut = **`archaic_core`** trans-langue sans ambiguïté : `ſ ꝛ ⁊ ꝑ ꝓ ꝗ ꝙ ꝯ ꝝ ꝫ ꝭ þ ð ȝ` + formes décomposées `aͤ oͤ uͤ` ; **exclus du défaut : œ æ ß ç et tout accent moderne** (langue-relatifs — œ est du français moderne standard, ß de l'allemand → faux positifs AIR structurels ; la perte est déjà couverte par `diacritic_err`/`mufi_err`, les deux directions visibles en classe taxonomy). **`air` actif par défaut** (scalaire, `None` si la sortie ne porte aucun caractère de la liste) ; **`hcpr` visible seulement avec liste configurée** (anti-colonne-jumelle de `mufi_err`). Listes nommées en **package-data** (`archaic_core`, `archaic_de`, `archaic_fr_medieval`…) sélectionnables par corpus + override par run ; **nom + hash de la liste au manifeste et au rapport** (comparabilité). HCPR = généralisation paramétrable de `diacritic_err`/`mufi_err` (parité bit-à-bit si factorisation) ; **AIR est l'apport net**. Reste au build : dénominateur exact d'AIR (borné [0,1]) + comportement sur l'étage brut des pipelines 2 étages. |
| R-2.5 `cev_jsd` + `reading_order_suspect` | tranche 4e (ou 4g.2+) **avec sa section** | implémentation directe de la JSD (quelques lignes, pattern inter_engine) — Q6 résolue : pas de dépendance lib CEV |
| R-2.1 IC bootstrap | déjà livré (T9) | bootstrap maison ; avertissement « IC chevauchants » = ajout mineur aux sections cross/synthesis |
| R-2.4 folds/pondération · R-2.7 stabilité répliques | différés d'**enveloppe** | cf. §3.6 |
| Annexe C contamination | docs corpus/library | conservée intégralement (§13) ; les dégradations 4d servent de sonde (« corrige vers le canon plutôt que vers l'image » = lecture de mémoire) |

## 10. Hygiène de clés pré-1.0 (couplée au plan A)

Les clés et sémantiques gèlent à la 1.0. Trois décisions **avant** le gel :
1. `hallucination` : procédure §8 (exécutée à 4g.2).
2. `searchability` : durcissement **échelle Elastic AUTO** (0 édition < 3
   caractères · 1 pour 3-5 · 2 pour ≥ 6) — les valeurs baisseront vs runs passés,
   raison de plus pour le faire pré-1.0.
3. `flesch_delta` : **abandonné** (amendement de la table 4a — construct hors
   domaine sur ponctuation OCR abîmée ; couvert par lexical_modernization /
   4g.2 / hcpr-air ; réversible sans perte, formules publiées). Journal D-0xx au
   premier commit concerné.

## 11. Tests de conformité (transverse, P0)

- [ ] **Golden** : corpus d'exemple officiel scoré par les deux chemins à chaque
  CI (job 3.12) ; échec si divergence > 1e-9 (scores ponctuels) ; versions
  épinglées (`hipe-ocrepair-scorer==0.9.9`) ; toute montée de version passe par
  le golden ; docs dégénérés inclus (réf vide, sortie absente).
- [ ] **Property tests** : MER ∈ [0,1] ; **CER ≥ cMER** (dénominateurs) ;
  CER = cMER quand I = 0 ; triplet Σ = 1 ; `pref = improvement − regression` ;
  normalisation idempotente ; `cev_jsd` ∈ [0,1] ; CCR = 0 ⟺ system ≡ raw.
- [ ] **Sensibilité Unicode** : paires construites (œ/oe, æ/ae, ß/ss, ſ/s, aͤ,
  césures DTA) vérifiant chaque profil — valeurs **dérivées à la main** (jamais
  Picarones ni le scorer comme source des attendus *écrits* ; le scorer reste
  l'oracle *exécuté*).

## 12. Questions ouvertes — mises à jour

| # | v1.1 | Statut v1.2 |
|---|---|---|
| Q1 | Python ≥ 3.12 ? | **Résolue** : scorer en dépendance de test, golden sur job CI 3.12, `skipif` ailleurs |
| Q2 | worst-pages : UI ou export ? | **Résolue** : extension du `DiagnosticsPayload`/section existants (T11) |
| Q3 | granularité de l'unité ? | **Résolue** : document (page) Cinoc, inscrite au rapport |
| Q4 | liste `C` par défaut ? | **Actée (2026-06-11)** : défaut = `archaic_core` trans-langue (œ/æ/ß/ç **exclus** — langue-relatifs) ; `air` actif par défaut, `hcpr` sur liste configurée ; listes nommées package-data + override par run, nom + hash tracés (détail §9). Au build : dénominateur AIR + étage brut |
| Q5 | revendiquer la conformité au README/papier ? | **Actée (plan A)** : oui, à la 1.0 |
| Q6 | lib CEV ou implémentation directe ? | **Résolue** : implémentation directe de la JSD |

## 13. Phasage (intégré à P2, ex-Étape 4 — plan A)

| Tranche | Contenu | Place dans P2 |
|---|---|---|
| **4g.1** | profils `hipe`/`heritage` (couche 2) · `cmer` · `ConformityPayload` + section · export JSONL · golden/property/Unicode | **1ʳᵉ tranche** de P2 révisée |
| **4g.2** | `CorrectionPayload` (triplet · pcis+médiane · catastrophic · CCR/change/length · char_ins_ratio · absorption · over_normalization · éditions consécutives) · worst-pages étendu · **procédure `hallucination`** | 2ᵉ tranche |
| Suite | 4a (sans readability) → 4b (+hcpr/air) → 4c réduit → 4e réduit (± cev_jsd) → 4f (avec R14) → 4d | cf. `ANALYSE_ETAPE_4.md` §Ordre |

Estimation : 4g.1 ≈ 1 session de construction ; 4g.2 ≈ 1-2 sessions. Aucune
deadline externe (compétition close) ; la deadline interne est le **gel** : seules
les familles *Picarones* y sont assujetties — 4g l'est par choix (plan A), pour que
la 1.0 porte l'argument de conformité.

---

## Annexe A — Correspondance des noms (frontière section/export)

| Clé interne (registre/payload) | Nom HIPE exporté | Source |
|---|---|---|
| `cmer` (micro/macro par vue `hipe`) | `cmer_micro` / `cmer_macro` | scorer |
| `mer` (micro/macro par vue `hipe`) | `wmer_micro` / `wmer_macro` | scorer |
| `pref` (payload) | `pref_score_cmer_macro` / `pref_score_wmer_macro` | scorer |
| `pcis` (payload) | `pcis_cmer_macro` / `pcis_wmer_macro` | scorer |
| `char_ins_ratio`, `ccr`, `change_ratio`, `length_ratio`, `hcpr`, `air`, `cev_jsd` | identiques (acronymes des papiers, citabilité) | Levchenko/Koynov/CEV |

## Annexe B — Décisions consignées (v1.1 → v1.2)

Retarget Picarones → Cinoc (gel) · **dépendance inversée** : in-tree + scorer en
oracle de test épinglé (§5, 6 motifs) · conformité = scores ponctuels, IC =
bootstrap maison T9 · « dict ouvert » rejeté → payloads typés `extra="forbid"` ·
HCPR/AIR → 4b avec **liste archaïque unique** (la liste « diacritiques modernes »
de v1.1 n'avait aucun consommateur : perte = `diacritic_err`, directions = classe
taxonomy) · over_normalization + error_absorption absorbés dans `CorrectionPayload`
· worst-pages = extension du payload diagnostics existant · folds + répliques =
différés d'enveloppe · `hallucination` = procédure différée-avec-critères (§8) ·
unité = document/page · **Q4 actée le même jour (post-v1.2)** : défaut =
`archaic_core` trans-langue, œ/æ/ß/ç exclus ; `air` par défaut, `hcpr` sur liste
configurée (§9, §12).

## Annexe C — Protocole de contamination (conception de corpus, pas de code)

Risque : sur des textes célèbres ou massivement numérisés (Gallica), un VLM/LLM
peut **reconstituer** le texte depuis son entraînement au lieu de le **lire** — un
CER excellent qui ne mesure pas la reconnaissance (Levchenko 2025). Conséquences
pour tout benchmark Cinoc comparant des modèles génératifs :

1. Inclure une part de matériel **improbable à l'entraînement** (pages inédites,
   GT interne, documents non diffusés).
2. Test de détection : évaluer sur des images **dégradées artificiellement de
   manière non historique** (les dégradations 4d servent de sonde) — un modèle qui
   « corrige » vers le texte canonique plutôt que vers l'image lit sa mémoire.
3. Tout rapport comparatif inter-modèles mentionne le statut de contamination
   présumé du corpus (public ancien / public récent / inédit).

Relève de la constitution des jeux d'évaluation ; consigné ici parce qu'il
conditionne l'interprétabilité de toutes les métriques ci-dessus.
