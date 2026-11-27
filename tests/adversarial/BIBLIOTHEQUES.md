# Étude de réutilisation : bibliothèques matures pour les contrats à revoir

Suite de la contre-expertise au commit `04a1c17b` (`tests/adversarial/README.md`).
Consigne du mainteneur : chercher les causes communes, simplifier les contrats,
examiner les bibliothèques matures avant toute réimplémentation, étudier BagIt
et RO-Crate avant d'inventer un format. **Aucun code produit n'a été écrit.**

**Méthode.** J'ai installé chaque candidat dans un venv séparé
(`scratchpad/libs-venv`, Python 3.13), lu son API, puis je l'ai essayé sur les
contre-exemples des rapports adversariaux. Les scripts d'essai sont dans
`scratchpad/libs-try/*.py`, hors de la copie figée. Les versions et dates
viennent de PyPI (27/11/2026).

**Lecture des verdicts :**
- **réutiliser X** : on appelle X.
- **méthode de X, N lignes maison** : la convention ou l'algorithme de X, réécrit
  parce que X pèse trop ou sort de la liste blanche.
- **maison** : rien de mature ne couvre le besoin.

---

## 0. Causes communes : ce que les bibliothèques confirment

1. **Statistiques suffisantes absentes (besoins 1, 2, 3 et 8).** Toutes les
   références comptent avant de diviser :
   - jiwer : `substitutions`, `deletions`, `insertions`, `hits` ;
   - nervaluate : `correct`, `incorrect`, `partial`, `missed`, `spurious` ;
   - scorer HIPE : TP, FP, FN ;
   - ocrd-segment-evaluate : sommes des aires et des comptes.

   Leur agrégat corpus est une **finalisation des comptes sommés**. Une fois
   l'observation faite de comptes, les outils de scipy s'appliquent tels quels.
   C'est vrai aussi du bootstrap **par grappe** : c'est le même appel sur les
   comptes sommés par grappe.
2. **Coordonnée d'étape absente (besoins 4, 5 et l'axe 9 du README).** Aucune
   bibliothèque ne répare cela. Le modèle de données établi existe :
   Provenance Run Crate prévoit une `ControlAction` par étape, avec
   `actionStatus` et `error`.
3. **Identité déclarée plutôt que calculée (besoins 5 et 7).** Le manifeste
   BagIt (`manifest-sha256.txt`) donne gratuitement l'empreinte de chaque image,
   vérité terrain et sortie. Le graphe RO-Crate dit qui a produit quoi.
4. **La page blanche n'est réglée par personne.** Pour une référence vide avec
   44 caractères inventés :

   | Outil | Valeur par document |
   |---|---|
   | jiwer | `cer` = 44 |
   | dinglehopper | ∞ |
   | nervaluate (rappel sans GT) | 0 |
   | ocrd-segment-evaluate | sentinelle −1 |

   Au niveau corpus, seul jiwer est juste (4,4), parce qu'il somme les comptes.
   Le statut de non-mesure reste donc **maison** (besoin 3).

---

## 1. Tableau récapitulatif

