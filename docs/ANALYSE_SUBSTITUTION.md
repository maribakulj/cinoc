# ANALYSE_SUBSTITUTION.md — Ce que Cinoc réimplémente, et ce qu'il doit garder

> **Analyse, pas plan** (audit du 2026-11-25, D-264). Les décisions qui touchent
> la route vers la 1.0 sont reportées dans `PLAN_FIN_MIGRATION.md` (P5d → P5g) ;
> ce fichier garde les **preuves** qui les fondent. Verdicts **PROVISOIRES — à
> confirmer au build** (`CLAUDE.md` §9) : un prototype n'est pas une migration.

## Verdict

**L'hypothèse est réfutée pour l'essentiel.** Sur ~44 000 LOC de production, environ
**450 à 550 LOC** ont un équivalent direct dans une bibliothèque — et cet équivalent est,
dans presque tous les cas, une fonction de **scipy, numpy ou rapidfuzz, déjà
dépendances du cœur**. Aucune bibliothèque tierce examinée ne remplace un composant
avec profit : chacune est soit plus lourde de deux ordres de grandeur, soit moins
sûre, soit moins fidèle sur les données patrimoniales mesurées.

**Ce que l'audit a vraiment trouvé, ce sont des défauts** — vingt et un, dont deux
fuites réseau (corrigées, D-263) et plusieurs qui faussent des chiffres affichés.
Les comparer aux implémentations de référence a été le moyen le plus efficace de les
débusquer : c'est le rôle à donner à ces bibliothèques, **oracles de test**, pas
dépendances d'exécution.

## Méthode

Cinq audits parallèles (formats ; métriques ; statistiques ; adapters, LLM et IIIF ;
exécution, rapports et web). Chaque bibliothèque candidate installée **seule dans un
venv vierge** (taille et distributions transitives mesurées), comparée sur les données
du dépôt (`tests/fixtures/reference_corpus`, `corpus/37-GT-BNL`, `examples/`, PAGE
OCR-D réels, manifestes IIIF publics), maturité et licence lues sur PyPI. Prototypes et
sorties : scratchpad de la session, non versionnés (règle §5.3 : pas de code sans
consommateur) ; chaque chiffre ci-dessous dit d'où il vient. Non vérifié : statistiques
GitHub (API inaccessible), outils Java (PRImA, ocrevalUAtion), ARM.

## Cartographie

Décisions : **R** remplacer · **I** interfacer · **C** conserver · **C+** conserver et
corriger · **S** supprimer · **E** extraire.

### Formats et mise en page (`formats/`, `domain/layout.py`, `adapters/layout/`)

