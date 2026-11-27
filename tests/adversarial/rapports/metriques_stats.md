# Contre-expertise `metriques_stats` — Cinoc @ 04a1c17b

Tests : `tests/adversarial/metriques_stats/` (copie figée) — `ms_support.py` (fabrique de corpus via fichiers + `evaluate_run`), `test_ms_aggregation.py` (affirmation 1), `test_ms_statistics.py` (affirmation 3). Tout passe par `evaluate_run` + registre par défaut ; références = calcul à la main sur ΣTP/ΣFP/ΣFN ou Σnum/Σden, `jiwer`, `scipy`, `numpy`. Aucun monkeypatch.

**Bilan : 21 rouges, 15 verts.** Les deux affirmations sont **confirmées** sur le fond, avec des réfutations nettes sur un sous-ensemble : CER/WER/MER/cMER sont exacts au niveau corpus face à jiwer (hors références vides), les taux de préservation sont exacts, l'ECE est bien calculé sur le pool, le bootstrap rééchantillonne les documents, et `--repeat` n'a pas de cache partagé.

---

## A. Affirmation 1 — contrat mathématique des métriques

### A1. Référence vide : l'hallucination d'une page blanche disparaît du CER, du WER et de `ins_rate`

| champ | contenu |
|---|---|
| Affirmation | Un texte inventé sur une page blanche a un poids nul et peut disparaître du CER global. |
| Verdict | **confirmé** (CER, WER, `ins_rate`, `char_accuracy`, `fca`) ; **réfuté** pour `cmer`, `mer`, `bow_precision`, `unanchored_trigrams` : leur dénominateur contient l'hypothèse. |
| Contre-exemple | page `a` : GT `abcdefghij`, sortie identique ; page `blank` : GT `""`, sortie de 44 car. / 7 mots. `test_ms_aggregation.py::test_reference_vide__hallucination_comptee_au_numerateur[cer|wer|ins_rate|char_accuracy|fca]` ; classement : `::test_reference_vide__pipeline_qui_hallucine_est_classe_apres` ; contrôle vert : `::test_reference_vide__metriques_a_denominateur_hypothese_penalisent[cmer|mer|bow_precision|unanchored_trigrams]` |
| Comportement actuel | Par page : `cer = 1.0`, `support = 0`. Agrégat : **CER 0,0, WER 0,0, ins_rate 0,0, char_accuracy 1,0, fca 1,0**, avec `support = 2`, `expected = 2` (« 2/2 notés » alors que la page ne pèse rien). Classement : le pipeline H, qui invente une page entière, obtient **CER 0,0**. Le pipeline S, silencieux sur la page blanche et avec 1 faute ailleurs, obtient **0,1**. H passe devant. |
| Comportement attendu | La statistique suffisante du CER est (Σ éditions, Σ longueurs de réf.). Le corpus doit valoir 44/10 = **4,4** ; H = 4,4 > S = 0,1. Tout texte inséré est une erreur, quelle que soit la page. |
| Tests existants | `tests/evaluation/test_metrics_text.py::test_cer_weight_is_reference_length` **inscrit le défaut comme voulu** (`réf vide → poids nul → exclue du micro`). `tests/evaluation/test_micro_interval.py::test_zero_weight_documents_weigh_nothing` en fait autant pour l'IC. L'analyse détaillée `document_hallucination` peut signaler le passage, mais pas en mode rapide et jamais dans le chiffre. |
| Cause architecturale | `Observation(value, weight)` (`cinoc/evaluation/metric.py:22`) : la métrique rend un **taux** et un dénominateur, jamais le numérateur. Quand le dénominateur vaut 0, le numérateur ne peut pas être reconstruit (`value × 0 = 0`), d'où le `_error_rate` arbitraire à 1,0 (`metrics/text.py:114`) puis la perte de la page à l'agrégat `micro_ratio` (`inference.py:166`, appelé par `runner.py:307`). `support` compte cette page comme notée. **Une seule cause** pour 5 métriques. `region_cer` et `line_identity_cer` renvoient `None` quand le nombre de caractères de réf. vaut 0 (`metrics/layout.py:116`, `:341`) : un bloc fantôme sur une région sans texte disparaît pareillement (non testé séparément). |
| Gravité scientifique | **Élevée.** Le CER est la métrique de tête et le seul test affiché par le rapport. Les pages blanches sont courantes dans un corpus patrimonial (gardes, versos, planches), et inventer du texte sur une page blanche est un mode d'échec connu des VLM. Sur ces pages, un VLM qui hallucine a le même CER qu'un moteur muet ; s'il est meilleur ailleurs, il passe devant. L'écart publié est **non borné** : il vaut toute la longueur inventée, rapportée à la longueur du corpus. |

