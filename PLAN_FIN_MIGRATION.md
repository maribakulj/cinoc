# PLAN_FIN_MIGRATION.md — Route unique vers `1.0.0` et gel de Picarones

> Plan **prospectif et linéaire**. Cinq étapes, dans l'ordre d'exécution. On fait
> 1, puis 2, puis 3, etc. Rien en parallèle, rien « au cas où », rien laissé pour
> après. Quand la 1.0 sort, **tout le périmètre gardé est dedans** et Picarones
> peut être gelé sans aucune perte.
>
> **Autorité de statut = roll-up de [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md).** Ce
> fichier ne déclare aucun « fait » : toutes les étapes ci-dessous sont
> **planifiées**. Chaque livraison réconcilie le roll-up dans le même commit.

---

## Où on en est (juin 2026)

Cinoc est déjà très avancé. **Déjà livré** : tout le moteur déterministe
(domain → formats → evaluation → pipeline), le Space web (coquille, lanceur
SSE, persistance, sécurité publique, importeurs IIIF/Gallica/eScriptorium/
HuggingFace/HTR-United, historique SQLite, page segmentation), les moteurs
Tesseract / Kraken / Mistral OCR / OpenAI / Anthropic / Mistral-VLM / Ollama, le
mode VLM zero-shot, la segmentation (CanonicalLayout + fan-out + PP-DocLayout),
et les métriques CER/WER/MER, diacritiques, MUFI, confusion, taxonomie,
diagnostics, **économie mesurée** (jetons réels + temps réel, pas d'estimation),
calibration, statistiques (Nemenyi + bootstrap), synthèse factuelle.

**Ce qui manque pour la 1.0**, et que les cinq étapes ci-dessous couvrent
**entièrement** :

1. ~~Le Space public **n'exécute aucun moteur**~~ → **✅ résolu (D-075)** : image
   moteur Tesseract + mode public fail-closed ; un visiteur fait un vrai OCR sans
   clé. *(Reste différé : segmenteur PP-DocLayout sur le Space, T2.5.)*
2. ~~**Parité moteurs** Google / Azure / Pero / Calamari~~ → **✅ (D-076→D-080)**.
3. **Parité d'interface** (rapport interactif, galerie, champs de formulaire).
4. Les **métriques restantes** de Picarones jugées utiles (voir §« Verdict
   métrique » plus bas).
5. La **release 1.0** et le **gel** de Picarones.

---

## Révision juin 2026 — scope v1 élargi : 6 phases (parité **+** plateforme)

> **Décision produit (D-109)** : la v1 ne se contente pas de la **parité
> Picarones** ; elle inclut le **rapport interactif complet** (U1→U4 livrés),
> **les images + strates**, **un dataset de référence curé** (preuve d'extensibilité,
> **un seul** suffit) et **les saveurs** (fichier/dossier/IIIF/servie). La v1 passe
> de « portage propre » à « plateforme de benchmark complète ». Le **dataset curé
> est la clé de voûte** : il *produit* la donnée que strates, images-à-l'échelle,
> IIIF et les **familles de métriques riches** (layout/NER/image) consomment.

**Correction d'un classement erroné** : les images **ne sont pas** « bloquées sur
producteur » (contrairement à ce que j'avais dit). `DocumentRef.image_uri` existe,
l'upload de corpus garde les images, le runner a le `DocumentRef` en main → **T3/T4
sont constructibles** (il manque le câblage de la *référence* dans le résultat).
Seules **les strates** manquaient d'un champ ; c'est l'objet de la Phase 0.

| Phase | Contenu | Dépend de | Parité ou neuf |
|---|---|---|---|
| **P0 — Enveloppe données** (socle, petit) | `DocumentRef.metadata` optionnel (→ strate) + **référence image** propagée dans `RunDocumentResult` (jamais les octets). domain/evaluation/pipeline. | — | parité (forme) |
| **P1 — Rapport sur données locales** | **T3** vraies vignettes · **T4** fac-similé medium + diff pleine page borné · **U5′** strates (forme **optionnelle**, rendues si présentes) + démo élargie multi-genre · micro (nombres FR, saveur **dossier**). | P0 | **parité Picarones** |
| **P2 — Métriques** (ex-étape 4) | 4a-4c (texte/philologie) · 4d (robustesse/image — **besoin réfs image P0**) · 4e (inter-moteurs/lignes) · 4f (NER) + métriques layout/région. *Parallélisable après P0.* | P0 | parité |
| **P3 — Dataset de référence curé** (le neuf, **UN seul**) | spec de standardisation (alignée P0) · **un** corpus libre de droits, GT riche (texte + layout + entités) + métadonnée strate + **IIIF statique** (manifestes + vignettes) · importeur (SHA → `RunManifest`). **Preuve que la chaîne tient et qu'elle est extensible** ; d'autres datasets = incrémental post-v1. | P0 ; conception ⇄ P2 (schéma GT) | **neuf** |
| **P4 — Saveurs & échelle** | saveur **réfs IIIF** (URLs du dataset P3) · saveur **servie** (app web : galerie paginée, images à la demande, échelle 5000). *(dossier déjà en P1.)* | P1, P3 | partiel neuf |
| **P5 — Release 1.0 + gel Picarones** | checklist · tag · README/CHANGELOG · gel. | tout | — |

**Intégration métriques ⇄ dataset** (le point clé) : P2 et P3 se renforcent. Le
dataset **donne aux métriques leur vérité-terrain** (layout→région/structure ;
entités→NER ; multi-genres→**par strate** ; images→qualité/robustesse) ; sans lui,
la moitié des familles de l'étape 4 ne se testent que sur fixtures minces. **Point
de couplage = le schéma de GT de la spec P3**, à concevoir en connaissant ce que
les familles consomment → **l'analyse de l'étape 4 nourrit la spec du dataset**.
En pratique : métriques développées sur fixtures (P2), puis **exercées sur la vraie
donnée diverse** quand P3 arrive. Parallélisme propre.

**Ordre de build** : **P0 → P1** d'abord (rapport complet sur corpus locaux,
valeur visible vite), **P2 (métriques)** en parallèle après P0, **P3 (dataset)**
chantier de fond, **P4** une fois P1+P3 prêts, **P5** la fin.

**Le long pôle** = la curation/les droits du **seul** dataset P3 (diligence
humaine, pas du code) — réduit à « choisir **un** corpus libre de droits et le
faire à fond ».

**Séquencement i18n du rapport (D-114)** : le **contenu des sections** est
aujourd'hui en **FR en dur** (le chrome — onglets/héros/glossaire — est déjà
bilingue). L'i18n **complète** du rapport (sections → bilingue FR/EN) est une
**passe finale, APRÈS P2** : on n'internationalise pas une cible mobile — P2
ajoute ~6 sections de métriques, donc i18n d'office maintenant = soit surcoût
sur chaque tranche métrique, soit anglais « moitié traduit » qui régresse. Une
**seule passe**, sur la surface **complète et stable**, un catalogue cohérent.
Les **nombres FR** (`1,4 %`, espace fine — formatage de la *langue par défaut*,
indépendant de l'anglais) restent une **micro de P1**, faisable quand on veut.

---


## Décisions déjà actées

| Décision | Choix |
|---|---|
| **Abandons définitifs** | 8 familles jetées (liste §« Abandons »), validées |
| **NER** | extra optionnel `[ner]`, jamais de silence si absent |
| **Économie** | coûts mesurés réels (déjà l'état du code) — pas de CO₂ |
| **Parité moteurs** | Google + Azure **first-party** (extras `[google]`/`[azure]`) ; Pero + Calamari **first-party in-tree** (comme Kraken — décision révisée D-078 ; le seam plugin reste pour les vrais tiers) |
| **Toutes les métriques gardées** | **obligatoires avant 1.0** (le gel ferme la fenêtre de portage — rien en backlog) |
| **Fin** | release `1.0.0` puis gel immédiat de Picarones |

**Méthode de fidélité** : Picarones n'est **jamais** l'oracle. Toute valeur
attendue d'un test vient d'une référence externe (jiwer, formule publiée,
q-table, cassette HTTP réelle) ou d'un cas calculé à la main. `make ci` complet
avant chaque push.

---

# LES 5 ÉTAPES, DANS L'ORDRE

## Étape 1 — Le Space exécute un vrai OCR gratuit ✅ (D-075)

**C'est le manque n°1 et le point de départ.** Aujourd'hui le Space est une
vitrine qui ne fait tourner aucun moteur. Cible : un visiteur uploade un corpus,
lance Tesseract, reçoit un vrai rapport CER — **sans clé, sans installation**.

| | |
|---|---|
| **Fichiers touchés** | `deploy/Dockerfile.engine` (**nouveau** — image qui contient un moteur, ≠ image vitrine actuelle) : `apt-get install tesseract-ocr tesseract-ocr-fra tesseract-ocr-lat tesseract-ocr-eng`, `pip install .[serve,tesseract]`, `ENV TESSDATA_PREFIX=…`, **`ENV OMP_THREAD_LIMIT=1`**, **smoke-test au build** (`tesseract --version` + `--list-langs | grep -qx fra` + OCR d'une image générée), `USER` non-root · `deploy/requirements.txt` (+`pytesseract`) · `.github/workflows/deploy-space.yml` (build image moteur + **smoke OCR réel** post-déploiement) · `cinoc/interfaces/web/app.py` + `security/` (mode public : exécute **uniquement** le socle first-party gratuit ; plugins et cloud restent gated) · `cinoc/app/engines.py` (Tesseract disponible sur le Space) |
| **Risques** | Cold-start free-tier 2 vCPU → `OMP_THREAD_LIMIT=1` **obligatoire** (sans lui, deadlock OpenMP — incident documenté côté Picarones). Abus public → rate-limit, caps upload, sémaphore jobs, timeout coopératif (déjà en place). Déterminisme → version du binaire Tesseract épinglée et tracée dans `RunManifest`. |
| **Décision incluse (segmenteur)** | Une fois l'image Tesseract déployée, **mesurer le cold-start**, puis trancher pour PP-DocLayout sur le Space : (a) le baker si le free-tier tient, (b) rester en dégradé gracieux (« segmenteur indisponible », il tourne en local), ou (c) monter de tier (budget — ta décision). Aucune des trois ne bloque la 1.0 : le dégradé gracieux est déjà livré. |
| **Fait quand** | Le build échoue si Tesseract/`fra` manque ou si l'OCR dépasse le timeout. Un visiteur fait un vrai run Tesseract sur le Space public sans clé. En mode public, les plugins et le cloud sont gated. `make ci` vert, `/health` < 50 ms. |

---

## Étape 2 — Parité moteurs ✅ (D-076→D-080)

Compléter les moteurs côté utilisateur, selon l'arbitrage acté. **Un seul contrat
`Protocol`**, chaque moteur extra-gated, fail-closed sans clé (listé mais
indisponible, jamais de crash). C'est la couche adapters dans son rôle légitime —
**pas** le double contrat qui a plombé Picarones.

| Sous-étape | Contenu | Fichiers touchés |
|---|---|---|
| **2a — Google Vision** | adapter cloud first-party | `cinoc/adapters/ocr/google_vision.py` (**nouveau**), extra `[google]` dans `pyproject.toml`, entrée `cinoc/app/engines.py`, `tests/adapters/ocr/test_google_vision.py` (cassette + valeurs main) |
| **2b — Azure Document Intelligence** | adapter cloud first-party | `cinoc/adapters/ocr/azure_di.py` (**nouveau**), extra `[azure]`, entrée factory, `tests/adapters/ocr/test_azure_di.py` |
| **2c — Pero + Calamari** | **first-party in-tree** (révisé D-078, comme Kraken) | `cinoc/adapters/ocr/{pero,calamari}.py` (**nouveaux**), extras `[pero]`/`[calamari]`, builders + sondes `cinoc/app/engines.py`, `_OCR_ENGINES`, tests mockés ; `docs/PLUGINS.md` documente le seam entry-points `cinoc.modules` pour les **vrais** tiers (déjà prouvé D-034) |
| **2d — Vérifs** | zero-shot déjà livré → test bout-en-bout + doc ; tous les adapters cloud remontent bien `tokens_in/out` (alimente l'économie) | `tests/pipeline/` (spec zero_shot 1 étage IMAGE→texte), `tests/adapters/llm/` (jetons non-`None` sur cassette) |
| **2e — Prompts curés par période** ✅ (D-080) | porter les **16 prompts** Picarones (correction + zero-shot) calibrés par type : médiéval FR/EN, imprimé ancien, presse XIXe FR/EN/DE/européenne. **Donnée curée**, pas de la surface exécutable (comme les profils de normalisation) + **prompt libre dans l'UI** (demande utilisateur — textarea déjà câblé) | `cinoc/prompts/*.txt` + loader (`available_prompts`/`load_prompt`), `Competitor.prompt_name` + résolution `app/run_planning` (mutuellement exclusif avec le prompt libre prioritaire), `<select>` curé au formulaire web + `benchmark.js`, `package-data`, `tests/` (chargement + sélection + résolution) |

| | |
|---|---|
| **Risques** | Croissance de surface → mitigée : un `Protocol`, un test par moteur, extra-gated, fail-closed. Ne **jamais** réintroduire de double contrat interne. Prompts = données versionnées (déterminisme : fichier tracé dans `RunManifest`). |
| **Fait quand** | Google/Azure listés ; avec clé → OCR réel sur cassette ; sans clé → indisponible propre. Pero/Calamari listés in-tree (extras), indisponibles sans leur lib, non déployés au Space. Zero-shot testé. Les 16 prompts sélectionnables **+ prompt libre éditable dans l'UI** (D-080). `make ci` vert. **→ Étape 2 COMPLÈTE (2a–2e).** |

---

## Étape 3 — Parité de l'interface et du rapport ✅ (3a→3e livrés)

Le web et le rapport portent déjà beaucoup (benchmark, SSE `Last-Event-ID`,
library, history, segmentation, CSRF, rate-limit, i18n FR/EN). Cette étape comble
**le delta** avec Picarones. Tout reste **déterministe, sans LLM** (invariant
anti-hallucination) ; le JS client est en lecture seule, zéro appel réseau.

| Sous-étape | Contenu | Fichiers touchés |
|---|---|---|
| **3a — Rapport interactif** | **compare 2 runs client-side ✅ (D-081)** (`FileReader`+`JSON.parse`, plafond 50 Mo, bandeau sticky, CSP `/reports/` par hash) · **badges moteur A→E ✅ (D-082)** · **deeplinks + sommaire + ARIA ✅ (D-083)** · **navigation clavier + palette daltonien ✅ (D-084)** ; *reste hors-3a* : **formatage des nombres FR/EN** = en réalité une **i18n complète du rapport** (texte FR uniquement aujourd'hui) → à planifier à part (cf. 3e), pas une sous-tranche 3a | `cinoc/reports/` (`compare.js`+`report.js`/`embedded.py` + `engine_badges.py` + `renderer.py`) ; la voie server-side `reports/compare.py` reste pour `cinoc compare` |
| **3b — Galerie & drill-in** ✅ | **drill-in diff caractère surligné GT↔hypothèse ✅ (D-085)** · **galerie de documents synthétique ✅ (D-086)** (cartes : aperçu CSS sur la charte + CER par moteur/badges A→E, comme le défaut Picarones — zéro image, autonome) ; **fac-similés réels = opt-in séparé** (canal images base64, décision ultérieure) | `cinoc/reports/text_diff.py` + `sections/gallery.py` + section `diagnostics` |
| **3c — Champs de formulaire** | parité CLI/web : **champ `model` des moteurs OCR ✅ (D-087)** · **`/api/models/{provider}` + suggestions vision ✅ (D-088)** · **preview de normalisation (config YAML custom sans persistance) ✅ (D-089)** · **`char_exclude` ✅ (D-090)** · **sélecteur profil métrique ✅ (D-144)** (`standard`/`essentiel`/`philologie` → colonnes de classement de la vue `text` ; `standard` byte-identique) · **config save/load JSON ✅ (D-145)** (`POST /api/runs/config` valide un `LaunchRequest` ; export = blob client, import = validé serveur avant repeuplement) ; *reste* : toggle expose-ALTO | `cinoc/interfaces/web/routers/` + `app/{models,normalization_preview,run_planning}.py` + templates ; la construction de spec reste en `app/run_planning` (garde-fou `interfaces` mince) |
| **3d — Observabilité & a11y ✅** | **`/metrics` Prometheus opt-in ✅ (D-091)** · **polish a11y ✅ (D-092)** : lien d'évitement clavier + `progressbar` ARIA ; sélecteur de langue, feedback dropzone (`.is-dragover`), désactivation bouton + barre de progression + `aria-live` **déjà présents** (audit) | `cinoc/interfaces/web/metrics.py` + `create_app` ; `base.html`/`benchmark.html`/`benchmark.js`/`shell.css`/`i18n.py` |
| **3e — Glossaire FR/EN ✅ (D-093)** | glossaire pédagogique porté : 15 entrées FR/EN (métriques **réellement calculées**), `GlossarySection` en disclosure natif `<details>` (zéro JS), lang via `SectionContext`/`/reports/{name}?lang=` | `cinoc/reports/glossary/{fr,en}.yaml` + `glossary/__init__` (loader) + `sections/glossary.py` ; `SectionContext.lang`, `render_document(lang=)`, router `?lang=` ; `package-data`, CSS au design, `tests/` |

| | |
|---|---|
| **Risques** | Garder `interfaces` mince. `/metrics` strictement opt-in. Validation chemins/SSRF maintenue. Golden du rapport reste octet-stable. Glossaire = données i18n (pas de prose LLM). |
| **Fait quand** | Compare hors-ligne, galerie lazy, drill-in diff, deeplinks clavier, nombres localisés, config round-trip, preview normalisation, `/metrics` opt-in, glossaire FR/EN affiché — tous testés. `make ci` vert. |

---

## Étape 4 — Toutes les métriques restantes (l'avant-dernière, comme demandé)

On ajoute **en bloc final** les familles de métriques jugées utiles et encore
absentes de Cinoc. **Aucune n'est optionnelle** : le gel de Picarones ferme la
fenêtre de portage, donc tout ce qu'on garde doit être ici. Chaque famille est
livrée **entièrement** : la métrique + son payload dans `RunResult` + **sa
section de rapport** (le consommateur réel) + ses tests à valeurs calculées main.
Les familles marquées 🔶 sont **réparées** au portage, pas copiées avec leurs
défauts.

| Sous-étape | Familles | Fichiers principaux | Note |
|---|---|---|---|
| **4g — Conformité HIPE & bilan de correction** (inséré 2026-06-11, plan A — [`SPEC_HIPE.md`](SPEC_HIPE.md), réconcilié [`ANALYSE_ETAPE_4.md`](cinoc/evaluation/ANALYSE_ETAPE_4.md)) | **4g.1 conformité ✅ (D-115)** : profils `hipe`/`heritage` · `cmer` · payload+section `conformity` · export JSONL `--hipe-jsonl` · golden vendoré skip-gaté · **4g.2 bilan de correction ✅ (D-116)** : triplet/pref/pcis · CCR/change/length · **absorbe `over_normalization` (4c) et `error_absorption` (4e)** · éditions consécutives · R-1.8 dans les métriques · procédure `hallucination` (machinerie livrée — exécution sur runs réels avant 1.0) | `formats/text/normalization.py`, `evaluation/{metrics/conformity,conformity}.py`, `reports/sections/conformity.py`, `app/hipe_export.py` | 🔶 ordre interne de P2 révisé : 4g.1→4g.2→4a→4b→4c réduit→4e réduit→4f→4d ; `readability` (4a) **abandonné** (arbitré 2026-06-11) |
| **4a — Données structurées ✅ (D-117)** | numseq_strict/numseq_value (années/foliation/montants/régnal — **roman → 4b**, R1) ; ~~readability/Flesch~~ **abandonné, acté D-117** (couvert par 4g.2 + hcpr/air) | `evaluation/metrics/structured_data.py`, payload + collecteur, section `reports/sections/structured_data.py` | ✅ livré : 2 lentilles strict/valeur, adaptatif (`None` sans signal), vue défaut enrichie |
| **4b — Philologie étendue ✅ TERMINÉE** (D-118→D-122) | abbreviations · early_modern (positionnel) · modern_archives (archival) · roman (5 statuts) · **`air`/`hcpr`** (archaïsmes bidirectionnels, scalaires) | `evaluation/{markers,archives,roman,archaic,preservation}.py`, `metrics/archaic.py`, section `philology` + colonnes `by_engine` | ✅ dé-fragmenté : roman compté **une seule fois** (R1) ; `air`/`hcpr` = scalaires (`air` défaut, `hcpr` opt-in, anti-colonne-jumelle de `mufi_err`) ; moteur de préservation factorisé (parité bit-à-bit) |
| **4c — Fidélité textuelle (réduit) ✅ (D-123)** | rare_tokens + lexical_modernization (collecteur corpus) ; `over_normalization`→4g.2, `equivalence_profile`/`searchability_hooks` **abandonnés** | `evaluation/textual_fidelity.py`, section `reports/sections/textual_fidelity.py` | ✅ câblage homogène (R6 — un seul canal collecteur, 0 calcul en couche rapport) ; rareté corpus-wide résolue à `build` ; payload-only |
| **4d — qualité image ✅ / robustesse abandonnée** (scindée 4d.1/4d.2) | **4d.1 qualité image ✅ (D-128)** : netteté/bruit/contraste/inclinaison mesurés (numpy+PIL) → **16ᵉ payload `image_quality`** scope corpus par document · section onglet documents · constantes = conventions éditoriales (R8) · pas de mock (R9, démo octet-stable) · **`image_predictive` abandonné acté** (C3) · **4d.2 robustesse ABANDONNÉE (D-129)** : renversement du verdict GARDER (dégradations synthétiques de validité douteuse, coût re-OCR disproportionné, résilience réelle → strates P3) ; `robustness`/`robustness_projection` **non portés** | `evaluation/image_quality.py` ✅, section `reports/sections/image_quality.py` ✅ ; `robustness.py` **non créé** (abandonné) | ✅ 4d.1 ; ❌ 4d.2 abandonnée (D-129) → **P2 TERMINÉE** |
| **4e — Inter-moteurs & lignes ✅ TERMINÉE** (D-124→D-126, scindée 4e.1/4e.2/4e.3 — `ANALYSE_ETAPE_4` §Cible 4e) | **4e.1 inter_engine ✅ (D-124)** : divergence Jensen-Shannon (sur comptages taxonomy, zéro recalcul) + oracle/complémentarité (R10 : GT vide → `None`) · `incremental_comparison` **abandonné, acté** (C2) ; ~~error_absorption~~ **absorbé en 4g.2** (D-116) · **4e.2 lignes ✅ (D-125)** : alignement **F15** porté tel quel, percentiles/Gini, seuils catastrophiques **inclusifs** (répare le seuil 1.00 mort), heatmap positionnelle, applicabilité par sonde `\n` (vue à plat → absent) · **4e.3 longitudinal ✅ (D-126)** : OLS porté tel quel (parité scipy en test) + **vrai test de rupture Pettitt 1979** (R11 — significatif seulement si p ≤ 0.05, fini le max-diff) ; pas un payload (multi-runs) → `app/history.series_insight` → cartes tendance `/history` ; CLI `history` non créée (CLAUDE §8.4) | `evaluation/{inter_engine,lines,longitudinal}.py` ✅ (13ᵉ+14ᵉ payloads + fonctions pures multi-runs, section `cross_engine` étendue + section `lines` + cartes `/history`) | ✅ alignement ligne-à-ligne fiabilisé (F15) ; oracle gap = **borne documentée** ; **vrai détecteur de rupture** (Pettitt, p-value — plus jamais une rupture « toujours trouvée ») |
| **4f — NER ✅ (D-127)** | F1 par catégorie, entités manquées/hallucinées, appariement IoU 0.5, **R14** (spans hypothèse reprojetés en coords GT) | `adapters/ner/spacy_extractor.py` (lazy, fail-closed), `evaluation/{ner,metrics/ner}.py`, payload+section `ner`, loader ENTITIES, builder registre, extra `[ner]` | ✅ **anti-silence** : adapter lève (jamais `[]` muet) ; R14 (le F1 ne mesure plus le profil ins/del de l'OCR) ; *différé surface* : étape NER en pipeline vivant + formulaire web + 422 au plan |

| | |
|---|---|
| **Risques** | Ne pas réimporter les défauts 🔶 (fragmentation, silences, alignements naïfs). spaCy strictement en extra. Déterminisme : versions de modèle dans `RunManifest`, seeds fixes. |
| **Fait quand** | Chaque famille a sa section + ses tests à valeurs-main/référence externe ; câblée dans un profil ; **plus aucune famille gardée hors Cinoc**. `make ci` vert, couverture ≥ 85 %. |

---

## Étape 5 — Release `1.0.0` puis gel de Picarones

| Sous-étape | Contenu |
|---|---|
| **5a — Release 1.0.0** | Vérifier la checklist ci-dessous · tag `v1.0.0` · `README` (positionnement 1.0, matrice moteurs/extras, mode Space) · `CHANGELOG` minimal · `pricing.json` daté · roll-up `MIGRATION_PLAN.md` réconcilié |
| **5b — Gel de Picarones** | Bannière `README` Picarones → « projet figé, successeur Cinoc » · dépôt GitHub archivé en lecture seule · note de dépréciation sur le Space HF Picarones (lien vers le Space Cinoc) · plus aucun commit Picarones |

### Checklist « 1.0 prête »

> **État au 2026-09-09 (D-223)** : **Étapes 1→4 ✅** (Space-OCR, parité moteurs,
> interface/rapport, P2 métriques) **+ i18n finale ✅** (D-136→D-142) **+ P0→P3 ✅**
> (enveloppe données, rapport local, métriques, dataset curé publié) **+ 3c
> expose-ALTO ✅** (D-219). **Reste pour la 1.0** : **P5** (release + gel) ; **P4**
> réduit à la *saveur servie*, que ce plan déclare lui-même pouvoir suivre la 1.0.
> **Aucun tag `git` n'existe** : la version est le repli `setuptools_scm`, donc la
> 1.0 n'a jamais été publiée.
>
> **Hors numérotation P#, livré en août 2026** : l'**axe correction structurée**
> (`ALTO → ALTO`, `cinoc correct`) — inventorié au roll-up de
> [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) §« Axe correction structurée ». Il ne
> figurait dans aucune des cinq étapes ci-dessous : ce plan décrivait le portage
> de Picarones, et cet axe est du **neuf**. Il porte **un arbitrage à rendre avant
> la 1.0** — lui donner une surface web, ou acter qu'il reste un outil de ligne de
> commande.
>
> **Différé opérationnel** : segmenteur Space (T2.5 — dégradé gracieux livré, ne
> bloque pas 1.0). **Surface NER vivante** : `Competitor.ner` est câblé au
> planificateur ; le formulaire web reste à trancher avec l'arbitrage ci-dessus.

- [x] **Étape 1 ✅ (D-075)** : le Space public exécute Tesseract gratuitement (build fail-fast, OMP borné, `fra` présent ; mode public fail-closed, binaire tracé au `RunManifest`). *Décision segmenteur (PP-DocLayout, T2.5) **différée** — mesurer le cold-start ; dégradé gracieux livré, ne bloque pas 1.0.*
- [x] **Étape 2 ✅ (D-076→D-080)** : Google + Azure first-party, Pero + Calamari first-party in-tree (D-078), zero-shot vérifié, jetons remontés par les adapters cloud, **16 prompts curés portés** + prompt libre UI.
- [x] **Étape 3 / Rapport interactif** : 4 onglets, chrome unifié + exports, héros+cartes, glossaire en dialog, graphes SVG, tables triables + survol-définitions, profil moteur drill-in, galerie-entrée + détail document drill-in (U1→U4 livrés, cf. `PLAN_UI_RAPPORT.md`).
- [x] **P0 — Enveloppe données** : `DocumentRef.metadata` optionnel + référence image dans `RunDocumentResult` (jamais les octets). *(strates D-110 + image D-111)*
- [x] **P1 — Rapport données locales ✅** : T3 vignettes ✅ · T4 fac-similé + diff pleine page ✅ · U5′ strates ✅ · **nombres FR ✅ (D-215** — séparateur décimal localisé à l'affichage, couches machine en point) · saveur **dossier ✅** (CLI `--report-dir` + téléchargement ZIP web **D-214**).
- [x] **P2 / Étape 4 TERMINÉE** : **toutes** les familles métriques gardées portées (4g + 4a→4f, ordre révisé — `ANALYSE_ETAPE_4.md`), chacune avec section + tests valeurs-main. Plus aucune famille gardée hors Cinoc. **4g.1 ✅** (conformité HIPE, D-115) · **4g.2 ✅** (bilan de correction, D-116 — absorbe over_normalization/error_absorption ; procédure `hallucination` : machinerie livrée, **exécutée sur run réel ✅ D-218** — Dresden curé 10 p., Tesseract `deu`, hallucination = 0,818, chaîne complète validée) · **4a ✅** (données structurées, D-117 — readability abandonné, acté) · **4b.1 ✅** (philologie/abréviations, D-118) · **4b.2 ✅** (philologie/imprimé ancien — stratégie positionnelle, D-119) · **4b.3 ✅** (philologie/archives modernes — stratégie archival bornée, D-120) · **4b.4 ✅** (philologie/numéraux romains — 5 statuts, R1 fermée, R2, D-121) · **4b.5 ✅** (philologie/archaïsmes `air`/`hcpr` — scalaires, moteur de préservation factorisé/parité, listes package-data + empreinte, D-122) → **4b TERMINÉE** · **4c réduit ✅** (fidélité textuelle — rare_tokens + lexical_modernization, collecteur corpus, R6 câblage homogène, D-123) · **4e.1 ✅** (inter-moteurs — JS sur comptages taxonomy + oracle bag-of-words borne documentée, R10, abandon `incremental_comparison` acté, D-124) · **4e.2 ✅** (distribution par ligne — alignement F15, percentiles/Gini, seuils inclusifs, heatmap, sonde `\n`, D-125) · **4e.3 ✅** (longitudinal — OLS parité scipy + **Pettitt** R11, `series_insight` → `/history`, D-126) → **4e TERMINÉE** · **4f ✅** (NER — R14 reprojection des spans en coords GT, scalaire `ner_f1` + 15ᵉ payload + section + adapter spaCy fail-closed + extra `[ner]`, D-127 ; étape NER en pipeline vivant différée = surface) · **4d.1 ✅** (qualité d'image — 16ᵉ payload `image_quality` scope corpus par document, numpy+PIL, constantes = conventions éditoriales R8, pas de mock R9, `image_predictive` abandonné C3, D-128) · **4d.2 robustesse ABANDONNÉE (D-129)** — renversement assumé du verdict GARDER : dégradations **synthétiques** (validité douteuse vs vrais défauts de scan), coût re-OCR disproportionné, seule feature à traîner la couche 6 + la tension CLI §8.4, résilience réelle = affaire des **strates du dataset P3**. → **P2 TERMINÉE.**
- [x] **i18n finale du rapport ✅ (D-136→D-142)** : passe unique après P2 (D-114) — **tout** le rapport (chrome + héros + 4 onglets + **toutes** les sections + aria-labels) est bilingue FR/EN via `SectionContext.lang` (route web `?lang=en`), mécanisme unique `html.localized` inline (R7 — pas de catalogue). FR byte-identique ; +1 test EN par section.
- [x] **P3 — Dataset de référence curé ✅** : standardiseur (D-202) + importeur réf-IIIF (D-203) + script de publication HF (D-206) + **dataset Dresden publié** & rapport à liens IIIF/HF prouvé (D-207) + import web (D-211) + **découverte automatique** par compte/tag (D-213). Chaîne prouvée extensible.
- [x] **P4 — Saveurs & échelle ✅** : saveur réfs IIIF ✅ (D-207) · saveur dossier/ZIP ✅ (D-214) · **saveur servie ✅ (D-231)** — la page web ne porte que des URL, les vignettes sont produites à la demande, **sans plafond** (le rapport autonome, lui, s'arrête à 300 documents *en silence*). Galerie paginée et chargement paresseux : déjà acquis côté rapport.
- [x] `make ci` vert (3 OS × Python 3.11/3.12/3.13), couverture ≥ 85 %, tous les garde-fous d'archi verts. *(Vérifié localement le 2026-09-09 : `ruff` + `mypy --strict` + suite complète, couverture très au-dessus du seuil. Deux défauts trouvés à cette occasion et corrigés : filtre anti-SSRF cassé sur réseau NAT64 — D-221 — et deux briques de la correction structurée hors du gate — D-222.)*
- [x] `README`/`CHANGELOG`/`pricing.json` à jour, roll-up réconcilié : **README ✅** · **CHANGELOG ✅** (section `[1.0.0]` datée) · **roll-up ✅** (D-223, puis au fil des D-entries) · **`pricing.json` vérifié au tag ✅** — `last_updated` 2026-06-10, `valid_until` 2026-12-01, donc **valide au 2026-09-10** ; le rapport avertit de lui-même au-delà de cette date.
- [x] **Parité web ⇄ CLI ✅ (D-224→D-227)** : toute *capacité* du web l'est aussi en ligne de commande — acquisition de corpus (`cinoc corpus`), introspection (`cinoc list`), validation à blanc, export ALTO, segmentation seule. Les 26 routes sont couvertes ou justifiées `transport`, verrouillé par `tests/guardrails/test_web_cli_parity.py` ; `CLAUDE.md` §8.4 amendé en conséquence. **`examples/config.yaml`** livré, exécutable sans moteur.
- [x] **Arbitrage rendu ✅ (D-229)** : la correction structurée est **livrée au web** (`POST /api/runs/correction` + section au composeur), et non actée comme outil de ligne de commande — le gel de Picarones ferme la fenêtre, et une capacité qu'on ne peut lancer que par un terminal n'est pas dans le produit. Le lanceur **refuse** un corpus dont la vérité terrain est extraite de son propre ALTO (zéro tautologique). `README` à jour.
- [x] **Tag `v1.0.0` posé ✅** (2026-09-10) — la version cesse d'être le repli `setuptools_scm`.
- [ ] Gel de Picarones (5b) — **différé à la demande de l'utilisateur**, hors du chemin de la 1.0. Rien n'en dépend : le périmètre gardé est **entièrement** dans Cinoc, c'est la condition que le gel attendait.

---

# RÉFÉRENCES

## Abandons définitifs (9) — validés

Ce qui était dans Picarones et **ne sera pas porté** → le gel n'en perd rien.
Les 8 premiers sont jugés sans valeur même réparés ; le 9ᵉ (`robustness`) avait
une valeur réelle mais un rapport coût/validité défavorable (décision produit
D-129, réversible via journal si un besoin concret émerge) :

| # | Famille | Ce que ça faisait | Pourquoi on l'abandonne |
|---|---|---|---|
| 1 | Estimation CO₂ | g CO₂/1000 pages | kWh inventé × intensité conventionnelle ; aucun chiffre mesuré → viole l'anti-hallucination |
| 2 | `image_predictive` | « prédire » le CER depuis la qualité image | **abandon acté D-128 (4d.1), motif corrigé (C3)** : pas un stub mais une **re-pondération** des mêmes features qu'`image_quality` (sa docstring assume « Pas de prédiction CER absolue ») — aucun pouvoir prédictif ni info nouvelle, nom mensonger, moitié « homogénéité » couplée à un détecteur narratif supprimé. La **mesure** de qualité, elle, est gardée (4d.1 ✅) |
| 3 | Calibration au-delà de l'existant | ECE/MCE supplémentaires | Cinoc a déjà `ConfidenceToken` + ECE/MCE ; un seul moteur fournit des confiances → rien à étendre |
| 4 | Registre `levers` (561 LOC) | « leviers d'amélioration » | 561 LOC, dépendances **silencieuses** (pattern narratif déjà supprimé). Les 2-3 observations saines sont repliées dans `synthesis` |
| 5 | taxonomy intra_doc / cooccurrence / comparison | 3 re-projections de la taxonomy | aucune info nouvelle, peu testées, 3 renderers à maintenir. La taxonomy cœur est gardée |
| 6 | `reliability` (Cohen κ / Krippendorff α) | accord inter-annotateurs | plafonné à 2 annotateurs, jamais branché ; outillage de campagne d'annotation, pas de benchmark |
| 7 | `module_policy` | audit de manifeste tiers | zéro module tiers ; les entry-points `cinoc.modules` font déjà mieux |
| 8 | WIL | variante d'erreur mot | quasi-monotone du WER : zéro décision différente, une colonne de plus |
| 9 | `robustness` (4d.2) | courbes CER vs niveaux de dégradation **réels** (re-OCR sur images dégradées) | **décision produit D-129** (renverse le verdict GARDER, l'analyse l'autorise) : dégradations **synthétiques** (bruit gaussien, blur, NEAREST…) de **validité douteuse** vs vrais défauts de scan (rousseurs, transparence, gondolage) ; **coût re-OCR disproportionné** (≈ 300 ré-exécutions, payant sur cloud) vs valeur d'un graphe vu une fois ; **seule feature** à exiger la couche 6 + la tension CLI §8.4 ; la résilience **réelle** se mesure mieux sur les **strates du dataset P3** (images vraiment dégradées). `image_quality` (4d.1) couvre déjà « mes images sont-elles dégradées ? ». `robustness_projection` (jamais porté) devient sans objet. Réversible : l'enveloppe `analyses` l'accueillerait si un besoin de courbes de résilience émergeait |

## Verdict métrique-par-métrique (sur pièces)

Synthèse des deux audits de qualité d'exécution. ✅ utile · 🔶 réparable
(réparée au portage) · 🟡 gadget (abandonnée).

| Famille | Verdict | Sur pièces | Destination |
|---|---|---|---|
| CER / WER / MER | ✅ | parité jiwer | livré |
| diacritiques, MUFI, del/ins | ✅ | NFD align, PUA | livré |
| confusion + char_scores | ✅ | Levenshtein minimal (fix F4) | livré |
| taxonomy cœur | ✅ | classes à sens analytique | livré |
| searchability | ✅ | Levenshtein≤2 (Elastic), 21 tests | livré |
| hallucination | 🔶 | trigrammes ; faux positifs diacritiques/multilingue | livré, à durcir |
| economics | ✅ | jetons + temps mesurés | livré (CO₂ exclu) |
| calibration | ✅ | Guo et al. | livré |
| longitudinal | 🔶 | OLS OK ; « CUSUM » = max-diff naïf | livré ; change-point raffiné en 4e |
| numerical_sequences | ✅ | regex conservatrices, recto/verso | **étape 4a** |
| readability (Flesch) | ✅ | formules publiées | **4a** |
| abbreviations | ✅ | 2 scores, pas de GT spéciale | **4b** |
| early_modern + roman + archives | 🔶 | fragmenté, roman doublée | **4b** (unifié) |
| rare_tokens + lexical + over_norm + equivalence | 🔶 | câblage fragmenté | **4c** (unifié) |
| robustness | 🟡 | vraies dégradations PIL + re-OCR, mais **synthétiques** (validité douteuse) + coût re-OCR disproportionné | **abandonnée 4d.2 (D-129)** — résilience réelle → strates P3 |
| image_quality | ✅ | mesure portée, constantes **documentées** (conventions éditoriales R8) | **4d.1 ✅ (D-128)** |
| inter_engine | ✅ | Jensen-Shannon + oracle gap | **4e** |
| error_absorption | ✅ | multiset correct | **4e** |
| line_metrics | ✅ | percentiles/Gini ; alignement à fiabiliser | **4e** |
| NER | ✅ | IoU solide, mais découplée chez Picarones | **4f** (recâblée) |
| taxonomy dérivées, CO₂, image_predictive, calibration+, levers, reliability, module_policy, WIL, **robustness** (D-129) | 🟡 | voir Abandons | **abandonnées** |

## Garde-fous anti-« syndrome Picarones » appliqués à ce plan

- **Un seul plan, linéaire** — plus de double axe T#/S#, plus de phases croisées.
- **Zéro shim** : un seul format `RunResult`, aucun pont vers Picarones.
- **Budgets fichier** : chaque nouveau fichier sous 600 LOC ou entrée justifiée.
- **Pas de spéculatif** : chaque métrique de l'étape 4 a un consommateur (sa
  section). Les 🔶 sont réparées, jamais empilées telles quelles. Les 8 abandons
  restent dehors.
- **Anti-silence** : NER et coûts affichent un message explicite si une
  dépendance/un tarif manque, jamais `[]`/`0` muet.
- **Anti-hallucination** : aucun LLM dans le rapport ; tout nombre est une
  fonction auditable des données d'entrée.
- **`make ci` complet avant chaque push.**
