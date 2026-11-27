# Synthèse de conception : cinq contrats à remplacer (contre-expertise `04a1c17b`)

Ce document fait suite à `README.md`, `CONVENTIONS.md`, `BIBLIOTHEQUES.md` et `rapports/*.md` de ce dossier. Il ne corrige rien et n'écrit aucun code. Il ramène les 90 défauts confirmés (51 `valide`, 39 `discutable`) à cinq contrats fautifs, et donne pour chacun :
- le contrat qui le remplace ;
- les invariants qui jugeront la correction ;
- l'ordre des corrections ;
- la liste fermée de ce qui reste à arbitrer.

**Règles suivies** (consigne du mainteneur) :
- chaque cause remplace un contrat existant, en place ; aucune couche ni aucun plan nouveau ;
- bibliothèque mature d'abord ;
- tests avant correctifs ;
- une tranche est finie quand ses **invariants** sont établis, pas quand un compte de tests passe au vert ;
- la cohérence des contrats n'est jamais sacrifiée à une contrainte de taille ou de dépendance. Le bilan de lignes (§ 2.5) est indicatif et n'a décidé d'aucun choix.

## Révision n° 1

| Point du mainteneur | Section modifiée |
|---|---|
| 1. Statistiques suffisantes propres à chaque métrique, combinaison et finalisation | § 2.1 a (table par famille) |
| 2. Micro et macro, chacun avec son inférence appariée ; les rangs sont des analyses distinctes | § 2.1 d ; invariants A3, A4, A5 |
| 3. Quatre axes ; une contribution au micro avec un ratio individuel indéfini | § 2.1 b ; invariants A1, A2 |
| 4. Supports conditionnel, apparié et global, et l'analyse qui utilise chacun | § 2.1 c ; invariants A1, A5, A6 (ex-S6 et S9) |
| 5. Pas de monotonie universelle ; propriétés par métrique ; corpus de références vides | § 3 M1 à M8 (ex-S4 supprimé) |
| 6. Clé de reprise sur les artefacts consommés ; répétitions indépendantes | § 2.2 ; invariants F3, F4 |
| 7. Intégrité et non authenticité ; risques des liens physiques ; fichiers réellement exécutés | § 2.3 a, b, c ; invariants I1, I6, F7 |
| 8. Objectif d'appariement lexicographique ; filiation démontrée ; bijection contre fusions et scissions | § 2.4 ; invariant M8 |
| 9. Relecture, reproduction et réévaluation ; coûts historiques contre coûts du rejeu | § 2.3 d ; invariants I4, I5, A12 |
| 10. Familles de Holm définies a priori, sans fusion sur résultats identiques | § 2.1 d ; invariant A9 (remplace l'ex-N4) |
| Décisions rendues | ci-dessous, retirées du § 6 |
| K1 et K2 conçus ensemble | § 2.1 (une seule section) ; tranches 1a et 1b (§ 5) |

### Décisions rendues (intégrées)

| Décision | Effet dans ce document |
|---|---|
| BagIt validé | `bagit` en dépendance de base et dans `LAYERS["app"]` (ex-H1) |
| Hypothesis validé | extra `dev`, profil déterministe (§ 3) |
| Plancher SciPy relevé | `scipy>=1.15`, pour `rng=` (ex-H7) |
| Rupture explicite du schéma `RunResult` | schéma v6 restructuré ; un JSON antérieur est refusé et se re-note depuis son archive (ex-N2) |
| Enregistrements par étape | `StepRecord` (§ 2.2) |
| Persistance atomique immédiate | chaque `StepRecord` est écrit dès la fin de son étape (§ 2.2, F5 ; ex-N9) |
| RO-Crate reporté à la publication scientifique | hors 1.0 (ex-H6 et H8) |
| Refus du fan-out multipage à image unique en 1.0 | invariant F8 (ex-C16) |

---

## 1. Causes communes

### 1.1 Les cinq contrats

| # | Contrat fautif (actuel) | Pourquoi il produit plusieurs symptômes | Arbitrages servis | Tests V / D |
|---|---|---|---|---|
| **K1** | **L'observation est un ratio et un poids, pas une statistique suffisante.** `Observation(value, weight)` (`evaluation/metric.py:22`). L'agrégat est Σv·w/Σw (`runner.py:307-327` → `inference.py:166`). Les IC sont calculés par pipeline sur les couples (v, w) (`inference.py:182-271`). `_error_rate` vaut 0 ou 1 sur dénominateur nul (`metrics/text.py:114`). | Aucun poids ne reconstruit un F1. Un dénominateur nul perd son numérateur (page blanche). Un plancher par page n'est pas un plancher du corpus. Rien ne vérifie que le poids est le dénominateur (τ). Faute de statistiques, aucun Δ micro apparié ni aucune grappe n'est possible. **14 métriques sur 29** sont fausses pour cette seule raison. | **2**, **1** | V 9 · D 10 (C01, C02×3, C03, C04, C05×2, C06 `ic_apparie`, C09) |
| **K2** | **La non-mesure n'a ni axe ni motif ; « attendu » et support dérivent de l'échec d'exécution.** `MetricScore.value=None` (`evaluation/result.py:31-46`). `missed` n'est incrémenté que dans la branche `failed` (`runner.py:146-160`). Cinq endroits rendent `None` sans motif : `runner.py:519-538` et `:555-575`, `metrics/layout.py:92`, `pipeline/fanout.py:230-235`, et `support ≥ 1` à `analysis.py:960`. Le support est implicite et diffère entre agrégat, IC et test (`inference.py:116-122`). `max_error` est déduit de `higher_is_better` (`runner.py:409`). | `None` code six situations. Une unité réussie mais inexploitable sort des deux compteurs. Un pipeline non applicable vide les tests des autres. Un échec non aléatoire fait gagner. La valeur imputée à un échec dépend du signe de la métrique, pas de sa définition. | **3**, **8**, **1** (support) | V 8 · D 6 (C06 `meme_documents`, C07, C08×2, C13×2) |
| **K3** | **L'étape n'est pas l'unité d'enregistrement.** L'issue est portée par l'unité : `DocumentExecution` (`pipeline/types.py:73-142`) impose « échec ⇒ aucun artefact » (`:96-99`), et `billed` y remplace toute la consommation (`:111-112`). L'orchestrateur reconstruit un échec nu (`orchestrator.py:333-347`). Le workspace est par pipeline (`orchestrator.py:233-243` → `adapters/_workspace.py:23-28`). L'usage est par unité (`result.py:82`). La clé de reprise est par unité (`resume.py:130`). Les analyses lisent le pool final (`runner.py:131-138`). | Faute de coordonnée « étape », l'échec aval efface l'amont réussi (artefacts, coût, évaluabilité, reprise). Deux étapes de même label s'écrasent. `correction` et `decisions` jugent la dernière étape. Une vue de préfixe est facturée au coût du pipeline entier. | **4**, **8** (opérationnel), **7** (provenance par unité) | V 13 · D 5 (C12×3, C18×2) |
| **K4** | **L'identité est déclarée, jamais calculée ni vérifiée ; le cache tient lieu d'archive.** `content_hash` n'est jamais relu (`resume.py:296-301`, `:316-324`, `representations.py:37`). L'empreinte d'étape hache une version saisie à la main (`pipeline/fingerprint.py:72`, `:18`). `GroundTruthRef` n'a pas d'empreinte (`domain/documents.py:22-32`). Le manifeste ne garde que `corpus_name`/`n_documents` (`domain/run.py:90-91`). L'empreinte d'image est jetée (`resume.py:150-172`). `ResumeStore` porte deux rôles (`resume.py:205-219`). `_rebased` suit les chemins absolus et les liens (`:187-200`). La relecture hors ligne télécharge (`orchestrator.py:246-268`). | Ce qui est déclaré ne se vérifie pas. Une sortie altérée, un index modifié, une GT remplacée ou une brique corrigée sans nouvelle version passent sans trace, et une reprise réécrit l'archive publiée. | **5**, **7**, **4** (intégrité) | V 9 · D 9 (C14×4, C15×3, C17×2) |
| **K5** | **La correspondance est une égalité de clé, pas un alignement global.** « Id d'abord, en bloc » (`metrics/layout.py:232-265`, `:256` ; `_ordres` `:372-392`). Glouton dans l'ordre du fichier (`:172-195`). Pages aplaties (`:145`, `:202`, `:49`). Deux projections `LAYOUT → texte` (`evaluation/projectors.py:30-67` contre `adapters/layout/to_text.py:31-86`). Fan-out à image unique (`fanout.py:67,101`). Multi-ensemble de mots en calibration (`calibration.py:126`). | Un id partagé par hasard (`r1…rN`, `region_N`), un mot répété ou une position dans le fichier tiennent lieu de preuve d'homologie. Le résultat dépend de l'ordre de sérialisation et apparie entre pages. | **6** | V 12 · D 5 (C10×2, C11×2, C16) |
| — | Plan d'expérience (aucun type « comparaison », `provenance_campagne.md`). | Décision de méthode, pas de code. | — | D 4 (C19) |

Totaux : V 9 + 8 + 13 + 9 + 12 = **51** ; D 10 + 6 + 5 + 9 + 5 + 4 = **39**.

### 1.2 Recoupements

| Arbitrage | K1 | K2 | K3 | K4 | K5 | Lecture |
|---|---|---|---|---|---|---|
| 1 Estimandes, tests appariés, grappes | ● | ◐ | | | | Les estimandes sont des fonctions des statistiques (K1). Leurs supports sont dérivés des axes (K2). |
| 2 Statistiques suffisantes | ● | | | | | |
| 3 Non-mesure typée | ○ | ● | ○ | | | La validité et la définition du scalaire viennent de K1. L'exécution (cause d'indisponibilité) vient de K3. |
| 4 Par étape, isolation, intégrité | | | ● | ◐ | | |
| 5 Archive ≠ cache | | | ○ | ● | | L'archive scelle des `StepRecord` (K3). |
| 6 Appariement | ○ | | | | ● | Les comptes de détection sont des statistiques K1. |
| 7 Empreintes, identité des données, distant inconnu | | | ◐ | ● | | |
| 8 Conditionnel, couverture, supports, opérationnel | ○ | ● | ◐ | | | |