### A2. `ner_f1`, `ner_f1_exact` : moyenne pondérée de F1, pas un micro-F1

| champ | contenu |
|---|---|
| Affirmation | Un vrai micro-F1 agrège TP/FP/FN avant le ratio. |
| Verdict | **confirmé**. |
| Contre-exemple | d1 : 1 entité GT trouvée + 9 FP ; d2 : 10 entités GT, toutes trouvées. `test_ms_aggregation.py::test_ner_f1__micro_sur_tp_fp_fn[ner_f1|ner_f1_exact]` |
| Comportement actuel | **0,9256** = (0,1818 × 1 + 1 × 10)/11. Le payload `ner` du **même** `RunResult` donne **0,7097** (vert : `::test_ner_payload__micro_sur_tp_fp_fn`). Deux « F1 NER » contradictoires dans un même résultat. |
| Comportement attendu | F1(ΣTP=11, ΣFP=9, ΣFN=0) = 22/31 = **0,7097** (définition du micro-F1, CoNLL/HIPE). |
| Tests existants | `tests/evaluation/test_ner_runner.py` : un seul document, donc F1 = 1. `test_ner.py::TestEntitiesCollector` teste le collecteur, juste, mais pas le scalaire multi-documents. |
| Cause architecturale | `Observation(value=f1, weight=len(reference.entities))` (`metrics/ner.py:54`, `:78`). Le F1 n'est pas linéaire en (num, den) : **aucun poids** ne permet à Σ(v·w)/Σw de le reconstruire. Même cause que A1 : le contrat ne transporte pas les statistiques suffisantes. Ces statistiques existent pourtant à côté, dans `NerCounts`. |
| Gravité scientifique | **Élevée pour la NER.** L'écart vaut ici +0,22. Le biais est systématique : les FP d'un document à peu d'entités sont noyés par le poids des documents riches. Un extracteur bavard est sur-noté. |

### A3. `ner_f1` : les faux positifs d'un document sans entité GT sont ignorés

| champ | contenu |
|---|---|
| Verdict | **confirmé**. |
| Contre-exemple | d1 : 2 entités GT trouvées ; d2 : GT sans entité, 8 entités inventées. `test_ms_aggregation.py::test_ner_f1__faux_positifs_sur_document_sans_entite_gt` |
| Comportement actuel | **1,0**. Le document d2 vaut `None` (`metrics/ner.py:51`) et sort de la moyenne. |
| Comportement attendu | F1(2, 8, 0) = **1/3**. Un FP est un FP, même sur une page sans entité. |
| Cause architecturale | Même contrat : un document sans dénominateur (Σ entités GT = 0) n'a aucune façon de transmettre son numérateur d'erreurs (FP). |
| Gravité scientifique | Élevée : un extracteur qui invente des entités sur des pages sans nom propre obtient un F1 parfait. |

### A4. Mode détaillé : un label absent de la GT fait planter `evaluate_run` (défaut découvert en route)

| champ | contenu |
|---|---|
| Verdict | **confirmé** (non annoncé par le mainteneur). |
| Contre-exemple | GT `PER` seul ; la sortie contient `PER` (juste) + `LOC` (FP). `analyses="toutes"`. `test_ms_aggregation.py::test_ner_payload__label_absent_de_la_gt__ne_plante_pas` |
| Comportement actuel | `ValidationError: EntityCategoryScore.support ≥ 1`, et **tout le run** tombe. |
| Comportement attendu | Une ligne `LOC` avec TP 0, FP 1, rappel non défini ; le run continue. |
| Tests existants | `test_ner.py::TestEntitiesCollector` n'emploie que des labels présents dans la GT. |
| Cause architecturale | `EntityCategoryScore.support: int = Field(ge=1)` (`cinoc/evaluation/analysis.py:960`), alimenté par `ctp + cfn` (`cinoc/evaluation/ner.py:339`), qui vaut 0 pour une catégorie présente seulement en FP. |
| Gravité scientifique | Pas de chiffre faux, mais le seul F1 NER juste (le payload) est **inatteignable** dès qu'un modèle NER sort un label hors du schéma de la GT, ce qui arrive couramment entre jeux d'étiquettes. |

