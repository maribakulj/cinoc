# Changelog

Tous les changements notables de Cinoc. Format inspiré de
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; versionnage SemVer.
La version est dérivée des tags git (`setuptools_scm`) ; le journal **décisionnel
granulaire** vit dans [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md).

## [Non publié]

Préparation de la `1.0.0` : réécriture propre de Picarones sous le nom **Cinoc**,
architecture en 8 couches concentriques vérifiée mécaniquement, moteur de
benchmark déterministe, et **toutes** les familles de métriques jugées utiles.

**Aucune version n'est publiée** : le dépôt ne porte aucun tag. La décision de
publier, et son moment, appartiennent au mainteneur.

Pour qui suivait déjà la branche `main`, les changements qui cassent un usage
existant sont réunis sous **Ruptures**, juste en dessous ; les sections
suivantes ne les répètent pas.

### Ruptures (pour qui suivait `main`)

**Installation**

- `pytesseract` et l'extra `[tesseract]` disparaissent : Cinoc lance le binaire
  `tesseract` lui-même, seul le binaire est requis.
- Les SDK des moteurs distants sont épinglés par majeure : `openai>=3,<4`,
  `anthropic>=2,<3`, `mistralai>=3,<4`.
- `pydantic>=2.10` (les sommes exactes de la calibration sont des
  `fractions.Fraction`, D-313).
- `OPENAI_BASE_URL` n'est plus lue (un avertissement le dit si elle est posée) :
  un serveur compatible OpenAI se règle par instance, dans la spec.

**Ce que mesurent les chiffres**

- Le banc est **rapide par défaut** : seules les métriques déclarées sont
  calculées. Les analyses (inférence détaillée, bilans de correction, décisions
  du correcteur…) se réclament par `analyses: "toutes"` dans la spec,
  `cinoc run --analyses toutes`, ou la case *Mode détaillé* de la page.
- La vue `texte` compare désormais sous une normalisation par défaut : NFC,
  caractères invisibles retirés, tout blanc (sauts de ligne compris) réduit à
  une espace, bords retirés. Une seconde vue `texte (lignes)`, où le saut de
  ligne compte, s'ajoute quand la vérité terrain tient sur plusieurs lignes.
  Les CER d'avant, calculés sur le texte brut, ne se comparent pas à ceux-ci.
- Une unité en échec est enregistrée, **exclue** de la moyenne et montrée
  (n notés / n attendus à côté de chaque agrégat) ; elle comptait jusqu'ici
  comme une absence muette.
- La métrique `hallucination` s'appelle `unanchored_trigrams` (même calcul) ;
  un ancien score se relit sous son ancienne clé, sans glossaire, et
  `cinoc compare` ne l'apparie pas au nouveau nom. Le champ
  `n_hallucination_heavy` du bilan de correction devient `n_heavy_insertion`,
  et un bilan d'avant est refusé.
- Seules les métriques **établies** classent les moteurs et entrent dans les
  tests de significativité ; les métriques adaptées et exploratoires passent
  dans une table *Diagnostic*.
- Le test affiché est corrigé de Holm sur les tests du run, et le post-hoc ne
  dit que ce qu'il sait.