● = cause principale ; ◐ = contribue ; ○ = fournit un ingrédient.

Les arbitrages 3 et 8 n'ont pas de contrat propre : ils découlent de K1 et K2, conçus ensemble (§ 2.1). Les arbitrages 4, 5 et 7 se partagent un objet unique, `StepRecord`, dont K4 calcule et vérifie l'empreinte.

Tests à cheval sur deux causes :
- `a5_*` (K3 puis K4) ;
- C01 (K1, K2) ;
- C12 `la_reprise` (K3, K4) ;
- C18 (K3, K4) ;
- `ner_payload…label_absent` (K2, K1).

### 1.3 Hors des cinq contrats

| Défaut | Rattachement |
|---|---|
| SIGINT : la file n'est pas arrêtée, et des unités sont payées sans être archivées | persistance atomique immédiate (décidée) + arrêt de la file à l'annulation ; tranche 2 |
| saknussemm : délai codé en dur ; unité `ok` alors que toutes ses lignes sont en repli | réglage opérationnel déclaré (K4) + issue `partial` (K2, K3) |
| `dependencies_lock` = métadonnées d'installation | K4 (fichiers réellement exécutés, § 2.3 c) |
| Lignes de layout avec des `\n` (fan-out → saknussemm) | corrigé dans `aba0fe7`, gelé (arbitrage 9) |

---

## 2. Contrats simplifiés

Pseudo-signatures, pas du code.

### 2.1 K1 + K2 : observation, axes, supports, estimandes (conception commune)

#### a. Statistique suffisante propre à chaque métrique (point 1)

Chaque métrique déclare trois choses :
- sa statistique `S` ;
- sa **combinaison** (associative, commutative, avec un élément neutre) ;
- sa **finalisation** `S → float | None`.

La valeur d'un document et l'agrégat micro passent par la **même** finalisation : `micro = finalize(combine(S_d))`.

Il n'y a ni algèbre générique ni registre de monoïdes. Une petite classe de statistique est créée par famille ci-dessous, chacune avec un consommateur, son `+` et ses finaliseurs.

