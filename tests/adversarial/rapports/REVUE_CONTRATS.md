# Revue adverse de `CONTRATS.md` (révision n° 1)

Relecteur indépendant : je n'ai pas écrit le document et je ne le défends pas. Chaque contre-exemple vise une phrase précise du document. Il est minimal et exécutable, et il est comparé à une référence indépendante (`Fraction`, énumération exhaustive, scipy, jiwer, nervaluate, bagit) chaque fois qu'il s'agit d'un calcul.

| | |
|---|---|
| **Objet** | `tests/adversarial/CONTRATS.md`, révision n° 1 : K1 à K5, 36 invariants |
| **Code confronté** | copie figée `04a1c17b` (rien d'autre n'a été modifié que ce fichier) |
| **Scripts** | `/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/ce-review2/` (23 scripts `k*.py`, chacun affirme son contre-exemple) |
| **Rejouer** | `/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/ce-review2/run_all.sh` (sortie 0 = les 23 contre-exemples sont reproduits ; une sortie par script, `out_*.txt`) |
| **Environnement** | `ce-venv` (cinoc éditable, numpy 2.4.6, scipy 1.18.1, rapidfuzz 3.14.6, jiwer 4.0.0) ; `review-venv` (avec `bagit` et `nervaluate`) |

Verdicts :
- **faux** : la phrase est fausse ou contradictoire sur un cas ;
- **à préciser** : la phrase admet deux lectures, ou laisse un cas sans règle, et une lecture plausible casse un invariant ;
- **tient** : j'ai cherché sans trouver de contre-exemple.

## Comptes

| | faux | à préciser | tient | total |
|---|---|---|---|---|
| Invariants (§ 3) | **10** (M1, M3, M4, M5, M6, M8, A3, A4, A7, I1) | **10** (A2, A5, A6, A8, I3, I5, I6, F3, F5, F7) | **16** | 36 |
| Clauses de contrat (§ 2 et § 6) | **11** (R1 à R11) | **20** (P1 à P20) | voir § 4 | — |

---

## 1. Points faux

| # | Phrase visée | Contre-exemple (minimal) | Script | Correction minimale |
|---|---|---|---|---|
| **R1** | § 2.1 a : « combinaison (**associative**, commutative, avec un élément neutre) », par `math.fsum`, pour les familles à somme réelle (ECE/MCE Σ conf_b, Moyenne de réels). **M6** : « combiner les histogrammes par document = calculer sur les jetons poolés » | Confiances [0,1 ; 0,2] et [0,3] : `fsum` du lot complet = 0,6 ; `fsum` des sommes par document = 0,6000000000000001. (a+b)+c ≠ a+(b+c). Les deux ECE diffèrent au dernier bit. `fsum` n'est exact que sur la liste **complète** de ses termes. | `k1_fsum_non_associatif.py` | Statistiques réelles en entiers (confiance quantifiée, durées en ns, coûts en micro-unités) ou en partiels exacts (`Fraction`, partiels de Shewchuk). `fsum` seulement sur la liste plate des termes, à la finalisation. |
| **R2** | Table « Texte par région » : S = (éditions sur paires bijectives **+ texte non apparié de l'hypothèse**, car. réf.). **M4** idem | VT : 2 régions de 10 car. P ne rend que la 1ʳᵉ, parfaitement : **0,000** sous la formule. Q rend les deux, avec 1 faute : 0,050. Perdre une région entière note mieux qu'une coquille. Le code actuel (`metrics/layout.py:103-108`) compte la région manquante en suppressions et donne 0,500 : la révision **régresse**. | `k1_region_cer_reference_non_appariee.py` | Ajouter au numérateur « + texte des régions de référence non appariées (suppressions) ». |
| **R3** | Table « Ordre de lecture » : S = (discordantes, « **paires ordonnées par la référence** ») ; **M5** ; § 2.4 « respecte `reading_order` imbriqué » | PAGE `UnorderedGroup{m1, m2}`, hypothèse (m2, m1). Le parseur voit `ordered=False`, mais `ReadingOrderGroup.flatten()` (`formats/pagexml/types.py:44`) puis `LayoutPage.reading_order`, liste plate (`domain/layout.py:111`), donnent ('m1','m2'). Résultat : `kendall_distance` = **1,0**, au lieu de « aucune paire ordonnée ». La statistique annoncée n'est pas calculable sur le type existant. | `k1_tau_groupe_non_ordonne.py` | Porter l'ordre partiel (groupes ordonnés ou non) dans `LayoutPage`. Sinon, écrire « toutes les paires de l'ordre aplati » et retirer « imbriqué ». |
| **R4** | § 2.1 d, ligne Micro : « p : permutation appariée (échange A/B par document) ». **A3** « égaux à scipy » | F1 NER, 2 entités de référence par document. A prédit toujours (tp 2, fp 4, fn 0), soit F1 = 0,5. B est parfait (2,0,0) avec probabilité 1/3 et muet (0,0,2) sinon, soit R_B = 0,5. Donc R_A = R_B en population. Taux de rejet à α = 0,05 : **0,17 (n = 10), 0,30 (n = 30), 0,31 (n = 100)**, sans décroître avec n. Témoin CER (même n_réf des deux côtés) : 0,044. L'échange teste l'échangeabilité de (S_A,d, S_B,d), pas R_A = R_B, dès que les dénominateurs diffèrent entre pipelines : F1/P/R, `bow_*`, MER/cMER (n_réf + I), `unanchored_trigrams` (n = trigrammes produits). | `k1_permutation_ratio_niveau.py`, `k1_permutation_cer_temoin.py` | Réserver la permutation aux familles dont le dénominateur est fixé par la référence. Pour les autres : IC par bootstrap apparié et p par inversion de l'IC, ou permutation studentisée. Nommer H0. |
| **R5** | § 2.1 c : « D^M_P = {d : scalaire défini} », « D^M_AB = D^M_A ∩ D^M_B ». **A4**, **A6** | d1 : A = B = (5,0,0). d2 n'a aucune entité de référence : A invente 5 entités (F1 = 0, donc défini), B se tait ((0,0,0), indéfini). D^M_AB = {d1}, d'où **Δ macro = 0**. Pourtant B domine A sur chaque document (micro : 1,0 contre 0,667). Le support macro dépend du pipeline pour toute famille dont le dénominateur contient l'hypothèse. L'intersection retire justement le document où B a raison. Même chose pour MER sur référence vide. | `k2_support_macro_depend_du_pipeline.py` | Fixer D^M par la **référence** (n_réf > 0 ou tp+fn > 0), le même pour tous les pipelines. Un document sans référence ne va qu'au micro. |
| **R6** | § 2.1 b : « execution : ok \| truncated \| partial — **sans effet sur les supports** ». § 2.1 e « Rien n'est imputé par défaut ». **A7** | Fan-out sur 2 pages de 2 régions. P perd 1 région sur p2 : `partial`, la région est absente du texte (`fanout.py:230-235`), CER micro **0,262**. Q perd les 2 régions sur p2 : `failed`, exclue, CER micro **0,000**, couverture 1/2. Une région en échec est imputée « vide » en silence. Plus d'échecs donnent un meilleur agrégat conditionnel. Même mécanisme pour `truncated`. | `k2_partial_impute_en_silence.py` | La part manquante d'un `partial` ou `truncated` porte un motif d'axe 3 qui exclut l'observation par défaut. Elle n'est notée que sous la sensibilité `empty_page`. |
| **R7** | **M1** : « égal à jiwer … pages à référence vide comprises » **et** « corpus entièrement vide : CER/WER micro indéfinis » | jiwer 4.0.0 : `cer([""], ["xyz"]) = 3`, `wer = 1`, `cer([""], [""]) = 0`. L'oracle désigné rend un nombre là où l'invariant exige « indéfini ». | `k1_editops_egalites.py` | « Égal à jiwer quand Σ n_réf > 0 ». |
| **R8** | **M3** : « Vérif. : O nervaluate (NER) » | `ner_f1` apparie par IoU d'empan ≥ 0,5 (`evaluation/ner.py:48`, `:190`, `:229`). La VT est [0,10) PER, la prédiction [0,30) PER (IoU 1/3). Cinoc rend (tp, fp, fn) = (0, 1, 1). nervaluate rend `ent_type` correct = 1 (F1 = 1), `partial` partiel (F1 = 0,5), `strict` et `exact` 0. Aucun schéma nervaluate ne calcule la grandeur de `ner_f1` ni celle de `ner_f1_exact`. | `k1_ner_oracle_nervaluate.py` | Prendre comme oracle une énumération sur l'IoU d'empan et retirer nervaluate de M3 (ou le garder seulement pour une métrique « bornes exactes », qui n'existe pas). |
| **R9** | § 2.3 c : executed_files = modules chargés « pour construire puis exécuter le module (**différence de `sys.modules`**) ». § 2.3 c « une réutilisation exige que tous les fichiers enregistrés se re-hachent ». **I1** | L'étape A importe `shared_norm`. L'étape B l'utilise aussi, avec un import paresseux. Le record de B ne contient pas `shared_norm` (déjà chargé), et il est **vide** au 2ᵉ document (tout est déjà chargé). Après modification de `shared_norm`, la vérification des fichiers enregistrés de B passe : relecture périmée. L'ensemble enregistré dépend de l'historique du processus (ordre des étapes, des documents). | `k4_fichiers_executes_sys_modules.py` | Instantané de **tous** les modules hors stdlib chargés dans le processus à la fin de l'étape (sur-approximation sûre), mémoïsé par run, plus les bibliothèques partagées chargées. |
| **R10** | § 2.3 c : binaries = « {exécutable résolu à l'appel : sha256} ». **I1** « modifier un … binaire … change l'identité » | Ici, `/usr/bin/tesseract` fait **39 320 octets** : une coquille. Le moteur est `libtesseract.so.5.0.3` (3,2 Mo), plus `liblept.so.5.0.4`, dans des paquets distincts. Une mise à jour du moteur laisse l'empreinte inchangée. Le code actuel trace au moins `tesseract --version` (5.3.4, la version de la bibliothèque) ; le contrat, qui tient les versions pour des « étiquettes », le remplace par une preuve plus faible. | `k4_binaire_bibliotheque_partagee.py` | Hacher aussi les bibliothèques partagées chargées par le binaire (`ldd`, `/proc/<pid>/maps`), ou garder la sortie complète de `--version` en étiquette. |
| **R11** | § 2.4 étape 1 : « **Filiation démontrée** … chaque étape déclarée `preserves_region_ids` … Alors les ids **sont** l'appariement ». **M8** « ids conservés sous filiation démontrée » | (a) La filiation n'est pas démontrée mais **déclarée** par le module (code tiers in-process), le défaut même que K4 reproche à l'existant. Un module qui garde les ids et change le repère (redressement, recadrage) donne IoU = 0,0 sur les deux paires, avec tp = 2 et `region_detection` = 1,0. (b) Même honnête, sous filiation l'hypothèse hérite des régions de la VT : la détection vaut 1 par construction, pour un pipeline qui n'a rien segmenté. | `k5_filiation_declaree.py` | Sous filiation, les ids ne font que **départager** des paires admissibles (l'IoU reste exigé). `region_detection` est `not_applicable` quand les régions sont héritées de la VT. |

