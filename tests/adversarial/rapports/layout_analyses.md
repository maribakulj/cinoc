# Contre-expertise — domaine `layout_analyses` (commit 04a1c17b, copie figée)

Tests : `tests/adversarial/layout_analyses/` (copie figée), 5 fichiers, **30 tests : 23 rouges, 7 verts**.
Tous construits par les API publiques (`metric.fn(DocContext)`, `correspondance`, `evaluate_run`,
`calibration_analysis`, `parse_layout_xml`, `layout_to_text`, `LayoutToTextExtractor.execute`,
`run_region_fanout` avec un reconnaisseur factice injecté). Références indépendantes :
`scipy.optimize.linear_sum_assignment`, IoU d'intervalles calculée à la main, `difflib.SequenceMatcher`.

Synthèse en une ligne : l'appariement glouton n'est qu'un défaut **étroit** ; les défauts **graves**
du domaine sont (1) la stratégie « identifiant d'abord, géométrie seulement si aucun id ne se recoupe »,
qui apparie des blocs non homologues et masque une inversion d'ordre de lecture, (2) l'aplatissement
multipage sans indice de page, (3) `correction` et `decisions` qui lisent le pool final et non la cible
de la vue — sous une vue d'ablation, un bilan « régression catastrophique » s'affiche à côté d'un CER de 0.

---

## L1 — Appariement glouton contre optimum global

| champ | contenu |
|---|---|
| Affirmation | L'appariement IoU est glouton et peut rendre moins que l'optimum. |
| Verdict | **confirmé**, mais dans un cas **étroit** (il faut des boîtes de référence qui se chevauchent fortement). |
| Contre-exemple | Page 128×128, boîtes pleine hauteur. Réf A=[0,10], B=[2,12] ; hyp X=[1,11], Y=[-3,7]. IoU(A,X)=9/11, IoU(A,Y)=7/13, IoU(B,X)=9/11, IoU(B,Y)=1/3. Le glouton donne X à A ; B n'a plus que Y (< 0,5). `test_la_matching.py::test_glouton_vs_optimal__la_detection_atteint_l_optimum_global`, `::test_glouton_vs_optimal__region_cer_suit_l_appariement_optimal`. C'est le plus petit contre-exemple possible (2×2 : avec une seule réf ou une seule hyp, le glouton est optimal). |
| Comportement actuel | `region_detection` = **0,5** (1 VP). `correspondance` = `{A: X}`. `region_cer` = **1,444** pour des textes parfaits sous l'appariement optimal. |
| Comportement attendu | F1 = **1,0** : `linear_sum_assignment` rend 2 paires, que l'on maximise la cardinalité des paires au-dessus du seuil ou la somme des IoU (les deux critères concordent ici). `region_cer` = 0. Écart : **0,5 de F1**, soit 1,44 de CER par région. |
| Tests existants | `tests/evaluation/test_region_detection.py`, `test_appariement_geometrique.py` : boîtes toujours disjointes, chaque boîte n'a qu'un seul candidat au-dessus du seuil. Le cas d'un conflit n'est jamais construit. |
| Cause architecturale | `cinoc/evaluation/metrics/layout.py:172` `_greedy_pairs` : chaque réf, **dans l'ordre du fichier**, prend sa meilleure hyp libre. La même fonction sert `region_detection`, `correspondance` (et donc `region_cer`, `reading_order_*`). **Une cause, trois symptômes** (L1, L2, une partie de L5). Le projet utilise déjà l'algorithme hongrois pour les lignes (`metrics/flexible.py:50`). |
| Gravité scientifique | **Faible** sur une VT propre. Avec un seuil inclusif et des réf disjointes, une hyp ne dépasse 0,5 avec deux réf que dans le cas dégénéré IoU = 0,5 exactement. Le défaut demande donc des boîtes de réf qui se recouvrent (boîtes englobantes de polygones de colonnes inclinées, régions en L). Quand il joue, il sous-estime le F1 d'un système **et** dépend de l'ordre (L2). |

## L2 — Ordre des régions

