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

Les scripts de vérification de l'auteur sont tous dans **un seul dossier**, `tests/adversarial/rapports/revision2_verifications/`. Ceux de la revue sont dans `tests/adversarial/rapports/revue_contre_exemples/`.

## Révision n° 7 (arbitrages du mainteneur du 28/11, après la tranche 1a)

Ce sont des précisions ciblées, pas une révision générale.

| Point | Section | Ce qui change |
|---|---|---|
| Observations partielles et correction structurée | § 2.1 f (nouveau) | Une observation partielle est conservée. On publie une qualité **conditionnelle** (observations complètes, par défaut) et une qualité **opérationnelle** (ce que l'utilisateur reçoit), toujours avec la couverture. Les lignes de saknussemm se répartissent en quatre classes : corrigée (dont `review_required`), abstention volontaire, refus technique, repli. Seul le repli rend l'étape partielle. L'évaluation lit l'état déclaré et ne le reconstruit pas ; la tranche 2 le porte au `StepRecord`. |
| Chemins d'alignement des analyses qualitatives | § 2.1 a, § 6.2 | Les confusions, la taxonomie et le diff surligné gardent **temporairement** le chemin RapidFuzz. La convention est inscrite dans chaque résultat concerné (`alignment_path: "rapidfuzz"`, contre `"canonical"` pour les comptes). Le résultat ne prétend pas décomposer exactement les comptes canoniques quand ils divergent. La fréquence et l'ampleur des divergences seront mesurées avant toute reconstruction canonique (question ouverte, non bloquante). |
| Taille du JSON | § 2.1 a | Le JSON complet est conservé. Sa taille compressée est mesurée et publiée, sans nouveau format. |
| Verdicts de l'ancienne inférence | § 2.1 d | Jusqu'à la livraison de la tranche I, aucun verdict n'est **confirmatoire**. Tout résultat de test produit par l'ancienne inférence est étiqueté **exploratoire** dans le rapport et le `RunResult`, et le mot « significatif » n'est plus employé comme verdict. Le chantier de recherche statistique n'est pas rouvert pour autant.<br>Le périmètre est fixé par l'inventaire du 28/11 :<br>• les tests inter-moteurs (Wilcoxon, Friedman, Holm, Nemenyi) : sections `cross_engine` et `key_measures`, `_inference_text` ;<br>• le scalaire `significance_p` ;<br>• les tendances longitudinales de l'historique web (pente OLS, rupture de Pettitt).<br>Les p brutes et corrigées restent publiées comme nombres. Le payload porte un statut `exploratory` ; aucun libellé « significatif / significant / significative » ne sert de verdict, et aucune paire n'est dite « significative ». Les booléens internes (`significant`) ne sont plus publiés comme verdicts. |
| Validation sémantique de l'archive | § 2.3 e, I (tranche 3) | Une archive relue est validée sémantiquement. Chaque scalaire doit égaler la finalisation de sa statistique, et chaque agrégat doit égaler la combinaison des observations conservées. Sinon l'archive est refusée. |
| Coût de l'alignement canonique | § 2.1 a | Il est mesuré sur des textes longs et fortement dégradés (pages entières bruitées, CER élevé), pas seulement sur les petits exemples. |
| Réévaluations | D-313 | Les réévaluations faites sur `abee7b5` seul (S30) sont distinguées de celles qui demandent les deux correctifs gelés (`aba0fe7`, `50cad9f` : S31, S31L). Les `RunResult` v5 d'origine et leurs réévaluations v6 sont conservés comme artefacts distincts, avec leur provenance. L'écart d'un ULP du CER Dresden E5 est consigné dans D-313. |

## Révision n° 6 (arbitrages du mainteneur)

| Point | Section | Ce qui change |
|---|---|---|
| **Défaut du générateur** de `revision2_verifications/d1_d3_options.py` | § 2.1 d, annexe (D3) | **Partie (1), D3** : FN était fixe alors que TP variait, donc TP + FN ≠ 5. Corrigé avec fn = 5 − tp et une assertion TP + FN = 5 pour chaque document et chaque pipeline. Après rejeu, la conclusion ne change pas :<br>• F1 de B : 0,592 → **0,586** (avec invention : 0,097, inchangé) ;<br>• Kish(den) de B : 39,0 → **39,8** (avec invention : 1,4, inchangé) ;<br>• F1 de A : **0,818** (non affiché avant) ;<br>• Kish(réf) = 40 dans les deux cas ; la p de BA s'écrit maintenant < 2·10⁻⁴ (aucun réplicat de signe contraire sur 4 999), et non « < 10⁻⁴ », qui excédait la résolution.<br>**Partie (2), B9c** : le générateur respectait déjà TP + FN = r (A : (r, 2r, 0) ; B : (r, 0, 0) ou (0, 0, r)). L'assertion est ajoutée ; rejoué, les chiffres sont **identiques**. |
| **Principe métrologique / inférentiel** | en-tête, § 2.1 d, § 3, § 5, § 6.3 | Les garanties M et le cœur de K1 à K5 sont **inconditionnels**. Les invariants d'inférence (A3, A5, A8, A9, A10, A13) sont **conditionnels** à une procédure validée. Hors de ce cadre : « inférence non estimable » ou étiquette **exploratoire**. Les tranches métrologiques passent d'abord ; l'inférence conditionnelle (tranche I) et la recherche (R, sans échéance) sont à part. |
| B1 | § 2.1 a, M2 | Plancher au niveau du corpus, documenté ; les comptes et le taux d'erreur non tronqué sont publiés à côté. |
| B2 | § 2.1 d | Le bootstrap percentile et le bootstrap-t sont deux procédures distinctes. La cohérence de leurs p et IC n'est pas présumée. Toute procédure non validée reste exploratoire. |
| B3 | § 2.1 c | Grappes déclarées par le corpus, avec la **population cible** et la **pondération des grappes** documentées. |
| B4 | § 2.1 d, A9 | Pas de famille exhaustive par défaut (720 tests sur Dresden). La spec déclare **avant l'expérience** des hypothèses principales et secondaires ; Holm s'applique à la famille confirmatoire déclarée. Sans déclaration, aucune inférence confirmatoire n'est publiée. |
| B5 | § 2.1 d, A5 | Méthode de permutation explicite, jamais `auto` ; analyses de rangs distinctes des tests du micro et du macro. |
| B6, B7 | § 2.1 b, c | validés |
| B8 | § 2.3 d | Reproductibilité sous environnement **et** protocole identiques (`ProtocolDefinition` + environnement complet), pas seulement les versions de NumPy et SciPy. |
| B9a | § 2.1 d, § 6.3 | Kish(réf) est utile, mais ne mesure pas directement l'influence d'une observation sur un ratio à dénominateur d'hypothèse : ce n'est pas une garantie. |
| B9b | § 6.3 | La calibration empirique est validée en principe, pas comme preuve générale. Une calibration à α = 0,05 ne démontre rien aux seuils extrêmes qu'exige Holm. |
| B9c | § 2.1 d | Aucune solution validée. Les familles à dénominateur d'hypothèse rendent **« inférence non estimable »** ; les options passent en recherche (§ 6.3). |
| Tranches | § 5 | Ordre : 1a, 1b, 2, 3, 4 (métrologiques), puis I (inférence conditionnelle) ; R (recherche) sans échéance. |
| Tests de 1a et 1b | § 4.1 | Liste exacte : 17 tests valides importés, dont 3 reformulés (rév. 7 : `mx::…deplace_lagregat`) ; 9 discutables reformulés ; tests à écrire, dont les tests de la révision n° 7 (§ 4.1, « 1b · Tests de la révision n° 7 »). |
| Historique | annexe | Les révisions 1 à 5 sont déplacées en annexe, sans modification de leur contenu. |

## Principe : garanties métrologiques et garanties inférentielles

> « Les calculs des métriques, leur agrégation, l'applicabilité et les supports doivent être corrects pour **toutes** les observations. L'inférence statistique, en revanche, est **conditionnée** à un protocole, des hypothèses et des méthodes **effectivement validées**. » (mainteneur)

| Nature | Ce qui est garanti | Où |
|---|---|---|
| **Métrologique** (inconditionnelle) | Vrai pour **toute** observation, sans hypothèse statistique : statistiques suffisantes, combinaison et finalisation, agrégats micro et macro, quatre axes, supports, couverture, échecs, étapes, identité, archive, correspondance. | K1 (§ 2.1 a), K2 (§ 2.1 b, c, e), K3, K4, K5 ; invariants M, A1, A2, A4, A6, A7, A11, A12, I, F ; tranches 1a, 1b, 2, 3, 4 |
| **Inférentielle** (conditionnelle) | Vrai seulement pour une procédure **validée**, sous sa H0 nommée, sur une famille confirmatoire **déclarée** a priori. Sinon : « inférence non estimable », ou étiquette « exploratoire » (jamais « significatif »). | § 2.1 d ; invariants A3, A5, A8, A9, A10 ; tranche I |
| **Recherche** | Procédures candidates non validées, sans échéance de livraison. | § 6.3 ; A13 |

Procédures **validées** en 1.0 :
- **SF**, le changement de signe exact (énumération, ou tirages en nombre suffisant pour le plus petit seuil de Holm) ;
- la **permutation explicite des rangs** ;
- **Holm**, sur la famille déclarée.

Toute autre procédure (bootstrap percentile, bootstrap-t, PS) est **non validée**.

**Les questions ouvertes de B9 ne bloquent pas** les corrections suivantes, toutes métrologiques :
- le F1 ;
- le CER sur les références vides ;
- l'intégrité des artefacts ;
- les échecs partiels ;
- l'archivage ;
- les correspondances documentaires.

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
| Exactitudes | `char_accuracy`, `word_accuracy`, `fca` | (erreurs, n_réf) | max(0, 1 − e/n), plancher **au niveau du corpus**, après combinaison (B1, documenté) ; les comptes (e, n) et le taux d'erreur **non tronqué** e/n sont publiés à côté | n = 0 |
| Appariement P/R/F | `ner_f1`, `ner_f1_exact`, `region_detection`, `bow_*` | (tp, fp, fn) | F1 = 2tp/(2tp+fp+fn) ; P ; R | dénominateur nul |
| Proportions | `searchability`, `diacritic_err`, `mufi_err`, `hcpr`, `air`, `numseq_*`, `unanchored_trigrams`, `*_coverage`, préservation | (k, n) | k/n | n = 0 |
| Texte par région (R2) | `region_cer`, `line_identity_cer` | (éditions sur paires bijectives **+ texte de l'hypothèse non apparié + texte de la référence non apparié**, car. réf.) | ratio | car. réf. = 0 |
| Ordre de lecture (R3) | `reading_order_tau` | (discordantes, paires que la référence ordonne) sur les régions appariées | d/(c+d) | aucune paire |
| Calibration (analyse) | ECE, MCE | (n_b, justes_b) entiers, Σ conf_b en `Fraction`, sur 10 classes fixées par le protocole | ECE = (1/N) Σ_b \|justes_b − Σconf_b\| ; MCE = max sur classes non vides | N = 0 |
| Moyennes | estimande macro, durées, coûts | (Σ x exacte, n) | Σx/n | n = 0 |
| Quantiles (P3) | percentiles par ligne | multi-ensemble des valeurs **du document** ; combinaison = concaténation | quantile, méthode déclarée | vide |

La valeur ponctuelle (page, micro, macro) est **exacte**, et c'est une garantie métrologique. Les procédures de tirage de la tranche I (SF en tirages) parcourent les documents dans l'ordre canonique (tri par id) ; leurs sorties sont reproductibles sous environnement et protocole identiques (B8). Les IC de quantiles relèvent de la recherche (A13, § 6.3).

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

**Ce que le macro ne voit pas (N3).** Un document sans référence est hors de D^M par définition, donc le macro ne voit jamais l'invention sur un tel document. Elle est visible à deux endroits :
- au **micro**, par les insertions et les fp au numérateur ;
- dans l'analyse dédiée **« invention hors référence »** (C5). Elle est calculée sur le **support apparié** de chaque paire (documents sans référence où les deux pipelines ont une statistique), et sur le support global de la famille pour le tableau. Pour chaque pipeline, la couverture des pages sans référence (mesurées / attendues) est publiée à côté. Unité inventée, par famille dont le macro est publié :
  - taux d'édition, MER, cMER, exactitudes : insertions (caractères ou mots), soit \|h\| ;
  - F1 et rappels (NER, régions, `bow`) : fp ;
  - texte par région : texte des régions d'hypothèse non appariées ;
  - proportions à dénominateur de référence (`numseq_*`, `searchability`, `diacritic_err`, `mufi_err`, `hcpr`, préservation, couvertures) : « **non définie** », car la statistique ne compte aucune unité de l'hypothèse. La fiche de ces métriques dit « insensible à l'invention par construction ».

| Support | Définition | Analyses |
|---|---|---|
| Conditionnel, par pipeline | D^μ_P ; D^M_P = D^M ∩ D^μ_P | agrégats micro et macro d'un pipeline ; couverture ventilée par axe et par motif (l'IC marginal n'a pas de procédure validée en 1.0 : § 6.3) |
| Apparié, par paire | D^μ_AB = D^μ_A ∩ D^μ_B ; D^M_AB = D^M ∩ D^μ_A ∩ D^μ_B | Δ micro et Δ macro ponctuels (métrologiques) ; leurs p et IC si une procédure validée s'applique (§ 2.1 d) ; Wilcoxon de la paire |
| Global, sur la famille | D^μ_F, D^M_F (∩ sur F) | Friedman et Nemenyi ; **seul tri** multi-pipelines (P8 : les ordres appariés ne composent pas un classement) |
| Sensibilité `empty_page` | attendus ∩ {VT disponible} | toute part manquante notée vide : unité en échec, région en échec, fin tronquée (R6) |

**Grappes (B3).** Les grappes sont déclarées par le corpus (champ de `DocumentRef`). Le corpus documente aussi :
- la **population cible** : ce que l'échantillon de documents ou de grappes représente ;
- la **pondération des grappes** : le macro est une moyenne par document ou par grappe, déclarée.

Les deux sont publiés avec chaque agrégat. Le micro, ratio de sommes, ne dépend pas de la pondération ; le macro en dépend.

**Ce que publient les supports.** Les supports conditionnel, apparié et global sont **métrologiques**. Ils définissent sur quoi portent un agrégat, une couverture ou un Δ ponctuel, et restent corrects pour toute observation. Les colonnes « IC » et « p » qu'ils servent relèvent du § 2.1 d (inférence conditionnelle).

#### d. Inférence conditionnelle (points 2 et 10 ; B2, B4, B5, B9)

Rien dans cette sous-section n'est une garantie métrologique. Une p ou un IC est publié comme **confirmatoire** seulement si trois conditions sont réunies :
1. la comparaison appartient à la famille confirmatoire **déclarée par la spec avant l'expérience** (B4) ;
2. la procédure est **validée** pour la famille de métriques concernée ;
3. ses conditions d'application sont remplies.

Sinon, le résultat est publié comme :
- « **inférence non estimable** », avec son motif, quand aucune procédure validée n'existe ou que ses conditions ne sont pas remplies ;
- ou « **exploratoire** », quand une procédure validée est appliquée hors de la famille déclarée. Le résultat porte alors une p non corrigée et n'est jamais présenté comme « significatif ».

Le Δ ponctuel, lui, reste toujours publié : il est métrologique.

n est le nombre d'unités de rééchantillonnage : documents, ou grappes si elles sont déclarées.

| Procédure | Statut en 1.0 | H0 nommée | p | IC | Conditions |
|---|---|---|---|---|---|
| **SF** : changement de signe exact sur r_d(δ) = e_d − δ·n_d (Δ micro), ou sur d_d(δ) = r_A,d − r_B,d − δ (Δ macro) | **validée** (exacte, à tout seuil) | A et B échangeables dans chaque unité | p(0) par énumération si 2^n ≤ 2^16 ; sinon (k+1)/(B+1) avec B + 1 ≥ m/α, pour que le plus petit seuil de Holm soit atteignable, et une graine déclarée | inversion du même test, {δ : p(δ) > α}, **sous le modèle déclaré d'effet constant**. Il est d'un seul tenant (monotonie, revue § 7.1) ; couverture mesurée 0,942 sous effets hétérogènes, une mesure et non une preuve | rejet possible dans une famille de taille m ssi max n₀ ≥ 1 + log₂(m/α) ; IC borné ssi m_unités ≥ 6 (C3, D4) |
| **Permutation des rangs** : Wilcoxon par paire sur D^M_AB ; Friedman et Nemenyi sur D^M_F si k ≥ 3 | **validée** (exacte) | échangeabilité | `zero_method="wilcox"`, `method=PermutationMethod` explicite, jamais `auto` (B5) ; rangs sur `Fraction` | — | publiée comme « analyse de rangs par document », **distincte** des tests du micro et du macro ; variance nulle → « non calculé » |
| **Holm** | **validé** | — | sur la famille confirmatoire déclarée (B4) ; un test non calculable y garde sa place (p = 1) ; aucune fusion de pipelines sur leurs résultats | — | m = taille de la famille **déclarée** |
| **BA percentile**, **bootstrap-t**, **PS** | **non validées** (B2, B9c) | R_A = R_B | — | — | non publiées en 1.0 ; recherche (§ 6.3) |

| Famille de métriques | Dénominateur | Δ micro en 1.0 | Δ macro en 1.0 |
|---|---|---|---|
| Taux d'édition ; proportions à dénominateur de référence ; `bow_recall`, rappel NER ; texte par région | référence | SF | SF |
| Exactitudes ; F1 ; MER, cMER | hypothèse, ou finalisation non linéaire | **« inférence non estimable »** (B9c) ; Δ ponctuel publié | SF (statistique linéaire des différences de scalaires sur D^M_AB, fixé par la référence) |
| Précisions, `unanchored_trigrams`, `air`, τ | hypothèse | « inférence non estimable » ; Δ ponctuel publié | pas de macro |
| ECE, MCE (analyses) | — | aucun test ; IC non estimable | — |

Règles :
- **Familles déclarées (B4).**
  - La spec déclare, avant l'expérience, ses hypothèses **principales** et **secondaires**, chacune sous la forme (vue, métrique, estimande, paire de pipelines). Holm s'applique à la famille confirmatoire déclarée (Q1 : une famille ou deux, § 6.2).
  - Toute autre comparaison est descriptive (Δ ponctuel) ou exploratoire (p non corrigée de SF, étiquetée).
  - Sans déclaration, **aucune inférence confirmatoire** n'est publiée. La famille exhaustive (720 tests sur `dresden.yaml`) n'est jamais un défaut confirmatoire.
  - Chaque famille déclarée est publiée avec son m et le n₀ requis, ⌈1 + log₂(m/α)⌉. **La composition de la famille décide directement de ce qui est publiable** (D4).
- **Peu d'unités (C3).** Avec au plus 5 unités (les 5 grappes BNL), aucun Δ n'est significatif : SF a p ≥ 1/16. Avec 10 pages (Dresden), un rejet n'est possible que si la famille déclarée vérifie m ≤ α·2^(n₀−1), soit m ≤ 25 pour n₀ = 10.
- **Grappes et répétitions (P5, P6).**
  - SF échange A et B au niveau de la grappe déclarée.
  - Les grappes sont triées par leur plus petit id de document.
  - Une répétition n'est jamais une unité d'inférence.
  - Sous grappes, les rangs portent sur les moyennes par grappe, selon la pondération déclarée (B3), ou ne sont pas publiés.
- **Diagnostic de levier (B9a).** n_eff_réf = (Σ r_d)² / Σ r_d², sur une quantité de **référence** commune à la paire. Il n'est **pas** une condition de validité : il ne mesure pas directement l'influence d'une observation sur un ratio à dénominateur d'hypothèse. Il est publié à titre descriptif à côté de chaque Δ des familles concernées, et sert à la recherche (§ 6.3).

#### e. Échecs

`FailurePolicy = Literal["exclude", "empty_page"]`. `max_error` est retiré. Il n'y a pas d'imputation par défaut, y compris pour `partial` et `truncated` (R6). `UnitOutcome` gagne `partial`. La validation a lieu avant exécution : VT et image lisibles et hachées, pont de projection présent.

| | |
|---|---|
| **Supprime** | `Observation`, `micro_ratio`, `micro_ratio_ci` (aucune procédure d'IC marginal validée : § 6.3), `bootstrap_batch`, `_intervals`, `_aggregate`, `_error_rate`, `missed`/`_expects`, `worst`/`_score_failed`, F1 par document, `support ≥ 1`, la famille de Holm « tests calculés », le jugement par `editops` non canonique |
| **Bibliothèques** | `scipy.stats` (`permutation_test`, `wilcoxon` avec `PermutationMethod`, `friedmanchisquare`) ; `rapidfuzz` (distances simple et pondérée) ; `fractions` (stdlib). Oracles : DP lexicographique (S/D/I), jiwer (S+D+I quand Σ n_réf > 0), énumération exhaustive (NER, régions), scipy |
| **Couche** | `evaluation` (3) ; `partial` en `domain/usage.py` (1) ; `not_transcribed` déclaré par l'importeur (`app`, 6) ; validation préalable en `app` |
| **Ne fait pas** | Pas d'algèbre générique, pas de méthode delta pour l'IC, pas de bornes dans `MetricSpec`, pas d'imputation par défaut |

#### f. Observations partielles et issues de la correction structurée (révision n° 7, tranche 1b)

**Une observation partielle est conservée.** Son axe 3 vaut `partial_output` ou `truncated_output`, et sa statistique est calculée sur ce qui a été produit, puis stockée (`stat_partielle`). Elle n'est jamais jetée, ni imputée en silence.

**Deux qualités publiées, toujours avec leur couverture.**

| Qualité | Population | Rôle |
|---|---|---|
| **Conditionnelle** (défaut) | observations complètes : axes 1 à 3 au vert | qualité de ce que le pipeline sait faire quand il va au bout |
| **Opérationnelle** | toutes les unités attendues : partielles notées telles que produites ; échecs notés comme une sortie vide (politique `empty_page`) | qualité de ce que l'utilisateur reçoit réellement |

La couverture (complètes / partielles / en échec / attendues) est publiée à côté des deux. Les deux qualités sont **métrologiques** : aucune inférence n'en découle sans procédure validée (§ 2.1 d).

**Issues d'une ligne de correction structurée (saknussemm), en quatre classes.** Les trois premières sont des **décisions du correcteur**. L'unité reste complète et sa sortie est notée normalement.
- **Corrigée** (`corrected` avec texte modifié). `review_required` en est une sous-classe : la correction est gardée, et le correcteur déclare ne pas pouvoir l'établir. Elle est comptée à part.
- **Abstention volontaire**. Le producteur propose le texte source inchangé (statut `corrected` avec `final_text == source_text`). C'est aussi le cas d'une règle qui ne s'applique pas. Ce n'est ni un échec ni un repli.
- **Refus technique**. Les garde-fous de la bibliothèque ou une revue refusent la proposition. La source est gardée, avec un code dans l'ensemble fermé `FALLBACK_REASON_CODES`, hors `all_attempts_exhausted` et `chunk_error_absorbed` : étage C (`too_different_from_source`, `closer_to_*`, `absorbs_*`, `unanchored_run`, `rejected`), césure et paires, passes document-wide, revue humaine. C'est une décision valide, pas une panne.

La quatrième est un **incident d'exécution**.
- **Repli**. Aucune proposition exploitable n'a pu être obtenue (`all_attempts_exhausted` : délais, réponses illisibles ; `chunk_error_absorbed`). La source est gardée par nécessité : l'étape est **partielle**. Une unité dont **toutes** les lignes sont en repli est partielle, sans aucune correction, et ne passe **jamais** pour `ok`.

**Comptes publiés par unité et par pipeline** : lignes corrigées, `review_required`, abstentions, refus par code, replis par code. Ces classes sont **disjointes** : `corrected` n'inclut pas `review_required`, et le total des corrections est leur somme.

**Précisions d'implémentation tranchées le 28/11**, après les tests rouges :
- **`failure_policy`.** Elle choisit lequel des deux agrégats est l'agrégat **principal** : `exclude` donne le conditionnel, `empty_page` donne l'opérationnel. Les deux sont **toujours** publiés.
- **Couverture.** Ses catégories sont : complètes, partielles (`partial_output` **et** `truncated_output`, ventilées par motif), en échec, attendues. La couverture publiée à côté de l'opérationnel est la même que celle du conditionnel.
- **Diff surligné.** Son payload de données (`document_texts`, couche 3) porte `alignment_path`, que le rendu affiche.
- **Statut `exploratory`.** Tout payload de l'ancienne inférence le porte, y compris `not_computed`.
- **Historique web.** Une rupture de Pettitt est affichée dès que le test est calculable, avec sa p et l'étiquette exploratoire, quelle que soit la valeur de p. Filtrer sur la significativité serait un verdict implicite.
- **Wording des sections.** Toute phrase qui qualifie un résultat de test de « verdict » est reformulée en « résultat (exploratoire) ».
- Le CER compare le texte produit à la vérité terrain, quelle que soit la classe.
- La classe change seulement l'axe 3 (repli ⇒ `partial_output`) et les comptes publiés.

**Où vit chaque état** (dépendance documentée avec la tranche 2) :
- **Adaptateur (couche 5)** : il classe les lignes à partir du rapport de la bibliothèque (`DecisionStage.status`, `reason.code`), sans lire de texte pour deviner, et déclare la complétude de son étape.
- **Exécuteur (couche 4)** : il porte cette déclaration dans `UnitOutcome = partial` avec ses comptes.
- **Évaluation** : elle **lit** l'état déclaré et ne le **reconstruit jamais**, ni à partir des textes ni à partir d'heuristiques.
- **Tranche 2** : en 1b, l'état est porté par unité. La tranche 2 le déplace dans le `StepRecord` de l'étape concernée, sans changer sa sémantique.

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
validation(record) (N4) : toute la partie CALCULÉE de record.definition ET tout record.environment, re-calculés dans le
                   processus courant, en RÉSOLVANT chaque élément par son NOM et non par le chemin enregistré :
                   module -> résolution SANS IMPORT : pour chaque composant du nom, chercheurs de sys.meta_path
                   (finder.find_spec(nom, chemins du parent)), jamais importlib.util.find_spec, qui importe le parent ; fichier de poids -> chemin dérivé des réglages effectifs ;
                   binaire -> shutil.which(nom) puis ld.so --list ; chaque empreinte est comparée à celle enregistrée sous ce nom,
                   et toute sortie --version doit être identique
RunMode = Literal["fresh", "resume", "rescore"]
```

- **Deux temps (P10, N4).** La recherche ne porte que sur ce qui est connu **avant** l'exécution. Le record trouvé n'est réutilisé que si la validation passe, et elle couvre tout ce que la recherche ne contient pas : sources sur disque de la brique (N5), fichiers de poids, environnement.
  - **Résolution par nom.** Comparer le chemin enregistré laisserait passer un module que le processus courant résout ailleurs (autre venv, homonyme plus tôt dans `sys.path`).
  - **Échec de validation.** L'étape est réexécutée et le record remplacé, dans le cache seulement.
  - **Vérification.** `r2_p10_recherche_validation.py` doit refuser la réutilisation dans ses deux cas : poids remplacés, et module résolu dans un autre venv.
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
  sha256 des SOURCES SUR DISQUE (N5) : tous les .py du paquet déclaré par la brique et de sa fermeture d'imports STATIQUE
    (graphe AST des `import`, résolu sans import par les chercheurs de sys.meta_path, composant par composant ;
    un paquet qui modifie son __path__ à l'exécution est étiqueté `resolution_statique`), limitée à sa distribution (pour une brique first-party :
    les paquets cinoc atteints), chemins relatifs triés ; INDÉPENDANT de ce que le processus a chargé,
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
- **Pourquoi deux mécanismes (N5).** Ce qui est **chargé** dépend de l'histoire du processus : trois processus qui calculent le même CER chargent 68 ou 69 modules (`r2_p11_definition_chargee.py`). Le chargé ne sert donc qu'à l'**environnement**, qui valide le cache. La **définition**, qui identifie le protocole et la brique, ne hache que les sources sur disque de la fermeture statique.
  - Coût assumé : toute modification d'un `.py` de cette fermeture change la définition, donc invalide le cache des briques concernées.
  - Un import dynamique (`importlib.import_module(nom_calculé)`) échappe à la fermeture statique. La brique qui en fait doit déclarer ces modules ; à défaut, la vérification (A, I1) échoue.
- Il sert à **valider** le cache (§ 2.2) et à **qualifier** une reproduction. Il ne fait jamais partie de l'identité de définition.
- Les bibliothèques ouvertes par `dlopen` dans un sous-processus échappent à `ld.so --list` : la limite est écrite (O4).

#### d. Protocole, corpus, observation (R9, P11, P12)

```
ProtocolDefinition (portable) = H(spec de vue, définition de chaque métrique (famille, finalisation, règle canonique P1, version de définition),
                                  contenu du profil de normalisation, unicodedata.unidata_version,
                                  sha256 de TOUS les .py SUR DISQUE de cinoc.domain, cinoc.formats et cinoc.evaluation
                                  (fermeture statique d'evaluation) et des profils de normalisation, chemins relatifs triés (N5))
ProtocolEnvironment = extensions compilées chargées (rapidfuzz, numpy, scipy…), leurs versions, plateforme
CorpusIdentity      = H(liste triée de (id, sha256 image, {type: sha256 VT}))          # séparée (P12)
ObservationId       = H(sha256 de la sortie notée, sha256 de la VT DE CE document, ProtocolDefinition)
```

| Opération | Exécute | Résultat exigé | Coûts publiés |
|---|---|---|---|
| Relecture des observations | rien | octets identiques, hors horodatages | historiques, attribués à leur run |
| Reproduction sous **définition** identique | évaluation (et moteurs en rejeu) | mêmes statistiques et scalaires (arithmétique exacte, P1 canonique), **quel que soit l'environnement** ; un environnement différent est publié comme qualification. Les sorties inférentielles qui reposent sur des tirages ne sont reproductibles que sous **environnement et protocole identiques** (B8) : `ProtocolDefinition` identique et environnement complet identique (plateforme, interpréteur, toutes les bibliothèques chargées), et pas seulement NumPy et SciPy | coûts du rejeu séparés |
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

#### a. Objectif (R11, N6, P16, P17)

Un seul appariement sert les boîtes de régions et les empans NER (P20, R8). L'admissibilité est en arithmétique exacte (P17) : 2·\|∩\| ≥ \|∪\| (ou > selon O2), en entiers dans un repère commun, en `Fraction` si les dimensions des pages diffèrent. Le calcul se fait page par page.

**Étape 1 : paires héritées, fixées (C4).** Sous filiation vérifiée, chaque paire héritée est **fixée avant toute optimisation**. Elle ne participe ni au critère du nombre de paires ni aux suivants. Quatre conditions, toutes requises :
- la chaîne de `StepRecord` de l'hypothèse a consommé l'artefact de la VT (même `content_hash`) ;
- chaque étape de la chaîne est déclarée `preserves_region_ids` ;
- même id, même page ;
- **géométrie de l'hypothèse identique** à celle de la VT de même id : boîte et polygone égaux en entiers (N6).

Raison : une filiation démontrée par les empreintes, avec une géométrie inchangée, est une preuve de correspondance (arbitrage 6). Elle prime donc sur une coïncidence géométrique, qui peut l'emporter au critère du nombre de paires quand des régions de la VT se recouvrent (`r3_n6_heritage_hors_optimum.py` (b) : `region_cer` vaut 0,76 avec la paire gardée, 0,84 avec l'optimum). Un échange d'ids change la géométrie, donc ne crée aucune paire héritée (`r2_r11_filiation_permutee.py` : `region_cer` 0). Une transformation géométrique déclarée est hors 1.0 (O13).

**Étape 2 : le reste.** Sur les régions non héritées, l'appariement bijectif maximise, dans l'ordre lexicographique :
1. le nombre de paires admissibles ;
2. Σ IoU ;
3. Σ distance d'édition des textes appariés, quand il y a du texte (P16) ;
4. l'ordre géométrique canonique (page, y0, x0, y1, x1).

Aucun identifiant n'intervient à l'étape 2. Sans filiation, l'appariement entier est l'optimum de l'énumération exhaustive (M8).

**Calcul exact (P17), par composante connexe** du graphe d'admissibilité d'une page :
- un poids **entier** par composante, où chaque critère est multiplié par une borne strictement supérieure au maximum de tous les suivants ;
- l'IoU est ramenée au dénominateur commun des seules unions des paires **admissibles** de la composante ;
- l'affectation hongroise se fait en entiers Python.

Le coût mesuré par la revue (ppcm de 63 334 bits à n = 100, `r2_p17_poids_entier_cout.py`) vient du ppcm pris sur toutes les unions de la page. Par composante, il est borné par la taille de la composante. `linear_sum_assignment` (flottants) reste l'oracle sur les instances sans ex æquo, avec l'énumération exhaustive sur les petites.

**Héritage.** Sous filiation, `region_detection` (et les fusions et scissions) sont `not_applicable` (`regions_inherited`). `line_identity_*` ne s'appliquent que sous filiation vérifiée des lignes : même règle, géométrie de ligne identique (P19).

#### b. Ordre partiel et linéarisation (R3, N7)

`LayoutPage.reading_order: tuple[str | OrderGroup, ...]`, avec `OrderGroup(ordered: bool, members)`. C'est un changement de domain (couche 1), mappé depuis les `OrderedGroup`/`UnorderedGroup` de PAGE (ALTO n'a que des groupes ordonnés). La référence ordonne (a, b) seulement à travers un groupe ordonné : c'est ce que mesure le τ.

**Linéarisation pour la vue texte (N7).** Les membres d'un groupe non ordonné sont rangés dans un **ordre géométrique canonique** : (y0, x0) de la boîte englobante du membre, puis id. Jamais dans l'ordre de déclaration XML. Un membre sans géométrie est rangé après les autres, par id, et l'observation porte l'étiquette `order_by_id`.

Invariant : permuter les déclarations d'un groupe non ordonné ne change ni la projection ni le CER (`r2_r3_groupe_non_ordonne_cer.py` : 0,919 contre 0,0 aujourd'hui, identiques après correction). La fiche de la vue texte publie que cette vue impose un ordre là où la VT n'en impose pas. La métrique insensible à l'ordre des lignes est `fca`. L'appariement des membres avant concaténation est l'option ouverte O14.

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

La colonne **Revue** nomme le contre-exemple de `rapports/revue_contre_exemples/` (ou de `revision2_verifications/`) que l'invariant doit satisfaire. Il est porté en test adversarial rouge au premier commit de la tranche indiquée (T).

**Nature des invariants.**
- **Métrologiques, inconditionnels** : tous les M, A1, A2, A4, A6, A7, A11, A12, tous les I et tous les F. Ils valent pour toute observation.
- **Inférentiels, conditionnels à une procédure validée** : A3, A5, A8, A9, A10. Ils s'énoncent « pour une procédure validée (SF, permutation des rangs, Holm sur une famille déclarée), alors … ; sinon, la sortie est « inférence non estimable » ou « exploratoire » ».
- **Recherche** : A13.

### Par métrique (M) (point 5)

| # | Invariant | Vérif. | Revue | T |
|---|---|---|---|---|
| M1 | **Taux d'édition.** (S, D, I) canoniques (max S), égaux à la DP lexicographique. CER/WER micro égaux à jiwer quand Σ n_réf > 0 (S+D+I seulement) ; MER s'en écarte sur les ex æquo d'alignement, comme écrit. Une page à référence vide ajoute \|h\| au numérateur, avec scalaire `zero_denominator`. Corpus entièrement vide : micro indéfini pour tous, écart volontaire à jiwer (qui rend 3 et 0), Σ insertions publiée. `not_transcribed` est hors des attendus. | P ; O DP, jiwer | `k1_editops_egalites.py`, `r2_p1_mer_parite_jiwer.py` | 1a |
| M2 | **Exactitudes** : valeur corpus = max(0, 1 − Σe/Σn), plancher au niveau du corpus (B1), jamais une moyenne de planchers par page. Les comptes (Σe, Σn) et le taux d'erreur **non tronqué** Σe/Σn sont publiés à côté. | P | — | 1a |
| M3 | **F1/P/R, agrégation** : F1(Σtp, Σfp, Σfn) ; un document sans référence contribue ses fp ; une catégorie présente seulement en prédiction a P = 0, R indéfini, sans erreur ; tout vide : indéfini. Oracle : énumération par IoU d'empan, règle de Cinoc ; pas nervaluate. (La propriété d'appariement relève de M8.) | P ; O énumération | `k1_ner_oracle_nervaluate.py` | 1a |
| M4 | **Texte par région** : le numérateur compte les éditions sur paires, le texte d'hypothèse non apparié et le texte de référence non apparié ; perdre une région n'est jamais mieux noté qu'une coquille. `line_identity_*` sont `not_applicable` sans filiation. | P | `k1_region_cer_reference_non_appariee.py` | 4 |
| M5 | **τ** : seules les paires que la référence ordonne comptent ; les paires d'un groupe non ordonné sont exclues ; avec un ordre total sans ex æquo, la valeur égale (1 − τ)/2 de scipy. | P ; O scipy | `k1_tau_groupe_non_ordonne.py` | 4 |
| M6 | **ECE/MCE** : pour toute partition et tout ordre des documents, l'histogramme combiné est égal (`==`) à celui des jetons poolés, et l'ECE identique bit à bit. | P | `k1_fsum_non_associatif.py`, `r2_r1_fraction.py` | 1a |
| M7 | **Projection unique** : un layout identique donne un CER nul sous toute vue. **Linéarisation canonique** (N7) : permuter les déclarations d'un groupe non ordonné ne change ni la projection ni le CER ; un membre sans géométrie est étiqueté `order_by_id`. | P | `r2_r3_groupe_non_ordonne_cer.py`, `r3_n7_rejeu.py` | 4 |
| M8 | **Appariement** (régions et empans NER). **Sans filiation** : optimum lexicographique égal à l'énumération exhaustive, quels que soient les ids. **Sous filiation vérifiée** : paires héritées (même id, géométrie identique) fixées, plus l'optimum de l'énumération sur le reste (C4). Un échange d'ids ne crée aucune paire héritée. Admissibilité exacte, indépendante de la largeur de page ; invariant par permutation ; `region_detection` `not_applicable` sous héritage ; fusions et scissions hors bijection, `ref_overlap` signalé ; calcul exact par composante connexe. | P ; O énumération, `linear_sum_assignment` | `k5_filiation_declaree.py`, `k5_objectif_lexicographique.py`, `k5_seuil_iou_flottant.py`, `r2_r11_filiation_permutee.py`, `r2_p17_poids_entier_cout.py`, `r3_n6_heritage_hors_optimum.py` | 4 |

### Par analyse (A)

| # | Invariant | Vérif. | Revue | T |
|---|---|---|---|---|
| A1 | **Agrégat conditionnel** sur D^μ_P et D^M_P, couverture ventilée par axe ; plus d'échecs, de régions perdues ou de troncatures ne l'améliorent jamais sans que la couverture le dise ; aucune part manquante n'est notée par défaut. | P ; A | `k2_partial_impute_en_silence.py` | 1b |
| A2 | **Quatre axes** : attendus = applicables ; `not_transcribed` distinct d'une référence vide ; statistique présente ⇔ axes 1 à 3 au vert ; `partial_output` et `truncated_output` à l'axe 3. | P ; A | `k2_partial_impute_en_silence.py` | 1b |
| A3 | **Δ micro et Δ macro, inférence conditionnelle** (§ 2.1 d).<br>• Pour les familles où SF s'applique (dénominateur de référence pour le micro ; toute famille à macro publié pour le macro) : rejet ≤ α sous échangeabilité à tout seuil, y compris les seuils de Holm. L'IC par inversion est d'un seul tenant, cohérent avec p, sous le modèle déclaré d'effet constant. « Aucun rejet possible dans la famille » si max n₀ < 1 + log₂(m/α) ; « IC non borné » si m_unités ≤ 5. En tirages, B + 1 ≥ m/α.<br>• Pour les familles à dénominateur d'hypothèse (micro) : « **inférence non estimable** », le Δ ponctuel étant publié ; BA, bootstrap-t et PS ne sont jamais publiés.<br>• Hors de la famille déclarée : au plus « exploratoire », jamais « significatif ».<br>• Un pipeline pire, par invention, ne change jamais un « estimable » en « non estimable » : le diagnostic est calculé sur la référence (D3). | P (simulation SF, énumération) ; O scipy | `k1_permutation_cer_temoin.py`, `n1_n2_procedure_unique.py` (a), `r3_sf_inversion.py`, `r4_sf_holm_dresden.py`, `r4_levier_echappatoire.py`, `d1_d3_options.py` (1) ; pour la famille non estimable : `k1_permutation_ratio_niveau.py`, `r2_r4_inversion_bootstrap.py`, `r3_ps_niveau_scenarios.py`, `r3_ba_n_min_scenarios.py`, `r4_ba_kish_confirmation.py` | I |
| A4 | **Macro et invention hors référence** (métrologique). Le macro est calculé sur D^M, fixé par la référence, avec la pondération des grappes déclarée (B3). Il ne voit pas l'invention sur un document sans référence (N3). **« Invention hors référence »** (C5) : calculée sur le support apparié (et global pour le tableau), avec la couverture des pages sans référence par pipeline. Deux pipelines identiques sur ce support ont la même valeur, quoi que chacun ait fait hors du support. L'unité inventée est déclarée par famille, et vaut « non définie » pour les proportions à dénominateur de référence. Pas de macro pour les familles dont le scalaire dépend de l'hypothèse. | A | `k2_support_macro_depend_du_pipeline.py`, `r2_r5_support_reference.py`, `r3_invention_hors_reference.py` | 1b |
| A5 | **Analyses de rangs** (conditionnel : permutation explicite validée). Nommées comme telles, distinctes des tests du micro et du macro (B5). `zero_method="wilcox"` et `method=PermutationMethod`, jamais `"auto"` ; p égale à l'énumération faite à la main sur rangs moyens ; ex æquo exacts préservés ; Friedman seulement si k ≥ 3 ; variance nulle → « non calculé » avec place gardée. | O énumération, scipy ; A | `k1_rangs_ex_aequo.py`, `r2_p4_wilcoxon_auto.py`, `n8_wilcoxon_methode_explicite.py` | I |
| A6 | **Classement** (métrologique) : deux pipelines ne s'ordonnent que sur leur support apparié ; aucun classement n'est composé à partir des ordres appariés ; seul le support global trie (B7). | A | `k2_ordres_apparies_intransitifs.py`, `k2_support_macro_depend_du_pipeline.py` | 1b |
| A7 | **Échecs** : aucune imputation par défaut ; `empty_page` note vide toute part manquante (unité, région, fin tronquée) et porte ce nom. | A | `k2_partial_impute_en_silence.py` | 1b |
| A8 | **Grappes** (conditionnel : SF par grappe). Échange A/B par grappe déclarée ; grappes triées par leur plus petit id, donc en singletons SF par grappe = SF par document, bit à bit ; deux groupements donnent deux résultats ; une répétition n'est jamais une unité d'inférence ; population cible et pondération déclarées (B3). | P ; A | `k1_grappes_singletons_ordre.py` | I |
| A9 | **Famille de Holm** (conditionnel) : composée des seules hypothèses principales et secondaires **déclarées avant l'expérience** (B4) ; taille et membres indépendants des résultats ; un test non calculable, ou à variance nulle, garde sa place ; sans déclaration, aucune inférence confirmatoire n'est publiée. | P | `k1_rangs_ex_aequo.py` (cas 2), `r4_sf_holm_dresden.py` | I |
| A10 | **Invariance par ordre** (conditionnel) : p et IC de SF (et des rangs) invariants par permutation de l'ordre des documents de la spec, que ce soit en énumération ou en tirages triés par id. | P | — (constaté sur `micro_ratio_ci` : [0,0953 ; 0,7596] → [0,1032 ; 0,7403]) | I |
| A11 | **Analyses d'une vue** : étape cible et son entrée déclarée seulement. | A | — | 2 |
| A12 | **Coûts** : coût d'un préfixe ; facture de l'étape fautive comptée ; coûts historiques jamais additionnés aux coûts du rejeu. | A | — | 2, 3 |
| A13 | **Quantiles par ligne** (recherche). Les quantiles eux-mêmes sont métrologiques (multi-ensemble par document) ; leur IC n'a pas de procédure validée en 1.0. Piste : tirer des documents, couverture mesurée à 0,92 contre 0,25 en tirant des lignes (P3). | P (simulation) | `k1_quantiles_grappes.py` | R |

### Identité, provenance, archive (I)

| # | Invariant | Vérif. | Revue | T |
|---|---|---|---|---|
| I1 | **Identité d'exécution** : modifier un fichier chargé dans le processus (même importé par une autre étape, ou paresseusement), une bibliothèque partagée, une bibliothèque d'un binaire, un fichier de poids, une source de la brique sur disque ou un réglage envoyé interdit la réutilisation. Il en va de même d'un module que le processus courant **résout ailleurs** (autre venv, homonyme dans `sys.path`) : la validation résout par nom. L'environnement enregistré ne dépend ni de l'ordre des étapes ni de celui des documents. La version du paquet et les réglages opérationnels n'entrent pas dans la définition. | A | `k4_fichiers_executes_sys_modules.py`, `k4_binaire_bibliotheque_partagee.py`, `r2_p10_recherche_validation.py`, `r3_n4_n5_rejeu.py`, `n5_resolution_sans_import.py` | 3 |
| I2 | **Identité du corpus** : un octet changé d'une image ou d'une VT change `CorpusIdentity`. | A ; P | — | 3 |
| I3 | **Identité du protocole** : `ProtocolDefinition` hache les sources **sur disque** de la fermeture statique. Elle est identique pour trois processus qui chargent des ensembles de modules différents, et identique sur deux plateformes aux mêmes sources. Corriger la VT de d2 ne change pas l'`ObservationId` de d1. Changer de profil, de métrique ou de version Unicode change la définition. | A | `k4_observation_id_depend_du_corpus.py`, `k4_protocole_depend_de_la_plateforme.py`, `r2_p11_definition_chargee.py`, `r3_n4_n5_rejeu.py`, `n5_resolution_sans_import.py` | 3 |
| I4 | **Relecture** : octets identiques. | P | — | 3 |
| I5 | **Reproduction** : à définition identique (sources sur disque), statistiques et scalaires identiques quel que soit l'environnement ou l'historique du processus, l'écart d'environnement étant publié ; réévaluation = nouvelles identités avec filiation. | A | `k4_protocole_depend_de_la_plateforme.py`, `r2_p11_definition_chargee.py` | 3 |
| I6 | **Intégrité** : refus d'une archive altérée, d'un fichier non listé (même ajouté à la racine), d'un lien symbolique ou dur hors option, d'un `fetch.txt`, ou d'une empreinte racine différente de l'ancre. Aucune authenticité revendiquée au-delà. | O `bagit` ; A | `k4_bagit_fichiers_hors_manifeste.py` | 3 |
| I7 | **Provenance** par unité et par étape (servi ou « inconnu »). | A | — | 2 |

### Fonctionnels (F)

| # | Invariant | Vérif. | Revue | T |
|---|---|---|---|---|
| F1 | **Isolation physique** + empreinte vérifiée. | A | — | 2, 3 |
| F2 | **Conservation de l'amont**. | A | — | 2 |
| F3 | **Reprise** : recherche sur le déclaré et les artefacts consommés ; validation sur la partie calculée de la définition et sur l'environnement, résolus par nom ; en `resume`, un record `partial` ou `failed` est retenté, même après un réglage opérationnel relevé. | A | `k3_reprise_record_non_ok.py`, `k4_fichiers_executes_sys_modules.py`, `r2_p10_recherche_validation.py` | 2, 3 |
| F4 | **Répétitions indépendantes**. | A | — | 2 |
| F5 | **Durabilité** : panne simulée après chaque appel de la séquence `fsync`/`replace` (système de fichiers factice, panne externe) ; jamais de record pointant un blob absent ou partiel. | A | — (argument P14) | 2 |
| F6 | **Relecture autonome** : ni réseau ni corpus. | A | — | 3 |
| F7 | **Archive scellée** jamais écrite ; un blob partagé altéré en place est détecté dans chaque archive qui le partage ; le mode 0444 n'est jamais compté comme une protection. | A ; O `bagit` | `k4_bagit_fichiers_hors_manifeste.py` | 3 |
| F8 | **Refus avant de payer**. | A | — | 1b |
| F9 | **Parité** des capacités nouvelles. | garde existante | — | 3 |

**37 invariants** (8 M, 13 A, 7 I, 9 F).
- **31 métrologiques**, inconditionnels.
- **5 inférentiels**, conditionnels : A3, A5, A8, A9, A10.
- **1 de recherche** : A13.

La révision n° 6 change la **nature** de A3, A5, A8, A9, A10 (désormais conditionnels), de A4 (devenu métrologique, son Δ passant à A3) et de A13 (recherche). Elle change le contenu de M2 (B1). Les révisions antérieures sont dans l'annexe.

---

## 4. Tests

Les chemins sont relatifs à `tests/adversarial/`. **ms** = `metriques_stats/test_ms_aggregation.py` ; **app** = `applicabilite_echecs/test_ce_applicabilite.py` ; **mx** = `applicabilite_echecs/test_ce_max_error.py` ; **st** = `metriques_stats/test_ms_statistics.py`.

### 4.1 Tranches 1a et 1b : tests rouges

**1a · Valides importés tels quels (9)**, aujourd'hui rouges :

| Test | Invariant |
|---|---|
| ms `::test_reference_vide__hallucination_comptee_au_numerateur[cer-4.4]`, `[wer-7.0]`, `[ins_rate-7.0]` | M1 |
| ms `::test_reference_vide__pipeline_qui_hallucine_est_classe_apres` | M1 |
| ms `::test_ner_f1__micro_sur_tp_fp_fn[ner_f1]`, `[ner_f1_exact]` | M3 |
| ms `::test_ner_f1__faux_positifs_sur_document_sans_entite_gt` | M3 |
| ms `::test_region_detection__micro_sur_tp_fp_fn` | M3 (agrégation ; boîtes disjointes, sans dépendance à l'appariement) |
| ms `::test_bow_f1__micro_sur_tp_hyp_ref` | M3 |

**1a · Discutables, attendu fixé par B1 (3)** :

| Test | Attendu reformulé |
|---|---|
| ms `::test_reference_vide__hallucination_comptee_au_numerateur[char_accuracy-0.0]` | `char_accuracy` corpus = max(0, 1 − 44/10) = 0,0, et le taux d'erreur non tronqué 4,4 est publié à côté avec ses comptes (44, 10). |
| ms `::…[fca-0.0]` | `fca` corpus = 0,0 (plancher au corpus), avec ses comptes et son taux non tronqué publiés à côté. |
| ms `::test_char_accuracy__vaut_un_moins_cer_corpus` | `char_accuracy` corpus = 1 − 0,5 = 0,5 (plancher appliqué au corpus, non atteint), et non 0,833 ; comptes publiés. |

**1a · À écrire** :
- `k1_editops_egalites.py` et `r2_p1_mer_parite_jiwer.py` (M1 : S/D/I canoniques, écart volontaire à jiwer) ;
- M1 sur un corpus entièrement vide (micro indéfini, Σ insertions publiée) ;
- `k1_ner_oracle_nervaluate.py` (M3 : oracle par énumération) ;
- `k1_fsum_non_associatif.py` et `r2_r1_fraction.py` (M6) ;
- M2 : comptes et taux non tronqué publiés ;
- propriétés P de M1, M2, M3 et M6.

Test à inverser : `tests/evaluation/test_metrics_text.py::test_cer_weight_is_reference_length`.

**1b · Valides importés (6, dont 1 reformulé par la révision n° 7)**, plus **2 valides reformulés** :

| Test | Invariant | Attendu |
|---|---|---|
| app `::test_applicabilite__artefact_sans_contenu_dune_unite_reussie_reste_attendu` | A2 | tel quel |
| app `::test_applicabilite__artefact_reference_mais_absent_du_disque_nabat_que_son_unite` | A2 | tel quel |
| app `::test_applicabilite__fanout_entierement_en_echec_nest_pas_une_unite_ok` | A2 | tel quel |
| app `::test_applicabilite__sortie_incompatible_refusee_ou_attendue` | A2, F8 | tel quel |
| mx `::test_max_error__un_echec_compte_comme_note_deplace_lagregat` | A7, § 2.1 f | **reformulé (rév. 7)** : `max_error` est retiré. Sous `empty_page`, l'échec est une hypothèse vide (tp 0, fp 0, fn 7). `bow_precision` (dénominateur : l'hypothèse) **ne bouge pas** (14/14), par construction ; `bow_recall` bouge de 14/14 à 14/21, `bow_f1` vaut 0,8. Par défaut : 1,0 sur 2 notés sur 3 attendus, couverture `step_failed` : 1 ; l'agrégat **opérationnel** vaut 14/21 (rappel). |
| ms `::test_ner_payload__label_absent_de_la_gt__ne_plante_pas` | A2 (rappel indéfini à l'axe 4) | tel quel |
| app `::test_applicabilite__reference_vide_nest_pas_comptee_notee` | A1, A4 | **reformulé (T1)** : micro de A = 12/120 = 0,100 ; 12 documents au support micro, 6 au macro (pages blanches hors de D^M). |
| app `::test_applicabilite__pipeline_non_applicable_nannule_pas_le_test_des_autres` | A6 | **reformulé (support)** : C, non applicable, ne change pas le support apparié de (A, B), qui compte 8 documents. La p (0,0078) relève de la tranche I. |

**1b · Discutables, attendu fixé par les arbitrages (6)** :

| Test | Conv. | Attendu reformulé |
|---|---|---|
| app `::test_applicabilite__gt_referencee_mais_absente_refusee_avant_de_payer` | C13 | Refus typé avant le premier appel de moteur (F8). |
| app `::test_applicabilite__fanout_sans_aucune_region_reconnue_reste_attendu` | C13 | La page reste attendue (2 attendus). Elle porte `partial_output`, n'est pas notée par défaut, et vaut 1,0 sous `empty_page`. |
| app `::test_applicabilite__reference_vide_nentre_pas_dans_le_test_apparie` | C01 | **Partie support (1b)** : les 6 pages blanches sont hors de D^M, donc hors de toute analyse par document. La p (0,031) relève de la tranche I. |
| mx `::test_max_error__un_echec_ne_note_jamais_mieux_quune_reponse` | C08 | Aucune imputation par défaut (couverture 2/3). Sous `empty_page`, l'échec vaut la valeur d'une hypothèse vide (CER 1,0), sous ce nom. |
| mx `::test_max_error__echec_note_comme_une_page_vide[ins_rate]` | C08 | Non noté par défaut ; sous `empty_page`, `ins_rate` de l'échec = 0,0, sous ce nom. |
| st `::test_echec_non_aleatoire__classement_sur_documents_communs` | C07 | A et B ne sont ordonnés que sur leur support apparié (B 0,040 devant A 0,050), et le tri multi-pipelines se fait sur le support global (B7). La couverture 7/8 de A est publiée. |

**1b · À écrire** :
- `k2_partial_impute_en_silence.py` (A1, A2, A7) ;
- `k2_support_macro_depend_du_pipeline.py`, `r2_r5_support_reference.py`, `r3_invention_hors_reference.py` (A4) ;
- `k2_ordres_apparies_intransitifs.py` (A6) ;
- A2 : troncature aval sous une vue amont complète ; unité saknussemm en repli total (`partial`) ; `not_transcribed` distinct d'une référence vide ;
- B3 : population cible et pondération des grappes publiées, macro par grappe différent du macro par document ;
- propriétés P de A1 et A2.

**1b · Tests de la révision n° 7** (écrits, rouges ; formes d'API fixées dans `tests/adversarial/_contrat.py`) :

| Fichier | Test | Invariant / ligne de la rév. 7 |
|---|---|---|
| `applicabilite_echecs/test_ce_observations_partielles.py` | `test_f_observation_partielle__conservee_avec_sa_statistique[cer, bow_recall]` | § 2.1 f, une observation partielle est conservée (`stat_partielle`), jamais jetée |
| id. | `test_f_deux_agregats__conditionnel_et_operationnel_avec_couverture[cer, bow_recall]` | § 2.1 f, deux qualités (CER : 1/28 et 21/56 ; rappel : 9/10 et 3/5) et couverture 2 / 1 / 1 / 4 |
| id. | `test_f_sans_partielle_ni_echec__les_deux_qualites_coincident` | § 2.1 f, sans part manquante les deux qualités sont égales |
| id. | `test_f_evaluation_lit_letat_declare__etape_complete_texte_identique`, `…__etape_partielle_texte_complet` | § 2.1 f, l'évaluation lit l'état déclaré, ne le reconstruit pas |
| id. | `test_f_persistance__aller_retour_json_conserve_partielle_agregats_couverture` | § 2.1 f, persistance |
| `applicabilite_echecs/test_ce_saknussemm_issues.py` | `test_f_quatre_classes__comptees_par_unite_et_par_pipeline` | § 2.1 f, quatre classes comptées par unité et par pipeline (corrigée, `review_required`, abstention, refus par code, repli par code) |
| id. | `test_f_seul_le_repli_rend_lunite_partielle` | § 2.1 f, seul le repli rend l'unité `partial` |
| id. | `test_f_unite_entierement_en_repli__jamais_ok_et_observation_partielle[chunk_error_absorbed, all_attempts_exhausted]` | § 2.1 f, 100 % en repli n'est jamais `ok` (la seconde variante dure ≈ 12 s : délais d'attente de la bibliothèque) |
| id. | `test_f_le_cer_ne_depend_pas_de_la_classe` | § 2.1 f, même texte sorti des trois décisions et du repli : même statistique, seul l'axe 3 change |
| id. | `test_f_unite_partielle_mixte__statistique_partielle_sur_le_texte_produit` | § 2.1 f, `stat_partielle` (2, 0, 0, 75) |
| id. | `test_f_persistance__aller_retour_json_conserve_les_comptes_de_classes` | § 2.1 f, persistance |
| `metriques_stats/test_ms_exploratoire_alignement.py` | `test_exploratoire__le_payload_dinference_porte_son_statut[wilcoxon, friedman]` | rév. 7, statut `exploratory` du payload ; p publiées comme nombres |
| id. | `test_exploratoire__aucun_libelle_de_verdict_dans_les_sections[…]` (16 cas) | rév. 7, aucun verdict dans `cross_engine` et `key_measures`, FR et EN |
| id. | `test_exploratoire__le_texte_dinference_n_emploie_aucun_verdict[…]` (4 cas) | rév. 7, `_inference_text` |
| id. | `test_alignement__confusions_et_taxonomie_portent_leur_chemin`, `…__les_comptes_portent_la_convention_canonique` | rév. 7, `alignment_path` `"rapidfuzz"` / `"canonical"` |
| id. | `test_alignement__confusions_sans_concordance_…`, `…__taxonomie_sans_concordance_…`, `…__concordance_vraie_…` | rév. 7, « ab » → « ba » : la concordance avec les comptes canoniques vaut faux ; vraie sans ex æquo |

**Inversés par la révision n° 7** (verdict « significatif » remplacé par l'étiquette « exploratoire » ; assertions numériques inchangées) : `tests/reports/test_cross_engine_section.py::{test_significant_verdict_and_parsed_columns, test_verdict_reads_the_holm_corrected_p, test_inference_block_renders_ranks_posthoc_and_intervals, test_renders_english_labels}` ; `tests/reports/test_key_measures_section.py::{test_significance_as_neutral_fact_wilcoxon, test_three_engines_are_a_friedman_with_its_pairs, test_a_friedman_not_rejected_after_holm_says_so}` ; `tests/interfaces/test_real_corpus_bnl.py::test_bnl_posthoc_shows_the_pair_that_differs` ; `tests/interfaces/web/test_history_trends.py::{test_history_says_when_a_slope_is_not_significant, test_history_says_when_a_slope_is_significant, test_history_renders_significant_change_point}`.

Tests à inverser :
- `tests/app/test_unit_outcome.py::test_max_error_is_zero_for_a_higher_is_better_metric` ;
- `…::test_max_error_scores_the_failure_like_an_empty_page`, qui devient le test de `empty_page` ;
- `applicabilite_echecs/…::test_troncature__notee_attendue_et_signalee` (vert), qui devient « exclu par défaut, noté sous `empty_page` ».

**Bilan 1a + 1b** : 17 valides (14 importés tels quels, 3 reformulés) et 9 discutables reformulés, plus les tests de la révision n° 7 (42 cas écrits, 11 tests inversés).

Les autres tests sont répartis ainsi :
- **valides** (34) : 3 coûts d'échec partiel, 5 `correction`/`decisions` et 5 `a5` en tranche 2 (`a5` aussi en 3) ; 2 `a7` et 7 de provenance en tranche 3 ; 12 de mise en page en tranche 4 ;
- **discutables** (30) : C05×2, C06×2 et C09 en tranche I ; C12×3 et C18×2 en 2 ; C14×4, C15×3 et C17×2 en 3 ; C03, C04, C10×2, C11×2 et C16 en 4 ; C19×4 hors code (plan d'expérience).

### 4.2 Autres reformulations (tranches I et 3)

| Test | Conv. | T | Attendu reformulé |
|---|---|---|---|
| st `::test_test_omnibus__meme_sens_que_le_cer_micro_affiche` | C05 | I | Le test SF du Δ micro du CER va dans le sens du Δ micro ou n'est pas significatif (p = 1). Le Wilcoxon n'est publié que comme analyse de rangs. |
| st `::test_test_omnibus__p_du_ratio_micro_par_permutation_appariee` | C05 | I | La p de SF du Δ micro est égale au changement de signe exact (1,0). Elle est corrigée par Holm seulement si la comparaison est déclarée. |
| st `::test_intervalles__ic_apparie_sur_la_difference_micro` | C06 | I | L'IC du Δ micro du CER par inversion de SF exclut 0 (Δ constant de 0,01). |
| st `::test_intervalles__meme_documents_que_le_test` | C06 | I | L'IC du Δ porte sur D^μ_AB, les mêmes documents que le test ; aucun IC marginal n'est publié en 1.0. |
| st `::test_bootstrap__grappes_documentaires_declarables` | C09 | I | Deux groupements donnent deux résultats SF ; en singletons, résultat identique à SF par document. |
| `version_manuelle__brique_modifiee…`, `identite_saknussemm__prompt…` | C17 | 3 | Inchangés par rapport à la révision 2 : la définition change avec les sources sur disque et avec les réglages envoyés. |

### 4.3 Tests qui figent un défaut

À inverser dans le commit du correctif.

| Test | Défaut figé | T |
|---|---|---|
| `test_metrics_text.py::test_cer_weight_is_reference_length` | page blanche hors du micro | 1a |
| `test_unit_outcome.py::test_max_error_is_zero_for_a_higher_is_better_metric`, `::test_max_error_scores_the_failure_like_an_empty_page` | `max_error` | 1b |
| `adversarial/…::test_troncature__notee_attendue_et_signalee` (vert) | troncature notée par défaut (R6) | 1b |
| `adversarial/…::le_type_interdit_bien_les_artefacts_dune_unite_failed` (vert) | « échec ⇒ aucun artefact » | 2 |
| `test_appariement_geometrique.py::test_identifiants_partages_inchanges` | id prioritaire sans filiation | 4 |
| `test_calibration.py::test_analysis_scores_tokens_against_reference_multiset` | multi-ensemble (si O3) | 4 |
| `test_micro_interval.py::test_zero_weight_documents_weigh_nothing` | IC marginal du micro (procédure retirée) | I |
| `test_inference_scipy_parity.py` (`family_size == len(computed)`) ; `test_inference.py::test_not_computed_says_why` (`family_size == 0`) | famille dépendante des résultats | I |

### 4.4 Autres tests à écrire

Tous les scripts de la revue (`revue_contre_exemples/`) et de l'auteur (`revision2_verifications/`), dans la tranche que leur donne le § 3, et :
- A12 (coûts historiques contre rejeu) ;
- I7 (modèle distant sans modèle servi) ;
- F2 (annulation) ;
- F4 (même dossier) ;
- F5 (panne simulée) ;
- F9 (entrées de parité) ;
- M8 (filiation vérifiée conservée) ;
- les propriétés P de M4, M5, M7, M8, A8, A9, A10, I2, I4 et F3.

---

## 5. Tranches

**Ordre.** Les tranches **métrologiques** passent d'abord : 1a, 1b, 2, 3, 4. Elles ne dépendent d'aucune question statistique ouverte. La tranche **I**, inférence conditionnelle, suit 1a et 1b et ne dépend pas de 2 à 4. La rubrique **R** (recherche, § 6.3) n'a pas d'échéance. Le premier commit de chaque tranche ne contient que des tests rouges (§ 4).

| Tranche | Nature | Invariants | Préalables (scripts portés en tests rouges) | Critère de fin |
|---|---|---|---|---|
| **1a · Statistiques suffisantes et agrégation** (K1) | métrologique | M1, M2, M3, M6 | § 4.1 (1a) ; `k1_editops_egalites.py`, `r2_p1_mer_parite_jiwer.py`, `k1_ner_oracle_nervaluate.py`, `k1_fsum_non_associatif.py`, `r2_r1_fraction.py` | Invariants établis contre les oracles (DP, jiwer, énumération). Prévisions vérifiées en re-notant les deux `RunResult` commités : CER/WER micro BNL et Dresden inchangés ; `char_accuracy` Dresden E5 de 0,3125 à 0,0, avec le taux d'erreur non tronqué 1,8614 publié à côté. |
| **1b · Non-mesure et supports** (K2) | métrologique | A1, A2, A4, A6, A7, F8 | § 4.1 (1b) ; `k2_partial_impute_en_silence.py`, `k2_support_macro_depend_du_pipeline.py`, `r2_r5_support_reference.py`, `r3_invention_hors_reference.py`, `k2_ordres_apparies_intransitifs.py` | Invariants établis. Dresden E5 publié « conditionnel 4/10 », avec la page tronquée 177 hors du défaut et dans `empty_page`. Grappes, population cible et pondération déclarées (B3). Amendement CLAUDE.md §3 (B6). |
| **2 · Étape** (K3) | métrologique et fonctionnelle | A11, A12 (préfixe), I7, F1, F2, F3 (recherche, réutilisabilité), F4, F5 | `k3_reprise_record_non_ok.py` | Socle `tesseract → deskew → tesseract` : chaque vue garde sa lecture. Une panne simulée ne perd aucune étape payée. |
| **3 · Identité et archive** (K4) | métrologique et fonctionnelle | I1 à I6, A12 (historique/rejeu), F3 (validation), F6, F7, F9 | `r2_p10_recherche_validation.py`, `r2_p11_definition_chargee.py`, `r3_n4_n5_rejeu.py`, `n5_resolution_sans_import.py`, scripts `k4_*` | Une archive de campagne est scellée, validée, relue et reproduite sous la même définition, réseau et corpus retirés. Son empreinte racine est publiée. |
| **4 · Correspondance** (K5) | métrologique | M4, M5, M7, M8 | `r2_r11_filiation_permutee.py`, `r2_r3_groupe_non_ordonne_cer.py`, `r2_p17_poids_entier_cout.py`, `r3_n6_heritage_hors_optimum.py`, `r3_n7_rejeu.py`, `r4_c4_c5_rejeu.py`, scripts `k5_*` | Optimum égal à l'énumération ; ordre partiel représenté ; NER sous l'appariement unique ; CER par région E1/E3/E4 re-notés. |
| **I · Inférence conditionnelle** | inférentielle (après 1a, 1b) | A3, A5, A8, A9, A10 | § 4.2 ; `k1_permutation_cer_temoin.py`, `n1_n2_procedure_unique.py` (a), `r3_sf_inversion.py`, `r4_sf_holm_dresden.py`, `k1_rangs_ex_aequo.py`, `r2_p4_wilcoxon_auto.py`, `n8_wilcoxon_methode_explicite.py`, `k1_grappes_singletons_ordre.py` ; pour la non-estimabilité : `k1_permutation_ratio_niveau.py`, `r2_r4_inversion_bootstrap.py`, `r3_ps_niveau_scenarios.py`, `r3_ba_n_min_scenarios.py`, `r4_ba_kish_confirmation.py`, `r4_levier_echappatoire.py`, `d1_d3_options.py` | Seules SF, la permutation des rangs et Holm sur la famille **déclarée** produisent des sorties confirmatoires ; toute autre sortie est « non estimable » ou « exploratoire ». Prévision : Δ micro du CER E5−E0 BNL par SF, par document (37 unités), p et IC par inversion calculés avant le correctif ; par grappe (5 unités), « aucun rejet possible ; IC non borné ». Chaque spec de campagne déclare sa famille, et son n₀ requis est publié. |
| **R · Recherche** | sans échéance | A13 et § 6.3 | `c1_c2_levier_calibration.py`, `r4_ba_kish_calibration.py`, `r4_diagnostic_non_ancillaire.py`, `d1_d3_options.py` (2), `k1_quantiles_grappes.py` | Aucun critère de livraison. Une procédure ne quitte R qu'en devenant validée, par une décision du mainteneur. |

---

## 6. Arbitrages

### 6.1 Rendus (intégrés au corps, retirés des questions ouvertes)

| # | Décision | Où |
|---|---|---|
| B1 | Plancher des exactitudes au niveau du corpus, explicitement documenté ; comptes et taux d'erreur non tronqués conservés et publiés à côté. | § 2.1 a, M2 |
| B2 | Bootstrap percentile et bootstrap-t sont distincts ; la cohérence de leurs p et IC n'est pas présumée ; toute procédure non validée reste exploratoire. | § 2.1 d |
| B3 | Grappes déclarées par le corpus ; population cible et pondération des grappes documentées. | § 2.1 c, A8 |
| B4 | Pas de famille exhaustive comme défaut confirmatoire. La spec déclare avant l'expérience les hypothèses principales et secondaires ; le reste est descriptif ou exploratoire ; Holm s'applique à la famille confirmatoire déclarée ; sans déclaration, aucune inférence confirmatoire. | § 2.1 d, A9 |
| B5 | Méthode de permutation explicite, jamais `auto` ; analyses de rangs distinctes des tests du micro et du macro. | § 2.1 d, A5 |
| B6 | Amendement de CLAUDE.md §3 (niveau absent → axes, `not_transcribed`, `partial`), validé. | tranche 1b |
| B7 | Tri multi-pipelines sur le support global seulement, validé. | § 2.1 c, A6 |
| B8 | Reproductibilité sous environnement **et** protocole identiques, pas seulement les versions de NumPy et SciPy. | § 2.3 d |
| B9a | Kish(réf) est utile et descriptif ; il ne mesure pas directement l'influence ; ce n'est pas une garantie de validité. | § 2.1 d, § 6.3 |
| B9b | Calibration empirique validée en principe, pas comme preuve générale ; une calibration à α = 0,05 ne démontre rien aux seuils extrêmes de Holm. | § 6.3 |
| B9c | Aucune solution validée : les familles à dénominateur d'hypothèse rendent « inférence non estimable » ; les options vont en recherche. | § 2.1 d, § 6.3 |

Décisions antérieures, toujours en vigueur :
- BagIt ;
- Hypothesis ;
- plancher SciPy ;
- rupture du schéma `RunResult` ;
- enregistrements par étape ;
- persistance atomique immédiate ;
- RO-Crate reporté à la publication ;
- fan-out multipage à image unique refusé en 1.0.

### 6.2 Encore ouverts (aucun ne bloque 1a ni 1b)

| # | Question | Tranche | Recommandation |
|---|---|---|---|
| Q1 | **Principales et secondaires** (B4) : une seule famille de Holm, ou deux familles corrigées séparément ? | I | Deux familles, chacune corrigée par Holm, les secondaires publiées comme telles. Pas de procédure hiérarchique en 1.0. |
| O1 | **C04** : lignes fantômes | 4 | insertions comptées |
| O2 | **C10 + P20** : seuil inclusif ou strict, unique pour boîtes et empans ; θ_m | 4 | inclusif (2·\|∩\| ≥ \|∪\|), la convention actuelle de NER et des régions, en arithmétique exacte ; θ_m = 0,5 |
| O3 | **C11** : jugement d'un jeton en calibration | 4 | alignement LCS |
| O4 | **C17** (résiduel) : stdlib et interpréteur, `dlopen` des sous-processus | 3 | stdlib non hachée, version de l'interpréteur dans l'environnement ; limite `dlopen` écrite |
| O5 | **C19** : plan d'expérience | hors code | témoin obligatoire ; `max_tokens` aligné ou montré non limitant ; recopie `repetition-1 → 2…5` retirée |
| O6 | **H2** : `shapely` | 4 | boîtes, faute de consommateur exigeant des polygones |
| O7 | **H4** : images IIIF | 3 | empreinte obligatoire, octets selon la licence |
| O8 | **H5** : faces des capacités d'archive et des modes | 3 | options de `cinoc run` ; web `front-absent` déclaré |
| O9 | **Authenticité** | 3 | ancrage de l'empreinte racine en 1.0 ; signature hors 1.0 |
| O10 | **Mutualisation** par défaut | 3 | reflink, sinon copie ; lien dur sur option |
| O11 | **Archives S30/S31** | 3 | script de conversion ponctuel hors produit, ou réexécution des parties gratuites |
| O12 | **Séparateur de blocs** de la projection unique | 4 | `\n` |
| O13 | **Filiation sous transformation géométrique déclarée** (redressement, recadrage) | 4 | hors 1.0 : sans géométrie identique, pas de filiation (N6) |
| O14 | **Groupe non ordonné dans la vue texte** (N7) : ordre géométrique canonique (retenu) ou appariement des membres à l'hypothèse avant concaténation | 4 | ordre canonique en 1.0, publié dans la fiche de la vue ; `fca` comme lecture insensible à l'ordre ; appariement des membres seulement si un consommateur l'exige |

### 6.3 Recherche (sans échéance de livraison)

| # | Sujet | État au moment de la révision n° 6 |
|---|---|---|
| R1 | **Procédure pour les familles à dénominateur d'hypothèse** (F1, MER, cMER, exactitudes, précisions, τ) : BA percentile, bootstrap-t apparié, diagnostic de queue | Niveaux mesurés (`d1_d3_options.py` (2), chiffres inchangés après correction du générateur ; revue n = 25 / lognormal n = 60 / lognormal n = 100) :<br>• BA : 0,062 / 0,082 / 0,073 ;<br>• bootstrap-t : 0,055 / 0,071 / 0,060 ;<br>• BA + kurtosis ≤ 10 : 0,062 / 0,075 / 0,063 ;<br>• bootstrap-t + kurtosis ≤ 10 : 0,055 / 0,062 / 0,054.<br>La revue mesure BA jusqu'à 0,096 (§ 8.2). Aucune n'est validée (B9c). |
| R2 | **Critère de calibration** : tolérance sur le niveau vrai, nombre de simulations | Proposé : borne de Clopper-Pearson à 95 % ≤ τ_niveau = 0,06, avec N ≥ 4 600 jeux retenus par case. C'est une calibration en principe, pas une preuve (B9b). Elle ne dit rien des seuils extrêmes de Holm, α/m. |
| R3 | **Diagnostic d'influence** propre aux ratios à dénominateur d'hypothèse, au-delà de Kish(réf) (B9a) | à concevoir |
| R4 | **IC marginaux** d'un pipeline, IC de l'ECE, IC des quantiles (A13) | aucune procédure validée ; pour les quantiles, la piste est le tirage par documents (P3) |
| R5 | **Puissance** perdue par la non-estimabilité | chiffrée par la revue : MER n = 20, 0,43 → 0 sous Kish(den) ; corrélé n = 30, 0,41 → 0,08 ; à mesurer sous la règle finale |

---

## Annexe : historique des révisions 1 à 5

Ces tables sont conservées telles qu'elles ont été arrêtées à chaque révision. Leurs chiffres et leurs recommandations ont été remplacés par le corps du document et par les arbitrages de la révision n° 6 (§ 6.1).

### Révision n° 5 (clôture de la révision n° 4, `REVUE_CONTRATS.md` § 8)

La revue conclut que rien n'empêche la tranche 1a, sauf le paramétrage de B9. Un script a été ajouté : `revision2_verifications/d1_d3_options.py`, 2 000 jeux par case, qui reprend les générateurs de la revue.

| Point | Section | Ce qui change |
|---|---|---|
| **D3** échappatoire par invention | § 2.1 d, A3, B9a | Le diagnostic porte sur des **quantités de référence**, les mêmes pour les deux pipelines : n_eff_réf = (Σ r_d)² / Σ r_d². r_d vaut tp+fn pour les F1 et rappels, n_réf pour les taux d'édition, MER et exactitudes, la taille de la référence (mots, entités, régions, paires ordonnées) pour les précisions et τ, et le nombre de mots de référence pour l'ECE. Ce diagnostic ne dépend d'aucune sortie et ne peut donc pas être contourné. Vérifié sur l'exemple de la revue : B, qui invente 2 000 entités, reste jugé (Kish(réf) = 40, aucun réplicat de signe contraire sur 4 999, soit p < 2·10⁻⁴), alors que Kish(den) tombait à 1,4 (chiffres du générateur corrigé en révision n° 6). Effet secondaire : pour MER à n = 20 (n_réf constant), Kish(réf) = n = 20, donc la comparaison redevient publiable. La perte de puissance chiffrée par la revue (0,43 → 0) disparaît par construction pour ce cas. |
| **D4** seuils de SF sans Holm | § 2.1 d, A3, B4 | Seuil écrit à l'échelle de la famille. Holm compare la plus petite p à α/m : **un rejet est possible dans une famille de taille m ssi max_i n₀,i ≥ 1 + log₂(m/α)**. Le test i n'est jamais rejeté si 2^(1−n₀,i) > α. La phrase sur Dresden est corrigée : avec la famille par défaut B4 sur `dresden.yaml` (m = 720), il faut **n₀ ≥ 15** ; les 10 pages Dresden **ne permettent aucun rejet** (p minimale corrigée 1,0, `r4_sf_holm_dresden.py`). Chaque campagne publie le n₀ requis par sa famille. **La composition de la famille (B4) décide donc directement de ce qui est publiable.** |
| **D2** critère d'A3 dépendant du nombre de simulations | A3, B9b | Le critère porte sur le **niveau vrai** : tolérance τ_niveau. Règle de décision : une case passe si la borne supérieure unilatérale à 95 % (Clopper-Pearson) du taux de rejet observé est ≤ τ_niveau, avec un nombre de jeux retenus N tel qu'un niveau vrai de 0,05 passe avec une probabilité d'au moins 0,9 lorsque τ_niveau = 0,06 : **N ≥ 4 600** par case. Calcul binomial exact de Clopper-Pearson : 0,905 à 4 600, 0,886 à 4 400. Un niveau vrai de 0,06 n'est accepté qu'avec une probabilité ≤ 0,05, à tout N, par construction. Les valeurs sont proposées, non décidées (B9b). |
| **D1** BA anticonservateur sous queue lourde | § 2.1 d, B9c | Rien n'est décidé. Les options sont présentées dans B9c avec leur niveau mesuré (Kish(réf) ≥ 20, 2 000 jeux, erreur Monte-Carlo ≈ 0,005-0,006), sur la revue (n = 25) puis le lognormal (n = 60 et 100) :<br>• (a) BA tel quel : 0,062 / 0,082 / 0,073 ;<br>• (b) **bootstrap-t apparié** (studentisé par l'écart-type linéarisé, une seule linéarisation pour tous les ratios de sommes ; p et IC des mêmes réplicats) : 0,055 / 0,071 / 0,060 ;<br>• (c) BA + diagnostic de queue (kurtosis des tailles de référence ≤ 10) : 0,062 / 0,075 / 0,063, avec 35 % à 65 % de jeux refusés sur le lognormal ;<br>• (b)+(c) : 0,055 / **0,062** / **0,054**. |

**Prêts pour la tranche 1a** (tests rouges dès maintenant) : M1, M2, M3, M6, A4, A5, A8, A9, A10, A13 ; et **A3**, avec les sept scénarios de la revue (§ 8.2) et ceux de `d1_d3_options.py`. Le correctif d'inférence des familles à dénominateur d'hypothèse attend B9a-c. SF, les rangs et Holm n'attendent que B4 (taille de la famille).

### Révision n° 4 (clôture de la révision n° 3, `REVUE_CONTRATS.md` § 7)

La revue lève 6 points de la révision n° 3 (N2, N3, N4, N5, N7, N8). Elle en lève 2 en partie, N1 et N6, et relève 5 contradictions nouvelles. Toutes sont traitées et **aucune n'est rejetée**. Deux scripts ont été ajoutés dans `revision2_verifications/` :
- `c1_c2_levier_calibration.py` : 5 scénarios, 8 valeurs de n, 600 simulations par case ;
- `n5_resolution_sans_import.py`.

Les 7 scripts `r3_*.py` de la revue deviennent des tests des tranches indiquées.

| Point | Section | Ce qui change |
|---|---|---|
| **C1** PS hors niveau sous fort levier (0,35-0,54) et dénominateurs lognormaux (0,10-0,14) | § 2.1 d, A3, B9 | **PS est retirée du contrat.** Sous le seuil du diagnostic, aucune procédure ne tient, ni PS ni BA (C2). Au-dessus, BA tient et fournit en plus l'IC. Les familles à dénominateur d'hypothèse n'ont donc qu'une procédure, BA, conditionnée au diagnostic. |
| **C2** BA hors niveau sous levier et lognormal, même à n = 50-100 | § 2.1 d, A3, B9 | **Diagnostic de levier déclaré** : taille effective de Kish n_eff = (Σ_d den_d)² / Σ_d den_d², calculée pour chaque pipeline de la paire, et l'on garde le minimum. On a toujours n_eff ≤ n, et n_eff ≈ 1/(part maximale) quand une unité domine. La p et l'IC de BA ne sont publiés que si **n_eff ≥ 20**, quel que soit n ; sinon « non estimable (levier ou effectif) ». Valeur calibrée sur les scénarios à levier borné (F1, levier r0 = 10, lognormal, MER) : au seuil 20, aucune case ne dépasse α + 3 erreurs Monte-Carlo, ni pour BA ni pour PS. La case la plus serrée est F1 à n = 50 (BA 0,073 pour une borne de 0,077). À 15, des cases dépassent : F1 n = 20 (BA 0,108) ; levier r0 = 60 à n = 100 (BA 0,116). Le scénario à levier **non borné** (r0 = 60) est déclaré non estimable dans 100 % des jeux jusqu'à n = 100 (n_eff médian 16,7). Le seuil sur n_eff remplace n_min, puisque n ≥ n_eff ≥ 20. |
| **C3** seuil « n ≤ 5 » de SF | § 2.1 d, A3 | Deux comptes distincts. **Rejet possible** ssi n₀ = #{unités à r_d(0) ≠ 0} ≥ 6, car la p minimale vaut 2^(1−n₀). **IC borné** ssi m = #{unités à n_d > 0} ≥ 6, car p(δ → ±∞) → 2^(1−m). Dans le contre-exemple n = 8 dont 3 pages vides, p(0) = 0,016 rejette, mais m = 5 donne un IC non borné, et c'est ce qui est publié. **Avec au plus 5 unités** (les 5 grappes BNL), **aucun Δ d'aucune famille ne peut être déclaré significatif** : SF a p ≥ 2^(1−5) = 1/16, BA est non estimable (n_eff ≤ 5 < 20), et la PS retirée aurait eu p ≥ 2/32. La même borne vaut pour le Wilcoxon de la paire. |
| **C4** paire héritée hors de l'optimum quand la VT se recouvre | § 2.4 a, M8 | Choix : **les paires héritées sont fixées avant l'optimisation**, qui ne porte que sur les régions restantes. Une filiation démontrée par les empreintes, avec une géométrie identique, est une preuve de correspondance (arbitrage 6) ; elle prime sur une coïncidence géométrique. La phrase « appartient toujours à un optimum » est retirée, de même que le critère 4. Invariant M8 : sans filiation, l'optimum est égal à l'énumération ; sous filiation, les paires héritées plus l'optimum de l'énumération sur le reste. Dans `r3_n6_heritage_hors_optimum.py` (b), `region_cer` vaut 0,76 (paire gardée) et non 0,84. |
| **C5** « invention hors référence » | § 2.1 c, A4 | Calculée sur le **support apparié** de la paire, et sur le support global pour le tableau. La couverture des pages sans référence est publiée par pipeline. L'unité inventée est déclarée par famille : insertions pour les taux d'édition, MER et exactitudes ; fp pour les F1 et rappels ; texte d'hypothèse non apparié pour le texte par région. Pour les proportions à dénominateur de référence (`numseq_*`, `searchability`, `diacritic_err`, `mufi_err`, `hcpr`, préservation, couvertures), elle est « **non définie** » : leur statistique ne compte aucune unité de l'hypothèse. Leur macro reste publié, avec la mention « insensible à l'invention par construction ». |
| Remarque `find_spec` (N5) | § 2.2, § 2.3 c | `importlib.util.find_spec("pkg.sub")` importe `pkg`. La résolution interroge donc les chercheurs de `sys.meta_path`, composant par composant, avec les `submodule_search_locations` du parent, sans l'importer. Vérifié : un `__init__` à effet de bord n'est pas exécuté, et `cinoc.evaluation.metric`, installé en éditable, est résolu sans importer `cinoc`. Limite écrite : un paquet qui modifie son `__path__` dans son `__init__` est résolu statiquement, et l'observation porte l'étiquette `resolution_statique`. |
| N1 (partiel) | § 2.1 d | levé par C1, C2, C3 |
| N6 (partiel) | § 2.4 a | levé par C4 |

**Prêts pour la tranche 1a** (tests rouges dès maintenant) : M1, M2, M3, M6, A4, A5, A8, A9, A10, A13. **A3** l'est aussi, B9 étant reformulé ci-dessus ; le correctif d'inférence attend la décision du mainteneur sur B9.

### Révision n° 3 (clôture de la revue, `REVUE_CONTRATS.md` § 6)

La revue lève 25 points de la révision n° 2, en lève 6 en partie (R4, R5, R11, P4, P10, P11) et relève 8 contradictions nouvelles. Toutes sont traitées ci-dessous et **aucune n'est rejetée**. Trois scripts ont été ajoutés :
- `revision2_verifications/n1_n2_procedure_unique.py` (N1, N2) ;
- `revision2_verifications/n8_wilcoxon_methode_explicite.py` (N8) ;
- les scripts `r2_*.py` de la revue, qui deviennent des tests des tranches indiquées.

| Point | Section | Ce qui change |
|---|---|---|
| **N1** niveau de l'inversion du bootstrap aux petits n (0,188 à n = 5, 0,117 à n = 10) | § 2.1 d, A3 | *(Remplacé en révision n° 4 par C1-C3 : PS retirée, n_min remplacé par le diagnostic de levier.)* Procédure fixée selon la famille et n, l'effectif des unités de rééchantillonnage (grappes si elles sont déclarées). **Dénominateur fixé par la référence** : changement de signe exact, valable à tout n (rejet sous H0 mesuré à 0,000 à n = 5 et 0,037 à n = 10). Quand 2^(1−n) > α, soit n ≤ 5, on publie « aucun rejet possible ; IC non borné ». **Dénominateur d'hypothèse** : si n ≥ n_min = 30, bootstrap apparié, avec un niveau mesuré de 0,050 à n = 30 et 0,061 à n = 50, mais 0,087 à n = 20. Si n < n_min, p par **permutation studentisée** (rejet mesuré entre 0,000 et 0,060 pour n de 5 à 30) et **pas d'IC** (« IC non estimable : n < 30 »). n_min et le jeu de scénarios de calibration sont l'arbitrage bloquant B9. Le BNL à 5 grappes et le Dresden à 10 pages sont donc dans le régime petit n. |
| **N2** p et IC contradictoires pour un même Δ | § 2.1 d, A3 | **Une seule procédure par Δ.** Changement de signe : l'IC est l'**inversion du même test**, {δ : p(δ) > α}, sous un modèle d'effet de taux constant. Mesuré sur 800 jeux : l'IC est toujours d'un seul tenant, et p et IC ne se contredisent jamais. Bootstrap : p et IC percentile (`quantile(method="inverted_cdf")`) viennent des **mêmes réplicats** ; aucune contradiction sur 6 000 jeux. Sous n_min, le seul objet publié est la p de permutation. |
| **N3** A4 faux | § 2.1 c, A4 | A4 dit désormais que le macro **ne voit pas** l'invention sur un document hors de D^M. Elle est visible au **micro** (insertions, fp) et dans une analyse dédiée, « invention hors référence » : par pipeline, nombre de documents sans référence à sortie non vide, et somme des unités inventées. |
| **N4** clé en deux temps incomplète | § 2.2, § 2.3 c ; I1, F3 | La validation porte sur toute la partie **calculée** de la définition (sources de la brique, fichiers de poids) **et** sur l'environnement. Chaque module est **résolu par son nom** dans le processus courant (`importlib.util.find_spec(nom).origin`), puis haché et comparé à l'empreinte enregistrée sous ce nom, et non sous un chemin. De même, les poids sont résolus par les réglages effectifs et les binaires par `shutil.which`. |
| **N5** définition dépendante des modules chargés | § 2.3 c, d ; I3, I5 | La définition hache les sources **sur disque** : tous les `.py` du paquet déclaré par la brique et de sa fermeture d'imports **statique** (graphe AST, résolu par `find_spec` sans exécuter), limitée à sa distribution. Pour le protocole, ce sont tous les `.py` sur disque de `cinoc.domain`, `cinoc.formats` et `cinoc.evaluation` (fermeture statique d'`evaluation`), plus les profils de normalisation. Le résultat ne dépend pas de ce que le processus a chargé. Ce qui est chargé ne sert qu'à l'**environnement**. |
| **N6** filiation trompée par un échange d'ids | § 2.4 a, M8 | Sous héritage, une paire par id n'existe que si la géométrie de l'hypothèse est **identique** à celle de la VT de même id (boîte et polygone égaux). L'id n'intervient alors **qu'en 4ᵉ critère**, entre des ex æquo exacts des trois premiers. L'optimum reste celui de l'énumération (M8). Dans le contre-exemple, les géométries échangées ne sont plus identiques, donc l'optimum géométrique s'applique et `region_cer` = 0. |
| **N7** linéarisation d'un groupe non ordonné | § 2.4 b, M7 | Convention écrite : la vue texte linéarise les membres d'un groupe non ordonné dans un **ordre géométrique canonique** (y0, x0 de leur boîte), jamais dans l'ordre de déclaration XML. Un membre sans géométrie est rangé en dernier par id, et l'observation porte l'étiquette `order_by_id`. Invariant : permuter les déclarations ne change ni la projection ni le CER. La vue texte pénalise donc la liberté que laisse la VT, ce que publie la fiche de la vue. La métrique insensible à l'ordre des lignes est `fca`, qui apparie les lignes par le hongrois. L'appariement des membres avant concaténation reste ouvert (O14). |
| **N8** `method="auto"` de scipy mal décrit | § 2.1 d, A5, B5 | Ce que fait réellement scipy 1.18.1 (`_wilcoxon.py`, l. 128-242) : n > 50, asymptotique ; n ≤ 50 sans zéro ni ex æquo, loi exacte ; zéros ou ex æquo et n ≤ 13, énumération des 2^n ; zéros ou ex æquo et 13 < n ≤ 50, asymptotique avec correction de continuité. **Contrat** : `method=PermutationMethod` explicite, énumération exacte si 2^n ≤ 2^16, sinon 99 999 échanges avec une graine déclarée. Vérifié égal à une énumération écrite à la main sur rangs moyens (n = 7 : 0,2656, alors que `method="exact"` donne 0,2188 ; n = 20 : 0,4366, alors que `auto` donne 0,4271). |
| R4 (partiel) | § 2.1 d | levé par N1 et N2 |
| R5 (partiel) | A4 | levé par N3 |
| R11 (partiel) | § 2.4 a | levé par N6 |
| P4 (partiel) | B5 | levé par N8 |
| P10 (partiel) | § 2.2 | levé par N4 |
| P11 (partiel) | § 2.3 c-d | levé par N5 |
| Remarque P17 (coût du ppcm) | § 2.4 a | Calcul exact par **composante connexe** du graphe d'admissibilité. Le dénominateur commun ne porte que sur les unions des paires **admissibles** de la composante. |
| Remarque : un seul emplacement pour les scripts | en-tête | `revision2_verifications/` seulement |

### Révision n° 2 (revue adverse `rapports/REVUE_CONTRATS.md`)

Les 23 contre-exemples de la revue se reproduisent sur la copie (`run_all.sh` : 23/23). **Aucun point n'est rejeté.**

Trois points sont acceptés avec une précision vérifiable :
- **P1** : le départage canonique est calculé et vérifié (`revision2_verifications/p1_departage_canonique.py`) ;
- **R4** : niveau mesuré par `revision2_verifications/r4_bootstrap_niveau.py`, complété en révision n° 3 par N1 et N2 ;
- **R10** : la résolution des bibliothèques d'un binaire est précisée.

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

### Révision n° 1 (rappel)

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
