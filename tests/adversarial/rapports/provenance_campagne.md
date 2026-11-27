# Contre-expertise — domaine `provenance_campagne` (commit 04a1c17b)

Tests : `tests/adversarial/provenance_campagne/` dans la copie figée
(`test_pc_provenance.py` pour l'affirmation 8, `test_pc_ablation.py` pour l'affirmation 10).
Tous passent par les API publiques (`orchestrator.run`, `ResumeStore`, `ModuleRegistry`,
`module_identities`, `unit_key`, specs YAML de la campagne). Aucun monkeypatch du produit :
le seul « faux » externe est un serveur Ollama local (boucle locale) qui répond à `/api/tags`.

**Bilan : 30 tests, 17 rouges (défauts confirmés), 13 verts (affirmations réfutées ou points déjà traités).**

---

## Affirmation 8 — Provenance

### 8.1 Identité de la vérité terrain et des images

| champ | contenu |
|---|---|
| Affirmation | Le manifeste ne permet pas de vérifier exactement les données évaluées (au mieux un nom ou un chemin). Un `.gt.txt` modifié ne s'y voit pas. Un rapport peut être recalculé contre une autre GT sans que rien ne le signale. |
| Verdict | **confirmé**, et c'est pire que l'énoncé : le manifeste ne porte **ni empreinte ni même le chemin** des GT. |
| Contre-exemple | 2 documents, GT `abcd`. On remplace `d2.gt.txt` par `abXd` et on relance : `test_pc_provenance.py::test_identite_gt__deux_gt_differentes_donnent_deux_manifestes`. Archive produite, GT remplacée par `wxyz`, re-notation `--offline` : `::test_identite_gt__renotation_hors_ligne_contre_autre_gt_signalee`. Empreinte absente : `::test_identite_gt__resultat_porte_empreinte_de_chaque_gt`, `::test_identite_image__resultat_porte_empreinte_de_chaque_image`. Données réelles : `::test_identite_gt__run_result_publie_porte_les_gt_et_leurs_empreintes` (le `RunResult` BNL publié). |
| Comportement actuel | Le CER bouge (0,0 → 1,0 en re-notation hors ligne), mais les manifestes sont **identiques** hors horloges et `artifacts_dir`. Le SHA-256 de la GT et celui de l'image (calculés avec `hashlib`) n'apparaissent nulle part dans le `RunResult`. Le `RunResult` BNL publié (37 pages) ne contient **aucune** chaîne `.gt.txt`. Côté corpus, il ne garde que `corpus_name`, `n_documents` et `image_ref: "0000.png"`. |
| Comportement attendu | Pour chaque document : l'empreinte du contenu de chaque GT notée (et du fichier source de la GT dérivée, l'ALTO pour BNL) et celle de l'image, dans le manifeste. C'est le minimum pour qu'un tiers vérifie qu'il note *les mêmes données* (critère de sortie de P5h : « re-noter et retrouver les chiffres au chiffre près »). |
| Tests existants | `tests/app/test_resume.py::test_image_content_change_invalidates_cache` vérifie que l'image entre dans la **clé de cache**. Mais la clé n'est pas exposée. Aucun test ne regarde la GT dans le manifeste. C'est voulu : l'évaluation est toujours recalculée, donc la GT ne doit pas entrer dans la clé. Personne n'a vérifié qu'elle était tracée ailleurs. |
| Cause architecturale | `cinoc/domain/documents.py:22-32` : `GroundTruthRef` n'a que `type` et `uri`, sans `content_hash`. `cinoc/domain/run.py:90-91` : `RunManifest` ne porte que `corpus_name` et `n_documents`, sans `CorpusSpec` ni empreinte par document. `cinoc/evaluation/result.py:53-69` : `RunDocumentResult` ne garde que `image_ref`. L'empreinte de l'image est calculée (`cinoc/app/resume.py:130`, `unit_key`) puis jetée. **Une seule cause pour les 5 symptômes** : le corpus évalué n'a pas d'identité de contenu dans le contrat de sortie. Aggravant : l'archive (`--resume-dir`) range les images par SHA-256 mais **ne contient pas les GT**. La re-notation hors ligne lit donc la GT que la machine possède *maintenant*. |
| Gravité scientifique | **Haute.** Un chiffre publié peut changer sans trace dès qu'une GT est corrigée, ou que la dérivation ALTO → `.gt.txt` de l'importeur change de convention. Ordre de grandeur réel, tiré du README de la campagne : la seule convention `ſ`/`s` fait 15 % de l'erreur de Tesseract sur BNL (CER 0,0584 contre 0,0495, Δ ≈ 0,009 absolu). La césure (`⸗`) est le défaut qui a invalidé la campagne d'août. Ces deux écarts se produisent avec un manifeste identique. |