| Composant | Candidats | Preuve | Décision |
|---|---|---|---|
| `_xml.py` (parse durci) | defusedxml, lxml par défaut, parseurs d'ocrd et pagexml-tools | 10/10 vecteurs rejetés (XXE, entités paramètre, DTD externe, billion laughs, quadratique, DOCTYPE, imbrication 100 000, UTF-16), aucun accès disque sous `strace`. defusedxml : `.lxml` **déprécié**, accepte DTD externe et DOCTYPE par défaut, dernière version 2023. pagexml-tools accepte XXE en silence ; ocrd accepte DOCTYPE distant | **C** |
| Parseurs ALTO / PAGE | `ocrd_models` (OCR-D core 3.13), pagexml-tools 0.9.1, xsdata | PAGE : résultats identiques à ocrd sur 5 fichiers, Cinoc 2,4× plus rapide ; pagexml-tools échoue sur un PAGE préfixé `pc:`. ALTO : **aucune bibliothèque Python maintenue** ; xsdata échoue sur v2/v3/BnF et perd l'entrelacement String/SP | **C+** (lire les `<Word>` PAGE : 161 et 258 mots perdus sur deux pages OCR-D — **corrigé** D-273, 161/161 et 258/258 lus, identiques après aller-retour) |
| Writers ALTO / PAGE | ocrd_page, xsdata | **0/21 ALTO et 0/11 PAGE écrits par Cinoc valides au XSD officiel** (ALTO 4.4, PAGE 2019). ALTO : `PHYSICAL_IMG_NR`/`Page@ID` absents, `TextBlock@TYPE` interdit en v4. PAGE : `Metadata` et dimensions absents, types de région hors énumération, ImageRegion réécrite en TextRegion, sous-régions mal placées, `TextLine@id` manquant. Corrections locales ; l'oracle est `lxml.XMLSchema` + XSD vendorisés (aucune dépendance) | **C+** — contredit L9 de `MIGRATION_COUCHE_2.md` (« conforme par construction ») ; **corrigé** : ALTO D-272, PAGE D-273 |
| `CanonicalLayout` | DoclingDocument (docling-core), PcGts d'OCR-D | Docling perd ids de ligne, 3 339 mots et leurs confiances, SUBS, polygones ; rabat les boîtes hors page. ocrd_page : generateDS mutable, non pydantic, sans JSON. Le modèle Cinoc est le plus fidèle des trois en aller-retour ALTO | **C** ; Docling au plus en exporteur |
| `_geometry.py`, IoU | shapely 2.2 | IoU identique sur 20 000 paires ; Cinoc 10,7 ms, shapely 152 à 754 ms. Polygone ≠ bbox seulement en manuscrit (écart IoU ≤ 0,065) | **C** |
| `ocrd_processor.py` | API `ocrd` (+327 Mo, 75 distributions) | Pas de DAG typé, pas de cache par contenu, pas d'annulation coopérative. L'adapter lance 3 processus par page (~4-7 s fixes) ; un METS par gabarit en fait 1 ; `ocrd process` enchaîne plusieurs processeurs | **I** amélioré (METS gabarit, chaîne de processeurs, arrêt à l'annulation) |
| `reading_order.py` | Breuel (kraken, Apache-2.0), eynollah, docling | **Bug** : titre pleine largeur + deux colonnes → `columns` rend `T L1 R1 L2 R2`. Le test ne vérifie que le premier élément et la longueur | **C+** : porter Breuel (~35 LOC numpy, sans dépendre de kraken) |
| Code mort / doublons | — | `reading_order._feuilles` mort ; `to_text._feuilles` = `LayoutPage.leaf_regions` ; deux `_Counter` identiques | **S** (~30 LOC) |

### Métriques, alignement, normalisation (`evaluation/`, `formats/text/`)

| Composant | Candidats | Preuve | Décision |
|---|---|---|---|
| CER/WER/MER/cMER (`metrics/text.py`) | jiwer 4.0, dinglehopper 0.11 | Déjà adossés à rapidfuzz. Identiques à jiwer (audit précédent) et à dinglehopper **160/160** en appel par chaînes. dinglehopper : ~270× plus lent, 370 Mo / 83 distributions (ocrd obligatoire), WER d'une autre définition | **C** ; dinglehopper en **oracle CI** (variante légère `--no-deps`, 107 Mo) |
| 5 alignements `difflib` | `rapidfuzz.distance.Levenshtein.opcodes` | difflib est sous-optimal (425-616 éditions en excès sur le corpus) et **triple les lacunes** de la taxonomie face au WER affiché à côté (555 contre 168) ; signale comme hallucinations deux sorties simplement brouillées. Un helper de ~20 lignes : 55/55 tests passent (`merge=True`), 1,5-4× plus rapide | **R** (un helper ; `word_misses` fusionné avec `modernization_counts`) |
| `char_confusions` | `Levenshtein.editops` | Compte de substitutions = le S du CER (8 430 contre 7 024), 7× plus rapide | **R** (~−25 LOC) |
| `diagnostics.line_cers` | `lines.aligned_line_cers` (déjà au dépôt) | Lignes appariées par index : CER différent sur 1 131 des 2 340 lignes | **R** (~−17 LOC) |
| Normalisation (15 profils) | dinglehopper (table SBB), cor-asv-ann, ftfy | 5 des 19 clés Cinoc couvertes ailleurs ; u/v, i/j, ꝑ, ꝓ, ꝗ, œ, æ, ß nulle part. cor-asv-ann **ne s'installe pas** (tensorflow 1.15) et mute sa propre table en mémoire. Le shim `nfc`/`diplomatic` de `from_dict` et `from_yaml` n'ont aucun consommateur | **C**, **S** du shim (~−20 LOC) |
| NER (`ner_f1`) | nervaluate 1.2, HIPE-scorer, seqeval | Cinoc entre strict et fuzzy ; seule implémentation qui résiste à la dérive d'offsets OCR (reprojection R14) | **C** ; nervaluate seulement si un consommateur demande strict/partial |
| `roman.py` | paquet `roman` 5.2 | Concordent sur les 3 999 formes canoniques ; `roman` refuse les formes médiévales (iiij). **Bug** : `IIV`, `IXI`, `VIV`, `XIIX` acceptés ; les 5 « numéraux » détectés au corpus sont des mots (`ci`, `dix`) | **C+** ; `roman` en oracle de test |
| FCA, bow, diacritiques, philologie, structured_data | — | Rien d'équivalent en Python ; FCA absente de dinglehopper | **C** |
| `lines.percentile`, `kendall_distance` | `numpy.percentile`, `scipy.stats.kendalltau` | Identiques (0 écart) | **R** facultatif (~−22 LOC) |

### Statistiques (`evaluation/inference.py`, `longitudinal.py`, `inter_engine.py`, `calibration.py`, `adapters/merge/`)

| Composant | Candidats | Preuve | Décision |
|---|---|---|---|
| Nemenyi (table q, rangs) | `scipy.stats.studentized_range`, `rankdata` ; scikit-posthocs (+175 Mo, 20 distributions) | scipy = scikit-posthocs sur 5 000 tirages ; la table maison diverge dès k = 30 (153 verdicts différents à k = 50) et **renvoie silencieusement la colonne α = 0,05 pour tout α ≠ 0,01** | **R** par scipy (~−60 LOC) |
| Groupes d'indiscernables | barres CD (Demšar) | Sur BNL réel, le rapport implique 4 paires significatives là où il y en a 1 | **C+** (~15 LOC, barres chevauchantes) |
| Holm (absent) | statsmodels (+98 Mo), `scipy.stats.false_discovery_control` (BH/BY seulement) | Holm maison = statsmodels à 0,0 près | **10 lignes maison** |
| OLS (`linear_trend`) | `scipy.stats.linregress` | Identique à 4e-12 ; **aucune p-value aujourd'hui** : une pente non significative (p = 0,14) s'affiche comme tendance | **R** par scipy (gagne p et erreur-type) |
| Pettitt | pyhomogeneity (abandonné 2020, p Monte-Carlo sans graine, p = 2,0) | Identique en asymptotique ; Cinoc en O(n²), formule par rangs en O(n) | **C** |
| Jensen-Shannon | `scipy.spatial.distance.jensenshannon(base=2)**2` | Écart 1,6e-10 (attention : scipy rend la racine) | **R** (~−30 LOC) |
| Bootstrap stdlib | `numpy.random.default_rng` | 27-31× plus rapide, bit-identique sur numpy 2.1→2.4 et Python 3.11→3.13. La vraie raison du choix stdlib est la parité avec Picarones, pas le déterminisme | **R** possible — exige d'amender D-067 et de refaire un golden (décision mainteneur) |
| ECE/MCE | netcal, torchmetrics (exigent torch), sklearn | Convention de bornes différente : 2,9 % des jetons tesseract changent de bin | **C**, documenter la convention |
| Vote multi-moteurs (`_vote.py`) | ROVER : SCTK (CTM horodaté), crowd-kit (+410 Mo) | **Ce n'est pas un ROVER** : alignement en étoile sur la première source alphabétique, insertions perdues, **résultat qui dépend du nom des sources**. WER fusionné 0,089 contre 0,048 pour un ROVER, à 3 moteurs | **C+** : vrai ROVER maison (~80 LOC stdlib), crowd-kit en oracle hors CI |

### Adapters, LLM, corpus (`adapters/llm`, `ocr`, `correction`, `corpus`)

| Composant | Candidats | Preuve | Décision |
|---|---|---|---|
| 4 adapters LLM + `_base` | **LiteLLM** 1.111, any-llm-sdk 1.54, aisuite | LiteLLM marche (prototype de 75 lignes : troncature, modèle servi, cache, coût) mais : **277 Mo / 61 distributions**, import 3-4 s et ~300 Mo de RAM, **appel réseau à l'import** qui télécharge sa table de prix (coût dépendant de l'heure d'import, incompatible avec le mode public fail-closed), 270 versions en 12 mois, **versions 1.82.7/1.82.8 compromises sur PyPI le 2026-03-24** (voleur d'identifiants). any-llm : 74 Mo, pas de table de coûts | **C+** ; LiteLLM au plus en **plugin tiers** (`cinoc.modules`), jamais au cœur |
| `_resilience.py` | tenacity, stamina | `network_slot` (plafond par fournisseur) n'existe chez aucun ; le retry s'empile sur celui des SDK (un 429 = 2 requêtes invisibles) | **C** `network_slot`, **une seule** couche de retry |
| `pricing.json` | `litellm.model_cost` | EUR, datée, tarifs à la page : aucun équivalent. Divergence déjà visible sur mistral-small | **C** ; LiteLLM en test hors CI de dérive des prix |
| Tesseract | pytesseract (déjà), tesserocr | **L'OCR est calculé 2 à 3 fois par page** (`image_to_string`, `image_to_data`, `image_to_alto_xml`). Un seul appel du binaire avec plusieurs renderers : même texte, mêmes mots, même ALTO, **2,7-3,9× plus rapide**, confidences plus précises. tesserocr embarque une autre libtesseract (5.5.4 contre 5.3.4 système) : texte différent, manifeste faux | **C+** : un appel, `OMP_THREAD_LIMIT=1` |
| Azure DI, Google Vision | SDK officiels (4 Mo + azure-core ; 46 Mo + grpcio) | Pile HTTP unique et cassettes : légitime | **C** (ajouter le retry) |
| `iiif.py` | iiif-prezi3 3.1, iiif-prezi (2019), piffle | iiif-prezi3 ne lit que la v3, rejette 7/12 manifestes réels, **accepte en silence** une v2 à 0 canvas, impose `requests`. **Deux bugs Cinoc** : Bodleian v2 → l'`@id` du service est pris pour l'image (303 vers `info.json`) : **corpus de JSON déguisés en images** ; Wellcome v3 → vignette 742×1024 au lieu de 2569×3543 : **OCR sur 12× moins de pixels** | **C+** |
| `_http.py` (anti-SSRF) | advocate (2020, requests), httpx-secure (async seulement) | Seul client synchrone à IP épinglée + IPv4 embarquée (NAT64) + plafond. Deux trous trouvés et **fermés** (D-263) | **C** |
| `escriptorium.py` | escriptorium-connector 0.2.6 | Exige `pydantic<2`, `lxml<5` : incompatible | **C** |
| `mistralai<2` | — | PyPI en est à 3.9 : plafond à revoir avec le SDK | à P5f item 8 |