| Famille | Métriques | Statistique `S` | Combinaison | Finalisation | Scalaire indéfini quand |
|---|---|---|---|---|---|
| Taux d'édition | `cer`, `cer_diplo`, `wer`, `ins_rate`, `del_rate` | (S, D, I, n_réf), entiers (`rapidfuzz.editops`) | somme | (S+D+I)/n_réf ; I/n_réf ; D/n_réf | n_réf = 0 |
| MER | `mer`, `cmer` | (S+D+I, H+S+D+I) | somme | ratio | les deux textes sont vides |
| Exactitudes | `char_accuracy`, `word_accuracy`, `fca` | (erreurs, n_réf) | somme | max(0, 1 − e/n), plancher appliqué **après** combinaison (C02, résiduel § 6) | n = 0 |
| Appariement P/R/F | `ner_f1`, `ner_f1_exact`, `region_detection`, `bow_precision`/`recall`/`f1` | (tp, fp, fn) | somme | F1 = 2tp/(2tp+fp+fn) ; P = tp/(tp+fp) ; R = tp/(tp+fn) | dénominateur respectif nul |
| Proportions | `searchability`, `diacritic_err`, `mufi_err`, `hcpr`, `air`, `numseq_*`, `unanchored_trigrams`, `*_coverage`, préservation | (k, n) | somme | k/n | n = 0 |
| Texte par région | `region_cer`, `line_identity_cer` | (éditions sur paires bijectives + texte non apparié de l'hypothèse, car. réf.) | somme | ratio | car. réf. = 0 (le numérateur contribue quand même) |
| Ordre de lecture | `reading_order_tau` | (paires discordantes, paires ordonnées par la référence) sur les régions appariées | somme | d/(c+d) | aucune paire |
| Calibration (analyse) | ECE, MCE | histogramme sur des classes **fixées par le protocole** (10 × 0,1) : (n_b, Σ justes_b, Σ conf_b), Σ conf réel | somme par classe (`math.fsum`) | ECE = Σ n_b/N·\|acc_b − conf_b\| ; MCE = max sur classes non vides | N = 0 |
| Moyenne de réels | **estimande macro** de toute métrique ; durées, coûts | (Σ x, n), x réel | `math.fsum` en ordre canonique des documents | Σx/n | n = 0 |
| Quantiles (analyses) | percentiles par ligne | données élémentaires : multi-ensemble de valeurs | concaténation | quantile, méthode déclarée (`numpy`, `method="linear"`) | vide |

Le bootstrap travaille sur les statistiques empilées en tableau (`n_docs × k`) : on somme les lignes tirées, puis on finalise. Les quantiles sont la seule famille qui rééchantillonne des données élémentaires.

#### b. Quatre axes par observation (point 3)

```
Observation[S] (pipeline × document × vue × métrique)
  applicability : "applicable" | "no_ground_truth" | "not_in_view"               # 1. la VT du type existe, la métrique est dans la vue
  availability  : "available" | "gt_unreadable" | "output_missing" | "output_unreadable"
                  | "step_failed" | "step_cancelled" | "step_not_reached"         # 2. les entrées sont réellement là ; l'exécution (K3) est une CAUSE d'indisponibilité
  validity      : "valid" | motif propre à la métrique                            # 3. S mesure fidèlement ce document (ex. page sans dimensions pour la détection ; jetons sans confiance pour l'ECE)
  stat          : S | None                                                        # présente ⇔ axes 1 à 3 au vert
  scalar        : float | None ; scalar_reason : "zero_denominator" | "no_pairs" | … # 4. le ratio individuel finalize(S_d) est défini
  execution     : ok | truncated | partial                                        # étiquette recopiée du StepRecord, sans effet sur les supports
validateur : un axe n'est évalué que si les précédents sont au vert ; chaque axe non vert porte son motif
```

Une page à référence vide est applicable, disponible, valide, avec `scalar=None` pour `zero_denominator`. Elle **contribue au micro** par ses insertions (point 3) et sort du macro.

#### c. Trois supports (point 4)

Pour une vue v, une métrique m et une famille F de pipelines déclarée :
- attendus(P) = {d : applicable} ;
- D^μ_P = {d : stat présente} ;
- D^M_P = {d : scalaire défini}.

| Support | Définition | Analyses qui l'utilisent |
|---|---|---|
| **Conditionnel**, par pipeline | D^μ_P, D^M_P | agrégats micro et macro d'un pipeline ; couverture \|D^μ_P\|/\|attendus\| et \|D^M_P\|/\|attendus\| avec ventilation par motif ; IC marginal, étiqueté « conditionnel » |
| **Apparié**, par paire (A, B) | D^μ_AB = D^μ_A ∩ D^μ_B ; D^M_AB = D^M_A ∩ D^M_B | Δ micro et Δ macro, leurs IC et p ; Wilcoxon de la paire ; tout ordre entre A et B |
| **Global**, sur la famille | D^μ_F = ∩_{P∈F} D^μ_P ; D^M_F idem | Friedman, Nemenyi, rangs moyens ; tri multi-pipelines du tableau, si retenu (§ 6) |
| Sensibilité « page vide » | attendus ∩ {GT disponible} | agrégat où les sorties manquantes sont notées `finalize(S(réf, ""))`, sous ce nom |

C'est ce qui lève la contradiction entre les anciens S6 et S9. Ajouter un pipeline ne change ni les supports conditionnels ni les supports appariés des autres. Il change le support global, que les analyses globales déclarent.

#### d. Estimandes, inférence et famille de Holm (points 2 et 10)

| Estimande ou analyse | Statistique appariée | Inférence | Bibliothèque |
|---|---|---|---|
| **Micro** R_P = finalize(Σ S) | Δ^μ = R_A − R_B sur D^μ_AB (ratio de sommes) | p : permutation appariée (échange A/B par document) ; IC : bootstrap apparié (documents tirés une fois pour A et B) | `scipy.stats.permutation_test(permutation_type="samples")`, `scipy.stats.bootstrap(paired=True)` |
| **Macro** M_P = moyenne des scalaires sur D^M_P | Δ^M = moyenne sur D^M_AB de (r_A,d − r_B,d) | p : changement de signe des différences ; IC : bootstrap de la moyenne des différences | idem |
| **Analyses de rangs par document**, nommées ainsi | Wilcoxon signé (paire, sur D^M_AB) ; Friedman + Nemenyi (famille, sur D^M_F) | telles qu'aujourd'hui | `scipy.stats.wilcoxon`, `friedmanchisquare` |
| Grappes déclarées | mêmes statistiques | unité de rééchantillonnage et d'échange = la grappe | mêmes appels sur les statistiques sommées par grappe |

Règles :
- Les analyses de rangs ne sont jamais affichées comme test du micro ni du macro. Leur estimande est un décalage de localisation des différences (Wilcoxon) ou des rangs moyens (Friedman).
- Avant tout tirage, les documents sont triés par id et les sommes de réels passent par `fsum`. Le résultat est ainsi invariant par permutation de la spec (A10).
- **Famille de Holm** (point 10) : définie par la spec avant exécution, en (vue × métrique établie × estimande × paire déclarée). Elle ne dépend d'aucun résultat. Un test non calculable garde sa place (p = 1 dans la correction, publié « non calculé »). Des pipelines aux sorties identiques ne sont jamais fusionnés. Aujourd'hui, la famille est l'ensemble des tests **calculés** (`inference.py:346`), donc elle dépend des données.

#### e. Échecs (arbitrage 8)

`FailurePolicy = Literal["exclude", "empty_page"]`. `max_error` est retiré. Rien n'est imputé par défaut. `empty_page` est une sensibilité nommée, dont la valeur est celle que la métrique donne à une hypothèse vide. `UnitOutcome` gagne `partial` (sous-appels en échec : régions d'un fan-out, lignes en repli).

Validation avant exécution : VT et image lisibles et hachées (K4), pont de projection présent pour chaque couple (vue × pipeline). Sinon, refus.