### 8.2 Alias de modèles (`mistral-small-latest`) et digest Ollama

| champ | contenu |
|---|---|
| Affirmation | Le manifeste enregistre l'alias et non le modèle résolu. Un digest Ollama qui change n'est pas vu. |
| Verdict | **partiel**. Réfuté pour le run d'un seul tenant et pour Ollama. Confirmé pour l'attribution par unité après reprise. |
| Contre-exemple | Modèle demandé `m-latest`, servi `m-2506` : `::test_alias_modele__manifeste_enregistre_le_modele_servi` (**vert**). Bascule de l'alias entre deux runs repris sur la même archive (d1 servi par `m-2503`, d2 par `m-2506`) : `::test_alias_modele__reprise_apres_bascule_attribue_le_modele_par_unite` (**rouge**). Vrai `OllamaAdapter` contre un faux serveur local, même tag `qwen2.5vl:3b` sous deux digests : `::test_digest_ollama__un_tag_reaffecte_change_la_cle_d_unite` (**vert**). |
| Comportement actuel | Le manifeste garde le modèle demandé dans `adapter_kwargs` et les modèles servis (`response.model`) dans `served_models`. Le digest Ollama entre dans `system_binaries_lock` **et** dans la clé d'unité : deux digests donnent deux clés, donc l'unité est ré-exécutée. Après bascule, d1 est **relue** (elle est absente de `calls`). `served_models` vaut `("m-2503","m-2506")`, une union sur tout le run, et aucune `DocumentUsage` ne dit quelle unité vient de quel instantané. L'information existe dans `index.json` de l'archive (`provenance.served_models`) mais n'atteint pas le `RunResult`. |
| Comportement attendu | Le modèle servi rapporté par unité (ou par document × pipeline), pour qu'un agrégat sur des unités d'instantanés différents soit détectable et filtrable. L'alias lui-même n'entre pas dans la clé, à juste titre : on ne connaît la cible qu'après l'appel. |
| Tests existants | `tests/adapters/test_ollama_digest.py`, `tests/adapters/test_served_model.py`, `tests/app/test_archive_rescore.py` couvrent la captation. Aucun ne combine reprise et bascule d'alias. |
| Cause architecturale | `cinoc/app/run_manifest.py:141` (`served_models`) **fusionne** par `adapter_name`. `cinoc/evaluation/result.py:82-110` : `DocumentUsage` n'a ni `served_models` ni `parameters_hash`. Restes : le digest Ollama est sondé **une fois**, avant la première page (`cinoc/adapters/llm/ollama.py:470`). Un `ollama pull` en cours de run n'est pas vu. Si `/api/tags` échoue, l'identité devient `{}` avec un simple avertissement. Mistral OCR (`mistral-ocr-latest`) n'a que le modèle demandé dans son identité. |
| Gravité scientifique | **Moyenne-basse.** Le mélange se voit au niveau du run (deux noms dans `served_models`) mais ne s'attribue pas. Il faut une reprise étalée dans le temps, plausible pour S31 (plusieurs jours, `--resume-dir`). Le chiffre agrégé mélange alors deux modèles sans qu'on puisse le recalculer pour un seul. |

### 8.3 Versions de modules relevées à la main