### Exécution, rapports, web, infrastructure

| Composant | Candidats | Preuve | Décision |
|---|---|---|---|
| Exécuteur + fan-out | OCR-D, Prefect/Dagster | Voir `ocrd_processor` : inadéquat au DAG typé | **C** |
| `resume.py` | diskcache (2023), joblib.Memory | joblib sert un **résultat périmé** quand les octets changent sous le même chemin ; diskcache ne copie pas les fichiers. **Défaut Cinoc** : la clé ignore les binaires système (mise à jour de tesseract → anciennes sorties sous un manifeste qui annonce la nouvelle version) | **C+** (rejoint P5f 2b) |
| `reports/svg.py` | pygal (LGPL, `<script>` à uuid aléatoire), matplotlib-SVG (+60 Mo, 600× plus lent, couleurs en dur), leather | Cinoc 1-2 ko par graphique, déterministe, sans script, thème CSS ; pygal casse CSP et déterminisme | **C** |
| `reports/html.py` | — | ~580 des 702 LOC sont du **CSS littéral** | **E** vers `_assets/report.css` (libère une exemption de budget) |
| Sections du rapport | Jinja2 | 5 600 LOC à réécrire ; fuzz XSS (FR/EN) : 0 charge brute dans le DOM | **C** |
| i18n web | gettext + Babel (+35 Mo) | Équivalence totale prouvée, mais 1 373 lignes de `.po`, étape de compilation, 254 appels de gabarit à réécrire, aucun pluriel à servir. Le dictionnaire lève sur clé absente, gettext non | **C** ; `StrictUndefined` Jinja2 + test de parité FR/EN ; **S** `library_open` |
| CLI (argparse) | typer (+15 Mo), click | Les garde-fous lisent `build_parser().subcommands` | **C** |
| Prétraitement image | opencv (+225 Mo), scikit-image (+224 Mo) | Otsu identique (129) sur 3 images | **C** |
| Registre, découverte, versioning, jobs, historique | pluggy, sqlite-utils, Celery/RQ | Déjà sur la stdlib (`importlib.metadata`, `sqlite3`, `concurrent.futures`) | **C** |
| `dalembert.py` | minicons | ~30 LOC remplaçables, au prix d'une recalibration de Platt | **C** |