---

## 2. Points à préciser

| # | Phrase visée | Contre-exemple | Script | Correction minimale |
|---|---|---|---|---|
| **P1** | Tables « Taux d'édition » et « MER » : S = (S, D, I) par `rapidfuzz.editops` | « ab » contre « ba » admet deux alignements optimaux, (S,D,I) = (2,0,0) et (0,1,1). Le CER vaut 1 dans les deux cas. En revanche `ins_rate` vaut 0 ou 0,5, et MER vaut 1 ou 0,667. Seul S+D+I est intrinsèque ; I et D dépendent du départage (rapidfuzz choisit (0,1,1)). | `k1_editops_egalites.py` | Écrire que le départage de rapidfuzz fait partie de la définition, sa version étant dans `ProtocolIdentity`, ou poser une règle canonique. |
| **P2** | § 2.1 a « on somme les lignes tirées, puis on finalise » ; § 2.1 b (une page blanche est au support micro) ; A3 | 3 documents, dont 2 blancs. Un réplicat a Σ n_réf = 0 avec une probabilité de 0,30. scipy rend alors l'IC [−0,1 ; **inf**] en percentile et **NaN** en BCa (`DegenerateDataWarning`). Pour la fixture T1 reformulée (12 documents, dont 6 blancs), la probabilité d'au moins un réplicat dégénéré sur 9 999 est de 0,91. | `k1_bootstrap_denominateur_nul.py` | Règle déclarée : le réplicat est rejeté et compté, ou l'IC est déclaré « non estimable » au-delà d'un taux. Méthode (percentile ou BCa) nommée. |
| **P3** | Table « Quantiles » : « les quantiles sont la seule famille qui rééchantillonne des **données élémentaires** » | 8 pages de 60 lignes, avec un effet de page. Couverture de l'IC à 95 % de la médiane des CER par ligne : **0,25** en tirant des lignes, **0,92** en tirant des documents. | `k1_quantiles_grappes.py` | La statistique d'un document est le multi-ensemble de ses lignes, et l'on tire des **documents**. |
| **P4** | § 2.1 d « Analyses de rangs … telles qu'aujourd'hui » ; A5 ; A9 « jamais fusionnés » | (1) 3 différences nulles sur 8. Selon `zero_method` et `method`, p varie de 0,109 à 0,313. (2) Avec deux pipelines identiques gardés : Wilcoxon p = 1, Friedman **NaN**. (3) Friedman avec 2 pipelines : `ValueError`. (4) Des ex æquo exacts (|Δ| = 1/10) sont cassés par l'arrondi flottant : p = 0,588 sur les flottants, 0,655 sur les valeurs exactes. | `k1_rangs_ex_aequo.py` | Fixer `zero_method` et `method`. Calculer les rangs sur des scalaires exacts (`Fraction`). Publier « non calculé » si k < 3 ou si la variance est nulle. |
| **P5** | **A8** « en singletons, l'IC égale l'IC par document » | Graine fixe. Les grappes `c1…c10` se trient c1, c10, c2…, les documents d01…d10 autrement : les IC valent [0,0301 ; 0,0691] et [0,0290 ; 0,0701]. L'égalité n'est vraie qu'à l'erreur de Monte-Carlo près. | `k1_grappes_singletons_ordre.py` | Ordonner les grappes par le plus petit id de document qu'elles contiennent. |
| **P6** | § 2.1 d « Grappes déclarées … mêmes appels » ; § 2.2 « Répétitions » | Ni Wilcoxon ni Friedman ne tiennent compte des grappes. Le contrat ne dit pas comment les répétitions entrent dans l'inférence. Les traiter en documents indépendants reproduit le défaut de P3. | (même mécanisme que P3) | Une répétition n'est jamais une unité d'inférence : grappe = document (ou moyenne par document), y compris pour les rangs, ou « non publié sous grappes ». |
| **P7** | § 2.1 b, axe 1 (`applicable \| no_ground_truth \| not_in_view`) ; § 6 n° 12 (N1) ; **M4** « une région de référence sans texte, appariée à du texte, contribue au numérateur » | Une VT vide parce que la page **n'a pas été transcrite** (fichier placeholder, VT de segmentation partielle) et une page **blanche** ont la même représentation. Toute lecture correcte compte alors en hallucinations (M1 et M4). N1 exige « niveau absent → `not_applicable` », mais l'énumération n'a pas de valeur pour ce cas. | (arithmétique de `k1_region_cer…`) | Ajouter `level_absent` / `not_transcribed`, déclaré par l'importeur, distinct d'une référence vide. |
| **P8** | **A6** « deux pipelines ne s'ordonnent que sur leur support apparié » ; § 6 n° 14 | Chacun sur son propre support apparié : B bat A, C bat B, A bat C (un cycle). Le support global {d4} donne trois ex æquo. | `k2_ordres_apparies_intransitifs.py` | Écrire que les ordres appariés ne composent pas un classement ; seul le support global trie. |
| **P9** | § 2.2 `step_key` ; I1 « les réglages opérationnels n'y entrent pas » ; § 1.3 saknussemm `partial` | Le contrat ne dit pas quels records sont réutilisables. Un record `partial` produit avec un délai de 5 s a la même clé qu'avec 60 s : `--resume` relit la sortie dégradée qu'on cherchait à corriger. | `k3_reprise_record_non_ok.py` | Seul un record `ok` est réutilisable ; ou les réglages opérationnels entrent dans la clé des records non `ok`. |
| **P10** | § 2.2 `step_key(k) = H(identité de l'étape k, …, unit_inputs **lus**, …)` avec identité ⊃ `executed_files` (§ 2.3 c) | Les fichiers exécutés et les entrées « lues » ne sont connus **qu'après** l'exécution : la clé de recherche ne peut pas les contenir. Le texte suggère un mécanisme en deux phases (« une réutilisation exige … ») sans le poser. | `k4_fichiers_executes_sys_modules.py` (l'ensemble n'existe qu'après exécution) | Clé de recherche = partie déclarée + entrées résolues. Fichiers exécutés = prédicat de validité du record trouvé. |
| **P11** | § 2.3 d `ProtocolIdentity` ⊃ « executed_files du code d'évaluation » ; **I5** | Le calcul d'un CER charge 103 extensions C dont le **nom** porte la plateforme (`…cpython-313-x86_64-linux-gnu.so`). Pour un tiers sur macOS, sous Windows ou avec un autre Python, l'identité diffère toujours : la « reproduction sous protocole identique » est inaccessible hors de la machine d'origine. | `k4_protocole_depend_de_la_plateforme.py` | Séparer l'identité de **définition** (sources `evaluation`/`formats` de Cinoc, profils, Unicode) de celle d'**environnement**, publiée à part. |
| **P12** | § 2.3 d `ProtocolIdentity` ⊃ « empreintes des VT » ; ObservationId ⊃ VT du document ; **I3** | Corriger la VT de d2 change l'`ObservationId` de d1, qui est inchangé. Re-noter d1 seul ne reproduit jamais son identité. | `k4_observation_id_depend_du_corpus.py` | Retirer de `ProtocolIdentity` les VT du corpus (celle du document est déjà dans l'ObservationId). Identité de corpus séparée. |
| **P13** | § 2.3 e « Archive … spec.json, run_result.json, observations ; lecture = `bagit.Bag.validate()` + refus de tout lien (lstat) » ; § 2.3 b « 0444 » ; **I6** | Si les fichiers sont à la racine, `bag.save()` liste bien les tags existants, et leur altération est **refusée**. En revanche, l'**ajout** de `observations.json` ou de `overrides/spec.json` non listés passe `validate(fast=False)`, et l'empreinte racine ne change pas. `lstat` ne voit pas un lien dur (`S_ISLNK=False`, `st_nlink=2`). Sous uid 0, une écriture en place sur un blob 0444 lié réussit et altère `data/`, ce qui sera détecté à la validation. | `k4_bagit_fichiers_hors_manifeste.py` | Tout sous `data/`, ou refus de tout fichier non listé dans un manifeste. « Lien » = symbolique, ou `st_nlink > 1` hors option. Ne pas présenter 0444 comme une protection. |
| **P14** | § 2.2 « fichier temporaire, `fsync`, `os.replace` » ; **F5** « laisse k records valides » | Argument (non scriptable sans coupure d'alimentation) : sans `fsync` du répertoire après `os.replace`, le renommage peut être perdu. Rien n'impose que les blobs référencés soient durables avant le record. Un record peut alors pointer un blob partiel, que `read_verified` refuse. | — | Ordre : blobs `fsync` → record `fsync` → `os.replace` → `fsync` du répertoire. |
| **P15** | § 2.3 c « weights : révision RÉSOLUE (hash de commit du Hub) » | Argument : le commit identifie le dépôt distant, pas les octets chargés depuis le cache local, qui est modifiable. C'est la critique que le document adresse à `RECORD`. | — | Hacher les fichiers de poids chargés (le cache HF nomme déjà ses blobs LFS par sha256). |
| **P16** | § 2.4 étape 2 « tri … puis **texte** … départage les ex æquo résiduels » ; « les mêmes paires bijectives servent `region_cer` » | Boîte dupliquée (VLM qui répète une région), VT « Zurich », hypothèses « Aaaaaa » et « Zurich » sur la même boîte. L'ordre alphabétique retient « Aaaaaa » et donne `region_cer` = **2,0**. L'autre choix, de même objectif, donne 1,0. Il suffit de renommer le texte fautif « Zzzzzz » pour que l'appariement bascule. | `k5_objectif_lexicographique.py` (1) | 3ᵉ critère lexicographique : Σ distance d'édition des textes appariés, puis l'ordre canonique. |
| **P17** | § 2.4 « IoU ≥ θ ou > θ » ; § 6 n° 4 « > 0,5 strict » | Les boîtes sont des pixels entiers rendus **relatifs** (`metrics/layout.py:160`). Pour une IoU exacte de 1/2 : page de 3 px → 0,49999999999999994 ; page de 7 px → 0,5000000000000001. Le choix strict ou inclusif est tranché par l'arrondi. | `k5_seuil_iou_flottant.py` | Admissibilité en entiers : 2·\|∩\| > \|∪\| sur les pixels. |
| **P18** | § 6 n° 4 « strict (unicité de l'appariement plan, Kirillov et al. 2019) » ; § 2.4 étape 3 (fusions) | L'unicité exige des segments **disjoints des deux côtés**. Avec des régions de VT qui se recouvrent : IoU(r1,h1) = 0,95, IoU(r1,h2) = 0,60, IoU(r2,h1) = 0,63. L'optimum (accord de l'oracle exhaustif) apparie r1↔h2 et r2↔h1, et h1 est publié comme **fusion** (IoGT 0,95 et 1,0). | `k5_objectif_lexicographique.py` (2) | Retirer la justification. Calculer les relations entre régions de VT disjointes, ou exclure les recouvrements de la VT. |
| **P19** | § 2.4 « les mêmes paires bijectives servent … `line_identity_*` » ; « aucun identifiant n'intervient sans filiation » | Les paires bijectives sont des paires de **régions** ; `line_identity_cer` et `line_identity_coverage` apparient des **lignes** par id (`metrics/layout.py:304-370`). Sans filiation, aucun id n'est permis, et ces deux métriques n'ont plus de définition. | — | `line_identity_*` applicables seulement sous filiation, `not_applicable` sinon. |
| **P20** | § 6 n° 4 (régions : > 0,5 strict) contre `ner_f1` (IoU ≥ 0,5 inclusif, `evaluation/ner.py:48,190`) | Deux conventions de seuil coexistent pour la même notion d'admissibilité. | — | Une seule convention, écrite dans les deux fiches. |

---

## 3. Tableau par invariant

| Inv. | Verdict | Renvoi | Remarque |
|---|---|---|---|
| M1 | **faux** | R7, P1, P7 | La propriété « page vide ajoute \|h\| » tient ; l'égalité à jiwer ne tient pas sur le corpus tout vide. |
| M2 | tient | | Le plancher après combinaison est cohérent avec la finalisation unique. |
| M3 | **faux** | R8 | La propriété « +1 fp sans partenaire admissible » tient sous la cardinalité maximale ; c'est l'oracle qui ne mesure pas la même grandeur. |
| M4 | **faux** | R2, P7 | |
| M5 | **faux** | R3 | Hors groupes non ordonnés, l'égalité à `(1 − τ)/2` de scipy tient sans ex æquo. |
| M6 | **faux** | R1 | En arithmétique exacte, l'histogramme (n_b, Σ justes, Σ conf) suffit (§ 4). |
| M7 | tient | | |
| M8 | **faux** | R11, P16, P17, P18 | L'invariance par permutation et par renommage sans filiation tient (§ 4). |
| A1 | tient | (R6) | Par construction. L'agrégat conditionnel hérite toutefois de l'imputation de R6. |
| A2 | à préciser | P7 | |
| A3 | **faux** | R4, P2 | Tient pour la famille « taux d'édition » (témoin). |
| A4 | **faux** | R5 | |
| A5 | à préciser | P4, P6 | |
| A6 | à préciser | P8, R5 | |
| A7 | **faux** | R6 | |
| A8 | à préciser | P5, P6 | |
| A9 | tient | | § 4 |
| A10 | tient | | Le tri par id rend le tirage indépendant de l'ordre de la spec (§ 4). |
| A11 | tient | | |
| A12 | tient | | |
| I1 | **faux** | R9, R10 | |
| I2 | tient | | Pour IIIF, l'empreinte des octets servis peut varier d'une requête à l'autre (réencodage) : à surveiller avec H4. |
| I3 | à préciser | P12, P11 | |
| I4 | tient | | |
| I5 | à préciser | P11 | |
| I6 | à préciser | P13 | |
| I7 | tient | | |
| F1 | tient | | |
| F2 | tient | | |
| F3 | à préciser | P9, P10 | La sémantique « octets consommés » est juste. |
| F4 | tient | | La recopie `repetition-1 → 2` n'est pas trouvée, puisque `repetition_id` est dans la clé. |
| F5 | à préciser | P14 | |
| F6 | tient | | |
| F7 | à préciser | P13 | La détection tient (témoin `data/` refusé) ; la « protection » 0444, non. |
| F8 | tient | | |
| F9 | tient | | |

---

## 4. Ce qui tient

| Affirmation | Pourquoi elle résiste |
|---|---|
| **Famille « taux d'édition »** : S+D+I additif, micro = finalize(ΣS), Δ micro par échange de signe | Le même document donne le même n_réf aux deux pipelines, donc Δ = Σ(E_A − E_B)/Σn est linéaire. Niveau mesuré : 0,044 pour un nominal de 0,05, avec des lois différentes (`k1_permutation_cer_temoin.py`). Le cas Simpson (p = 1) se vérifie à la main. |
| **ECE/MCE par histogramme** à classes fixées | ECE = (1/N) Σ_b \|Σ justes_b − Σ conf_b\| et MCE = max sur les classes non vides : l'histogramme est exactement suffisant. Seule la représentation flottante pèche (R1). Les classes fixées par le protocole sont cohérentes avec `calibration.py:83` (`min(int(c·10), 9)`). |
| **Poids (n+1)·[adm] + IoU·[adm]** pour l'ordre lexicographique | k+1 paires admissibles pèsent au moins (k+1)(n+1), plus que tout k-appariement (au plus k(n+1)+k ≤ k(n+1)+n). L'oracle exhaustif confirme le résultat de `linear_sum_assignment` (`k5_objectif_lexicographique.py` (2)). |
| **M8** : invariance par permutation des régions et par renommage des ids sans filiation | Le tri canonique précède le calcul et les ids n'y entrent pas : le résultat est une fonction de l'ensemble. |
| **A9** : famille de Holm a priori, test non calculable gardé à p = 1 | Holm contrôle le FWER sous toute dépendance. Une entrée à p = 1 ne peut qu'augmenter m, donc rendre la correction plus conservatrice, jamais l'invalider. Ajouter un pipeline change la famille par défaut (§ 6 n° 13) et donc les p corrigées des paires existantes ; c'est cohérent avec « défini par la spec ». |
| **A10** : tri par id avant tout tirage | Avec une graine fixée, le tirage ne dépend que de l'ordre des lignes, désormais canonique. |
| **Supports** (§ 2.1 c) | D^M ⊆ D^μ ⊆ attendus. Apparié ⊆ conditionnel. Ajouter un pipeline ne change ni les supports conditionnels ni les supports appariés des autres. La contradiction ex-S6/S9 est bien levée. Le défaut de R5 tient à la **définition** de D^M, pas à la structure en trois supports. |
| **§ 2.3 a** : intégrité contre authenticité | Juste. Un fichier de tag listé altéré et un `data/` altéré sont refusés par `bagit` (témoins de `k4_bagit…`). Un faussaire peut réécrire les manifestes, et l'ancre externe est la bonne réponse. |
| **K3** : clé par octets consommés, `repetition_id` dans la clé, conservation de l'amont, persistance par étape | Aucun contre-exemple hors P9, P10 et P14. Les invariants F1, F2, F4, F6, A11 et A12 tiennent. |
| **M2, M7, F8, F9, I2, I4, I7** | Pas de contre-exemple. |
| **Arithmétique du document** | V 9+8+13+9+12 = 51 ; D 10+6+5+9+5+4 = 39 ; 8+12+7+9 = 36. |
| **Références au code** | Vérifiées exactes sur `04a1c17b` : `evaluation/metric.py:22` ; `metrics/text.py:113-116` (`_error_rate`) ; `runner.py:409` (`worst`) ; `inference.py:346` (famille = tests calculés) ; `app/resume.py:130` (`unit_key`) ; `pipeline/fingerprint.py:72` ; `domain/documents.py:22-32` (pas d'empreinte) ; `domain/run.py:90-91` ; `calibration.py:126` (multi-ensemble) ; `metrics/flexible.py:50` (`linear_sum_assignment`) ; `pipeline/fanout.py:230-235` (région ignorée) ; `analysis.py:960` (`support ≥ 1`) ; `pipeline/types.py:96-112`. Les seuls écarts avec l'existant sont R2 (la formule régresse sur le code), R3 (ordre plat), R10 (preuve plus faible que l'étiquette actuelle) et P20. |

---

## 5. Avis

**Les contradictions se résolvent en corrigeant `CONTRATS.md`. Aucun des cinq contrats n'est à repenser dans son principe** :
- statistique suffisante et finalisation unique (K1) ;
- axes et trois supports (K2) ;
- record par étape et clé sur les octets consommés (K3) ;
- identité calculée, avec une archive distincte du cache (K4) ;
- appariement global (K5).

Une tranche peut s'ouvrir sur chacun.

La plupart des corrections tiennent en une phrase : R2, R3, R5, R6, R7, R8, R11 et P1 à P20. Deux points demandent toutefois de **re-spécifier un mécanisme**, et pas seulement une formulation. Ils sont à corriger avant les tranches 1a et 3 :

1. **R4 (inférence du Δ micro)**. La permutation appariée n'est un test de « R_A = R_B » que pour les familles à dénominateur fixé par la référence. Pour F1/P/R, `bow`, MER/cMER et `unanchored_trigrams`, elle rejette 31 % du temps à α = 0,05, sans amélioration quand n croît. Le tableau du § 2.1 d doit donc choisir l'inférence **par famille**, comme le § 2.1 a le fait déjà pour la statistique.
2. **R9, R10, P10 et P11 (identité par fichiers exécutés)**. Le principe est bon ; le calcul annoncé (différence de `sys.modules`, exécutable seul) ne peut pas établir I1. Il faut :
   - un instantané du processus, bibliothèques partagées comprises ;
   - une clé en deux temps (recherche sur le déclaré, validation sur les fichiers) ;
   - pour I5, une séparation entre l'identité de la définition et celle de l'environnement.

   Sans cela, I5 n'est pas atteignable par un tiers.

Le point de méthode le plus transversal est R5 : un support macro qui dépend du dénominateur de l'hypothèse rend le Δ macro aveugle aux hallucinations. Le corriger, en fixant D^M par la référence, renforce K2 sans le changer.

---

## 6. Clôture de la révision n° 2

Objet : `CONTRATS.md` révisé une deuxième fois par son auteur. La table « Révision n° 2 » répond aux 31 points ; aucun n'est rejeté. Pour chacun, j'ai :
- rejoué mon contre-exemple contre la nouvelle spécification quand c'était mécanisable (scripts `r2_*.py`) ;
- sinon, relu la clause ;
- cherché une contradiction nouvelle introduite par la correction.

Les scripts sont dans `/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/ce-review2/`. `run_all.sh` rejoue les 23 + 10 scripts (33/33 reproduits). J'ai aussi exécuté le script P1 de l'auteur (« 3000 cas ») : il passe.

Les scripts `k*.py` de la revue reproduisent toujours, ce qui est attendu : ils visent le code, qui n'a pas changé. Les scripts `r2_*.py` visent la spécification révisée.

**Comptes** : **25 levés**, **6 partiellement** (R4, R5, R11, P4, P10, P11), **0 non levé**. **8 contradictions nouvelles** (N1 à N8), toutes corrigibles par une clause.

### 6.1 Point par point

| Point | Verdict | Une ligne |
|---|---|---|
| R1 | **levé** | `Fraction` : le contre-exemple donne poolé == par document. La partition en 7 et l'ordre mélangé donnent une égalité exacte. Coût : 0,36 s pour 200 000 jetons, dénominateur de 52 bits (`r2_r1_fraction.py`). |
| R2 | **levé** | Le texte de référence non apparié est au numérateur (§ 2.1 a, M4). |
| R3 | **levé** | Ordre partiel en domain ; le τ ne compte que les paires ordonnées. Voir N7 pour la projection texte. |
| R4 | **partiellement** | Le niveau est bon à n ≥ 30. À n = 5 et 10 (le régime des 5 grappes BNL et des 10 pages Dresden), l'inversion du bootstrap rejette à **0,188 et 0,117**, au-delà de la borne d'A3 (0,071). Voir N1 et N2. |
| R5 | **partiellement** | Le support est désormais symétrique. Mais A4 affirme « il voit l'hallucination d'un document sans référence », ce qui est faux : ce document a tp + fn = 0 et sort de D^M par définition, donc Δ macro = 0 (N3). |
| R6 | **levé** | `partial_output` et `truncated_output` à l'axe 3, exclus par défaut : P et Q sont tous deux exclus, la non-monotonie disparaît. |
| R7 | **levé** | Écart à jiwer écrit (« S+D+I quand Σ n_réf > 0 »). |
| R8 | **levé** | L'oracle est l'énumération ; NER passe sous l'appariement unique. |
| R9 | **levé** | Instantané du processus entier, indépendant de l'historique, pour l'**environnement**. Voir N5 pour la **définition**. |
| R10 | **levé** | Bibliothèques du binaire (`ld.so --list`) et `--version` ; la limite `dlopen` est écrite (O4). |
| R11 | **partiellement** | L'admissibilité exigée lève mon contre-exemple (repère changé, IoU 0). Elle ne prouve pas l'homologie quand des régions de VT se recouvrent : un échange d'ids passe (N6). |
| P1 | **levé** | max S, vérifié (DP, 3000 cas). MER s'écarte de jiwer sur les ex æquo (« a b »/« b a » : 1,0 contre 0,667), comme le document l'écrit. Les tests de parité MER/cMER existants n'utilisent que des paires non ambiguës et restent verts (`r2_p1_mer_parite_jiwer.py`). |
| P2 | **levé** | Réplicats écartés et comptés ; ε = 1 % ; percentile (BCa est indéfini avec des réplicats infinis, c'est exact). Pour T1, la probabilité qu'un réplicat soit dégénéré est de 2,4·10⁻⁴, très en dessous de ε. |
| P3 | **levé** | On tire des documents (A13). |
| P4 | **partiellement** | `Fraction`, k ≥ 3 et « non calculé » sont réglés. Mais B5 décrit mal `method="auto"` de scipy 1.18.1 en présence d'ex æquo (N8). |
| P5 | **levé** | Grappes triées par leur plus petit id : singletons = documents, bit à bit. |
| P6 | **levé** | Une répétition n'est jamais une unité d'inférence ; rangs sur moyennes par grappe. |
| P7 | **levé** | `not_transcribed` est déclaré par l'importeur, hors des attendus. |
| P8 | **levé** | Seul le support global trie. |
| P9 | **levé** | `partial` et `failed` sont retentés. `truncated` n'est réutilisé que parce que sa cause, `stop_reason="length"` (`adapters/llm/_base.py:543`), dépend de `max_tokens`, qui est dans la clé. |
| P10 | **partiellement** | La clé en deux temps est posée, mais recherche et validation divergent sans détection dans deux cas (N4). |
| P11 | **partiellement** | La séparation définition / environnement est faite. Mais la définition hache les sources « **chargées** », ce qui réintroduit la dépendance à l'historique (N5). |
| P12 | **levé** | L'`ObservationId` ne contient que la VT de son document ; `CorpusIdentity` est séparée. |
| P13 | **levé** | Tout est sous `data/` ; tout fichier non listé est refusé ; `st_nlink > 1` est refusé hors option ; 0444 n'est plus présenté comme une protection. |
| P14 | **levé** | Ordre de durabilité imposé ; F5 est testé par panne simulée. |
| P15 | **levé** | Les poids chargés sont hachés dans la définition. Pour leur rôle dans la réutilisation, voir N4 (a). |
| P16 | **levé** | 3ᵉ critère (Σ distance d'édition) : l'exemple « Zurich » retient la bonne hypothèse. |
| P17 | **levé** | Admissibilité exacte en entiers. Remarque de coût (`r2_p17_poids_entier_cout.py`) : si le ppcm est pris sur **toutes** les unions d'une page, il atteint 14 588 bits à n = 40 et 63 334 bits à n = 100, soit environ 2 s × la constante du hongrois par page. Il faut le restreindre aux paires admissibles, ou départager par passes ou par composantes connexes. |
| P18 | **levé** | Justification retirée ; `ref_overlap` est `not_applicable` et compté. |
| P19 | **levé** | `line_identity_*` seulement sous filiation des lignes. |
| P20 | **levé** | Une seule règle (inclusive, O2) pour les boîtes et les empans. |

### 6.2 Contradictions nouvelles

| # | Phrase visée | Contre-exemple minimal | Script | Correction minimale |
|---|---|---|---|---|
| **N1** | § 2.1 d « inversion du bootstrap apparié » ; A3 « taux de rejet ≤ α + 3 erreurs Monte-Carlo pour chaque famille » | Scénario F1 de la revue (R_A = R_B = 0,5), 1000 simulations. Taux de rejet : **0,188 (n = 5)**, **0,117 (n = 10)**, 0,036 (n = 30). La borne est 0,071. L'auteur n'a mesuré que n = 30 et 100. | `r2_r4_inversion_bootstrap.py` (1) | En dessous d'un n minimal à chiffrer (unités de rééchantillonnage, donc grappes), p « non estimable » ; ou permutation studentisée, dont l'auteur a mesuré 0,067 et 0,063, à mesurer aussi à n = 5 et 10. |
| **N2** | § 2.1 d, ligne « Taux d'édition » : p par changement de signe, IC par bootstrap apparié | n = 10, B un peu pire que A. Dans **50 %** des jeux de données, la p et l'IC se contredisent. Exemple : 5 différences non nulles, toutes négatives, donnent p = 2·2⁻⁵ = 0,0625, alors que l'IC à 95 % [−19 ; −3] exclut 0. | `r2_r4_inversion_bootstrap.py` (2) | Une seule procédure par Δ : l'IC obtenu en inversant le test de changement de signe, ou la p tirée du même bootstrap. Sinon, écrire laquelle des deux décide. |
| **N3** | A4 « il voit l'hallucination d'un document sans référence » | Contre-exemple R5 rejoué : D^M = {d1}, Δ macro = 0 ; micro : A 0,667, B 1,0. | `r2_r5_support_reference.py` | A4 : « le macro ne voit pas l'hallucination d'un document sans référence ; le micro la voit. » |
| **N4** | § 2.2 `lookup_key` (partie **déclarée**) et `validation` (re-hachage des fichiers de `record.environment`) ; I1 « modifier un fichier de poids interdit la réutilisation » | (a) Les poids et les sources de la brique sont dans `StepDefinition`, ni dans la clé ni dans la validation : un `fra.traineddata` remplacé est relu (clé identique, validation vraie). (b) La validation re-hache les chemins **enregistrés**. Si le processus courant résout le module ailleurs (autre venv, homonyme plus tôt dans `sys.path`), l'ancien fichier, intact, valide une exécution dont le code a changé. | `r2_p10_recherche_validation.py` | La validation porte sur toute la partie **calculée** de la définition (poids, sources) en plus de l'environnement, et résout chaque module **par son nom** dans le processus courant (`importlib.util.find_spec`) avant de hacher. |
| **N5** | § 2.3 d `ProtocolDefinition` ⊃ « sources .py de cinoc.evaluation et cinoc.formats **chargées** » ; I3, I5 | Même CER, même copie, trois processus : re-notation seule, empreinte `a41e…` (68 modules) ; plus validation d'images, `6564…` (69) ; plus analyse longitudinale, `5bd8…` (69). Trois définitions pour un même protocole. | `r2_p11_definition_chargee.py` | Hacher toutes les sources des deux paquets sur disque, pas les modules chargés. |
| **N6** | § 2.4 a 1 : filiation vérifiée par « la paire (même id) est admissible », « retenue en priorité » ; M8 « optimum égal à l'énumération » | VT r1 = page entière, r2 = ses 60 % supérieurs. Une brique `preserves_region_ids` échange les deux ids. Chaque paire par id est admissible (IoU 3/5), donc retenue : `region_cer` = **1,2**, alors que l'optimum (IoU 1 et 1) donne 0,0. | `r2_r11_filiation_permutee.py` | Sous héritage, exiger une géométrie **identique** à celle de la VT (empreinte des coordonnées), ou ne retenir une paire par id que si elle appartient à un optimum lexicographique. |
| **N7** | § 2.4 b « la projection en texte linéarise un groupe non ordonné dans l'ordre de déclaration du fichier » ; M5 ; M7 | Deux marginalia d'un `UnorderedGroup`, hypothèse dans l'ordre inverse. Le τ ne pénalise pas, mais le CER de la vue texte vaut **0,919** ou **0,0** selon l'ordre de déclaration dans le XML d'une VT identique. | `r2_r3_groupe_non_ordonne_cer.py` | Écrire la convention (la vue texte impose l'ordre de déclaration, publiée comme telle), ou apparier les membres d'un groupe non ordonné avant de les concaténer. |
| **N8** | § 6 B5 « `method="auto"` (exact si n ≤ 50 sans zéro ni ex æquo, sinon approximation) » | scipy 1.18.1, n = 7 avec des ex æquo : `auto` rend p = 0,266, `exact` 0,219, `approx` 0,161. `auto` ne fait aucune des deux choses annoncées. Les ex æquo exacts sont précisément ce que P4 préserve. La p reste déterministe (vérifié). | `r2_p4_wilcoxon_auto.py` | Passer `method` explicitement et écrire la méthode réellement appliquée avec la version tracée. |

Remarque de forme : la table de la révision n° 2 renvoie à `scratchpad/ce-contrats-r2/`, alors que les scripts de l'auteur sont aussi dans `tests/adversarial/rapports/revision2_verifications/`. Mieux vaut un seul chemin.

### 6.3 Avis de clôture

La révision n° 2 lève 25 points sur 31 et n'en laisse aucun entièrement debout. Les six levées partielles et les huit contradictions nouvelles se corrigent chacune par une clause, sans toucher aux contrats. Deux d'entre elles sont à régler **avant la tranche 1a** :
- **N1, N2** : niveau aux petits n, et cohérence entre p et IC pour un même Δ ;
- **N3** : formulation d'A4.

Deux autres sont à régler avant la tranche 3 :
- **N4** : la validation doit couvrir la partie calculée de la définition et résoudre par nom ;
- **N5** : sources sur disque, pas modules chargés.

N6 est à régler avant la tranche 4. Aucun contrat n'est à repenser.

---

## 7. Clôture de la révision n° 3

Objet : la révision n° 3 de `CONTRATS.md`, avec sa table « Révision n° 3 » et les deux nouveaux scripts de l'auteur, `revision2_verifications/n1_n2_procedure_unique.py` et `n8_wilcoxon_methode_explicite.py`. Je les ai exécutés tous deux ; ils reproduisent les valeurs annoncées.

Méthode :
- les contre-exemples `r2_*` sont rejoués contre les règles révisées ;
- la partie statistique est mesurée sur les scénarios que B9 nomme lui-même.

Les sept scripts `r3_*.py` sont dans `/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/ce-review2/`. `run_all.sh` rejoue les 23 + 10 + 7 scripts ; les 40 se reproduisent.

**Comptes N1 à N8** : **6 levés** (N2, N3, N4, N5, N7, N8), **2 partiels** (N1, N6), **0 non levé**.

Parmi les six points partiels de la révision n° 2 :
- **levés** : R5, P4, P10 et P11 ;
- **encore partiels** : R4 (via N1) et R11 (via N6).

**Contradictions nouvelles : 5** (C1 à C5).

### 7.1 Point par point

| Point | Verdict | Une ligne |
|---|---|---|
| N1 | **partiel** | SF tient à tout n. En revanche, BA (n ≥ 30) et PS (n < 30) ne tiennent pas la borne d'A3 sur deux des quatre scénarios que B9 retient lui-même (C1, C2). |
| N2 | **levé** | Une seule procédure par Δ. SF par inversion : l'indicatrice de chaque partie J est monotone en δ (Σ_J e ≤ δ Σ_J n), donc p_haut croît, p_bas décroît et l'IC est d'un seul tenant. Je trouve 0 violation sur 300 jeux. Couverture de 0,942 sous effets hétérogènes de type Simpson à n = 10. Pour BA, p et IC viennent des mêmes réplicats (`r3_sf_inversion.py` (1), (3)). Une exception, sur le seuil « n ≤ 5 » : voir C3. |
| N3 | **levé** | A4 est corrigé. La nouvelle analyse « invention hors référence » est à préciser (C5). |
| N4 | **levé** | Rejeu de `r2_p10` sous la validation révisée (partie calculée de la définition, et modules résolus par leur nom) : les poids remplacés et le module résolu dans un autre venv sont tous deux détectés (`r3_n4_n5_rejeu.py`). |
| N5 | **levé** | Les sources sur disque rendent la définition indépendante de ce qui est chargé. Remarque : `find_spec("pkg.sub")` importe `pkg`, donc exécute son `__init__`. « Résolu sans exécuter » n'est vrai que pour les modules de premier niveau ; il suffit de corriger la phrase (même script). |
| N6 | **partiel** | L'échange d'ids est levé (`region_cer` 0). Mais la justification « une paire héritée appartient toujours à un optimum des critères 1 et 2 » est fausse quand des régions de la VT se recouvrent (C4). |
| N7 | **levé** | L'ordre (y0, x0) ne dépend plus de la déclaration : même projection, même CER (`r3_n7_rejeu.py`). |
| N8 | **levé** | `PermutationMethod` explicite, vérifié contre une énumération écrite à la main (n = 7 : 0,2656 ; n = 20 : 0,4366). La graine déclarée rend la p répétable. |

### 7.2 Contradictions nouvelles

| # | Phrase visée | Contre-exemple minimal | Script | Correction minimale |
|---|---|---|---|---|
| **C1** | § 2.1 d, PS : « rejet mesuré entre 0,000 et 0,060 pour n de 5 à 30 » ; A3 : « pour chaque procédure et chaque n du jeu de calibration, taux de rejet ≤ α + 3 erreurs MC » ; B9 : le jeu comprend « une page à fort levier, des dénominateurs très inégaux » | PS implémentée comme dans `n1_n2_procedure_unique.py` (c), sous H0 R_A = R_B, 1 000 simulations par case, borne 0,071 :<br>• scénario F1 de la revue : 0,000 à 0,073 ;<br>• **un document à 60 entités, les autres à 2** : **0,346 (n = 6), 0,519 (n = 10), 0,542 (n = 15), 0,418 (n = 20)** ;<br>• **dénominateurs lognormaux** : **0,141 (n = 8), 0,121 (n = 15), 0,119 (n = 25)** ;<br>• MER : 0,000 à 0,071.<br>La mesure de l'auteur ne porte que sur le premier scénario. | `r3_ps_niveau_scenarios.py` | Ne publier la p de PS que si un diagnostic de levier déclaré (part maximale d'une unité dans Σ dénominateur) est sous un seuil calibré sur tout le jeu B9 ; sinon « non estimable (levier) ». |
| **C2** | B9 : « n_min = le plus petit n à partir duquel BA tient α + 3 erreurs MC sur **tous** les scénarios » ; § 2.1 d « n_min = 30 provisoirement » | BA, 600 simulations par case, borne 0,077 :<br>• lognormal : **0,107 (n = 30)**, 0,087 (n = 50), 0,062 (n = 100) ;<br>• levier : 0,065 (n = 30), **0,083 (n = 50), 0,087 (n = 100)**.<br>Sur le jeu de calibration de B9, n_min est d'au moins 100, ou n'existe pas tant que le levier ne diminue pas avec n. Comme PS échoue aussi (C1), **aucune** procédure du contrat ne couvre une famille à dénominateur d'hypothèse dont une unité a un fort levier. | `r3_ba_n_min_scenarios.py` | Même diagnostic de levier pour BA. Définir n_min sur les scénarios à levier borné, et publier « non estimable » au-delà du seuil de levier, quel que soit n. |
| **C3** | § 2.1 d, SF : « si n ≤ 5, aucun rejet possible ; IC non borné » | Une page à référence vide (n_d = 0, au support micro) a r_d(δ) = e_d, constant en δ : quand δ → ±∞, p tend vers environ 2·2^(k−n). Exemple : n = 8 dont 3 pages vides donne p(0) = 0,016 (rejet), mais p(δ = 10) = 0,055 > α. L'IC est donc **non borné** alors que n = 8 > 5. | `r3_sf_inversion.py` (2) | Le seuil porte sur n_eff = #{unités à n_d > 0}. Publier « IC non borné » quand 2^(1+k−n) > α. |
| **C4** | § 2.4 a : « Une paire héritée a IoU = 1. Elle appartient donc **toujours** à un optimum des critères 1 et 2 » ; M8 | Le critère 1 (nombre de paires) prime sur l'IoU. VT : r1 (page entière) et r2 (60 % du haut). La brique garde r1 à l'identique (même id, même géométrie) et remplace r2 par h2 (de 40 % à 100 %). L'énumération donne r1↔h2 et r2↔(copie de r1), avec la clé (2, 6/5). La paire héritée est hors de tout optimum, et `region_cer` vaut 0,84 contre 0,76 si elle est gardée. | `r3_n6_heritage_hors_optimum.py` (b) | Fixer les paires héritées avant l'optimisation, qui porte alors sur le reste ; ou retirer la phrase et écrire dans M8 que l'héritage ne survit pas au critère 1. |
| **C5** | § 2.1 c, « invention hors référence » : « par pipeline … publiés à côté de chaque macro » ; A6 | (a) Calculée par pipeline, donc sur des supports différents : A échoue sur 3 pages blanches sur 4 et affiche (0 document, 0 caractère inventé) ; B les lit toutes et affiche (1, 2). Sur leur support apparié, les deux sont identiques. (b) « Unités inventées » n'est pas défini pour les proportions à dénominateur de référence (`numseq_*`, `searchability`, `diacritic_err`, `mufi_err`), dont le macro est pourtant publié : leur statistique ne compte aucune unité de l'hypothèse (`metrics/structured_data.py:168-175`). | `r3_invention_hors_reference.py` | Publier l'analyse sur le support apparié ou global, avec la couverture des pages vides, et déclarer l'unité inventée par famille (« non défini » pour ces proportions). |

Remarque, sans contradiction : à n ≤ 5, PS ne peut pas rejeter non plus. Le cas extrême (l'identité et l'échange complet ont le même |T|) est atteint par 2 des 32 permutations, donc p ≥ 2/32 > α. Il faut l'écrire comme pour SF. Avec les 5 grappes de BNL, aucun Δ d'aucune famille ne peut donc être déclaré significatif.

### 7.3 Ce qui tient dans la partie statistique

- **SF** : niveau ≤ α à tout n sous sa H0 nommée (échangeabilité), et elle s'applique à la famille dont le dénominateur est fixé par la référence. L'IC par inversion est d'un seul tenant, par la monotonie démontrée au § 7.1 (N2), et couvre bien le Δ micro sous des effets hétérogènes (0,942 pour un nominal de 0,95). Il n'y a aucune contradiction entre p et IC.
- **BA** : p et IC sont tirés des mêmes réplicats, donc cohérents par construction. P2 (réplicats écartés au-delà de ε) est inchangé et tient.
- **N8 et P4** : la méthode des rangs est explicite et répétable.

### 7.4 Avis : la tranche 1a peut-elle commencer ?

**Oui pour le premier commit, celui des tests adversariaux rouges. Non pour le correctif d'inférence tant que B9 n'est pas reformulé.**

Les contrats de la tranche 1a sont stables et sans contradiction ouverte :
- les statistiques exactes par famille ;
- P1 ;
- D^M fixé par la référence ;
- SF ;
- les rangs explicites ;
- Holm a priori ;
- les grappes et l'ordre canonique.

Les invariants correspondants (M1, M2, M3, M6, A4, A5, A8, A9, A10, A13) peuvent être écrits en tests rouges dès maintenant. Les scénarios de C1 et C2 doivent y entrer comme cas de calibration d'A3.

B9, en revanche, ne peut pas être tranché tel qu'il est écrit : sa propre définition (« tous les scénarios du jeu ») réfute n_min = 30, et aucune procédure ne tient sous fort levier. Avant de coder l'inférence des familles à dénominateur d'hypothèse, B9 doit être reformulé :
- un diagnostic de levier déclaré ;
- « non estimable » au-delà de son seuil, à tout n ;
- n_min calibré sur les scénarios à levier borné.

Restent ensuite à écrire C3 (n_eff) et C5 (support et unités de l'analyse d'invention). Ce sont des clauses ; aucun contrat n'est à repenser. C4 relève de la tranche 4.

---

## 8. Clôture de la révision n° 4

Objet : la révision n° 4 de `CONTRATS.md`, avec sa table « Révision n° 4 » et les scripts de l'auteur `c1_c2_levier_calibration.py` et `n5_resolution_sans_import.py`. Je les ai exécutés tous deux ; ils redonnent les valeurs annoncées.

J'ai recalibré B9 **indépendamment**, avec mon propre code, ma propre graine et un nombre de réplicats différent, sur :
- les scénarios de C1 et C2 ;
- **trois scénarios que l'auteur n'a pas vus** :
  - des dénominateurs bimodaux ;
  - une corrélation entre le dénominateur et l'effet ;
  - des grappes de tailles inégales, avec un effet propre à chaque grappe.

Les scripts `r4_*.py` sont dans `/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/ce-review2/` et `run_all.sh` les rejoue avec les autres. Comptez environ 40 minutes : les calibrations sont longues.

**Comptes** : C1 à C5 et la remarque `find_spec` (6 points) donnent **4 levés** (C1, C4, C5, `find_spec`), **2 partiels** (C2 / B9 et C3), **0 non levé**. **4 contradictions nouvelles** (D1 à D4), plus une perte de puissance chiffrée.

### 8.1 Point par point

| Point | Verdict | Une ligne |
|---|---|---|
| C1 | **levé** | PS est retirée ; il ne reste qu'une procédure par famille. |
| C2 / B9 | **partiel** | Le diagnostic de Kish refuse bien les cas à levier non borné. Mais au seuil 20, le niveau ne tient pas sur le scénario lognormal de l'auteur dès que l'erreur Monte-Carlo est réduite (D1), et le critère d'A3 dépend du nombre de simulations (D2). Le diagnostic porte sur les sorties et peut être contourné (D3). |
| C3 | **partiel** | Les comptes n₀ ≥ 6 (rejet possible) et m ≥ 6 (IC borné) sont exacts, et ce sont les bonnes quantités. Mais ils ignorent la correction de Holm : « avec les 10 pages Dresden, SF peut rejeter » est faux sous la famille par défaut B4 (D4). |
| C4 | **levé** | Paires héritées fixées, puis optimum sur le reste : `region_cer` = 0,76 (`r4_c4_c5_rejeu.py`). |
| C5 | **levé** | L'analyse se fait sur le support apparié, et A et B y sont identiques ; l'unité est déclarée par famille (même script). |
| `find_spec` | **levé** | Résolution par `sys.meta_path` composant par composant : le `__init__` n'est pas exécuté et `cinoc` n'est pas importé (script de l'auteur rejoué). |

### 8.2 Calibration indépendante de B9

BA conditionné à n_eff ≥ 20 (`r4_ba_kish_calibration.py`, 600 jeux par case, 1 499 réplicats). Colonnes :
- **niveau parmi les retenus** : taux de rejet sous H0, parmi les jeux qui passent le diagnostic ;
- **BA sans diagnostic** : taux de rejet sur tous les jeux ;
- **non estimables** : part des jeux refusés par le diagnostic.

| Scénario (n) | Niveau parmi les retenus (borne) | BA sans diagnostic | Non estimables |
|---|---|---|---|
| revue (25) | **0,078** (0,077) ; à 2 000 jeux : **0,067** (0,065) | 0,078 | 0 % |
| revue (30 à 100) | 0,050 à 0,058 | idem | 0 % |
| levier r0 = 60 (10 à 100) | — | 0,045 à 0,128 ; à 2 000 jeux, **0,061 (60) et 0,071 (100)** | **100 %** (refus justifié : BA ne tient pas) |
| lognormal (60) | **0,095** (0,086) ; à 1 059 et 770 retenus : **0,096 et 0,079** (0,070 et 0,074) | 0,076 à 0,078 | 45 % |
| lognormal (100) | 0,065 (0,079) ; à 1 277 retenus : **0,075** (0,068) | 0,070 à 0,073 | 13 à 15 % |
| MER (25 à 100) | 0,032 à 0,038 | idem | 0 % |
| MER (20) | — | **0,030** ; à 2 000 jeux : **0,0495** | **100 %** |
| bimodal\* (100) | 0,072 (0,077) | 0,070 | 2 % |
| corrélé\* (40, 60, 100) | 0,063 / 0,055 / 0,047 | idem | 10 % / 0 % / 0 % |
| corrélé\* (30) | 0,25 sur 32 retenus (trop peu pour conclure) | 0,053 ; à 2 000 jeux : **0,0695** | 95 % |
| grappes\* (40, 60, 100) | 0,072 / 0,058 / 0,053 | idem | 17 % / 0 % / 0 % |
| Jeux à 20 ≤ n_eff < 25, scénarios lourds confondus (975 jeux) | **0,073** (0,071) | — | — |

\* scénario nouveau, non vu par l'auteur.

Ce qui en ressort :
- **Le diagnostic fait bien son travail principal.** Il refuse le levier non borné (BA y rejette entre 0,06 et 0,07), et sur les trois scénarios nouveaux le niveau parmi les retenus tient dès que n ≥ 40.
- **Il ne rend pas BA valide sous des dénominateurs à queue lourde.** Sur le lognormal de l'auteur, le niveau parmi les retenus vaut entre 0,075 et 0,096 à n = 60 et 100. La règle ≥ 30 ne corrige rien (0,081 à n = 100), et un Kish calculé sur la référence non plus (0,071 à 0,073) (`r4_diagnostic_non_ancillaire.py`). C'est BA percentile qui est anticonservatrice d'environ 1,5·α. Les 600 jeux de l'auteur et le faible nombre de jeux retenus (518, borne 0,079) l'avaient masqué.
- **Puissance perdue là où BA tient.** Pour MER à n = 20, BA a un niveau de 0,0495 (2 000 jeux), mais n_eff ≈ 0,96·n < 20 entraîne 100 % de « non estimable ». Sous l'alternative q_B = 0,4, la puissance de BA (0,43) devient une **puissance publiée de 0**. Ailleurs, la perte touche des cas où BA ne tenait pas non plus :
  - corrélé à n = 30 : niveau 0,0695, puissance 0,41 réduite à 0,08 publiée ;
  - bimodal à n = 60 : niveau 0,070, puissance 0,34 réduite à 0,03 ;
  - levier à n = 100 : puissance 0,78 réduite à 0 (`r4_ba_kish_confirmation.py`).

### 8.3 Contradictions nouvelles

| # | Phrase visée | Contre-exemple minimal | Script | Correction minimale |
|---|---|---|---|---|
| **D1** | B9 et § 2.1 d : « au seuil n_eff ≥ 20, aucune case ne dépasse α + 3 erreurs Monte-Carlo » | Scénario lognormal de l'auteur, n = 60 : 0,096 parmi 1 059 jeux retenus (borne 0,070). À n = 100 : 0,075 parmi 1 277 (borne 0,068). Jeux juste au-dessus du seuil : 0,073 (borne 0,071). | `r4_ba_kish_confirmation.py`, `r4_diagnostic_non_ancillaire.py` | Soit publier le niveau réel de BA sous queue lourde (environ 0,075 à 0,08) comme tolérance assumée, soit changer la procédure pour ces familles (bootstrap studentisé, à calibrer), soit ajouter au diagnostic un critère de queue. |
| **D2** | A3 : « taux de rejet ≤ α + 3 erreurs Monte-Carlo » | Un vrai niveau de 0,075 passe à 600 jeux (borne 0,077) et échoue à 2 000 (borne 0,065). L'invariant change de verdict avec le nombre de simulations, sans que la procédure change. | mêmes scripts | Fixer une **tolérance sur le niveau vrai** (par exemple ≤ 0,06) et un nombre de simulations qui la rend décidable (erreur MC ≤ 0,003, soit environ 5 000 jeux retenus par case). |
| **D3** | § 2.1 d : n_eff = min sur la paire de (Σ den)²/Σ den², den étant celui de **chaque pipeline** | 40 documents ; A a F1 0,8 et B F1 0,6, avec n_eff 38,9 et p < 10⁻⁴. Si B invente **en plus** 2 000 entités sur un document, il est encore pire (F1 0,10), mais n_eff tombe à 1,4 et le verdict devient « non estimable ». Être pire efface le verdict. | `r4_levier_echappatoire.py` | Calculer le diagnostic sur des quantités de **référence** (tp+fn, n_réf), qui sont ancillaires et communes à la paire (niveau mesuré équivalent, 0,071 à 0,073). Ou publier l'invention massive comme constat. |
| **D4** | C3, § 2.1 d : « un rejet n'est possible que si n₀ ≥ 6 » ; « avec les 10 pages Dresden, SF peut rejeter » ; B4 (famille par défaut) | `campaigns/2026-11-26-reference/dresden.yaml` : 10 pipelines, 45 paires, 8 couples (vue, métrique établie), 2 estimandes, donc m = 720. La p minimale de SF vaut 2⁻⁹, soit 0,00195, et la p corrigée par Holm vaut **1,0**. Un rejet exige n₀ ≥ 1 + log₂(m/α), soit **15** unités. | `r4_sf_holm_dresden.py` | Écrire le seuil corrigé (rejet possible ssi m·2^(1−n₀) ≤ α), et publier pour chaque campagne le n₀ requis par sa famille. Une famille déclarée réduite (un témoin contre les autres) relève de B4. |

### 8.4 Avis : reste-t-il une contradiction qui empêche de commencer la tranche 1a ?

**Non pour commencer la tranche 1a : tests rouges d'abord, puis l'implémentation des statistiques, des supports, de SF, des rangs et de Holm.** Ces contrats sont stables, sans contradiction ouverte, et D4 n'est qu'un seuil à écrire.

Une condition reste toutefois attachée à B9 : **telle qu'elle est écrite, elle n'est pas satisfaite par son propre scénario lognormal** une fois l'erreur Monte-Carlo maîtrisée (D1). Son critère d'acceptation est aussi indécidable en l'état (D2). Avant d'implémenter BA pour les familles à dénominateur d'hypothèse (F1, MER, exactitudes, précisions, τ), il faut que le mainteneur tranche trois choses :
1. une tolérance de niveau explicite, avec le nombre de simulations qui la décide ;
2. un diagnostic calculé sur la référence (il ferme aussi D3) ;
3. pour les queues lourdes, soit la tolérance qu'il accepte (environ 0,075), soit une autre procédure.

Ce sont des paramètres de B9, pas une contradiction de contrat. Les tests rouges d'A3 peuvent être écrits dès maintenant, avec les sept scénarios de ce paragraphe.