| champ | contenu |
|---|---|
| Affirmation | Une brique modifiée sans relever sa `version` garde la même clé d'unité et relit un cache périmé. |
| Verdict | **confirmé** (c'est un choix assumé, `fingerprint.py:18`, mais scientifiquement non sûr). Il s'étend aux bibliothèques tierces. |
| Contre-exemple | Une brique `1.0` lit « abcd ». On la corrige pour qu'elle lise « abXd », sans changer sa version, et on reprend sur la même archive (GT `abXd`) : `::test_version_manuelle__brique_modifiee_sans_relever_sa_version_reexecutee`. Vrai module `saknussemm` construit par le registre : `::test_version_manuelle__identite_saknussemm_porte_la_version_de_la_bibliotheque`, `::test_identite_saknussemm__prompt_et_temperature_envoyes_au_llm_sont_traces`, `::test_identite_saknussemm__poids_du_scoreur_qe_epingles`. |
| Comportement actuel | La brique corrigée n'est **jamais appelée** (`calls == []`). Le CER publié est **0,25** (la sortie périmée) au lieu de 0,0. L'identité hachée de `saknussemm:regles` vaut `{"version":"1.1","settings":{"label","producer"},"binaries":{}}` : ni `saknussemm 0.9.0`, ni règles. Celle de `saknussemm:mistral` vaut `{label, producer, model}` : ni le `SYSTEM_PROMPT` de la bibliothèque, ni la température, ni `max_tokens`. Celle de `saknussemm:mistral_qe` ne contient aucune révision des poids `pjox/dalembert`, chargés par `from_pretrained(model_name)` sans `revision`. Par comparaison, `mistral:correction` trace modèle, prompt, `max_tokens`, température et graine. |
| Comportement attendu | Ce qui détermine la sortie doit entrer dans l'empreinte : au minimum la version de la bibliothèque enveloppée, le prompt et les réglages d'échantillonnage réellement envoyés, la révision des poids. Pour le code first-party : soit une empreinte du **code** du module (haché des sources du module et de ses dépendances internes), soit un garde-fou CI qui échoue quand le source d'une brique change sans que sa version change. |
| Tests existants | `tests/app/test_resume.py::test_module_version_change_invalidates_cache` prouve qu'une version relevée invalide le cache. `::test_code_version_change_keeps_the_cache` fige le choix inverse. Rien ne vérifie que la version **est** relevée. |
| Cause architecturale | `cinoc/pipeline/fingerprint.py:72` (`step_fingerprint`) ne hache que `version` (une chaîne déclarée), les `settings` effectifs et les `binaries`. La correction des sorties repose sur « l'engagement de chaque module à relever sa version » (`fingerprint.py:18`), que rien ne vérifie. `cinoc/adapters/layout/saknussemm_correct.py:161` déclare `_VERSION = "1.1"` sans hook `effective_settings` ni `system_binaries`. `cinoc/adapters/quality/dalembert.py:138-139` charge les poids sans `revision`. Même cause qu'en 8.4 : seul `code_version` capturerait ces changements, et il est volontairement hors de la clé. |
| Gravité scientifique | **Haute pour toute campagne reprise** (`--resume-dir` est le mode normal de P5h : la spec complète « relit » la partie sans clé). Une correction de `layout_to_text`, du découpage (`EXECUTION_VERSION="1"`, aussi manuel) ou des règles `saknussemm` sans changement de version donne des chiffres de l'ancien code sous la `code_version` du nouveau. L'erreur est sans borne : c'est tout l'effet de la correction (ici 0,25 de CER sur une page). |

### 8.4 Reprise d'archive sous un autre environnement

| champ | contenu |
|---|---|
| Affirmation | Une archive reprise avec un autre code, d'autres binaires ou d'autres SDK mélange des provenances, et le manifeste final ne le dit pas. |
| Verdict | **partiel** : **réfuté pour les binaires**, **confirmé pour le code et les SDK**. |
| Contre-exemple | Binaires : d1 sous `tool 5.3`, reprise sous `5.4`. Résultat : `::test_reprise_autres_binaires__unite_reexecutee_pas_melangee` (**vert**). Archive où d1 vient de `5.3` et d2 de `5.4`, relue hors ligne : `::test_reprise_hors_ligne_binaires_melanges__refus_pas_melange_silencieux` (**vert**). Code : d1 sous `code_version 1.0`, d2 sous `2.0`, même archive : `::test_reprise_autre_code__resultat_dit_la_version_de_chaque_unite` (**rouge**). |
| Comportement actuel | Binaires : ils sont dans la clé, donc l'unité est ré-exécutée et le manifeste ne dit que `5.4`. Hors ligne, les unités produites sous un autre binaire sont **refusées** (`ArchiveIncompleteError`), pas mélangées. Mais `binaries.json` est « dernier écrivain gagne » par module (`resume.py:402`) : d1 devient inatteignable hors ligne alors qu'elle est dans l'archive. Le dossier `tessdata` (un chemin de la machine) entre lui aussi dans l'identité : une archive n'est pas réutilisable sur une machine où il diffère, même si les `.traineddata` sont identiques. C'est conservateur. Code : d1 est relue, le manifeste dit `code_version 2.0` et le `dependencies_lock` du processus courant. Seul `resumed: true` distingue d1. L'`index.json` de l'archive garde bien `provenance.code_version: "1.0"` pour d1, mais cette valeur n'atteint pas le `RunResult`. |
| Comportement attendu | Le `RunResult` doit dire, par unité relue, sous quel `code_version` (et quel `dependencies_lock`) elle a été produite, ou refuser une fusion hétérogène comme il le fait pour les binaires. |
| Tests existants | `tests/app/test_resumed_units.py` (drapeau `resumed`, durée héritée) et `tests/app/test_archive_rescore.py`. Aucun ne compare la provenance relue à celle du manifeste final. |
| Cause architecturale | `cinoc/app/run_manifest.py:180,185` : `build_manifest` écrit `dependencies_lock()` et `code_version` **du processus qui relit**. `cinoc/domain/run.py:96-99` : un seul `code_version` et un seul `dependencies_lock` par run. `cinoc/evaluation/result.py:110` : `DocumentUsage.resumed` est un booléen. Le contrat suppose un environnement unique par run, alors que la reprise en produit plusieurs. Même cause qu'en 8.2 (provenance par unité perdue entre archive et `RunResult`). Observation sur la campagne publiée : `code_version` vaut `0.1.1.dev159+g78c21e6ef` (périmée, reconnu au README). Son `dependencies_lock` liste `pytesseract 0.3.13` alors que D-300 a retiré cette dépendance : les deux champs reflètent les métadonnées de la dernière **installation**, pas le code exécuté. |
| Gravité scientifique | **Moyenne.** Les binaires, la cause la plus probable d'écart pour Tesseract, sont bien tenus. Le code et les SDK ne le sont pas, et S31 prévoit explicitement de réinstaller cinoc puis de reprendre une archive. Sans défaut de version (8.3), les sorties restent justes. Avec un tel défaut, la provenance publiée est fausse. |

---

## Affirmation 10 — Campagne scientifique (`campaigns/2026-11-26-reference/`, D-304)

### Validation d'intégration ou démonstration ?

Ce qui a été exécuté (S30, partie sans clé) est une **validation d'intégration**, et le README le dit en partie lui-même :

- E3 et E4 « règles » donnent **exactement** les chiffres d'E1 (BNL 0,0639 ; Dresden 0,7775). Les règles `default_french_ocr_rules()` ne changent rien. Elles sont de plus françaises et appliquées à de l'allemand Fraktur (moitié de BNL) et à du Kurrent (Dresden).
- E4 « règles » route par `heuristic` QE, dont l'AUC est de 0,500 (le hasard).
- E5 local sur Dresden : 6 pages sur 10 dépassent le délai. Le chiffre publié (1,8614) porte sur **4 pages sur 10**, quand E0 porte sur 10/10. Le test apparié se restreint correctement aux 4 pages communes (`n_documents: 4`, `insufficient_support`), mais le tableau d'agrégats juxtapose des supports différents.
- Une seule exécution par pipeline. Le VLM local est *supposé* déterministe (`temperature 0`, `seed 0`) mais pas mesuré. La procédure S31 (étape 4) **copie** `repetition-1` vers `repetition-2…5` : la dispersion d'E5 local sera nulle **par construction**, pas mesurée.

La démonstration (les questions de P5h) dépend toute de S31, encore non exécutée. Sa conception est examinée ci-dessous.

### Les comparaisons de la campagne : ce qui change en même temps

| Question (P5h) | Paire comparée | Variable visée | Autres variables qui changent | Test |
|---|---|---|---|---|
| La segmentation aide-t-elle Tesseract ? | E0 · tesseract / E1 · seg → tesseract | segmentation (+ découpage + projection) | aucune déclarée ; même `lang` | `test_pc_ablation.py::test_ablation_segmentation_ocr__meme_reglages_tesseract_page_et_region` **vert** |
| La segmentation aide-t-elle **les VLM** ? | E1 · seg → mistral (par région) / E5 · mistral (page) | segmentation | **`max_tokens` 1024 contre 2048** ; l'ordre de lecture vient de `layout_to_text` d'un côté, du modèle de l'autre (inhérent, à dire) ; un seul segmenteur (Tesseract), donc la conclusion est « Tesseract-seg aide-t-elle », pas « la segmentation » ; **pas de E1 pour le VLM local**, donc la question n'est posée que pour un modèle | `::test_ablation_segmentation_vlm__meme_reglages_vlm_page_et_region` **rouge** |
| À partir de quel CER la post-correction est-elle utile ? | E0 → E2 (tesseract ; mistral-ocr) | ajout d'une correction | aucune dans la paire (préfixe identique) | `::test_ablation_post_correction__e2_est_e0_plus_une_seule_etape` **vert** (4/4) |
| — même question, entre corpus | E2 BNL / E2 Dresden | CER d'entrée | **prompt** (curé `correction_press_19c_european` sur BNL, générique sur Dresden), langue, écriture | analyse (2 niveaux d'OCR × 2 corpus = 4 points, sans courbe dose-réponse) |
| La correction sélective est-elle plus rentable ? | E3 · saknussemm (mistral) / E4 · … sélectif (mistral, QE dalembert) | routage QE | aucune (`qe`, `qe_skip` seuls) ; mais un seul seuil (0,5), non calibré sur BNL, avec un scoreur français sur un corpus à moitié allemand ; BNL seulement | `::test_ablation_selective__e4_ne_differe_de_e3_que_par_le_routage_qe` **vert** |
| La correction par règles fait-elle quelque chose ? | E1 / E3 · saknussemm (règles) | ajout de la correction | aucune | `::test_ablation_correction_regles__e3_est_e1_plus_une_seule_etape` **vert** (et Δ = 0 mesuré) |
| **Apport de Saknussemm contre une correction LLM libre** | E2 · tesseract → mistral / E3 · seg → tesseract → saknussemm (mistral) | structuration (correction ligne à ligne, identités ALTO) | **(a) sortie OCR corrigée** : page entière contre régions segmentées (lecture BNL 0,0584 contre 0,0639 ; Dresden 0,7563 contre 0,7775) ; **(b) prompt** : curé presse XIXᵉ contre `SYSTEM_PROMPT` de la bibliothèque, **non tracé** au manifeste ; **(c) `max_tokens`** 2048 contre le défaut de la bibliothèque (inconnu) ; **(d) température** 0,0 déclarée contre `options.temperature` de la bibliothèque (non tracée) ; **(e)** granularité des appels (une page contre une ligne : inhérent à la méthode, à dire) ; **(f)** reconstruction du texte (sortie libre contre `CORRECTED_TEXT` réassemblé depuis le LAYOUT, ce qui change les sauts de ligne, donc la vue `texte (lignes)`). Seul le modèle demandé est commun (`mistral-small-latest`, alias). | `::test_ablation_saknussemm__e2_et_e3_partent_de_la_meme_sortie_ocr` **rouge** (×2) ; `::test_ablation_saknussemm__un_temoin_correction_libre_sur_la_meme_lecture` **rouge** (×2) |

