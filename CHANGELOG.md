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

### Ajouté

- **Brancher un processeur OCR-D.** La brique `ocrd` fabrique le workspace
  METS que ces outils attendent, lance le processeur nommé et relit son
  PAGE-XML — la centaine de processeurs OCR-D devient un paramètre de spec.
  Réservée à la ligne de commande, comme `cli_layout`.

- **Brancher un segmenteur sans écrire de Python.** La brique `cli_layout`
  lance un outil externe et relit le PAGE-XML ou l'ALTO qu'il écrit : eynollah,
  `kraken segment`, les processeurs OCR-D ou dhSegment deviennent **une ligne
  de spec** au lieu d'un adaptateur. L'interface n'est pas l'outil, c'est le
  format. Réservée à la ligne de commande — elle exécute une commande décrite
  par la spec, et le lanceur web la refuse toujours, instance privée comprise.
- **Les segmenteurs déclarent ce qu'ils savent détecter** — leurs classes et le
  corpus sur lequel ils ont été entraînés, visible dans `cinoc list engines`.
  Une table « classe → réglage » qui ne parle pas la langue de son segmenteur
  est désormais refusée avant le run, au lieu d'être ignorée en silence.

- **Le rapport montre ce qu'il y a dans chaque chaîne.** Section « Composition
  des chaînes » : les étapes réellement exécutées, la forme du graphe, le
  fan-out et les réglages effectifs de chaque brique — lus du manifeste. Un nom
  de pipeline porte une intention, pas un contenu.

### Corrigé

- **Un chemin Windows dans une commande `cli_layout` est refusé, plus mangé.**
  Le découpage est POSIX sur les trois systèmes — une spec est une donnée
  reproductible, elle doit se lire partout de la même façon — et l'antislash y
  est un caractère d'échappement : `C:\Outils\eynollah.exe` devenait
  `C:Outilseynollah.exe` *en silence*, et l'outil paraissait introuvable sans
  raison. La commande qui en contient un est maintenant refusée au plan, avec
  la forme à écrire (barres obliques, guillemets pour une espace).

- **Les deux écritures de coordonnées ALTO sont lues.** Le schéma ALTO v4 admet
  `"x1,y1 x2,y2"` *et* `"x1 y1 x2 y2"` ; cinoc refusait la seconde, et jetait
  donc en silence toute la géométrie des outils qui l'emploient — kraken entre
  autres.

- **Une reconnaissance par région peut rendre plusieurs lignes.** Le fan-out ne
  lisait que du texte plat : une page de trois blocs sortait avec trois lignes
  d'ALTO au lieu de vingt, structurellement fausse et illisible par un outil de
  relecture — sans qu'aucune métrique de texte puisse le voir, le contenu étant
  juste. Un reconnaisseur qui déclare `LAYOUT` voit désormais ses lignes
  greffées, coordonnées retraduites et identifiants préfixés.
- **Le catalogue des recettes ne peut plus ignorer une brique du registre.**
  Deux segmenteurs — les deux seuls exécutables sans dépendance lourde —
  n'étaient proposés par aucun rôle. Un garde-fou confronte désormais les deux
  listes dans les deux sens.

