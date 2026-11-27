# Classement des tests rouges par le relecteur indépendant (contre-expertise 04a1c17b)

V = valide sans réserve ; D = valide mais discutable (choix documenté contesté, ou attendu exact dépendant d'une convention) ; I = invalide (retiré : `test_ablation_saknussemm__e2_et_e3_partent_de_la_meme_sortie_ocr[bnl|dresden]`).
Totaux après retrait : 90 rouges = 51 V + 39 D.

## metriques_stats (10 V, 11 D)
| Test | Classe | Justification |
|---|---|---|
| reference_vide…[cer] | V | Page blanche (poids 0) disparaît : 0,0 ; jiwer corpus 44/10 ; `metric.py` revendique « Σ erreurs / Σ dénominateurs, comparable à jiwer » |
| reference_vide…[wer], [ins_rate] | V | 0 au lieu de 7 |
| reference_vide…[char_accuracy], [fca] | D | 1,0 affiché pour un moteur qui invente ; l'attendu exact (0,0) suppose un plancher au niveau corpus ; un test « < 1 » serait inattaquable |
| pipeline_qui_hallucine_est_classe_apres | V | 0,0 vs 0,1 au lieu de 4,4 vs 0,1 |
| ner_f1__micro…[ner_f1], [ner_f1_exact] | V | 0,9256 (moyenne de F1 pondérée) vs 0,7097 dans l'analyse NER du même résultat |
| ner_f1__faux_positifs_sur_document_sans_entite_gt | V | poids nul : 8 FP invisibles, 1,0 au lieu de 1/3 |
| ner_payload__label_absent_de_la_gt | V | plantage `support >= 1` (`ner.py:338`) |
| region_detection__micro… | V | 0,9256 au lieu de 0,7097 |
| bow_f1__micro… | V | 0,9256 alors que P (11/20) et R (1) affichés donnent 0,7097 |
| reading_order_tau__micro_sur_paires | D | poids = blocs = unité déclarée `REGION` (D-289) ; le test choisit les paires ; contredit seulement la docstring d'`Observation` |
| char_accuracy__vaut_un_moins_cer_corpus | D | exception documentée (`text.py:247-248`, plancher 0 par doc) ; incohérence d'affichage réelle 0,833 vs 0,5 |
| line_identity_cer__ligne_fantome… | D | convention (D-288 ne visait que `region_cer` ; `lines.py` ignore les lignes en trop) |
| test_omnibus__meme_sens_que_le_cer_micro_affiche | D | Simpson vérifié ; mais procédure documentée (Demšar) teste les valeurs par document |
| test_omnibus__p_du_ratio_micro_par_permutation… | D | p = 1 confirmé ; exige un autre test que le Wilcoxon documenté |
| intervalles__ic_apparie_sur_la_difference_micro | D | absence d'IC apparié = manque de fonctionnalité ; IC marginaux documentés (`inference.py:_intervals`) |
| echec_non_aleatoire__classement_sur_documents_communs | D | politique `exclude` par défaut documentée (A3), affiche 7/8 |
| intervalles__meme_documents_que_le_test | D | IC marginaux documentés (`inference.py:245`, `analysis.py:48`) |
| bootstrap__grappes_documentaires_declarables | D | manque de fonctionnalité, vérifié par nom de paramètre seulement |

## applicabilite_echecs (10 V, 7 D)
| Test | Classe | Justification |
|---|---|---|
| artefact_sans_contenu…reste_attendu | V | `uri=None` accepté ; unité ok, 2/2, document b disparaît |
| artefact_reference_mais_absent_du_disque… | V | `EvaluationError`, tout le run perdu |
| gt_referencee_mais_absente_refusee_avant_de_payer | D | le chargeur YAML refuse déjà (`loader.py:121-130`) ; le test construit `CorpusSpec` à la main |
| fanout_sans_aucune_region_reconnue_reste_attendu | D | convention documentée (CLAUDE.md §3 « niveau absent → None ») |
| fanout_entierement_en_echec_nest_pas_une_unite_ok | V | toutes les régions en échec : unité ok sans message |
| pipeline_non_applicable_nannule_pas_le_test_des_autres | V | cas complets à 0 ; p de référence 0,0078 |
| reference_vide_nest_pas_comptee_notee | V | 12 notés pour un agrégat sur 6 |
| reference_vide_nentre_pas_dans_le_test_apparie | D | p = 0,1616 reproduit ; convention 1,0/0,0 documentée (`_error_rate`) ; en tension avec metriques_stats |
| sortie_incompatible_refusee_ou_attendue | V | 0/0 sans signal |
| echec_partiel__lamont_reussi_reste_observable | D | choix délibéré de `DocumentExecution` (test vert le confirme) |
| echec_partiel__le_cout_amont_reste_compte_a_lunite | V | 500/200/1 perdus |
| echec_partiel__le_bilan_economique_compte_lamont_paye | V | 1100 au lieu de 1600 |
| echec_partiel__pipeline_tout_en_echec_garde_sa_facture | V | `if not entries: continue` contredit son commentaire |
| echec_partiel__la_reprise_ne_repaie_pas_lamont | D | cache par unité documenté |
| max_error__un_echec_ne_note_jamais_mieux… | D | la spec promet « 1 pour un taux d'erreur » ; exigence normative |
| max_error__echec_note_comme_une_page_vide[ins_rate] | D | doc contradictoire (« 1 » vs « comme une page vide » = 0) |
| max_error__un_echec_compte_comme_note_deplace_lagregat | V | bow_precision : poids 0, compté 3/3, effet nul |

## artefacts_archive (7 V, 7 D)
| Test | Classe | Justification |
|---|---|---|
| a5_meme_adaptateur_deux_etapes__fichier_de_chaque_etape_conserve | V | même chemin, écrasement (usage documenté PLUGINS.md) |
| a5_…chaque_vue_notee_sur_sa_sortie | V | CER 1,0 au lieu de 0 |
| a5_archive__empreinte…egale_hash_enregistre | V | fichier écrasé copié, ancien hash |
| a5_relecture_offline__chaque_etape_relit_son_propre_fichier | V | même cause |
| a5_socle_tesseract_avant_apres_redressement… | V | reproduit sur le socle |
| a7_octet_change_dans_une_sortie… | D | `content_hash` jamais vérifié, mais aucune promesse d'intégrité documentée |
| a7_index_json_valide_mais_altere… | D | idem |
| a7_image_partagee_corrompue… | D | aucun effet sur les scores hors ligne |
| a7_uri_absolue_hors_archive__refusee | V | la raison écrite pour `..` vaut pour l'absolu |
| a7_lien_symbolique_hors_archive__refuse | V | `normpath` ne résout pas les liens |
| a7_relecture_offline_image_distante__aucun_telechargement | D | limite connue documentée (PLAN_FIN_MIGRATION.md:678) |
| a7_relecture_offline_serveur_d_images_eteint… | D | idem |
| a7_archive_seule_sans_images_du_corpus__reevaluable | D | clé dérivée de l'image du corpus, documenté |
| a7_archive_publiee__une_reprise_normale_ne_la_modifie_pas | D | documenté (« une reprise normale les ré-exécute ») |

## layout_analyses (17 V, 6 D)
| Test | Classe | Justification |
|---|---|---|
| correction_vue_cible_ocr__pas_de_bilan_hors_du_prefixe_evalue | V | pool final (D-276) ; calibration corrigée pour la même raison (D-281 D9) |
| correction_vue_cible_correction__lit_la_sortie_de_cette_etape | V | bilan juge `refine` |
| correction_etape_brute_en_aval__le_brut_est_l_entree_du_correcteur | V | brut = texte reprojeté en aval |
| decisions_vue_cible_ocr…, decisions_vue_cible_correction… | V | pool final |
| economie_vue_cible_ocr__ne_facture_pas_l_etage_llm | D | fixture sans usage par étape ; `None` défendable, pas démontré |
| calibration_mots_permutes…, calibration_mot_repete_deplace… | D | attendus justes (0,45 ; 0,19) mais multi-ensemble documenté (`calibration.py:13-17`) |
| glouton_vs_optimal__la_detection_atteint_l_optimum_global | D | glouton documenté, convention courante en détection |
| glouton_vs_optimal__region_cer_suit_l_appariement_optimal | D | idem |
| ordre_des_regions_de_reference__la_detection_n_en_depend_pas | V | F1 dépend de l'ordre du fichier |
| ordre_des_regions_hypothese__egalite_d_iou_sans_effet_d_ordre | V | départage `>=` |
| ids_identiques_non_homologues__appariement_par_geometrie | V | 8/9 ; prémisse « deux systèmes ne partagent jamais leurs id » fausse |
| ids_partiellement_partages__la_region_non_nommee_reste_appariee | V | un id commun désactive la géométrie |
| multipage_detection__pas_d_appariement_entre_pages | V | pages aplaties |
| multipage_mise_en_page_repetee… | V | 8/9 au lieu de 0 |
| multipage_ids_locaux_a_la_page… | V | dict par id écrase la page 1 |
| alto_sans_id__appariement_par_geometrie_et_ordre_inverse_detecte | V | `region_0/1` des deux côtés |
| ordre_de_lecture_imbrique__la_projection_d_evaluation_le_respecte | V | premier niveau seulement |
| deux_projections__meme_layout_meme_texte | V | « \n\n » vs « \n » |
| deux_projections__ordre_imbrique_identique | V | ordre inversé |
| deux_projections__candidat_parfait_cer_nul_vue_lignes | V | CER 4/28 |
| fanout_multipage__une_page_n_est_pas_lue_dans_l_image_d_une_autre | D | mécanisme réel mais montré sans découpeur |

## provenance_campagne (7 V, 8 D ; 2 I retirés)
| Test | Classe | Justification |
|---|---|---|
| ablation_saknussemm__un_temoin_correction_libre…[bnl], [dresden] | D | constat exact, mais aucune question déclarée de P5h ne l'exige (recommandation de méthode) |
| ablation_segmentation_vlm__meme_reglages…[bnl], [dresden] | D | max_tokens 1024/2048 documenté ; facteur seulement si troncature (tracée) |
| identite_gt__deux_gt_differentes_donnent_deux_manifestes | V | aucune empreinte de GT |
| identite_gt__resultat_porte_empreinte_de_chaque_gt | V | idem |
| identite_image__resultat_porte_empreinte_de_chaque_image | V | hachée dans la clé seulement |
| identite_gt__renotation_hors_ligne_contre_autre_gt_signalee | V | idem |
| identite_gt__run_result_publie_porte_les_gt… | V | vérifié autrement que par la sonde « .gt.txt » |
| alias_modele__reprise_apres_bascule_attribue_le_modele_par_unite | D | `served_models` documenté comme union |
| version_manuelle__brique_modifiee_sans_relever_sa_version… | D | contrat voulu (CLAUDE.md §3, contrepartie 3) |
| version_manuelle__identite_saknussemm_porte_la_version_de_la_bibliotheque | V | seule la version de l'adaptateur (1.1) |
| identite_saknussemm__prompt_et_temperature… | D | exige des clés précises et suppose ce que la bibliothèque envoie |
| identite_saknussemm__poids_du_scoreur_qe_epingles | V | `from_pretrained` sans révision |
| reprise_autre_code__resultat_dit_la_version_de_chaque_unite | D | exclusion documentée (D-279) |

## Causes communes (relecteur)
1. poids nul de la référence vide (+ « n notés » gonflé) — 7 tests ; 2. F1 en moyenne pondérée au lieu de micro — 5 ; 3. écrasement même label deux étapes — 5 ; 4. pool final au lieu de l'étape ciblée — 5 ; 5. appariement par id dès un id partagé — 3 ; 6. aplatissement multipage — 3 ; 7. aucune empreinte GT/image dans `RunResult` — 5 ; 8. coût amont perdu quand l'unité échoue — 3.

## Tension signalée
`metriques_stats` veut compter l'hallucination sur page blanche dans le CER micro ; `applicabilite` veut exclure les pages blanches du Wilcoxon. Compatibles seulement si le test apparié ne porte pas sur le CER par document.