| champ | contenu |
|---|---|
| Affirmation | E0-E5 ne sont pas de véritables ablations ; en particulier, l'apport de Saknussemm n'est pas isolé d'une correction LLM libre au même LLM sur la même sortie OCR. |
| Verdict | **partiel**. Quatre comparaisons sur six sont bien des ablations à une variable : E0→E1, E0→E2 (×2 OCR), E1→E3-règles, E3→E4. **La comparaison centrale (Saknussemm contre LLM libre) n'en est pas une** : au moins 4 variables non voulues changent en même temps, et le pipeline témoin n'existe dans aucune des deux specs. La question « la segmentation aide-t-elle les VLM ? » change aussi `max_tokens`. |
| Contre-exemple | `bnl.yaml` et `dresden.yaml` publiés ; tests ci-dessus. |
| Comportement actuel | Pour `saknussemm:mistral` (E3) et `saknussemm:mistral_qe` (E4), aucun pipeline `correction` au même modèle ne lit la même lecture (`seg → tesseract:reco → layout_to_text`). L'entrée de la correction d'E2 a pour amont `tesseract:lecture` page entière. |
| Comportement attendu | Une ablation compare deux pipelines qui ne diffèrent que de l'intervention étudiée. Pour isoler la structuration, il faut le même OCR (même amont), le même LLM, les mêmes réglages d'échantillonnage et un prompt soit identique, soit déclaré comme faisant partie de la méthode et tracé. |
| Tests existants | `tests/app/test_campaign_specs.py` vérifie que la partie sans clé est incluse dans la spec complète et que chaque pipeline nomme `lecture`. Rien ne vérifie le **plan d'expérience** (paires, variable unique). |
| Cause architecturale | Le dépôt n'a aucune représentation des **comparaisons** : une spec est une liste plate de pipelines, et l'ablation n'est qu'une convention de nommage (`E0`…`E5`) et de prose (README). La vue `lecture` (`target_step`) mesure bien chaque chaîne avant correction, mais elle ne remplace pas un témoin : la différence des différences (gain E3 sur sa lecture contre gain E2 sur la sienne) reste confondue avec le CER de départ, qui est justement la variable de la question E2. Le prompt de Saknussemm est invisible pour la même raison qu'en 8.3 (`saknussemm_correct.py` sans `effective_settings`). |
| Gravité scientifique | **Haute pour la conclusion « Saknussemm apporte X par rapport à une correction LLM »**. L'écart E2/E3 attribuable à la seule sortie OCR vaut déjà Δ lecture = 0,0055 de CER sur BNL (≈ 9 % relatif) et 0,021 sur Dresden, **avant toute correction**. Il s'y ajoute un écart de prompt non mesuré. Sur BNL, un écart E2/E3 de l'ordre de 0,005 ne pourrait pas être attribué à la structuration. Les conclusions E0→E2 et E3→E4 restent valides dans leur portée (un seul seuil, un seul scoreur). |