## Dépendances rejetées, et pourquoi

| Bibliothèque | Poids mesuré | Raison du rejet comme dépendance | Usage retenu |
|---|---|---|---|
| ocrd (OCR-D core) | 327 Mo, 75 distributions | opencv, docker, pymongo… ; pas de DAG typé ; parseur moins durci | interface CLI (`ocrd_processor`) |
| dinglehopper | 370 Mo (107 Mo sans ocrd) | 270× plus lent, WER d'une autre définition | **oracle CI** |
| LiteLLM | 277 Mo, 61 distributions | réseau à l'import, prix non reproductibles, incident PyPI 2026-03 | plugin tiers éventuel ; test de dérive des prix |
| pagexml-tools | 236 Mo | XXE accepté, échec sur namespace préfixé | — |
| docling-core | 160 Mo | perd mots, ids, confiances | exporteur futur si un consommateur apparaît |
| scikit-posthocs / statsmodels | +175 / +98 Mo | trois lignes de scipy font le même calcul | oracle ponctuel |
| crowd-kit | ~+410 Mo | transformers pour un vote | oracle ROVER hors CI |
| pygal | 0,9 Mo | LGPL, script non hachable, non déterministe | — |
| defusedxml | — | `.lxml` déprécié, moins strict que `_xml.py` | — |
| netcal / torchmetrics | torch | — | — |
| iiif-prezi3 | — | v3 seulement, accepte une v2 vide en silence | — |
| cor-asv-ann | tensorflow 1.15 | ne s'installe pas, état global muté | tables de niveau 1 comme **donnée** si un profil OCR-D est demandé |

