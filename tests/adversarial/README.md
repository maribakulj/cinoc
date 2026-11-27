# Contre-expertise de Cinoc au commit `04a1c17b`

**Question posée** : les contrats fondamentaux de Cinoc conviennent-ils à un véritable instrument scientifique ?

**Réponse courte** : **non, pas en l'état**. Quatre contrats sont à revoir (ce n'est pas réparable symptôme par symptôme) :

- l'observation métrique `Observation(value, weight)` ;
- l'issue portée par l'unité plutôt que par l'étape ;
- la confusion du cache de reprise et de l'archive scientifique ;
- l'appariement de mise en page « par identifiant d'abord ».

Plusieurs autres défauts sont réels mais réparables localement. Une partie des affirmations est réfutée, preuves à l'appui. Aucun produit n'a été modifié.

## Méthode et preuves

| | |
|---|---|
| **Code examiné** | copie figée détachée à `04a1c17b`, environnement Python isolé qui ne voit qu'elle. Suite existante verte sur cette copie : 3 810 passés, 216 ignorés. |
| **Tests adversariaux** | 145 tests, chacun affirmant le comportement **attendu** sur un contre-exemple minimal construit par les API publiques (pannes simulées par des briques tierces enregistrées, jamais par monkeypatch du code testé), comparé à une référence indépendante quand c'est possible (calcul à la main, `jiwer`, `scipy.stats`, `scipy.optimize.linear_sum_assignment`, `difflib`). |
| **Résultat** | **90 rouges = défauts confirmés, 55 verts = affirmations réfutées ou déjà traitées.** |
| **Relecture** | Les 92 rouges initiaux ont été relus par un agent indépendant (qui n'avait pas les rapports) : 51 valides, 39 valides mais discutables (le comportement contesté est un choix documenté, ou l'attendu exact dépend d'une convention), **2 invalides, retirés**. Aucun rouge n'échoue pour une raison accessoire. |
| **Où** | Les tests sont dans la branche **locale** `contre-expertise-04a1c17b` de la copie figée (commits `c16e377`, `614a16c`) et dans le bundle ce bundle. Les rapports détaillés par domaine sont `tests/adversarial/rapports/*.md` (fiches complètes : contre-exemple, comportement actuel/attendu, tests existants, cause `fichier:ligne`). Rien n'est poussé ni mergé. |

Reproduire :

```bash
git -C <clone> fetch <bundle> contre-expertise-04a1c17b
cd <copie à 04a1c17b + cette branche> && python -m pytest -q -p no:cacheprovider tests/adversarial
```

## 1. Contrats en cause

| Contrat | Verdict | Symptômes (affirmations) | Rouges |
|---|---|---|---|
| **`Observation(value, weight)` + agrégat Σv·w/Σw** (`evaluation/metric.py:22`, `runner.py:307`, `inference.py:166`) | **à revoir** | Le type transporte un ratio déjà calculé, jamais ses statistiques suffisantes : aucun choix de poids ne représente un F1, un dénominateur nul (page blanche) ou une borne appliquée au corpus. Sur les 29 métriques par document, **14 sont mal agrégées** (1, 2, 3) | ~16 |
| **Issue portée par l'unité** (`DocumentExecution`, `pipeline/types.py:96-99` ; reprise par unité `resume.py:130`) | **à revoir** | Un OCR payé suivi d'une correction en échec perd ses artefacts, son coût et la possibilité d'évaluer l'amont ; la reprise repaie l'amont (6, 9) | ~8 |
| **`ResumeStore` utilisé comme archive scientifique** + `content_hash` jamais vérifié | **à revoir** | Ni vérifiable ni immuable ; portable en partie seulement ; corruption et liens suivis sans alerte (7) | ~11 |
| **Appariement de mise en page « id d'abord, en bloc », pages aplaties** (`metrics/layout.py:145,172,202,256`) | **à revoir** | Un seul id commun désactive la géométrie ; les ids `r1…rN` des segmenteurs de Cinoc entrent en collision avec ceux d'une vérité terrain ; le multipage apparie entre pages (4) | ~10 |
| **`MetricScore.value=None` + `expected`** (`runner.py:149-159,307-327`) | **à revoir** (lié au premier) | `None` code au moins six non-mesures distinctes, et `expected` ne croît que sur un échec (2) | ~8 |
| **Empreinte d'étape fondée sur une version déclarée à la main** (`pipeline/fingerprint.py:72`) | **à revoir** | Une brique modifiée sans relever sa version relit un cache périmé (8) | 2 |
| Pool final lu par `correction`/`decisions` (`runner.py:135,229,236`) | réparable localement | 9 | 5 |
| Chemin de workspace sans id d'étape (`adapters/_workspace.py:23-28`) | réparable localement | 5 | 5 |
| Identité du corpus évalué (pas d'empreinte de GT ni d'image dans `RunResult`/`RunManifest`) | réparable localement | 8 | 5 |
| Inférence : estimande non nommé, pas d'IC apparié, pas de grappe | réparable localement | 3 | 6 |
| `max_error` déduit de `higher_is_better` (`runner.py:409`) | réparable localement | 2 | 3 |
| Appariement glouton (`_greedy_pairs`) | réparable localement (Hongrois, par page) | 4 | 4 |
| Deux projections `LAYOUT → texte` divergentes (couche 3 contre couche 5) | réparable localement | 4 | 4 |
| Plan d'expérience de la campagne | réparable localement | 10 | 4 |
| **Adaptés** : relecture sans SDK ni clé ni réseau (hors images distantes), refus des `..`, aucun chemin absolu écrit dans l'archive, binaires et digest Ollama dans la clé, bootstrap par document, collecteurs de vue / `inference` / `hipe`, calibration sur l'étape ciblée, ECE au niveau corpus, CER/WER/MER/cMER corpus identiques à jiwer hors références vides | — | — | 55 verts |

## 2. Par affirmation

### 1. Contrat mathématique des métriques — **confirmé**

| Contre-exemple | Actuel | Attendu (référence) |
|---|---|---|
| Page à vérité terrain vide, 44 caractères inventés, plus une page à 10 caractères parfaite | CER corpus **0,0** (« 2/2 notés ») | **4,4** (jiwer : 44 insertions / 10). Un pipeline qui hallucine passe devant un pipeline muet. **Un test existant fige ce comportement** : `test_metrics_text.py::test_cer_weight_is_reference_length` |
| Même cas pour WER, `ins_rate` | 0,0 | 7,0 |
| Même cas pour `char_accuracy`, `fca` | 1,0 | < 1 (l'attendu exact dépend du plancher) |
| NER, deux documents déséquilibrés (ΣTP 11, ΣFP 9, ΣFN 0) | `ner_f1` = **0,926** (moyenne de F1 pondérée) | **0,710**. Le payload NER du **même** `RunResult` dit 0,710 |
| NER, faux positifs sur un document sans entité de référence | 1,0 | 1/3 |
| `region_detection`, `bow_f1` | 0,926 (la précision 11/20 et le rappel 1 affichés à côté donnent 0,710) | 0,710 |
| `reading_order_tau`, poids par blocs | 0,167 | 1/46 = 0,022, par paires (discutable : unité déclarée `REGION`, D-289) |
| `char_accuracy` avec un document à CER > 1 | 0,833 (plancher par page, documenté) | 1 − CER corpus = 0,5 |

En route : en mode détaillé, un label NER absent de la vérité terrain **fait planter tout le run** (`EntityCategoryScore.support ≥ 1`).

**Cause unique** : l'observation est un ratio, pas des comptes additifs. Les 15 métriques justes le sont parce que leur ratio *est* une moyenne pondérée par son dénominateur.

### 2. Applicabilité et politique d'échec — **confirmé**

- **`expected` ne croît que dans la branche des échecs.** Une unité **réussie** qui ne fournit pas ce que la vue exige sort en silence du compte, avec l'issue `ok`. Cas reproduits :
  - artefact sans contenu (`uri=None`) : 2/2 au lieu de 3 ;
  - sortie incompatible : 0/0 ;
  - fan-out dont toutes les régions échouent : unité `ok`, sans message.
- **Un pipeline non applicable annule les tests des autres.** Un 3ᵉ pipeline sans type de la vue met les cas complets à 0 : « support insuffisant » au lieu de p = 0,0078 (scipy).
- **Pages blanches.** Elles comptent comme « notées » (12 au lieu de 6) et entrent dans le Wilcoxon avec des valeurs fabriquées 1,0/0,0 : p passe de 0,031 à 0,162. L'agrégat, lui, les exclut. Agrégat, IC et test ne portent donc pas sur la même population.
- **Fichier manquant.** Une vérité terrain ou un artefact absent du disque lève `EvaluationError` **après** l'exécution facturée des moteurs, et tout le `RunResult` est perdu. Le chargeur YAML protège la vérité terrain, pas une spec construite autrement.
- **`max_error`.** `worst = 0.0 if higher_is_better else 1.0`.
  - Pour le CER, non borné, **échouer (1,0) note mieux qu'halluciner (2,77)**.
  - Pour `ins_rate`, la documentation se contredit : « 1 », puis « comme une page vide », qui vaut 0.
  - Pour `bow_precision`, un échec est compté avec un poids nul et ne pèse pas.
- **Réfuté.** Une vérité terrain absente reste hors des deux compteurs, et une troncature `max_tokens` est notée et marquée `truncated`.

### 3. Statistiques — **confirmé**

- **Simpson.** 12 petites pages où A est parfait, plus une grande page où A fait 400 fautes.
  - Tableau : CER micro A 0,179, B 0,011, donc B est meilleur.
  - Juste en dessous : « Wilcoxon → différence significative » (p Holm 0,0195) **dans le sens de A**, sans dire ni le sens ni que le test porte sur des CER par page non pondérés.
  - Une permutation appariée exacte sur la différence de CER micro donne **p = 1,0**.
- **Aucun IC apparié.** B fait toujours exactement une faute de plus qu'A : les IC marginaux [0,224 ; 0,345] et [0,234 ; 0,355] se chevauchent presque entièrement, alors que l'IC de la différence vaut [0,01 ; 0,01].
- **Échec non aléatoire (`exclude` par défaut).** A échoue sur la page difficile. Le tableau donne A 0,05 (7/8) contre B 0,31 (8/8), alors que B est meilleur sur **chacune** des 7 pages communes. Le test et les IC portent sur 7 pages, l'agrégat sur 8.
- **Grappes.** Aucune notion de grappe documentaire : des pages d'un même manuscrit sont traitées comme indépendantes, et l'IC est trop étroit.
- **Répétitions.** Elles rejouent `temperature=0` et `seed=0` : la « fourchette » mesure le non-déterminisme résiduel du fournisseur, pas une variabilité d'échantillonnage.
- **Réfuté.** Le bootstrap rééchantillonne bien des documents, et `--repeat` utilise des archives disjointes.

> Tension à arbitrer : compter l'hallucination sur page blanche dans le CER micro (affirmation 1) **et** exclure les pages blanches du test apparié (affirmation 2) ne tiennent ensemble que si le test apparié ne porte pas sur le CER par document. C'est une seule décision : **quel estimande Cinoc publie, et quel test le teste.**

### 4. Layout — **confirmé** (le glouton est un défaut étroit ; les défauts graves sont ailleurs)

| Contre-exemple | Actuel | Attendu |
|---|---|---|
| Glouton contre optimum, 2×2 régions à recouvrement fort | F1 0,5, CER par région 1,444 | 1,0 et 0 (`linear_sum_assignment`) — cas étroit sur une vérité terrain propre |
| Permuter l'ordre des régions **de référence** | F1 {0,5 ; 1,0} selon l'ordre | invariant |
| Transcription parfaite, ids `r1`/`r2` attribués dans l'autre sens | CER par région 0,889, tau 1,0 | 0, et ordre jugé sur la géométrie |
| Deux ALTO sans `ID` (renommés `region_N` des deux côtés), ordre réellement inversé | tau 0,0, inversion masquée | inversion détectée |
| Un seul id partagé | la géométrie est désactivée pour toutes | appariement géométrique, id en départage |
| Multipage, même gabarit, sortie parfaite | F1 1,0 entre pages différentes ; CER par région 0,889 | appariement **par page** |
| Le même layout, projeté par la couche 3 et par la couche 5 | séparateurs `\n\n` contre `\n` ; ordre imbriqué ignoré ; candidat parfait à CER 4/28 sous « texte (lignes) » | une seule projection |
| Fan-out multipage | lit les régions de la page 2 dans l'image de la page 1 (mécanisme montré sans découpeur) | une image par page |

Réfuté : le fan-out préserve l'ordre de lecture.

### 5. Intégrité des artefacts — **confirmé**

- Deux étapes de même `adapter_name` et même label écrivent `<ws>/pipeline0/<doc>.<label>.txt` : **la seconde écrase physiquement la première**. Le `content_hash` de l'étape a reste celui de a, mais le fichier contient b.
- La vue `target_step: a` obtient CER 1,0 au lieu de 0. L'archive recopie le fichier écrasé avec l'ancien hash, et la relecture `--offline` reproduit l'erreur.
- **Reproduit sur le socle** : `tesseract` → `preprocess:deskew` → `tesseract`. La première lecture (CER ≈ 0,015, vérifiée au binaire) est écrasée, les deux vues affichent 0,0, **et le gain du redressement disparaît**.
- Les recettes y échappent (elles nomment chaque instance par l'id d'étape) ; les specs écrites à la main et les plugins y sont exposés.
- Cause : `RunContext` ne transmet pas `step.id` au chemin de workspace.

### 6. Échecs partiels — **confirmé**

Scénario : OCR facturé (500/200 jetons, 1 page), puis correction en échec (`billed=300`).

| Effet | Actuel | Attendu |
|---|---|---|
| Évaluer l'étape amont (vue ciblant l'OCR) | `None` | 0,10 |
| Coût porté par l'unité | 300 jetons | 800 |
| Bilan économique | 1 100 jetons, soit −31 % | 1 600 |
| Pipeline dont toutes les unités échouent | disparaît du bilan | sa facture reste comptée |
| Reprise `--resume-dir` | rappelle l'OCR (2 appels) | ne repaie pas l'amont |

Le type interdit bien les artefacts d'une unité `failed` : l'affirmation est exacte. C'est précisément la cause.

### 7. Cache et archive — **confirmé** (un point réfuté)

| Propriété | Garantie | Preuve |
|---|---|---|
| Vérifiable | **non** | un octet changé dans une sortie est relu et noté (CER 0,0 au lieu de 0,1) ; un `index.json` altéré mais valide est accepté ; une image partagée corrompue est servie — aucune empreinte n'est jamais recalculée |
| Immuable | **non** | une reprise ordinaire réécrit en place une unité archivée (`failed` → `ok`) ; aucun scellement |
| Portable | partiel | les relatifs et le refus des `..` sont corrects, mais **un chemin absolu ou un lien symbolique hors de l'archive est suivi** (lecture de fichiers arbitraires sur la machine qui relit) ; les images du corpus d'origine sont indispensables (la clé d'unité hache l'image du corpus) ; la spec n'est pas archivée |
| Réévaluable hors moteur | partiel | **réfuté pour SDK, clé et réseau coupés : scores identiques** ; mais une image distante est retéléchargée, et si le serveur est éteint l'unité intacte devient « échouée (infrastructure) » : l'agrégat publié change en silence |

### 8. Provenance — **confirmé, et pire que l'énoncé pour la vérité terrain**

- **Vérité terrain.** Ni le manifeste ni le `RunResult` ne portent l'empreinte ni même le chemin des vérités terrain ; l'archive ne les contient pas.
  - Changer un `.gt.txt`, ou re-noter hors ligne contre une vérité terrain remplacée : le CER bouge (0,0 → 1,0) et les manifestes restent identiques.
  - Cas réel : la seule convention `ſ`/`s` pèse ~15 % de l'erreur de Tesseract sur BNL et passe inaperçue.
- **Image.** Son empreinte entre dans la clé d'unité, puis elle est jetée.
- **Versions déclarées à la main.** Une brique corrigée sans relever sa version relit une sortie périmée : CER publié 0,25 au lieu de 0. Les trous concrets :
  - l'identité de `saknussemm` ne porte ni la version de la bibliothèque (0.9.0), ni son prompt, ni sa température ;
  - les poids D'AlemBERT ne sont épinglés sur aucune révision.
- **Alias et environnements.** Partiel. Sur un seul run, l'alias demandé et le modèle servi sont bien tracés, et le digest Ollama entre dans la clé ; les binaires changés provoquent une ré-exécution.
  - Après une reprise, `served_models` est une union, et une unité relue produite sous une autre `code_version` ou d'autres SDK apparaît sous ceux du processus qui relit.
  - Le `dependencies_lock` de la campagne publiée liste encore `pytesseract`, retiré par D-300.

### 9. Cohérence des analyses — **confirmé pour `correction`, `decisions` et `economics`** (le reste est conforme)

Montage : chaîne `ocr → correction → refine` en mode détaillé.

- **`correction`.** Sous la vue ciblant `correction` (CER 0), le bilan annonce une « régression catastrophique », calculée sur `refine`. La vue « OCR seul » porte un bilan de correction. Dans `ocr → correction → projection`, le « brut » est le texte final reprojeté, d'où un gain nul.
- **`decisions`.** Même cause (pool final), payload hors de l'étape évaluée.
- **`economics`.** Le CER suit la vue, le coût est celui du pipeline entier : `DocumentUsage` n'a pas d'usage par étape.
- **Calibration.**
  - Réfuté : elle lit bien l'étape ciblée.
  - Confirmé : le multi-ensemble de mots biaise. Mots permutés : ECE 0,05 au lieu de 0,45 par alignement. Mot répété et déplacé : 0,01 au lieu de 0,19. Le biais sous-estime l'ECE d'un moteur surconfiant.
- **Réfuté.** Les 13 collecteurs de vue, `inference` et `hipe` sont conformes.

### 10. Campagne scientifique — **confirmé : S30 est une validation d'intégration, pas une démonstration**

- Les preuves :
  - les règles `saknussemm` changent zéro caractère par rapport à E1 ;
  - le score de qualité heuristique a une AUC de 0,5 ;
  - E5 local sur Dresden est noté sur 4 pages sur 10 ;
  - la recopie de `repetition-1` donne une dispersion nulle par construction ;
  - en plus, découvert par S31L : sur toute chaîne segmentation → reco par région → saknussemm, le fan-out livrait une ligne de layout par région contenant des `\n`. saknussemm refusait toutes les lignes, se repliait sans rien corriger et payait trois tentatives.
- **Vraies ablations à une variable (vertes)** : E0→E1, E0→E2 (×2 OCR), E1→E3-règles, E3→E4.
- **Ce qui manquait pour isoler saknussemm** : une correction LLM libre au **même** LLM sur la **même** lecture segmentée. E3 (saknussemm) et E2 (correction libre sur la page entière) diffèrent d'au moins quatre variables : la sortie OCR corrigée, le prompt, `max_tokens` et la température.
- **Témoin ajouté** : il a été ajouté à la campagne Mistral en cours (S31), sans changement de produit :
  - chaîne `seg → tesseract:reco → lecture → mistral:correction`, même modèle et température qu'E3-small ;
  - les SHA-256 des 47 images et 47 vérités terrain, et les réglages effectifs de saknussemm, iront dans le README de campagne.
- **Matrice minimale** (détail dans `provenance_campagne.md`) :
  - A0→A4 : chaîne OCR → correction, une étape ajoutée à la fois ;
  - B0/B1 : VLM avec et sans segmentation, à `max_tokens` aligné ;
  - C0/C2 : Mistral OCR seul, puis corrigé.

## 3. Défauts trouvés en dehors des dix affirmations

| Défaut | Où | État |
|---|---|---|
| NER en mode détaillé : un label absent de la vérité terrain fait planter tout le run | `ner.py:338` | confirmé (test rouge) |
| Fan-out → saknussemm : une ligne de layout par région avec des `\n` ; rien n'est corrigé et le modèle est payé trois fois | `pipeline/fanout.py::_lignes_reconnues` | corrigé dans `aba0fe7` (branche de travail, **non mergé**, gelé) |
| L'archive n'était écrite qu'en fin de run : un run tué perd tout ce qu'il a payé | `pipeline/orchestrator.py` | corrigé dans le worktree de la campagne Mistral (**non mergé**, gelé) |
| saknussemm × `ollama` : `OllamaStructuredClient(timeout=300.0)` codé en dur, sans réglage. Sur CPU, la page BNL 0000 (28 lignes) donne 3 × 300 s puis 28/28 lignes en repli (1 847 s perdues). **L'unité est archivée `ok`**, et comme le délai est hors empreinte, elle est relue telle quelle ensuite. Une unité dont toutes les corrections ont échoué passe donc pour une mesure (affirmation 2) | `adapters/layout/saknussemm_correct.py::_build_producer` | constaté par la campagne locale ; réglage `timeout` en commit local **gelé**, unités dégradées purgées de l'archive locale |
| SIGINT : `cinoc run` n'arrête pas vite (`ThreadPoolExecutor.__exit__` attend la file) ; les unités terminées après l'interruption sont payées mais non archivées ; il faut un `kill -9`. Contredit l'invariant « annulation coopérative via `Deadline` + `RunControl` » | orchestrateur | constaté, **non corrigé** (gel) |

## 4. Effet sur les chiffres déjà affichés

- **Tableau partiel du README** (S30 : CER/WER « texte » sur BNL et Dresden). Les corpus n'ont pas de page à vérité terrain vide, donc le CER/WER micro est exact (identique à jiwer). Il est **non vérifiable** quant aux vérités terrain évaluées (affirmation 8).
- **Points exposés** :
  - les CER par région (E1/E3/E4) : appariement par identifiant, risque de collision `r1…rN` ;
  - tout résultat des chaînes à fan-out antérieur à `aba0fe7` ;
  - toute « différence significative » affichée à côté d'un CER micro.
- **Campagnes en cours** (Mistral ≈ 0,3 € dépensés, et modèles locaux). Les **sorties brutes restent bonnes**, re-notables quand le contrat sera arbitré. Mais leurs chiffres ne doivent pas être publiés tels quels.

## 5. Ce que le mainteneur doit arbitrer (avant tout correctif)

1. **Estimande publié et test associé.** Ratio micro du corpus (avec un test ou un IC apparié **sur la différence de ce ratio**, par permutation ou bootstrap par document ou par grappe) ou effet par document (Wilcoxon/Friedman, mais alors ne plus l'afficher à côté du ratio micro comme s'il le testait). Les deux peuvent coexister s'ils sont nommés.
2. **Observation métrique.** Remplacer `Observation(value, weight)` par des **comptes additifs** plus une **finalisation par métrique** appliquée de la même façon à la page et au corpus, avec bornes et pire valeur déclarées. Cela règle d'un coup les F1, les pages blanches, `max_error` et les planchers.
3. **Non-mesure typée.** Un statut par score (vérité terrain absente / inapplicable / incompatible / artefact absent / tronqué / échec) et un `expected` dérivé de la vérité terrain pour chaque unité.
4. **Issue par étape.** Garder les étapes réussies jusqu'à l'étape fautive (artefacts, coûts, évaluation), et reprendre par préfixe d'étapes.
5. **Archive scientifique distincte du cache.** Elle doit être :
   - scellée, avec un manifeste d'empreintes vérifié à la relecture ;
   - porteuse des vérités terrain et de la spec ;
   - sans chemin absolu ni lien suivi ;
   - sans aucun téléchargement à la relecture.

   Le `ResumeStore` reste un cache.
6. **Appariement de mise en page.** Géométrique, par page, optimal (Hongrois), l'id ne servant qu'à départager ; une seule projection `LAYOUT → texte`.
7. **Identité d'étape.** Empreinte mécanique (ou garde CI qui oblige à relever la version) ; bibliothèque, prompt et poids épinglés.
8. **Politique d'échec par défaut** pour le classement (`exclude` avantage le pipeline qui échoue sur les pages difficiles).
9. **Sort des correctifs gelés** (`aba0fe7` fan-out ; archive par unité) et des campagnes en cours.

Aucun tag, aucune publication, aucune nouvelle fonctionnalité n'a été faite. Rien n'a été mergé depuis la demande de contre-expertise.
