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
| **P5a — Dette révélée par l'usage** | sept défauts trouvés par le premier banc de presse multi-colonnes ; onze PR ordonnées en quatre groupes. Une seule brique neuve : l'appariement géométrique des régions, qui débloque l'OLR inter-systèmes. | P2 (métriques layout) | correctif |
| **P5b — Persistance et calcul à la demande** | garder ce qu'un run a produit (fait), puis calculer une analyse au clic dans la saveur servie. **Suspendue** à un arbitrage de produit : le manifeste porte-t-il la liste des documents, ou le serveur retient-il l'association run ⇄ spec. | P5a | neuf |
| **P5c — Joignabilité** | ce qui est construit doit être atteignable. Une capacité entière — les recettes — livrée en `app`, en routeur, en CLI, testée… et jamais appelée par la page. Le garde-fou de parité était vert : il ne regarde pas dans ce sens. La phase ferme la **classe** avant d'en réparer les cas. | P5a | correctif + surface |
| **P5 — Release 1.0 + gel Picarones** | checklist · tag · README/CHANGELOG · gel. | tout, **dont P5a** ; P5b et P5c ne bloquent pas le tag | — |

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

## Étape 4bis / **P5a** — La dette que l'usage réel a révélée (bloque le tag)

> **Pourquoi cette phase n'existait pas.** La checklist « 1.0 prête » est passée
> au vert le 2026-09-09. Elle a été vérifiée sur les corpus du dépôt : un bloc de
> texte par page, quelques milliers de caractères. **Aucun banc n'avait encore
> tourné sur de la presse ancienne multi-colonnes** — 40 000 caractères par page,
> six colonnes, des centaines de régions. Le premier l'a fait en septembre, et il
> a trouvé sept défauts. Cinq faussent des résultats ou les rendent illisibles.
>
> Publier la 1.0 avec eux, ce n'est pas publier un outil incomplet : c'est
> publier des **classements faux**. D'où le blocage explicite du tag.
>
> **Ce que la phase dit de la méthode, au passage.** Ces défauts n'étaient pas
> détectables par relecture : ils exigeaient un corpus dont la *forme* diffère de
> celle des fixtures. C'est l'argument, a posteriori, du dataset curé de P3 — et
> la raison d'en vouloir un **second**, de genre différent.

### L'enchaînement, dans l'ordre de fusion

Quatre groupes. À l'intérieur d'un groupe, les PR sont indépendantes ; entre
groupes, l'ordre compte — corriger les chiffres avant d'en corriger le coût,
et le coût avant d'ouvrir la surface d'extension.

| # | PR | Ce qu'elle corrige | Effet mesuré | état |
|---|---|---|---|---|
| **G1** | | **Ce qui fausse des résultats** | | |
| 1 | #129 | deux régions pour la même aire, fan-out qui ne descendait pas dans les blocs composés, DPI que Tesseract devinait, distance d'édition quadratique | CER 1,009 → plausible | ✅ |
| 2 | #131 | le candidat noté était choisi par *type* d'artefact, donc un intermédiaire dès qu'une étape suit la correction | CER 0,884 → 0,808 | ✅ |
| 3 | #130 | confusions de caractères alignées à la mauvaise granularité | ×258 | ✅ |
| **G2** | | **Ce que coûte une évaluation** | | |
| 4 | #132 | les analyses ignoraient `metric_names` : 34 produites pour 6 demandées | ×21,8 | ✅ |
| **G3** | | **Le point d'extension** | | |
| 5 | #127 | un segmenteur ne disait pas ce qu'il sait détecter | — | ✅ |
| 6 | #128 | brancher un segmenteur exigeait d'écrire du Python | — | ✅ |
| 7 | #133 | modules privés imposés à un module tiers ; module installé invisible — **web et CLI** | vérifié sur un module tiers réel | ✅ |
| **G4** | | **Écrit à partir de là** | | |
| 8 | #135 | apparier les régions par géométrie, pas par identifiant | débloque l'OLR inter-systèmes | ✅ |
| 9 | #136 | `code_version` dépendante du répertoire courant | reproductibilité §12 | ✅ |
| 10 | #137 | `timeout` de Tesseract non réglable depuis la spec | une unité perdue sans recours | ✅ |
| 11 | — | deux vues texte observent deux fois les mêmes textes | **3,7 %** mesuré (38 % annoncé) | **fermé, non retenu** |
| **hors plan** | | **Né d'une décision produit en cours de route** | | |
| 12 | #138 | distance et alignement écrits à la main, là où `rapidfuzz` est déjà une dépendance | ×13 ; `mer` de 11 s à 0,009 s | ✅ |
| 13 | #139 | **le banc est rapide par défaut**, le détail se réclame | 916 s → **29 s** | ✅ |

