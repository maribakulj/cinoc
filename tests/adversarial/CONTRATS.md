# Synthèse de conception : cinq contrats à remplacer (contre-expertise `04a1c17b`)

Ce document fait suite à `README.md`, `CONVENTIONS.md`, `BIBLIOTHEQUES.md`, `rapports/*.md` et `rapports/REVUE_CONTRATS.md` de ce dossier. Il ne corrige rien et n'écrit aucun code. Il ramène les 90 défauts confirmés (51 `valide`, 39 `discutable`) à cinq contrats fautifs, et donne pour chacun :
- le contrat qui le remplace ;
- les invariants qui jugeront la correction ;
- l'ordre des corrections ;
- la liste fermée de ce qui reste à arbitrer.

**Règles suivies** (consigne du mainteneur) :
- chaque cause remplace un contrat existant, en place ;
- bibliothèque mature d'abord ;
- tests avant correctifs ;
- une tranche est finie quand ses **invariants** sont établis ;
- la cohérence des contrats n'est jamais sacrifiée à une contrainte de taille ou de dépendance.

## Révision n° 2 (revue adverse `rapports/REVUE_CONTRATS.md`)

Les 23 contre-exemples de la revue se reproduisent sur la copie (`run_all.sh` : 23/23). **Aucun point n'est rejeté.**

Trois points sont acceptés avec une précision vérifiable :
- **P1** : le départage canonique est calculé et vérifié (`ce-contrats-r2/p1_departage_canonique.py`) ;
- **R4** : l'inversion du bootstrap a été mesurée au bon niveau sur le scénario de la revue (`ce-contrats-r2/r4_bootstrap_niveau.py`) ;
- **R10** : la résolution des bibliothèques d'un binaire est précisée.

Ces deux scripts sont dans le dossier de travail (`scratchpad/ce-contrats-r2/`), hors de la copie.

| Point | Section | Ce qui change |
|---|---|---|
| **R1** `fsum` non associatif | § 2.1 a, M6 | Statistiques réelles stockées **exactes** : entiers quand la grandeur est discrète (jetons, ns, micro-unités), sinon `Fraction`. Combinaison = addition exacte ; une seule conversion en flottant, à la finalisation. Propriété : pour toute partition et tout ordre des documents, la statistique combinée est égale (`==`). |
| **R2** régions de référence non appariées | § 2.1 a, M4 | Le numérateur compte aussi le texte des régions de référence non appariées (suppressions), comme le code actuel (`layout.py:103-108`). |
| **R3** ordre partiel | § 2.4 b, M5 | `LayoutPage.reading_order` devient un arbre de groupes ordonnés et non ordonnés (domain, couche 1). Le τ ne compte que les paires que la référence ordonne. M5 passe en tranche 4. |
| **R4** inférence du Δ micro | § 2.1 d (table par famille), A3 | Permutation (changement de signe) seulement si le dénominateur est fixé par la référence. Sinon, bootstrap apparié par document, et p par inversion du bootstrap. Niveau mesuré sur le scénario de la revue : 0,063 (n = 30 et 100, 300 simulations) contre 0,30 pour la permutation. La H0 de chaque test est nommée. |
| **R5** support macro | § 2.1 c, A4, A6 | D^M est fixé **par la référence** (n_réf > 0, ou tp + fn > 0), le même pour tous les pipelines. Pas de macro publié quand le scalaire dépend de l'hypothèse (précisions, τ). |
| **R6** `partial`/`truncated` imputés en silence | § 2.1 b, e ; A1, A2, A7 | La part manquante porte un motif d'axe 3 (`partial_output`, `truncated_output`). L'observation est exclue par défaut et notée telle quelle sous la seule sensibilité `empty_page`, qui couvre toute part manquante. |
| **R7** jiwer sur référence vide | M1 | « Égal à jiwer quand Σ n_réf > 0, pour S+D+I seulement ». Les écarts volontaires sont écrits : jiwer rend `cer([""], ["xyz"]) = 3` et `cer([""], [""]) = 0` ; Cinoc rend « indéfini ». |
| **R8** oracle NER | M3, M8 | nervaluate est retiré. L'oracle devient l'énumération exhaustive de l'appariement par IoU d'empan, la règle même de Cinoc. Constat associé : l'appariement NER actuel est glouton (`ner.py`, `align_entities`), donc il passe sous l'appariement unique de K5. |
| **R9** différence de `sys.modules` | § 2.3 c, I1 | Instantané du **processus entier** à la fin de chaque étape : modules hors stdlib et bibliothèques partagées mappées. C'est une sur-approximation sûre, indépendante de l'historique, mémoïsée par run. |
| **R10** binaire coquille | § 2.3 c, I1 | Sont hachés l'exécutable **et** les bibliothèques qu'il charge (`ld.so --list` sous Linux, `otool -L` sous macOS ; Cinoc exécute déjà ce binaire, donc aucune frontière de confiance nouvelle). La sortie complète de `--version` reste tracée. |
| **R11** filiation déclarée | § 2.4 a, M8 | La filiation est **vérifiée** : chaîne d'empreintes jusqu'à la VT, plus déclaration du module, plus id identique **et** paire admissible. Les ids ne font que choisir parmi des paires admissibles. `region_detection` est `not_applicable` quand les régions sont héritées de la VT. |
| **P1** départage S/D/I | § 2.1 a, M1 | Règle canonique : parmi les alignements optimaux, **maximiser S**. Les comptes (S, D, I) deviennent uniques et indépendants de la bibliothèque. Calcul : deux appels `rapidfuzz` (distance d, distance pondérée W avec (K, K, K−1), K = \|r\|+\|h\|+1, S = K·d − W). Vérifié contre une DP lexicographique sur 3 000 cas. |
| **P2** réplicats dégénérés | § 2.1 d, A3 | Un réplicat dont la finalisation est indéfinie est écarté et compté. Au-delà d'un taux ε, IC et p sont « non estimables ». Méthode percentile nommée (§ 6, B2). |
| **P3** quantiles | § 2.1 a, A13 | La statistique d'un document est le multi-ensemble de ses lignes ; on tire des **documents**. |
| **P4** analyses de rangs | § 2.1 d, A5, A9 | `zero_method` et `method` fixés (§ 6, B5). Rangs calculés sur des scalaires exacts (`Fraction`, convertis une fois). Friedman seulement si k ≥ 3. « Non calculé » si la variance est nulle, et le test garde sa place dans la famille. |
| **P5** grappes et ordre | § 2.1 d, A8 | Les grappes sont triées par le plus petit id de document qu'elles contiennent : en singletons, l'IC est identique bit à bit à l'IC par document. |
| **P6** grappes et répétitions dans l'inférence | § 2.1 d, A8 | Une répétition n'est jamais une unité d'inférence ; la grappe d'une répétition est son document. Sous grappes déclarées, les analyses de rangs portent sur les moyennes par grappe, ou ne sont pas publiées. |
| **P7** VT non transcrite | § 2.1 b, A2, M1, M4 | Axe 1 : `not_transcribed`, déclaré par l'importeur, distinct d'une référence vide (page blanche). Hors des attendus. |
| **P8** ordres appariés intransitifs | § 2.1 c, A6 | Les ordres appariés ne composent pas un classement. Seul le support global trie. |
| **P9** reprise d'un record `partial` | § 2.2, F3 | Seuls les records `ok` et `truncated` (cause de la coupure incluse dans la clé) sont réutilisables en `resume`. `partial` et `failed` sont retentés ; ils ne sont relus qu'en `rescore`. |
| **P10** clé circulaire | § 2.2, § 2.3 c, F3 | Clé en deux temps : **recherche** sur la partie déclarée et les entrées consommées ; **validation** du record trouvé sur l'environnement enregistré à la première exécution. |
| **P11** protocole dépendant de la plateforme | § 2.3 c, d ; I3, I5 | Deux identités : **définition** (portable : sources `.py`, réglages, profils, Unicode, règles de calcul) et **environnement** (extensions compilées, bibliothèques, plateforme). Elle est enregistrée, qualifie une reproduction sans la bloquer, et sert à valider le cache sur la même machine. |
| **P12** `ObservationId` dépendant du corpus | § 2.3 d, I3 | Les VT du corpus sortent de l'identité du protocole. L'`ObservationId` ne contient que la VT de son document. `CorpusIdentity` est séparée. |
| **P13** BagIt : fichiers hors manifeste, liens durs, 0444 | § 2.3 b, e ; I6, F7 | Tout le contenu est sous `data/`. Tout fichier non listé dans un manifeste est refusé. Un « lien » est un lien symbolique ou un fichier avec `st_nlink > 1` hors option. Le mode 0444 n'est pas présenté comme une protection. |
| **P14** durabilité | § 2.2, F5 | Ordre imposé : `fsync` des blobs → record écrit et `fsync` → `os.replace` → `fsync` du répertoire. |
| **P15** poids | § 2.3 c | Les fichiers de poids chargés sont hachés, pas seulement le commit du Hub. |
| **P16** ex æquo géométriques | § 2.4 a, M8 | 3ᵉ critère lexicographique : Σ distance d'édition des textes appariés ; ensuite l'ordre géométrique canonique, sans le texte. |
| **P17** IoU flottante au seuil | § 2.4 a, M8 | Admissibilité en arithmétique exacte : 2·\|∩\| ≥ \|∪\| en entiers, dans un repère commun, en `Fraction` si les dimensions des pages diffèrent. |
| **P18** justification Kirillov | § 2.4 c, § 6 | Justification retirée. Les relations de fusion et de scission entre régions de VT qui se recouvrent sont `not_applicable` (`ref_overlap`), et leur nombre est publié. |
| **P19** `line_identity_*` sans filiation | § 2.4 a, M4 | Applicables seulement sous filiation vérifiée des lignes ; `not_applicable` sinon. |
| **P20** deux conventions de seuil | § 2.4 a, § 6 (O2) | Un seul appariement et une seule règle d'admissibilité pour les boîtes et les empans NER. |