### Proposition minimale de matrice d'ablation (non écrite dans le dépôt)

Lignes = pipelines. Colonnes = étapes. « = » signifie identique à la ligne de référence indiquée. Chaque comparaison ne change **qu'une** cellule. Toutes les lignes partagent la segmentation `tesseract_layout` et `tesseract:reco` (même `lang`), sauf A0 et B0.

| id | segmentation | lecture | correction | réglages LLM | compare à | variable isolée |
|---|---|---|---|---|---|---|
| A0 | — | tesseract (page) | — | — | — | référence page |
| A1 | tesseract_layout | tesseract (région) → `layout_to_text` | — | — | A0 | segmentation (OCR) |
| A2 | = A1 | = A1 | **mistral:correction**, entrée = `lecture` de A1 | M, T = 0, `max_tokens` N, prompt P | A1 | ajout d'une correction libre |
| A3 | = A1 | = A1 | **saknussemm:mistral**, entrée = `reco` de A1 | M, T = 0, `max_tokens` N, prompt P' tracé | **A2** | **structuration seule** (même OCR, même LLM, mêmes réglages ; P' = P si la bibliothèque l'accepte, sinon P' déclaré comme partie de la méthode) |
| A4 | = A1 | = A1 | = A3 + QE `dalembert` (révision épinglée), seuil s | = A3 | A3 | sélectivité (idéalement 2-3 seuils) |
| B0 | — | VLM M (page), `max_tokens` N_p | — | M, T = 0, prompt Q | — | référence VLM page |
| B1 | tesseract_layout | VLM M (région), `max_tokens` N_p | — | = B0 | B0 | segmentation (VLM) |
| C0/C2 | — | mistral-ocr (page) | — / = A2 | = A2 | A0 / C0 | moteur OCR ; correction sur un 2ᵉ niveau de CER |