**Ce que la mesure a corrigé dans ce plan.** L'item 11 était annoncé « facteur 2 ».
Mesuré trois fois, il a donné 17 %, puis 43 %, puis 38 % — un chiffre qui bouge
ainsi n'est pas un arbitrage, c'est le signe qu'on regarde le mauvais poste. Le
vrai coût était ailleurs, et c'est l'item 12 qui l'a trouvé. **Mesurer avant
d'écrire a changé deux fois ce qu'il fallait écrire** ; c'est la leçon
méthodologique de cette phase, et elle vaut plus que les correctifs eux-mêmes.

**L'item 13 n'était dans aucun plan.** Il est né d'une question simple posée en
cours de route — *pourquoi produire par défaut ce que personne ne demande ?* —
et il rend à lui seul un facteur 31 sur le cas courant, soit davantage que les
optimisations qu'on envisageait à sa place. Une décision de produit a battu
trois jours d'optimisation.

**Ce que la revue de #133 a trouvé, et qui est corrigé dedans.** Elle ne câblait
que la CLI : le web ignorait `third_party_statuses`, ce qui rompait la parité
D-224 sans que `test_web_cli_parity` le voie — la capacité étant neuve des deux
côtés, aucune route n'était en défaut. Et `test_default_loader_runs_clean`
affirmait que la découverte rend `()` : il ne vérifiait donc le câblage qu'**en
l'absence** de ce qu'il câble, et tombait dès qu'un module tiers était réellement
installé. Les deux sont réglés dans la PR.

### G4-8 — Apparier les régions par géométrie ✅ (#135)

Six métriques de structure existent — `region_detection`, `region_cer`,
`line_identity_cer`, `line_identity_coverage`, `reading_order_tau`,
`reading_order_coverage` — et la vérité terrain se lit en ALTO, en PAGE-XML ou en
JSON natif. Sur le papier, cinoc sait donc déjà noter une OLR.

En pratique, **une seule de ces six marche entre deux systèmes différents.** Les
cinq autres apparient les blocs **par identifiant**, or les identifiants de la
BnF (`r_10_1`) ne seront jamais ceux d'un détecteur (`r1`, `block_0`). Mesuré, en
prenant une vérité terrain et en la re-numérotant — géométrie et texte
rigoureusement identiques :

| | mêmes identifiants | identifiants d'un autre système |
|---|---|---|
| `region_detection` | 1,000 | **1,000** ✓ |
| `region_cer` | 0,000 | **1,000** ⚠ |
| `reading_order_tau` | 0,000 | **None** |
| `reading_order_coverage` | 1,000 | **0,000** |

`region_cer` est le cas grave : il annonce **1,000**, le pire score possible, pour
une transcription **parfaite**. Ce n'est pas « non applicable », c'est un faux
négatif silencieux — un banc classerait dernier un système irréprochable.

`region_detection` sait déjà apparier par IoU de boîte. **Réutiliser cet
appariement** pour les quatre autres les rend utilisables entre systèmes, sans
rien inventer. C'est ce qui manquait au banc de presse : faute de pouvoir mesurer
l'ordre de lecture, il a fallu se rabattre sur le CER pleine page, qui le mesure
de travers — et qui a fait conclure, à tort, qu'une chaîne de référence perdait
contre Tesseract seul.