Les deux mécanismes à re-spécifier, signalés par la revue, sont l'**inférence du Δ micro par famille** (R4, § 2.1 d) et l'**identité d'exécution** (R9, R10, P10, P11, § 2.3 c-d). Le correctif le plus transversal, **R5**, est propagé dans K2 et dans A4 à A6.

## Révision n° 1 (rappel)

Statistiques par famille (point 1) · micro et macro chacun avec son inférence, rangs à part (2) · quatre axes (3) · trois supports (4) · propriétés par métrique (5) · clé sur artefacts consommés et répétitions (6) · intégrité contre authenticité, liens, fichiers exécutés (7) · appariement lexicographique et filiation (8) · relecture, reproduction et réévaluation (9) · familles de Holm a priori (10).

Décisions rendues et intégrées :
- BagIt ;
- Hypothesis (extra `dev`) ;
- `scipy>=1.15` ;
- rupture du schéma `RunResult` (v6, un JSON antérieur est re-noté depuis son archive) ;
- enregistrements par étape ;
- persistance atomique immédiate ;
- RO-Crate reporté à la publication ;
- refus du fan-out multipage à image unique en 1.0 ;
- K1 et K2 conçus ensemble.

---

## 1. Causes communes

### 1.1 Les cinq contrats

| # | Contrat fautif (actuel) | Pourquoi il produit plusieurs symptômes | Arbitrages | Tests V / D |
|---|---|---|---|---|
| **K1** | **L'observation est un ratio et un poids, pas une statistique suffisante.** `Observation(value, weight)` (`evaluation/metric.py:22`). L'agrégat est Σv·w/Σw (`runner.py:307-327` → `inference.py:166`). Les IC sont calculés par pipeline sur les couples (v, w) (`inference.py:182-271`). `_error_rate` vaut 0 ou 1 (`metrics/text.py:114`). | Aucun poids ne reconstruit un F1. Un dénominateur nul perd son numérateur. Un plancher par page n'est pas un plancher du corpus. Le poids du τ n'est pas son dénominateur. Aucun Δ apparié ni aucune grappe n'est possible. **14 métriques sur 29** sont fausses. | **2**, **1** | V 9 · D 10 (C01, C02×3, C03, C04, C05×2, C06 `ic_apparie`, C09) |
| **K2** | **La non-mesure n'a ni axe ni motif ; « attendu » et support dérivent de l'échec d'exécution.** `MetricScore.value=None` (`result.py:31-46`). `missed` n'est compté que sur `failed` (`runner.py:146-160`). Cinq endroits rendent `None` sans motif (`runner.py:519-538`, `:555-575`, `layout.py:92`, `fanout.py:230-235`, `analysis.py:960`). Le support est implicite (`inference.py:116-122`). `max_error` est déduit du signe de la métrique (`runner.py:409`). | `None` code six situations. Une unité réussie mais inexploitable sort des compteurs. Un pipeline non applicable vide les tests des autres. Un échec non aléatoire fait gagner. L'imputation dépend du signe de la métrique. | **3**, **8**, **1** | V 8 · D 6 (C06 `meme_documents`, C07, C08×2, C13×2) |
| **K3** | **L'étape n'est pas l'unité d'enregistrement.** `DocumentExecution` (`pipeline/types.py:73-142`, `:96-99`, `:111-112`) ; orchestrateur `:333-347` ; workspace par pipeline (`orchestrator.py:233-243` → `_workspace.py:23-28`) ; usage et clé de reprise par unité (`result.py:82`, `resume.py:130`) ; pool final (`runner.py:131-138`). | L'échec aval efface l'amont. Deux étapes de même label s'écrasent. Les analyses jugent la dernière étape. Une vue de préfixe est facturée au coût du pipeline entier. | **4**, **8**, **7** | V 13 · D 5 (C12×3, C18×2) |
| **K4** | **L'identité est déclarée et non vérifiée ; le cache tient lieu d'archive.** `content_hash` jamais relu (`resume.py:296-301`, `:316-324`, `representations.py:37`) ; version saisie à la main (`fingerprint.py:72`, `:18`) ; GT sans empreinte (`documents.py:22-32`) ; manifeste réduit à `corpus_name`/`n_documents` (`run.py:90-91`) ; empreinte d'image jetée (`resume.py:150-172`) ; double rôle du `ResumeStore` (`:205-219`) ; `_rebased` (`:187-200`) ; téléchargement hors ligne (`orchestrator.py:246-268`). | Sorties altérées, index modifiés, GT remplacées et briques corrigées passent sans trace ; une reprise réécrit l'archive. | **5**, **7**, **4** | V 9 · D 9 (C14×4, C15×3, C17×2) |
| **K5** | **La correspondance est une égalité de clé, pas un alignement global.** `layout.py:232-265`, `:256`, `:372-392` ; glouton (`:172-195`) ; pages aplaties (`:145`, `:202`, `:49`) ; deux projections (`projectors.py:30-67` contre `to_text.py:31-86`) ; fan-out (`fanout.py:67,101`) ; multi-ensemble (`calibration.py:126`) ; appariement NER glouton par IoU (`ner.py`, `align_entities`, R8). | Ids partagés par hasard, mots répétés et ordre du fichier tiennent lieu de preuve d'homologie. | **6** | V 12 · D 5 (C10×2, C11×2, C16) |
| — | Plan d'expérience | méthode, pas code | — | D 4 (C19) |