| champ | contenu |
|---|---|
| Affirmation | Permuter les régions de l'hypothèse ne doit pas changer la détection ; cela doit changer l'ordre de lecture s'il est mesuré. |
| Verdict | **partiel**. (a) Permuter l'**hypothèse** sans égalité d'IoU : **réfuté**, F1 inchangé. (b) Permuter la **référence** : **confirmé**, le F1 change. (c) Égalité d'IoU : **confirmé** (mineur), permuter l'hypothèse change le F1. (d) Ordre de lecture entre systèmes à ids étrangers : **réfuté**, il est bien mesuré (tau = 1,0 pour une inversion totale). |
| Contre-exemple | (a) `test_la_matching.py::test_ordre_des_regions_hypothese__la_detection_n_en_depend_pas_hors_egalites` (vert). (b) `::test_ordre_des_regions_de_reference__la_detection_n_en_depend_pas` : même ensemble {A, B}, ordre [A,B] puis [B,A]. (c) `::test_ordre_des_regions_hypothese__egalite_d_iou_sans_effet_d_ordre` : a=[0,10], b=[4,14], x=[1,11], y=[-1,9], IoU(a,x)=IoU(a,y)=9/11, valeurs exactes en dyadique. (d) `::test_permutation_regions_hypothese__detection_inchangee_ordre_de_lecture_mesure` (vert). |
| Comportement actuel | (b) F1 ∈ {0,5 ; 1,0} selon l'ordre de la VT. (c) hyp [x,y] → 1,0 ; [y,x] → 0,5 (en cas d'égalité, `>=` donne la victoire à la **dernière**). |
| Comportement attendu | Une métrique d'ensemble ne dépend pas de l'ordre de sérialisation. Le F1 optimal est 1,0 dans les deux cas. |
| Tests existants | Aucun ne permute. |
| Cause architecturale | `layout.py:172-197` (`_greedy_pairs`, `>=` en `:190`). Même cause que L1. |
| Gravité scientifique | Faible. Elle ne se déclenche qu'en cas de conflit (L1) ou d'égalité. Mais elle rend le chiffre non reproductible si l'on réordonne un fichier, ce qui contredit l'invariant de déterminisme sur le *contenu*. |

## L3 — Identifiants identiques mais non homologues (dont ALTO sans `ID`)

| champ | contenu |
|---|---|
| Affirmation | Cinoc apparie par `id` plutôt que par géométrie, même quand les ids coïncident sans désigner la même région. |
| Verdict | **confirmé**, **grave**. |
| Contre-exemple | (1) VT r1=haut « alpha », r2=bas « beta » ; un détecteur numérote r1=bas « beta », r2=haut « alpha » ; transcription parfaite, même ordre de lecture haut→bas. `test_la_matching.py::test_ids_identiques_non_homologues__appariement_par_geometrie`. (2) Deux ALTO **sans attribut `ID`** (2 colonnes). VT gauche « alpha » puis droite « beta » ; sortie droite « beta » puis gauche « alpha ». Les deux côtés reçoivent `region_0`/`region_1` par `formats/_region_ids.py`. `test_la_multipage_ids.py::test_alto_sans_id__appariement_par_geometrie_et_ordre_inverse_detecte`. |
| Comportement actuel | (1) `region_detection` 1,0 (il apparie par géométrie) mais `region_cer` = **0,889** et `reading_order_tau` = **1,0** (« ordre totalement inversé ») pour une sortie parfaite. (2) `region_cer` = **0,889** pour un texte parfait, et `reading_order_tau` = **0,0** alors que l'ordre est réellement inversé : l'erreur d'ordre est **masquée**. |
| Comportement attendu | (1) CER par région 0, tau 0. (2) CER par région 0, tau 1,0. Un identifiant n'établit une correspondance que si les deux fichiers partagent un espace de noms. Deux numérotations séquentielles indépendantes (`r1…`, `region_0…`) n'en partagent pas. C'est la géométrie (déjà utilisée par `region_detection`) qui doit décider, ou du moins confirmer l'appariement. |
| Tests existants | `test_appariement_geometrique.py::test_identifiants_partages_inchanges` **fige** le choix « l'identifiant reste prioritaire » pour que « aucune valeur déjà publiée ne bouge ». Aucun test ne construit des ids partagés mais non homologues. |
| Cause architecturale | `layout.py:232-266` `correspondance` : `if communs: return {id: id for id in communs}` (`:256`). Même logique dans `_ordres` (`:382`). La géométrie n'est ni consultée ni utilisée pour vérifier. Le domaine (`domain/layout.py:85` `Region.id`) ne dit pas si un id est un identifiant **stable entre systèmes** ou un simple numéro local. Les segmenteurs de Cinoc numérotent eux-mêmes `r1…rN` par (y, x) (`adapters/layout/_base.py:131`), ce qui produit des collisions avec toute VT numérotée `r1…`. **Une cause, trois métriques fausses** : `region_cer`, `reading_order_tau`, `reading_order_coverage`. `region_detection`, purement géométrique, n'est pas touché, d'où une incohérence interne : 1,0 de détection à côté de 0,89 de CER par région. |
| Gravité scientifique | **Élevée.** Avec *n* blocs numérotés différemment, `region_cer` compare des textes sans rapport (≈ 1 ou plus) pour une transcription parfaite, et `reading_order_tau` mesure l'accord entre deux conventions de numérotation, pas l'ordre de lecture. Cas réaliste : un détecteur de Cinoc (`r1…`, tri y/x) contre une VT PAGE dont les régions s'appellent aussi `r1…` (convention courante des exports), ou deux ALTO sans `ID`. Le classement sur la vue `structure` peut s'inverser. |