**Retenus comme oracles de test, sans dépendance d'exécution** : XSD ALTO/PAGE
officiels (lxml), dinglehopper, `roman`, scipy (déjà là), HIPE-OCRepair scorer (déjà
l'extra `hipe-oracle`), crowd-kit et LiteLLM hors CI.

## Défauts trouvés

| # | Défaut | Gravité | Statut |
|---|---|---|---|
| 1 | Segmenteur distant : validation SSRF puis seconde résolution DNS | sécurité | **corrigé** (D-263) |
| 2 | Auth renvoyée sur redirection vers un autre port / https → http | sécurité | **corrigé** (D-263) |
| 3 | ALTO et PAGE écrits invalides au XSD officiel | conformité | **corrigé** : ALTO (D-272), PAGE (D-273) |
| 4 | IIIF v2 : URL du service prise pour l'image (corpus corrompu) | intégrité des données | → P5d item 7 |
| 5 | IIIF v3 : vignette au lieu de l'image pleine résolution | biais de mesure | → P5d item 7 |
| 6 | Vote multi-moteurs : pas un ROVER, dépend du nom des sources | justesse | → P5e item 11 |
| 7 | Taxonomie et hallucinations sur `difflib` sous-optimal | justesse | → P5e item 11 |
| 8 | Pires lignes appariées par index | justesse | → P5e item 11 |
| 9 | Nemenyi : colonne α = 0,05 servie pour tout α ≠ 0,01 | justesse | → P5e item 4 |
| 10 | Tendance OLS affichée sans test de significativité | justesse | → P5e item 11 |
| 11 | Romains absurdes acceptés ; mots détectés comme romains | justesse | → P5e item 8 |
| 12 | Ordre de lecture `columns` entrelace les colonnes sous un titre large | justesse | → P5e item 11 |
| 13 | Clé de reprise aveugle aux binaires système | reproductibilité | → P5f item 2b |
| 14 | PAGE : `<Word>` ignorés à la lecture | perte de données | **corrigé** (D-273) |
| 15 | `alto_source` : lignes sans ID non vérifiées sous ComposedBlock | justesse | **corrigé** (D-273) |
| 16 | Tesseract exécuté 2-3× par page ; OpenMP non borné | coût | → P5g item 6 |
| 17 | `ocrd_processor` : 3 processus par page, non tués à l'annulation | coût, annulation | → P5g item 6 |
| 18 | Calibration : convention de bornes différente des références | documentation | → P5e item 9 |
| 19 | i18n web : une clé mal orthographiée rend `''` en silence | robustesse | → P5g item 6 |
| 20 | Version Unicode (`unidata_version`) absente du manifeste | reproductibilité | → P5f item 2 |
| 21 | Registre : `bool("false")` vaut `True` (`registry.py:193`) | robustesse | → P5g item 6 (non vérifié côté web) |

## Ce qui reste la contribution propre de Cinoc

Ce que l'audit n'a trouvé **nulle part ailleurs**, et qui justifie donc le code
maintenu : le DAG d'artefacts typés avec fan-out par région et fusion multi-sources ;
la reprojection d'entités résistante à la dérive OCR (R14) ; les profils de
normalisation patrimoniaux (u/v, i/j, abréviations, MUFI) ; les métriques
philologiques ; le parseur ALTO tolérant aux variantes BnF ; le transport anti-SSRF
synchrone à IP épinglée ; le rapport autonome déterministe sous CSP stricte ;
l'économie datée en euros. C'est là que doit aller l'effort — pas dans un client LLM
ou une table de Nemenyi.