- **Statistiques suffisantes** (refonte des contrats, tranche 1a, D-313) :
  chaque observation porte les comptes de sa famille — (S, D, I, n_réf),
  (erreurs, n_réf), (tp, fp, fn) ou (k, n) — et l'agrégat d'un moteur est la
  métrique calculée sur leur **somme**, non plus une moyenne pondérée des
  valeurs par document. Valeurs qui changent, et pourquoi :
  - une page à **référence vide** entre au CER, au WER, à `ins_rate`,
    `del_rate`, `cer_diplo`, `region_cer` et `line_identity_cer` du corpus par
    ses insertions (elle en était exclue) ; son propre scalaire est
    **indéfini** (il valait 1 ou 0) ; un corpus entièrement vide a un CER
    indéfini, le total des insertions publié ;
  - les comptes S, D, I sont **canoniques** (parmi les alignements de coût
    minimal, celui qui maximise S) : `ins_rate`, `del_rate`, MER et cMER
    changent sur les alignements ex æquo (« a b »/« b a » : MER 1,0, jiwer
    0,667), CER et WER jamais ;
  - F1 NER, `region_detection` et `bow_f1` au corpus sont le F1 des comptes
    cumulés ; un document sans entité de référence apporte ses faux positifs ;
    une catégorie seulement prédite a un rappel indéfini, sans erreur ;
  - `char_accuracy`, `word_accuracy` et `fca` au corpus : max(0, 1 − Σe/Σn),
    le plancher appliqué au corpus et non page par page ; le taux d'erreur
    non tronqué et ses comptes sont publiés à côté ;
  - `reading_order_tau` au corpus : Σ discordantes / Σ paires ; une
    proportion à dénominateur nul (`mufi_err` sans glyphe MUFI…) est
    indéfinie, plus « non applicable » ;
  - ECE et MCE en arithmétique exacte (au dernier chiffre près), identiques
    quel que soit l'ordre des jetons et des documents.
- `failure_policy: max_error` est **retiré** : « la pire valeur de l'échelle »
  n'est la statistique d'aucune sortie. `failure_policy: empty_page` le
  remplace : l'unité en échec est notée comme une page vide (un CER de 1, une
  exactitude de 0, un taux d'insertion de 0), sous ce nom.
- L'intervalle du micro d'un MER ou d'un cMER, dont le dénominateur dépend de
  la sortie, n'est plus publié : « inférence non estimable ».
- **Non-mesure et supports** (refonte des contrats, tranche 1b, D-313) :
  - une sortie **tronquée** n'est plus notée par défaut (elle l'était) : elle
    porte l'axe `truncated_output`, sa statistique est gardée à part
    (`stat_partielle`) et la couverture la compte ; une sortie **partielle**
    (régions perdues d'un fan-out, lignes de correction restées en repli) fait de
    même, l'unité devenant `partial` — jamais `ok` ;
  - chaque agrégat est publié en deux qualités, **conditionnelle** (observations
    complètes) et **opérationnelle** (partielles notées telles que produites,
    échecs comme une page vide), avec leur couverture ; `failure_policy` choisit
    la principale (`aggregate`) ; `empty_page` note désormais aussi les
    sorties partielles et tronquées telles que produites ;
  - le **macro** (moyenne sur D^M, par document ou par grappe), les supports
    apparié et global (`comparison`) et l'« invention hors référence » sont
    publiés ; `support` d'un agrégat est |D^μ|, les attendus sont les
    observations applicables (un artefact absent du disque ou une vérité
    terrain illisible compte, avec son motif, au lieu d'abattre le run) ;
  - une vérité terrain référencée mais **absente du disque** est refusée
    avant le premier appel de moteur ;
  - `not_transcribed` (vérité terrain vide non saisie) ≠ page blanche ;
    `DocumentRef.cluster`, `CorpusSpec.target_population` et
    `cluster_weighting` (B3) ;
  - les quatre issues d'une ligne de correction structurée (corrigée, à
    revoir, abstention, refus par code, repli par code) sont comptées par unité
    et par pipeline ; seul le repli rend l'étape partielle ;
  - tout résultat de test de l'ancienne inférence est **exploratoire**
    (`InferencePayload.status`, `significance_p`) : ni « significatif » ni « non
    significatif » ne qualifie un résultat, dans les sections inter-moteurs et
    mesures clés comme dans l'historique ; la rupture de Pettitt s'affiche dès
    que le test est calculable (au moins 3 runs, série non constante), avec sa
    p ;
  - le rapport **affiche** ce que le résultat publie : les deux qualités avec
    leur couverture, le tri du support global, une section « comparaison
    appariée » (supports par paire, invention hors référence), la population
    cible et la pondération du macro, les issues de lignes déclarées par
    l'adaptateur (classes disjointes : corrigée, à revoir, abstention, refus,
    repli) ; une sortie illisible (mise en page invalide, octets non UTF-8) est
    notée comme une sortie vide dans la qualité opérationnelle, et une vérité
    terrain illisible refuse le run avant le premier appel de moteur ;
  - les confusions, la taxonomie et le diff surligné portent leur
    `alignment_path` (`rapidfuzz`), de même que les cartes de mots, la fidélité
    textuelle et le bilan de correction, et le rapport l'écrit ; les confusions
    et la taxonomie portent `matches_canonical_counts` ; les comptes d'édition
    sont canoniques (`EditCounts.alignment_path`) ;
  - seconde revue : « Significativité inter-moteurs » et « Significativité &
    recouvrement » deviennent « Tests inter-moteurs (exploratoires) » et
    « Tests et recouvrement (exploratoires) » ; le texte d'un test nomme ses
    observations (« observations complètes » sous `exclude`, « observations
    opérationnelles (échecs notés comme une sortie vide) » sous `empty_page`, plus
    jamais « cas complets ») et écrit le CER micro de chaque moteur **sur le
    support du test** ; l'autre qualité est écrite à côté de l'agrégat principal
    (mesures clés, comparaison des moteurs, fiches moteur), avec sa couverture ;
    la flèche de tri suit le sens de la métrique ; une liste de confusions
    tronquée dit « les k plus fréquentes sur N » ; un sidecar sans classe de
    ligne s'écrit « classes non déclarées par l'archive », jamais des zéros ; un
    pipeline hors vue n'a aucune ligne dans les tableaux par document ; la
    comparaison de deux runs dit la politique et la qualité de chacun ;
  - un document sans grappe forme sa propre grappe, distincte d'une grappe
    déclarée de même nom (le macro par grappe ne les fusionne plus) ;
    `stat_partielle` est `None` pour une sortie illisible, même partielle ou
    tronquée (sa statistique vide va dans `stat_vide`).