## L4 — Identifiants partiellement partagés

| champ | contenu |
|---|---|
| Affirmation | Des ids partiellement partagés font perdre l'appariement des autres régions. |
| Verdict | **confirmé**. |
| Contre-exemple | VT {r1 haut « alpha », r2 bas « beta »} ; hyp {r1 haut « alpha », x9 bas « beta »}, textes parfaits. `test_la_matching.py::test_ids_partiellement_partages__la_region_non_nommee_reste_appariee`. Le témoin `::test_ids_partages_homologues__identite_exacte_conservee` est vert. |
| Comportement actuel | `correspondance` = `{r1: r1}` : un seul id commun désactive la géométrie pour **toutes** les régions. `region_cer` = **0,889** (r2 compté comme supprimé, x9 comme fantôme), `reading_order_tau` = **None**, `reading_order_coverage` = **0,5**. |
| Comportement attendu | CER par région 0, couverture 1,0, tau 0. Les régions sans id commun doivent être appariées par géométrie. |
| Tests existants | Aucun cas mixte. |
| Cause architecturale | `layout.py:256` : stratégie « tout ou rien ». Même cause que L3. |
| Gravité scientifique | Moyenne à élevée. Un correcteur ou un réordonnanceur qui renomme ou fusionne une partie des blocs voit son CER par région gonflé du double de leur texte (suppression + insertion). |

## L5 — Documents multipages

