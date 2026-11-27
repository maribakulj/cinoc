# Contre-expertise — applicabilité et politique d'échec (`applicabilite_echecs`)

Copie figée `04a1c17b`. Tests : `tests/adversarial/applicabilite_echecs/` (`_kit.py` + 3 fichiers). Les briques de test sont des modules tiers (`Module` Protocol, imports de `cinoc.adapters.extension`), branchées par `discover_plugins` avec un chargeur d'entry-points simulé. Les runs passent par `cinoc.app.run`. Les références indépendantes sont une distance d'édition écrite à la main, `scipy.stats.wilcoxon`, et la valeur que la métrique donne elle-même à une page vide. Aucun monkeypatch du produit.

**Synthèse.** Le défaut central est confirmé : « n attendus » (`MetricScore.expected`) n'augmente **que** pour une unité `failed`. Toute unité **réussie** qui ne fournit pas ce que la vue exige sort en silence des deux compteurs. Elle reçoit `value=None`, `support` ne la compte pas, `expected` non plus, et l'issue reste `ok`. J'ai observé ce défaut par cinq chemins différents (artefact sans contenu, sortie incompatible, pipeline hors vue, fan-out entièrement en panne, hypothèse de layout sans texte). Par ailleurs, la règle `max_error` est déduite de `higher_is_better` seul (`runner.py:409`), et elle est fausse pour les métriques non bornées. Enfin, un échec aval efface l'amont : artefacts, coûts, évaluation et reprise.

---

## A. Affirmation 2 — applicabilité

### A1. Unité réussie dont l'artefact n'a pas de contenu
| champ | contenu |
|---|---|
| Affirmation | n attendus ne doit pas diminuer en silence quand une unité réussie ne fournit pas l'information |
| Verdict | **confirmé** |
| Contre-exemple | 3 pages avec GT. Le moteur rend pour `b` un artefact `RAW_TEXT` déclaré, avec `uri=None` (forme autorisée par `Artifact`). Test : `test_ce_applicabilite.py::test_applicabilite__artefact_sans_contenu_dune_unite_reussie_reste_attendu` |
| Comportement actuel | CER **0,0** sur **2/2**, issue de `b` = `ok`. La page `b` (sortie fausse `zzzz`) disparaît du numérateur comme du dénominateur. |
| Comportement attendu | 2/3, ou une issue non-`ok`. Une page avec GT pour laquelle le moteur n'a rien rendu de lisible est une page attendue. |
| Tests existants | `tests/app/test_unit_outcome.py` ne couvre que les unités `failed`. |
| Cause architecturale | `runner.py:149-159` : `missed` n'est incrémenté que dans la branche `failed`. Ensuite `_context_for` (`runner.py:526-533`) rend `None` sans motif, et `_aggregate` (`runner.py:307-327`) calcule `expected = support + missed`. **Même cause que A4, A5, A6 et A7.** |
| Gravité | Le CER publié peut être aussi bon qu'on veut : chaque page sans contenu est retirée. Ici 0,0 au lieu de 0,333. |