### A5. `region_detection` : moyenne pondérée de F1

| champ | contenu |
|---|---|
| Verdict | **confirmé**. |
| Contre-exemple | d1 : 1 région GT trouvée + 9 fantômes ; d2 : 10 régions GT, toutes trouvées. `test_ms_aggregation.py::test_region_detection__micro_sur_tp_fp_fn` |
| Comportement actuel | **0,9256**. |
| Comportement attendu | F1(11, 9, 0) = **0,7097**. |
| Tests existants | `tests/evaluation/test_region_detection.py` : un seul document par test, donc pas d'agrégat. |
| Cause architecturale | `metrics/layout.py:277` : `Observation(f1, weight=len(ref_boxes))`, même cause que A2. Les régions fantômes d'une page à peu de régions sont noyées. |
| Gravité scientifique | Moyenne à élevée pour comparer des segmenteurs. Une sur-segmentation localisée est sous-pénalisée : +0,22 ici. |

### A6. `reading_order_tau` : poids = nombre de blocs, alors que le dénominateur est le nombre de paires

| champ | contenu |
|---|---|
| Verdict | **confirmé**. |
| Contre-exemple | d1 : 2 blocs inversés (1 paire discordante sur 1) ; d2 : 10 blocs dans l'ordre (0 sur 45). `test_ms_aggregation.py::test_reading_order_tau__micro_sur_paires` |
| Comportement actuel | **0,1667** = (1 × 2 + 0 × 10)/12. |
| Comportement attendu | Σ discordantes / Σ paires = 1/46 = **0,0217**. Le docstring d'`Observation` dit que `weight` est le **dénominateur** ; ici il ne l'est pas, et le chiffre n'est ni micro, ni macro (0,5). |
| Tests existants | `tests/evaluation/test_reading_order.py` teste `kendall_distance` page par page, sans agrégat. |
| Cause architecturale | `metrics/layout.py:419` (`weight=communs`). Le contrat laisse chaque métrique choisir un poids sans le vérifier contre son dénominateur. |
| Gravité scientifique | Moyenne : un facteur 7,7 sur ce cas. Les petites pages sont sur-pondérées, de façon quadratique. |

### A7. `bow_f1` : moyenne pondérée de F1 (choix documenté)

| champ | contenu |
|---|---|
| Verdict | **confirmé** (documenté dans le docstring : « pas le F1 micro exact, choix documenté »). `bow_precision` et `bow_recall` sont **exacts** : vert, `::test_bow_precision_recall__micro_sur_comptes`. |
| Contre-exemple | d1 : 1 mot GT + 9 parasites ; d2 : 10 mots justes. `test_ms_aggregation.py::test_bow_f1__micro_sur_tp_hyp_ref` |
| Comportement actuel / attendu | **0,9256** contre F1(Σtp=11, Σ|hyp|=20, Σ|réf|=11) = **0,7097**. Le F1 affiché ne correspond pas aux P et R affichés à côté : 2·0,55·1/1,55 = 0,7097. |
| Cause architecturale | `metrics/bow.py:82`, même cause que A2. |
| Gravité scientifique | Moyenne : `bow_f1` figure dans le profil `standard` (par défaut) et contredit les colonnes P et R voisines. |

### A8. `char_accuracy` / `word_accuracy` / `fca` : plancher par page, donc ≠ 1 − CER corpus

| champ | contenu |
|---|---|
| Verdict | **confirmé** (documenté : « sauf plancher 0 quand un doc a CER > 1 »). |
| Contre-exemple | d1 : GT `ab`, sortie `000000` (CER 3) ; d2 : 10 car. justes. `test_ms_aggregation.py::test_char_accuracy__vaut_un_moins_cer_corpus` |
| Comportement actuel | CER corpus 0,5 ; **char_accuracy 0,833**. |
| Comportement attendu | max(0, 1 − 0,5) = **0,5**. La borne s'applique au corpus, pas à chaque page avant l'agrégat. |
| Cause architecturale | `metrics/text.py:246` : `max(0, 1 − rate)` par page. Le plancher **non linéaire** est appliqué avant l'agrégat linéaire. Pour `fca` (`metrics/flexible.py:95`), le plancher par page s'ajoute au poids 0 de la page blanche (A1). |
| Gravité scientifique | Élevée sur sorties génératives (CER > 1 sur une page qui boucle ou duplique) : l'exactitude affichée est surestimée de toute la part des erreurs au-delà de 100 %. |