| champ | contenu |
|---|---|
| Affirmation | Les régions de la page 2 sont appariées à celles de la page 1, et l'agrégation par page est fausse. |
| Verdict | **confirmé** (trois symptômes). |
| Contre-exemple | (a) VT p1 bloc haut / p2 bloc bas ; hyp p1 bloc bas / p2 bloc haut. `test_la_multipage_ids.py::test_multipage_detection__pas_d_appariement_entre_pages`. (b) Deux pages de même gabarit, ids étrangers, sortie parfaite. `::test_multipage_mise_en_page_repetee__region_cer_nul_pour_une_hypothese_parfaite`. (c) Ids locaux à la page (`r1` sur p1 et p2, que le domaine n'interdit pas) ; erreur totale sur p1 (« XXXXX »). `::test_multipage_ids_locaux_a_la_page__toutes_les_regions_comptent`. |
| Comportement actuel | (a) `region_detection` = **1,0** au lieu de 0 : la boîte de la page 2 sert à la page 1. (b) À IoU égale (1,0), le `>=` du glouton apparie la réf p1 à l'hyp **p2** et inversement : `region_cer` = **0,889** et `reading_order_tau` = **1,0** pour une sortie parfaite. (c) `region_cer` = **0,0** sur un poids de **4** caractères au lieu de 5/9 sur 9 : la page 1 est **effacée** par écrasement de clé et son erreur disparaît. |
| Comportement attendu | Appariement **à l'intérieur de chaque page**, puis agrégation micro sur les pages. (a) 0, (b) 0, (c) 5/9 sur un poids de 9. |
| Tests existants | Tous les tests de structure sont monopages. Le docstring de `CanonicalLayout` dit d'ailleurs que « le multi-page est réservé ». |
| Cause architecturale | `layout.py:145` `_detection_boxes` et `:202` `_identified_boxes` concatènent les boîtes relatives de toutes les pages sans indice de page. `:49` `_region_texts` est un `dict` global par id. `_ordres` concatène les ordres. Le domaine n'impose pas l'unicité des ids dans un document (`domain/layout.py:146`). Le parseur ALTO produit bien des layouts multipages (`formats/alto/layout_map.py:151`). |
| Gravité scientifique | Moyenne, mais limitée aux ALTO multi-`<Page>` (rares : la BnF et la BnL livrent un ALTO par page). Sur un tel document, les gabarits répétés (colonnes identiques d'une page à l'autre) sont **la règle**, et (b) fausse alors tous les chiffres par région d'une sortie parfaite. |

## L6 — Réassemblage par ordre de lecture (couches 3/4/5)

| champ | contenu |
|---|---|
| Affirmation | Le réassemblage par ordre de lecture (fan-out, couche 4) est correct là où l'appariement intervient. |
| Verdict | **partiel**. Le fan-out lui-même : **réfuté**, il préserve `reading_order` et l'identité des régions. La **projection** `LAYOUT → texte` : **confirmé**, il en existe deux et elles divergent. Le fan-out multipage : **confirmé** (cas limite). |
| Contre-exemple | Vert : `test_la_reassembly.py::test_fanout__ordre_de_lecture_preserve_au_reassemblage`. Rouges : `::test_ordre_de_lecture_imbrique__la_projection_d_evaluation_le_respecte` (bloc composé C{c1 « alpha », c2 « beta »}, ordre plat c2→c1, la forme documentée par `LayoutPage.reading_order`) ; `::test_deux_projections__meme_layout_meme_texte` ; `::test_deux_projections__ordre_imbrique_identique` ; `::test_deux_projections__candidat_parfait_cer_nul_vue_lignes` (5 blocs, VT LAYOUT projetée par la vue, candidat = même layout projeté par l'étape `projection` des recettes, vue `keep_line_breaks`, via `evaluate_run`) ; `::test_fanout_multipage__une_page_n_est_pas_lue_dans_l_image_d_une_autre`. |
| Comportement actuel | Couche 3 : `"alpha\nbeta"`, l'ordre imbriqué est **ignoré**. Couche 5 : `"beta\nalpha"`. Séparateur de blocs : `\n\n` (couche 3) contre `\n` (couche 5). Résultat : CER = **0,143** pour un candidat parfait sous la vue « texte (lignes) » (une erreur par frontière de bloc). Fan-out : les régions de la page 2 sont lues dans l'**image de la page 1**, sans avertissement. |
| Comportement attendu | Un seul réassemblage qui respecte l'ordre plat sur des régions imbriquées, avec le même séparateur des deux côtés : CER 0 pour un candidat identique. Le fan-out doit refuser un layout multipage avec une seule image, ou recevoir une image par page. |
| Tests existants | `tests/pipeline/test_segmentation_*` et les tests du projecteur : jamais d'ordre imbriqué, et jamais de comparaison entre les deux projecteurs. |
| Cause architecturale | Deux implémentations d'une même règle : `evaluation/projectors.py:30-67` (`_ordered_top_regions` ne résout que les ids **de premier niveau**, `:34` ; `"\n\n".join`, `:67`) et `adapters/layout/to_text.py` (`_page_text` descend dans les feuilles ; `"\n".join`). C'est la dérive que `formats/_region_ids.py` dit avoir corrigée pour les ids. Fan-out : `pipeline/fanout.py:67` `run_region_fanout(page_image: Artifact)` reçoit une seule image pour `for page in layout.pages` (`:101`). |
| Gravité scientifique | Moyenne. Une VT ALTO/PAGE comparée à une sortie de recette « segmentation → lecture → projection » sous la vue « texte (lignes) » est pénalisée de (nombre de blocs − 1)/(nombre de caractères), soit environ 1 point de CER sur une page de presse à 50 blocs et 5 000 caractères. Elle est pénalisée de vraies erreurs d'ordre sous **toutes** les vues dès que la VT PAGE ordonne des régions imbriquées. |

## A1 — `correction_analysis` lit le pool final, pas la cible de la vue

| champ | contenu |
|---|---|
| Affirmation | `correction_analysis` consomme les pools finaux et non l'étape ciblée. |
| Verdict | **confirmé** (trois symptômes). |
| Contre-exemple | Chaîne `ocr « le chat dart » → correction « le chat dort » → refine « le chien dort »`, VT « le chat dort », `analyses="toutes"`. `test_la_analyses_target.py::test_correction_vue_cible_ocr__pas_de_bilan_hors_du_prefixe_evalue`, `::test_correction_vue_cible_correction__lit_la_sortie_de_cette_etape`. Chaîne documentée dans `runner._scored_step` : `ocr → correction → projection` (un RAW_TEXT **après** le CORRECTED_TEXT), `::test_correction_etape_brute_en_aval__le_brut_est_l_entree_du_correcteur`. |
| Comportement actuel | (1) La vue « ocr_seul » porte un bilan de correction, calculé sur `refine`. (2) Sous la vue `target_step="correction"`, le CER vaut **0,0**, mais le bilan affiche `improvement_rate` 0, `regression_rate` 1, `errors_after` 1, `cmer_corrected` 0,231 et une **régression catastrophique** (Δ = 0,147 > 0,10) : c'est le bilan de `refine`. (3) Chaîne avec projection en aval : « brut » = texte final reprojeté, d'où `errors_before` = **0** et `improvement_rate` = **0** ; tout le gain de la correction disparaît. |
| Comportement attendu | Le bilan d'une vue juge la cible de cette vue (« corrigé » = sortie de `target_step`) contre l'**entrée** de cette étape (« brut » = ce qu'elle a consommé), et il est absent d'une vue dont le préfixe ne contient pas de correction. Attendu : (1) absent, (2) amélioration 1/1, 0 erreur après, (3) `errors_before` = 1, amélioration 1/1. |
| Tests existants | `tests/evaluation/test_correction.py::test_through_evaluate_run` : une chaîne à deux étages sans `target_step`, sans étape répétée et sans RAW_TEXT en aval. Rien ne croise vue d'ablation et bilan. |
| Cause architecturale | `evaluation/runner.py:135` `pools = latest_by_type(by_step)`, passé tel quel en `:229`. `correction.py:97` `_text_of` lit le **type** dans le pool, `:119` `_two_stage_pipelines` détecte un CORRECTED_TEXT **n'importe où**. Le contrat `_Outputs = {pipeline: {doc: {type: artifact}}}` a perdu l'étape et la provenance (`inputs_from`). D-276 l'acte : « Calibration, correction et décisions lisent le pool, comme avant ». D-285 n'a ensuite corrigé que la calibration. **Même cause que A2.** |
| Gravité scientifique | **Élevée pour P5h** (campagne d'ablation publiée, fondée sur `target_step`). Le rapport juxtapose sous une même vue un CER de 0 et une « régression catastrophique ». Les chaînes `correction → refine` ne peuvent pas avoir de bilan du premier étage. La chaîne « correction → projection » annonce **zéro** correction utile. |

## A2 — `decisions_analysis` lit le pool final

| champ | contenu |
|---|---|
| Affirmation | `decisions_analysis` consomme le pool final. |
| Verdict | **confirmé**. |
| Contre-exemple | Même chaîne, les deux étapes de correction publient `DECISIONS`. `test_la_analyses_target.py::test_decisions_vue_cible_ocr__pas_de_decisions_hors_du_prefixe`, `::test_decisions_vue_cible_correction__lit_les_decisions_de_cette_etape`. |
| Comportement actuel | La vue « ocr_seul » porte un payload `decisions`. Sous la vue ciblant `correction`, l'échantillon montre `refine.l1` (final_text « le chien dort »). |
| Comportement attendu | Pas de décisions hors du préfixe évalué. Sous la vue ciblant `correction`, les décisions de cette étape. |
| Tests existants | `test_decisions.py` et `test_decisions_review.py` appellent la fonction directement, avec un pool à une seule étape. |
| Cause architecturale | `runner.py:236` `decisions_analysis(view.name, pools)` : la signature ne reçoit même pas la vue, seulement son nom. `decisions.py:84` lit `by_document[doc][DECISIONS]`. Même cause que A1. |
| Gravité scientifique | Moyenne. Lecture qualitative (aucun score), mais elle est attribuée à la mauvaise vue et au mauvais étage. |

## A3 — `economics` : coût du pipeline entier sous une vue de préfixe

| champ | contenu |
|---|---|
| Affirmation | (relevé par la revue du registre) L'économie suit-elle la cible ? |
| Verdict | **partiel**. Le CER suit la vue, mais le coût est celui du pipeline entier. |
| Contre-exemple | `test_la_analyses_target.py::test_economie_vue_cible_ocr__ne_facture_pas_l_etage_llm` : 1 000 jetons d'entrée et 500 de sortie (étage LLM), vue « ocr_seul ». |
| Comportement actuel | La ligne « ocr_seul » a `cer` = 0,083 (OCR) mais `tokens_in` = **1000** et le coût de l'étage LLM. |
| Comportement attendu | Le coût d'un préfixe ne comprend que les étapes du préfixe. |
| Tests existants | Aucun ne combine économie et `target_step`. |
| Cause architecturale | `evaluation/result.py:82` `DocumentUsage` est par (pipeline × document), **sans ventilation par étape**. `runner.py:222` passe tout l'`usage`. On ne peut pas corriger localement sans un usage par étape dans le contrat. |
| Gravité scientifique | Moyenne pour P5h : le front de Pareto coût/CER d'une ablation place « OCR seul » au coût de l'OCR + LLM. |

## A4 — Calibration : étape et multi-ensemble de mots

| champ | contenu |
|---|---|
| Affirmation | La calibration, fondée sur le multi-ensemble des mots de la VT, compte juste un mot mal placé ou répété. |
| Verdict | Étape lue : **réfuté**, elle suit bien `target_step` (`test_calibration__lit_les_confiances_de_l_etape_ciblee`, vert). Multi-ensemble : **confirmé** (choix documenté, mais biaisé). Sans désordre, les deux jugements concordent (`test_calibration_sans_desordre__…`, vert). |
| Contre-exemple | `test_la_calibration.py::test_calibration_mots_permutes__correct_par_alignement` : VT « un deux », jetons « deux »(0,95) « un »(0,95). `::test_calibration_mot_repete_deplace__correct_par_alignement` : VT « de la ville de paris », OCR « de la ville paris de », tout à 0,99 (le 2ᵉ « de » perdu, un « de » inséré en fin). |
| Comportement actuel | ECE = **0,05** au lieu de **0,45** (exactitude 1,0 au lieu de 0,5). ECE = **0,01** au lieu de **0,19** : le « de » inséré est jugé juste parce qu'un « de » de la VT n'a pas encore été consommé. |
| Comportement attendu | Un jeton est juste s'il tombe dans un bloc `equal` d'un **alignement** VT ↔ séquence de jetons (`difflib.SequenceMatcher(autojunk=False)` ici, ou Levenshtein mot à mot comme ocrevalUAtion ou dinglehopper). C'est l'exactitude *de cette prédiction* au sens de Guo et al. 2017. Idéalement, l'alignement se fait **par ligne**, pour ne pas pénaliser comme erreur de reconnaissance une erreur d'ordre de colonnes. Les deux biais du multi-ensemble vont dans le même sens : il **sur-crédite** les insertions et déplacements de mots fréquents, donc il **sous-estime** l'ECE et le MCE d'un moteur surconfiant. |
| Tests existants | `tests/evaluation/test_calibration.py::test_analysis_scores_tokens_against_reference_multiset` **fige** le multi-ensemble (règle D-068). |
| Cause architecturale | `calibration.py:126` `_judge` (consommation gloutonne d'un `Counter`, dans l'ordre des jetons) et `:109` `_reference_words`. Plus profond : `domain/confidence.py` `ConfidenceToken` = `{text, confidence}`, **sans position** (ni ligne ni décalage). Un alignement par ligne est impossible sans enrichir le contrat ; un alignement sur la séquence de jetons est possible localement. `_reference_words` ne lit qu'une VT `RAW_TEXT` : avec une VT ALTO ou PAGE, la calibration est absente. |
| Gravité scientifique | Moyenne. Sur du français, les mots-outils (de, la, le, et) forment une large part des jetons (estimation, non mesurée ici). Toute insertion ou tout déplacement de l'un d'eux est crédité, ce qui pousse l'ECE publié vers le bas et classe mieux un moteur surconfiant. |

## A5 — Collecteurs, inférence, conformité HIPE

| champ | contenu |
|---|---|
| Affirmation | Toutes les analyses du mode détaillé lisent la cible. |
| Verdict | **réfuté** pour les 13 collecteurs, `inference` et `hipe`. |
| Contre-exemple | `test_la_analyses_target.py::test_score_et_collecteurs__suivent_target_step` (vert) : sous « ocr_seul », `document_texts` montre « le chat dart » (l'OCR) et le CER vaut 1/12. |
| Cause | `runner.py` → `_score_document` → `text_context` / `entity_context`, construits sur `_candidate_for(view, …)`. `inference` lit `series`, `hipe` lit les résultats par vue. Réserve : les collecteurs texte ne sont nourris que si la vue déclare une métrique `(RAW_TEXT, RAW_TEXT)`. Une vue de structure seule n'en a aucun (ce n'est pas un défaut). |

Observation non testée ici (couche 6) : une unité dont **une** étape échoue a `by_step` vide (`pipeline/types.py:131` `DocumentExecution.failed`). Sous une vue « OCR seul », l'OCR réussi d'un document dont seul l'étage LLM a échoué est donc traité comme un échec de l'OCR (exclu, ou noté à l'erreur maximale sous `max_error`).

---

## Tableau des analyses (registre réel : `runner.ANALYSES_CONNUES` = `COLLECTEURS` ∪ {calibration, correction, decisions, economics, hipe, inference})

| analyse (`kind`) | artefact lu | cible attendue | conforme ? |
|---|---|---|---|
| diagnostics | `text_context` (candidat de `target_step`) | sortie de `target_step` | oui |
| taxonomy | `text_context` | idem | oui |
| document_hallucination | `text_context` | idem | oui |
| document_texts | `text_context` + CER de la vue | idem | oui (testé) |
| structured_data | `text_context` | idem | oui |
| philology (markers) | `text_context` | idem | oui |
| roman | `text_context` | idem | oui |
| textual_fidelity | `text_context` | idem | oui |
| inter_engine | `text_context` + taxonomy de la même vue | idem | oui |
| word_errors | `text_context` | idem | oui |
| ner | `entity_context` (candidat ENTITIES de la vue) | idem | oui |
| lines | `text_context` (si la vue garde les `\n`) | idem | oui |
| document_lines | `text_context` (si la vue garde les `\n`) | idem | oui |
| calibration | `CONFIDENCES` de `_scored_step` | confiances de `target_step` | oui (testé) ; jugement par multi-ensemble biaisé (A4) |
| inference | `series` de la vue | scores de la vue | oui |
| hipe (conformity) | résultats des vues raw/hipe/heritage | idem | oui |
| economics | CER de la vue **+ `usage` du pipeline entier** | coût du préfixe jusqu'à `target_step` | **non** (A3) |
| correction | **pool** : dernier `RAW_TEXT`, dernier `CORRECTED_TEXT` | brut = entrée de `target_step`, corrigé = sortie de `target_step` | **non** (A1, testé) |
| decisions | **pool** : dernier `DECISIONS` | `DECISIONS` de `target_step` | **non** (A2, testé) |

---

## Sortie exacte de pytest

Commande : `cd <copie figée> && ce-venv/bin/python -m pytest -q -p no:cacheprovider tests/adversarial/layout_analyses -rA`

```
PASSED tests/adversarial/layout_analyses/test_la_analyses_target.py::test_score_et_collecteurs__suivent_target_step
PASSED tests/adversarial/layout_analyses/test_la_analyses_target.py::test_calibration__lit_les_confiances_de_l_etape_ciblee
PASSED tests/adversarial/layout_analyses/test_la_calibration.py::test_calibration_sans_desordre__multiensemble_et_alignement_concordent
PASSED tests/adversarial/layout_analyses/test_la_matching.py::test_ordre_des_regions_hypothese__la_detection_n_en_depend_pas_hors_egalites
PASSED tests/adversarial/layout_analyses/test_la_matching.py::test_permutation_regions_hypothese__detection_inchangee_ordre_de_lecture_mesure
PASSED tests/adversarial/layout_analyses/test_la_matching.py::test_ids_partages_homologues__identite_exacte_conservee
PASSED tests/adversarial/layout_analyses/test_la_reassembly.py::test_fanout__ordre_de_lecture_preserve_au_reassemblage
FAILED tests/adversarial/layout_analyses/test_la_analyses_target.py::test_correction_vue_cible_ocr__pas_de_bilan_hors_du_prefixe_evalue
FAILED tests/adversarial/layout_analyses/test_la_analyses_target.py::test_correction_vue_cible_correction__lit_la_sortie_de_cette_etape
FAILED tests/adversarial/layout_analyses/test_la_analyses_target.py::test_correction_etape_brute_en_aval__le_brut_est_l_entree_du_correcteur
FAILED tests/adversarial/layout_analyses/test_la_analyses_target.py::test_decisions_vue_cible_ocr__pas_de_decisions_hors_du_prefixe
FAILED tests/adversarial/layout_analyses/test_la_analyses_target.py::test_decisions_vue_cible_correction__lit_les_decisions_de_cette_etape
FAILED tests/adversarial/layout_analyses/test_la_analyses_target.py::test_economie_vue_cible_ocr__ne_facture_pas_l_etage_llm
FAILED tests/adversarial/layout_analyses/test_la_calibration.py::test_calibration_mots_permutes__correct_par_alignement
FAILED tests/adversarial/layout_analyses/test_la_calibration.py::test_calibration_mot_repete_deplace__correct_par_alignement
FAILED tests/adversarial/layout_analyses/test_la_matching.py::test_glouton_vs_optimal__la_detection_atteint_l_optimum_global
FAILED tests/adversarial/layout_analyses/test_la_matching.py::test_glouton_vs_optimal__region_cer_suit_l_appariement_optimal
FAILED tests/adversarial/layout_analyses/test_la_matching.py::test_ordre_des_regions_de_reference__la_detection_n_en_depend_pas
FAILED tests/adversarial/layout_analyses/test_la_matching.py::test_ordre_des_regions_hypothese__egalite_d_iou_sans_effet_d_ordre
FAILED tests/adversarial/layout_analyses/test_la_matching.py::test_ids_identiques_non_homologues__appariement_par_geometrie
FAILED tests/adversarial/layout_analyses/test_la_matching.py::test_ids_partiellement_partages__la_region_non_nommee_reste_appariee
FAILED tests/adversarial/layout_analyses/test_la_multipage_ids.py::test_multipage_detection__pas_d_appariement_entre_pages
FAILED tests/adversarial/layout_analyses/test_la_multipage_ids.py::test_multipage_mise_en_page_repetee__region_cer_nul_pour_une_hypothese_parfaite
FAILED tests/adversarial/layout_analyses/test_la_multipage_ids.py::test_multipage_ids_locaux_a_la_page__toutes_les_regions_comptent
FAILED tests/adversarial/layout_analyses/test_la_multipage_ids.py::test_alto_sans_id__appariement_par_geometrie_et_ordre_inverse_detecte
FAILED tests/adversarial/layout_analyses/test_la_reassembly.py::test_ordre_de_lecture_imbrique__la_projection_d_evaluation_le_respecte
FAILED tests/adversarial/layout_analyses/test_la_reassembly.py::test_deux_projections__meme_layout_meme_texte
FAILED tests/adversarial/layout_analyses/test_la_reassembly.py::test_deux_projections__ordre_imbrique_identique
FAILED tests/adversarial/layout_analyses/test_la_reassembly.py::test_fanout_multipage__une_page_n_est_pas_lue_dans_l_image_d_une_autre
FAILED tests/adversarial/layout_analyses/test_la_reassembly.py::test_deux_projections__candidat_parfait_cer_nul_vue_lignes
23 failed, 7 passed in 1.81s
```

---

## Contrats en cause

| contrat | verdict | argument |
|---|---|---|
| Appariement de régions (`metrics/layout.py` : `_greedy_pairs` + `correspondance`) | **à revoir** | Le glouton seul serait **réparable localement** (remplacer `_greedy_pairs` par `linear_sum_assignment` sur la matrice d'IoU seuillée, par page : déjà utilisé dans `flexible.py`). Mais la règle « id d'abord, en bloc, sinon géométrie » est un contrat d'identité erroné. Elle suppose que deux fichiers qui partagent un id partagent un espace de noms, ce que ni le domaine ni les sources (`region_N` synthétisés, `r1…` des segmenteurs) ne garantissent. Le test qui la fige protège des « valeurs déjà publiées » au détriment de leur justesse. Il faut un appariement géométrique par page, avec l'id au plus comme départage ou comme vérification. |
| `CanonicalLayout` multipage (`domain/layout.py`) | **réparable localement** | Le type porte déjà les pages. Il suffit que les métriques apparient à l'intérieur de chaque page et que le domaine (ou les métriques) refuse les ids dupliqués, ou les qualifie par page. Le fan-out doit refuser un layout multipage avec une seule image. |
| Projection `LAYOUT → texte` (deux implémentations, couches 3 et 5) | **réparable localement** | Il faut une seule fonction de réassemblage, celle de couche 5 qui respecte l'ordre plat imbriqué, utilisée des deux côtés, avec un séparateur unique. C'est la même discipline « une règle, une copie » que celle déjà appliquée aux ids. |
| Entrée des analyses autonomes (`runner.pools` → `correction`/`decisions`) | **à revoir** | Le pool `{type: artefact}` efface l'étape et la provenance. Une analyse ne peut donc pas savoir ce qu'une étape a consommé ni respecter `target_step`. Il faut leur passer `by_step` et la vue (comme `_scored_steps` le fait pour la calibration), et lire « brut » sur l'entrée déclarée (`inputs_from`) de l'étape ciblée. C'est indispensable avant une campagne d'ablation P5h. |
| `DocumentUsage` (économie) | **à revoir** | Sans usage par étape dans le contrat, aucun coût de préfixe n'est calculable. L'économie d'une vue d'ablation est donc structurellement fausse, ou doit être explicitement déclarée « coût du pipeline entier ». |
| Calibration (`ConfidenceToken` + jugement par multi-ensemble) | **réparable localement** (en partie) | Aligner la séquence de jetons sur la VT (Levenshtein mot à mot) se fait sans toucher le contrat et supprime le sur-crédit. Un alignement par ligne, qui ne confond pas reconnaissance et ordre de lecture, demande d'ajouter une position (ligne) à `ConfidenceToken`. |
| Collecteurs de vue, inférence, HIPE | **adapté** | Ils lisent le candidat de la vue (`_candidate_for` / `series`), donc la cible. Le témoin le confirme. |