### A2. Artefact référencé mais absent du disque
| champ | contenu |
|---|---|
| Affirmation | idem (« artefact référencé mais manquant sur disque ») |
| Verdict | **confirmé** (ce n'est pas silencieux, mais la portée est fausse) |
| Contre-exemple | Le pipeline `p` rend pour `b` une URI vers un fichier jamais écrit ; le pipeline `q` est sain. Test : `…::test_applicabilite__artefact_reference_mais_absent_du_disque_nabat_que_son_unite` |
| Comportement actuel | `EvaluationError: représentation illisible (raw_text)` : **tout le `RunResult` est perdu**, alors que les 4 unités ont déjà été exécutées (`['a','b','a','b']`). |
| Comportement attendu | Seule l'unité `p × b` est classée (« artefact absent »). `q` est noté sur 2/2 et `p` sur n/2. |
| Tests existants | aucun |
| Cause architecturale | `evaluation/representations.py:37-43` lève une exception au niveau du run. Ni `executor._check_outputs` (`executor.py:276-284`) ni l'orchestrateur ne vérifient que le contenu existe. |
| Gravité | Pas de chiffre faux, mais une campagne facturée est perdue sans `--resume-dir`. |

### A3. Vérité terrain référencée mais absente
| champ | contenu |
|---|---|
| Affirmation | distinguer « GT absente » d'un échec |
| Verdict | **confirmé** |
| Contre-exemple | La GT de `b` pointe vers un fichier inexistant. Test : `…::test_applicabilite__gt_referencee_mais_absente_refusee_avant_de_payer` |
| Comportement actuel | Le moteur est exécuté sur `['a','b']`, **puis** `EvaluationError` survient et tout le run est perdu. |
| Comportement attendu | Un refus **avant** d'exécuter le moindre moteur, puisque la GT est connue dès le chargement. À défaut, le document est classé « GT illisible » et le reste est noté. |
| Tests existants | aucun |
| Cause architecturale | `representations.py:37-43`, appelé depuis `_reference_for` (`runner.py:345-354`). Rien ne valide les GT avant `orchestrator.run`. |
| Gravité | Coût payé pour rien. Pas de chiffre faux. |

### A4. Fan-out : toutes les régions en échec, unité « ok »
| champ | contenu |
|---|---|
| Affirmation | idem (unité réussie sans layout exploitable) |
| Verdict | **confirmé** (deux symptômes) |
| Contre-exemple | Segmenteur tiers à 2 régions, reconnaisseur qui lève `AdapterStepError("503")` sur chaque région de la page `panne`. Vue `LAYOUT` avec `region_cer`. Tests : `…::test_applicabilite__fanout_sans_aucune_region_reconnue_reste_attendu` et `…::test_applicabilite__fanout_entierement_en_echec_nest_pas_une_unite_ok` |
| Comportement actuel | `region_cer(panne) = None`, agrégat calculé sur **1/1**, issue `ok`, message `None`. Le seul signal est un `logger.warning`. |
| Comportement attendu | La page compte (CER 1, ou 1/2 attendus), et l'issue dit que des régions ont échoué. |
| Tests existants | `tests/pipeline/test_fanout.py::test_a_failing_region_does_not_abort_the_page` vérifie que la page survit, pas que l'échec soit tracé. |
| Cause architecturale | `pipeline/fanout.py:230-235` avale l'erreur sans rien remonter dans le `StepOutput`. `evaluation/metrics/layout.py:92` rend `None` quand c'est l'**hypothèse** qui n'a pas de niveau texte : une hypothèse vide est confondue avec une métrique inapplicable. S'y ajoute la même cause que A1. |
| Gravité | Le `region_cer` publié exclut précisément les pages où l'API distante est tombée (quotas, 5xx) : le biais est favorable. Les échecs partiels de région sont eux aussi invisibles (unité `ok`). |

### A5. Sortie incompatible avec la vue
| champ | contenu |
|---|---|
| Verdict | **confirmé** |
| Contre-exemple | Vue `candidate_types={raw_text, layout}` qui note un CER, **sans** projection `layout→raw_text`. Le pipeline `seg` (réussi) ne rend que `layout`. Test : `…::test_applicabilite__sortie_incompatible_refusee_ou_attendue` |
| Comportement actuel | La spec est acceptée. `seg` obtient `None` sur **0/0**, issues `['ok','ok']` : on ne peut pas le distinguer d'un pipeline hors sujet. |
| Comportement attendu | Un refus au chargement (la jonction n'a pas de pont), ou 0/2. |
| Cause architecturale | `RunSpec._check_view_targets` (`domain/run_spec.py:37-63`) ne vérifie pas les projections. `_project_side` (`runner.py:572-574`) rend `None` sans motif. |
| Gravité | La comparaison est vide sans le dire. Combiné à A6, elle supprime aussi les tests des autres pipelines. |

### A6. Un pipeline non applicable annule les tests de significativité des autres
| champ | contenu |
|---|---|
| Verdict | **confirmé** |
| Contre-exemple | `A` (1 erreur/page) et `B` (2 à 9 erreurs) sur 8 pages, plus un pipeline `C` qui ne rend que `corrected_text` (vue texte = `raw_text`). Test : `…::test_applicabilite__pipeline_non_applicable_nannule_pas_le_test_des_autres` |
| Comportement actuel | `test=None`, `not_computed='insufficient_support'`, **0** cas complets. Oracle : `scipy.stats.wilcoxon(A,B).pvalue = 0,0078`. |
| Comportement attendu | Wilcoxon A/B, p = 0,0078. `C` est écarté de la famille. |
| Cause architecturale | `runner.py:146-148` crée une série pour **chaque** pipeline du run ; `inference.omnibus_test` (`inference.py:116-122`) exige ensuite une valeur de tous les pipelines. Le motif affiché (« support insuffisant ») est faux : la vraie raison est « un pipeline n'est pas applicable ». |
| Gravité | **Élevée et réaliste.** Une campagne d'ablation (P5h) qui mêle un pipeline segmentation-seule ou ALTO-seul à des OCR perd tous ses verdicts, et le rapport attribue cette perte au corpus. |

### A7. Référence vide (page blanche)
| champ | contenu |
|---|---|
| Verdict | **confirmé** |
| Contre-exemple | 6 pages de texte où `A` fait moins d'erreurs que `B`, et 6 pages blanches (GT `""`) où `A` rend `.` et `B` rien. Tests : `…::test_applicabilite__reference_vide_nest_pas_comptee_notee` et `…::test_applicabilite__reference_vide_nentre_pas_dans_le_test_apparie` |
| Comportement actuel | Agrégat `A` = 0,05 (correct, calculé sur les 6 pages de texte), mais **n notés = 12/12**. Le Wilcoxon est fait sur **12** cas, où une valeur fabriquée 1,0 est comparée à 0,0 sur les pages blanches : **p = 0,162**, rangs moyens à égalité (1,5 / 1,5). |
| Comportement attendu | 6 notés. Le test sur les 6 pages de texte donne p = 0,031 selon `scipy` (significatif). Un CER x/0 est indéfini (jiwer refuse une référence vide). |
| Cause architecturale | Les métriques texte rendent `Observation(value=0\|1, weight=0)` pour une référence vide. `_aggregate` compte `support=len(pairs)` sans regarder le poids (`runner.py:319-327`), et `_inference_entries` (`runner.py:290-302`) transmet la valeur. L'IC, lui, écarte les poids nuls (`inference.py:252`) : l'agrégat, le test et l'IC utilisent donc trois populations différentes. |
| Gravité | **Élevée.** Les pages blanches (versos, gardes, plats) sont courantes dans les corpus patrimoniaux. Un écart significatif disparaît (0,031 → 0,162), et plus de pages blanches peuvent inverser le sens du test. |

### A8. Repères (verts : réfutent un défaut sur ces cas)
- `…::test_gt_absente__ni_notee_ni_attendue` : une GT absente donne `None`, hors de n notés **et** de n attendus. Correct.
- `…::test_troncature__notee_attendue_et_signalee` : une sortie coupée par `max_tokens` est notée (CER exact calculé à la main), comptée 2/2, et l'issue vaut `truncated`. Correct. Dans ce domaine, la troncature est la seule non-mesure bien traitée. Non testé : l'issue `truncated` vaut pour toute l'unité, et une vue `target_step` qui note une étape amont complète hérite de ce drapeau.

## B. Affirmation 2 (suite) — règle `max_error`

**Où elle est déduite** : `evaluation/runner.py:409`, `worst = 0.0 if metric.spec.higher_is_better else 1.0`. `MetricSpec` (`domain/evaluation.py:106`) ne déclare ni bornes ni pire valeur. Le runner calcule pourtant `metric.fn(page vide)` (`runner.py:397-405`) : il en garde le poids et **jette la valeur**.

| champ | B1. CER non borné | B2. `ins_rate` | B3. `bow_precision` |
|---|---|---|---|
| Verdict | **confirmé** | **confirmé** | **confirmé** |
| Contre-exemple | `panne` échoue sur `b`, `bavard` y hallucine (`"zq"×30`), les autres pages sont parfaites. `test_ce_max_error.py::test_max_error__un_echec_ne_note_jamais_mieux_quune_reponse` | Même scène. `…::test_max_error__echec_note_comme_une_page_vide[ins_rate]` | Même scène. `…::test_max_error__un_echec_compte_comme_note_deplace_lagregat` |
| Actuel | Échec noté **1,0**, hallucination **2,767** (calculée à la main). Agrégats : `panne` 0,333 et `bavard` 0,922, donc **échouer classe mieux que répondre**. | Échec 1,0, page vide **0,0** (poids 7 dans les deux cas). | Échec noté 0,0 avec **poids 0**, compté 3/3, agrégat **1,0**, identique à celui sans l'échec. |
| Attendu | La « pire » valeur doit être au moins aussi mauvaise que toute valeur atteignable, ou alors la règle doit s'appeler « page vide » et le dire. | La doc promet « comme une page rendue vide » : on attend 0,0. | Un échec compté parmi les notés doit peser, sinon il ne doit pas être compté. |

Les 11 autres métriques testées (`cer`, `wer`, `mer`, `cmer`, `del_rate`, `char_accuracy`, `word_accuracy`, `bow_recall`, `bow_f1`, `searchability`, `numseq_value`) sont **vertes** : pour elles, la constante coïncide avec la page vide. La déduction est donc juste dans la majorité des cas, et fausse exactement pour les métriques non bornées ou pondérées par l'hypothèse.

- **Tests existants** : `tests/app/test_unit_outcome.py::test_max_error_scores_the_failure_like_an_empty_page` et `…::test_max_error_is_zero_for_a_higher_is_better_metric` ne testent que `cer` (où vide = 1) et `char_accuracy` (où vide = 0). Ce sont les deux seuls cas où la constante est juste.
- **Gravité** : avec `max_error`, un VLM qui boucle (CER > 1, fréquent) est classé derrière un moteur qui échoue. Le choix de la politique peut donc inverser un classement. `ins_rate` et `bow_precision` sont des métriques adaptées : elles ne sont pas classées, mais elles sont affichées.

## C. Affirmation 6 — échecs partiels (OCR réussi et facturé, puis LLM en panne)

Le scénario : la brique `ce_ocr` (500/200 jetons, 1 page) puis la brique `ce_llm`, qui lève `AdapterStepError(billed=300 jetons)` sur `b`. Fichier : `test_ce_echecs_partiels.py`.

| Point vérifié | Test | Actuel | Attendu | Verdict |
|---|---|---|---|---|
| Le type interdit les artefacts d'une unité `failed` | `…::test_echec_partiel__le_type_interdit_bien_les_artefacts_dune_unite_failed` | lève `CinocError` | (constat) | **affirmation exacte** (vert) |
| Artefacts et observations de l'amont conservés, vue `target_step: ocr` | `…::test_echec_partiel__lamont_reussi_reste_observable` | CER OCR de `b` = **None** | 0,10 (calculé à la main) | **confirmé** |
| Coût amont dans la ligne `usage` | `…::test_echec_partiel__le_cout_amont_reste_compte_a_lunite` | `tokens_in=300`, `tokens_out=None`, `billed_pages=None` | 800 / 200 / 1 | **confirmé** |
| Bilan économique du run | `…::test_echec_partiel__le_bilan_economique_compte_lamont_paye` | `tokens_in` = **1100** | 1600 (−31 %) | **confirmé** |
| Pipeline dont toutes les unités ont échoué | `…::test_echec_partiel__pipeline_tout_en_echec_garde_sa_facture` | **aucune ligne** au bilan, alors que 600 jetons sont facturés | une ligne | **confirmé** |
| Reprise de l'aval seul (`--resume-dir`) | `…::test_echec_partiel__la_reprise_ne_repaie_pas_lamont` | OCR de `b` appelé **2 fois** (l'unité réussie `a` est bien reprise) | 1 fois | **confirmé** |

- **Tests existants** : `tests/app/test_resumed_units.py::test_a_failed_unit_keeps_what_it_got_billed_through_the_archive` et `tests/evaluation/test_economics.py::test_a_failed_unit_s_billed_consumption_is_paid_not_processed` couvrent un pipeline **à une étape**, où `billed` est toute la consommation. Le cas multi-étapes n'est jamais construit.
- **Cause architecturale (unique)** :
  - L'issue est portée par l'**unité**, pas par l'étape. `PipelineExecutor.execute_document` (`pipeline/executor.py:119-151`) n'attrape rien : l'exception sort avec `by_step` et `step_usage` en variables locales.
  - L'orchestrateur (`app/orchestrator.py:333-347`) reconstruit `DocumentExecution.failed(..., billed=exc.billed)`, c'est-à-dire la seule étape fautive. Le type l'impose : `pipeline/types.py:96-99` interdit `by_step` si l'issue est `failed`, et `billed` remplace toute la consommation (`types.py:111-112`).
  - La reprise est adressée par unité : `unit_key` (`app/resume.py:130`), et `load` ne rend jamais une unité en échec en reprise normale (`resume.py:222-231`). On ne peut donc reprendre qu'à partir de zéro.
  - `economics.py:309-311` saute un pipeline sans unité non-`failed`.
- **Gravité** : le coût d'un pipeline OCR→LLM est sous-estimé en proportion de son taux d'échec aval (ici −31 %), et le rapport coût/qualité est biassé en faveur des correcteurs fragiles. L'ablation « OCR seul / OCR+LLM » dans le même run (que permet `target_step`) perd les pages où le LLM a échoué, et uniquement celles-là : les deux bras ne sont plus évalués sur les mêmes pages.

---

## Catégories de non-mesure

| Catégorie | Représentation actuelle | n attendus | n notés | agrégat | tests stat. | correcte ? |
|---|---|---|---|---|---|---|
| GT absente (aucune GT du type) | `MetricScore.value=None`, `support=None` (par document) | non compté | non | exclue | exclue (cas incomplet, pour tous) | **oui** |
| GT référencée, fichier absent | `EvaluationError` levée, run perdu | — | — | — | — | **non** (A3) |
| Référence vide (page blanche) | `value=0\|1`, `support=0` | compté | **compté** | exclue (poids 0) | **incluse, valeur fabriquée** | **non** (A7) |
| Métrique inapplicable côté référence (`Observation=None`) | `value=None` | non compté | non | exclue | exclue | **oui** |
| Hypothèse vide de niveau (layout sans texte) | `value=None`, comme une métrique inapplicable | non compté | non | exclue | exclue | **non** (A4, confondue avec la ligne au-dessus) |
| Sortie incompatible (pas de projection) | `value=None` sans motif, spec acceptée | non compté | non | exclue | annule les tests des autres | **non** (A5) |
| Pipeline hors vue (aucun type candidat) | `None` partout, 0/0 | 0 | 0 | `None` | **annule les tests des autres** (« support insuffisant ») | **non** (A6) |
| Artefact sans contenu (`uri=None`), unité `ok` | `value=None`, issue `ok` | **non compté** | non | exclue | exclue | **non** (A1) |
| Artefact référencé absent du disque | `EvaluationError`, run perdu | — | — | — | — | **non** (A2) |
| Troncature (`max_tokens`) | `DocumentUsage.outcome="truncated"` + message (par unité) | compté | compté | incluse | incluse | **oui** (drapeau par unité, pas par étape) |
| Échec d'unité, `exclude` | `DocumentUsage.outcome="failed"` + `reason`, `value=None` | compté | non | exclue | exclue pour tous (cas complets, montré par `n_documents`) | **oui** (choix documenté, avec un biais de survie à savoir lire) |
| Échec d'unité, `max_error` | `value` = 0/1 selon `higher_is_better`, poids de la page vide | compté | compté | incluse | incluse | **non** (B1-B3) |
| Échec partiel (amont réussi, aval en échec) | identique à « échec d'unité » | compté | non | exclue, **y compris la vue de l'étape amont** | exclue | **non** (C) |
| Région en échec dans un fan-out | région sans ligne, unité `ok`, journal seulement | compté | compté (texte), **non** (`region_cer` si toutes échouent) | inclus comme des suppressions, ou exclu | idem | **non** (A4) |
| Délai / annulation | `failed`, `reason="cancelled"` | comme un échec | | | | non testé ici (même chemin que l'échec d'unité) |

Le nœud commun : `MetricScore.value=None` code au moins **six** situations distinctes, et seul le chemin `failed` sait les distinguer, grâce à `DocumentUsage`. Pour une unité réussie, aucun champ ne dit *pourquoi* il n'y a pas de score.

---

## Sortie `pytest`

```
$ cd contre-expertise && ce-venv/bin/python -m pytest -q -p no:cacheprovider tests/adversarial/applicabilite_echecs
FAILED tests/adversarial/applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__artefact_sans_contenu_dune_unite_reussie_reste_attendu
FAILED tests/adversarial/applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__artefact_reference_mais_absent_du_disque_nabat_que_son_unite
FAILED tests/adversarial/applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__gt_referencee_mais_absente_refusee_avant_de_payer
FAILED tests/adversarial/applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__fanout_sans_aucune_region_reconnue_reste_attendu
FAILED tests/adversarial/applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__fanout_entierement_en_echec_nest_pas_une_unite_ok
FAILED tests/adversarial/applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__pipeline_non_applicable_nannule_pas_le_test_des_autres
FAILED tests/adversarial/applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__reference_vide_nest_pas_comptee_notee
FAILED tests/adversarial/applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__reference_vide_nentre_pas_dans_le_test_apparie
FAILED tests/adversarial/applicabilite_echecs/test_ce_applicabilite.py::test_applicabilite__sortie_incompatible_refusee_ou_attendue
FAILED tests/adversarial/applicabilite_echecs/test_ce_echecs_partiels.py::test_echec_partiel__lamont_reussi_reste_observable
FAILED tests/adversarial/applicabilite_echecs/test_ce_echecs_partiels.py::test_echec_partiel__le_cout_amont_reste_compte_a_lunite
FAILED tests/adversarial/applicabilite_echecs/test_ce_echecs_partiels.py::test_echec_partiel__le_bilan_economique_compte_lamont_paye
FAILED tests/adversarial/applicabilite_echecs/test_ce_echecs_partiels.py::test_echec_partiel__pipeline_tout_en_echec_garde_sa_facture
FAILED tests/adversarial/applicabilite_echecs/test_ce_echecs_partiels.py::test_echec_partiel__la_reprise_ne_repaie_pas_lamont
FAILED tests/adversarial/applicabilite_echecs/test_ce_max_error.py::test_max_error__un_echec_ne_note_jamais_mieux_quune_reponse
FAILED tests/adversarial/applicabilite_echecs/test_ce_max_error.py::test_max_error__echec_note_comme_une_page_vide[ins_rate]
FAILED tests/adversarial/applicabilite_echecs/test_ce_max_error.py::test_max_error__un_echec_compte_comme_note_deplace_lagregat
17 failed, 14 passed in 4.75s
```
17 rouges (défauts confirmés) et 14 verts : GT absente, troncature, interdiction d'artefacts dans le type, et 11 métriques pour lesquelles `max_error` donne bien la valeur de la page vide.

## Contrats en cause

- **`MetricScore` (`evaluation/result.py:31-46`) avec `expected` : à revoir.** `value=None` sans motif ne permet pas de distinguer les six non-mesures du tableau. `expected` est défini par la seule issue `failed`, ce qui exclut en silence toute unité réussie mais inexploitable. Il faut un statut typé par score (GT absente, référence vide, inapplicable, sortie incompatible, sortie manquante, échec), et `expected` doit dériver de la GT pour **chaque** unité, comme le fait déjà `_expects`.
- **`MetricSpec` et la règle `max_error` (`domain/evaluation.py:106`, `runner.py:409`) : réparables localement.** Il suffit de noter l'échec à la valeur que la métrique rend pour la page vide, valeur que le runner calcule déjà puis jette. Il faut aussi soit renommer la politique (« page vide »), soit déclarer une borne pour chaque métrique ; un CER non borné n'a pas de « maximum ».
- **Sélection des cas pour les tests (`runner._inference_entries`, `inference.omnibus_test:116`) : réparable localement.** Il faut écarter les pipelines sans aucun document applicable et les documents à poids nul, pour que l'agrégat, l'IC et le test portent sur la même population.
- **`DocumentExecution` (`pipeline/types.py:96-99`), l'exécuteur et la clé de reprise par unité : à revoir.** L'échec est un état de l'**unité** qui efface le préfixe réussi : artefacts, coûts, évaluation et reprise disparaissent ensemble. Le contrat doit porter une issue **par étape**, conserver `by_step`/`step_usage` jusqu'à l'étape fautive, et adresser la reprise par préfixe d'étapes.
- **Fan-out (`pipeline/fanout.py:230-235`) et `region_cer` (`metrics/layout.py:92`) : réparables localement.** Il faut faire remonter le nombre de régions en échec dans le `StepOutput` (issue ou message), et noter une hypothèse sans texte comme du texte vide plutôt que « non applicable ».
- **Chargement des représentations (`representations.py:37-43`) : réparable localement.** Il faut valider l'existence des GT avant l'exécution, et classer un artefact illisible au niveau de l'unité plutôt que de lever une exception pour tout le run.