### A9. `line_identity_cer` : les lignes fantômes ne comptent pas

| champ | contenu |
|---|---|
| Verdict | **confirmé** (défaut découvert en route, voisin d'A1). |
| Contre-exemple | GT : ligne `l1` ; sortie : `l1` identique + `l2` fantôme de 10 car. `test_ms_aggregation.py::test_line_identity_cer__ligne_fantome_comptee_en_insertion` |
| Comportement actuel / attendu | **0,0** ; attendu **1,0** = 10 insertions / 10. Convention de `region_cer` depuis D-288 : le bloc fantôme compte en insertions. |
| Cause architecturale | `metrics/layout.py:312` ne parcourt que les lignes de référence : le numérateur oublie les insertions. |
| Gravité scientifique | Moyenne : les lignes dupliquées ou inventées par une étape aval sont invisibles. |

### A10. Contrôles verts (affirmation réfutée ou déjà traitée)

| point | test | résultat |
|---|---|---|
| CER, WER, MER, cMER micro = jiwer au niveau corpus (3 docs inégaux) | `::test_taux_additifs__parite_corpus_jiwer` | exact. Le micro est juste quand la statistique est (num, den) et den > 0. |
| CER non borné ; cMER dans [0, 1] | `::test_cer_borne__peut_depasser_un_et_cmer_borne` | CER 3,0 (correct par définition), cMER 1,0. |
| Taux de préservation (`diacritic_err`, et par construction `mufi_err`, `hcpr`) | `::test_preservation__micro_sur_comptes` | 1/5, exact. |
| ECE/MCE sur jetons **poolés** | `::test_calibration__ece_sur_jetons_poolés` | ECE = 0,1167 = \|10/12 − 0,95\|. Ce n'est pas une moyenne d'ECE par page : juste. |
| Exhaustivité de l'audit | `::test_registre__toutes_les_metriques_sont_auditees` | 29 métriques par-document au registre réel (`metric_specs()`), toutes au tableau ci-dessous. |

---

## B. Affirmation 3 — statistiques

### B1. Le test « inter-moteurs (CER) » ne teste pas le CER affiché, et peut le contredire

| champ | contenu |
|---|---|
| Affirmation | Wilcoxon et Friedman ne testent pas directement la différence du ratio micro affiché. |
| Verdict | **confirmé**. |
| Contre-exemple | 12 petites pages (20 car.) : A parfait, B 2 fautes ; 1 grande page (2 000 car.) : A 400 fautes, B parfait. `test_ms_statistics.py::test_test_omnibus__meme_sens_que_le_cer_micro_affiche`, `::test_test_omnibus__p_du_ratio_micro_par_permutation_appariee` |
| Comportement actuel | Tableau (micro) : **A 0,179, B 0,011**, donc B est meilleur. Payload : Wilcoxon p = 0,0195, p Holm = 0,0195 < 0,05, **rangs moyens A 1,08 / B 1,92**, donc A est meilleur. Le rapport (`reports/sections/key_measures.py:320`) écrit sous le tableau : « Test inter-moteurs (CER) — Wilcoxon … → différence **significative** entre les deux moteurs », **sans sens** et sans dire que le test porte sur les CER par page non pondérés. Les IC marginaux affichés se chevauchent (A [0,000 ; 0,194], B [0,003 ; 0,100]). |
| Comportement attendu | Le test associé au chiffre doit tester ce chiffre : un test de permutation appariée par document sur ΔCER micro, ou un IC bootstrap apparié de Δ. Référence indépendante (permutation exacte, 2¹³ échanges) : **p = 1,0**, car Δmicro repose entièrement sur une page. Sinon, le rapport doit nommer l'estimande (« médiane des écarts de CER par page ») et son sens. |
| Tests existants | `test_inference.py` et `test_inference_scipy_parity.py` vérifient la parité avec scipy (5 000 tirages), donc que le test est bien calculé, mais jamais ce qu'il teste par rapport au chiffre du tableau. |
| Cause architecturale | `omnibus_test` (`inference.py:108`, `stats.wilcoxon` l. 129) reçoit les `value` par page sans les poids, que `_inference_entries` (`runner.py:277`) transmet pourtant. Le payload n'a pas de champ « estimande ». Le rapport juxtapose l'agrégat micro et un test de rangs non pondéré sous le même nom. |
| Gravité scientifique | **Élevée.** Les pages de tailles très inégales sont la norme (registre vs journal). Le rapport peut afficher « significatif » à côté d'un classement que le test contredit, ou au contraire valider un écart micro porté par une seule page. Le verdict de significativité ne se transfère pas au chiffre publié. |

### B2. Pas d'intervalle apparié sur la différence

| champ | contenu |
|---|---|
| Verdict | **confirmé**. |
| Contre-exemple | 30 pages de difficulté très variable ; B fait toujours exactement 1 faute de plus que A (sur 100 car.). `test_ms_statistics.py::test_intervalles__ic_apparie_sur_la_difference_micro` |
| Comportement actuel | IC **marginaux** seulement : A 0,285 [0,224 ; 0,345], B 0,295 [0,234 ; 0,355]. Ils se chevauchent presque entièrement. Wilcoxon p = 8·10⁻⁷. Aucun champ du payload ne porte (a, b, lower, upper). |
| Comportement attendu | IC bootstrap **apparié** (mêmes documents tirés pour A et B) de ΔCER micro. Référence numpy : Δ = 0,01 constant, IC [0,01 ; 0,01], qui exclut 0. |
| Cause architecturale | `_intervals` (`inference.py:242`) : un `micro_ratio_ci` par pipeline, chacun sur ses propres documents. `InferencePayload` n'a pas de type « différence ». |
| Gravité scientifique | Moyenne : le test est juste ici. Mais l'unique incertitude chiffrée sur l'écart, celle que le lecteur voit (les IC du dot plot), suggère « pas de différence » quand la différence est certaine. Elle ne mesure pas l'écart. |

### B3. Données manquantes non aléatoires : sous la politique par défaut, l'échec sur la page difficile fait gagner

| champ | contenu |
|---|---|
| Verdict | **confirmé** sous le défaut `failure_policy="exclude"` (`domain/evaluation.py:271`, arbitrage A3) ; **réfuté** sous `max_error` (vert, `::test_echec_non_aleatoire__politique_max_error_penalise` : A = 1 035/1 700 > B = 528/1 700). |
| Contre-exemple | 7 pages faciles (100 car.) : A 5 fautes, B 4 ; 1 page difficile (1 000 car.) : A échoue, B 500 fautes. `test_ms_statistics.py::test_echec_non_aleatoire__classement_sur_documents_communs`, `::test_intervalles__meme_documents_que_le_test` |
| Comportement actuel | Tableau : **A 0,050 (7/8), B 0,311 (8/8)**, A devant. Test : Wilcoxon sur 7 cas complets, p = 0,0156, rang moyen **B** meilleur → « différence significative ». IC : A sur 7 documents [0,05 ; 0,05], B sur 8 [0,04 ; 0,43]. Trois objets, trois ensembles de documents : le test et l'IC de A portent sur 7 pages, l'IC et l'agrégat de B sur 8. |
| Comportement attendu | Les chiffres mis en regard doivent porter sur le **même support** (cas complets), ou l'échec doit être pénalisé. Sur les pages communes, A = 0,05 > B = 0,04. |
| Tests existants | D-275 documente le choix « IC marginaux » et affiche « 7/8 ». `test_inference.py::test_omnibus_drops_incomplete_documents` vérifie l'exclusion, pas la comparabilité. |
| Cause architecturale | `_aggregate` (`runner.py:307`) agrège chaque pipeline sur ses propres documents notés ; `omnibus_test` travaille sur les cas complets ; `_intervals` sur les documents marginaux. Rien dans le contrat n'impose un support commun à ce qui est comparé. |
| Gravité scientifique | **Élevée.** Un moteur qui expire, refuse ou tronque précisément sur les pages difficiles (le cas typique d'un VLM : page dense, sortie trop longue) obtient, par défaut, un meilleur CER que celui qui les traite. Le « 7/8 » est affiché, mais le classement du tableau reste trompeur. |

### B4. Unité de rééchantillonnage, grappes, répétitions

| point | verdict | test | détail |
|---|---|---|---|
| Bootstrap par document (et non par caractère) | **réfuté** (correct) | `::test_bootstrap__unite_de_reechantillonnage_le_document` (vert) | À 2 documents, IC = [0,1 ; 0,5], les atomes {d1,d1} et {d2,d2}. Un bootstrap par caractère serait étroit. |
| Grappes documentaires (pages d'un même manuscrit) | **confirmé**, test structurel | `::test_bootstrap__grappes_documentaires_declarables` (rouge) | Ni `micro_ratio_ci` ni `DocumentRef` (`id`, `image_uri`, `ground_truths`, `metadata`) n'ont de notion de grappe. L'IC suppose des pages indépendantes : sur un corpus de N pages tirées de quelques manuscrits, il est **trop étroit**, d'un facteur qui dépend de la corrélation intra-manuscrit (non chiffrable ici). `stratum` est une strate, pas une grappe. |
| `--repeat` : cache partagé | **réfuté** | `::test_repetitions__archives_disjointes` (vert) | `repetition_dir` donne à chaque répétition une archive neuve. |
| `--repeat` : indépendance des répétitions | **partiel**, non testable ici (appels facturés) | — | Chaque répétition rejoue `temperature=0`, `seed=0` (`adapters/llm/_base.py:139`) : la « fourchette » (`app/variance.py:70`, min / médiane / max et étendue relative, pas une variance) mesure le **non-déterminisme résiduel du fournisseur**, pas une variabilité d'échantillonnage. Elle vaut 0 pour tout moteur local déterministe. Elle n'a aucun rapport avec l'incertitude sur le corpus (IC bootstrap), et le rapport ne porte que le dernier run. C'est conforme à ce que le module annonce (« mesure le dispositif »), mais cette fourchette ne doit pas être lue comme une erreur type. |

---

## C. Tableau récapitulatif — toutes métriques (registre réel, 29 + 1 inter-moteurs)

« Correcte ? » = l'agrégat publié est-il égal à la métrique calculée au niveau corpus sur ses statistiques suffisantes ?

| métrique | domaine | bornes | statistique suffisante correcte | agrégation actuelle (Σ v·w / Σ w, w =) | correcte ? |
|---|---|---|---|---|---|
| `cer` | texte, car. | [0, ∞) | (Σ éditions, Σ \|réf\|) | \|réf\| ; réf. vide → v = 1, w = 0 | **non** (réf. vide, A1) ; oui sinon |
| `cer_diplo` | texte, car. | [0, ∞) | idem après repli | \|réf normalisée\| | **non** (même cas que A1) |
| `wer` | texte, mot | [0, ∞) | (Σ éditions mot, Σ mots réf.) | mots réf. | **non** (A1) ; oui sinon (jiwer) |
| `mer` | texte, mot | [0, 1] | (Σ S+D+I, Σ H+S+D+I) | H+S+D+I | **oui** (jiwer) |
| `cmer` | texte, car. | [0, 1] | (Σ S+D+I, Σ H+S+D+I) | H+S+D+I | **oui** (jiwer) |
| `del_rate` | texte, mot | [0, 1] | (Σ D, Σ mots réf.) | mots réf. | oui (D = 0 sur réf. vide) |
| `ins_rate` | texte, mot | [0, ∞) | (Σ I, Σ mots réf.) | mots réf. ; réf. vide → w = 0 | **non** (A1 : l'hallucination sur page blanche disparaît) |
| `char_accuracy` | texte, car. | [0, 1] | 1 − CER corpus, plancher sur le corpus | max(0, 1 − CER) par page, w = \|réf\| | **non** (A8 + A1) |
| `word_accuracy` | texte, mot | [0, 1] | 1 − WER corpus, plancher sur le corpus | max(0, 1 − WER) par page | **non** (même cause qu'A8) |
| `fca` | texte, car. | [0, 1] | (Σ coût d'appariement, Σ car. réf.), plancher sur le corpus | plancher par page, réf. vide → w = 0 | **non** (A1, A8) |
| `bow_precision` | texte, mot | [0, 1] | (Σ tp, Σ \|hyp\|) | \|hyp\| | **oui** |
| `bow_recall` | texte, mot | [0, 1] | (Σ tp, Σ \|réf\|) | \|réf\| | **oui** |
| `bow_f1` | texte, mot | [0, 1] | (Σ tp, Σ \|hyp\|, Σ \|réf\|) → F1 | F1 par page, w = \|réf\| | **non** (A7, documenté) |
| `searchability` | texte, mot | [0, 1] | (Σ retrouvés, Σ mots réf.) | mots réf. ; réf. vide → `None` | oui (un rappel, pas de FP par construction) |
| `unanchored_trigrams` | texte, trigramme | [0, 1] | (Σ non ancrés, Σ trigrammes hyp.) | trigrammes hyp. | **oui** |
| `diacritic_err` | texte, car. | [0, 1] | (Σ mal lus, Σ cibles réf.) | cibles réf. | **oui** (test vert) |
| `mufi_err` | texte, car. | [0, 1] | idem | idem | oui (même moteur `preservation_counts`) |
| `hcpr` | texte, car. | [0, 1] | (Σ préservés, Σ cibles réf.) | idem | oui (même moteur) |
| `air` | texte, car. | [0, 1] | (Σ insérés, Σ cibles hyp.) | cibles hyp. | oui (lecture du code) |
| `numseq_strict` | texte, séquence | [0, 1] | (Σ restitués, Σ séquences GT) | séquences GT | oui (rappel seul, insertions non comptées par conception) |
| `numseq_value` | texte, séquence | [0, 1] | idem | idem | oui (idem) |
| `ner_f1` | entités | [0, 1] | (Σ TP, Σ FP, Σ FN) → F1 | F1 par doc, w = \|GT\| ; GT sans entité → `None` | **non** (A2, A3) ; payload `ner` juste, mais plante (A4) |
| `ner_f1_exact` | entités | [0, 1] | (Σ TP_exact, Σ FP + mal écrits, Σ FN + mal écrits) | idem | **non** (A2) |
| `region_detection` | layout, région | [0, 1] | (Σ TP, Σ \|hyp\|, Σ \|réf\|) → F1 | F1 par page, w = \|réf\| | **non** (A5) |
| `region_cer` | layout, car. | [0, ∞) | (Σ éditions + fantômes, Σ car. réf.) | car. réf. ; 0 car. réf. → `None` | oui si car. réf. > 0 ; **non** sinon (cause d'A1, non testé) |
| `line_identity_cer` | layout, car. | [0, ∞) | (Σ éditions **+ lignes fantômes**, Σ car. réf.) | numérateur sans insertions | **non** (A9) |
| `line_identity_coverage` | layout, ligne | [0, 1] | (Σ retrouvées, Σ lignes réf.) | lignes réf. | oui |
| `reading_order_tau` | layout, région | [0, 1] | (Σ paires discordantes, Σ paires) | w = nb de blocs communs | **non** (A6) |
| `reading_order_coverage` | layout, région | [0, 1] | (Σ ordonnés, Σ blocs réf.) | blocs réf. | oui |
| `significance_p` (inter-moteurs) | séries par doc | [0, 1] | — (test) | Wilcoxon/Friedman sur `value` **non pondérées**, cas complets | **ne teste pas** le chiffre affiché (B1) |
| ECE / MCE (analyse, hors registre) | jetons | [0, 1] | jetons poolés par bin | jetons poolés | **oui** (test vert) |

Sur les 29 métriques par-document : **15 agrégées correctement**, 14 non. Elles se répartissent en quatre causes : référence vide, statistique non linéaire, poids qui n'est pas le dénominateur, numérateur incomplet. Elles se ramènent toutes au même contrat.

---

## Sortie de pytest

```
$ cd contre-expertise && ce-venv/bin/python -m pytest -q -p no:cacheprovider tests/adversarial/metriques_stats
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_reference_vide__hallucination_comptee_au_numerateur[cer-4.4]
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_reference_vide__hallucination_comptee_au_numerateur[wer-7.0]
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_reference_vide__hallucination_comptee_au_numerateur[ins_rate-7.0]
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_reference_vide__hallucination_comptee_au_numerateur[char_accuracy-0.0]
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_reference_vide__hallucination_comptee_au_numerateur[fca-0.0]
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_reference_vide__pipeline_qui_hallucine_est_classe_apres
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_ner_f1__micro_sur_tp_fp_fn[ner_f1]
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_ner_f1__micro_sur_tp_fp_fn[ner_f1_exact]
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_ner_f1__faux_positifs_sur_document_sans_entite_gt
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_ner_payload__label_absent_de_la_gt__ne_plante_pas
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_region_detection__micro_sur_tp_fp_fn
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_reading_order_tau__micro_sur_paires
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_bow_f1__micro_sur_tp_hyp_ref
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_char_accuracy__vaut_un_moins_cer_corpus
FAILED tests/adversarial/metriques_stats/test_ms_aggregation.py::test_line_identity_cer__ligne_fantome_comptee_en_insertion
FAILED tests/adversarial/metriques_stats/test_ms_statistics.py::test_test_omnibus__meme_sens_que_le_cer_micro_affiche
FAILED tests/adversarial/metriques_stats/test_ms_statistics.py::test_test_omnibus__p_du_ratio_micro_par_permutation_appariee
FAILED tests/adversarial/metriques_stats/test_ms_statistics.py::test_intervalles__ic_apparie_sur_la_difference_micro
FAILED tests/adversarial/metriques_stats/test_ms_statistics.py::test_echec_non_aleatoire__classement_sur_documents_communs
FAILED tests/adversarial/metriques_stats/test_ms_statistics.py::test_intervalles__meme_documents_que_le_test
FAILED tests/adversarial/metriques_stats/test_ms_statistics.py::test_bootstrap__grappes_documentaires_declarables
21 failed, 15 passed in 14.21s
```

Verts (15) : `metriques_a_denominateur_hypothese_penalisent` ×4, `ner_payload__micro_sur_tp_fp_fn`, `bow_precision_recall__micro_sur_comptes`, `cer_borne__peut_depasser_un_et_cmer_borne`, `taux_additifs__parite_corpus_jiwer`, `preservation__micro_sur_comptes`, `calibration__ece_sur_jetons_poolés`, `registre__toutes_les_metriques_sont_auditees`, `ratio_de_comptes__substitutions_controlees`, `echec_non_aleatoire__politique_max_error_penalise`, `bootstrap__unite_de_reechantillonnage_le_document`, `repetitions__archives_disjointes`.

---

## Contrats en cause

- **`Observation(value, weight)` + agrégat Σ(v·w)/Σw (`evaluation/metric.py:22`, `runner.py:307`, `inference.py:166`) — à revoir.** Le type transporte un ratio déjà calculé et un poids, jamais les statistiques suffisantes. Il ne peut donc représenter ni un numérateur sur dénominateur nul (A1, A3), ni un ratio non linéaire comme le F1 (A2, A5, A7), ni une borne qui s'applique au corpus (A8). Il ne vérifie pas non plus que le poids est bien le dénominateur (A6). La forme qui couvre les 29 métriques est une observation de **comptes additifs** (ex. `counts: Mapping[str, int]`) plus une fonction de finalisation par métrique `f(Σ counts) → value`, appliquée identiquement à la page et au corpus. Le bootstrap rééchantillonne alors ces comptes. Ce n'est pas réparable localement : chaque correctif métrique par métrique (choisir un autre poids) reste faux pour le F1, quel que soit le poids.
- **Inférence (`inference.py:108`, `:242`, payload `InferencePayload`) — réparable localement.** Le bootstrap par document est juste et les comptes par document arrivent déjà au runner. Il suffit d'ajouter un test, ou un IC apparié, **sur la différence du ratio micro** (permutation ou bootstrap apparié des comptes, sur les cas complets), d'imposer le même support aux agrégats, aux IC et aux tests mis en regard, et de nommer l'estimande du Wilcoxon/Friedman dans le payload et le rapport. Une clé de grappe facultative sur `DocumentRef` (bootstrap par grappe) relève de la même retouche.
- **Politique d'échec (`domain/evaluation.py:271`) — adaptée dans son mécanisme, inadaptée par défaut pour un classement.** `max_error` fait ce qu'il faut ; mais `exclude` par défaut, combiné à des agrégats sur supports différents, récompense l'échec non aléatoire. Le « n notés / n attendus » le montre sans l'empêcher.
- **Payload NER (`analysis.py:960`) — réparable localement** (`support ≥ 0`, ou rappel indéfini pour une catégorie sans GT).