Une seule ligne manque pour la question centrale : **A2 sur la lecture segmentée** (`seg → tesseract:reco → layout_to_text:lecture → mistral:correction`). Les briques existantes l'expriment, et la clé d'unité relirait son préfixe. Il faut aussi aligner `max_tokens` dans B0/B1, tracer le prompt et la température de `saknussemm` et épingler la révision de D'AlemBERT. Le prompt de correction doit être le même sur les deux corpus, ou la comparaison entre corpus doit être abandonnée.

---

## Sortie `pytest`

```
$ cd <copie figée> && ce-venv/bin/python -m pytest -q -p no:cacheprovider tests/adversarial/provenance_campagne
FAILED tests/adversarial/provenance_campagne/test_pc_ablation.py::test_ablation_saknussemm__un_temoin_correction_libre_sur_la_meme_lecture[bnl]
FAILED tests/adversarial/provenance_campagne/test_pc_ablation.py::test_ablation_saknussemm__un_temoin_correction_libre_sur_la_meme_lecture[dresden]
FAILED tests/adversarial/provenance_campagne/test_pc_ablation.py::test_ablation_saknussemm__e2_et_e3_partent_de_la_meme_sortie_ocr[bnl]
FAILED tests/adversarial/provenance_campagne/test_pc_ablation.py::test_ablation_saknussemm__e2_et_e3_partent_de_la_meme_sortie_ocr[dresden]
FAILED tests/adversarial/provenance_campagne/test_pc_ablation.py::test_ablation_segmentation_vlm__meme_reglages_vlm_page_et_region[bnl]
FAILED tests/adversarial/provenance_campagne/test_pc_ablation.py::test_ablation_segmentation_vlm__meme_reglages_vlm_page_et_region[dresden]
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_identite_gt__deux_gt_differentes_donnent_deux_manifestes
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_identite_gt__resultat_porte_empreinte_de_chaque_gt
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_identite_image__resultat_porte_empreinte_de_chaque_image
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_identite_gt__renotation_hors_ligne_contre_autre_gt_signalee
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_identite_gt__run_result_publie_porte_les_gt_et_leurs_empreintes
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_alias_modele__reprise_apres_bascule_attribue_le_modele_par_unite
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_version_manuelle__brique_modifiee_sans_relever_sa_version_reexecutee
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_version_manuelle__identite_saknussemm_porte_la_version_de_la_bibliotheque
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_identite_saknussemm__prompt_et_temperature_envoyes_au_llm_sont_traces
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_identite_saknussemm__poids_du_scoreur_qe_epingles
FAILED tests/adversarial/provenance_campagne/test_pc_provenance.py::test_reprise_autre_code__resultat_dit_la_version_de_chaque_unite
17 failed, 13 passed in 3.53s
```

