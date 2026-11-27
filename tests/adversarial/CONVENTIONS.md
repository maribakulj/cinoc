# Dossier d'arbitrage : les conventions derrière les 39 tests « discutables »

Ce dossier fait suite à la contre-expertise au commit `04a1c17b` (`README.md` de ce dossier). Il ne décide rien et ne corrige rien.

**Périmètre.** Ce dossier couvre les 39 tests rouges que la relecture indépendante a classés « valides mais discutables ». Pour chacun, la convention dont dépend l'attendu exact est identifiée. Un test peut dépendre de plusieurs conventions : il est marqué avec la principale, et sa fiche cite les autres. Les 51 tests « valides » ne sont cités ici que lorsqu'une convention change leur attendu (voir § Tensions, T1).

**Marquage** (`tests/adversarial/conftest.py`) : `@pytest.mark.valide` ou `@pytest.mark.discutable("Cxx-…")`. L'argument est l'identifiant de la fiche. Les verts ne sont pas marqués. Aucune assertion ni aucun attendu n'a été modifié : seuls des décorateurs ont été ajoutés, et six paramètres ont été enveloppés dans `pytest.param(..., marks=…)`.

```
python -m pytest -q -p no:cacheprovider tests/adversarial -m valide      → 51 failed, 94 deselected
python -m pytest -q -p no:cacheprovider tests/adversarial -m discutable  → 39 failed, 106 deselected
python -m pytest -q -p no:cacheprovider tests/adversarial -m "not valide and not discutable" → 55 passed
```

**Chiffres réels.** Ils sont recalculés hors ligne à partir des deux `RunResult` commités (`campaigns/2026-11-26-reference/*-sans-cle.run_result.json`, vue `texte`, CER). Les erreurs par page sont reconstituées par `valeur × support`. Les bootstraps comptent 10 000 tirages, la permutation 200 000 échanges de signe, avec une graine fixe. Ces chiffres ne sont pas citables, pour la même raison que la campagne : elle n'est pas publiée.

**Statuts.**
- **tranchée** : l'arbitrage fixe l'attendu. Il ne reste qu'une modalité de mise en œuvre, sans effet sur ce que le test doit constater.
- **tranchée en partie** : l'arbitrage fixe le principe, mais un choix résiduel change l'attendu du test.
- **ouverte** : aucun arbitrage ne s'applique.

---

## Tableau récapitulatif