Totaux : V **51** ; D **39**.

### 1.2 Recoupements

| Arbitrage | K1 | K2 | K3 | K4 | K5 |
|---|---|---|---|---|---|
| 1 Estimandes, tests appariés, grappes | ● | ◐ | | | |
| 2 Statistiques suffisantes | ● | | | | |
| 3 Non-mesure typée | ○ | ● | ○ | | |
| 4 Par étape, isolation, intégrité | | | ● | ◐ | |
| 5 Archive ≠ cache | | | ○ | ● | |
| 6 Appariement | ○ | | | | ● |
| 7 Empreintes, identité des données, distant | | | ◐ | ● | |
| 8 Conditionnel, couverture, supports, opérationnel | ○ | ● | ◐ | | |

● = cause principale ; ◐ = contribue ; ○ = ingrédient.

Les arbitrages 3 et 8 découlent de K1 et K2 (conçus ensemble, § 2.1). Les arbitrages 4, 5 et 7 se partagent `StepRecord` (K3) et son identité calculée (K4).

Tests à cheval :
- `a5_*` (K3, K4) ;
- C01 (K1, K2) ;
- C12 `la_reprise` (K3, K4) ;
- C18 (K3, K4) ;
- `ner_payload…label_absent` (K2, K1).

### 1.3 Hors des cinq contrats

| Défaut | Rattachement |
|---|---|
| SIGINT : file non arrêtée, unités payées sans être archivées | persistance atomique immédiate + arrêt de la file (tranche 2) |
| saknussemm : délai codé en dur, unité `ok` en repli total | réglage opérationnel déclaré (K4) ; `partial` (K2, K3) |
| `dependencies_lock` = métadonnées d'installation | K4 (instantané du processus) |
| Lignes avec des `\n` (fan-out → saknussemm) | corrigé dans `aba0fe7`, gelé |

---

## 2. Contrats

### 2.1 K1 + K2 : observation, axes, supports, estimandes (conception commune)

#### a. Statistique suffisante par famille (point 1 ; R1, R2, P1, P3)

Chaque métrique déclare sa statistique `S`, sa **combinaison** (addition exacte, donc associative et commutative, avec un élément neutre) et sa **finalisation** `S → float | None`. La valeur d'un document et l'agrégat micro passent par la même finalisation.

Il n'y a pas d'algèbre générique : une petite classe par famille. Deux règles d'exactitude :
- **R1.** Les composantes sont entières quand la grandeur est discrète (comptes, jetons, durées en ns, coûts en micro-unités), et `Fraction` sinon (Σ conf). La conversion en flottant n'a lieu qu'une fois, à la finalisation.
- **P1.** Les comptes d'édition (S, D, I) sont **canoniques** : parmi les alignements de coût minimal, on retient celui qui maximise S. Comme S+D+I = d et I − D = \|h\| − \|r\|, ce choix fixe les trois comptes. Calcul : d = `Levenshtein.distance(r, h)`, W = `Levenshtein.distance(r, h, weights=(K, K, K−1))` avec K = \|r\|+\|h\|+1, puis S = K·d − W. Le procédé vaut aussi pour les mots (listes). Vérifié contre une DP lexicographique (`p1_departage_canonique.py`, 3 000 cas). Il diffère de jiwer et de `rapidfuzz.editops` sur I et D (« ab »/« ba » : (2, 0, 0) contre (0, 1, 1)), jamais sur S+D+I.