### Item 11 — fermé sans être retenu, et ce qu'il a appris

**Écrit, testé, vérifié sans perte — puis écarté sur sa mesure.** Le correctif
existait : les treize collecteurs rendus indifférents aux métriques de leur vue
(le CER de ``document_texts`` déplacé de l'observation vers la construction, où
il ne sert qu'à ordonner), puis les vues regroupées par signature de texte. Gate
complet vert, et les deux ``RunResult`` produits avec et sans le correctif sont
**rigoureusement identiques**.

| | 30 unités, mode détaillé |
|---|---|
| sans le correctif | 512,9 s |
| avec | 493,8 s |

**3,7 %.** Le plan annonçait 38 %. Pour une logique de regroupement ajoutée au
runner et l'interface d'un collecteur modifiée, l'échange n'est pas bon
(``CLAUDE.md`` §5 : une feature s'ajoute *dans un budget*).

**Et l'écart désigne le vrai coût.** Retirer une observation sur deux fait gagner
19 s : les **deux** passes d'observation pèsent donc 38 s sur 512, soit **7 %**.
Les 92 % restants sont dans l'**assemblage** des analyses, pas dans l'observation
par unité.

**Pourquoi trois mesures successives s'étaient trompées.** Elles portaient sur
quatre pipelines ; le banc réel en a dix. Or plusieurs analyses comparent les
pipelines **deux à deux** — 6 paires à quatre pipelines, **45** à dix, **66** à
douze. Ce poste croît au **carré** du nombre de moteurs et écrase tout le reste
dès qu'on en compare plus d'une poignée. Un profil sur un échantillon réduit ne
pouvait structurellement pas le voir : *réduire le corpus pour profiler est sûr,
réduire le nombre de concurrents ne l'est pas*.

### Le vrai poste du mode détaillé — constat, pas item

Les analyses par **paires de pipelines** sont quadratiques. C'est là qu'il
faudrait chercher si le mode détaillé devenait un usage courant sur de grands
bancs.

Ce n'est **pas** inscrit comme travail à faire : depuis que le mode rapide est le
défaut (item 13), le mode détaillé est une demande explicite et ponctuelle. Écrire
l'optimisation maintenant serait spéculatif — la règle « pas de consommateur =
supprimé » vaut aussi pour la performance.

### Deux réserves ouvertes, constatées en revue

Ni l'une ni l'autre ne bloque, les deux méritent d'être écrites plutôt que
retenues.

**Un module tiers peut exécuter n'importe quoi, et n'est pas dans
`CLI_ONLY_KINDS`.** Cette liste protège `cli_layout` et `ocrd` d'un lancement par
HTTP. Un plugin installé, lui, passe — sur une instance privée, le web pourrait
le lancer. Installer un plugin est déjà une décision de confiance de
l'exploitant, d'où l'absence d'urgence ; mais la frontière mérite d'être
explicite plutôt qu'implicite.

**Le contrôle de cohérence ne voit pas les modules tiers.** `declared_labels`
interroge le registre du socle : un segmenteur tiers ne déclarant pas ses
classes, son vocabulaire est inconnu et le contrôle passe. Correct par défaut
(on ne refuse que ce qu'on peut réfuter), mais un module tiers **qui** déclare
`LABELS` ne serait pas vérifié non plus.

### Ce que P5a ne contient pas

Ni feature, ni surface nouvelle — à l'exception assumée de l'item 13, qui est une
décision de produit et non un correctif. Les modules tiers eux-mêmes vivent
**hors du dépôt** ; la chaîne NDNP de la Library of Congress en est la preuve
exécutée.

---

## Étape 4ter / **P5b** — Ce que le mode rapide appelle ensuite

> **Pourquoi cette phase existe.** L'item 13 a posé une question qu'il ne résout
> pas : si le détail ne se produit plus par défaut, comment l'obtenir **après
> coup**, sans relancer un banc entier ? La réponse actuelle — relancer avec
> `--analyses toutes`, la reprise rendant l'exécution gratuite — fonctionne mais
> reste grossière : tout ou rien, et en ligne de commande.
>
> **Suspendue, et doublée par P5c.** L'obstacle décrit plus bas est un arbitrage
> de produit non rendu, pas un développement en attente. Tant qu'il ne l'est
> pas, **P5c passe devant** : elle ne demande aucune décision de ce genre et
> rend joignable du code déjà écrit.

| # | Contenu | Dépend de |
|---|---|---|
| **1** ✅ | **Garder ce qu'un run a produit** — *résolu en le cherchant, pas en le construisant*. Le mécanisme existait : `ResumeStore.save` **copie** les fichiers et réécrit leur chemin, donc les sorties survivent au workspace. Vérifié sur le banc de presse : 30 unités sur 30 retrouvées, textes compris, des heures après. Il ne manquait que la **trace** — le manifeste ignorait où elles étaient conservées, donc un `RunResult` ne pouvait pas retrouver ce qu'il avait produit. `RunManifest.artifacts_dir` comble ça. | — |
| **1bis** | **Une saveur « textes à côté ».** Idée de l'utilisateur, mesurée : `document_texts` pèse **52 %** d'un résultat détaillé (1,94 Mo sur 3,71), les métriques **1,3 %**. Sortir les textes en fichiers voisins, selon la convention que `precomputed` lit déjà, rendrait un rapport **capable de recalculer seul** — sans cache de reprise ni spec d'origine. **Son argument n'est plus le poids** : depuis le mode rapide, le résultat tombe à 0,08 Mo et le rapport à 3,8 Mo, presque entièrement des images. Ce qu'elle apporte est le cas de *celui qui reçoit* le rapport, pas de celui qui l'a lancé. **Idée consignée, pas engagée.** | — |
| **2** | **Calculer une analyse à la demande, dans la saveur servie.** Un clic sur une section absente la produit, avec le vrai code — pas une réimplémentation en JavaScript, qui divergerait et violerait « tous les nombres sont une fonction auditable des données d'entrée ». L'aperçu de segmentation est le précédent. | 1 |

**Obstacle trouvé en vérifiant la faisabilité (passage 3 de la boucle).** Le
recalcul lui-même est bon marché — **9,8 s pour une analyse**, contre 493 s pour
les trente-quatre, artefacts rechargés en 0,2 s. Mais un `RunResult` **ne peut
pas retrouver ses propres unités** : leur empreinte dépend du document, et le
manifeste porte le nom du corpus et son compte, **pas la liste**. Le recalcul
exige donc la spec d'origine, qu'un rapport n'a pas.

Deux façons de lever ça, et c'est un arbitrage de produit : faire porter la
liste des documents au manifeste — un `RunResult` reste alors **autosuffisant**,
au prix de chemins locaux inscrits dans un fichier destiné au partage — ou faire
retenir l'association run ⇄ spec au serveur, plus léger mais inopérant dès que
le rapport voyage. L'item **1bis** ci-dessus contourne les deux.

Et le garde-fou de parité interdit de livrer la moitié : toute commande CLI doit
déclarer son pendant web. Livrer `cinoc analyse` seul ferait rougir la CI — ce
qui est exactement son office.

**Ce que ça ne sera pas.** Le rapport **autonome** ne calcule rien : un fichier
seul n'a ni code ni données, et y embarquer les textes de toutes les pages le
ferait peser des centaines de méga-octets. La fonctionnalité appartient à la
saveur servie, et c'est une limite de conception assumée, pas un manque.

**Inconnue levée** : le cache de reprise garde bien les textes — il **copie**
les fichiers. L'item 1 n'était donc pas un développement mais un constat, plus
une trace de deux lignes. Un mécanisme portait deux rôles sans que le second
soit nommé nulle part : éviter de ré-exécuter, *et* conserver les sorties.

C'est le troisième item de suite dont la mesure préalable change la nature —
après l'item 11 (fermé à 3,7 % au lieu de 38 %) et l'item 13 (une ligne de
décision produit valant mieux que trois jours d'optimisation). **Chercher avant
d'écrire a évité un développement entier.**

---

## Étape 4quater / **P5c** — Joignabilité : ce qui est construit doit être atteignable

> **Pourquoi cette phase existe.** Un audit des trente et une routes de l'app a
> trouvé une capacité complète — les **recettes** — livrée en couche `app`,
> livrée au routeur, livrée en CLI, testée, documentée… et **jamais appelée par
> la page**. Le garde-fou de parité était vert, et à bon droit : il vérifie
> route ⇄ commande CLI, et rien ne vérifiait route ⇄ page. Ce n'est pas un oubli
> isolé : c'est une **classe** de défaut, que cette phase ferme avant d'en
> réparer les cas.

### Ce que l'audit a mesuré

| Route | Statut au garde-fou | Appels depuis la page |
|---|---|---|
| `GET /api/recipes` | `cli:list` ✅ | **0** |
| `POST /api/runs/recipe` | `cli:run` ✅ | **0** |
| `POST /api/runs/spec` | `cli:run` ✅ | **0** |

Pour comparaison, les routes réellement branchées : `/api/runs` (7 occurrences),
`/api/models/` (3), `/api/corpus` (3), `/api/runs/config` (2), puis
`/api/normalization/preview`, `/api/runs/correction`, `/api/segmentation/run` et
`/api/segmentation/preview` (une chacune). Le front construisant certaines URL
par concaténation, l'inventaire des `fetch()` a été relu un par un : aucun ne
vise une recette.

**Un second cas, d'une autre nature.** `standardize_corpus`
(`app/dataset_standardize.py`, D-202) — le producteur de dataset curé, sept
tests, vérifié sur dix pages réelles du Dresdner Hofdiarium — n'a **ni commande
CLI ni route web**. Il est seul dans ce cas parmi les 84 fonctions publiques de
`app/`. D-205 le disait sans le nommer : la preuve de bout en bout a tourné par
un « script de preuve (scratchpad, non committé) ». Le garde-fou ne peut pas le
voir non plus — il n'audite que ce qui possède déjà **une** des deux faces.

**Deux fausses pistes écartées en vérifiant.** Les cinq importeurs de corpus
sont joignables : la page les câble par `data-import-source`, pas par
`data-source`. Et dix des onze fonctions `app/` sans appelant externe sont
appelées **à l'intérieur de leur propre module** — un premier scan qui excluait
le fichier de définition les avait fait passer pour orphelines.

### Ce que cela coûte à l'utilisateur

Un utilisateur du web dispose de **quatre formes** de pipeline ; le graphe en
admet des centaines, et la CLI les atteint toutes. Les recettes étaient
précisément la **troisième voie** conçue par D-239 contre ce déséquilibre —
« une forme éprouvée, nommée par son intention, dont l'utilisateur ne remplit
que les briques ». Elle existe, elle est correcte, elle n'a jamais été offerte.

Conséquence concrète, vécue au premier banc de presse ancienne : le défaut de
page blanche se contournait par `--dpi 300`, et **aucun réglage d'adapter n'est
atteignable depuis le web** — ni `dpi`, ni `psm`, ni `timeout`, ni `oem`.
`RecipeRequest` accepte `choices` (quelle brique pour quelle étape) mais pas
`params`. Un utilisateur du web qui rencontre ce défaut n'a donc aucun recours,
alors même que le correctif tient en un entier.

### L'enchaînement, dans l'ordre de fusion

| # | Contenu | Dépend de |
|---|---|---|
| **1** | **La troisième clause du garde-fou de parité.** Toute route `/api/*` est soit appelée par le front, soit déclarée `front-absent: <raison>`, soit une `dette:<id>` avec son échéance — exactement la forme des deux clauses existantes. Écrite **en premier** parce qu'elle transforme le reste de la phase en CI rouge plutôt qu'en bonnes intentions : les trois routes de recette rougissent aussitôt et s'inscrivent en dettes datées. | — |
| **2** | **Brancher les recettes dans la page.** `GET /api/recipes` peuple un catalogue (titre + description, déjà bilingues) ; lancer appelle `POST /api/runs/recipe` avec les briques choisies. Le lanceur, le suivi SSE et l'affichage du rapport existent — c'est le chemin du bouton « lancer » actuel. Ferme deux des trois dettes. | 1 |
| **3** | **Ouvrir `params` à la requête de recette.** `plan_from_recipe` accepte déjà `params` ; seule la frontière HTTP les refuse. Rend `dpi`/`psm`/`timeout` atteignables sans inventer de surface : un réglage par étape, validé par le rôle. | 2 |
| **4** | **Trancher la porte « spec complète ».** `POST /api/runs/spec` est documentée comme « la porte qui donne au web l'intégralité du graphe sans une case de plus ». Soit on lui donne une zone de dépôt (un fichier YAML/JSON glissé, le corpus restant celui du serveur), soit on acte qu'elle est réservée aux clients programmatiques et on l'inscrit `front-absent`. Les deux sont défendables ; ce qui ne l'est pas, c'est le silence. Ferme la troisième dette. | 1 |
| **5** | **Les recettes manquantes — de la donnée, pas du code.** Cinq recettes existent (`ocr_simple`, `ocr_puis_llm`, `alto_corrige`, `presse_ancienne`, `vote_trois_moteurs`). Manquent au moins la chaîne de segmentation → reconnaissance par région → projection telle que la presse ancienne la demande réellement, et une forme avec préprocessing. Ajouter une recette est un fichier YAML validé au chargement. | 3 |
| **6** | **`standardize_corpus` : une face ou l'autre.** Soit une sous-commande `cinoc corpus standardize` (et son pendant web, que la clause de parité imposera), soit l'inscription explicite qu'il s'agit d'un producteur interne au dépôt, hors produit. Le tenir livré-mais-injoignable est le seul état à exclure. | 1 |
| **7** | **Le composeur contraint.** Dernier parce qu'il n'est que l'éditeur de ce que 2→5 rendent réel. `roles()` porte déjà la signature typée de chaque rôle : à partir d'un ensemble de types disponibles, les rôles proposables sont ceux dont les `entrees` y sont contenues. L'UI devient une liste d'étapes et un menu **qui ne contient que ce qui peut se brancher** — pas un canevas de nœuds, où rien n'empêche de relier une sortie texte à une entrée image. Sa sortie naturelle est un YAML de recette : de la donnée, versionnable, relançable en CLI, qui alimente le catalogue au lieu de mourir dans un formulaire. | 5 |

### Pourquoi P5c passe avant P5b

P5b est **suspendue à un arbitrage de produit** non rendu : pour recalculer une
analyse, il faut retrouver les unités d'un run, donc soit inscrire la liste des
documents au manifeste — un `RunResult` devient autosuffisant, au prix de
chemins locaux dans un fichier destiné au partage — soit faire retenir
l'association run ⇄ spec au serveur, plus léger mais inopérant dès que le
rapport voyage. P5c ne dépend d'aucune décision de ce genre : son item 1 tient
en une dizaine de lignes dans un fichier qui fait déjà ce travail dans les deux
autres sens, et ses items 2 et 3 branchent du code déjà écrit et déjà testé.
**Rendre joignable ce qui existe passe avant construire ce qui n'existe pas.**

### Ce que P5c ne contient pas

Aucune brique de pipeline, aucune métrique, aucune section de rapport. Une seule
surface nouvelle — le composeur de l'item 7 — et elle n'ajoute aucune capacité :
elle rend atteignable la capacité que les rôles portent déjà. Le reste est du
câblage et un garde-fou.

### Ce que l'audit a corrigé au passage

Deux endroits affirmaient que la post-correction structurée n'a pas de surface
web : `CLAUDE.md` §0 et la ligne « couche 8 » du roll-up. C'est faux depuis
D-229 — le bouton `correct-launch` existe, `benchmark.js` appelle
`/api/runs/correction`, et la checklist de ce plan le coche. Les deux sont
réconciliés dans le même commit que cette phase. La leçon rejoint celle de la
checklist « 1.0 prête » : un statut recopié pourrit, et celui-ci a pourri dans
le sens rassurant — il annonçait un manque là où il y avait une livraison.

---

## Étape 5 — Release `1.0.0` puis gel de Picarones

| Sous-étape | Contenu |
|---|---|
| **5a — Release 1.0.0** | Vérifier la checklist ci-dessous · tag `v1.0.0` · `README` (positionnement 1.0, matrice moteurs/extras, mode Space) · `CHANGELOG` minimal · `pricing.json` daté · roll-up `MIGRATION_PLAN.md` réconcilié |
| **5b — Gel de Picarones** | Bannière `README` Picarones → « projet figé, successeur Cinoc » · dépôt GitHub archivé en lecture seule · note de dépréciation sur le Space HF Picarones (lien vers le Space Cinoc) · plus aucun commit Picarones |

### Checklist « 1.0 prête »

> **État au 2026-09-09 (D-223, révisé D-232)** : **Étapes 1→4 ✅** (Space-OCR, parité moteurs,
> interface/rapport, P2 métriques) **+ i18n finale ✅** (D-136→D-142) **+ P0→P3 ✅**
> (enveloppe données, rapport local, métriques, dataset curé publié) **+ 3c
> expose-ALTO ✅** (D-219). **Reste pour la 1.0** : **P5** (release + gel) ; **P4**
> réduit à la *saveur servie*, que ce plan déclare lui-même pouvoir suivre la 1.0.
> **Aucun tag `git` n'existe** : la version est le repli `setuptools_scm`, donc la
> 1.0 n'a jamais été publiée.
>
> **Révision 2026-09-23 — cet encadré a verdi trop tôt.** Il a été vérifié sur
> les corpus du dépôt, tous à un bloc de texte par page. Le premier banc de
> presse ancienne multi-colonnes a trouvé **sept défauts**, dont cinq faussent
> des résultats. Ils forment **P5a**, qui s'intercale ici et bloque le tag. La
> leçon n'est pas « la checklist était mal faite » : c'est qu'une checklist ne
> vaut que ce que vaut la **forme** des données sur lesquelles on la coche.
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
- [x] **P5a — dette révélée par l'usage réel ✅** : 12 items fusionnés (#127→#133, #135→#139) ; l'item 13 — la déduplication entre vues — **fermé sur sa mesure** : 3,7 % réels contre 38 % annoncés, pour une complexité ajoutée au runner. Les cinq défauts qui faussaient des résultats sont corrigés. **Le blocage du tag est levé.**
- [ ] **P5c — joignabilité** : toute route déclarée est atteignable depuis la page, ou le dit. Né d'un audit des 31 routes — trois d'entre elles, celles des **recettes**, ont zéro appel dans le front alors que le garde-fou de parité les donne vertes. Ferme la classe (troisième clause du garde-fou), puis les cas : recettes branchées, `params` ouverts, porte « spec complète » tranchée, `standardize_corpus` doté d'une face, composeur contraint. **Ne bloque pas le tag ; passe avant P5b**, qui est suspendue à un arbitrage.
- [ ] **P5b — persistance et calcul à la demande** : garder ce qu'un run a produit (**fait**, `RunManifest.artifacts_dir`), puis calculer une analyse au clic dans la saveur servie. Né de #139. **Ne bloque pas le tag** — et reste **suspendue** tant que l'arbitrage manifeste-porte-les-documents ⇄ serveur-retient-la-spec n'est pas rendu.
- [ ] **Tag `v1.0.0`** — *à poser par le mainteneur, quand il le décide*. Le blocage posé par P5a est **levé** : les défauts qui produisaient de faux classements sont corrigés et fusionnés. Un tag posé le 2026-09-10 l'a été **sans son accord** et a été supprimé (D-232) : le dépôt ne porte aucun tag, la version reste le repli `setuptools_scm`. Le reste de la checklist étant vert, la 1.0 est **prête techniquement** — publier reste une décision, pas une étape.
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