- **La post-correction structurée s'identifie par sa fonction, pas par sa
  bibliothèque.** L'identifiant de capacité devient `structured_correction`
  (le détail continue d'indiquer quoi installer), le planificateur prend le
  correcteur en paramètre, et les trois clients écrits pour `saknussemm`
  quittent `adapters/llm/` — où leurs noms génériques induisaient en erreur —
  pour `adapters/correction/`. Un test d'architecture empêche désormais la
  confusion de revenir.

- **Les lignes envoyées au correcteur structuré connaissent leurs voisines.**
  Le pont vers `saknussemm` ne posait ni `prev_line_id` ni `next_line_id` :
  le contexte (`prev_text`/`next_text`) était donc toujours vide et chaque
  ligne arrivait seule au modèle.

- **Des confidences par mot pour les moteurs qui n'en produisent pas.**
  `text_confidences` note chaque mot avec un modèle de langue d'époque, ce qui
  allume la section calibration (ECE, MCE, courbe de fiabilité) pour l'OCR
  Mistral, un VLM en transcription directe ou un texte corrigé — jusqu'ici
  vides faute de donnée. Ce n'est pas la même grandeur qu'une confiance
  moteur : celle-ci dit la sûreté des pixels, celle-là la plausibilité du mot.
  Le rapport peut désormais les comparer sur le seul critère commun — laquelle
  prédit le mieux une erreur.


- **La chaîne NDNP de la Library of Congress, exécutable telle quelle.** Trois
  briques manquaient : `tesseract_layout` (l'analyse de page de Tesseract
  lui-même — le segmenteur que NDNP utilise **par défaut**, le détecteur
  neuronal n'étant qu'une option), le choix du `--psm` **selon la classe de
  région**, et `gap_fill`, qui croise la lecture par régions avec une passe
  page entière pour que ce qu'un détecteur rate ne disparaisse pas du texte.

### Corrigé

- **Un bloc composé ne se projette plus en texte vide.** Les lignes d'un ALTO
  `ComposedBlock` vivent dans ses enfants ; la projection layout → texte ne
  lisait que le premier rang, donc toute mise en page imbriquée — ce que
  Tesseract produit systématiquement — donnait un texte vide et un CER de 1,0,
  sans erreur ni avertissement.

- **Deux pipelines produisant de l'ALTO n'écrasent plus le même fichier.** Le
  nom de sortie ne portait que l'identifiant de document ; comparer deux chaînes
  qui émettent toutes deux de l'ALTO — ce qu'un banc fait par définition — n'en
  laissait qu'une, sans avertissement. Le nom porte désormais le pipeline.


- **Un segmenteur de mise en page installable par pip** : `doclayout_yolo`
  (extra `[yolo]`). Les deux segmenteurs existants exigeaient PaddleX ou un
  endpoint distant, donc la famille de pipelines hybrides n'était exécutable
  sur aucune machine nue. Les poids sont tirés du Hub au premier run.
- **Le scoreur de qualité D'AlemBERT** (extra `[qe]`) pour le routage sélectif
  de la post-correction : il note le besoin de correction d'une ligne sans
  punir l'orthographe d'époque — la note est prise sur une copie dé-glyphée
  (`ſ` → `s`) pendant que le document reste intact. AUC ligne 0,766, contre
  0,500 (le hasard) pour l'heuristique de référence.


- **Post-correction structurée voyant le scan**, pilotée par Mistral.
  `saknussemm` livrait une chaîne vision complète (découpe par ligne, gardes
  desserrées, plafond d'images) qu'aucun client de ce dépôt ne pouvait
  atteindre : deux producteurs de plus la branchent — `mistral` (sur le texte)
  et `mistral_vision` (qui découpe chaque ligne dans l'image et la montre au
  modèle). Le plafond de huit images par appel est déclaré au moteur, donc le
  lot est scindé avant la requête plutôt que refusé après. Disponibles depuis la
  CLI (`cinoc correct --producer`) comme depuis le web, sans liste recopiée.
- **Moteur déterministe** : pipelines OCR / HTR / VLM / OCR→LLM, exécutés via un
  orchestrateur unique (CLI **et** web), `RunManifest` reproductible, annulation
  et timeout coopératifs.
- **Métriques** : familles caractère/mot (CER/WER/MER/cMER…), philologiques
  (diacritiques, MUFI, abréviations, numéraux romains, archaïsmes), conformité
  HIPE, calibration (ECE/MCE), NER, inter-moteurs (Wilcoxon/Friedman/Nemenyi,
  oracle, Jensen-Shannon), distribution par ligne, longitudinal (OLS + Pettitt),
  qualité d'image, données structurées, bilan de correction.
- **Moteurs first-party** : Tesseract, Kraken, Pero, Calamari, Mistral OCR,
  Google Vision, Azure Document Intelligence (OCR/HTR) ; OpenAI, Anthropic,
  Mistral, Ollama (LLM/VLM). Jetons et coûts remontés ; tarifs datés.
- **Segmentation** : segmenteur local PP-DocLayout **et** segmenteur distant
  (endpoint object-detection HuggingFace, interchangeable sans réinstallation).
- **Rapport HTML autonome et interactif** : 4 onglets, graphes SVG serveur
  (zéro JS de calcul), tables triables, drill-in moteur/document, comparaison de
  2 runs côté client, glossaire, **bilingue FR/EN** (nombres localisés à
  l'affichage, couches machine en point).
- **Saveurs de rapport** : fichier unique (images inline), dossier/ZIP (images
  séparées), références IIIF/HF (images chargées depuis HuggingFace).
- **Export ALTO XML** (Tesseract) : option *Exporter l'ALTO* au lanceur →
  un ALTO par document (géométrie + texte), téléchargeable depuis le rapport
  (`alto.zip`) — ré-importable dans eScriptorium ou Transkribus.
- **Bibliothèque de corpus** : upload ZIP, imports IIIF / Gallica /
  eScriptorium / HuggingFace, datasets curés Cinoc (import + découverte
  automatique par compte + tag).
- **Interface web / Space** : lanceur de benchmark (SSE), historique
  longitudinal, page de segmentation, mode public *fail-closed*.
- **Extensibilité** : point d'extension unique (briques de pipeline) via
  entry-points `cinoc.modules`, découverte runtime, fail-closed en mode public.
- **Post-correction structurée** (`ALTO → ALTO`) : corrige un ALTO existant
  **dans** sa mise en page — chaque ligne garde son identifiant, donc
  l'appariement avant/après est *connu* au lieu d'être deviné. Producteurs
  déterministe (règles, hors ligne) ou LLM local (Ollama). Le rapport montre
  ce qui a été changé **et ce que le correcteur a refusé de changer**
  (artefact `DECISIONS`), avec des métriques d'identité de ligne appariées
  par identifiant. Disponible en CLI (`cinoc correct`) **et** au lanceur web.
- **CLI** : `demo`, `run`, `correct`, `corpus`, `list`, `hybrid`, `compare`,
  `history`, `serve` ; export JSON/CSV ; export JSONL conforme
  HIPE-OCRepair ; validation à blanc (`--check`) et fourchette sur runs
  répétés (`--repeat`). **Toute capacité de l'app web est accessible en
  ligne de commande**, et réciproquement — vérifié mécaniquement.
- **Exemple exécutable** : `examples/config.yaml`, un run complet qui tourne
  sans moteur ni réseau.

### Sécurité

- XML durci (`safe_parse_xml` : pas de DTD/DOCTYPE/entité externe ni réseau),
  validation systématique des chemins (anti-traversal), garde anti-SSRF sur les
  appels distants, plafonds d'upload, mode public sans secrets.