| Famille | Métriques | Statistique `S` | Finalisation | Scalaire indéfini quand |
|---|---|---|---|---|
| Taux d'édition | `cer`, `cer_diplo`, `wer`, `ins_rate`, `del_rate` | (S, D, I, n_réf) canoniques | (S+D+I)/n_réf ; I/n_réf ; D/n_réf | n_réf = 0 |
| MER | `mer`, `cmer` | (S+D+I, n_réf + I) | ratio | deux textes vides |
| Exactitudes | `char_accuracy`, `word_accuracy`, `fca` | (erreurs, n_réf) | max(0, 1 − e/n), plancher **après** combinaison (B1) | n = 0 |
| Appariement P/R/F | `ner_f1`, `ner_f1_exact`, `region_detection`, `bow_*` | (tp, fp, fn) | F1 = 2tp/(2tp+fp+fn) ; P ; R | dénominateur nul |
| Proportions | `searchability`, `diacritic_err`, `mufi_err`, `hcpr`, `air`, `numseq_*`, `unanchored_trigrams`, `*_coverage`, préservation | (k, n) | k/n | n = 0 |
| Texte par région (R2) | `region_cer`, `line_identity_cer` | (éditions sur paires bijectives **+ texte de l'hypothèse non apparié + texte de la référence non apparié**, car. réf.) | ratio | car. réf. = 0 |
| Ordre de lecture (R3) | `reading_order_tau` | (discordantes, paires que la référence ordonne) sur les régions appariées | d/(c+d) | aucune paire |
| Calibration (analyse) | ECE, MCE | (n_b, justes_b) entiers, Σ conf_b en `Fraction`, sur 10 classes fixées par le protocole | ECE = (1/N) Σ_b \|justes_b − Σconf_b\| ; MCE = max sur classes non vides | N = 0 |
| Moyennes | estimande macro, durées, coûts | (Σ x exacte, n) | Σx/n | n = 0 |
| Quantiles (P3) | percentiles par ligne | multi-ensemble des valeurs **du document** ; combinaison = concaténation | quantile, méthode déclarée | vide |

Le bootstrap convertit une fois en float64 les statistiques exactes des documents, dans l'ordre canonique (tri par id), puis somme les lignes tirées. La valeur ponctuelle est exacte ; les réplicats sont déterministes à versions égales (§ 6, B8). Les quantiles tirent des documents (P3).

#### b. Quatre axes par observation (point 3 ; R6, P7)

```
Observation[S] (pipeline × document × vue × métrique)
  applicability : "applicable" | "no_ground_truth" | "not_transcribed" (P7, déclaré par l'importeur) | "not_in_view"
  availability  : "available" | "gt_unreadable" | "output_missing" | "output_unreadable"
                  | "step_failed" | "step_cancelled" | "step_not_reached"       # l'exécution (K3) est une cause
  validity      : "valid" | "partial_output" | "truncated_output" (R6) | motif propre à la métrique
  stat          : S | None            # présente ⇔ axes 1 à 3 au vert ; une statistique partielle est gardée à part (stat_partielle) pour la sensibilité
  scalar, scalar_reason               # axe 4 : finalize(S_d) défini ?
```

- Une page à référence vide est applicable, disponible et valide, avec `scalar=None` pour `zero_denominator` : elle contribue au micro.
- Une page `not_transcribed` est hors des attendus.
- Une sortie `partial` (régions en échec) ou `truncated` n'est **pas** notée par défaut (R6).

#### c. Trois supports (point 4 ; R5, P8)

Pour la vue v, la métrique m et la famille F déclarée par la spec :
- **attendus** = {d : applicable} ;
- **D^μ_P** = {d : stat présente} ;
- **D^M** = {d : la **référence** définit le scalaire}, c'est-à-dire n_réf > 0, ou tp + fn > 0 (R5). Ce support est le même pour tous les pipelines.

Le macro n'est **publié que si**, sur D^M, le scalaire est défini pour toute hypothèse : taux d'édition, MER/cMER, exactitudes, rappels, F1 (tp + fn > 0 suffit), proportions à dénominateur de référence. Il n'est pas publié pour les précisions (`bow_precision`, précision NER), `unanchored_trigrams`, `air` et τ. Sur D^M, un pipeline sans statistique (axes 2 ou 3) sort du support macro, avec son motif.

| Support | Définition | Analyses |
|---|---|---|
| Conditionnel, par pipeline | D^μ_P ; D^M_P = D^M ∩ D^μ_P | agrégats micro et macro d'un pipeline ; couverture ventilée par axe et par motif ; IC marginal étiqueté « conditionnel » |
| Apparié, par paire | D^μ_AB = D^μ_A ∩ D^μ_B ; D^M_AB = D^M ∩ D^μ_A ∩ D^μ_B | Δ micro, Δ macro, leurs IC et p ; Wilcoxon de la paire |
| Global, sur la famille | D^μ_F, D^M_F (∩ sur F) | Friedman et Nemenyi ; **seul tri** multi-pipelines (P8 : les ordres appariés ne composent pas un classement) |
| Sensibilité `empty_page` | attendus ∩ {VT disponible} | toute part manquante notée vide : unité en échec, région en échec, fin tronquée (R6) |

#### d. Estimandes et inférence (points 2 et 10 ; R4, P2, P4, P5, P6)

**Δ micro par famille (R4).** La permutation appariée par changement de signe teste H0 « les étiquettes A/B sont échangeables dans chaque document ». Elle teste R_A = R_B seulement quand le dénominateur est le même pour A et B, c'est-à-dire fixé par la référence. Sinon, la p est obtenue par **inversion du bootstrap apparié** : p = min(1, 2·min(F̂*(0), 1 − F̂*(0⁻))), sur les réplicats mêmes de l'IC, avec H0 : R_A = R_B.

Niveau mesuré sur le scénario de la revue (`r4_bootstrap_niveau.py`, 300 simulations, erreur Monte-Carlo ≈ 0,013) :
- inversion du bootstrap : **0,063** (n = 30 et n = 100) ;
- permutation studentisée, qui demande une linéarisation par famille : 0,067 et 0,063 ;
- permutation non studentisée : **0,30**.

| Famille | Dénominateur | p du Δ micro | IC du Δ micro | Macro publié |
|---|---|---|---|---|
| Taux d'édition | n_réf | changement de signe (H0 : échangeabilité ; niveau témoin 0,044) | bootstrap apparié | oui |
| Proportions à dénominateur de référence ; `bow_recall`, rappel NER ; texte par région | référence | changement de signe | bootstrap apparié | oui |
| Exactitudes (plancher non linéaire) | n_réf | inversion du bootstrap | bootstrap apparié | oui |
| F1 (`ner_f1`, `ner_f1_exact`, `region_detection`, `bow_f1`) | 2tp+fp+fn (hypothèse) | inversion du bootstrap | bootstrap apparié | oui (D^M : tp+fn > 0) |
| MER, cMER | n_réf + I (hypothèse) | inversion du bootstrap | bootstrap apparié | oui (D^M : n_réf > 0) |
| Précisions, `unanchored_trigrams`, `air` | hypothèse | inversion du bootstrap | bootstrap apparié | non |
| τ | paires appariées (hypothèse) | inversion du bootstrap | bootstrap apparié | non |
| ECE, MCE (analyses) | — | aucun test confirmatoire | bootstrap par document | — |

Autres règles :
- **Macro.** Δ^M est la moyenne sur D^M_AB des différences exactes r_A,d − r_B,d. p par changement de signe (statistique linéaire), IC par bootstrap.
- **P2, réplicats dégénérés.** Un réplicat dont la finalisation est indéfinie (Σ dénominateur = 0) est écarté et compté. Au-delà de ε, IC et p sont « non estimables ». La méthode est le percentile (B2).
- **P4, analyses de rangs.** Elles sont publiées sous le nom « analyse de rangs par document », jamais comme test du micro ou du macro :
  - Wilcoxon par paire sur D^M_AB ;
  - Friedman et Nemenyi sur D^M_F, seulement si k ≥ 3 (k = 2 : Wilcoxon seul) ;
  - différences et rangs calculés sur des `Fraction`, converties une fois, donc des ex æquo exacts restent ex æquo ;
  - `zero_method` et `method` déclarés (B5) ;
  - variance nulle : « non calculé », place gardée dans la famille.
- **P5, P6, grappes et répétitions.** Tirages et échanges se font par grappe déclarée ; les grappes sont triées par leur plus petit id de document. Une répétition n'est jamais une unité d'inférence : la grappe d'une répétition est son document. Les statistiques sont sommées par document pour le micro et les scalaires moyennés par document pour le macro. Sous grappes, les rangs portent sur les moyennes par grappe, ou ne sont pas publiés (B3).
- **Famille de Holm (point 10).** Définie par la spec avant exécution, elle ne dépend d'aucun résultat (B4). Un test non calculable y garde sa place (p = 1). Aucun pipeline n'est fusionné à un autre sur ses résultats.

#### e. Échecs

`FailurePolicy = Literal["exclude", "empty_page"]`. `max_error` est retiré. Il n'y a pas d'imputation par défaut, y compris pour `partial` et `truncated` (R6). `UnitOutcome` gagne `partial`. La validation a lieu avant exécution : VT et image lisibles et hachées, pont de projection présent.

| | |
|---|---|
| **Supprime** | `Observation`, `micro_ratio`, `micro_ratio_ci`, `bootstrap_batch`, `_intervals`, `_aggregate`, `_error_rate`, `missed`/`_expects`, `worst`/`_score_failed`, F1 par document, `support ≥ 1`, la famille de Holm « tests calculés », le jugement par `editops` non canonique |
| **Bibliothèques** | `scipy.stats` (`bootstrap`, `permutation_test`, `wilcoxon`, `friedmanchisquare`) ; `rapidfuzz` (distances simple et pondérée) ; `fractions` (stdlib). Oracles : DP lexicographique (S/D/I), jiwer (S+D+I quand Σ n_réf > 0), énumération exhaustive (NER, régions), scipy |
| **Couche** | `evaluation` (3) ; `partial` en `domain/usage.py` (1) ; `not_transcribed` déclaré par l'importeur (`app`, 6) ; validation préalable en `app` |
| **Ne fait pas** | Pas d'algèbre générique, pas de méthode delta pour l'IC, pas de bornes dans `MetricSpec`, pas d'imputation par défaut |

### 2.2 K3 : enregistrement par étape (point 6 ; P9, P10, P14)

```
StepRecord(step_id, outcome ∈ {ok, truncated, partial, failed}, reason, message,
           artifacts, usage, served_models | None (« inconnu » si distant),
           definition (§ 2.3 c), environment (§ 2.3 c), lookup_key, produced_in: (run_id, repetition_id))
DocumentExecution(steps: tuple[StepRecord, ...])      # issue, usage et pool déduits
RunContext.workspace_uri = <ws>/<pipeline>/<step_id>/   # isolation physique
lookup_key(k) = H(partie DÉCLARÉE de la définition de l'étape k (brique, version, réglages envoyés, modèle demandé),
                  [(type, content_hash) des artefacts consommés, triés], [(nom, sha256) des unit_inputs déclarés],
                  repetition_id)
validation(record) : chaque fichier de record.environment se re-hache à l'identique, et chaque sortie --version est identique
RunMode = Literal["fresh", "resume", "rescore"]
```

- **Deux temps (P10).** Les fichiers réellement exécutés ne sont connus qu'après l'exécution. La recherche ne porte donc que sur ce qui est connu avant, et le record trouvé n'est réutilisé que s'il passe la validation. Sinon l'étape est réexécutée et le record est remplacé, dans le cache seulement.
- **Ce qui est réutilisable (P9).** En `resume`, seuls `ok` et `truncated` sont réutilisés (la cause d'une troncature, `max_tokens`, est un réglage envoyé, donc dans la clé). `partial` et `failed` sont retentés. `rescore` relit tout, sans exécuter.
- **Répétitions.** `repetition_id` entre dans la clé. Une répétition ne relit jamais une autre ; chaque observation dit `produced_in` et `reread`.
- **Durabilité (P14, décision rendue).** À la fin de chaque étape, dans cet ordre : `fsync` des blobs ; record écrit dans un fichier temporaire puis `fsync` ; `os.replace` ; `fsync` du répertoire. À l'annulation, la file est arrêtée.
- **Analyses.** `correction`, `decisions` et `economics` lisent l'étape cible et son entrée déclarée, jamais le pool.

| | |
|---|---|
| **Supprime** | `billed`, `DocumentExecution.failed`, « échec ⇒ aucun artefact », reconstruction de l'échec dans l'orchestrateur, `pools`, `_two_stage_pipelines`, `unit_key`, `served_models` stocké, `repetition_dir` comme seul garde-fou |
| **Couche** | `pipeline` (4) pour `StepRecord` ; `app` (6) pour clés, modes et persistance ; `evaluation` (3) pour les consommateurs |
| **Ne fait pas** | Pas de DAG, pas de reprise à l'intérieur d'une étape, pas de record « sautée » |

### 2.3 K4 : identité calculée ; cache et archive séparés (points 7 et 9 ; R9, R10, P11-P13, P15)

#### a. Intégrité, pas authenticité

BagIt vérifie l'intégrité ; il ne garantit ni l'immuabilité ni l'authenticité. Conséquences :
- Cinoc n'écrit jamais dans une archive scellée et la vérifie à chaque lecture ;
- l'authenticité tient à l'empreinte du `tagmanifest`, publiée hors de l'archive et comparée quand elle est fournie ;
- la signature est hors 1.0 (O9).

#### b. Mutualisation (P13)

| Mécanisme | Risque | Règle |
|---|---|---|
| Lien dur | une écriture en place altère toutes les copies ; impossible entre systèmes de fichiers ; invisible pour un test de lien symbolique (`st_nlink = 2`) ; le mode 0444 n'arrête pas root | seulement sur option ; sinon, `st_nlink > 1` est refusé comme un lien |
| Reflink (copie-sur-écriture) | dépend du système de fichiers | par défaut quand il est disponible |
| Copie | place | repli |
| Tous | un blob altéré touche chaque archive qui le partage | re-hachage à chaque lecture d'une archive scellée |

#### c. Identité d'exécution : définition et environnement (R9, R10, P10, P11, P15)

```
StepDefinition (portable) :
  brique, version déclarée, réglages ENVOYÉS, modèle demandé, served_model | inconnu,
  sha256 des SOURCES .py de la brique (sa distribution, ou son sous-paquet first-party), y compris importées paresseusement,
  sha256 des fichiers de poids chargés (P15),
  {distribution tierce chargée : version},
  {binaire : sortie complète de --version}
StepEnvironment (dépend de la plateforme) — instantané du PROCESSUS à la fin de l'étape (R9) :
  sha256 de chaque fichier de module hors stdlib présent dans sys.modules (.py, .so, .pyd) ;
  sha256 de chaque bibliothèque partagée mappée (/proc/self/maps sous Linux ; ailleurs « partiel », écrit) ;
  pour chaque binaire lancé : sha256 de l'exécutable et des bibliothèques qu'il charge (ld.so --list / otool -L) (R10) ;
  plateforme, implémentation et version de l'interpréteur
```

- L'instantané est une **sur-approximation** : il contient aussi ce que d'autres étapes ont chargé. Il ne dépend donc ni de l'ordre des étapes ni de l'ordre des documents. Il est mémoïsé par run.
- Il sert à **valider** le cache (§ 2.2) et à **qualifier** une reproduction. Il ne fait jamais partie de l'identité de définition.
- Les bibliothèques ouvertes par `dlopen` dans un sous-processus échappent à `ld.so --list` : la limite est écrite (O4).

#### d. Protocole, corpus, observation (R9, P11, P12)

```
ProtocolDefinition (portable) = H(spec de vue, définition de chaque métrique (famille, finalisation, règle canonique P1, version de définition),
                                  contenu du profil de normalisation, unicodedata.unidata_version,
                                  sha256 des sources .py de cinoc.evaluation et cinoc.formats chargées)
ProtocolEnvironment = extensions compilées chargées (rapidfuzz, numpy, scipy…), leurs versions, plateforme
CorpusIdentity      = H(liste triée de (id, sha256 image, {type: sha256 VT}))          # séparée (P12)
ObservationId       = H(sha256 de la sortie notée, sha256 de la VT DE CE document, ProtocolDefinition)
```

| Opération | Exécute | Résultat exigé | Coûts publiés |
|---|---|---|---|
| Relecture des observations | rien | octets identiques, hors horodatages | historiques, attribués à leur run |
| Reproduction sous **définition** identique | évaluation (et moteurs en rejeu) | mêmes statistiques et scalaires (arithmétique exacte, P1 canonique), **quel que soit l'environnement** ; un environnement différent est publié comme qualification. IC et p identiques seulement à environnement égal (B8) | coûts du rejeu séparés |
| Réévaluation sous nouvelle définition | évaluation | nouvelles identités, filiation vers l'archive, jamais sous l'identité d'origine | aucun coût moteur |

#### e. Archive (P13)

```
Archive = sac BagIt dont TOUT le contenu est sous data/ (objects/<sha>, ground_truth/<sha>, spec.json, run_result.json, observations) ;
lecture = bagit.Bag.validate() + refus de tout fichier hors des manifestes et des fichiers de tags standard
          + refus des liens (symboliques, ou st_nlink > 1 hors option) + refus de fetch.txt + empreinte racine comparée à l'ancre
read_verified(artifact) ; BlobStore (reflink > copie ; lien dur sur option) ; Cache = BlobStore + index mutable {lookup_key: StepRecord}
GroundTruthRef.content_sha256, DocumentRef.image_sha256, RunManifest.corpus (CorpusSpec avec empreintes)
```

| | |
|---|---|
| **Supprime** | `_rebased`, `_store_image`, `binaries.json`, rôle d'archive du `ResumeStore`, téléchargement hors ligne, clé lisant l'image du corpus, `RECORD` comme preuve |
| **Couche** | empreintes en `domain` (1) ; `StepDefinition`/`StepEnvironment` en `pipeline` (4) ; `ProtocolDefinition` en `evaluation` (3) ; `BlobStore` et archive en `app` (6), avec `bagit` (décidé) |
| **Ne fait pas** | Pas d'OCFL, pas de signature en 1.0, pas de RO-Crate, pas de `fetch.txt` |

### 2.4 K5 : appariement unique, régions et empans (point 8 ; R3, R8, R11, P16-P20)

#### a. Objectif

Un seul appariement sert les boîtes de régions et les empans NER (P20, R8). L'admissibilité est en arithmétique exacte (P17) : 2·\|∩\| ≥ \|∪\| (ou > selon O2), en entiers dans un repère commun, en `Fraction` si les dimensions des pages diffèrent. Le calcul se fait page par page.

1. **Filiation vérifiée (R11).** Trois conditions, toutes requises :
   - la chaîne de `StepRecord` de l'hypothèse a consommé l'artefact de la VT (même `content_hash`) ;
   - chaque étape de la chaîne est déclarée `preserves_region_ids` ;
   - la paire (même id, même page) est **admissible**.

   Une paire qui remplit les trois est retenue en priorité. Un id ne crée jamais une paire non admissible. Une transformation géométrique déclarée (redressement) n'est pas prise en compte en 1.0 (O13).
2. **Sinon, et pour le reste**, l'appariement bijectif maximise, dans l'ordre lexicographique :
   1. le nombre de paires admissibles ;
   2. Σ IoU ;
   3. Σ distance d'édition des textes appariés, quand il y a du texte (P16) ;
   4. puis l'ordre géométrique canonique (page, y0, x0, y1, x1).

   Aucun identifiant n'intervient. La structure de poids (n+1)·[adm] + IoU·[adm] est validée par la revue pour les critères 1 et 2.

   **Calcul exact** : un poids **entier** unique, où chaque critère est multiplié par une borne strictement supérieure au maximum de tous les suivants :
   - [adm] ;
   - IoU ramenée au dénominateur commun des unions ;
   - −Σ distance d'édition.

   L'affectation hongroise se fait en entiers Python (O(n³) par page). `linear_sum_assignment`, qui travaille en flottants, ne peut garantir l'ordre lexicographique quand il faut départager sur le texte des ex æquo exacts d'IoU. Il reste l'oracle sur les instances sans ex æquo, avec l'énumération exhaustive sur les petites.
3. **Héritage.** Sous filiation, `region_detection` (et les fusions et scissions) sont `not_applicable` (`regions_inherited`) : le pipeline n'a rien segmenté. `line_identity_*` ne s'appliquent que sous filiation vérifiée des lignes (P19).

#### b. Ordre partiel (R3)

`LayoutPage.reading_order: tuple[str | OrderGroup, ...]`, avec `OrderGroup(ordered: bool, members)`. C'est un changement de domain (couche 1), mappé depuis les `OrderedGroup`/`UnorderedGroup` de PAGE (ALTO n'a que des groupes ordonnés). La référence ordonne (a, b) seulement à travers un groupe ordonné. La projection en texte linéarise un groupe non ordonné dans l'ordre de déclaration du fichier.

#### c. Fusions et scissions (P18)

Ce sont des relations distinctes de la bijection, calculées sur les matrices IoGT et IoDT avec le seuil θ_m. Elles sont publiées comme comptes et ne modifient pas tp/fp/fn. Une région de VT qui en recouvre une autre rend ses relations `not_applicable` (`ref_overlap`), et ce nombre est publié. La justification par Kirillov et al. est retirée.

| | |
|---|---|
| **Autres** | `formats.layout_text` est l'unique projection. Le fan-out refuse un layout multipage à image unique (décidé). La calibration juge par alignement (si O3) |
| **Supprime** | `_greedy_pairs`, `_true_positives`, `correspondance` « id d'abord », `_ids_partages`, branche id de `_ordres`, `_identified_boxes`, `_region_texts` global, une projection, `_judge`, `align_entities` glouton, IoU relative flottante |
| **Couche** | appariement en `evaluation` (3) ; ordre partiel en `domain` (1) et parseurs en `formats` (2) ; `preserves_region_ids` déclaré dans le `Module` (4) |

### 2.5 Bilan de lignes

Indicatif seulement ; il n'a motivé aucun choix. L'ordre de grandeur est un total nul, à ±50 %.

---

## 3. Invariants

Vérification :
- **P** = propriété (`hypothesis`, extra `dev`, profil déterministe) ;
- **O** = oracle externe ;
- **A** = test adversarial.

La colonne **Revue** nomme le contre-exemple de `rapports/revue_contre_exemples/` que l'invariant doit satisfaire. Il est porté en test adversarial rouge au premier commit de la tranche indiquée (T).

### Par métrique (M) (point 5)

| # | Invariant | Vérif. | Revue | T |
|---|---|---|---|---|
| M1 | **Taux d'édition.** (S, D, I) canoniques (max S), égaux à la DP lexicographique. CER/WER micro égaux à jiwer quand Σ n_réf > 0 (S+D+I seulement). Une page à référence vide ajoute \|h\| au numérateur, avec scalaire `zero_denominator`. Corpus entièrement vide : micro indéfini pour tous, écart volontaire à jiwer (qui rend 3 et 0), Σ insertions publiée. `not_transcribed` est hors des attendus. | P ; O DP, jiwer | `k1_editops_egalites.py` | 1a |
| M2 | **Exactitudes** : max(0, 1 − Σe/Σn), jamais une moyenne de planchers. | P | — | 1a |
| M3 | **F1/P/R, agrégation** : F1(Σtp, Σfp, Σfn) ; un document sans référence contribue ses fp ; une catégorie présente seulement en prédiction a P = 0, R indéfini, sans erreur ; tout vide : indéfini. Oracle : énumération par IoU d'empan, règle de Cinoc ; pas nervaluate. (La propriété d'appariement relève de M8.) | P ; O énumération | `k1_ner_oracle_nervaluate.py` | 1a |
| M4 | **Texte par région** : le numérateur compte les éditions sur paires, le texte d'hypothèse non apparié et le texte de référence non apparié ; perdre une région n'est jamais mieux noté qu'une coquille. `line_identity_*` sont `not_applicable` sans filiation. | P | `k1_region_cer_reference_non_appariee.py` | 4 |
| M5 | **τ** : seules les paires que la référence ordonne comptent ; les paires d'un groupe non ordonné sont exclues ; avec un ordre total sans ex æquo, la valeur égale (1 − τ)/2 de scipy. | P ; O scipy | `k1_tau_groupe_non_ordonne.py` | 4 |
| M6 | **ECE/MCE** : pour toute partition et tout ordre des documents, l'histogramme combiné est égal (`==`) à celui des jetons poolés, et l'ECE identique bit à bit. | P | `k1_fsum_non_associatif.py` | 1a |
| M7 | **Projection unique** : un layout identique donne un CER nul sous toute vue. | P | — | 4 |
| M8 | **Appariement** (régions et empans NER) : optimum lexicographique égal à l'énumération exhaustive ; admissibilité exacte, indépendante de la largeur de page ; invariant par permutation et par renommage sans filiation ; une filiation déclarée sans paire admissible ne crée aucune paire ; `region_detection` `not_applicable` sous héritage ; fusions et scissions hors bijection, `ref_overlap` signalé. | P ; O énumération, `linear_sum_assignment` | `k5_filiation_declaree.py`, `k5_objectif_lexicographique.py`, `k5_seuil_iou_flottant.py` | 4 |

