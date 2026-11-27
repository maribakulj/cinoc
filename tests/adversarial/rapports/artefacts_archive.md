# Contre-expertise — `artefacts_archive` (affirmations 5 et 7), commit 04a1c17b

Tests : `tests/adversarial/artefacts_archive/test_ce_artefacts_archive.py` (copie figée).
Tout passe par les API publiques : module tiers écrit avec `cinoc.adapters.extension.workspace_artifact_path`,
`cinoc.app.run` + `ResumeStore` (= `--resume-dir`), `offline=True` (= `--offline`). Simulé seulement :
octets altérés, lien symbolique, SDK absent (`sys.modules[...] = None`), serveur d'images (`orchestrator.download`).
Références indépendantes : CER compté à la main sur des chaînes choisies pour ça (`abcdefghij` contre
`zzzzzzzzzz` = 1,0 ; `abcdefghiX` = 0,1), empreintes recalculées avec `hashlib.sha256`.

**Bilan : 14 rouges, 6 verts.** Affirmation 5 **confirmée** (y compris sur le socle : Tesseract + prétraitement).
Affirmation 7 **confirmée pour l'essentiel** : l'archive n'est ni vérifiable, ni immuable, ni pleinement
portable. Elle est réévaluable hors SDK et hors clé (**réfuté** sur ce point), mais pas hors réseau quand
le corpus a des images distantes.

---

## P1 — Deux étapes du même adaptateur : le fichier de la première est écrasé physiquement