| # | Convention | Tests discutables (nb) | Arbitrage | Statut | Options (fiche) | Recommandation (non décidée) |
|---|---|---|---|---|---|---|
| C01 | CER/WER/`ins_rate` sur référence vide | `reference_vide_nentre_pas_dans_le_test_apparie` (1) ; liés V : `hallucination…[cer, wer, ins_rate]`, `pipeline_qui_hallucine`, `reference_vide_nest_pas_comptee_notee` | 2, 3, 1 | tranchée en partie | comptes au corpus · exclusion · 1,0 par page · ∞ par page · normalisation par max(\|réf\|, \|hyp\|) | comptes au corpus + statut « référence vide » par page |
| C02 | Plancher des exactitudes (`char_accuracy`, `word_accuracy`, `fca`) | `hallucination…[char_accuracy]`, `[fca]`, `char_accuracy__vaut_un_moins_cer_corpus` (3) | 1, 2 | tranchée en partie | plancher au corpus · sans plancher (ISRI) · plancher par page (actuel) · macro | plancher au corpus (micro) + macro publié à part |
| C03 | Poids et unité de `reading_order_tau` | `reading_order_tau__micro_sur_paires` (1) | 1, 2 | tranchée en partie | paires (micro) · macro · blocs (actuel) · mesure par bloc (autre nom) | paires + macro |
| C04 | Lignes fantômes dans `line_identity_cer` | `line_identity_cer__ligne_fantome…` (1) | — | **ouverte** | insertions comptées · lignes appariées seules · deux métriques nommées | insertions comptées (cohérent avec D-288) |
| C05 | Estimande des tests omnibus (Demšar par document contre ratio micro) | `test_omnibus__meme_sens…`, `test_omnibus__p_du_ratio_micro…` (2) | 1 | tranchée | Wilcoxon/Friedman par document · permutation appariée du Δ micro · les deux, nommés | (arbitrage 1 : les deux, nommés) ; **attendus à reformuler** |
| C06 | IC marginaux contre IC appariés ; support des IC | `intervalles__ic_apparie…`, `intervalles__meme_documents…` (2) | 1, 8 | tranchée | marginaux seuls · Δ apparié sur le support commun · les deux | (les deux) ; `meme_documents` à reformuler |
| C07 | Politique d'échec par défaut et support du classement | `echec_non_aleatoire__classement…` (1) | 8 | tranchée | `exclude` + agrégat marginal · cas complets · imputation · couverture + conditionnel + support commun | (le dernier) ; attendu à recibler |
| C08 | Sémantique de `max_error` (imputation d'un échec) | `max_error__un_echec_ne_note_jamais_mieux…`, `max_error__…page_vide[ins_rate]` (2) | 8 | tranchée | 0/1 par `higher_is_better` (refusé) · page vide · pire observée · borne déclarée · aucune imputation | aucune imputation par défaut ; « page vide » comme sensibilité nommée |
| C09 | Grappes documentaires | `bootstrap__grappes_documentaires_declarables` (1) | 1 | tranchée en partie | bootstrap par document · par grappe · à deux niveaux · peu de grappes : non estimable ou bootstrap sauvage | grappe déclarée, bootstrap par grappe, « non estimable » sous un seuil |
| C10 | Appariement de détection : glouton contre optimal | `glouton_vs_optimal__…` (2) | 6 | tranchée | glouton par référence (actuel) · glouton COCO/VOC · hongrois 1-1 · PRImA (fusions/scissions) | (hongrois + comptes de fusions/scissions) |
| C11 | Calibration : jugement d'un jeton | `calibration_mots_permutes…`, `calibration_mot_repete…` (2) | — | **ouverte** | multi-ensemble (actuel) · alignement LCS · Levenshtein mot à mot · position · géométrie | alignement qui maximise les correspondances (LCS), départage déclaré |
| C12 | Granularité étape : issue, coût de préfixe, reprise | `echec_partiel__lamont_reussi…`, `echec_partiel__la_reprise…`, `economie_vue_cible_ocr…` (3) | 4 (+5, 7) | tranchée | — ; reprise : clé par unité · par préfixe d'étapes · par unité avec étapes conservées pour la seule renotation | reprise par préfixe d'étapes |
| C13 | Non-mesure typée (fan-out vide, GT illisible) | `fanout_sans_aucune_region…`, `gt_referencee_mais_absente…` (2) | 3 | tranchée | hypothèse vide notée comme texte vide · « exécution partielle », attendue non notée ; GT : refus avant exécution · statut par document | refus avant exécution si détectable, sinon statut |
| C14 | Archive scellée : intégrité et immuabilité | `a7_octet…`, `a7_index_json_valide…`, `a7_image_partagee…`, `a7_archive_publiee…` (4) | 5 | tranchée | format : BagIt · RO-Crate · OCFL · RO-Crate dans BagIt (« à étudier ») | BagIt + métadonnées RO-Crate ; OCFL si l'archive doit avoir des versions |
| C15 | Portabilité de l'archive : images | `a7_relecture_offline_image_distante…`, `a7_…serveur_d_images_eteint…`, `a7_archive_seule…` (3) | 5, 7 | tranchée | octets d'image dans l'archive · empreinte + référence épinglée seulement | empreinte obligatoire, octets facultatifs (licence) |
| C16 | Fan-out sur un layout multipage avec une seule image | `fanout_multipage__…` (1) | (6, indirect) | **ouverte** | une image par page · image partagée avec décalages déclarés · refus typé | refus typé en 1.0 |
| C17 | Identité d'étape : version déclarée contre empreinte automatique | `version_manuelle__brique_modifiee…`, `identite_saknussemm__prompt_et_temperature…` (2) | 7 | tranchée en partie | version déclarée (refusée) · empreinte des sources · garde CI · réglages effectifs déclarés | empreinte des sources + réglages effectifs ; **tests à reformuler** |
| C18 | Provenance par unité (`served_models`, `code_version`) | `alias_modele__reprise…`, `reprise_autre_code…` (2) | 4, 7 | tranchée en partie | attribution par unité · refus du mélange · union + drapeau | attribution par unité |
| C19 | Plan d'expérience de la campagne | `ablation_saknussemm__un_temoin…[bnl, dresden]`, `ablation_segmentation_vlm__meme_reglages…[bnl, dresden]` (4) | — | **ouverte** | ablation stricte à une variable · facteurs confondants déclarés · réglages équivalents non limitants · plan factoriel | témoin obligatoire pour Saknussemm ; `max_tokens` à trancher |

**Bilan : 19 conventions.**
- 9 tranchées : C05, C06, C07, C08, C10, C12, C13, C14, C15.
- 6 tranchées en partie : C01, C02, C03, C09, C17, C18.
- 4 ouvertes : C04, C11, C16, C19.

**Ordre de décision conseillé** : C10 avant C03 (le τ dépend des paires appariées), C01 avant C02 et C05, C17 avant C14.

---

## Fiches

### C01 — CER, WER et `ins_rate` sur une référence vide

- **Tests** :
  - discutable : `applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__reference_vide_nentre_pas_dans_le_test_apparie` ;
  - valides liés : `metriques_stats/test_ms_aggregation.py::test_reference_vide__hallucination_comptee_au_numerateur[cer|wer|ins_rate]`, `::test_reference_vide__pipeline_qui_hallucine_est_classe_apres`, `test_ce_applicabilite.py::test_applicabilite__reference_vide_nest_pas_comptee_notee` ;
  - les paramètres `[char_accuracy]` et `[fca]` relèvent aussi de C02.
- **Arbitrages** : 2 (comptes), 3 (statut de validité), 1 (micro et macro distingués). **Tranchée en partie.**
  - Avec des comptes additifs, Σ éditions / Σ longueurs inclut naturellement les insertions d'une page blanche, sauf exclusion explicite déclarée par la métrique.
  - Par document, x/0 est une non-mesure qui doit porter un statut typé.
  - Reste ouvert : la page blanche entre-t-elle dans le macro et dans le test apparié ?
- **Contre-exemples** :
  - (ms) page `a`, 10 caractères parfaits, plus une page blanche où le moteur invente 44 caractères (7 mots) ;
  - (app) 6 pages de texte de 20 caractères, où A fait 1 faute et B en fait 2 à 7, plus 6 pages blanches où A rend `.` et B ne rend rien.

| Option | Source | ms : CER / WER | app : micro A / B | app : test apparié | Attendu des tests |
|---|---|---|---|---|---|
| **A. Comptes au corpus** ; page blanche au numérateur seulement ; CER par page « non défini » (statut) | jiwer 4.0.0 `process_characters` / `process_words` sur liste : 44/10 = 4,4 et 7,0 (vérifié dans le venv d'oracle) ; ISRI `accsum` cumule caractères et erreurs sur les pages (Rice, Jenkins et Nartker 1996 ; ocreval, Santos 2019) | 4,4 / 7,0 | 0,100 / 0,225 | Wilcoxon par document sur 6 pages : p = 0,031 ; permutation appariée du Δ micro sur 12 pages : p = 0,165 | ms `[cer, wer, ins_rate]` et `pipeline_qui_hallucine` : verts. app `nentre_pas` : vert si le payload testé est le Wilcoxon par document. app `nest_pas_comptee_notee` (V) : **rouge sur sa 1ʳᵉ assertion** (0,05 attendu, 0,100 obtenu, voir T1) |
| **B. Exclusion de la page** (micro actuel) | `test_metrics_text.py::test_cer_weight_is_reference_length` (Cinoc) | 0,0 / 0,0 | 0,050 / 0,225 | Wilcoxon sur 6 pages : 0,031 | ms rouges ; app `nentre_pas` vert, `nest_pas_comptee_notee` vert |
| **C. 1,0 par page** (plafonné), qui entre dans le macro et le test (`_error_rate` actuel) | Cinoc `metrics/text.py:114` | micro 0,0 (poids 0) | 0,050 / 0,225 | Wilcoxon sur 12 pages, valeurs 1,0 contre 0,0 : 0,162 | app `nentre_pas` rouge (actuel) |
| **D. ∞ par page** | dinglehopper 0.11.0, `character_error_rate_n` : `inf` si n = 0 et d > 0, 0 si d = 0 (lu dans le source installé). `dinglehopper-summarize` fait la **moyenne** des CER par rapport (macro) | moyenne = ∞ | macro ∞ | test indéfini | tous rouges ; aucune agrégation finie |
| **E. Normalisation par max(\|réf\|, \|hyp\|)** pour les pages concernées | distance d'édition normalisée (Yujian et Bo 2007, IEEE TPAMI) ; c'est le dénominateur du cMER/MER | (0 + 44)/(10 + 44) = 0,815 | — | — | ms rouges ; change la définition du CER |

- **Effet réel** : nul aujourd'hui. Les 37 pages BNL et les 10 pages Dresden n'ont aucune vérité terrain vide. Le risque porte sur les corpus futurs, où les gardes, les versos et les planches sont courants.
- **A.**
  - Avantages : seule option où un pipeline qui hallucine est classé derrière un pipeline muet ; parité avec jiwer et ISRI ; conforme à l'arbitrage 2.
  - Risques : un CER corpus peut dépasser 1 à cause d'une seule page blanche, ce qui est correct par définition, mais il faut afficher la couverture.
- **B.**
  - Avantage : stabilité.
  - Risque : récompense l'hallucination sans borne.
- **C.**
  - Risque : la valeur 1,0 est fabriquée, puis mêlée à des taux d'une autre échelle dans les rangs.
- **D.**
  - Avantage : honnête par page.
  - Risque : inagrégeable.
- **E.**
  - Risque : change la métrique sous le même nom.
- **Recommandation (non décidée)** : A, avec le statut « référence vide » par page. La page est exclue du macro et du test par document, et incluse au micro et à son test apparié.

### C02 — Plancher des exactitudes (`char_accuracy`, `word_accuracy`, `fca`)

- **Tests** : `test_ms_aggregation.py::test_reference_vide__hallucination_comptee_au_numerateur[char_accuracy-0.0]`, `[fca-0.0]` (ils dépendent aussi de C01), `::test_char_accuracy__vaut_un_moins_cer_corpus`.
- **Arbitrages** : 1 et 2. **Tranchée en partie.**
  - La valeur actuelle (plancher par page, puis moyenne pondérée) n'est ni le micro (finalisation sur les sommes), ni le macro (moyenne non pondérée). L'arbitrage 2 l'exclut.
  - Reste ouvert : faut-il un plancher au micro ?
- **Contre-exemples** :
  - d1 : `ab` → `000000` (CER 3) ; d2 : 10 caractères parfaits ; CER corpus 0,5 ;
  - page blanche de C01.

| Option | Source | `vaut_un_moins_cer` | page blanche (`char_accuracy`) | Dresden E5 (4 pages notées) | Attendu |
|---|---|---|---|---|---|
| **A. Plancher au corpus** : max(0, 1 − ΣE/ΣN) | finalisation sur statistiques suffisantes (arbitrage 2) | 0,5 | 0,0 (avec C01-A) | **0,000** (1 − 1,8614 < 0) | les 3 tests verts (le 2ᵉ avec C01-A) |
| **B. Sans plancher** : (N − E)/N | ISRI Analytic Tools, définition (n − erreurs)/n cumulée par `accsum`, non bornée inférieurement | 0,5 | −3,4 | −0,861 | `vaut_un_moins` vert ; page blanche rouge |
| **C. Plancher par page, moyenne pondérée** (actuel, `text.py:246`) | Cinoc (exception documentée) | 0,833 | 1,0 (poids 0) | **0,3125** | rouges |
| **D. Macro** : moyenne non pondérée de max(0, 1 − CER_i) | arbitrage 1 (estimande macro) | (0 + 1)/2 = 0,5 | page blanche hors macro → 1,0 | 0,3251 | `vaut_un_moins` vert (coïncidence) ; page blanche rouge |

- **Effet réel** :
  - BNL : aucune page n'a un CER > 1, donc A = B = C = 1 − CER micro (E0 : 0,9416).
  - Dresden E5 (VLM local, une page bouclée à CER 5,08) : 0,000 sous A contre 0,3125 sous l'actuel. Toute la part des erreurs au-delà de 100 % disparaît de l'exactitude affichée.
- **Avantages et risques** :
  - A : le nom « exactitude » annonce [0, 1], et l'information perdue sous le plancher reste dans le CER publié à côté.
  - B : fidèle à ISRI, mais une « exactitude » négative déroute.
  - C : ni micro ni macro.
- **Recommandation (non décidée)** : A pour le micro, D publié à part comme macro.

### C03 — Poids et unité de `reading_order_tau`

- **Test** : `test_ms_aggregation.py::test_reading_order_tau__micro_sur_paires`.
- **Arbitrages** : 1 et 2. **Tranchée en partie.**
  - Le poids actuel (nombre de blocs, D-289, unité déclarée `REGION`) n'est pas le dénominateur de la statistique, qui est le nombre de paires. Le chiffre n'est donc ni micro ni macro.
  - Reste ouvert : quelle statistique de comptage porte le nom « τ » ?
- **Contre-exemple** : d1, 2 blocs inversés (1 paire discordante sur 1) ; d2, 10 blocs en ordre (0 sur 45).

| Option | Source | Valeur | Attendu |
|---|---|---|---|
| **A. Σ discordantes / Σ paires** (micro) | distance de Kendall normalisée par n(n−1)/2 (Kendall 1938 ; Lapata 2006, *Computational Linguistics* 32(4)) | 1/46 = **0,0217** | vert |
| **B. Macro** (moyenne des τ par page) | arbitrage 1 | 0,5 | rouge |
| **C. Pondéré par les blocs** (actuel) | Cinoc D-289 | 0,1667 | rouge (actuel) |
| **D. Mesure par bloc** : blocs à déplacer (n − LIS) / blocs, en micro | distance d'Ulam ; c'est une **autre** métrique, à nommer autrement | 1/12 = 0,0833 | rouge |
| (alternative de méthode) Évaluation par relations pondérées | PRImA (Clausner, Pletschacher et Antonacopoulos 2013, ICDAR, « The significance of reading order… ») | non calculable ici | — |

- **Effet réel** : sans objet, aucune métrique d'ordre de lecture dans les vues de la campagne.
- **Risques** : C sur-pondère les petites pages de façon quadratique (facteur 7,7 ici). D est légitime si l'unité voulue est la région, mais il ne s'appelle pas τ.
- **Recommandation (non décidée)** : A sous le nom τ, et B publié à part. D seulement sous un autre nom.

### C04 — Lignes fantômes dans `line_identity_cer`

- **Test** : `test_ms_aggregation.py::test_line_identity_cer__ligne_fantome_comptee_en_insertion`.
- **Arbitrage** : aucun. L'arbitrage 2 impose des comptes, pas leur contenu. **Ouverte.**
- **Contre-exemple** : la vérité terrain a une ligne `l1` (10 caractères) ; l'hypothèse a `l1` identique plus une ligne fantôme `l2` de 10 caractères.

| Option | Source | Valeur | Attendu |
|---|---|---|---|
| **A. Insertions comptées** au numérateur | convention de `region_cer` depuis D-288 (Cinoc) ; FCA, où le texte d'hypothèse resté non apparié compte en erreurs (Clausner, Pletschacher et Antonacopoulos 2020, *Pattern Recognition Letters* 131) ; CER sur texte sérialisé | 10/10 = **1,0** | vert |
| **B. Lignes appariées seules** (actuel, `lines.py`), avec rappel séparé (`line_identity_coverage`) | Cinoc | 0,0 | rouge |
| **C. Deux métriques nommées** : A sous `line_identity_cer`, B sous un nom du type « CER des lignes appariées », plus une précision de lignes | — | 1,0 et 0,0 | vert |

- **Effet réel** : sans objet, métrique absente des vues de la campagne.
- **Risques** :
  - A : une ligne de référence scindée en deux lignes d'hypothèse compte en suppression et insertion, ce qui mêle segmentation et reconnaissance.
  - B : une étape aval qui duplique ou invente des lignes est invisible, parce que la couverture n'est qu'un rappel.
- **Recommandation (non décidée)** : A, ou C si l'on veut garder la lecture actuelle sous un nom honnête.

### C05 — Estimande des tests omnibus : Demšar par document contre ratio micro

- **Tests** : `test_ms_statistics.py::test_test_omnibus__meme_sens_que_le_cer_micro_affiche`, `::test_test_omnibus__p_du_ratio_micro_par_permutation_appariee`.
- **Arbitrage** : 1 (micro et macro distingués ; tests correspondant à la grandeur estimée ; comparaisons appariées). **Tranchée.**
- **Contre-exemple (Simpson)** : 12 pages de 20 caractères (A parfait, B 2 fautes) et une page de 2 000 caractères (A 400 fautes, B parfait).

| Estimande et test | Source | A | B | p | Lecture |
|---|---|---|---|---|---|
| Micro (Σ erreurs / Σ réf.) | — | 0,179 | 0,011 | — | B meilleur |
| Macro (moyenne des CER par page) | HIPE-scorer publie `micro` et `macro_doc` (« moyenne des scores micro séparés par document ») | 0,0154 | 0,0923 | — | A meilleur |
| **Wilcoxon apparié sur les CER par page**, Holm | Demšar 2006 (*JMLR* 7) ; comparaisons multiples : Benavoli, Corani et Mangili 2016 (*JMLR* 17), qui déconseillent les post-hoc sur rangs moyens et préconisent Wilcoxon par paires + Holm | — | — | 0,0195 | effet par page, dans le sens de A |
| Test des signes par page | — | — | — | 0,0034 | idem |
| **Permutation appariée (échange de signe) du Δ micro**, exacte, 2¹³ | randomisation approchée : Noreen 1989 ; Riezler et Maxwell 2005 ; Dror et al. 2018 | — | — | **1,0** | Δ micro non significatif |
| Bootstrap apparié du Δ micro (IC 95 %) | Koehn 2004 (EMNLP, métrique corpus non décomposable) ; Efron et Tibshirani 1993 | — | — | IC [−0,10 ; 0,19] | contient 0 |

- **Ce que l'arbitrage implique pour les attendus.** Les deux tests juxtaposent le Wilcoxon et le micro. Sous l'arbitrage 1, c'est précisément la juxtaposition qui est fautive, pas le Wilcoxon. Les deux tests sont donc **à reformuler** :
  - `meme_sens` : le test associé au **micro** doit aller dans le sens du micro, ou ne pas être significatif (p = 1). Le Wilcoxon reste légitime, étiqueté « effet par document » à côté du **macro**, dans le sens de A.
  - `p_du_ratio_micro` : l'assertion `p_holm ≥ α` doit porter sur le champ du test micro, pas sur le Wilcoxon.
  - Le défaut constaté (un estimande non nommé, sans sens) reste confirmé.
- **Effet réel (BNL, vue `texte`)** :
  - E5 − E0 : Δ micro −0,0243 et Δ macro −0,0220. Wilcoxon p = 0,0005, permutation du Δ micro p = 0,0017 : les deux estimandes concordent.
  - E1 − E0 : Wilcoxon p = 0,351, permutation p = 0,301.
  - **Composition de la famille** : le Friedman publié (p = 0,029, Holm 0,228, famille de 8) compte E1, E3 et E4, qui sont identiques page à page. Restreint aux 3 pipelines distincts, il donne p = 0,051. Des pipelines identiques déplacent ainsi le seuil de significativité. C'est une question voisine, sans arbitrage.
- **Reste à choisir (modalité)** :
  - pour le micro : permutation (p) et bootstrap apparié (IC) ;
  - pour le macro : Wilcoxon par paires + Holm (Benavoli 2016), ou Friedman + Nemenyi (Demšar 2006) ;
  - la règle de famille (dédoublonner des pipelines identiques).

### C06 — IC marginaux contre IC appariés ; support des intervalles

- **Tests** : `test_ms_statistics.py::test_intervalles__ic_apparie_sur_la_difference_micro`, `::test_intervalles__meme_documents_que_le_test`.
- **Arbitrages** : 1 (comparaisons appariées) et 8 (performance conditionnelle et support commun). **Tranchée.**

| Option | Source | `ic_apparie` (30 pages, B = A + 1 faute) | `meme_documents` (A échoue sur 1 page sur 8) |
|---|---|---|---|
| A. IC marginaux seuls, chacun sur son support (actuel, D-275) | Cinoc `inference.py:_intervals` | A [0,224 ; 0,345], B [0,234 ; 0,355] : chevauchement | A sur 7 pages, B sur 8 |
| B. IC bootstrap apparié du Δ micro, sur le support commun | Efron et Tibshirani 1993 ; Koehn 2004 | Δ [0,01 ; 0,01] | Δ sur 7 pages |
| **C. Les deux** : marginaux étiquetés « conditionnels » (support propre et couverture), Δ apparié sur le support commun | arbitrages 1 et 8 | les deux | marginaux 7 et 8, Δ sur 7 |

- **Implications** :
  - `ic_apparie` reste vert sous C.
  - `meme_documents` exige des IC marginaux sur les 7 documents. C'est trop strict sous l'arbitrage 8, qui publie légitimement la performance conditionnelle sur son propre support. L'attendu devient : **l'intervalle qui accompagne le test (le Δ) porte sur les cas complets** du test. Test à reformuler.
- **Effet réel (BNL)** :
  - IC marginaux E0 [0,041 ; 0,078] et E5 [0,026 ; 0,046] : ils se chevauchent sur [0,041 ; 0,046] ;
  - IC apparié Δ(E5 − E0) [−0,041 ; −0,010] : il exclut 0 ;
  - Δ(E1 − E0) [−0,001 ; 0,017] : il contient 0.
- **Reste à choisir** : seulement la présentation (le dot plot des marginaux, et l'endroit où placer le Δ).

### C07 — Politique d'échec par défaut et support du classement

- **Test** : `test_ms_statistics.py::test_echec_non_aleatoire__classement_sur_documents_communs`.
- **Arbitrage** : 8 (performance conditionnelle, couverture, comparaison sur support commun, performance opérationnelle). **Tranchée.**
- **Contre-exemple** : 7 pages de 100 caractères (A 5 fautes, B 4) et 1 page de 1 000 caractères (A échoue, B 500 fautes).

| Option | Source | A | B | Classement |
|---|---|---|---|---|
| `exclude` + agrégat marginal comme classement (actuel, A3) | Cinoc | 0,050 (7/8) | 0,311 (8/8) | A devant |
| Cas complets seuls | analyse sur cas complets ; biaisée si la donnée manque en fonction de la difficulté (MNAR, Little et Rubin, *Statistical Analysis with Missing Data*) ; Demšar 2006 exige des blocs complets | 0,050 | **0,040** | B devant |
| Imputation « page vide » (C08) | — | 1 035/1 700 = 0,609 | 0,311 | B devant |
| **Couverture + performance conditionnelle + comparaison sur support commun** | arbitrage 8 | 0,050 (couverture 7/8) | 0,311 (8/8) ; sur support commun 0,040 contre 0,050 | B devant sur le support commun |

- **Implication** : l'assertion `cer_a.value ≥ cer_b.value` vise l'agrégat **marginal**. Sous l'arbitrage 8, A = 0,05 reste publiable comme performance conditionnelle (7/8). L'attendu se reporte sur l'objet de comparaison : sur le support commun, B (0,040) est devant A (0,050), et le tableau ne doit pas classer sur des agrégats de supports différents. Attendu à recibler.
- **Effet réel (Dresden, E5 VLM local, 6 échecs « délai »)** :
  - conditionnel 1,8614 sur **4/10 pages** (4 272 caractères sur 10 363, soit 41 %) ;
  - E0 sur le même support 0,7795, et 0,7563 sur les 10 pages ;
  - imputation page vide 1,3551.
- **Reste à choisir** : le tri par défaut du tableau. Recommandation (non décidée) : trier sur le support commun, avec une colonne de couverture.

### C08 — Sémantique de `max_error` (imputation d'un échec)

- **Tests** : `test_ce_max_error.py::test_max_error__un_echec_ne_note_jamais_mieux_quune_reponse`, `::test_max_error__echec_note_comme_une_page_vide[ins_rate]`. Valide lié : `::test_max_error__un_echec_compte_comme_note_deplace_lagregat` (`bow_precision`).
- **Arbitrage** : 8 (refus de toute erreur maximale universelle déduite de `higher_is_better`). **Tranchée.**
- **Contre-exemple** : référence de 30 caractères. `panne` échoue sur `b` ; `bavard` y écrit `zq × 30` (CER 2,767) ; `vide` y rend une page vide.

| Option | Source | Échec CER | Échec `ins_rate` | Échec `bow_precision` | `un_echec_ne_note_jamais_mieux` (≥ 2,767) | `page_vide[ins_rate]` |
|---|---|---|---|---|---|---|
| A. 0 ou 1 selon `higher_is_better` (actuel, `runner.py:409`) | — | 1,0 | 1,0 | 0,0, poids 0 | rouge | rouge |
| **B. « Page vide »** : valeur que la métrique donne à une hypothèse vide | promesse de la doc d'`EvaluationSpec` | 1,0 | 0,0 | 0/0 indéfini → non noté | rouge, **non exigible sous 8** | vert |
| C. Pire valeur observée sur ce document parmi les pipelines du run | — | 2,767 | 23/7 = 3,29 (jiwer) | — | vert | rouge |
| D. Borne déclarée par la métrique | métriques bornées seulement ; le CER n'a pas de borne | aucune | aucune | 0 | rouge | rouge |
| **E. Aucune imputation** : couverture + conditionnel + support commun | arbitrage 8 | non noté | non noté | non noté | sans objet | sans objet |

- **Implications** :
  - `un_echec_ne_note_jamais_mieux` exige une valeur imputée au moins égale à toute réponse. Seule C y satisfait, et elle n'est pas reproductible (elle dépend des pipelines présents). Sous l'arbitrage 8, cet attendu n'est plus exigible. Le test est à reformuler, par exemple : aucune règle ne s'appelle « erreur maximale », et la valeur imputée, s'il y en a une, est celle de la page vide, déclarée comme telle.
  - `page_vide[ins_rate]` reste vert sous B.
  - Le valide lié reste vert sous B, car la page vide n'est pas notée en `bow_precision` (0/0).
- **Effet réel (Dresden E5)** :
  - échecs imputés page vide : 1,3551. C'est aussi la valeur sous A pour le CER (1,0 par page en échec).
  - pire observée (E0, E1 ou E3 sur les pages en échec) : 1,2342. Elle est **inférieure** à la page vide, parce que Tesseract y fait moins de 100 % d'erreurs.
  - la page tronquée 177 (sortie bouclée, CER 5,08) reste notée. Sous A ou B, échouer sur cette page aurait coûté 1,0 au lieu de 5,08.
- **Recommandation (non décidée)** : E par défaut ; B comme analyse de sensibilité nommée « échec noté comme page vide » ; C écartée.

### C09 — Grappes documentaires

- **Test** : `test_ms_statistics.py::test_bootstrap__grappes_documentaires_declarables`.
- **Arbitrage** : 1 (« groupes documentaires »). **Tranchée en partie** : le principe est fixé, il reste la méthode et la déclaration.
- **Implication pour l'attendu** : le test vérifie des **noms** (`groups`, `clusters`, `group` dans la signature, `group` ou `cluster` dans `DocumentRef`). Un champ conforme à l'arbitrage mais nommé autrement (par exemple `collection` ou `volume`) le laisserait rouge. Il est à reformuler en test de comportement : la même liste de pages, groupée de deux façons, doit donner deux IC.

| Option | Source | BNL E0, IC 95 % du micro | BNL Δ(E5 − E0), IC apparié | Dresden |
|---|---|---|---|---|
| A. Bootstrap par document (actuel) | Efron et Tibshirani 1993 | [0,041 ; 0,078] (largeur 0,037) | [−0,041 ; −0,010] | possible, mais généralise aux pages **de ce manuscrit** |
| **B. Bootstrap par grappe** (on tire des grappes, comptes sommés) | Field et Welsh 2007 (*JRSS B* 69) ; Davison et Hinkley 1997, §3.8 | [0,044 ; 0,088] (largeur 0,044, soit +19 %) | [−0,042 ; −0,014] | **non estimable** (1 grappe) |
| C. Bootstrap à deux niveaux (grappes, puis pages) | Davison et Hinkley 1997, §3.8 | non calculé | — | idem |
| D. Peu de grappes : bootstrap sauvage par grappe, ou « non estimable » sous un seuil | Cameron, Gelbach et Miller 2008 (*REStat* 90) | 5 grappes, dont un singleton : percentile peu fiable | — | — |

- **Grappes réelles de BNL** : la page ALTO source (`<fileName>` du `.xml`). On compte 5 grappes : `ALTO00001` (8 crops), `00002` (11), `00003` (11), `00004` (6), `00008` (1). Elles ne sont déclarées nulle part dans le corpus.
- **Recommandation (non décidée)** :
  - une grappe déclarée par le corpus (champ de `DocumentRef`, ou métadonnée d'import) ;
  - B pour les IC micro, avec « non estimable » sous un seuil de grappes à fixer ;
  - l'IC par document conservé, étiqueté « conditionnel au corpus ».

### C10 — Appariement de détection : glouton contre optimal

- **Tests** : `test_la_matching.py::test_glouton_vs_optimal__la_detection_atteint_l_optimum_global`, `::test_glouton_vs_optimal__region_cer_suit_l_appariement_optimal`.
- **Arbitrage** : 6 (« méthodes globales établies ; fusions et scissions » ; par page). **Tranchée.**
- **Contre-exemple** : références A = [0, 10] et B = [2, 12], qui se recouvrent entre elles (IoU = 0,667) ; hypothèses X = [1, 11] et Y = [−3, 7] ; seuil 0,5 inclusif.

| Option | Source | Paires | F1 | Dépend de l'ordre ? | Attendu |
|---|---|---|---|---|---|
| A. Glouton par référence, dans l'ordre du fichier (actuel, `_greedy_pairs`) | — | 1 | 0,5 | oui (2 paires si la référence est lue [B, A]) | rouge |
| B. Glouton par hypothèse, dans l'ordre des scores | COCO, `pycocotools` `COCOeval.evaluateImg` (Lin et al. 2014) ; Pascal VOC (Everingham et al. 2010, *IJCV* 88). Sans score ici, l'ordre est celui du fichier | 2 dans 3 ordres sur 4, 1 dans l'ordre (réf. [B, A], hyp. [X, Y]) | 1,0 ou 0,5 | oui | vert dans l'ordre du test, mais fragile |
| **C. Hongrois 1-1** (cardinalité maximale, ou somme maximale des IoU : ici les deux concordent) | Kuhn 1955 ; `scipy.optimize.linear_sum_assignment` ; déjà employé par Cinoc pour les lignes (`flexible.py:50`) ; CLEAR MOT (Bernardin et Stiefelhagen 2008) | 2 | 1,0 ; `region_cer` 0 | non | **vert** |
| D. Évaluation PRImA par recouvrement (fusion, scission, manque, fausse détection, pondérées par scénario) | Clausner, Pletschacher et Antonacopoulos 2011 (ICDAR, « Scenario driven in-depth performance evaluation of document layout analysis methods ») | X recouvre A et B (9/11 chacune) : erreur de type fusion probable | pas un F1 | non | le F1 n'est pas défini ; s'ajoute à C |

- **Note** : pour la qualité panoptique, Kirillov et al. 2019 (CVPR) montrent qu'avec un seuil strict IoU > 0,5 et des segments disjoints, l'appariement est unique, donc glouton = optimal. Le contre-exemple exige des références qui se recouvrent, ou une égalité au seuil inclusif. Le défaut est donc **étroit**, comme le dit le rapport.
- **Implication** : l'attendu (F1 1,0, `region_cer` 0) tient pour la composante 1-1 retenue par l'arbitrage. Les comptes de fusions et de scissions sont un ajout, pas un remplacement.
- **Reste à choisir** : le critère du hongrois (cardinalité ou somme des IoU) et le seuil (inclusif ou strict).
- **Effet réel** : sans objet, aucune métrique de région dans les vues commitées.

### C11 — Calibration : jugement d'un jeton (multi-ensemble contre alignement)

- **Tests** : `test_la_calibration.py::test_calibration_mots_permutes__correct_par_alignement`, `::test_calibration_mot_repete_deplace__correct_par_alignement`.
- **Arbitrage** : aucun. **Ouverte.**
- **Cadre** : l'ECE de Guo, Pleiss, Sun et Weinberger 2017 (ICML ; ECE introduit par Naeini, Cooper et Hauskrecht 2015) mesure l'exactitude **de chaque prédiction**. Pour des jetons d'OCR, « la prédiction i » n'existe qu'après un alignement, et ce choix est la convention.
- **Contre-exemples** :
  - (1) VT « un deux », jetons « deux un » à 0,95 ;
  - (2) VT « de la ville de paris », jetons « de la ville paris de » à 0,99.

| Option | Source | ECE (1) | ECE (2) | Attendu |
|---|---|---|---|---|
| A. Multi-ensemble des mots de la VT (actuel, D-068) | Cinoc `calibration.py:126` | 0,05 | 0,01 | rouge |
| **B. Alignement qui maximise les correspondances** (LCS) | `difflib.SequenceMatcher(autojunk=False)` (référence du test) | **0,45** | **0,19** | vert |
| C. Alignement de Levenshtein mot à mot | ocrevalUAtion (Carrasco 2014, DATeCH) ; dinglehopper (`align`) | 0,45 / 0,19 avec le retour arrière de rapidfuzz 3.x (insertion + suppression) ; **0,95 / 0,39** si l'égalité de coût est départagée en faveur des substitutions | — | vert ou rouge selon le départage |
| D. Égalité position par position | — | 0,95 | 0,39 | rouge |
| E. Appariement géométrique des mots (boîtes ALTO `String` contre VT) | évaluation de mise en page au niveau mot | non calculable (`ConfidenceToken` n'a pas de position) | — | — |

- **Avantages et risques** :
  - A sur-crédite les insertions et les déplacements de mots fréquents : il sous-estime l'ECE d'un moteur surconfiant.
  - C est ambigu à coût égal : il faut un départage déclaré.
  - D pénalise tout décalage.
  - E est la plus juste, mais demande d'enrichir le contrat avec une position.
  - B et C traitent une erreur d'ordre de colonnes comme une erreur de reconnaissance. Un alignement par ligne corrigerait ce point, et demande lui aussi une position.
- **Effet réel** : sans objet, aucun payload de calibration dans les `RunResult` commités.
- **Recommandation (non décidée)** : B, ou C avec un départage « maximiser les correspondances » déclaré. L'alignement par ligne vient plus tard.

### C12 — Granularité étape : issue, coût de préfixe, reprise

- **Tests** : `test_ce_echecs_partiels.py::test_echec_partiel__lamont_reussi_reste_observable`, `::test_echec_partiel__la_reprise_ne_repaie_pas_lamont`, `test_la_analyses_target.py::test_economie_vue_cible_ocr__ne_facture_pas_l_etage_llm`.
- **Arbitrages** : 4 (résultats, coûts, statuts et artefacts par étape ; étapes réussies conservées), 5 (cache séparé), 7 (inconnu signalé). **Tranchée.**
- **Implications par test** :

| Test | Attendu sous les arbitrages | Remarque |
|---|---|---|
| `lamont_reussi` | CER OCR de `b` = 0,10 : la vue `target_step: ocr` note l'étape réussie | vert |
| `economie_vue_cible_ocr` | `tokens_in` = `None` (inconnu) parce que la fixture ne fournit qu'un usage au niveau du pipeline ; avec un usage par étape, ce serait le coût de l'étape OCR | vert ; la fixture sera à réécrire quand le contrat portera l'usage par étape |
| `la_reprise` | OCR de `b` appelé 1 fois | dépend de la modalité ci-dessous |

- **Reprise (modalité résiduelle)** :

| Option | OCR de `b` à la reprise | Attendu |
|---|---|---|
| A. Clé par unité (actuel, `resume.py:130`) | 2 appels | rouge |
| **B. Clé par préfixe d'étapes** (`step_fingerprint` existe déjà par étape et par amont) | 1 appel | vert |
| C. Clé par unité, mais étapes réussies d'une unité en échec conservées pour la seule renotation | 2 appels | rouge |

- **Effet réel** : aucun sur les `RunResult` commités. Les pipelines sont à une étape, ou en échec sur une étape unique (Dresden E5). Les chaînes E2 et E3 de S31 seront concernées.
- **Recommandation (non décidée)** : B.

### C13 — Non-mesure typée : fan-out sans région reconnue, vérité terrain illisible

- **Tests** : `test_ce_applicabilite.py::test_applicabilite__fanout_sans_aucune_region_reconnue_reste_attendu`, `::test_applicabilite__gt_referencee_mais_absente_refusee_avant_de_payer`.
- **Arbitrage** : 3 (statut typé et motif, en distinguant applicabilité, disponibilité, validité et exécution). **Tranchée.**
  - La règle « niveau absent → `None` » (CLAUDE.md §3) vise un niveau absent de la **vérité terrain** (applicabilité).
  - Une hypothèse vide parce que toutes les régions ont échoué relève du **statut d'exécution**.
- **Fan-out (modalité)** : les deux options donnent `expected` = 2, donc le test est vert sous les deux.
  - (a) noter l'hypothèse comme un texte vide : `region_cer` = 1 sur la page, plus le statut « exécution partielle » ;
  - (b) la déclarer attendue mais non notée : statut « exécution partielle », support 1/2.
- **GT illisible (modalité)** : le test accepte les deux branches.
  - (a) refus avant toute exécution, pour toute spec et pas seulement au chargement YAML ;
  - (b) statut « GT illisible » sur le document, et le reste est noté.
- **Recommandation (non décidée)** : refus avant exécution quand c'est détectable au démarrage ; statut quand le problème apparaît en cours de run ; (a) pour le fan-out, le comportement le moins favorable à la panne.

### C14 — Archive scellée : intégrité et immuabilité

- **Tests** : `test_ce_artefacts_archive.py::test_a7_octet_change_dans_une_sortie__corruption_detectee`, `::test_a7_index_json_valide_mais_altere__alteration_detectee`, `::test_a7_image_partagee_corrompue__corruption_detectee`, `::test_a7_archive_publiee__une_reprise_normale_ne_la_modifie_pas`.
- **Arbitrage** : 5 (cache mutable séparé d'une archive scellée, portable et vérifiable). **Tranchée.**
- **Implications** :
  - les quatre attendus tiennent **pour l'archive** ;
  - ces tests exercent aujourd'hui le `ResumeStore`. Une fois la séparation faite, ils sont à recibler sur le lecteur d'archive ;
  - pour le cache, recalculer les empreintes reste peu coûteux et conseillé, mais l'immuabilité n'est pas exigible : un cache se réécrit ;
  - `archive_publiee` devient : une reprise sur une archive scellée refuse d'écrire, ou écrit ailleurs.
- **Format** (« à étudier » selon l'arbitrage) :

| Option | Source | Intégrité | Immuabilité et versions | Provenance |
|---|---|---|---|---|
| BagIt | RFC 8493 (2018) : `manifest-sha256.txt`, `tagmanifest-*.txt`, `bag-info.txt` | oui : chaque fichier et chaque fichier de tags (dont `index.json`) est haché et vérifiable | non (pas de versions) | minimale |
| RO-Crate 1.1 | Soiland-Reyes et al. 2022 (*Data Science* 5) : `ro-crate-metadata.json` en JSON-LD ; profils Workflow Run Crate | non obligatoire | non | riche (PROV, schema.org) |
| OCFL 1.1 | Oxford Common File Layout : inventaire avec empreintes, versions immuables | oui | **oui** | minimale |
| RO-Crate dans un BagIt | combinaison décrite par la spécification RO-Crate | oui | non | riche |

- **Recommandation (non décidée)** : BagIt avec les métadonnées RO-Crate, qui couvre les trois tests d'intégrité ; OCFL si une archive publiée doit pouvoir recevoir des versions. Sous BagIt, le test `index_json_valide_mais_altere` est couvert par le `tagmanifest`.

### C15 — Portabilité de l'archive : images

- **Tests** : `test_ce_artefacts_archive.py::test_a7_relecture_offline_image_distante__aucun_telechargement`, `::test_a7_relecture_offline_serveur_d_images_eteint__unite_relue_de_l_archive`, `::test_a7_archive_seule_sans_images_du_corpus__reevaluable`.
- **Arbitrages** : 5 (portable) et 7 (identité des données). **Tranchée.**
  - Une renotation hors ligne ne télécharge rien.
  - L'identité d'une unité se lit dans l'empreinte d'image archivée, pas dans les octets de l'image du corpus.
- **Modalité** :

| Option | Taille | Licence | Ce qui reste possible |
|---|---|---|---|
| A. Octets d'image dans l'archive (actuel `images/<sha256>`) | BNL : 34,1 Mo d'images sur 37,4 Mo d'archive ; Dresden : 8,1 sur 9,0 Mo | à vérifier corpus par corpus (le README de `corpus/` signale les conditions BnF) | renotation, réexécution, audit visuel |
| B. Empreinte + référence épinglée (IIIF, ou révision HF comme Dresden `db171cc5…`) | négligeable | sans objet | renotation (un score ne dépend que des sorties et de la VT) ; pas la réexécution |

- **Attendus** : les trois tests sont verts sous A comme sous B, si la clé est dérivée de l'empreinte stockée.
- **Recommandation (non décidée)** : empreinte obligatoire, octets facultatifs selon la licence.

### C16 — Fan-out sur un layout multipage avec une seule image

- **Test** : `test_la_reassembly.py::test_fanout_multipage__une_page_n_est_pas_lue_dans_l_image_d_une_autre`.
- **Arbitrage** : 6 dit « page par page » pour l'appariement, pas pour le référentiel d'image. **Ouverte.**
- **Réserve du relecteur** : le mécanisme est montré sans découpeur.

| Option | Source | Attendu (`p2a` lu dans une autre image, ou `CinocError`) |
|---|---|---|
| A. Une image par page (le `DocumentRef` porte une image par page) | PAGE XML : une `Page` par fichier, `imageFilename` | vert |
| B. Image partagée, coordonnées des pages dans son référentiel, décalages déclarés (planche double) | ALTO admet plusieurs `<Page>` par fichier (`PHYSICAL_IMG_NR`, `PrintSpace`) | rouge si le layout déclare ce référentiel, car lire `p2a` dans l'image commune serait alors **correct**. Le layout du test ne déclare rien, ce qui est ambigu |
| C. Refus typé d'un layout multipage accompagné d'une seule image | — | vert |

- **Effet réel** : sans objet. Les ALTO BNL ont une page par fichier. Le feuillet BnF a une césure entre pages, mais il est hors campagne.
- **Recommandation (non décidée)** : C en 1.0, A ensuite. B seulement avec un référentiel déclaré dans le layout.

### C17 — Identité d'étape : version déclarée contre empreinte automatique

- **Tests** : `test_pc_provenance.py::test_version_manuelle__brique_modifiee_sans_relever_sa_version_reexecutee`, `::test_identite_saknussemm__prompt_et_temperature_envoyes_au_llm_sont_traces`. Valides liés : `version_manuelle__identite_saknussemm_porte_la_version_de_la_bibliotheque`, `identite_saknussemm__poids_du_scoreur_qe_epingles`.
- **Arbitrage** : 7 (empreintes automatiques de l'exécution et des protocoles de mesure). **Tranchée en partie** : la modalité change l'attendu.

| Mécanisme | Source | `brique_modifiee` | `prompt_et_temperature` |
|---|---|---|---|
| A. Version déclarée à la main (actuel, `fingerprint.py:72`) | — | rouge | rouge |
| B. Empreinte des sources du module (fichiers du module ; pour un paquet installé, empreintes du `RECORD`, PEP 376 et PEP 627) | — | **rouge** : la fixture simule la « correction » par un attribut d'instance (`_text`, passé au constructeur hors `adapter_kwargs`), le source ne change pas | rouge ; vert si la bibliothèque enveloppée est hachée |
| C. Garde CI : une source modifiée sans version relevée fait échouer la CI | — | rouge : ne couvre ni un plugin ni un module `register()` local | rouge |
| D. Réglages effectifs déclarés par le module (prompt, température, `max_tokens` envoyés), version de la bibliothèque, révision des poids (`from_pretrained(revision=…)` de Hugging Face) | — | vert si l'état d'instance est exposé dans les réglages | vert si les clés s'appellent `prompt` et `temperature` |

- **Implications** :
  - `brique_modifiee` modélise une modification de code par un changement d'état. Son attendu n'est atteint que par D, ou par un mécanisme qui hache l'état d'instance. Pour tester B, il faut le reformuler avec deux classes de sources différentes, de même nom et de même version.
  - `prompt_et_temperature` exige des **noms de clés**. Il est à reformuler en test de comportement : l'identité doit changer quand le prompt ou la température envoyés changent.
- **Recommandation (non décidée)** : B + D, plus la version de la bibliothèque et la révision des poids ; C comme filet de sécurité pour le first-party.

### C18 — Provenance par unité (`served_models`, `code_version`)

- **Tests** : `test_pc_provenance.py::test_alias_modele__reprise_apres_bascule_attribue_le_modele_par_unite`, `::test_reprise_autre_code__resultat_dit_la_version_de_chaque_unite`.
- **Arbitrages** : 4 et 7 (« inconnu signalé pour les modèles distants »). **Tranchée en partie.**

| Option | Source | `alias_modele` | `reprise_autre_code` |
|---|---|---|---|
| **A. Attribution par unité** dans `DocumentUsage` (modèle servi, `code_version`, empreinte des dépendances ; « inconnu » explicite) | W3C PROV-O (2013) ; identifiants rendus par le fournisseur (champ `model` de Mistral, `system_fingerprint` d'OpenAI) | vert | vert |
| B. Refus d'une fusion hétérogène (comme pour les binaires) | Cinoc (binaires) | rouge : le modèle servi n'est connu qu'après l'appel, donc le refus impose de réexécuter d1, et `calls ≠ ["d2"]` | vert si le mélange est signalé dans `metadata` |
| C. Union au niveau du run + drapeau « mélange » | Cinoc (actuel, sans drapeau) | rouge | vert si `"1.0"` figure dans `metadata` |

- **Recommandation (non décidée)** : A. L'union peut rester comme résumé.

### C19 — Plan d'expérience de la campagne

- **Tests** : `test_pc_ablation.py::test_ablation_saknussemm__un_temoin_correction_libre_sur_la_meme_lecture[bnl|dresden]`, `::test_ablation_segmentation_vlm__meme_reglages_vlm_page_et_region[bnl|dresden]`.
- **Arbitrage** : aucun. L'arbitrage 8 porte sur le support des comparaisons, pas sur le plan. **Ouverte.**

| Option | Source | Témoin Saknussemm | VLM page/région (`max_tokens` 2048 / 1024) |
|---|---|---|---|
| **A. Ablation stricte** : chaque comparaison présentée comme réponse change un seul facteur ; témoins ajoutés | Lipton et Steinhardt 2019 (*Queue* 17) sur les ablations ; Melis, Dyer et Blunsom 2018 (ICLR) sur le contrôle des réglages | vert après ajout de `seg → tesseract:reco → lecture → mistral:correction` | vert si les réglages sont alignés |
| B. Facteurs confondants déclarés avec chaque comparaison | — (Cinoc n'a pas de type « comparaison ») | le test devrait lire la déclaration | idem |
| C. Réglages « équivalents » plutôt qu'identiques, dont on montre qu'ils ne limitent pas : taux de troncature nul dans les deux bras | troncature tracée par unité (`truncated`) | — | rouge tel qu'écrit, mais le défaut serait sans effet ; à vérifier sur les données de S31 |
| D. Plan factoriel complet (OCR × segmentation × correction) | Montgomery, *Design and Analysis of Experiments* | vert | vert |

- **Effet réel** : avant toute correction, E2 et E3 ne partent pas de la même lecture.
  - BNL : 0,0584 contre 0,0639 (Δ = 0,0055, ≈ 9 % relatif) ;
  - Dresden : 0,7563 contre 0,7775 (Δ = 0,021).

  Un écart E2/E3 de cet ordre n'est pas attribuable à la structuration. Le README consolidé indique que le témoin a été ajouté à S31.
- **Risques** : D coûte plus que le plafond de 10 € ne le permet. B laisse publier des comparaisons confondues.
- **Recommandation (non décidée)** :
  - le témoin (A) est indispensable pour la question Saknussemm : sans lui, elle ne peut pas recevoir de réponse ;
  - `max_tokens` est **à trancher** : aligner (A), ou démontrer qu'il ne limite pas (C).

---

## Tensions entre conventions et combinaison cohérente

**T1 — Page blanche : micro, test apparié et « n notés » (C01 × C05 × un test valide).** C'est la tension annoncée par le relecteur, et elle touche un test classé **valide** :
- `test_applicabilite__reference_vide_nest_pas_comptee_notee` affirme `agg.value == sum(cer_a)/6 = 0,05`, c'est-à-dire l'exclusion des pages blanches (C01-B) ;
- les tests valides de `metriques_stats` (`[cer]`, `[wer]`, `[ins_rate]`, `pipeline_qui_hallucine`) exigent leur inclusion (C01-A) ;
- sous C01-A, le micro de A vaut 12/120 = **0,100**, et la 1ʳᵉ assertion du test d'applicabilité échoue.

Les deux familles ne peuvent pas passer ensemble. La combinaison cohérente :
- micro sur comptes, pages blanches incluses : A 0,100, B 0,225 ;
- statut « référence vide » par page, donc pages exclues du macro et du test par document : Wilcoxon sur 6 pages, p = 0,031 (attendu du test discutable) ;
- test apparié **du micro** sur les 12 pages : permutation, p = 0,165. Cette perte de significativité est alors réelle, puisque A insère 6 caractères, et non fabriquée comme aujourd'hui (Wilcoxon sur valeurs 1,0/0,0 : p = 0,162) ;
- « n notés » dédoublé : 12 pages contribuent au micro, 6 au macro.

Le test valide doit donc être reformulé sur sa valeur. Son assertion sur le support reste juste pour le macro.

**T2 — Exactitude sur page blanche (C01 × C02).** L'attendu 0,0 de `[char_accuracy]` et de `[fca]` suppose à la fois C01-A (l'insertion compte) et C02-A (plancher au corpus). Sous C01-A et C02-B, on obtient −3,4.

**T3 — Échecs : agrégat, IC et test sur la même population (C07 × C08 × C05 × C06).**
- Sans imputation (C08-E), l'agrégat de classement, l'IC du Δ et le test portent sur le support commun.
- Avec la sensibilité « page vide » (C08-B), les trois portent sur toutes les pages.
- Mélanger les deux (agrégat sous une politique, test sous l'autre) reproduit l'incohérence actuelle : 7/8 au tableau, 7 cas au test.
- Un échec sur une page **blanche** imputé « page vide » vaut 0 édition, c'est-à-dire un silence parfait. C'est acceptable seulement si la couverture est affichée.

**T4 — Issue par étape et support commun (C12 × C07).** Avec des issues par étape, un même pipeline a des supports différents selon la vue : `lecture` 8/8, `texte` 7/8 si la correction échoue sur une page. Une ablation intra-pipeline (vue `lecture` contre vue finale, comme E2 en S31) doit elle aussi se comparer sur son support commun.

**T5 — Empreinte automatique contre archive relisible (C17 × C14 × C15 × C18).** Une empreinte des sources change la clé du cache à chaque modification de code. Si la renotation d'une archive recalculait les clés d'exécution avec le code courant, toute archive deviendrait « absente » après la moindre modification. La combinaison cohérente :
- la clé de cache = l'empreinte d'exécution courante ;
- l'archive = sorties scellées + provenance enregistrée par unité (C18) ;
- la renotation vérifie l'intégrité de l'archive (C14), pas les empreintes du code courant.

**T6 — Appariement puis ordre de lecture (C10 × C03).** Le τ se calcule sur les paires de blocs appariés. Passer à l'appariement global géométrique (C10, et les tests valides L3/L4) change ces paires, donc C10 se décide avant de chiffrer C03. Les blocs non appariés relèvent de `reading_order_coverage`, pas du τ.

**T7 — Grappes et tests par document (C09 × C05).** Le bootstrap par grappe corrige les IC micro. Le Wilcoxon par page suppose, lui, des pages échangeables et indépendantes. Avec des grappes déclarées, le test par document devrait porter sur des agrégats par grappe, ou être stratifié. Ce point n'est pas arbitré. Avec 5 grappes BNL dont un singleton, la puissance serait très faible, et Dresden (1 grappe) n'a pas de test inter-grappes possible.

**Combinaison cohérente d'ensemble** :
- comptes additifs avec finalisation par métrique : C01-A, C02-A, C03-A, C04-A ;
- micro et macro publiés et nommés, chacun avec son test et son IC apparié sur le support commun : C05, C06 ;
- aucune imputation par défaut, couverture affichée, « page vide » en sensibilité : C07, C08 ;
- grappes déclarées : C09 ;
- appariement hongrois par page avant le τ : C10 ;
- alignement LCS pour la calibration : C11 ;
- issue et reprise par préfixe d'étapes : C12 ;
- statuts typés : C13 ;
- archive BagIt + RO-Crate séparée du cache, empreinte d'image obligatoire : C14, C15 ;
- refus du fan-out multipage à image unique : C16 ;
- empreinte des sources + réglages effectifs : C17 ;
- provenance par unité : C18 ;
- témoin obligatoire pour la question Saknussemm : C19.

Sous cette combinaison, **ces tests sont à reformuler, et non à rendre verts tels quels** :
- `test_omnibus__meme_sens…`, `test_omnibus__p_du_ratio_micro…` (C05) ;
- `intervalles__meme_documents…` (C06) ;
- `echec_non_aleatoire__classement…` (C07) ;
- `max_error__un_echec_ne_note_jamais_mieux…` (C08) ;
- `bootstrap__grappes…` (C09, noms de champ) ;
- `version_manuelle__brique_modifiee…`, `identite_saknussemm__prompt…` (C17) ;
- le test valide `reference_vide_nest_pas_comptee_notee` (T1, sur sa valeur).