### Par analyse (A)

| # | Invariant | Vérif. | Revue | T |
|---|---|---|---|---|
| A1 | **Agrégat conditionnel** sur D^μ_P et D^M_P, couverture ventilée par axe ; plus d'échecs, de régions perdues ou de troncatures ne l'améliorent jamais sans que la couverture le dise ; aucune part manquante n'est notée par défaut. | P ; A | `k2_partial_impute_en_silence.py` | 1b |
| A2 | **Quatre axes** : attendus = applicables ; `not_transcribed` distinct d'une référence vide ; statistique présente ⇔ axes 1 à 3 au vert ; `partial_output` et `truncated_output` à l'axe 3. | P ; A | `k2_partial_impute_en_silence.py` | 1b |
| A3 | **Δ micro** : inférence de la famille (§ 2.1 d) ; sous H0 R_A = R_B, taux de rejet ≤ α + 3 erreurs Monte-Carlo pour chaque famille ; réplicats dégénérés écartés et comptés, « non estimable » au-delà de ε. | P (simulation par famille) ; O scipy | `k1_permutation_ratio_niveau.py`, `k1_permutation_cer_temoin.py`, `k1_bootstrap_denominateur_nul.py` | 1a |
| A4 | **Δ macro** sur D^M_AB avec D^M fixé par la référence : il voit l'hallucination d'un document sans référence ; pas de macro publié pour les familles dont le scalaire dépend de l'hypothèse. | A ; O scipy | `k2_support_macro_depend_du_pipeline.py` | 1a |
| A5 | **Analyses de rangs** : nommées comme telles ; `zero_method` et `method` déclarés ; ex æquo exacts préservés ; Friedman seulement si k ≥ 3 ; variance nulle → « non calculé » avec place gardée. | O scipy ; A | `k1_rangs_ex_aequo.py` | 1a |
| A6 | **Classement** : deux pipelines ne s'ordonnent que sur leur support apparié ; aucun classement n'est composé à partir des ordres appariés ; seul le support global trie. | A | `k2_ordres_apparies_intransitifs.py`, `k2_support_macro_depend_du_pipeline.py` | 1b |
| A7 | **Échecs** : aucune imputation par défaut ; `empty_page` note vide toute part manquante (unité, région, fin tronquée) et porte ce nom. | A | `k2_partial_impute_en_silence.py` | 1b |
| A8 | **Grappes** : grappes triées par leur plus petit id ; en singletons, l'IC est identique bit à bit à l'IC par document ; deux groupements donnent deux IC ; une répétition n'est jamais une unité d'inférence. | P ; A | `k1_grappes_singletons_ordre.py` | 1a |
| A9 | **Famille de Holm** définie par la spec ; un test non calculable, ou à variance nulle, garde sa place. | P | `k1_rangs_ex_aequo.py` (cas 2) | 1a |
| A10 | **Rééchantillonnage** invariant par permutation de l'ordre des documents de la spec. | P | — (violé : [0,0953 ; 0,7596] → [0,1032 ; 0,7403]) | 1a |
| A11 | **Analyses d'une vue** : étape cible et son entrée déclarée seulement. | A | — | 2 |
| A12 | **Coûts** : coût d'un préfixe ; facture de l'étape fautive comptée ; coûts historiques jamais additionnés aux coûts du rejeu. | A | — | 2, 3 |
| A13 | **Quantiles par ligne** : on tire des documents ; couverture de l'IC de la médiane proche du nominal avec un effet de page. | P (simulation) | `k1_quantiles_grappes.py` | 1a |