| champ | contenu |
|---|---|
| Affirmation | `workspace_artifact_path` écrase le fichier de la 1re étape quand le même adaptateur (même label) sert deux fois, malgré la séparation logique `by_step`. |
| Verdict | **confirmé** |
| Contre-exemple | Pipeline `a: stamp(text=abcdefghij)` → `b: stamp(text=zzzzzzzzzz)`, vues `va` (`target_step: a`) et `vb` (`target_step: b`), VT `abcdefghij`. `test_a5_meme_adaptateur_deux_etapes__fichier_de_chaque_etape_conserve`, `…__chaque_vue_notee_sur_sa_sortie`. Sur le socle : `tesseract:fra` sur la page inclinée → `preprocess:deskew` → `tesseract:fra` sur la page redressée (`test_a5_socle_tesseract_avant_apres_redressement__chaque_etape_garde_son_fichier`). |
| Comportement actuel | Les deux artefacts ont la même `uri` (`<ws>/pipeline0/folio.stamp.txt`). Dans `by_step`, `a.content_hash` vaut sha256(« abcdefghij ») = `72399361…`, mais le fichier contient « zzzzzzzzzz » (`df635cc9…`). **CER `va` = 1,0 au lieu de 0,0** : l'étape a est notée sur la sortie de b. Témoin avec deux noms d'adaptateur distincts (`stamp1`/`stamp2`) : 0,0 et 1,0, correct (`test_a5_temoin_deux_adaptateurs_distincts__aucun_ecrasement`, vert). Socle : la lecture de la page inclinée (« **o**n annonce… », 1 erreur sur 69 caractères, CER ≈ 0,015, vérifiée en lançant `tesseract` directement) est remplacée par celle de la page redressée. Rapport : **CER v_brut = 0,0 = CER v_redresse** ; le redressement paraît sans effet alors qu'il corrige l'erreur. |
| Comportement attendu | Chaque artefact désigne un contenu dont le SHA-256 est son `content_hash` (définition de l'empreinte, `domain/artifacts.py`) ; chaque vue `target_step` note la sortie de *son* étape (D-261, P5e 1b). |
| Tests existants | `tests/app/test_step_target.py` couvre deux étapes du même **type**, mais avec deux adaptateurs **différents** (`precomputed:tesseract`, `precomputed:pero`). En plus, `precomputed` n'écrit rien dans le workspace : il pointe vers le fichier du corpus. Aucun test ne réutilise un `adapter_name`. |
| Cause architecturale | `cinoc/adapters/_workspace.py:23-28` : le chemin est `<workspace>/<stem>.<label>.<suffixe>`, sans identifiant d'étape. `RunContext` (`cinoc/pipeline/types.py:26-41`) ne transmet pas `step.id` au module, qui ne peut donc pas le mettre dans le nom. Le workspace est séparé **par pipeline**, pas par étape (`cinoc/app/orchestrator.py:233-243`). `modules` est indexé par `adapter_name` (`orchestrator.py:208-211`), donc les deux étapes partagent la même instance et le même label. Aucune vérification n'existe : l'évaluation et `ResumeStore.save`/`load` lisent l'`uri` sans jamais recalculer le `content_hash`. L'`Artifact.id` est aussi dupliqué (`folio:stamp:raw_text` deux fois), sans que rien ne le refuse. **Cette cause unique explique P1 et P2.** Les recettes y échappent : `_identite` (`cinoc/app/recipes.py:430-449`) donne à chaque étape le label `step_id`. Le défaut touche donc les specs écrites à la main (`cinoc run spec.yaml`, API, plugins). |
| Gravité scientifique | **Élevée pour l'ablation dans un même pipeline**, la fonction que `target_step` a été créée pour servir. Le chiffre de l'étape amont publié est celui de l'étape aval : l'écart vaut toute la différence entre les deux étapes. Sur le cas réaliste du socle (avec / sans redressement), le gain mesuré tombe à 0. Pour les briques du socle, les réglages sont par `adapter_name`. Deux étapes donnent donc des sorties différentes seulement si leurs **entrées** diffèrent (image brute ou prétraitée, texte d'une autre étape). C'est précisément le cas d'une ablation. |

## P2 — L'archive enregistre une empreinte que son propre fichier ne respecte pas ; la relecture le reproduit

| champ | contenu |
|---|---|
| Affirmation | Le hash enregistré correspond-il au fichier conservé, et chaque étape relit-elle son fichier avant et après archivage ? |
| Verdict | **confirmé** (défaut) |
| Contre-exemple | Même pipeline `stamp`×2, `--resume-dir` puis `--offline` avec un module qui lève s'il est appelé. `test_a5_archive__empreinte_de_chaque_fichier_archive_egale_hash_enregistre`, `test_a5_relecture_offline__chaque_etape_relit_son_propre_fichier`. |
| Comportement actuel | `index.json` : étape `a`, `content_hash = 72399361…` ; le fichier archivé `a.raw_text.txt` a pour SHA-256 `df635cc9…`, c'est-à-dire le contenu de b. `save` copie bien un fichier par étape (`<step>.<type><suffixe>`), mais il copie deux fois le même fichier source, déjà écrasé. Relecture hors ligne : **CER `va` = 1,0**, la même erreur qu'avant l'archivage, sans aucune alerte. |
| Comportement attendu | Une archive dont l'empreinte ne correspond pas au contenu n'est jamais écrite, ou elle est refusée à la relecture. |
| Tests existants | `test_step_target.py` vérifie la séparation dans l'archive avec deux adaptateurs distincts. Aucun ne compare `content_hash` au fichier. |
| Cause architecturale | Celle de P1, plus `cinoc/app/resume.py:316-324` (`save` copie `artifact.uri` sans comparer au `content_hash`) et `resume.py:296-301` (`load` ne vérifie que `is_file()`). |
| Gravité scientifique | Celle de P1, pérennisée : une campagne publiée re-notée par un tiers reproduit le chiffre faux, et la cohérence apparente vaut alors fausse preuve. |

## P3 — Corruption d'une sortie archivée : non détectée, l'unité est notée sur le contenu faux

| champ | contenu |
|---|---|
| Affirmation | Un octet changé dans une sortie archivée est-il détecté ? |
| Verdict | **confirmé** (non détecté) |
| Contre-exemple | Archive d'une passe `abcdefghiX` (CER 0,1). On remplace `X` par `j` dans `ocr.raw_text.txt`. `test_a7_octet_change_dans_une_sortie__corruption_detectee`. |
| Comportement actuel | La relecture hors ligne réussit et donne **CER 0,0** (au lieu de 0,1), alors que `index.json` porte toujours l'empreinte du contenu d'origine. |
| Comportement attendu | Empreinte recalculée → l'unité est refusée (`ArchiveIncompleteError` ou équivalent). Le contrat d'`Artifact` promet un « hash du contenu » ; l'archive le stocke, il ne sert à rien. |
| Tests existants | `tests/app/test_resume.py::test_corrupted_entry_falls_back_to_execution` ne teste qu'un `index.json` **illisible**. |
| Cause architecturale | `cinoc/app/resume.py:296-301` : l'unique contrôle est `Path(uri).is_file()`. Aucun appel à `compute_content_hash` à la relecture ; l'évaluation (`cinoc/evaluation/representations.py:37`, `calibration.py:72`, `decisions.py:46`) lit l'`uri` sans vérifier. **Même cause que P4, P5 et P2** : l'empreinte est de la métadonnée déclarative, pas un invariant vérifié. |
| Gravité scientifique | Élevée pour une archive publiée : n'importe quelle édition (volontaire, outil de synchronisation, encodage modifié par un éditeur) change le score sans aucun signal. Ampleur illimitée (ici 0,1 → 0,0). |

## P4 — `index.json` altéré en restant du JSON valide : accepté

| champ | contenu |
|---|---|
| Affirmation | Corruption de `index.json`. |
| Verdict | **partiel** : un JSON illisible est refusé (vert), une altération qui garde un JSON valide passe (rouge) |
| Contre-exemple | Troncature d'un octet → `test_a7_index_json_illisible__unite_refusee` (**vert** : `ArchiveIncompleteError`). `duration_seconds` passé à 1234,5 et `content_hash` remplacé par `0…0` → `test_a7_index_json_valide_mais_altere__alteration_detectee` (**rouge**). |
| Comportement actuel | Relecture acceptée : durée relue 1234,5 s au lieu de 0,000286 s, empreinte `000…0` acceptée. Les durées et les jetons (`usage`) servent à l'économie du rapport. |
| Comportement attendu | Un index signé ou haché (manifeste d'archive avec l'empreinte de chaque `index.json` et de chaque fichier) détecte toute altération. |
| Tests existants | `test_resume.py::test_corrupted_entry_falls_back_to_execution` (JSON cassé seulement). |
| Cause architecturale | `cinoc/app/resume.py:222-306` : validation **structurelle** (Pydantic, `_OUTCOMES`, `_REASONS`) seulement. L'archive n'a aucun manifeste d'intégrité au niveau racine : elle contient `<clé>/index.json`, `images/`, `binaries.json`, et rien qui les relie. |
| Gravité scientifique | Moyenne : coûts et durées publiés modifiables sans trace. Issue (`outcome`) et message aussi : une unité `failed` peut être réécrite en `truncated`. |

## P5 — Image partagée `images/<sha256>` corrompue : servie sans contrôle

| champ | contenu |
|---|---|
| Affirmation | Corruption d'une image partagée. |
| Verdict | **confirmé** (non détectée), gravité faible aujourd'hui |
| Contre-exemple | Un octet ajouté à `images/8ac02e56….png`. `test_a7_image_partagee_corrompue__corruption_detectee`. |
| Comportement actuel | Relecture acceptée. L'artefact `__initial__/IMAGE` du run relu pointe vers `images/8ac02e56….png`, dont le SHA-256 réel est `9f7b44c9…` : le nom *est* l'empreinte, et il n'est pas vérifié. |
| Comportement attendu | Nom ≠ empreinte → image refusée. |
| Tests existants | `tests/app/test_archive_images.py` (déduplication, `..` refusé) ; aucun test d'intégrité. |
| Cause architecturale | `cinoc/app/resume.py:360-376` (`_store_image` adresse par contenu à l'écriture) et `load` (aucun recalcul). L'IMAGE initiale a de plus `content_hash = None` (`orchestrator.py:573-583`). |
| Gravité scientifique | Faible pour les scores (hors ligne, aucun module ne relit l'image ; la clé d'unité hache l'image **du corpus**, pas celle de l'archive). Réelle pour tout consommateur de l'image archivée (`artifact_sink`, export, rapport qui la lirait). |

## P6 — Chemins absolus et liens symboliques : suivis hors de l'archive

| champ | contenu |
|---|---|
| Affirmation | D-304 refuse les `..` ; quid des absolus et des liens symboliques ? |
| Verdict | **confirmé** pour les absolus et les liens ; **réfuté** pour les fuites de chemin à l'écriture |
| Contre-exemple | (a) `uri` d'`index.json` remplacée par un chemin absolu vers `ailleurs.txt` (contenu = VT), hors archive : `test_a7_uri_absolue_hors_archive__refusee`. (b) `ocr.raw_text.txt` remplacé par un lien symbolique vers ce fichier : `test_a7_lien_symbolique_hors_archive__refuse`. Témoins : `../../ailleurs.txt` → `test_a7_temoin_uri_relative_en_point_point__refusee` (**vert**, refusé) ; balayage de tous les fichiers de l'archive à la recherche de la racine de la machine d'origine → `test_a7_archive__aucun_chemin_absolu_de_la_machine_d_origine` (**vert**). |
| Comportement actuel | (a) et (b) : le fichier extérieur est lu, et l'unité est notée **CER 0,0** (au lieu de 0,1). À l'écriture, en revanche, `save` réécrit chaque `uri` en relatif : aucune fuite de chemin absolu observée. |
| Comportement attendu | Une archive « se télécharge » (docstring de `_rebased`) : tout nom qui ne se résout pas, **liens résolus**, à l'intérieur de l'archive est refusé, absolu ou non. |
| Tests existants | `test_archive_images.py::test_an_archived_file_outside_the_archive_is_not_read` (paramétré sur deux formes de `..` seulement). |
| Cause architecturale | `cinoc/app/resume.py:187-199` : `_rebased` renvoie l'artefact **inchangé** si `Path(uri).is_absolute()` ou si `"://"` est dans l'`uri`, et contrôle avec `os.path.normpath`, qui ne résout pas les liens (pas de `resolve()`). `is_file()` (`resume.py:298`) suit le lien. |
| Gravité scientifique | Élevée pour une archive tierce : un `index.json` peut faire noter n'importe quel fichier de la machine qui relit, donc un score arbitraire. C'est aussi une lecture de fichiers locaux arbitraires, problème de sécurité qui dépasse la science : le contenu se retrouve dans le rapport via les extraits de texte. |

## P7 — Réévaluation hors moteur : SDK et clé, oui ; réseau, non (images distantes)

| champ | contenu |
|---|---|
| Affirmation | `--offline` fonctionne-t-il sans SDK, sans clé et sans réseau ? Une image distante est-elle téléchargée à la re-notation ? |
| Verdict | **réfuté** pour SDK et clé ; **confirmé** pour le réseau |
| Contre-exemple | Recette `vlm_seul · openai` servie par cassette, puis SDK `openai` à `None`, toutes les clés retirées, `httpx` refusant tout : `test_a7_reevaluation_sans_sdk_ni_cle_ni_reseau__scores_identiques` (**vert**, scores identiques). Corpus à image `https://…/folio.png` (serveur simulé) : `test_a7_relecture_offline_image_distante__aucun_telechargement`, `test_a7_relecture_offline_serveur_d_images_eteint__unite_relue_de_l_archive`. |
| Comportement actuel | La re-notation **retélécharge** l'image (1 appel). Serveur éteint : **aucune erreur**, l'unité sort `failed` (`infrastructure`, « image distante irrécupérable ») et le `RunResult` relu exclut une unité pourtant présente, intacte, dans l'archive. Si le serveur sert d'autres octets, la clé change et l'unité est « absente » (`ArchiveIncompleteError`). |
| Comportement attendu | Hors ligne, rien n'est téléchargé ; l'image d'identité est celle de l'archive (`images/<sha256>`). Une unité archivée n'est jamais rendue `failed` par une cause extérieure à l'archive. |
| Tests existants | `tests/app/test_archive_rescore.py` (cassettes, `cut_network`) couvre SDK et réseau des moteurs, avec des images locales seulement. Limite déjà écrite dans D-304 (« une image distante est encore téléchargée à la re-notation hors ligne »), sans test, et sans dire qu'un serveur éteint change le résultat publié au lieu de l'arrêter. |
| Cause architecturale | `cinoc/app/orchestrator.py:246-248` : `_materialize_remote_images` s'exécute **avant** la lecture de l'archive, sans tenir compte de `offline`, et une image injoignable court-circuite `resume_store.load` (`orchestrator.py:257-268`). Plus profondément, `unit_key` (`cinoc/app/resume.py:139-172`) identifie l'unité par les octets de l'image **du corpus** (`Path(document.image_uri).read_bytes()`). L'archive ne peut donc pas être relue sans le corpus d'origine, octet pour octet (voir P8). |
| Gravité scientifique | Moyenne : une re-notation tierce d'un corpus curé (HF/IIIF) dépend de la disponibilité et de la stabilité du serveur. Une panne réduit en silence le nombre d'unités notées, et l'agrégat publié change. |

## P8 — L'archive seule ne suffit pas : il faut les images du corpus d'origine

| champ | contenu |
|---|---|
| Affirmation | Une archive « réévaluable indépendamment » (portabilité). |
| Verdict | **confirmé** (non portable seule) |
| Contre-exemple | Archive d'une passe (CER 0,1) ; l'image du corpus est supprimée, la VT gardée, `images/<sha256>` toujours présente dans l'archive. `test_a7_archive_seule_sans_images_du_corpus__reevaluable`. |
| Comportement actuel | `ArchiveIncompleteError` : « Dont 1 sans image lisible : une unité sans image n'a pas d'empreinte ». |
| Comportement attendu | La VT et l'archive suffisent à re-noter, puisque l'archive porte déjà l'image par son empreinte. L'archive ne contient pas non plus la spec ni le `RunResult` : il faut aussi le fichier de run d'origine. |
| Tests existants | Aucun ; tous les tests de relecture gardent le corpus en place. |
| Cause architecturale | `cinoc/app/resume.py:150-153` (clé = octets de l'image du corpus) ; l'archive n'a aucun index racine (spec → clés d'unités). |
| Gravité scientifique | Faible sur les chiffres (le run échoue bruyamment) ; forte sur la publiabilité : publier « l'archive » ne suffit pas, il faut republier le corpus d'images à l'identique. |

## P9 — Cache et archive confondus : une reprise normale réécrit une archive publiée

| champ | contenu |
|---|---|
| Affirmation | `ResumeStore` (cache) et archive scientifique sont confondus ; une archive publiée doit être immuable. |
| Verdict | **confirmé** (par conception, documenté) |
| Contre-exemple | Run 1 : le moteur échoue, l'unité est archivée `failed`. Run 2, même `--resume-dir`, sans `--offline`, moteur réparé. `test_a7_archive_publiee__une_reprise_normale_ne_la_modifie_pas`. |
| Comportement actuel | `index.json` de la même clé réécrit en place : `outcome` passe de `failed` à `ok`. `binaries.json` est fusionné (« le dernier run l'emporte », `resume.py:394-409`), et toute spec différente ajoute des unités au même dossier. Rien ne distingue une archive close d'un cache ouvert. |
| Comportement attendu | Une archive publiée est en lecture seule (scellée par un manifeste) ; une reprise écrit ailleurs, ou refuse d'écrire. |
| Tests existants | `test_resume.py` / `test_archive_rescore.py` vérifient au contraire que les échecs sont retentés : c'est le comportement de cache voulu. |
| Cause architecturale | `cinoc/app/resume.py:205-219` : la docstring de `base_dir` le dit elle-même, « ce cache porte deux rôles pour un seul mécanisme ». `RunManifest.artifacts_dir` désigne un dossier mutable. |
| Gravité scientifique | Moyenne : le `RunResult` publié et l'archive peuvent diverger après coup sans trace. Avec P3 et P4, rien ne permet de prouver qu'une archive est celle du run publié. |

---

## Propriétés de l'archive

| propriété | garantie aujourd'hui ? | test(s) | cause |
|---|---|---|---|
| **Vérifiable** (contenu = empreintes enregistrées) | **non** | `test_a7_octet_change_dans_une_sortie__corruption_detectee` (rouge), `test_a7_index_json_valide_mais_altere__alteration_detectee` (rouge), `test_a7_image_partagee_corrompue__corruption_detectee` (rouge), `test_a5_archive__empreinte_…` (rouge) ; seul le JSON illisible est rejeté (`test_a7_index_json_illisible__unite_refusee`, vert) | `resume.py:296-301` ne contrôle que l'existence ; aucun recalcul de `content_hash`, aucun manifeste racine |
| **Immuable** | **non** | `test_a7_archive_publiee__une_reprise_normale_ne_la_modifie_pas` (rouge) | `ResumeStore` = cache et archive en un seul objet (`resume.py:205-219`, `save` réécrit sous la même clé, `record_binaries` fusionne) |
| **Portable** (relue ailleurs, sans la machine d'origine) | **partiel** | Aucun absolu écrit (`test_a7_archive__aucun_chemin_absolu_…`, vert) et `..` refusé (`test_a7_temoin_uri_relative_…`, vert) ; mais les absolus et les liens symboliques sont suivis hors de l'archive (`test_a7_uri_absolue_…`, `test_a7_lien_symbolique_…`, rouges) et le corpus d'images d'origine est indispensable (`test_a7_archive_seule_…`, rouge) | `_rebased` (`resume.py:187-199`) exempte les absolus et ne résout pas les liens ; `unit_key` (`resume.py:150-153`) lit l'image du corpus |
| **Réévaluable hors moteur** (sans SDK, clé, réseau) | **partiel** | Sans SDK et sans clé : oui (`test_a7_reevaluation_sans_sdk_ni_cle_ni_reseau__scores_identiques`, vert ; `test_a7_temoin_relecture_intacte__meme_score`, vert) ; sans réseau avec images distantes : non (`test_a7_relecture_offline_image_distante__aucun_telechargement`, `…serveur_d_images_eteint…`, rouges) | `orchestrator.py:246-268` télécharge avant de lire l'archive et court-circuite la relecture si l'image est injoignable |
| **Fidèle étape par étape** (`by_step` = fichiers distincts) | **non** si un `adapter_name` revient dans un pipeline | `test_a5_*` (4 rouges + socle Tesseract rouge) ; témoin à deux noms vert | `_workspace.py:23-28` (pas d'identifiant d'étape dans le chemin), `RunContext` sans `step_id` |

---

## Sortie de `pytest`

```
$ cd contre-expertise && ce-venv/bin/python -m pytest -q -p no:cacheprovider tests/adversarial/artefacts_archive
FAILED …::test_a5_meme_adaptateur_deux_etapes__fichier_de_chaque_etape_conserve
FAILED …::test_a5_meme_adaptateur_deux_etapes__chaque_vue_notee_sur_sa_sortie
FAILED …::test_a5_archive__empreinte_de_chaque_fichier_archive_egale_hash_enregistre
FAILED …::test_a5_relecture_offline__chaque_etape_relit_son_propre_fichier
FAILED …::test_a7_octet_change_dans_une_sortie__corruption_detectee
FAILED …::test_a7_index_json_valide_mais_altere__alteration_detectee
FAILED …::test_a7_image_partagee_corrompue__corruption_detectee
FAILED …::test_a7_uri_absolue_hors_archive__refusee
FAILED …::test_a7_lien_symbolique_hors_archive__refuse
FAILED …::test_a7_relecture_offline_image_distante__aucun_telechargement
FAILED …::test_a7_relecture_offline_serveur_d_images_eteint__unite_relue_de_l_archive
FAILED …::test_a5_socle_tesseract_avant_apres_redressement__chaque_etape_garde_son_fichier
FAILED …::test_a7_archive_seule_sans_images_du_corpus__reevaluable
FAILED …::test_a7_archive_publiee__une_reprise_normale_ne_la_modifie_pas
14 failed, 6 passed in 3.26s
```
Verts (preuves de réfutation ou témoins) : `test_a5_temoin_deux_adaptateurs_distincts__aucun_ecrasement`,
`test_a7_temoin_relecture_intacte__meme_score`, `test_a7_index_json_illisible__unite_refusee`,
`test_a7_archive__aucun_chemin_absolu_de_la_machine_d_origine`, `test_a7_temoin_uri_relative_en_point_point__refusee`,
`test_a7_reevaluation_sans_sdk_ni_cle_ni_reseau__scores_identiques`.

## Correctifs évidents (décrits, non écrits)

- Donner à `RunContext` le `step_id` et l'inclure dans `workspace_artifact_path`, ou un sous-dossier de workspace par étape fourni par l'exécuteur. En garde-fou, l'exécuteur vérifie après chaque étape que `sha256(uri) == content_hash` et que deux artefacts de l'unité ne partagent pas une `uri`.
- `ResumeStore.load` : recalculer le SHA-256 de chaque fichier (et des `images/<sha>`) et refuser l'unité en cas d'écart. Dans `_rebased`, refuser les absolus et `://`, et contrôler avec `Path.resolve()` (liens résolus).
- Hors ligne : ne pas appeler `_materialize_remote_images`, et calculer la clé à partir de l'image d'archive ou d'une empreinte d'image stockée dans un index racine.
- Séparer la notion d'archive : un `archive.json` racine (spec, liste des clés, empreinte de chaque `index.json` et de chaque fichier), scellé, et une relecture qui refuse d'écrire dans une archive scellée.

## Contrats en cause

- **Chemin d'artefact dans le workspace (`adapters/_workspace.py` + `RunContext`) : réparable localement.** Le défaut vient d'une coordonnée absente (l'étape) dans une fonction et un contexte ; l'ajouter, plus une vérification d'empreinte à l'exécuteur, ferme P1 et P2 sans toucher aux types pivots.
- **`Artifact.content_hash` comme garantie d'intégrité : à revoir.** Le domaine le présente comme l'identité du contenu, mais aucune couche ne le vérifie jamais (exécution, archive, évaluation). Tant que ce n'est pas un invariant contrôlé, l'empreinte décore l'artefact sans rien garantir (P2-P5).
- **`ResumeStore` comme archive scientifique : à revoir.** Un seul objet porte un cache mutable, qui retente et fusionne, et une archive qu'on publierait. Il lui manque le scellement, le manifeste d'intégrité, la clé indépendante du corpus et la relecture sans réseau, et ces propriétés contredisent le rôle de cache (P7-P9). Le contrat de relecture hors SDK et hors clé, lui, est **adapté** et tient (P7, vert).