| | |
|---|---|
| **Supprime ou fusionne** | `Observation` ; `micro_ratio`, `micro_ratio_ci`, `bootstrap_batch`, `_intervals` ; `_aggregate`, `_error_rate` ; `missed`, `_expects` et la branche `failed` d'`evaluate_run` ; règle `worst` et `_score_failed` (réduit à `empty_page`) ; F1 par document de `ner.py`, `bow.py` et `layout.py` ; `support ≥ 1` d'`EntityCategoryScore` ; motif faux `insufficient_support` quand un pipeline est hors vue ; famille de Holm « tests calculés » |
| **Bibliothèques** | `scipy.stats` (plancher 1.15) ; `rapidfuzz` (S/D/I). Oracles en `dev` : jiwer, nervaluate, scipy. Rejetée : la méthode delta (fausse d'un facteur 4 sur Simpson) |
| **Couche** | `evaluation` (3) : statistiques, axes et supports. `partial` en `domain/usage.py` (1). Validation préalable en `app` (6). Le placement des axes suit le critère de CLAUDE.md : vocabulaire d'évaluation, consommé par les couches 3 et 7 seulement, donc pas `domain` |
| **Ne fait pas** | Pas d'algèbre générique. Pas de bornes ni de « pire valeur » dans `MetricSpec`. Pas d'imputation par défaut. Pas de courbes risque-couverture. Pas de méthode delta. Aucune nouvelle métrique |

### 2.2 K3 : enregistrement par étape (point 6)

```
StepRecord(step_id, outcome ∈ {ok, truncated, partial, failed}, reason, message,
           artifacts: Mapping[ArtifactType, Artifact], usage: ResourceUsage,
           served_models: tuple[str, ...] | None,          # None + module distant ⇒ « inconnu », affiché tel
           identity (§ 2.3 c), executed_files, step_key, produced_in: (run_id, repetition_id))
DocumentExecution(steps: tuple[StepRecord, ...])            # issue, usage et pool déduits ; un échec = le dernier record, l'amont reste
RunContext.workspace_uri = <ws>/<pipeline>/<step_id>/        # isolation physique ; aucune signature d'adaptateur ne change
step_key(k) = H(identité de l'étape k,
                [(type, content_hash) des artefacts EFFECTIVEMENT résolus en entrée de l'étape k, triés],
                [(nom, sha256) des unit_inputs lus],
                repetition_id)
RunMode = Literal["fresh", "resume", "rescore"]             # réutilisation seulement en "resume" ou "rescore", toujours explicite
```

- **Artefacts consommés** (point 6). La clé d'une étape se calcule à partir des empreintes de ce qu'elle lit vraiment, et non de la clé amont. Un amont réexécuté qui rend les mêmes octets laisse l'aval réutilisable. Un amont non déterministe qui rend d'autres octets fait réexécuter l'aval. La reprise avance donc étape par étape : record k−1 vérifié, empreintes de ses sorties, puis clé k.
- **Répétitions** (point 6). `repetition_id` (0 pour un run seul, 1 à N pour `--repeat`) entre dans chaque clé. Une répétition ne peut pas relire celle d'une autre, même dans le même dossier. Chaque observation du `RunResult` porte `produced_in`, et `reread` avec sa source. Une recopie de `repetition-1` vers `repetition-2` (procédure S31) ne crée donc pas de répétition : elle est lue comme une relecture ou n'est pas trouvée.
- **Persistance atomique immédiate** (décidée). Chaque `StepRecord` est écrit dès la fin de son étape (fichier temporaire, `fsync`, `os.replace`), avant l'étape suivante. À l'annulation, la file est arrêtée.
- **Analyses** : `correction`, `decisions` et `economics` reçoivent (vue, étape notée, étape d'entrée déclarée par `inputs_from`), jamais le pool.

| | |
|---|---|
| **Supprime ou fusionne** | `billed`, `DocumentExecution.failed`, « échec ⇒ aucun artefact » ; reconstruction de l'échec dans l'orchestrateur ; `pools`, `_two_stage_pipelines`, `_text_of` sur le pool ; `unit_key` ; saut `if not entries: continue` d'`economics` ; `RunManifest.served_models` stocké (devient dérivé) ; `repetition_dir` comme seul garde-fou |
| **Bibliothèques** | stdlib ; modèle de Provenance Run Crate (une `ControlAction` par étape) comme forme de référence, sans dépendance |
| **Couche** | `StepRecord` en `pipeline` (4) ; clés et modes en `app` (6) ; consommateurs en `evaluation` (3) |
| **Ne fait pas** | Pas de DAG ni d'ordonnanceur. Pas de reprise à l'intérieur d'une étape. Pas de record « sautée » (absence = `step_not_reached`). Pas de coût par région |

### 2.3 K4 : identité calculée ; cache et archive séparés (points 7 et 9)

#### a. Ce que BagIt garantit, et ce qu'il ne garantit pas (point 7)

BagIt garantit la **vérification d'intégrité** : le contenu correspond aux manifestes du sac. Il ne garantit **ni l'immuabilité ni l'authenticité** : quiconque modifie le contenu peut réécrire les manifestes et le `tagmanifest`, et le sac redevient valide.

Conséquences :
1. Cinoc n'écrit jamais dans une archive scellée et la vérifie à chaque lecture. C'est une garantie sur Cinoc, pas contre un tiers.
2. L'authenticité tient à un **ancrage externe** : l'empreinte du `tagmanifest-sha256.txt` (empreinte racine) est publiée hors de l'archive (README de campagne, notice du dépôt, commit). La relecture la compare à une empreinte attendue quand on la lui fournit.
3. La signature détachée du `tagmanifest` est recommandée **hors 1.0** (§ 6).

#### b. Mutualisation physique : risques et règles (point 7)

| Mécanisme | Risque | Règle |
|---|---|---|
| Lien dur | même inode : une écriture **en place** (éditeur, `open("r+")`, outil de synchronisation) altère toutes les copies, archive comprise ; impossible entre systèmes de fichiers | seulement sur option explicite, sur le même système de fichiers ; blob en lecture seule (0444) ; jamais ouvert en écriture par Cinoc |
| Copie-sur-écriture (reflink : btrfs, XFS, APFS) | aucun pour l'écriture en place, qui crée de nouveaux blocs ; dépend du système de fichiers | choix par défaut quand il est disponible |
| Copie | coût en place | repli par défaut (autre système de fichiers, reflink absent) |
| Tous | un blob altéré touche toutes les archives qui le partagent | chaque lecture recalcule l'empreinte (aucun cache fondé sur `mtime` pour une archive scellée) ; `bagit.validate` refuse chaque sac touché |

#### c. Identité d'étape fondée sur les fichiers réellement exécutés (point 7)

```
StepIdentity(version déclarée,
             settings effectifs ENVOYÉS (prompt, température, max_tokens…),
             executed_files: {chemin relatif à son sys.path: sha256}
                # __file__ / __spec__.origin (.py, .so) de chaque module hors stdlib chargé
                # pour construire puis exécuter le module (différence de sys.modules)
             binaries: {exécutable résolu à l'appel: sha256} + fichiers de données déclarés (traineddata),
             weights: révision RÉSOLUE (hash de commit du Hub), jamais la chaîne demandée,
             distributions: {nom: version} (étiquettes, jamais preuves),
             interpreter: (implémentation, version))
```

- **`RECORD` est rejeté comme preuve.** C'est une liste d'installation, jamais revérifiée, et vide pour une installation éditable.
- **Imports paresseux.** Le record garde l'ensemble exécuté *après* l'exécution. Une réutilisation exige que **tous** les fichiers enregistrés se re-hachent à l'identique. Un fichier importé paresseusement puis modifié force donc une réexécution.
- **Coût.** Les empreintes sont mémoïsées le temps d'un run seulement.
- **Modèle distant.** Le modèle servi est enregistré, ou marqué « inconnu » en toutes lettres. Les poids d'un modèle distant sont toujours « inconnus ».

#### d. Protocole de mesure et trois opérations (point 9)

```
ProtocolIdentity = H(spec de vue, identité de chaque métrique (statistique, finalisation, executed_files
                     du code d'évaluation et de formats qui l'a calculée), contenu du profil de normalisation,
                     unicodedata.unidata_version, empreintes des VT)
ObservationId    = H(content_hash de la sortie notée, content_hash de la VT, ProtocolIdentity)
```

| Opération | Entrées | Ce qui est exécuté | Résultat exigé | Coûts publiés |
|---|---|---|---|---|
| **Relecture des observations** | archive scellée | rien (lecture des statistiques et du `RunResult` archivés) | octets identiques, hors horodatages | coûts historiques, attribués à leur run de production |
| **Reproduction sous protocole identique** | sorties archivées, même `ProtocolIdentity` (re-notation) ; ou rejeu des moteurs | évaluation ; moteurs seulement en rejeu | re-notation : `ObservationId` et valeurs identiques. Rejeu : les écarts de sortie sont publiés, pas fondus | rejeu : **coûts du rejeu**, séparés des coûts historiques |
| **Réévaluation sous nouveau protocole** | sorties archivées, autre `ProtocolIdentity` (nouvelle VT, normalisation, métrique) | évaluation | nouvelles observations, avec filiation vers l'archive et le protocole d'origine ; jamais publiées sous l'identité d'origine | aucun coût moteur |

#### e. Contrats

```
Artifact.content_hash : obligatoire dès qu'une uri existe ; calculé par l'exécuteur
read_verified(artifact) -> bytes          # point de lecture unique ; écart => CorruptedArtifactError
BlobStore : put -> sha256 (écriture atomique, lecture seule, reflink > copie ; lien dur sur option) ; get(sha) vérifié
Cache   = BlobStore + index mutable {step_key: StepRecord}
Archive = sac BagIt scellé : objects/<sha>, ground_truth/<sha>, spec.json, run_result.json, observations ;
          lecture = bagit.Bag.validate() + refus de tout lien (lstat) + refus de fetch.txt + empreinte racine comparée à l'ancre si fournie
GroundTruthRef.content_sha256, DocumentRef.image_sha256 ; RunManifest.corpus (CorpusSpec avec empreintes) ;
DocumentUsage par étape : usage historique (produced_in) + usage de ce run (0 pour une relecture)
```

| | |
|---|---|
| **Supprime ou fusionne** | `_rebased`, `_store_image`, `binaries.json` et ses deux accesseurs, rôle d'archive du `ResumeStore`, téléchargement hors ligne, clé lisant l'image du corpus, durées héritées présentées comme durées du run |
| **Bibliothèques** | `bagit` (décidé) ; `hashlib`, `importlib.metadata` (étiquettes) ; méthode DVC/git (adressage par contenu) ; méthode joblib/Snakemake, étendue aux fichiers chargés |
| **Couche** | champs d'empreinte en `domain` (1) ; `StepIdentity` en `pipeline` (4) ; `ProtocolIdentity` en `evaluation` (3) ; `BlobStore` et archive en `app` (6) |
| **Ne fait pas** | Pas d'OCFL, pas de signature en 1.0, pas de `fetch.txt`, pas de RO-Crate (reporté), pas de `rfc8785` (seul Cinoc recalcule). Octets d'image facultatifs selon la licence (§ 6, H4) |

### 2.4 K5 : appariement de structure (point 8)

**Objectif**, par page et pour un seuil d'admissibilité θ (IoU ≥ θ ou > θ, § 6) :
1. **Filiation démontrée.** La chaîne de `StepRecord` qui produit l'hypothèse a consommé un artefact dont le `content_hash` est celui de la VT de mise en page (K4), et chaque étape de cette chaîne est déclarée `preserves_region_ids` par son module (déclaration incluse dans son identité). Exemples : reconnaissance sur la segmentation de la VT, post-correction d'un ALTO de VT. Alors les ids, uniques par page, **sont** l'appariement. Les régions sans id commun passent à l'étape 2.
2. **Sans filiation** (ou pour le reste), on cherche un appariement **bijectif** M qui maximise, dans l'ordre lexicographique :
   1. le nombre de paires admissibles ;
   2. puis Σ IoU sur M.

   Calcul : `linear_sum_assignment` sur le poids (n+1)·[admissible] + IoU·[admissible], où la borne Σ IoU ≤ n garantit l'ordre lexicographique. Avant le calcul, les deux côtés sont triés dans un ordre géométrique canonique (page, y0, x0, y1, x1, puis texte), ce qui départage les ex æquo résiduels. **Aucun identifiant n'intervient sans filiation**, pas même pour départager. Oracle : énumération exhaustive sur les petites instances.
3. **Fusions et scissions** : ce sont des relations **distinctes** de la bijection, calculées sur les matrices IoGT = \|r∩h\|/\|r\| et IoDT = \|r∩h\|/\|h\| (méthode PRImA et ocrd-segment-evaluate). Une fusion est une h qui couvre au moins deux r à IoGT ≥ θ_m ; une scission est une r couverte par au moins deux h à IoDT ≥ θ_m. Elles sont publiées comme comptes à part et ne modifient pas tp/fp/fn.

Les mêmes paires bijectives servent `region_detection`, `region_cer`, `line_identity_*` et `reading_order_*`.

| | |
|---|---|
| **Autres contrats** | `formats.layout_text(layout)` est la **seule** projection `LAYOUT → texte`. Elle respecte `reading_order` imbriqué et sert à `evaluation.projectors` comme à `adapters.layout.to_text`. Le fan-out refuse, de façon typée, un layout multipage accompagné d'une seule image (décidé). La calibration juge un jeton par alignement de séquences, si C11-B |
| **Supprime ou fusionne** | `_greedy_pairs`, `_true_positives`, `correspondance` « id d'abord », `_ids_partages`, branche id de `_ordres`, `_identified_boxes` (fusionné avec `_detection_boxes`), `_region_texts` global, l'une des deux projections, `_judge` par multi-ensemble |
| **Bibliothèques** | `scipy.optimize.linear_sum_assignment` (déjà importé par `metrics/flexible.py:50`) ; méthode PRImA pour les relations. Rejeté : `pycocotools` (glouton par score) |
| **Couche** | appariement en `evaluation` (3) ; projection en `formats` (2), seule couche commune à 3 et 5 ; refus de fan-out en `pipeline` (4) ; `preserves_region_ids` dans le `Module` (contrat de couche 4, déclaratif) |
| **Ne fait pas** | Pas d'IoU polygonale (H2). Pas de profils pondérés PRImA. Pas d'alignement par ligne en calibration |

### 2.5 Bilan de lignes (indicatif, secondaire)

Ordre de grandeur ±50 %, mesuré sur l'étendue des symboles retirés :
- K1+K2 ≈ −20 ;
- K3 ≈ 0 ;
- K4 ≈ +120 (archive, empreinte des fichiers exécutés et du protocole sont des capacités nouvelles) ;
- K5 ≈ −90.

**Total ≈ 0.** Ce bilan n'a motivé aucun choix de contrat.

---

## 3. Invariants

Chaque invariant porte sur **une métrique ou une analyse nommée**, aucun n'est universel.

Vérification :
- **P** = propriété avec `hypothesis` (extra `dev`), profil déterministe dans `tests/conftest.py` (`derandomize=True`, `database=None`, `deadline=None`, `max_examples` borné pour `check-fast`). Les tests vivent à côté de leur couche.
- **O** = oracle externe.
- **A** = test adversarial ciblé.

« Manquant » = à écrire, rouge, avant la correction.

### Par métrique (M) (point 5 : propriétés propres à chaque métrique, aucune monotonie universelle)

| # | Invariant | Vérif. | Subsume / manquant |
|---|---|---|---|
| M1 | **Taux d'édition** (`cer`, `cer_diplo`, `wer`, `ins_rate`, `del_rate`, `mer`, `cmer`) : micro = finalize(Σ S), égal à jiwer sur la liste des documents, pages à référence vide comprises. Une page à référence vide ajoute \|h\| au numérateur, avec un scalaire `zero_denominator`. **Corpus entièrement vide** : CER/WER micro indéfinis (n_réf = 0) pour tout pipeline, muet compris ; aucun classement ; Σ insertions publiée comme statistique. `mer`/`cmer` sont définis dès qu'un texte n'est pas vide. | P ; O jiwer | `reference_vide[cer, wer, ins_rate]`, `pipeline_qui_hallucine`, C01 ; verts `taux_additifs…jiwer`, `cer_borne…`, `metriques_a_denominateur…` ; **manquant** : corpus entièrement vide |
| M2 | **Exactitudes** (`char_accuracy`, `word_accuracy`, `fca`) : valeur corpus = max(0, 1 − Σe/Σn), jamais une moyenne de planchers par page (sous C02-A). | P | C02×3 |
| M3 | **F1 à appariement** (`ner_f1`, `ner_f1_exact`, `region_detection`, `bow_*`) : corpus = F1(Σtp, Σfp, Σfn). Un document sans référence contribue ses fp. Une catégorie présente seulement en prédiction a P = 0 et R indéfini, sans lever d'erreur. Sous l'appariement de cardinalité maximale, ajouter une prédiction sans partenaire admissible augmente fp d'exactement 1 et ne change pas tp. Tout vide : F1 indéfini. | P ; O nervaluate (NER), calcul à la main | `ner_f1×2`, `ner_f1…sans_entite`, `ner_payload…label_absent`, `region_detection…`, `bow_f1…` ; vert `bow_precision_recall` |
| M4 | **Texte par région** (`region_cer`, `line_identity_cer`) : éditions sur les paires bijectives, plus le texte non apparié de l'hypothèse au numérateur. Une région de référence sans texte, appariée à du texte, contribue au numérateur. | P | C04 (sous A) ; **manquant** : région de référence sans texte (`layout.py:116`) |
| M5 | **τ** : finalize(discordantes, paires ordonnées par la référence) sur les régions appariées ; les régions non appariées vont à la couverture ; sans ex æquo, égal à (1 − τ)/2 de `scipy.stats.kendalltau`. | P ; O scipy | C03 |
| M6 | **ECE/MCE** : combiner les histogrammes par document = calculer sur les jetons poolés ; classes fixées par le protocole ; ECE ∈ [0, 1] ; un jeton est jugé par alignement (si C11-B). | P ; O calcul à la main, `difflib` | vert `ece_sur_jetons_poolés` ; C11×2 |
| M7 | **Projection `LAYOUT → texte`** : une seule fonction pour la VT et le candidat ; un layout identique donne un CER nul sous toute vue, ordre imbriqué compris. | P | `deux_projections×3`, `ordre_de_lecture_imbrique` |
| M8 | **Appariement de structure** (§ 2.4) : optimum lexicographique égal à l'énumération exhaustive ; invariant par permutation des régions des deux côtés et par renommage des ids sans filiation ; page par page ; ids conservés sous filiation démontrée ; fusions et scissions sans effet sur tp/fp/fn. | P ; O énumération, `linear_sum_assignment` | C10×2, `ordre_des_regions_de_reference`, `egalite_d_iou`, `ids_identiques_non_homologues`, `ids_partiellement_partages`, `alto_sans_id`, `multipage×3` ; **manquants** : filiation conservée ; fusion comptée hors bijection |

### Par analyse (A)

| # | Invariant | Vérif. | Subsume / manquant |
|---|---|---|---|
| A1 | **Agrégat conditionnel d'un pipeline** : micro sur D^μ_P, macro sur D^M_P ; couverture et motifs publiés ; ajouter un autre pipeline ne le change pas. | P ; A | `reference_vide_nest_pas_comptee` (T1), `artefact_sans_contenu`, `artefact…absent_du_disque`, `fanout_entierement_en_echec`, `sortie_incompatible`, C13×2 |
| A2 | **Quatre axes** : n attendus = applicables, quelle que soit l'issue d'exécution ; la statistique est présente ⇔ axes 1 à 3 au vert ; le scalaire peut être indéfini avec une statistique présente ; chaque exclusion a son axe et son motif. | P (pannes aléatoires par étape) ; A | **manquants** : troncature aval sous une vue amont complète ; saknussemm en repli total (`partial`) |
| A3 | **Δ micro apparié** sur D^μ_AB : IC par bootstrap apparié et p par permutation appariée, égaux à scipy ; sur Simpson, p = 1. | O scipy ; A | C05×2 (reformulés), C06 `ic_apparie` |
| A4 | **Δ macro apparié** sur D^M_AB : moyenne des différences, IC par bootstrap, p par changement de signe, égaux à scipy. | O scipy | **manquant** |
| A5 | **Analyses de rangs** : Wilcoxon (paire, D^M_AB) et Friedman/Nemenyi (famille, D^M_F), publiés comme « analyse de rangs par document », jamais comme test du micro ou du macro ; ajouter un pipeline change Friedman (déclaré), pas le Wilcoxon d'une paire. | A | `pipeline_non_applicable…`, C01 `nentre_pas` |
| A6 | **Classement** : deux pipelines ne s'ordonnent que sur leur support apparié ; aucune comparaison entre agrégats de supports différents. | A | C07, C06 `meme_documents` |
| A7 | **Échecs** : pas d'imputation par défaut ; la sensibilité « page vide » vaut finalize(S(réf, "")) et porte ce nom ; aucune valeur n'est déduite de `higher_is_better`. | A | C08×2, `max_error…deplace_lagregat` |
| A8 | **Grappes** : la même liste groupée de deux façons donne deux IC ; en singletons, l'IC égale l'IC par document ; sous le seuil, « non estimable ». | P ; A | C09 |
| A9 | **Famille de Holm** : taille et membres ne dépendent que de la spec ; un test non calculable garde sa place (p = 1, « non calculé ») ; aucune fusion de pipelines aux résultats identiques. | P | **manquant ; violé** (`inference.py:346`) |
| A10 | **Rééchantillonnage** (A3, A4, A8) : IC et p invariants par permutation de l'ordre des documents de la spec. | P | **manquant ; violé** : l'IC de `micro_ratio_ci` passe de [0,0953 ; 0,7596] à [0,1032 ; 0,7403] en inversant 8 documents |
| A11 | **Analyses d'une vue** (`correction`, `decisions`, `economics`) : elles ne lisent que l'étape cible, son entrée déclarée et la VT. | A | `correction×3`, `decisions×2`, `a5…chaque_vue_notee`, C12 `economie` |
| A12 | **Coûts** : coût d'un préfixe = Σ des étapes jusqu'à la cible ; la facture de l'étape fautive est comptée ; les coûts historiques (attribués à leur run) ne sont jamais additionnés aux coûts du rejeu. | A | `echec_partiel…cout_amont`, `…bilan_economique`, `…pipeline_tout_en_echec` ; **manquant** : coûts historiques contre rejeu |

### Identité, provenance, archive (I)

| # | Invariant | Vérif. | Subsume / manquant |
|---|---|---|---|
| I1 | **Identité d'étape** : modifier un fichier réellement exécuté (source, module importé paresseusement, binaire, fichier de données), un réglage envoyé ou la révision des poids change l'identité ; une réutilisation exige que les fichiers enregistrés se re-hachent à l'identique ; la version du paquet et les réglages opérationnels n'y entrent pas. | A | C17×2 (reformulés), `saknussemm…version`, `poids_du_scoreur_qe` ; verts `digest_ollama`, `reprise_autres_binaires` ; **manquant** : import paresseux modifié |
| I2 | **Identité du corpus** : un octet changé d'une image ou d'une VT change l'empreinte publiée ; re-noter contre une autre VT est signalé. | A ; P | `identite_gt×4`, `identite_image` |
| I3 | **Identité du protocole** : changer de profil de normalisation, de définition de métrique, de VT ou de version Unicode change `ProtocolIdentity` et chaque `ObservationId`. | A | **manquant** |
| I4 | **Relecture des observations** : lire une archive vérifiée rend des octets identiques, hors horodatages. | P (aller-retour) | `a5_relecture_offline` ; vert `a7_temoin_relecture_intacte` |
| I5 | **Reproduction et réévaluation** : sous le même protocole, une re-notation rend les mêmes `ObservationId` ; sous un autre, elle rend de nouvelles identités avec filiation, jamais publiées sous l'identité d'origine. | A | **manquant** |
| I6 | **Intégrité** : une archive altérée (octet d'une sortie, d'un index, d'une image, d'une VT, de la spec ; lien ; chemin absolu ; `fetch.txt`) est refusée avant toute note ; une empreinte racine différente de l'ancre fournie est refusée. Aucune authenticité n'est revendiquée au-delà. | O `bagit` ; A | C14 (3 sur 4), `a7_uri_absolue`, `a7_lien_symbolique`, `a5_archive__empreinte` ; **manquant** : ancre |
| I7 | **Provenance** par unité et par étape : modèle servi ou « inconnu » ; `code_version` et fichiers exécutés de production ; aucune union présentée comme attribut d'une unité. | A | C18×2 ; **manquant** : distant sans modèle servi |

### Fonctionnels (F)

| # | Invariant | Vérif. | Subsume / manquant |
|---|---|---|---|
| F1 | **Isolation physique** : deux étapes ne partagent jamais un fichier ; `sha256(fichier) = content_hash` à l'écriture et à chaque lecture. | A | `a5×5` |
| F2 | **Conservation de l'amont** : un échec à l'étape k garde les artefacts, coûts, issues et l'évaluabilité des étapes avant k. | A | `echec_partiel…lamont_reussi` ; inverse le vert `le_type_interdit…` ; **manquant** : annulation et délai |
| F3 | **Reprise sur artefacts consommés** : un amont réexécuté aux mêmes octets laisse l'aval relu ; à d'autres octets, il fait réexécuter l'aval. | A ; P | C12 `la_reprise` ; **manquant** : amont non déterministe |
| F4 | **Répétitions** : une répétition ne relit jamais une observation d'une autre, même dans le même dossier ; la réutilisation n'existe qu'en mode explicite ; chaque observation dit `produced_in` et `reread`. | A | vert `repetitions__archives_disjointes` (partiel) ; **manquant** : même dossier |
| F5 | **Persistance atomique** : un arrêt brutal après l'étape k laisse k records valides et aucun fichier partiel sous un nom final ; l'annulation arrête la file. | A | **manquant** |
| F6 | **Relecture autonome** : ni téléchargement, ni lecture du corpus d'origine ; une unité intacte n'est jamais déclarée `failed` pour une cause extérieure. | A | C15×3 |
| F7 | **Archive scellée et mutualisation** : une reprise n'écrit jamais dans une archive scellée ; un blob partagé altéré en place est détecté dans chaque archive qui le partage ; entre systèmes de fichiers, copie. | A ; O `bagit` | C14 `archive_publiee` ; **manquant** : altération d'un blob partagé |
| F8 | **Refus avant de payer** : VT ou image illisible, vue sans pont de projection, layout multipage à image unique en fan-out. | A | C13 `gt…avant_de_payer`, `sortie_incompatible`, C16 |
| F9 | **Parité** : chaque capacité nouvelle (sceller, vérifier, modes de run) a sa fonction `app` et ses faces déclarées dans `test_web_cli_parity`. | garde existante | **manquant** : entrées de table |

**36 invariants** : 8 M, 12 A, 7 I, 9 F.

Correspondance avec la première version :
- **supprimé** : S4 (monotonie universelle), remplacé par des propriétés propres à M1, M3 et M4 ;
- **éclatés** :
  - S1 en M1 à M6 ;
  - S5 en A3, A4 et A5 ;
  - S6 et S9 en A1, A5 et A6 (trois supports), plus A7 ;
  - S13 en I4, I5 et A12 ;
- **changés de nature** :
  - S2 devient A10 (rééchantillonnage seulement) ;
  - S3 devient M8 (objectif lexicographique, filiation) ;
  - S8 devient A1 et A2 (quatre axes) ;
  - S11 devient I1 (fichiers exécutés) ;
  - F3 porte sur les artefacts consommés ;
- **inversé** : l'ex-N4 devient A9 (familles a priori) ;
- **nouveaux** : A4, A9, A12, I3, I5, F4, F5, M6.

---

## 4. Tests à reformuler, à inverser, à écrire

### 4.1 Reformulations (avant toute correction)

| Test | Conv. | Attendu reformulé |
|---|---|---|
| `applicabilite…::reference_vide_nest_pas_comptee_notee` (**valide**) | T1 | Micro de A = 12/120 = 0,100. Les 6 pages blanches sont applicables, disponibles et valides, avec scalaire `zero_denominator` : 12 documents au support micro, 6 au support macro. |
| `test_omnibus__meme_sens_que_le_cer_micro_affiche` | C05 | Le test du Δ micro (permutation appariée) va dans le sens du Δ micro ou n'est pas significatif (ici p = 1). Le Wilcoxon, s'il est publié, est une analyse de rangs nommée comme telle, jamais affichée comme test du micro. |
| `test_omnibus__p_du_ratio_micro_par_permutation_appariee` | C05 | La p corrigée du test du Δ micro est ≥ α et égale à `scipy.stats.permutation_test` exact (1,0). |
| `intervalles__meme_documents_que_le_test` | C06 | L'IC du Δ porte sur le support apparié D^μ_AB (mêmes ids que le test). Les IC marginaux portent sur le support conditionnel et sont étiquetés ainsi. |
| `echec_non_aleatoire__classement_sur_documents_communs` | C07 | Sur le support apparié (A, B), B (0,040) est devant A (0,050). Aucun ordre n'est donné entre agrégats de supports différents, et la couverture 7/8 de A est publiée. |
| `max_error__un_echec_ne_note_jamais_mieux_quune_reponse` | C08 | Aucune « erreur maximale » n'est imputée. Par défaut, l'échec n'est pas noté (couverture 2/3). Sous `empty_page`, il vaut la valeur de la métrique pour une hypothèse vide (CER 1,0), sous ce nom. |
| `bootstrap__grappes_documentaires_declarables` | C09 | La même liste groupée de deux façons donne deux IC ; en singletons, l'IC égale l'IC par document. |
| `version_manuelle__brique_modifiee_sans_relever_sa_version_reexecutee` | C17 | Deux modules aux **fichiers exécutés** différents, de même nom et de même version déclarée, ont deux identités, donc le second est exécuté. Variante : un fichier importé paresseusement puis modifié refuse la réutilisation. |
| `identite_saknussemm__prompt_et_temperature_envoyes_au_llm_sont_traces` | C17 | L'identité change quand le prompt ou la température **envoyés** changent, et ne change pas pour un réglage opérationnel. On teste le comportement, pas des noms de clés. |

À recibler sans changer l'attendu :
- `reference_vide_nentre_pas_dans_le_test_apparie` (C01) : p = 0,031 lue dans l'**analyse de rangs** (6 pages) ;
- `pipeline_non_applicable…` : p = 0,0078 lue dans le Wilcoxon de la paire (A, B).

### 4.2 Tests existants qui figent un défaut

À inverser ou supprimer dans le commit du correctif.

| Test | Défaut figé | Tranche |
|---|---|---|
| `tests/evaluation/test_metrics_text.py::test_cer_weight_is_reference_length` | page blanche hors du micro | 1a |
| `tests/evaluation/test_micro_interval.py::test_zero_weight_documents_weigh_nothing` | idem pour l'IC | 1a |
| `tests/evaluation/test_inference_scipy_parity.py` (`family_size == len(computed)`), `test_inference.py::test_not_computed_says_why` (`family_size == 0`) | famille de Holm dépendante des résultats | 1a |
| `tests/app/test_unit_outcome.py::test_max_error_is_zero_for_a_higher_is_better_metric`, `::test_max_error_scores_the_failure_like_an_empty_page` | `max_error` déduit du signe ; la seconde devient le test de `empty_page` | 1b |
| `tests/adversarial/applicabilite_echecs/…::le_type_interdit_bien_les_artefacts_dune_unite_failed` (vert) | « échec ⇒ aucun artefact » | 2 |
| `tests/evaluation/test_appariement_geometrique.py::test_identifiants_partages_inchanges` | id prioritaire sans filiation | 4 |
| `tests/evaluation/test_calibration.py::test_analysis_scores_tokens_against_reference_multiset` | multi-ensemble (si C11-B) | 4 |

### 4.3 Tests manquants (à écrire rouges d'abord)

M1 corpus entièrement vide · M4 région de référence sans texte · M8 filiation conservée, fusion hors bijection · A2 troncature aval et saknussemm en repli total · A4 · A9 · A10 · A12 coûts historiques contre rejeu · I1 import paresseux · I3 · I5 · I6 ancre · I7 distant sans modèle · F2 annulation · F3 amont non déterministe · F4 même dossier · F5 · F7 blob partagé altéré · F9 entrées de parité.

Ajouter les propriétés P de M1 à M8, A1, A2, A8, A9, A10, I2, I4 et F3.

---

## 5. Ordre des tranches

Le premier commit de chaque tranche ne contient que des tests (§ 4), rouges pour la bonne raison. K1 et K2 partagent une conception (§ 2.1) et deux implémentations successives. La tranche 4 ne dépend que de 1a et 1b.

| Tranche | Invariants | Tests prérequis | Contrats | Critère de fin |
|---|---|---|---|---|
| **1a · Statistiques et estimandes** (K1, conception § 2.1) | M1 à M6, A3, A4, A5, A8, A9, A10 | T1, C05×2, C09 reformulés ; A4, A9, A10, M1 (corpus vide) ; propriétés M1 à M6 | statistiques par famille, finalisation, micro/macro, Δ appariés, analyses de rangs nommées, famille a priori, ordre canonique | Invariants établis sur les 29 métriques et l'ECE, contre jiwer, nervaluate et scipy. **Prévisions vérifiées** en re-notant les deux `RunResult` commités : CER/WER micro BNL et Dresden inchangés (aucune page blanche) ; `char_accuracy` Dresden E5 de 0,3125 à 0 ; Δ micro apparié E5−E0 sur BNL, IC [−0,041 ; −0,010]. |
| **1b · Axes et supports** (K2, même conception) | A1, A2, A6, A7, F8 | C06 `meme_documents`, C07, C08 reformulés ; A2 manquants | quatre axes, trois supports, `empty_page`, `partial`, validation préalable | Invariants établis. Dresden E5 publié 1,8614 « conditionnel 4/10 », ordonné face à E0 sur leur seul support apparié. Amendement CLAUDE.md §3 (N1) dans le même commit. |
| **2 · Étape** (K3) | A11, A12 (préfixe), I7, F1 (isolation), F2, F3, F4, F5 | C12×3 (fixture `economie` avec usage par étape), C18×2 ; F2 à F5 manquants | `StepRecord`, workspace par étape, `step_key` sur artefacts consommés, `repetition_id`, `RunMode`, persistance atomique, entrées des analyses | Invariants établis. Socle `tesseract → deskew → tesseract` : chaque vue garde sa lecture. Un arrêt brutal ne perd aucune étape payée. |
| **3 · Identité et archive** (K4) | I1 à I6, A12 (historique/rejeu), F1 (empreinte), F6, F7, F9 | C14×4 reciblés sur le lecteur d'archive, C15×3, C17×2 reformulés ; I1, I3, I5, I6, F7, F9 manquants | `read_verified`, `BlobStore`, sac BagIt, `StepIdentity` sur fichiers exécutés, `ProtocolIdentity`, empreintes de corpus | Invariants établis. Une archive de campagne est scellée, validée par `bagit`, relue (I4), re-notée sous le même protocole (I5), réseau et corpus retirés ; son empreinte racine est publiée hors de l'archive. |
| **4 · Correspondance** (K5) | M7, M8 | C10×2, C11×2 (si tranché), C16 ; M8 manquants ; propriétés M7 et M8 | appariement lexicographique, filiation, relations de fusion et scission, projection unique, refus de fan-out | Invariants établis contre l'énumération exhaustive et `linear_sum_assignment`. CER par région E1/E3/E4 re-notés. |

---

## 6. Ce qui reste ouvert (liste fermée)

| # | Question | Recommandation |
|---|---|---|
| 1 | **C02** : plancher des exactitudes (après combinaison, ou pas de plancher façon ISRI) | plancher au corpus (A) ; macro publié à part |
| 2 | **C04** : lignes fantômes dans `line_identity_cer` | insertions comptées (A, M4) |
| 3 | **C09** : déclaration des grappes (champ de `DocumentRef` ou métadonnée d'import) et seuil « non estimable » | champ déclaré par le corpus ; seuil à chiffrer (BNL : 5 grappes, dont un singleton) |
| 4 | **C10** (résiduel) : seuil d'admissibilité strict ou inclusif, et seuil θ_m des fusions et scissions | IoU > 0,5 strict (unicité de l'appariement plan, Kirillov et al. 2019) ; θ_m = 0,5 |
| 5 | **C11** : jugement d'un jeton en calibration | alignement LCS (B) |
| 6 | **C17** (résiduel) : périmètre des fichiers exécutés (stdlib et interpréteur hachés, ou seulement leur version enregistrée) | version de l'interpréteur enregistrée, stdlib non hachée ; tout le reste haché |
| 7 | **C19** : plan d'expérience | témoin `seg → tesseract:reco → lecture → mistral:correction` obligatoire ; `max_tokens` aligné ou montré non limitant ; la recopie `repetition-1 → 2…5` de S31 retirée ou déclarée relecture (F4) |
| 8 | **H2** : IoU polygonale (`shapely`) | rester en boîtes tant qu'aucun consommateur n'exige de polygones ; jamais en extra avec repli (la métrique dépendrait du paquet installé) |
| 9 | **H3** : IC scipy dépendants de la version | accepter « mêmes octets à versions égales », versions tracées |
| 10 | **H4** : images IIIF dans l'archive | empreinte obligatoire, octets facultatifs selon la licence ; la re-notation n'a besoin que des empreintes |
| 11 | **H5** : faces des capacités nouvelles (sceller, vérifier, modes) | options de `cinoc run` ; vérification implicite à chaque relecture ; web `front-absent` déclaré |
| 12 | **N1** : formulation de l'amendement CLAUDE.md §3 (« niveau absent → `None` ») | niveau absent de la VT → `not_applicable` ; de l'hypothèse → statistique valide (texte vide noté) ou indisponible avec motif, plus `partial` |
| 13 | **Famille de Holm par défaut**, quand la spec ne déclare pas de comparaisons (point 10) | toutes les paires de la spec × métriques établies × vues × {micro, macro} ; les analyses de rangs hors de la famille confirmatoire |
| 14 | **C07** (résiduel) : tri par défaut du tableau | aucun tri implicite entre supports différents ; tri sur le support global de la famille, avec colonne de couverture |
| 15 | **Authenticité** : signature du `tagmanifest` en 1.0, ou ancrage externe seul | ancrage de l'empreinte racine en 1.0 ; signature hors 1.0 |
| 16 | **Mutualisation** par défaut | reflink, sinon copie ; lien dur sur option explicite seulement |
| 17 | **Archives S30/S31** au format `ResumeStore` | script de conversion ponctuel hors produit (`campaigns/`, supprimé après usage), ou réexécution des parties gratuites |
| 18 | **Séparateur de blocs** de la projection unique | `\n`, celui de la couche 5 qui a produit les sorties de campagne |