| # | Besoin | Recommandation | Couche | Nouvelle dépendance ? |
|---|---|---|---|---|
| 1 | Estimandes micro/macro, tests et IC sur la grandeur estimée, apparié, grappes | **Réutiliser `scipy.stats`** : `bootstrap(paired=True, vectorized=True)` sur les comptes, `permutation_test(permutation_type="samples")`, grappes = même appel sur les comptes sommés par grappe. Wilcoxon/Friedman inchangés (scipy). Nemenyi et Holm : garder les ~40 lignes maison, avec scikit-posthocs et statsmodels comme **oracles** de test. Méthode delta : **non** (fausse ici d'un facteur 4) | `evaluation` | non (scipy déjà là) |
| 2 | Observations à statistiques suffisantes, finalisation par métrique | **Méthode de jiwer / nervaluate, ~40 lignes maison** pour le contrat (`counts` + `finalize`). `rapidfuzz.editops` (déjà là) fournit S/D/I. jiwer, dinglehopper et nervaluate restent des **oracles**. Rejetés : `editdistance` (pas de S/D/I) et jiwer en production (doublon de rapidfuzz, plus click) | `evaluation` | non |
| 2-NER | Comptes NER, micro/macro, strict/partiel | **Méthode de nervaluate** (schémas SemEval 2013) et **conventions HIPE** (micro / macro_doc, strict / fuzzy), maison sur la reprojection R14 existante. nervaluate en **oracle** (0 dépendance, MIT). seqeval et le scorer HIPE sont **inapplicables** (jetons alignés exigés) | `evaluation` | non (nervaluate : dev/oracle) |
| 3 | Statut typé de non-mesure | **Rien de mature, maison** (`Literal` pydantic). Seule convention voisine : le `zero_division` de scikit-learn/seqeval | `domain` / `evaluation` | non |
| 4 | Résultats, coûts, statuts et artefacts par étape ; isolation et intégrité | **Maison** sur la stdlib (`hashlib`, `os.replace`, `os.link`) ; **méthode du cache DVC** (adressage par contenu, fichiers en lecture seule) ; **modèle de données** de Provenance Run Crate | `pipeline` / `app` | non |
| 5 | Archive scellée, portable, vérifiable, séparée du cache | **BagIt (RFC 8493) avec RO-Crate dans `data/`**, profil **Process Run Crate 0.6** (Provenance Run Crate pour les étapes). Validation : **réutiliser `bagit`** (LoC, un fichier, 0 dépendance, domaine public). `ro-crate-metadata.json` : **maison (~100 lignes pydantic)**, validé par `roc-validator` en job oracle. `rocrate` (ro-crate-py) en option seulement. W3C PROV seul : **non** | `app` | **oui : `bagit`** (liste blanche `app`) |
| 6 | Appariement de mise en page : par page, géométrique, optimal, fusions et scissions, ordre de lecture | **Réutiliser `scipy.optimize.linear_sum_assignment`** (déjà importé par `flexible.py`). IoU de boîtes : garder les 6 lignes maison. **Méthode PRImA / ocrd-segment-evaluate** (IoGT/IoDT ≥ 0,5) pour fusions et scissions, ~40 lignes. Ordre : `scipy.stats.kendalltau` ou le compte actuel, plus ~15 lignes pour l'ordre partiel. `shapely` seulement si un consommateur exige les polygones. `pycocotools` **rejeté** | `evaluation` | non (`shapely` : arbitrage) |
| 7 | Empreintes automatiques ; identité des données et GT ; modèle distant inconnu | `hashlib` (déjà là). Identité des données : **le manifeste BagIt**. Versions : `importlib.metadata` (déjà là) plus le hachage du `RECORD`. Empreinte de code : **méthode joblib / Snakemake**, fermeture AST ~40 lignes maison. JSON canonique : **méthode RFC 8785** (`rfc8785` si des flottants sont hachés). Distant : **maison** (`unknown` typé) | `pipeline` / `app` | non (ou `rfc8785`) |
| 8 | Performance conditionnelle, couverture, support commun, performance opérationnelle | **Méthode de fairlearn `MetricFrame`** (désagrégation). **Maison** sur les comptes : `group-by` par strate puis même finalisation ; couverture = statuts ; support commun = intersection ; opérationnel = quantiles numpy de l'usage par étape | `evaluation` | non |

---

## 2. Fiches par besoin

### Besoin 1 — Estimandes, tests et IC appariés, grappes

**Défauts visés** (`metriques_stats.md` B1 à B4) :
- le Wilcoxon contredit le CER micro (Simpson) ;
- aucun IC sur la différence ;
- les supports diffèrent ;
- aucune notion de grappe.

| Candidat | Maturité | Licence, dépendances | Essai sur un contre-exemple | Verdict |
|---|---|---|---|---|
| `scipy.stats.bootstrap` | scipy 1.18.1 (08/2026). Python 3.11 plafonne à scipy 1.17.1 ; plancher actuel `scipy>=1.11` | BSD, déjà en base | Simpson (12 × 20 car. ; 1 × 2 000 car.) : IC apparié de ΔCER micro (A − B), percentile [−0,10 ; 0,19], BCa [−0,10 ; 0,195]. Il **contient 0**, alors que Wilcoxon dit p = 0,0195. Cas B2 (B fait toujours une faute de plus) : IC [−0,01 ; −0,01], qui exclut 0 | **réutiliser** |
| `scipy.stats.permutation_test` (`permutation_type="samples"`) | idem | idem | Simpson : p exacte = **1,0** (2¹³ échanges), comme l'attendu du rapport. Ratio de sommes à dénominateurs **différents** par pipeline (MER, `bow_precision`) : échantillons 2-D `(num, den)` avec `axis=-1`, p = 0,8672, **identique** à l'énumération exacte écrite à la main | **réutiliser** |
| Bootstrap par grappe | ni scipy, ni statsmodels, ni `arch` (9.0.0 : IID, blocs, stationnaire, pas de grappe) | — | Sommer les comptes par grappe (`np.bincount`), puis appeler `bootstrap(paired=True)` sur les grappes. 6 manuscrits × 5 pages avec effet manuscrit : IC par document [−0,019 ; 0,003], IC par grappe [−0,034 ; 0,014], plus large comme attendu | **réutiliser scipy sur les comptes groupés** (0 ligne de rééchantillonnage maison) |
| Méthode delta (ratio de sommes) | classique | — | Simpson : erreur type 0,031 contre **0,131** au bootstrap. Une page à fort levier invalide la linéarisation | **rejeter** comme méthode principale |
| `scikit-posthocs` 0.18.0 (11/2026) | actif | MIT. Tire **pandas, seaborn, matplotlib, statsmodels** | `posthoc_nemenyi_friedman` et la règle CD de Cinoc (`inference.py:162`) donnent les **mêmes** paires significatives (k = 4, n = 20) | **oracle de test** seulement |
| `statsmodels` 0.15.0 (`multipletests(method="holm")`, SE robustes par grappe) | actif | BSD. Tire pandas, patsy, formulaic | — | **oracle** (Holm) ; trop lourd pour `evaluation` |

**Ce que cela remplace dans Cinoc :**
- `micro_ratio_ci` (`inference.py:182-215`, ~35 lignes) est remplacé par un
  appel à `bootstrap`. On gagne BCa et l'apparié.
- On ajoute environ 20 lignes : un IC apparié et une permutation de la
  différence par paire de pipelines, plus une clé de grappe facultative
  (`DocumentRef.metadata["cluster"]` ou un champ dédié).
- Sans changement : `omnibus_test`, Holm et Nemenyi, qui sont justes et testés
  contre scipy. Le payload doit en revanche nommer leur **estimande** (« effet
  médian par document »), ce qui ne dépend d'aucune bibliothèque.

**Ce qu'aucune bibliothèque ne couvre :**
- le **même support** pour l'agrégat, l'IC et le test. C'est une règle de
  sélection des documents en amont (`runner._inference_entries`) ;
- la **politique d'échec** par défaut (arbitrage 8).

**Risques :**
- `rng=` n'existe que depuis scipy 1.15 (`random_state=` avant).
- Les tirages de `bootstrap` dépendent de la version de scipy, et le flux de
  `numpy.Generator` n'est pas garanti stable d'une version à l'autre (NEP 19).
  L'invariant « mêmes octets » ne tient donc qu'à versions égales, ce que le
  manifeste trace déjà.
- Avec peu de documents et une page dominante, les méthodes percentile et
  « basic » divergent : sur Simpson, « basic » donne [0,145 ; 0,436]. Afficher
  le nombre de documents et de grappes est un garde-fou nécessaire.

### Besoin 2 — Observations à statistiques suffisantes

**Défauts visés :** 14 métriques sur 29 sont mal agrégées (`metriques_stats.md`,
tableau C), et la cause est unique : `Observation(value, weight)`
(`metric.py:22`).

**Conventions des références** (essais `t_text.py`, `t_counts.py`) :

| Outil | Ce qu'il expose | Agrégat corpus | Référence vide |
|---|---|---|---|
| **jiwer 4.0.0** (06/2025, Apache-2.0 ; click, rapidfuzz) | `process_characters` / `process_words` → S, D, I, H ; `cer`, `wer`, `mer` | **Σ comptes** : CER 4,4 sur le cas A1, attendu atteint | par document : `cer` = 44 (pas d'état « indéfini ») |
| **rapidfuzz 3.14.6** (08/2026, MIT, 0 dépendance ; **déjà en `evaluation`**) | `Levenshtein.editops` / `opcodes` → `replace` / `delete` / `insert` | à faire soi-même | `normalized_distance("", "xx")` = 1,0 |
| **dinglehopper 0.11.0** (04/2025, Apache-2.0 ; tire OCR-D) | `character_error_rate_n` → **(taux, n)** : la forme exacte de l'`Observation` actuelle | `cli_summarize` : **moyenne simple** des CER par page (macro) | ∞ |
| **ocrevalUAtion** (Java) | CER/WER par fichier et global | convention seulement, non intégrable | — |
| **editdistance 0.8.1** (2024, MIT) | une distance, **sans S/D/I** | — | — |

**Prototype hors produit** (`t_counts.py`, une vingtaine de lignes) :
`counts: Counter` par document et `FINALIZE[métrique](Σ counts)`. Il retrouve :
- CER corpus 4,4, identique à jiwer ;
- micro-F1 NER 0,7097, identique à nervaluate ;
- un IC apparié sur Δ micro par un appel à `scipy.stats.bootstrap`.

Le même `finalize` s'applique à la page et au corpus. Le plancher de
`char_accuracy` passe donc au niveau corpus (cause A8), et le F1 devient exact
(causes A2, A5, A7).

**Verdict :** méthode de jiwer et nervaluate, ~40 lignes maison. Le contrat
(type `Observation` à comptes, table des finalisations, bornes et pire valeur
déclarées) est propre à Cinoc. Aucune bibliothèque ne le fournit en dehors de
ses propres métriques.

**Ce que cela remplace :**
- `metric.py` (`Observation`), `micro_ratio` et `_aggregate` (`runner.py:307`),
  `_error_rate` (`text.py:114`) ;
- les 29 retours `Observation(value=…, weight=…)` deviennent des comptes.

Le bilan net est proche de zéro : le code se déplace sans grossir. jiwer reste
oracle en dev, dinglehopper oracle en job `oracle` (déjà en place).

**Corollaire, calibration (`layout_analyses.md` A4).** Le multi-ensemble de mots
glouton (`calibration.py:126`) se remplace par un alignement de séquences de
jetons avec `rapidfuzz.distance.Levenshtein.opcodes`, déjà dans la liste
blanche. Aucune nouvelle bibliothèque n'est nécessaire.

### Besoin 2-NER — Comptes d'entités

**Défauts visés :** `ner_f1` est une moyenne pondérée de F1 (A2), les faux
positifs d'un document sans GT sont ignorés (A3), et un label absent de la GT
fait planter le run (A4).

| Candidat | Maturité | Essai | Applicabilité |
|---|---|---|---|
| **nervaluate 1.2.1** (03/2026, MIT, **0 dépendance**, Python ≥ 3.11) | actif | Configuration A2 du rapport (doc 1 : 1 GT et 9 FP ; doc 2 : 10 GT) : correct 11, spurious 9, missed 0, **F1 0,7097** (attendu 0,710 ; Cinoc 0,926). FP sur un document sans GT : spurious compté, F1 0,5. Label présent seulement en prédiction : précision 0, rappel 0, F1 0, **pas de plantage**. Empan décalé d'un caractère : `strict` incorrect, `partial` 0,5, `ent_type` correct | Travaille sur des empans `{label, start, end}`, donc compatible avec les empans **reprojetés** de Cinoc (R14). Son appariement suit SemEval 2013 (recouvrement quelconque), pas l'IoU ≥ 0,5 de Cinoc (D-288) |
| **seqeval 1.2.2** (dernière version **10/2020** ; tire scikit-learn) | inactif | — | Étiquettes BIO **par jeton**, séquences de même longueur. Inapplicable : la sortie OCR n'a pas les jetons de la GT |
| **Scorer CLEF-HIPE 2020/2022** (impresso / hipe-eval, absent de PyPI) | stable, lié aux campagnes | — | TSV IOB sur les **jetons de la GT**. Fournit TP/FP/FN, **micro** et **macro_doc** (moyenne des micro par document), **strict** (bornes exactes) et **fuzzy** (au moins un jeton commun). Inapplicable tel quel ; ses **conventions** sont la référence du domaine patrimonial |
| `hipe-ocrepair-scorer` 0.9.9 (déjà extra `hipe-oracle`) | — | — | Post-correction OCR, **pas** la NER. Déjà utilisé comme oracle |

**Verdict :** méthode de nervaluate et HIPE. Le compteur reste maison, sur
`align_entities` et `compute_ner` (~80 lignes de `ner.py`). La reprojection
(~40 lignes) n'existe nulle part ailleurs. Les noms d'estimandes suivent HIPE :
`micro` et `macro_doc`, `strict` et `fuzzy`. nervaluate peut servir d'oracle sur
les empans reprojetés (dev, 0 dépendance).

Remplacer le seuil IoU ≥ 0,5 par les schémas nervaluate ou HIPE est un
**choix de convention** que je ne tranche pas. Il rendrait les chiffres
comparables aux campagnes HIPE.

### Besoin 3 — Statut typé de non-mesure

Aucune bibliothèque ne distingue « GT absente », « inapplicable »,
« incompatible », « artefact absent », « tronqué » et « échec ». Chaque outil a
sa convention :
- ∞ chez dinglehopper ;
- 0 chez nervaluate ;
- −1 chez ocrd-segment-evaluate ;
- `zero_division` (`"warn"`, 0 ou 1) chez scikit-learn et seqeval.

**Verdict : maison.** Un `Literal` pydantic en `domain` (comme `UnitOutcome` et
`FailureReason`), plus un `expected` dérivé de la GT. La seule dépendance est
pydantic, déjà en base.

### Besoin 4 — Résultats par étape, isolation physique, intégrité

**Défauts visés :** l'issue est portée par l'unité (`pipeline/types.py:96-99`),
le workspace n'a pas d'id d'étape (`adapters/_workspace.py:23-28`), et
`content_hash` n'est jamais vérifié.

| Brique | Source | Verdict |
|---|---|---|
| Écriture atomique | `tempfile` + `os.replace` (stdlib). L'extra `oracle` tire `atomicwrites`, **déprécié** en amont, à ne pas reprendre | **maison, ~10 lignes** |
| Vérification à la lecture | `hashlib.sha256` (déjà `compute_content_hash`) : recalcul à chaque relecture, refus sur écart | **maison, ~10 lignes** |
| Magasin adressé par contenu | méthode du cache DVC (`cache/ab/cdef…`, liens `reflink` > `hardlink` > `copy`, fichiers en lecture seule) ; Git fait de même | **méthode de DVC** (DVC 3.67 lui-même : application complète, hors de question comme dépendance) |
| Modèle « une issue par étape » | Provenance Run Crate 0.6 : une `ControlAction` par étape, `actionStatus` Completed/Failed, `error`, `object`/`result` par `CreateAction` | **modèle de données à reprendre**, ce qui aligne le contrat sur le format d'archive (besoin 5) |

Rien à installer. La correction est contractuelle : `step.id` doit entrer dans
le chemin et dans `RunContext`, et l'issue doit être portée par l'étape.

### Besoin 5 — Archive scientifique scellée, séparée du cache

**Défauts visés** (`artefacts_archive.md` P2 à P9) :
- pas de vérification ;
- pas d'immutabilité ;
- liens symboliques et chemins absolus suivis ;
- pas de GT ni de spec dans l'archive ;
- téléchargement à la relecture.

**Ce que garantissent les formats :**

| Propriété exigée | BagIt (RFC 8493) | RO-Crate 1.3 et profils Run Crate 0.6 |
|---|---|---|
| Fixité | Manifestes `manifest-<alg>.txt` obligatoires sur **tout** le payload ; SHA-256 et SHA-512 **obligatoires** dans les outils, SHA-512 par défaut. « Valide » = complet + empreintes vérifiées. `tagmanifest` pour les métadonnées | aucune (description seulement) |
| Portabilité, chemins relatifs | chemins relatifs, séparateur `/`, payload sous `data/`. §5.1 : l'outil **doit** empêcher tout accès hors du bag | `@id` relatifs à la racine du crate |
| Liens symboliques | **non mentionnés** par la RFC | non mentionnés |
| Contenus distants | `fetch.txt` : les « trous » doivent figurer au manifeste ; le bag n'est complet qu'après téléchargement | entités web (`@id` URL), éventuellement liées à `fetch.txt` |
| Provenance | `bag-info.txt` (paires clé-valeur libres) | `CreateAction` (instrument, object, result, agent, `endTime`, `actionStatus`, `error`) ; `SoftwareApplication.softwareVersion` ; `environment`, `containerImage` ; par étape (Provenance Run Crate) `ControlAction` et `HowToStep` |
| Sécurité active | hors champ (§5.4 : signatures à ajouter si besoin) | — |

**Combinaison standard.** La spécification RO-Crate décrit « RO-Crate dans un
Bag » : `ro-crate-metadata.json` à la racine de `data/`, le manifeste couvrant
tout `data/`, et un UUID frais recommandé dans `bag-info.txt`. Il existe un
précédent direct : **CWLProv**, produit par `cwltool --provenance`, est déjà
BagIt + Research Object + PROV, et `runcrate convert` le convertit en Workflow
Run Crate.

**Essais `bagit` 1.9.0** (06/2025, LoC, un fichier de 1 601 lignes,
0 dépendance, domaine public ; scripts `t_bag*.py`) :

| Cas | Résultat |
|---|---|
| Création + validation | valide |
| Un octet changé dans une sortie, même taille | **détecté**, SHA-256 et SHA-512 |
| Un octet ajouté | détecté (`Payload-Oxum`) |
| Lien symbolique vers l'extérieur, présent à la création ou substitué ensuite à un fichier listé | **refusé à l'ouverture** (`Path … is unsafe`, test par `realpath`) |
| Entrée de manifeste en `../` | **refusée** |
| Lien symbolique **intérieur** au bag | **suivi** ; le contenu est vérifié contre le manifeste |
| `fetch.txt` dont l'entrée n'est pas au manifeste | **accepté comme valide**, écart à la RFC §2.2.3 |
| Image partagée entre deux bags par **lien dur** | les deux bags sont valides, même inode. La mutualisation physique (arbitrage 5) est compatible |
| Image nommée par son SHA-256 (`data/images/<sha256>.png`) | compatible ; le manifeste redonne l'empreinte, ce qui sert de contrôle croisé gratuit |

**Essais `rocrate` 0.16.0** (ro-crate-py, 10/2026, Apache-2.0 ; tire
requests, jinja2, click, arcp, python-dateutil ; import en 0,3 s) :
- J'ai construit un crate avec image adressée par contenu, GT, sortie, deux
  `CreateAction` (une réussie, une `FailedActionStatus` avec `error`) et un
  `SoftwareApplication` distant en `softwareVersion: "unknown"`.
- Je l'ai écrit dans le payload d'un bag : le bag est valide et le crate se
  relit.
- `roc-validator` 0.14.0 (profil `process-run-crate`) ne relève **aucune
  violation REQUIRED du profil**. Seuls échecs : la résolution du contexte
  JSON-LD, hors ligne, et 4 RECOMMENDED de style (valeur unique plutôt que
  liste à un élément).
- `roc-validator` tire rdflib, pyshacl, rich, requests-cache… Il a sa place en
  CI, pas en base.

**Verdict :**
- **Format :** RO-Crate dans un Bag. Profil Process Run Crate 0.6 au minimum,
  Provenance Run Crate 0.6 pour l'issue par étape (besoin 4). Aucun format
  nouveau à inventer.
- **Validation à la relecture :** réutiliser `bagit` (`Bag(path).validate()`).
  Il apporte la fixité, la complétude et la défense contre les chemins
  dangereux. Il faut lui ajouter deux contrôles maison de quelques lignes :
  refuser **tout** lien symbolique (`os.lstat`), et refuser tout `fetch.txt`
  dans une archive scellée, puisque l'arbitrage 5 exclut le téléchargement à
  la relecture.
- **Écriture :** `bagit.make_bag` sur un dossier de préparation (il déplace le
  contenu en place dans `data/`), ou ~40 lignes maison. Le format est trivial
  (`bagit.txt`, `manifest-sha512.txt`, `tagmanifest`, `bag-info.txt`).
- **`ro-crate-metadata.json` :** maison, ~100 lignes de modèles pydantic pour un
  graphe fixe (Dataset racine, File, SoftwareApplication, CreateAction ou
  ControlAction), validé par `roc-validator` en job `oracle`. Ajouter ro-crate-py
  en base pour écrire un seul fichier JSON coûte 5 dépendances, dont un second
  client HTTP (requests, alors que Cinoc a choisi httpx).
- **W3C PROV** (`prov` 3.3.1) : à ne pas ajouter. Les Run Crates portent la
  provenance en schema.org, alignée sur PROV-O.
- **Cache :** le `ResumeStore` reste un cache mutable. L'archive scellée est
  **exportée** depuis lui (copie ou lien dur des contenus immuables) et n'est
  jamais réécrite.

**Ce que cela remplace :** rien n'est supprimé du `ResumeStore` (421 lignes).
On ajoute un exportateur et un vérificateur, soit environ 150 à 200 lignes au
lieu d'un format d'archive maison. Le `index.json` par unité est remplacé, côté
archive, par le graphe RO-Crate.

### Besoin 6 — Appariement de mise en page

**Défauts visés** (`layout_analyses.md` L1 à L6) : appariement glouton,
identifiants d'abord, pages aplaties, deux projections divergentes.

| Candidat | Maturité, poids | Essai | Verdict |
|---|---|---|---|
| `scipy.optimize.linear_sum_assignment` | scipy, **déjà importé** (`metrics/flexible.py:50`) | Matrice L1 du rapport (A-X 9/11, A-Y 7/13, B-X 9/11, B-Y 1/3), poids mis à 0 sous le seuil : **2 paires** (A↔Y, B↔X), contre 1 pour le glouton. Indépendant de l'ordre | **réutiliser** |
| `pycocotools` 2.0.11 (12/2025, BSD, Cython) | maintenu (fork ppwwyyxx) | IoU de boîtes identiques. Mais `COCOeval` apparie **gloutonnement par score de détection** : sur L1, 1 paire si X passe d'abord, 2 si Y passe d'abord. Il reproduit L1 et L2. Il mesure aussi une mAP sur des scores que les segmenteurs ne fournissent pas | **rejeter** |
| `shapely` 2.2.0 (10/2026, BSD ; GEOS, ~8 Mo installés ; Python ≥ 3.11) | très mature | IoU polygonal exact (0,7256 contre 0,6923 en boîtes sur un pentagone) ; matrice vectorisée ; `make_valid` sur un polygone PAGE auto-intersectant | **seulement si un consommateur l'exige** (voir § 3, point 2) |
| **PRImA Layout Evaluation** (Clausner, Pletschacher, Antonacopoulos, ICDAR 2011) | outil de référence, **pas de bibliothèque Python** ; la page PRImA n'indique ni licence ni plateforme | — | **méthode** : fusion = une région de l'hypothèse recouvre plus d'une région de la GT ; scission = l'inverse ; manque, manque partiel, fausse détection, erreur de classe ; poids par profil ; ordre de lecture avec groupes ordonnés et non ordonnés |
| **ocrd-segment-evaluate** (`ocrd_segment` 0.2.2, 10/2025, Apache-2.0 ; tire OCR-D, pycocotools, shapely, scikit-image) | actif mais lourd | J'ai lu `evaluate.py` (620 lignes) : COCO pour l'IoU, puis comptes de **sur- et sous-segmentation** par IoGT et IoDT ≥ 0,5, rappel et précision **micro par sommes**, et P/R/IoU **au pixel**. Sentinelle −1 pour l'indéfini. Un FIXME reconnaît que les scissions « admissibles » (dans le sens des lignes) ne sont pas distinguées | **méthode** (IoGT/IoDT) |
| Ordre de lecture : `scipy.stats.kendalltau` | scipy, déjà là | Sans ex æquo, (1 − τ)/2 égale la discordance normalisée de `reading_order.py` (0,1333 sur l'essai), en O(n log n) au lieu de O(n²) | **réutiliser** (facultatif) |

**Constat qui réduit la gravité de L1.** Pour des segmentations **planes**
(régions sans recouvrement) au seuil **strict** > 0,5, l'appariement est
**unique**. C'est le théorème qui fonde la Panoptic Quality (Kirillov et al.,
CVPR 2019). Glouton et hongrois ne diffèrent donc qu'avec des régions qui se
recouvrent (imbrication, couches ALTO, boîtes englobantes de polygones) ou au
seuil inclusif `>=` 0,5 qu'utilise Cinoc. Le hongrois reste la seule méthode
correcte dans tous les cas, et il est déjà dans la liste blanche.

**Verdict :**
- **Appariement :** réutiliser `linear_sum_assignment`, **par page**. L'id ne
  sert qu'à départager les ex æquo (arbitrage 6).
- **Fusions et scissions :** méthode PRImA et ocrd-segment-evaluate, ~40 lignes
  maison (matrices IoGT et IoDT, puis comptes), qui deviennent des comptes
  additifs (besoin 2).
- **Ordre partiel :** maison, ~15 lignes. On ne compte que les paires que la
  référence ordonne ; les paires d'un `UnorderedGroup` sont exclues.

**Ce que cela remplace :** `_greedy_pairs` (25 lignes), la branche « ids
d'abord » de `correspondance` et `_ordres`, et l'aplatissement multipage de
`_detection_boxes` et `_identified_boxes`. Au total, ~80 lignes réécrites sur
`metrics/layout.py` (463 lignes). La projection unique `LAYOUT → texte` ne
relève d'aucune bibliothèque : c'est un dédoublonnage interne entre
`projectors.py` et `adapters/layout/to_text.py`.

### Besoin 7 — Empreintes, identité des données, modèles distants

| Sous-besoin | Pratique établie | Essai | Verdict |
|---|---|---|---|
| Identité des images et des GT | Manifeste BagIt : une ligne `sha256  data/…` par fichier | voir besoin 5 | **réutiliser BagIt**. `RunResult` porte en plus une empreinte de corpus, hachage de la liste triée (id, sha256 de l'image, sha256 de chaque GT) : ~10 lignes |
| Version des bibliothèques | `importlib.metadata` (déjà dans `app/versioning.py`). Le fichier `RECORD` d'une roue liste le sha256 de **chaque** fichier installé | `bagit` : 7 entrées hachées ; `saknussemm` : 96. Pour une installation **éditable** (cinoc en dev), `RECORD` ne contient que le `.pth`, et `direct_url.json` indique `editable: true` | **réutiliser**. Empreinte d'une dépendance tierce = sha256 du `RECORD` ; signaler « éditable, empreinte non garantie » sinon. Limite : `RECORD` date de l'installation et n'est jamais revérifié |
| Empreinte du code d'une brique | joblib `Memory` : hache le **source de la fonction** décorée seulement (lu dans `memory.py` : `get_func_code`), pas ses appelées. Snakemake : déclencheur `code` (code de la règle, portée exacte non documentée sur la page de la CLI). DVC : fichiers de code **déclarés** en `deps`. Nix et Bazel : fermeture complète | Prototype `t_srchash.py` : fermeture AST des imports `cinoc.*` de `adapters.ocr.tesseract`, 17 modules, une empreinte. Trop sensible si l'on y met `domain` (un commentaire invalide le cache) ; restreinte au sous-arbre `adapters`, elle reste utile | **méthode, ~40 lignes maison**, à deux usages distincts : (a) **identité scientifique** enregistrée, fermeture complète, jamais dans la clé ; (b) **clé de cache** = version déclarée + garde CI qui échoue si l'empreinte source change sans que `version` bouge. C'est la séparation que pratiquent Snakemake (cache inter-workflows) et cwltool (`--cachedir` contre `--provenance`) |
| JSON canonique haché | RFC 8785 (JCS) ; paquet `rfc8785` 0.1.4 (Trail of Bits, Apache-2.0, 0 dépendance, 280 lignes) | `canonical_json` de Cinoc ≠ JCS sur les **flottants** (`0.0` contre `0`) et sur l'ordre des clés hors du plan multilingue de base (code points contre UTF-16). Identique sinon | **méthode RFC 8785**. Inutile tant que l'empreinte n'est recalculée que par Cinoc ; nécessaire si un tiers doit la vérifier hors Python. Dans ce cas, `rfc8785` (voir § 3, point 1) |
| Modèle distant inconnu | Rien d'établi. RO-Crate : `softwareVersion` est une chaîne libre | essayé dans le crate (`"unknown"`) | **maison** : état typé `unknown` plus modèle servi déclaré par le fournisseur, jamais une version inventée |

### Besoin 8 — Performance conditionnelle, couverture, support commun, opérationnel

| Candidat | Verdict |
|---|---|
| **fairlearn** 0.15.0 (10/2026, MIT ; tire scikit-learn, pandas) — `MetricFrame` : une métrique désagrégée par groupe (`by_group`), écarts entre groupes | **méthode** : désagréger les **comptes** par strate (`stratum` existe déjà dans `DocumentRef.metadata`), puis appliquer la même finalisation. ~20 lignes ; IC par strate par le même `bootstrap` |
| Couverture | **maison** : n mesurés / n attendus par statut (besoin 3). C'est le dénominateur que les compteurs actuels faussent |
| Support commun | **maison** : intersection des documents mesurés pour tous les pipelines comparés, appliquée **aussi** à l'agrégat affiché |
| Courbes risque-couverture (prédiction sélective) | rien de mature hors des bibliothèques torch ; **maison** si un consommateur apparaît |
| Opérationnel (latence, coût) | **maison** : quantiles `numpy` sur un usage **par étape** (correctif A3 de `layout_analyses.md`) ; `economics.py` existe déjà |

---

## 3. Points où un arbitrage du mainteneur bute sur `CLAUDE.md`

Je les signale sans les trancher.

1. **Liste blanche de la couche `app` (`test_layer_dependencies.py`, `LAYERS["app"]`
   = stdlib + pydantic + yaml).** Elle bute sur l'arbitrage 5. Réutiliser `bagit`
   pour vérifier l'archive impose de l'y ajouter (et en base : la relecture
   `--offline` est une capacité de base). Même chose pour `rfc8785` en
   `pipeline`, dont la liste blanche est stdlib + pydantic, si les empreintes
   doivent être vérifiables hors Python. L'alternative qui respecte la liste
   blanche : écrire le bag maison (~40 lignes) et n'utiliser `bagit` que comme
   oracle de test. C'est contraire à la consigne « réutiliser les bibliothèques
   matures ».
2. **Liste blanche de `evaluation` (pydantic, numpy, rapidfuzz, scipy) et
   invariant de déterminisme (§ 12).** Elle bute sur l'arbitrage 6 si l'IoU
   polygonal est exigé.
   - `shapely` n'y est pas.
   - Il ne peut **pas** être un extra optionnel avec repli sur les boîtes :
     la valeur d'une métrique dépendrait alors d'un paquet installé, ce qui
     viole « même spec, même corpus, même code → mêmes métriques ».
   - Il faut donc soit `shapely` en base dans la liste blanche, soit rester en
     boîtes. Aujourd'hui, la règle « pas de consommateur » (§ 5.3) plaide pour
     les boîtes (`metrics/layout.py:9` le dit déjà).
3. **Invariant « mêmes octets » (§ 12) contre arbitrage 1.** Déléguer le
   bootstrap à `scipy.stats.bootstrap` rend l'IC dépendant de la version de
   scipy, et le flux numpy n'est pas garanti stable non plus (NEP 19).
   L'invariant devient « mêmes octets à versions égales », ce que le manifeste
   permet de vérifier. À accepter explicitement, ou à garder le
   rééchantillonnage maison actuel (numpy seul), étendu à l'apparié et aux
   grappes (~15 lignes de plus).
4. **Arbitrage 5 (« aucun téléchargement à la relecture ») contre D-094
   (« images = références » dans `RunResult`, saveur « réfs IIIF »).** BagIt
   prévoit `fetch.txt` pour ces trous, mais un bag avec `fetch.txt` n'est
   **complet** qu'après téléchargement, et `bagit` 1.9.0 ne vérifie même pas
   que l'entrée figure au manifeste. Il faut choisir : copier les images IIIF
   dans l'archive scellée (poids, droits de diffusion), ou admettre une
   archive « à trous » dont la fixité n'est vérifiable qu'après récupération.
5. **§ 8.4 amendé (parité web/CLI, `test_web_cli_parity`, table `FRONT`).**
   « Vérifier une archive scellée » et « exporter une archive depuis le cache »
   sont des **capacités** nouvelles. Elles exigent une fonction en `app` et deux
   faces, ou une déclaration `front-absent` justifiée. Ce n'est pas un conflit,
   mais un coût à prévoir avec l'arbitrage 5.
6. **Règle « pas de consommateur = supprimé » (§ 5.3) contre profil complet.**
   Provenance Run Crate (`ControlAction`, `HowToStep`, `OrganizeAction`,
   `ParameterConnection`) ne doit être rempli que là où l'arbitrage 4 le
   consomme (issue par étape). Process Run Crate suffit pour le reste.
7. **Plancher Python 3.11.** Il n'y a pas de conflit pour scipy (≤ 1.17.1 sur
   3.11 ; `bootstrap` et `permutation_test` existent bien avant le plancher
   1.11), nervaluate (≥ 3.11) ni `bagit`. Mais `rng=` n'existe qu'à partir de
   scipy 1.15 : il faut relever le plancher `scipy>=1.11` ou passer
   `random_state=`.
8. **Oracles en CI et `tests/conftest.py` (réseau refusé, D-303).**
   `roc-validator` résout le contexte JSON-LD RO-Crate par le réseau. En job
   `oracle`, il faut soit un contexte local (`--profiles-path` ou cache), soit
   le marqueur `network`.

Aucun candidat n'ouvre de second point d'extension tiers (§ 3) : toutes les
bibliothèques citées sont des dépendances internes first-party.