### Identité, provenance, archive (I)

| # | Invariant | Vérif. | Revue | T |
|---|---|---|---|---|
| I1 | **Identité d'exécution** : modifier un fichier chargé dans le processus (même importé par une autre étape, ou paresseusement), une bibliothèque partagée, une bibliothèque d'un binaire, un fichier de poids ou un réglage envoyé interdit la réutilisation. L'environnement enregistré ne dépend ni de l'ordre des étapes ni de celui des documents. La version du paquet et les réglages opérationnels n'entrent pas dans la définition. | A | `k4_fichiers_executes_sys_modules.py`, `k4_binaire_bibliotheque_partagee.py` | 3 |
| I2 | **Identité du corpus** : un octet changé d'une image ou d'une VT change `CorpusIdentity`. | A ; P | — | 3 |
| I3 | **Identité du protocole** : `ProtocolDefinition` est la même sur deux plateformes aux mêmes sources ; corriger la VT de d2 ne change pas l'`ObservationId` de d1 ; changer de profil, de métrique ou de version Unicode change la définition. | A | `k4_observation_id_depend_du_corpus.py`, `k4_protocole_depend_de_la_plateforme.py` | 3 |
| I4 | **Relecture** : octets identiques. | P | — | 3 |
| I5 | **Reproduction** : à définition identique, statistiques et scalaires identiques quel que soit l'environnement, l'écart d'environnement étant publié ; réévaluation = nouvelles identités avec filiation. | A | `k4_protocole_depend_de_la_plateforme.py` | 3 |
| I6 | **Intégrité** : refus d'une archive altérée, d'un fichier non listé (même ajouté à la racine), d'un lien symbolique ou dur hors option, d'un `fetch.txt`, ou d'une empreinte racine différente de l'ancre. Aucune authenticité revendiquée au-delà. | O `bagit` ; A | `k4_bagit_fichiers_hors_manifeste.py` | 3 |
| I7 | **Provenance** par unité et par étape (servi ou « inconnu »). | A | — | 2 |