Verts (preuves de réfutation ou de point traité) : `test_ablation_selective__…`, `test_ablation_post_correction__…` (×4), `test_ablation_correction_regles__…` (×2), `test_ablation_segmentation_ocr__…` (×2), `test_alias_modele__manifeste_enregistre_le_modele_servi`, `test_digest_ollama__un_tag_reaffecte_change_la_cle_d_unite`, `test_reprise_autres_binaires__unite_reexecutee_pas_melangee`, `test_reprise_hors_ligne_binaires_melanges__refus_pas_melange_silencieux`.

## Contrats en cause

- **Identité du corpus évalué** (`GroundTruthRef`, `RunManifest.corpus_name/n_documents`, `RunDocumentResult.image_ref`) : **réparable localement**. Il suffit d'ajouter une empreinte de contenu par GT et par image, calculée à la lecture par l'évaluation et écrite au manifeste (ou au `RunDocumentResult`), et de verser les GT dans l'archive. La clé d'unité n'a pas à changer, puisque l'évaluation reste recalculée. Le schéma (`RunResult` v6) change.
- **Empreinte d'étape fondée sur une `version` déclarée** (`pipeline/fingerprint.py:72`, `EXECUTION_VERSION`) : **à revoir**. Tant que la justesse du cache repose sur un engagement manuel non vérifié, une campagne reprise peut publier les sorties d'un ancien code sous la version du nouveau. Il faut une empreinte mécanique (sources du module, version de la bibliothèque enveloppée, révision des poids) ou un garde-fou CI qui l'impose. Les briques `saknussemm` et `dalembert` montrent que même les briques first-party ne déclarent pas ce qui détermine leur sortie.
- **Provenance par unité dans le `RunResult`** (`DocumentUsage`, `build_manifest`) : **réparable localement**. L'archive garde déjà `code_version`, `parameters_hash` et `served_models` par artefact. Il suffit de les remonter dans `DocumentUsage`, ou de refuser une fusion hétérogène comme le refus hors ligne le fait déjà pour les binaires.
- **Binaires et digest Ollama** (`system_binaries` dans la clé) : **adapté**. Un changement de Tesseract, de `traineddata` ou de digest ré-exécute ou refuse, et ne mélange jamais. Seuls défauts : le chemin `tessdata` entre dans l'identité (portabilité) et `binaries.json` garde le dernier écrivain par module.
- **Plan d'expérience de la campagne** (aucun type « comparaison » ; specs plates) : **réparable localement**. Pour la 1.0, il suffit d'ajouter le pipeline témoin `seg → tesseract → layout_to_text → mistral:correction`, d'aligner `max_tokens`, de tracer les réglages de `saknussemm` et de tester les paires déclarées, comme le fait `test_pc_ablation.py`. Sans ce témoin, la campagne ne peut pas conclure sur l'apport de Saknussemm.
