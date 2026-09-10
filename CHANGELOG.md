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