**Format**

- `RunResult` passe en version **7** (D-313) : `MetricScore` gagne `stat`
  (la statistique suffisante), `scalar_reason`, `untruncated_error_rate` et
  les axes de l'observation ; par document, `support` n'est plus un poids
  (les dénominateurs sont dans `stat`). Un JSON d'une version antérieure est
  **refusé** avec un message — ni relu, ni converti — et se re-note depuis son
  archive (`cinoc run --resume-dir … --offline`). Le CSV gagne les colonnes
  `statistic`, `scalar_reason` et `untruncated_error_rate`. Les versions 6 et 7
  n'ont jamais été publiées : `stat_partielle`, `stat_vide` (la statistique
  « sortie vide » de chaque unité notée vide), `macro`, `macro_support`,
  `coverage`, les agrégats `conditional_aggregate` et `operational_aggregate`,
  `line_outcomes`, `step_issues` (par étape, l'ensemble trié de ses issues),
  `cluster` (par document), `target_population`, `cluster_weighting`, les
  analyses `comparison` et `invention_outside_reference`, `status` de
  l'inférence et de `significance_p`. L'agrégat **principal** n'est plus
  stocké : il se dérive de `failure_policy` (`RunResult.principal_aggregate`),
  et un pipeline qui ne voit pas une vue (aucune étape ne déclare un type
  qu'elle note) n'a aucun agrégat dans cette vue. `PairwiseDifference` perd son
  booléen `significant`.
  Seconde revue de 1a + 1b : un JSON **sans** `schema_version` est refusé comme
  un JSON antérieur (le chargeur et le widget « comparer un run »), le CSV
  exporte les **deux qualités** (colonnes `quality` et `principal`), `diagnostics`
  porte `n_pairs` et `n_substitutions` par pipeline (une liste de confusions
  tronquée le dit), et `decisions` porte `status` : `not_declared` pour un
  sidecar sans `line_class`, sans aucun compte.

**Ce qui est désormais refusé au lieu d'être ignoré**

- Une étape qui ne déclare aucun type de sortie (`output_types` vide) : refusée
  au chargement, par son nom (`load_run_spec`, `cinoc run --check`, dépôt de
  spec du web).
- Un réglage qu'une brique ne déclare pas, et un réglage pour une étape
  facultative non retenue.
- Une table « classe → réglage » qui ne parle pas la langue de son segmenteur
  (refusée avant le run).
- Une commande `cli_layout` qui contient un antislash (chemin Windows) : le
  découpage est POSIX, la forme à écrire est donnée.
- Une spec écrite à la main qui noterait un ALTO contre la vérité extraite de
  lui-même.
- Deux pipelines qui écriraient le même fichier ALTO (ils s'écrasaient).

**Ligne de commande**

- `cinoc run` sort en code **3** quand au moins une unité a échoué (rapport,
  JSON et CSV écrits quand même), **1** quand le run est impossible, **0**
  sinon ; il sortait en 0 sans bilan.
- `cinoc correct` : sans `--ocr-sidecar`, la vue `structure` n'est plus
  ajoutée (l'ALTO corrigé n'est plus sa propre vérité) ; `--no-ground-truth`
  ignore désormais toute vérité, `.gt.txt` compris.
- `cinoc corpus import zip` d'une archive sans extension `.zip` garde son nom
  entier (il était coupé au dernier point).
- L'identifiant de capacité de la post-correction structurée devient
  `structured_correction`.

**Fichiers produits**

- L'ALTO écrit par Cinoc s'appelle partout `<doc>.<pipeline>.alto.xml`
  (`cinoc run --alto-dir`, `cinoc hybrid`, `alto.zip` du web, qui portait un
  autre nom) ; l'identifiant de document y garde ses points.
- Les pipelines lancés depuis la page portent le nom de leur recette, comme en
  ligne de commande (`ocr_simple · tesseract`, `… #2` pour un homonyme).

**Application web**

- Sans `CINOC_DATA_DIR`, `cinoc serve` et `create_app()` écrivent sous un
  dossier **par utilisateur** (`~/.local/share/cinoc`,
  `~/Library/Application Support/cinoc`, `%LOCALAPPDATA%\cinoc`) au lieu d'un
  temporaire neuf à chaque lancement ; le mode public
  (`CINOC_PUBLIC_MODE=true`) reste éphémère. Les rapports déposés
  (`--reports-dir`) sont recopiés à chaque lancement : un rapport relancé est
  servi dans sa dernière version, un rapport retiré du dépôt n'est plus listé.
- Un corpus déposé `x.zip` s'appelle `x` (il gardait l'extension).
- L'état d'un job (`GET /api/runs/<id>`, SSE) gagne `pipeline`, `document_id`
  et `outcome`.
- Le message d'un modèle absent change de forme : il donne
  `--set <étape>.model=…` et la ligne `adapter_kwargs` d'une spec.

**API Python et extension**

- `ArtifactType.CANONICAL_DOCUMENT`, `READING_ORDER` et `ALIGNMENT`, jamais
  produits ni lus, sont retirés ; l'ordre de lecture vit dans
  `LayoutPage.reading_order`.
- La normalisation n'a plus qu'une entrée, `from_yaml_text` (`from_dict`,
  `from_yaml`, les raccourcis `nfc`/`diplomatic` et `default_name` sont
  retirés).
- Les trois clients de la post-correction structurée quittent
  `cinoc.adapters.llm` pour `cinoc.adapters.correction`.
- `cinoc.app.corpus_upload` : `MAX_ZIP_BYTES` s'appelle `PUBLIC_MAX_ZIP_BYTES`,
  le plafond d'un déploiement se lit par `upload_zip_limit(public_mode=…)` ;
  `extract_corpus_zip` lit un flux binaire positionnable (un fichier ouvert) et
  non plus des octets, et `CorpusStore.save` exige `max_zip_bytes`.

### Ajouté

**Le banc**

- **Moteur déterministe** : pipelines OCR / HTR / VLM / OCR→LLM, exécutés par
  un orchestrateur unique (CLI **et** web), `RunManifest` reproductible,
  annulation et timeout coopératifs.
- **Recettes** (`cinoc list recipes`) : une forme de pipeline nommée par son
  intention — OCR seul, OCR puis LLM, VLM seul, segmentation puis lecture,
  vote de trois moteurs, ALTO corrigé… —, des briques et des réglages au choix,
  des étapes facultatives (`--with`) ; plusieurs recettes en file forment un
  run comparé. Un seul constructeur sert la page, `cinoc run --recipe`,
  `cinoc hybrid` et `cinoc correct`.
- **Réglages déclarés** par chaque brique : la page génère son pli de réglages,
  `cinoc list engines <brique>` dit ce qu'elle consomme, produit et exige (un
  nom mal tapé reçoit le plus proche), et l'empreinte d'archive ne bouge que si
  la sortie peut bouger.
- **Archive et reprise** : `--resume-dir` archive chaque unité, `--offline`
  re-note l'archive sans rappeler aucun moteur ; le manifeste dit quel modèle a
  servi et garde la réponse native de chaque moteur distant.
- **Métriques** : familles caractère/mot (CER/WER/MER/cMER…), philologiques
  (diacritiques, MUFI, abréviations, numéraux romains, archaïsmes), conformité
  HIPE, calibration (ECE/MCE), NER, inter-moteurs (Wilcoxon/Friedman/Nemenyi,
  oracle, Jensen-Shannon), distribution par ligne, longitudinal (OLS + Pettitt),
  qualité d'image, données structurées, bilan de correction. Chaque métrique a
  sa fiche (référence nommée, unité, catégorie établie / adaptée /
  exploratoire) ; jiwer, dinglehopper et `roman` sont exécutés en CI comme
  références, le scorer HIPE-OCRepair fournit un golden.
- **Moteurs first-party** : Tesseract, Kraken, Pero, Calamari, Mistral OCR,
  Google Vision, Azure Document Intelligence (OCR/HTR) ; OpenAI, Anthropic,
  Mistral, Ollama et tout serveur compatible OpenAI (LLM/VLM). Jetons — de
  cache et de raisonnement compris — et coûts remontés ; tarifs datés ; les
  modèles se demandent au fournisseur.
- **Des confidences par mot pour les moteurs qui n'en produisent pas** :
  `text_confidences` note chaque mot avec un modèle de langue d'époque, ce qui
  allume la calibration pour l'OCR Mistral, un VLM ou un texte corrigé. Ce
  n'est pas une confiance moteur (sûreté des pixels) mais la plausibilité du
  mot ; le rapport compare les deux sur le seul critère commun — laquelle
  prédit le mieux une erreur.

**Segmentation et mise en page**

- Segmenteurs : PP-DocLayout (local), endpoint object-detection HuggingFace
  (distant), `doclayout_yolo` (extra `[yolo]`, installable par pip, poids tirés
  du Hub au premier run), et `tesseract_layout` (l'analyse de page de
  Tesseract). Chacun déclare ses classes et son corpus d'entraînement, visibles
  dans `cinoc list engines`.
- **Brancher un segmenteur sans écrire de Python** : `cli_layout` lance un outil
  externe (eynollah, `kraken segment`, dhSegment…) et relit le PAGE-XML ou
  l'ALTO qu'il écrit ; `ocrd` fabrique le workspace METS d'un processeur
  OCR-D, le lance et relit son PAGE-XML. Ligne de commande seulement : le
  lanceur web les refuse, instance privée comprise.
- **La chaîne NDNP de la Library of Congress, exécutable telle quelle** :
  `tesseract_layout`, `--psm` choisi selon la classe de région, et `gap_fill`,
  qui croise la lecture par régions avec une passe page entière pour que ce
  qu'un détecteur rate ne disparaisse pas du texte.
- **Export ALTO XML** (option *Exporter l'ALTO*, `--alto-dir`) : un ALTO par
  document, téléchargeable depuis le rapport (`alto.zip`), ré-importable dans
  eScriptorium ou Transkribus. Les ALTO et PAGE écrits par Cinoc passent les XSD
  officiels (ALTO 4.4, PAGE 2019), vérifié en test.

**Post-correction structurée** (`ALTO → ALTO`)

- Corrige un ALTO existant **dans** sa mise en page : chaque ligne garde son
  identifiant, donc l'appariement avant/après est connu au lieu d'être deviné.
  Producteurs : déterministe (règles, hors ligne), Ollama, Mistral sur le texte
  et `mistral_vision`, qui découpe chaque ligne dans l'image et la montre au
  modèle (lot scindé sous le plafond de huit images par appel). Le rapport
  montre ce qui a été changé **et ce que le correcteur a refusé de changer**
  (artefact `DECISIONS`), avec des métriques d'identité de ligne. CLI
  (`cinoc correct`, `--producer`) et web (recette `alto_corrige`).
- **Le scoreur de qualité D'AlemBERT** (extra `[qe]`) pour le routage sélectif :
  il note le besoin de correction d'une ligne sans punir l'orthographe d'époque
  (note prise sur une copie dé-glyphée, `ſ` → `s`, le document restant
  intact). AUC ligne 0,766, contre 0,500 pour l'heuristique de référence.

**Le rapport**

- **Rapport HTML autonome et interactif** : 4 onglets, graphes SVG serveur
  (zéro JS de calcul), tables triables, drill-in moteur/document, comparaison
  de 2 runs côté client, glossaire, **bilingue FR/EN** (`--lang en` sur
  `cinoc demo`, `cinoc run` et `cinoc compare`, la console restant en
  français ; nombres localisés à l'affichage, couches machine en point).
- **Saveurs** : fichier unique (images inline), dossier/ZIP (images séparées) ;
  le rapport prend tels quels des liens IIIF/HF (images chargées depuis
  HuggingFace), qu'aucune commande n'écrit encore.
- **Composition des chaînes** : les étapes réellement exécutées, la forme du
  graphe, le fan-out et les réglages effectifs de chaque brique, lus du
  manifeste. Deux chaînes de même nom disent ce qui les distingue à côté du nom
  (`ocr.lang=fra`), et `cinoc compare` avertit quand deux chaînes appariées par
  leur nom n'ont pas la même composition (`ocr.lang : fra -> eng`). Les noms ne
  changent pas : ils entrent dans la clé d'archive.
- Le rapport dit la convention de normalisation à côté de chaque chiffre, et
  une vue sans aucun chiffre dit pourquoi (pas de vérité, ou toutes ses unités
  en échec) au lieu d'un tableau vide.

**Corpus et application web**

- **Bibliothèque de corpus** : dépôt ZIP, imports IIIF (pleine résolution, par
  le service d'images) / Gallica / eScriptorium / HuggingFace, datasets curés
  Cinoc (import + découverte automatique par compte et tag), recherche
  HTR-United (qui renvoie vers la source et ne télécharge rien).
- **Interface web / Space** : composeur de recettes (SSE, journal par unité,
  arrêt qui coupe l'appel en vol), historique longitudinal, page de
  segmentation, mode public *fail-closed*.
- **Extensibilité** : un point d'extension unique (briques de pipeline) via
  entry-points `cinoc.modules`, découverte au lancement, fail-closed en mode
  public. `docs/PLUGINS.md` (en anglais) donne un module complet, le script
  qui l'emploie sans paquet et sa spec — tous trois exécutés par la suite ;
  `DeadlineExceeded` rejoint `cinoc.adapters.extension`.

**Ligne de commande**

- `demo`, `run`, `correct`, `corpus`, `list`, `hybrid`, `compare`, `history`,
  `serve` ; export JSON/CSV ; export JSONL conforme HIPE-OCRepair ; validation à
  blanc (`--check`, qui refuse aussi une langue Tesseract non installée) ;
  fourchette sur runs répétés (`--repeat`, `pipeline · vue · métrique`, écrite
  dans `<rapport>.variance.json`, le rapport HTML portant le dernier run).
  **Toute capacité de l'app web est accessible
  en ligne de commande**, et réciproquement — vérifié mécaniquement.
- Une ligne de progression par unité terminée (`[3/16] pipeline · document —
  fait`) sur la sortie d'erreur, pour `cinoc run`, `cinoc correct` et
  `cinoc hybrid`, puis un bilan ; une console cp1252 lit `->` pour `→`.
- **Noter des sorties d'un autre outil, sans moteur** : `precomputed` lit du
  texte, et le guide donne la spec qui note un ALTO (`alto_source` →
  `layout_to_text`), exécutée telle quelle par la suite et sur la roue
  installée.
- **Exemple exécutable** : `examples/config.yaml`, un run complet sans moteur
  ni réseau (ses images ne sont pas livrées, il le dit).

### Modifié

- **Tesseract lit chaque page une seule fois** : texte, confidences et ALTO
  sortaient de deux ou trois passes d'OCR ; le binaire est lancé une fois pour
  toutes les sorties — identiques à l'octet, 2 à 3 fois plus vite, en
  parallèle sans perdre d'unité. Les données de langue lues (`*.traineddata`,
  par leur empreinte) entrent au manifeste et dans la clé d'archive.
- **Mesuré : le mode rapide** fait 29 s contre 616 s sur trente unités ; une
  spec de six métriques produisait trente-quatre analyses (98 % du temps
  d'évaluation) et un rapport de plusieurs dizaines de mégaoctets.
- **Une seule définition du CER**, un seul alignement (celui du WER, de coût
  minimal) pour toutes les analyses qui disent *quelles* erreurs ; l'intervalle
  de confiance porte sur l'agrégat micro affiché ; le vote ne dépend plus du
  nom des sources ; l'ordre de lecture lit les colonnes ; la pente
  longitudinale porte son test.
- **Des noms qui ne promettent pas plus qu'ils ne mesurent** : `searchability`
  suit l'échelle `fuzziness: AUTO` de Lucene, `ner_f1_exact` (nouvelle) juge
  aussi la forme écrite des entités, et les numéraux romains ne prennent plus des mots
  pour des nombres.
- **Une inférence tracée** : les quatre fournisseurs LLM tournent sous les
  mêmes réglages, écrits au manifeste ; une page coupée par la limite de jetons
  se voit (`truncated`) ; des délais finis, une seule couche de nouvelles
  tentatives, chaque tentative facturable comptée ; un délai dépassé n'accuse
  plus le moteur ; Mistral OCR est noté sans sa syntaxe markdown, ses blocs
  arrivent en `LAYOUT` ; Azure et Google rendent leurs confidences.
- **Un arrêt coupe l'appel en vol**, chez Tesseract comme chez les sept moteurs
  distants ; une génération Ollama, désormais diffusée, s'interrompt en moins
  d'une seconde au lieu de deux minutes.
- `RunResult` est déterministe et ne cite aucun chemin local : images relatives
  au dossier de la spec, aucun chemin de la machine dans l'ALTO de Tesseract.
- **Le dépôt ZIP de la page accepte un gros corpus hors mode public** : 200 Mo,
  le plafond de `cinoc corpus import zip`, au lieu de 25 ; le mode public
  (`CINOC_PUBLIC_MODE=true`) garde 25 Mo — un Space qui ne le pose pas prend
  donc 200 Mo. La page dit le plafond qu'elle applique (elle annonçait 500 Mo),
  un refus le redit dans sa langue, et l'archive déposée n'est plus recopiée
  en mémoire.
- `cinoc correct` lit la vérité comme le dépôt ZIP : `<nom>.gt.txt` (ou
  `<nom>.txt`) pour le texte, `<nom>.gt.xml` pour la mise en page, et dit avant
  le run ce que mesureront les chiffres ; `--pipeline <p>` relit l'ALTO d'un
  run de Cinoc à côté de l'image.

### Corrigé

- **`cinoc correct` notait un ALTO contre lui-même** : sur un ALTO d'OCR, il
  affichait `F1 1,0 · CER 0,0` — la sortie comparée à sa propre entrée — et
  ignorait le `<nom>.gt.txt` posé à côté.
- **`cinoc serve` perdait ce qu'on faisait dans la page** au redémarrage
  (dossier de données temporaire, liste des corpus en mémoire seule) ; il dit
  désormais au démarrage quel dossier il utilise.
- **Un rapport de la CLI servi par `cinoc serve` retrouve ses images** : un
  rapport déposé se relit contre son dossier de dépôt (écrire `--json` à côté
  de la spec suffit) au lieu de retomber sur l'aperçu synthétique.
- `cinoc corpus import zip --dest corpus` (dossier relatif) écrivait des chemins
  absolus sous un message qui les disait relatifs.
- **Un bloc composé ne se projette plus en texte vide** : les lignes d'un ALTO
  `ComposedBlock` vivent dans ses enfants, et toute mise en page imbriquée — ce
  que Tesseract produit systématiquement — donnait un CER de 1,0 sans
  avertissement.
- **Les deux écritures de coordonnées ALTO sont lues** (`"x1,y1 x2,y2"` *et*
  `"x1 y1 x2 y2"`) : la seconde, celle de kraken entre autres, jetait en silence
  toute la géométrie.
- **Une reconnaissance par région peut rendre plusieurs lignes** : une page de
  trois blocs sortait avec trois lignes d'ALTO au lieu de vingt ; un
  reconnaisseur qui déclare `LAYOUT` voit ses lignes greffées, coordonnées
  retraduites.
- Les mots des PAGE-XML sont lus ; un import IIIF rapporte la vraie image (il
  écrivait parfois l'`info.json` du service).
- Une sortie pré-calculée corrigée sous la même image n'est plus resservie par
  la reprise.
- Le pont vers `saknussemm` pose `prev_line_id`/`next_line_id` : chaque ligne
  arrive au modèle avec ses voisines au lieu d'un contexte vide.
- Le catalogue des recettes ne peut plus ignorer une brique du registre (deux
  segmenteurs n'étaient proposés par aucun rôle) : un garde-fou confronte les
  deux listes.
- Ce que promettent les recettes de correction est atteignable : `ocr_puis_llm`
  et `alto_corrige` disent « en mode détaillé » pour leurs bilans, et la page
  reçoit la case *Mode détaillé* que `POST /api/runs` acceptait déjà
  (`detailed_analyses`). `cinoc hybrid --help` lit ses briques sur les rôles de
  sa recette (il oubliait `ollama`).
- Chaque test de significativité nomme la vue qu'il juge.
- La page : surtitre de la bibliothèque traduit (`Vitrine · bibliothèque`),
  apostrophe droite qui ne s'espace plus (page et rapport), vignettes entières
  au lieu de rognées, journal qui nomme chaque unité et traduit les états,
  champs de réglage avec `id`, `name` et `label for`.
- La recherche HTR-United du guide trouve (`"medieval"`), et un identifiant
  dérivé d'une URL n'emporte plus son fragment ni sa requête.
- `cinoc list engines` ne dit plus que `saknussemm` manque à PyPI
  (`pip install "cinoc[saknussemm]"` l'installe, 0.9.0) ; sans l'extra
  `[images]`, l'absence de Pillow se dit une fois au lieu d'une par vignette.

### Sécurité

- XML durci (`safe_parse_xml` : pas de DTD/DOCTYPE/entité externe ni réseau),
  validation systématique des chemins (anti-traversal), garde anti-SSRF sur les
  appels distants, plafonds d'upload, mode public sans secrets.
- Aucun secret dans un rapport ni dans un export de configuration : le
  manifeste remplace toute valeur de réglage secret par `<secret>`.
- Le serveur ne lit aucune image hors de la racine d'un rapport (`../` et
  absolus sortants perdent leur référence, vignette, fac-similé et `bundle.zip`
  compris).
- Le segmenteur distant se connecte à l'IP validée (plus de seconde
  résolution DNS) et n'envoie son authentification qu'à son origine ; l'hôte
  Ollama ne vient plus du client mais d'une liste blanche ; un téléchargement
  d'import n'écrit qu'une image.
- Un serveur compatible OpenAI ne reçoit la clé d'OpenAI que si on la nomme ;
  une URL d'endpoint portant identifiants, requête ou fragment est refusée.

### Retiré

- `pytesseract` et l'extra `[tesseract]` ; la lecture d'`OPENAI_BASE_URL` ;
  trois `ArtifactType` jamais produits ; les raccourcis de la normalisation —
  détail sous *Ruptures*.