### Fonctionnels (F)

| # | Invariant | Vérif. | Revue | T |
|---|---|---|---|---|
| F1 | **Isolation physique** + empreinte vérifiée. | A | — | 2, 3 |
| F2 | **Conservation de l'amont**. | A | — | 2 |
| F3 | **Reprise** : clé de recherche sur les artefacts consommés ; validation sur l'environnement ; en `resume`, un record `partial` ou `failed` est retenté, même après un réglage opérationnel relevé. | A | `k3_reprise_record_non_ok.py`, `k4_fichiers_executes_sys_modules.py` | 2, 3 |
| F4 | **Répétitions indépendantes**. | A | — | 2 |
| F5 | **Durabilité** : panne simulée après chaque appel de la séquence `fsync`/`replace` (système de fichiers factice, panne externe) ; jamais de record pointant un blob absent ou partiel. | A | — (argument P14) | 2 |
| F6 | **Relecture autonome** : ni réseau ni corpus. | A | — | 3 |
| F7 | **Archive scellée** jamais écrite ; un blob partagé altéré en place est détecté dans chaque archive qui le partage ; le mode 0444 n'est jamais compté comme une protection. | A ; O `bagit` | `k4_bagit_fichiers_hors_manifeste.py` | 3 |
| F8 | **Refus avant de payer**. | A | — | 1b |
| F9 | **Parité** des capacités nouvelles. | garde existante | — | 3 |

**37 invariants** (8 M, 13 A, 7 I, 9 F).

- **Revus par la révision 2 :**
  - les 10 « faux » de la revue : M1, M3, M4, M5, M6, M8, A3, A4, A7, I1 ;
  - les 10 « à préciser » : A2, A5, A6, A8, I3, I5, I6, F3, F5, F7.
- **Nouveau :** A13 (P3).
- **Changent de tranche :** M4, M5 et M7 passent en tranche 4 (ils dépendent de l'appariement et de l'ordre partiel). M3 garde l'agrégation en 1a ; son appariement passe à M8.

---

## 4. Tests

### 4.1 À reformuler avant correction

| Test | Conv. | Attendu reformulé |
|---|---|---|
| `reference_vide_nest_pas_comptee_notee` (valide) | T1 | Micro de A = 12/120 = 0,100. Les 6 pages blanches sont au support micro et hors de D^M (n_réf = 0) : 12 au micro, 6 au macro. |
| `test_omnibus__meme_sens_que_le_cer_micro_affiche` | C05 | Le test du Δ micro du CER (changement de signe) va dans le sens du Δ micro ou n'est pas significatif (p = 1). Le Wilcoxon n'est publié que comme analyse de rangs. |
| `test_omnibus__p_du_ratio_micro_par_permutation_appariee` | C05 | p corrigée du Δ micro ≥ α et égale au changement de signe exact de scipy (1,0). |
| `intervalles__meme_documents_que_le_test` | C06 | L'IC du Δ porte sur D^μ_AB ; les IC marginaux sur le support conditionnel, étiquetés ainsi. |
| `echec_non_aleatoire__classement_sur_documents_communs` | C07 | Sur le support apparié, B (0,040) est devant A (0,050). Aucun ordre entre supports différents ; couverture 7/8 de A publiée. |
| `max_error__un_echec_ne_note_jamais_mieux_quune_reponse` | C08 | Aucune imputation par défaut (couverture 2/3). Sous `empty_page`, l'échec vaut la valeur de l'hypothèse vide (CER 1,0). |
| `bootstrap__grappes_documentaires_declarables` | C09 | Deux groupements, deux IC ; en singletons, IC identique bit à bit à l'IC par document. |
| `version_manuelle__brique_modifiee_sans_relever_sa_version_reexecutee` | C17 | Deux modules aux sources différentes, de même nom et de même version, ont deux définitions. Un fichier chargé par une autre étape puis modifié fait échouer la validation. |
| `identite_saknussemm__prompt_et_temperature_envoyes_au_llm_sont_traces` | C17 | La définition change quand le prompt ou la température envoyés changent, et pas pour un réglage opérationnel. |

À recibler sans changer l'attendu : `reference_vide_nentre_pas_dans_le_test_apparie` (p = 0,031, lue dans l'analyse de rangs) ; `pipeline_non_applicable…` (Wilcoxon de la paire).

### 4.2 Tests qui figent un défaut

À inverser dans le commit du correctif.

| Test | Défaut figé | T |
|---|---|---|
| `test_metrics_text.py::test_cer_weight_is_reference_length` | page blanche hors du micro | 1a |
| `test_micro_interval.py::test_zero_weight_documents_weigh_nothing` | idem pour l'IC | 1a |
| `test_inference_scipy_parity.py` (`family_size == len(computed)`) ; `test_inference.py::test_not_computed_says_why` (`family_size == 0`) | famille dépendante des résultats | 1a |
| `test_unit_outcome.py::test_max_error_is_zero_for_a_higher_is_better_metric`, `::test_max_error_scores_the_failure_like_an_empty_page` | `max_error` ; la seconde devient le test de `empty_page` | 1b |
| `adversarial/applicabilite_echecs/…::test_troncature__notee_attendue_et_signalee` (vert) | troncature notée par défaut (R6) ; devient le test de `empty_page` | 1b |
| `adversarial/applicabilite_echecs/…::le_type_interdit_bien_les_artefacts_dune_unite_failed` (vert) | « échec ⇒ aucun artefact » | 2 |
| `test_appariement_geometrique.py::test_identifiants_partages_inchanges` | id prioritaire sans filiation | 4 |
| `test_calibration.py::test_analysis_scores_tokens_against_reference_multiset` | multi-ensemble (si O3) | 4 |

### 4.3 À écrire, rouges d'abord

**Les 23 scripts de la revue**, portés dans la tranche indiquée au § 3.

S'y ajoutent :
- M1 (corpus entièrement vide) ;
- A10 (ordre des documents) ;
- A3 (niveau par famille, simulation) ;
- A12 (historique contre rejeu) ;
- I7 (distant sans modèle servi) ;
- F2 (annulation) ;
- F4 (même dossier) ;
- F5 (panne simulée) ;
- F9 (entrées de parité) ;
- M8 (filiation **vérifiée** conservée) ;
- les propriétés P de M1 à M8, A1, A2, A8, A9, A10, A13, I2, I4 et F3.

---

## 5. Tranches

Le premier commit d'une tranche ne contient que des tests rouges. 1a et 1b partagent la conception du § 2.1. La tranche 4 ne dépend que de 1a et 1b.

| Tranche | Invariants | Critère de fin |
|---|---|---|
| **1a · Statistiques et inférence** (K1) | M1, M2, M3, M6, A3, A4, A5, A8, A9, A10, A13 | Invariants établis contre les oracles. Prévisions vérifiées en re-notant les deux `RunResult` commités : CER/WER micro BNL et Dresden inchangés ; `char_accuracy` Dresden E5 de 0,3125 à 0 ; Δ micro E5−E0 BNL, IC [−0,041 ; −0,010]. |
| **1b · Axes et supports** (K2) | A1, A2, A6, A7, F8 | Invariants établis. Dresden E5 publié « conditionnel 4/10 », avec la page tronquée 177 hors du défaut et dans `empty_page`. Amendement CLAUDE.md §3 (B6). |
| **2 · Étape** (K3) | A11, A12 (préfixe), I7, F1, F2, F3 (recherche, réutilisabilité), F4, F5 | Socle `tesseract → deskew → tesseract` : chaque vue garde sa lecture. Une panne simulée ne perd aucune étape payée. |
| **3 · Identité et archive** (K4) | I1 à I6, A12 (historique/rejeu), F3 (validation), F6, F7, F9 | Une archive de campagne est scellée, validée, relue, reproduite sous la même définition, réseau et corpus retirés. Son empreinte racine est publiée. |
| **4 · Correspondance** (K5) | M4, M5, M7, M8 | Optimum égal à l'énumération ; ordre partiel représenté ; NER sous l'appariement unique ; CER par région E1/E3/E4 re-notés. |

---

## 6. Ce qui reste ouvert (liste fermée)

### Bloquants pour la tranche 1 (K1 + K2)

| # | Question | Recommandation |
|---|---|---|
| B1 | **C02** : plancher des exactitudes après combinaison, ou pas de plancher (ISRI) | plancher au corpus ; macro à part |
| B2 | **IC bootstrap** : méthode et taux ε de réplicats dégénérés | percentile (BCa est indéfini avec des réplicats infinis) ; ε = 1 %, au-delà « non estimable » ; 9 999 réplicats |
| B3 | **C09 + P6** : déclaration des grappes, seuil « non estimable », rangs sous grappes | champ déclaré par le corpus ; seuil à chiffrer (BNL : 5 grappes, dont un singleton) ; rangs sur moyennes par grappe, sinon non publiés |
| B4 | **Famille de Holm par défaut** (a priori) | toutes les paires de la spec × métriques établies × vues × {micro, macro publié} ; analyses de rangs hors de la famille confirmatoire |
| B5 | **Paramètres des rangs** (`zero_method`, `method`) | `zero_method="wilcox"`, `method="auto"` (exact si n ≤ 50 sans zéro ni ex æquo, sinon approximation), écrits dans la définition du protocole |
| B6 | **Amendement CLAUDE.md §3** (« niveau absent → `None` ») | VT absente → `no_ground_truth` ; VT non transcrite → `not_transcribed` ; niveau absent de l'hypothèse → statistique valide (texte vide) ou indisponible, avec motif ; `partial` |
| B7 | **C07** : tri par défaut du tableau | aucun tri entre supports différents ; tri sur le support global de la famille, avec couverture |
| B8 | **H3** : IC et p dépendants des versions de numpy et scipy | accepter « identiques à environnement égal » ; les statistiques et scalaires restent exacts et portables (I5) |

### Autres (tranches 2 à 4 ou publication)

| # | Question | Recommandation |
|---|---|---|
| O1 | **C04** : lignes fantômes | insertions comptées |
| O2 | **C10 + P20** : seuil inclusif ou strict, unique pour boîtes et empans ; θ_m | inclusif (2·\|∩\| ≥ \|∪\|), la convention actuelle de NER et des régions, en arithmétique exacte ; θ_m = 0,5 |
| O3 | **C11** : jugement d'un jeton en calibration | alignement LCS |
| O4 | **C17** (résiduel) : stdlib et interpréteur, `dlopen` des sous-processus | stdlib non hachée, version de l'interpréteur dans l'environnement ; limite `dlopen` écrite |
| O5 | **C19** : plan d'expérience | témoin obligatoire ; `max_tokens` aligné ou montré non limitant ; recopie `repetition-1 → 2…5` retirée |
| O6 | **H2** : `shapely` | boîtes, faute de consommateur exigeant des polygones |
| O7 | **H4** : images IIIF | empreinte obligatoire, octets selon la licence |
| O8 | **H5** : faces des capacités d'archive et des modes | options de `cinoc run` ; web `front-absent` déclaré |
| O9 | **Authenticité** | ancrage de l'empreinte racine en 1.0 ; signature hors 1.0 |
| O10 | **Mutualisation** par défaut | reflink, sinon copie ; lien dur sur option |
| O11 | **Archives S30/S31** | script de conversion ponctuel hors produit, ou réexécution des parties gratuites |
| O12 | **Séparateur de blocs** de la projection unique | `\n` |
| O13 | **Filiation sous transformation géométrique déclarée** (redressement, recadrage) | hors 1.0 : sans paire admissible, pas de filiation |
