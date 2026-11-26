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
| **P5d — Installable et sûr** | `pip install cinoc` fonctionne nu (aujourd'hui il plante) · aucun secret dans un rapport · ce que la page propose, le planificateur l'accepte · paquet publiable. | — | correctif |
| **P5e — Une mesure qui dit vrai** | statut de chaque unité (tronquée, en échec) visible et compté · statistiques correctes · normalisation par défaut · chaque métrique porte un nom qui ne promet pas plus qu'elle ne mesure. | P5d | correctif |
| **P5f — Une inférence tracée** | mêmes réglages pour tous les fournisseurs, écrits au manifeste · modèle servi et réponses natives conservés · endpoint par instance (vLLM/SGLang) · délais finis. | P5d | correctif + enveloppe |
| **P5g — Par soustraction** | un seul constructeur de pipeline et une seule politique de vues (absorbe P5c items 2-4, 6, 8) · listes parallèles dérivées du registre · code et docs sans consommateur retirés. | P5e, P5f | soustraction |
| **P5h — La preuve** | une campagne de référence publiée, rejouable, recoupée par un oracle externe ; ses défauts deviennent des correctifs, jamais des features. | P5g | validation |
| **P5i — Vitrine et release** | README court, parcours de deux minutes, résultat réel en tête · testeurs extérieurs · tag `v1.0.0` posé par le mainteneur. | P5h | — |
| **P5 — Release 1.0 + gel Picarones** | checklist · tag · README/CHANGELOG · gel. **Exécutée par P5i** (route ci-dessous, audit du 2026-11-25) ; P5b et P5c items 5 et 7 sortent du chemin de la 1.0. | P5d→P5h | — |

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

### Ce que la conception a changé à cet enchaînement

La première rédaction de cette phase mettait le câblage en tête et le composeur
en queue, et portait un item « les recettes manquantes » justifié par une
affirmation **fausse** : les recettes livrées décriraient mal la presse
ancienne. Elles la décrivent très bien — `presse_ancienne.yaml` porte
préprocessing, segmentation, reconnaissance par région, ordre de lecture et
projection, avec ses paramètres. L'erreur vient de n'avoir pas lu leur contenu.
Cet item est **retiré**.

La conception ([`PLAN_UI_COMPOSEUR.md`](PLAN_UI_COMPOSEUR.md)) a trouvé la cause
sous le symptôme : **deux constructeurs de pipeline qui ne se connaissent pas**.
`run_planning.py` (757 lignes, budget 760) assemble les étapes à la main pour la
page web seule ; `recipes.py` les déduit d'une table de rôles typés, pour la CLI
seule. Aucun des deux n'importe l'autre. C'est la *liste parallèle* que le
projet combat ailleurs, et l'un des deux est à trois lignes de son plafond —
donc chaque champ réclamé (`dpi`, `psm`) aggrave un fichier saturé pendant qu'à
côté un mécanisme typé rend le même service pour rien.

La colonne vertébrale de P5c est donc **la convergence vers un seul
constructeur**, et l'ordre en découle.

### L'enchaînement, dans l'ordre de fusion

| # | Contenu | Dépend de |
|---|---|---|
| **1** ✅ | **La troisième clause du garde-fou de parité.** Toute route `/api/*` est soit appelée par le front, soit déclarée `front-absent: <raison>`, soit une `dette:<id>` avec son échéance — la forme exacte des deux clauses existantes. Écrite **en premier** parce qu'elle transforme le reste de la phase en CI rouge plutôt qu'en bonnes intentions : les trois routes de recette rougissent aussitôt et s'inscrivent en dettes datées. **Livrée** : table `FRONT`, quatre formes (`vue` · `page:<fichier>` · `front-absent: <raison>` · `dette:<id>`), quatre tests. **Une déclaration, pas une détection** — lire le front pour prouver l'appel a été tenté : trois règles écrites et mesurées sur les trente-deux routes, trois échecs (URL concaténées, `href` fabriqués en f-string côté serveur, segments trop communs). La forme fiable est celle des deux clauses qui marchent : une table, dont le pouvoir est d'exiger une décision au moment où la route est ajoutée. | — |
| **2** | **Les deux rôles manquants.** Les adapters LLM déclarent quatre modes ; `roles()` n'en câble que deux (`text_only` → `correction`, `refine` → `refine`). Il n'existe **aucun rôle** pour `zero_shot` (le modèle lit l'image) ni pour `text_and_image`. Une recette ne peut donc pas décrire le zero-shot, l'un des pipelines phares du produit. Deux entrées dans une table — mais un préalable à toute convergence, pas un détail de fin de phase. | 1 |
| **3** | **La déclaration des paramètres au contrat de module.** Aucun module ne dit ce qu'il accepte : `params` est un dict non typé, donc un formulaire ne peut ni se générer ni valider, et une faute de frappe est **avalée en silence**. Même motif que D-251, qui a ajouté `LABELS` parce qu'une table `psm_by_class` était ignorée sans un mot. Décision d'**enveloppe** (axe 1), et les modules tiers l'obtiennent gratuitement — un segmenteur branché qui déclare ses paramètres reçoit son formulaire sans qu'on touche à cinoc. | 1 |
| **4** | **Couche 1 — le catalogue de recettes branché à la file.** `GET /api/recipes` peuple des cartes (titre et description sont dans les YAML, déjà bilingues) ; une forme choisie déplie ses étapes, une brique par étape prise dans `Role.briques` ; « ajouter à la file » appelle `POST /api/runs/recipe`. Le lanceur, le suivi SSE et l'affichage du rapport existent déjà. **Cinq formes deviennent atteignables sans une ligne de pipeline nouvelle.** Ferme deux des trois dettes de l'item 1. | 2 |
| **5** | **Couche 2 — le pli « réglages ».** Généré depuis la déclaration de l'item 3, un pli par étape. `--dpi 300` cesse d'être réservé au terminal — le contournement du défaut de page blanche devient accessible à qui n'ouvre pas de shell. Côté HTTP, `RecipeRequest` accepte enfin `params` ; `plan_from_recipe` les attendait déjà. | 3, 4 |
| **6** | **La bascule — un seul constructeur.** Les quatre onglets de mode deviennent quatre recettes ; `_pipeline_for_competitor` et `_hybrid_competitor` meurent. Le garde-fou n° 1 du projet interdit de garder deux chemins « le temps de migrer » : les deux coexistent aujourd'hui par accident, les laisser coexister par décision serait la faute qu'il nomme. Six acquis du formulaire actuel sont à préserver explicitement, listés au §7 de la conception — dont un secret (le jeton de segmenteur distant) qui ne doit **jamais** entrer dans une recette enregistrable. | 5 |
| **7** | **Couche 3 — le composeur contraint.** À partir des types déjà produits, les rôles proposables sont ceux dont les `entrees` y sont contenues : une fonction de cinq lignes sur `roles()`. Une liste d'étapes et un menu **qui ne contient pas le mauvais choix** — pas un canevas de nœuds, où l'on découvre l'erreur après l'avoir faite. Sortie : `[ enregistrer comme recette ]` → un YAML validé comme les autres, qui rejoint le catalogue de la couche 1. | 6 |
| **8** | **Les indépendants.** `standardize_corpus` reçoit une face (commande, et son pendant web que la clause de parité imposera) ou sort du produit ; la porte « spec complète » (`POST /api/runs/spec`) reçoit une zone de dépôt ou s'inscrit `front-absent` motivée ; et un **bouton d'arrêt** sur le suivi de run — `POST /api/runs/{job_id}/cancel` est servie et n'est appelée par personne, si bien qu'un banc lancé depuis le web ne peut pas être interrompu. Ferme `spec-web` et `annulation-web`. | 1 |

**Le garde-fou s'est justifié à sa première exécution.** En déclarant les trente-deux
routes une par une, il a trouvé une **quatrième** route injoignable que l'audit de D-257
avait manquée : `POST /api/runs/{job_id}/cancel`. La page lance un banc et n'offre aucun
moyen de l'arrêter — plus gênant à l'usage que les recettes, puisqu'un banc de trente
unités engage des appels facturés. C'est exactement ce qu'on attend d'un contrôle
mécanique : trouver ce que la lecture attentive a laissé passer.

> **Conception détaillée** : [`PLAN_UI_COMPOSEUR.md`](PLAN_UI_COMPOSEUR.md) —
> les trois couches, leurs maquettes, l'arbitrage sur la déclaration des
> paramètres, ce que la bascule doit préserver, et trois réserves consignées.

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

Aucune brique de pipeline, aucun moteur, aucune métrique, aucune section de
rapport. Les surfaces nouvelles — le catalogue, le pli de réglages, le
composeur — **n'ajoutent aucune capacité** : elles rendent atteignable ce que
les rôles portent déjà. Deux rôles, une déclaration au contrat, du câblage, un
garde-fou, et un constructeur retiré.

### Ce que l'audit a corrigé au passage

Deux endroits affirmaient que la post-correction structurée n'a pas de surface
web : `CLAUDE.md` §0 et la ligne « couche 8 » du roll-up. C'est faux depuis
D-229 — le bouton `correct-launch` existe, `benchmark.js` appelle
`/api/runs/correction`, et la checklist de ce plan le coche. Les deux sont
réconciliés dans le même commit que cette phase. La leçon rejoint celle de la
checklist « 1.0 prête » : un statut recopié pourrit, et celui-ci a pourri dans
le sens rassurant — il annonçait un manque là où il y avait une livraison.

---

## Étape 4quinquies / **P5d → P5i** — La route vers une 1.0 publiable

> **État consolidé au 2026-11-25** (D-260 → D-266). Cette section **remplace** la
> fin de l'ancienne route (P5b, P5c, P5) ; elle n'ajoute pas un plan à côté. Elle
> est née de trois audits du même jour, menés sur le **produit** et non sur la CI —
> installation dans un venv vierge, métriques confrontées à jiwer et dinglehopper,
> sorties confrontées aux XSD officiels, bibliothèques candidates mesurées une à
> une (`docs/ANALYSE_SUBSTITUTION.md`). La checklist « 1.0 prête » plus bas était
> verte ; elle avait été cochée sur la CI.
>
> **Règles de la route.** Rien de neuf n'y entre hors de ce que liste chaque phase ;
> un défaut trouvé en route devient un correctif, jamais une feature. Critère de
> sortie de toute session : **le parcours utilisateur qu'elle touche fonctionne sur
> le paquet installé**, et le défaut qu'elle ferme est reproduit par un test rouge
> avant le correctif. Un résultat de référence se calcule contre un **oracle
> externe** (scipy, jiwer, dinglehopper, XSD officiels), jamais contre Picarones
> (D-265).
>
> Marqueurs : **[connu]** = déjà écrit dans un `.md` du dépôt (cité) · **[audit]** =
> trouvé le 2026-11-25. Une session = une tranche (`CLAUDE.md` §9).

**Déjà livré sur cette route** : installation nue réparée et gardée par le job CI
`install-bare` (D-262) · aucun secret dans un rapport (D-262) · segmenteur distant
épinglé à l'IP validée et authentification limitée à l'origine (D-263) ·
`saknussemm==0.9.0` depuis PyPI (A1, D-261) · glossaire aligné sur le calcul pour
six métriques, README honnête sur le déterminisme, tarif Mistral OCR corrigé
(D-260) · la parité avec Picarones n'est plus un critère (D-265) · ce que la page propose se planifie, hôte ollama sur liste blanche (D-269) · paquet publiable : sdist 4,15 Mo, wheel sans `.md`, `cinoc --version`, `twine check` en CI (D-270) · ALTO écrits conformes au XSD officiel 4.4, vérifié en test (D-272) · PAGE écrits conformes au XSD officiel 2019, mots PAGE lus, identifiants du fan-out conformes (D-273) · IIIF importé en pleine résolution par le service d'images, téléchargement réservé aux images (D-274). **P5d est livrée.**

### Arbitrages à rendre (mainteneur) — chacun avant la session qui en dépend

| # | Question | Recommandation | Nécessaire avant |
|---|---|---|---|
| ~~A3~~ | ~~Politique d'échec~~ — **rendu (D-271)** : exclue de la moyenne **et** affichée (n notés / n attendus à côté de chaque agrégat) ; option « échec = erreur maximale ». | — | S5 |
| ~~A9~~ | ~~Validation XSD~~ — **rendu (D-271)** : oui, les ALTO et PAGE **écrits** par Cinoc sont validés contre les XSD officiels dans les tests ; l'entrée reste tolérante, aucune validation à l'exécution. | — | S2 |
| ~~A2~~ | ~~Normalisation par défaut~~ — **rendu (D-271)** : NFC + retrait des invisibles par défaut ; la comparaison brute reste une vue explicite. | — | S13 |
| ~~A6~~ | ~~Campagne~~ — **rendu (D-271)** : Tesseract + un petit VLM **local** via Ollama (Qwen2.5-VL 3B par défaut, repli SmolVLM/Moondream) tant que la clé Mistral n'est pas fournie ; Mistral ensuite, **plafond 10 €** pour pilote et campagne réunis, estimation montrée avant tout appel facturé. | — | S10, S30 |
| A4 | **Images du dépôt** (`corpus/`, 43 Mo, scans BnF et BNL) : redistribuables ? | Hors du paquet dans tous les cas (S1) ; vers un dataset HF si les droits le permettent, sinon hors de l'arbre public (S29). | S1, S29 |
| A5 | **Branche `claude/lucid-dirac-0s4p8r`** : seule à porter du code absent de `main` (`block_chain.py`, OCR → LLM par bloc), sans décision d'abandon trouvée. | Supprimer : couvert par la correction structurée. | S29 |
| A8 | **Pré-version.** | `v1.0.0rc1` sur GitHub seulement (pas PyPI), à la sortie de P5g, pour les testeurs ; aucun autre tag avant `v1.0.0`. | après S29 |
| A7 | **Testeurs extérieurs** : qui, combien. | Deux ou trois personnes d'institution patrimoniale, une par parcours. | S34 |
| ~~A1~~ | ~~Canal de publication~~ — **rendu** : `saknussemm` 0.9.0 sur PyPI (D-261). | — | — |

### Feuille de route, session par session

L'ordre suit une règle : **tout ce qui change un chiffre affiché passe avant la
campagne**, qui ne doit tourner qu'une fois ; et les changements d'enveloppe
(statut d'unité, sorties par étape, archive) passent avant ceux qui s'en servent.
Les numéros d'items renvoient aux tableaux de phase plus bas, qui portent le
détail et les preuves. **★** = indispensable à la 1.0 ; **◇** = peut glisser
après la 1.0 si le temps manque (voir « Ligne de coupe »).

**Bloc 1 — Finir P5d : installable, sûr, conforme**

| Session | Contenu | Sortie vérifiable | |
|---|---|---|---|
| S1 ✅ | P5d 4 (ce que la page propose se planifie ; `host` ollama sur liste blanche — D-269) · P5d 5 (sdist sans `corpus/`, `design/`, `campaigns/`, `.claude/` ; wheel sans `.md` ; `cinoc --version` — D-270) · P5d 6 (`twine check` — D-270) · ~~`pricing.json` revérifié~~ **fait** (D-267 : toutes les entrées aux sources primaires, `valid_until` 2027-05-25) | sdist < 5 Mo ✅ (4,15 Mo) ; `twine check` vert ✅ ; chaque option du `<select>` se planifie ✅ | ★ |
| S2 ✅ | P5d 7a — XSD ALTO 4.4 vendorisés, test sur toute sortie d'écrivain ; écrivain ALTO conforme (`PHYSICAL_IMG_NR`, `Page@ID`, pas de `TextBlock@TYPE` en v4, unité de mesure conservée) — D-272 | 21/21 ALTO écrits valides ✅ — mesuré plus large : **90/90** (45 ALTO du dépôt × `write_alto` et assembleur ; rouge prouvé à 90/90 invalides) | ★ |
| S3 ✅ | P5d 7b — XSD PAGE 2019 vendorisé, test sur toute sortie d'écrivain ; écrivain PAGE conforme (`Metadata` à date fixe, dimensions, types de région énumérés ou `structure {type:…;}`, ImageRegion/SeparatorRegion écrites comme telles, sous-régions avant les lignes, identifiants dérivés, géométrie inconnue marquée, layout hors pixels refusé) ; lecture des `<Word>` PAGE ; contrôle d'ID d'`alto_source` sous ComposedBlock ; identifiants de ligne du fan-out en `NCName` — D-273 | 11/11 PAGE écrits valides ✅ (+ 38 ALTO `mm10` refusés au lieu d'être écrits faux ; rouge prouvé à 49/49 invalides) ; mots PAGE conservés en aller-retour ✅ (161 et 258 mots sur les deux pages OCR-D) | ★ |
| S4 ✅ | P5d 7c — IIIF : le service d'images d'abord, requête « image entière » selon la version de l'Image API qu'il déclare (`full/max` en 3, `full/full` en 2, `native` en 1) ; l'URL directe seulement sans service, jamais un `info.json` ; téléchargement réservé aux images (octets magiques JPEG, PNG, TIFF, JPEG 2000, GIF, WebP vérifiés avant toute écriture, `NotAnImageError`), pour l'import **et** la matérialisation des images distantes au run — D-274 | les manifestes Bodleian et Wellcome en cassette donnent de vraies images pleine résolution ✅ (Bodleian 2644×4000 et 2620×4000 au lieu de leur `info.json` ; Wellcome v3 **et v2** 2569×3543 et 2411×3372 au lieu de vignettes 743×1024 et 732×1024 ; rouge prouvé : 4/4) | ★ |

**Bloc 2 — Garder ce qu'on observe (enveloppe)**

| Session | Contenu | Sortie vérifiable | |
|---|---|---|---|
| S5 ✅ | P5e 1 — issue de chaque unité produite par l'exécution (`DocumentExecution` : `ok` · `truncated` · `failed` + motif `engine` · `infrastructure` · `unsupported` · `cancelled`), transportée par `DocumentUsage` — une ligne par unité, échecs compris (`RunResult` v3) ; « n notés / n attendus » (`MetricScore.expected`) à l'écran, au CSV et au JSON ; « Unités en échec » et leur motif au rapport ; `failure_policy: exclude \| max_error` (A3) — D-275 | le contre-exemple pero affiche 4/5 et son motif ✅ (HTML FR/EN, JSON, CSV ; `max_error` : 5/5, CER 0,1667 = celui d'une page rendue vide ; rouge prouvé : 21 tests + 1 module à l'import) | ★ |
| S6 ✅ | P5e 1b — `DocumentExecution` rend `by_step` (entrées initiales sous `__initial__`) et `step_usage` ; pool et consommation totale s'en déduisent (`latest_by_type`) ; `EvaluationView.target_step` (défaut : l'étape la plus aval qui produit un type candidat), refusée au chargement si un pipeline du run ne la connaît pas ; précédence par type retirée, une étape visée qui déclare deux types candidats est refusée ; cache de reprise au format 2 (par étape), format 1 invalidé — D-276 | un pipeline à deux étapes de même type note les deux ✅ (`ocr1 → ocr2` sur une copie d'`examples/` : 0,0290 et 0,0145 dans le même run, égaux à tesseract et pero seuls ; sorties d'`examples/` et démo inchangées ; rouge prouvé : 8 tests de bout en bout + 3 d'exécuteur + 2 de runner) | ★ |
| S7 ✅ | P5e 2 + P5f 1 (mêmes adaptateurs) — raison d'arrêt lue et normalisée (`LLMCompletion.stop_reason` : `stop` · `length` · `refusal` · `error` · `unknown`), `length` → unité `truncated` (notée sur sa sortie réelle, signalée au rapport FR/EN, au JSON et au CSV ; fan-out compris), `refusal`/`error` → échec `engine` ; `temperature=0`, `seed=0`, `max_tokens=8192` (`top_p` non transmis) en kwargs de construction, identiques pour OpenAI, Mistral et Ollama, transmis aux API et écrits au manifeste défauts compris — Anthropic n'envoie que `max_tokens` (l'API refuse `temperature`/`top_p` depuis 2026-10-21, pas de `seed` : refusés à la construction, `None` au manifeste) ; `num_ctx`/`num_predict` pour Ollama ; correction structurée : troncature = erreur permanente, jamais rejouée ; cache de reprise : l'unité tronquée relue tronquée — D-277 | cassette `max_tokens` atteint → `truncated`, par fournisseur ✅ (4/4 ; `cinoc run` contre un faux serveur ollama : folio_002 coupé à `num_predict` → `truncated`, CER 0,5217 noté, 5/5 ; rouge prouvé : 22 tests de raison d'arrêt, dont les 4 de bout en bout « ok » au lieu de « truncated », 30 de réglages, 5 de correction structurée, 3 d'exécuteur, fan-out et reprise) | ★ |
| S8 ✅ | P5f 3 — sidecar `NATIVE_JSON` (réponse native brute, JSON canonique à clés triées, sans clé ni en-tête ni URL) pour les sept moteurs distants (Mistral OCR, Azure DI — corps de la sonde terminale —, Google Vision, OpenAI, Anthropic, Mistral, Ollama) et la correction structurée (`{"responses": [...]}`, ordre d'appel) ; fan-out : `{"regions": [...]}` ; les conversions `_completion_from_*` et extracteurs lisent le **corps** (dump du modèle du SDK, `sdk_native`), donc la relecture du sidecar est le chemin d'exécution ; traverse `by_step`, les puits et le cache de reprise (format 2 inchangé) ; jamais candidat (refusé par `EvaluationView`), hors `RunResult`, vit dans `artifacts_dir` (`--resume-dir`) — D-278 | un run cloud rejoué hors ligne donne les mêmes métriques ✅ (8 pipelines × 2 pages sur cassette, run 2 sans réseau ni SDK depuis les seuls sidecars, par les fonctions des adaptateurs : scores, agrégats et tests inter-moteurs identiques, pages coupées comprises ; secrets absents des sidecars, de l'archive et du `RunResult`, prouvé par fournisseur et sous les vrais SDK openai 3.59, anthropic 2.14, mistralai 1.12.4 ; rouge prouvé : 28 tests + 5 erreurs) | ★ |
| S9 ✅ | P5f 2 + 2b — modèle **servi** lu dans chaque réponse (`response.model`, OpenAI, Anthropic, Mistral, Ollama, Mistral OCR, correction structurée) → `RunManifest.served_models`, tarification indexée dessus ; `dependencies_lock` rempli depuis les `Requires-Dist` installés de `cinoc` ; `unicode_version` ; **une seule empreinte** (`pipeline.fingerprint.step_fingerprint` : étape + version du module + réglages effectifs — modèle, prompt, défauts, endpoint lu dans l'environnement — + binaires) = `parameters_hash` de provenance, dont dérive la clé d'unité (plus de `code_version`) ; cache **format 3** = archive (unités en échec comprises, retentées en reprise normale, binaires de l'archive) ; `cinoc run --resume-dir <archive> --offline` ; une archive par job web (`<data_dir>/archives/<job>`) ; `RunResult` v4 — D-279 | une archive se re-note après une montée de version de métrique, sans réseau ✅ (cassettes OpenAI + Mistral OCR + OCR local factice à binaire : `code_version` 1.0 → 1.0.1 et deux métriques ajoutées, réseau et SDK coupés, module de pipeline qui lève s'il est appelé → 78 scores par document identiques (3 pipelines × 2 pages × 13 métriques), 12 nouveaux calculés, issue `truncated` conservée ; module relevé, binaire changé ou `OPENAI_BASE_URL` posé → unité invalidée, ré-exécutée ou refusée hors ligne ; `cinoc` installé sur une copie d'`examples/` : 50 scores identiques hors ligne, code 1 et unité nommée quand une unité manque ; rouge prouvé sur l'ancien code : 13/13 du critère, 13 échecs et 4 modules en erreur d'import ailleurs — réglages, fan-out, rapport, modèle servi, reprise) | ★ |
| S9b ✅ | Correctif de S9 — (1) une sortie pré-calculée corrigée n'est plus resservie : hook facultatif `unit_inputs(document)` (`precomputed`, `precomputed_layout`, `precomputed_region`, `alto_source` + son sidecar OCR), contenu haché dans la clé d'unité, « absent » s'il manque ; (2) un instantané daté absent de la table (`gpt-4o-mini-2024-07-18`) prend le tarif de l'alias demandé, et le rapport le dit — D-280 | réécrire `<stem>.<label>.txt` sous la même image → la reprise réexécute et le CER change, refus nommé hors ligne ; un `precomputed` inchangé reste servi ✅ ; `gpt-4o-mini` demandé et `gpt-4o-mini-2024-07-18` servi → tarif de l'alias signalé, `gpt-4o` demandé → inconnu ✅ (rouge prouvé sur le code de S9) | |
| S10 ✅ | **Pilote** (P5h) — 10 pages de `37-GT-BNL`, Tesseract + un moteur cloud, plafond bas (A6). Les défauts trouvés s'inscrivent dans les sessions suivantes, pas à côté. **Fait en local** (A6 : Tesseract `fra+deu+ltz` et `Fraktur+fra`, `qwen2.5vl:3b` via Ollama en zero-shot, Tesseract → même modèle en correction ; aucun appel facturé) — D-281, `campaigns/2026-11-26-pilote-local/` | liste des défauts du pilote, chacun rattaché à une session ✅ (24 constats D1-D24, 40/40 unités `ok` dans le run retenu, re-notation `--offline` identique ; CER `texte` 0,1038 · 0,0915 · 0,0530 · 0,1110 — non citables) | ★ |
| S10b ✅ | **Correctifs du pilote** (D-281) qu'aucune session ne couvrait — **ouverte juste après S10, avant S11** (D1 fait perdre des pages à un `cinoc run` au défaut : correction prioritaire) : (D1) Tesseract en parallèle perd 19/20 pages par sursouscription OpenMP → `OMP_THREAD_LIMIT=1` dans l'environnement du binaire (avancé de S28) ; (D2) un run à unités en échec sort en code 0 sans bilan → bilan « n unités en échec / N » en fin de `cinoc run`, code de sortie à trancher ; (D4) `RunResult` déterministe octet pour octet — `candidate_types` (et `tags`), `frozenset`, sérialisés triés ; (D5) aucun chemin absolu local dans le `RunResult` ni les messages d'échec (`image_ref`, `artifacts_dir`) ; (D12) « Paramètres — » de la fiche moteur rempli ou retiré ; (D21) `corpus import` : message juste sur les chemins relatifs, identifiants toujours entre guillemets | D1 : `cinoc run` au défaut sur 10 pages BNL, 4 cœurs → 20/20 `ok` ; D4 : deux runs de la même spec → JSON identiques hors horodatage (rouge prouvé d'abord) — **fait (D-282)** : sur le corpus du pilote, `cinoc run` au défaut (4 workers, 4 cœurs, sans `OMP_THREAD_LIMIT` dans l'environnement) → **20/20 `ok` en 19 s** (contre 19/20 `failed`) ; deux runs de la même spec à deux types candidats sous `PYTHONHASHSEED` 0 et 3, et la re-notation `--offline` → JSON identiques hors horloge (rouge prouvé : `test_run_determinism` et `test_set_fields_serialize_sorted_whatever_the_hash_seed` échouaient sans le tri) ; aucun chemin absolu dans le `RunResult` ni le rapport ; bilan + code **3** quand une unité échoue (« Bilan : 2 unité(s) en échec / 20 (moteur : 2) ») | ★ (D1, D4, D5) |

**Bloc 3 — Une mesure qui dit vrai (P5e)**

| Session | Contenu | Sortie vérifiable | |
|---|---|---|---|
| S11 ✅ | P5e 3, 4, 6 — libellé Friedman ; inférence toujours calculée ; Nemenyi et rangs par scipy (corrige k ≥ 30 et α ≠ 0,01) ; barres CD chevauchantes ; post-hoc conditionné à Friedman ; Holm — **pilote (D-281, D7)** : « Wilcoxon p = 0,2319 » affiché à trois pipelines, « p = 0,0572 » à quatre, sept verdicts sans correction | verdicts identiques à scipy sur 5 000 tirages ; sur BNL, une paire significative affichée là où il y en a une — **fait (D-283)** : 5 005 tests seedés (k = 2 à 8, et 30 à 50 pour un dixième ; n = 4 à 40 ; ex æquo, absents ; α ∈ {0,01 ; 0,05 ; 0,10} ; familles de 1 à 8) — test nommé, p, verdict de Holm (forme descendante) et 19 727 paires Nemenyi (forme p-value, `studentized_range.sf`) identiques à scipy, ~12 s ; pilote re-noté `--offline` : « Friedman : p = 0,2319 » (3 pipelines) et « 0,0572 » (4), corrigées de Holm sur 7 tests (0,8751 ; 0,3430) — **aucune paire significative avec 10 documents**, et le rapport le dit (la p brute 0,0234 de `sans_cesure` aurait été un « significatif » ; corrigée, 0,1637) ; sur `bnl_mini` (30 documents, 5 moteurs, CI) le MER affiche la **seule** paire séparée (`easyocr – fra`) là où les groupes disjoints en impliquaient quatre | ★ |
| S12 ✅ | P5e 5 + bootstrap numpy (P5g 6, D-265) — IC du ratio micro, golden recalculé contre scipy ; **pilote (D-281, D6)** : la méthodologie annonce « macro-moyennes par document, sauf mention micro » alors que l'agrégat affiché est micro (0,1038 contre 0,1068 de moyenne des pages) et ne le dit pas — libellé aligné sur le calcul | le point affiché est dans son IC — **fait (D-284)** : corpus construit très déséquilibré (un document de 2 000 caractères à CER 0,01, neuf de 10 à 0,5) — CER affiché 0,0311, ancien IC [0,353 ; 0,500] (celui de la moyenne 0,451) **qui l'excluait**, rouge prouvé d'abord ; IC du ratio micro [0,0157 ; 0,5000], égal à `scipy.stats.bootstrap` (apparié, percentile, même graine, mêmes lots) à 1e-12 près ; sur 1 000 corpus tirés (poids log-normaux, un document dominant une fois sur trois), point dans son IC 1 000 fois, l'ancien IC l'excluait 340 fois ; **pilote re-noté `--offline`** (1,9 s, aucun appel) : 28 IC, 28 points dedans, agrégats inchangés à l'octet, JSON identiques d'un run à l'autre et entre Python 3.11 et 3.13 — CER `texte` de `tesseract_fra_deu` 0,1038 [0,0676 ; 0,1504] au lieu de « moyenne 0,1068 [0,0585 ; 0,1627] » ; méthodologie FR/EN : « agrégats micro, Σ erreurs / Σ longueurs de référence » | ★ |
| S13 ✅ | P5e 7 — normalisation par défaut (A2) ; une seule définition du CER dans le rapport ; calibration sur GT normalisée, convention de bornes documentée ; parité étendue (NFC/NFD, bords, NBSP, invisibles) ; **pilote (D-281)** : (D8) le saut de ligne compte comme une erreur face à l'espace — un VLM qui déroule ses lignes perd 23 % de CER à `flat_text` (0,0530 → 0,0406), `’`/`'` pèse aussi (→ 0,0488) : convention par défaut tranchée et dite **avant** la campagne (question E5) ; (D9) la calibration d'un pipeline OCR → LLM affiche l'ECE de son OCR alors que la vue note le texte corrigé | parité jiwer/dinglehopper documentée cas par cas — **fait (D-285)** : `tests/evaluation/test_normalization_parity.py`, dix cas (NFC/NFD, bords, NBSP, tiret conditionnel, espace zéro, `\n` contre espace, espaces multiples, tabulation, apostrophe) × cinq conventions — `texte` (`flat_text`, le défaut), `texte (lignes)` (`keep_line_breaks`), brute (`null`), jiwer 4.0.0 recalculé en CI, dinglehopper 0.11.0 figé et vérifié 10/10 dans un environnement séparé — chaque écart expliqué. (D8) vue sans profil → `flat_text`, seconde vue `texte (lignes)` quand la GT a des lignes, `’`/`'` distincts, convention et comparabilité écrites à côté du chiffre (FR/EN) ; une seule définition du CER (glossaire ; CER de ligne sans normalisation propre) ; calibration sur GT et jetons préparés par la vue, bins documentés ; (D9) confiances de l'étape notée, `step` requis. Pilote re-noté `--offline` (2,3 s) : CER `texte` VLM **0,0406**, `texte (lignes)` 0,0530 ; la chaîne n'affiche plus l'ECE de son OCR | ★ |
| S14 ✅ | P5e 11a — un helper `rapidfuzz` remplace les cinq `difflib` ; `char_confusions` en `editops` ; pires lignes alignées par F15 ; taxonomie `I→l` | les lacunes de la taxonomie cohérentes avec les D du WER — **fait (D-286)** : `evaluation._alignment` (`opcodes`, `alignment`, `aligned_to_reference`, `char_substitutions`) sert taxonomie, hallucinations, confusions, mots manqués, modernisation, pires lignes, distribution par ligne, correction et WER ; `difflib` sort de la couche 3. Chaque édition du WER a une classe et une seule : **lacunes = D − D des fusions/scissions, insertions = I − I des fusions/scissions, total = S + D + I**, vérifié contre `jiwer.process_words` (référence indépendante) sur sept cas construits, 300 tirés au hasard et les 150 couples réels de `bnl_mini` (rouge d'abord : 17 tests sur `difflib`, dont l'article bégayé « le roi le le roi le roi » — 2 lacunes + 3 insertions au lieu d'1 insertion). `bnl_mini` : lacunes **555 → 168** (= 185 D − 17 de fusion), insertions 653 → 266, total 6 826 → 6 401 (= S + D + I) ; confusions **7 018 → 8 424 = S du CER** ; hallucinations 2 → 1 document (la sortie `fra` brouillée n'en est plus). Pilote re-noté `--offline` (3 s, JSON identiques sous `PYTHONHASHSEED` 0 et 3 hors horloge), vue `texte` : lacunes VLM 29 → **28** (= 33 D − 5), les trois autres déjà justes (12, 9, 38) ; `I→l` : +1 `visual` VLM (`1`/`I`) et Tesseract fra+deu (`11`/`IL`) | ★ |
| S15 ✅ | P5e 11b — **reste de S14 (D-286)** : `reports/text_diff.py` (diff surligné du rapport) aligne encore par `difflib` et peut surligner un appariement que le CER n'a pas fait → helper `_alignment` ; vrai ROVER ; ordre de lecture par Breuel ; `linregress` pour la tendance ; `roman.py` strict | WER fusionné indépendant du nom des sources ; cas titre + deux colonnes ordonné — **fait (D-287)** : **ROVER** stdlib (réseau de confusion par alignements successifs, coûts et vote de crowd-kit, ordre d'alignement tiré du seul contenu) — sur `bnl_mini`, dix triplets × 30 pages, fusion et WER identiques sous renommage (l'ancien vote changeait sur 10/10 : WER de 0,2756 à 0,4002 pour `deu`/`easyocr`/`fra`), WER fusionné moyen 0,3411 → **0,3146**, triplets qui battent leur meilleur moteur 5 → **8**/10 ; **Breuel** : titre + deux colonnes → `T G1 G2 D1 D2` (avant `T G1 D1 G2 D2`), filet pleine largeur, parité avec kraken sur 500 pages tirées ; **tendance** par `linregress`, p et « significative / non significative / aucun test à 2 runs » sur `/history` (FR/EN) ; **romains** par la grammaire des chiffres (`IIV`, `IXI`, `VIV`, `XIIX` refusés, additif médiéval gardé) ; **diff surligné** = alignement du CER (S + D et S + I caractères surlignés, 34 des 150 couples `bnl_mini` en excès avant) — plus aucun `difflib` dans `cinoc/`. Chaque défaut rouge prouvé d'abord. | ★ |
| S16 ✅ | P5e 8 — **reste de S15 (D-287)** : la détection des numéraux romains prend des mots (`ci`, `dix`) pour des numéraux — la validation stricte est livrée, la détection en contexte reste ici ; **reste de S12 (D-284)** : la méthodologie dit « un document non produit par un moteur est omis de ses agrégats », faux sous `failure_policy: max_error` — phrase alignée sur la politique du run ; noms honnêtes (`unanchored_trigrams`, limites de `fca`, `searchability` relative, `ner_f1` nom exact, régions fantômes comptées, coût humain « simulation », historique par corpus et profil) | chaque défaut rouge d'abord — **fait (D-288)** : **`unanchored_trigrams`** (ex-`hallucination`, même calcul : valeurs du pilote re-noté `--offline` identiques à l'octet — 0,1550 · 0,1568 · 0,0442 · 0,1278) ; une page dupliquée vaut 0,021 (CER 1,01), dit au glossaire ; zéro alias — un `RunResult` d'avant se relit sous son ancienne clé (le `run_result.json` v4 du pilote se rend, `hallucination` en nom brut, et `compare` ne l'apparie pas au nouveau nom) ; `n_hallucination_heavy` → `n_heavy_insertion` (payload d'avant refusé). **`searchability`** à l'échelle AUTO de Lucene (0/1/2 éditions) : bruit de mots de deux lettres 0,6 → 0 ; `bnl_mini` 0,89-0,95 → 0,80-0,89. **`ner_f1_exact`** : « Montfort » lu « Montfert » 1,0 en `ner_f1`, 0 en exact ; « CoNLL/HIPE » retiré. **`region_cer`** : une région fantôme de 13 caractères sur 14 de référence → 13/14 (avant 0). **`fca`** déclarée limitée (fiche, radar « FCA ») : 0 pour des lignes fusionnées, et 1 − CER sous `flat_text`. **Coût humain** « simulation — hypothèse : 5 s par erreur caractère » (FR/EN). **Historique** par (corpus, profil, pipeline, vue) sur `/history` et `cinoc history` ; base d'avant refusée et dite. **Romains** en contexte : 6 → 0 détections sur la GT des 37 pages BNL (« ci-devant » ×4, « dix- huit », « di- sait »). **Méthodologie** : phrase des unités en échec selon `failure_policy` (FR/EN) | ★ |
| S17 ✅ | P5e 9 — **reste de S16 (D-288)** : `fca` reste au profil `standard` alors que, sous la vue à plat par défaut, elle vaut 1 − CER — garder, retirer ou réserver aux vues qui gardent les lignes ; catégorie et unité déclarées par métrique, fiche au glossaire, classement réservé aux établies, radar réduit ; **pilote (D-281, D11)** : le rapport par défaut ne montre aucune durée (un VLM 25× plus lent que Tesseract ne se lit qu'avec `--analyses`) — durée par page au nombre des colonnes par défaut, ou dit | test : toute métrique a catégorie, unité et fiche cohérentes avec le calcul — **fait (D-289)** : `MetricSpec.category` et `.unit` **requis** (`domain`), déclarés par chacune des 29 métriques : **4 établies** (`cer`, `wer`, `mer`, `cmer` — jiwer, scorer HIPE), 16 adaptées, 9 exploratoires ; `test_metric_cards` : catégorie, unité, fiche FR/EN (définition, mesure, limites, **oracle**) pour chacune, la définition nomme l'unité, et l'unité est ce que compte le **poids** (échantillons comptés à la main). **Tests réservés aux établies** : la famille de Holm du pilote passe de 6 à **4** tests (spec du pilote ; CER Holm 0,0391 → 0,0261) et, au profil `standard` d'avant, de **13 à 5** — le CER y était **non significatif** après Holm (0,0783 : `char_accuracy` et `fca`, deux copies de 1 − CER, triplaient le test) et l'est désormais (0,0261, Nemenyi sépare VLM – correction) ; `bnl_mini` 10 → 6, MER sépare toujours easyocr – fra. **Classement** : Mesures clés = établies seules ; « Comparaison » = table des établies, puis table **Diagnostic** (adaptées ≈, exploratoires ∗, sans tri ni test, FR/EN). **`fca` retirée de tout défaut** (pas réservée à `texte (lignes)` : sous elle, Tesseract 0,8959 contre 1 − CER 0,8963, VLM **0,19** contre 0,947 — redite ou contresens) ; `unanchored_trigrams` et `air` hors de `standard`. **Radar supprimé** : retirés les colinéaires et les exploratoires, il restait 2 axes, sous les 3 qu'il exige. **D11** : **durée par page** aux Mesures clés (VLM 63,5 s, Tesseract 2,6 s) et au CSV (lignes `usage`) ; une archive est dite (« une unité reprise garde la durée de sa première exécution ») — distinguer reprise et mesure reste S20 (D10) | ★ |
| S18 ✅ | P5e 10 — **reste de S15 (D-287)** : parité du ROVER avec crowd-kit (oracle non exécuté en S15) ; job CI oracle : dinglehopper léger (`--no-deps`), paquet `roman` | job opt-in vert — **fait (D-290)** : job CI **`oracle`** (ubuntu, Python 3.13 ; extra `oracle` épinglé à la version exacte + dinglehopper 0.11.0 et ocrd 3.13.3 en `--no-deps`, ~19 Mo au lieu de 370), marqueur `oracle`, `CINOC_REQUIRE_ORACLES=1` (un oracle installé mais inimportable échoue, nommé) ; simulé localement dans un venv vierge : **178 tests exécutés, 0 oracle sauté**. **Golden dinglehopper** sur `bnl_mini` (150 couples, vue `texte (lignes)`) : une chaîne d'écarts, chacun nommé et compté, tombe sur dinglehopper **150/150** au CER comme au WER — CER : espaces multiples d'une ligne (30 couples, presque tous `easyocr` : 0,1696 chez Cinoc contre 0,1964), invisibles (0), `normalize_sbb` (87 : `’` → `'` surtout, puis `⸗`, `—`, `==`), graphèmes (0) ; égalité sans pont sur 49 couples ; WER : invisibles (0), `normalize_sbb` (74), mots UAX #29 sans ponctuation (122) — l'écart moyen 0,058 est une autre définition, pas une erreur. **`roman` 5.2** exécuté : 4 999 formes canoniques à la même valeur (majuscules et minuscules) ; 137 256 chaînes de 1 à 6 lettres — 1 339 acceptées des deux côtés à la même valeur, 87 par Cinoc seul (toutes additives, chacune de la valeur de sa canonique), **0** par `roman` seul ; écarts voulus : additif médiéval, `j` final, `N` (`MMMM` n'en est pas un : `roman` 5.x monte à 4 999). **ROVER** : crowd-kit ne s'importe pas sans pandas, scikit-learn, scipy et nltk → **transcription littérale** de `crowdkit/aggregation/texts/rover.py` (1.4.2) dans le test, vérifiée une fois contre le paquet exécuté (300 fusions `bnl_mini` + 5 000 jeux tirés : 0 écart) ; même entrée (ordre de Cinoc) → même sortie sur les 300 fusions ; écarts : l'ordre des noms (74/300 fusions différentes — le défaut corrigé par D-287) et le bord de table (0 sur `bnl_mini`, 559 sur 5 000 jeux tirés ; seul écart restant, 5 000/5 000 identiques une fois neutralisé). Aucune adaptée ne passe établie (aucun des deux oracles ne couvre `cer_diplo`, `bow_*`, `searchability`, `del_rate`/`ins_rate`) | ★ |

**Bloc 4 — Une inférence de son temps (P5f)**

| Session | Contenu | Sortie vérifiable | |
|---|---|---|---|
| S19 ✅ | P5f 4 — Mistral OCR : markdown retiré du texte noté ; réponse OCR 4.1 projetée en `LAYOUT` depuis le sidecar ; `Region.confidence` ; aucune géométrie inventée | **fait (D-291)** : `formats.text.markdown_to_text` (pure : titres, emphase appariée, puces, citations, code, séparations, images retirés ; texte des liens et numéros de liste gardés ; tableaux une ligne par rangée, cellules séparées d'une espace ; lignes blanches retirées, aucun saut ajouté) lu par `_text_from_response` (`mistral_ocr` 1.2) ; `_mistral_layout.layout_from_response` : un bloc = une région (étiquette, boîte en pixels, `block_type_confidence_score`), texte en lignes **sans géométrie ni id**, coin manquant ou boîte inversée → région sans géométrie, **sans bloc → pas de `LAYOUT`** (un layout de figures seules se lirait comme une segmentation ratée) ; publié en plus par l'adaptateur, relu à l'identique depuis le sidecar ; `Region.confidence` ∈ [0, 1] en `domain`, rempli aussi par `to_canonical_layout` (score de détection, segmenteurs 1.1) ✅ (cassette **construite** d'après mistralai 3.9.0 + doc « Basic OCR », à confirmer sur réponse réelle ; rouge prouvé : 8 échecs, CER de la page 0,2836 → 0 (vue `texte`), 0,3060 → 0 (`texte (lignes)`), `folio_b` de S8 0,2028 → 0,0210 ; contre une VT aux mêmes boîtes `region_detection` 1,0, `region_cer` 0,0, `line_identity_cer` non applicable ; 69 tests ajoutés ; `make check-fast` vert — 3 163 passés, 181 ignorés —, Python 3.11 vert — 3 069 passés, 237 ignorés —, `PYTHONIOENCODING=cp1252` vert — 3 163 passés, 181 ignorés) — **dormant sur un vrai run** : le SDK épinglé 1.x ne demande pas les blocs et les retire au décodage (reste → S22) | ★ (markdown) / ◇ (LAYOUT) |
| S20 ✅ | P5f 5 + 7 — confidences Azure et Google ; délais finis ; une seule couche de retry ; retry des OCR cloud ; tentatives comptées dans le coût ; restes de S19 (score absent) et de S10b (`cinoc correct`) ; pilote D3 et D10 | **fait (D-292)** : `azure_di`/`google_vision` 1.2 publient `CONFIDENCES` lues dans les mots du corps (même forme que Tesseract) et entrent dans la calibration ; chaque moteur distant a un délai fini par défaut — 600 s LLM/VLM (OpenAI, Anthropic, Mistral, Ollama), 120 s OCR (Mistral OCR, Azure, Google), retries compris —, réglable par le `timeout` de la spec (le réglage de Tesseract) ; `call_resilient(deadline=, control=, meter=)` : deadline exigée, créneau acquis dans le temps restant, attente interrompue par l'annulation et jamais au-delà du délai, erreur après la deadline → `DeadlineExceeded` ; retentable = 429/5xx **ou transport** ; SDK sans retry propre (`max_retries=0` OpenAI/Anthropic, `retry_config=None` Mistral) : de 15 tentatives possibles à 5 ; Mistral OCR, Azure (soumission et sonde séparément) et Google enveloppés ; `ResourceUsage.billed_pages` (règle : succès compté, refus HTTP non, connexion refusée non, requête coupée après envoi oui — à confirmer chez chaque fournisseur, aucune source primaire) remplace « une page par document » au coût, fan-out compris ; une unité en échec porte ce qu'elle a fait facturer (`AdapterStepError.billed` → `DocumentExecution.billed`, archivé) ; **D3** : délai d'étape dépassé (pytesseract, outil externe, moteur distant) → `DeadlineExceeded`, motif existant `cancelled` « arrêtée (délai) », aucun motif créé ; **D10** : `DocumentUsage.resumed`, s/page marquée ↺ avec durées mesurées et reprises séparées, économie `n_resumed`, CSV `duration_seconds_first_run` ; `remote_segmenter` 1.2 : score absent → `None` ; `cinoc correct` : bilan et code 3 de `cinoc run` (`interfaces/_run_summary`) ✅ (rouge prouvé : 43 échecs — fan-out compris — + 3 modules en erreur d'import ; pilote re-noté `--offline` en 1,9 s, 40/40 unités reprises, « aucune durée n'est mesurée par ce run », 63,5 ↺ · 2,6 ↺ · 14,7 ↺ · 30,6 ↺ ; D3 rejoué au vrai Tesseract, `timeout: 0.05` : « arrêtée (délai) : 10 », code 3 ; `make check-fast` vert — 3 226 passés, 181 ignorés —, Python 3.11 vert — 3 128 passés, 241 ignorés —, `PYTHONIOENCODING=cp1252` vert — 3 226 passés, 181 ignorés) | ★ |
| S21 ✅ | P5f 6 — endpoint OpenAI-compatible par instance (vLLM, SGLang), liste blanche d'hôtes, sémaphore par hôte, coût « auto-hébergé » | **fait (D-293)** : `openai` prend `base_url` (http(s), ni identifiants, ni *query string*, ni fragment), `api_key_env` (un nom de variable ; `OPENAI_API_KEY` à l'endpoint d'OpenAI, aucune clé par défaut ailleurs — la clé d'OpenAI ne part plus chez un tiers ; nommée et absente → erreur qui la nomme) et `self_hosted` par instance, transmis par le registre ; `OPENAI_BASE_URL` n'est plus lue ; `base_url` au manifeste et dans l'empreinte tel quel (ni secret ni chemin) ; créneau réseau par serveur (`hôte:port`) ; liste blanche de D-269 étendue au `base_url` et renommée `CINOC_MODEL_HOSTS` (`check_model_host`, `check_endpoint_settings`) — mode public : aucune cible ; `api_key_env` refusé par HTTP ; `pricing.json` `endpoints` : hors endpoint du fournisseur, « auto-hébergé » (temps machine, jetons non facturés, FR/EN) si déclaré, sinon « tarif inconnu … @ hôte » — jamais le prix d'OpenAI ✅ (rouge prouvé : 2 modules en erreur d'import + 12 échecs ; **critère** : `cinoc run` sur 2 pages du pilote, même adaptateur, « OpenAI » à l'endpoint officiel servi par `MockTransport` sous le vrai SDK openai 3.59 et **Ollama `/v1` `qwen2.5vl:3b` réel** déclaré auto-hébergé — 4/4 unités, 134,9 s ; clé simulée reçue par `api.openai.com` seul, Ollama `Bearer cinoc-no-key` ; économie « machine+jetons » 0,00049 € et « machine — auto-hébergé : openai/qwen2.5vl:3b » 0,0048 €, aucun « tarif inconnu » ; `make check-fast` vert — 3 272 passés, 181 ignorés —, Python 3.11 vert — 3 174 passés, 241 ignorés —, `PYTHONIOENCODING=cp1252` vert — 3 272 passés, 181 ignorés) | ◇ |
| S22 ✅ | P5f 8 — **restes de S21 (D-293)** : la disponibilité web d'`openai` dépend d'`OPENAI_API_KEY` même pour une instance auto-hébergée (409) — disponibilité par instance ; `ANTHROPIC_BASE_URL` encore lu de l'environnement ; l'adaptateur `ollama` natif sans créneau réseau ne partage pas celui d'une instance `openai` pointée sur le même serveur ; **reste de S19 (D-291)** : sous le SDK `mistralai` relevé (≥ 2), Mistral OCR demande `include_blocks=True` et `confidence_scores_granularity="block"` — le SDK 1.x n'a pas ces paramètres et retire `blocks`/`confidence_scores` de la réponse qu'il décode, si bien que la projection `LAYOUT` de S19 ne reçoit jamais de blocs ; puis confirmer sur une réponse réelle la cassette construite (`content` par type de bloc, coins en pixels de `dimensions`) ; modèles listés en direct chez les quatre fournisseurs (une fonction, web et CLI) ; plus aucun modèle par défaut codé ; vision et dépréciation lues dans l'API ; SDK épinglés par majeure ; jetons de cache et de raisonnement lus ; **pilote (D-281)** : (D17) `cinoc list models ollama` ignore les modèles installés ; (D18) le modèle Ollama est tracé par son **tag** — le digest (`/api/tags`, `/api/show`) au manifeste et dans la clé d'unité ; (D13) `--check` refuse un modèle absent du fournisseur — **S22a fait (D-294)** : SDK épinglés par majeure dans `pyproject.toml` et `deploy/requirements.txt` (`openai>=3,<4`, `anthropic>=2,<3`, `mistralai>=3,<4` — de `<2` ; pas de SDK Ollama : l'adaptateur parle `httpx`) ; Mistral chat et OCR migrés (`from mistralai.client import Mistral`, `retry_config=None` vérifié sans retry sous 3.9, annulation par `__exit__`) ; **Mistral OCR 1.3 demande les blocs** (`include_blocks=True`, `confidence_scores_granularity="block"`) — la projection `LAYOUT` de S19 n'est plus dormante : cassette OCR 4 → vrai SDK 3.9 (`MockTransport`) → sidecar égal au corps, blocs et confiances gardés → `LAYOUT` ; disponibilité web d'`openai` **par instance** (`app.engines.instance_status` : un `base_url` sans `api_key_env` n'exige pas `OPENAI_API_KEY` — plus de 409) ; `ANTHROPIC_BASE_URL` n'est plus lue (endpoint passé explicitement au SDK, avertissement si posée ; `_native.endpoint_from_env` supprimé, sans consommateur) ; `ollama` natif sous `call_resilient` **sans retry**, au créneau de son serveur (`hôte:port`), partagé avec une instance `openai` sur `…:11434/v1` ✅ (`make check-fast` vert — 3 280 passés, 182 ignorés —, Python 3.11 vert — 3 182 passés, 242 ignorés —, `PYTHONIOENCODING=cp1252` vert — 3 280 passés, 182 ignorés ; vrais SDK openai 3.60, anthropic 2.14, mistralai 3.9 : 5/5 ; `pip-audit --strict` vert ; roue sans extra : `--help`, `list engines`, `demo`, `run examples/config.yaml` ✅) — **S22b fait (D-294)** : `app.models.available_models(provider, réglages)` — **une** fonction, en direct, pour `/api/models/{provider}` (composeur : les quatre fournisseurs par la même route, plus de datalist rendue serveur), `cinoc list models [--host]` et `cinoc run --check` ; lecture **pure** du corps par fournisseur (`models_from_listing`/`model_from_tag`, cassettes `tests/fixtures/cassettes/models/`) : OpenAI `id` + `shutdown_date` (vision et cycle de vie **inconnus**), Anthropic `capabilities.image_input`, `lifecycle`, `deprecated_at`, `retires_at`, toutes pages, alias résolu par `models.retrieve`, Mistral `capabilities.vision`/`ocr`, `aliases`, `deprecation`, Ollama `/api/tags` (digest, `capabilities`, sinon `/api/show`) ; liste illisible → raison (clé, SDK, serveur), jamais une liste vide ; **aucun modèle codé** — `_DEFAULT_MODEL` (5 adaptateurs), défauts du registre et `pricing.json` `default_models` (→ `token_kinds`) retirés, `app/models._CANONICAL` supprimé ; spec, concurrent du composeur (`ocr_model` pour l'OCR amont d'une chaîne) ou instance du registre sans `model` refusés avec la liste disponible ; garde-fou `tests/guardrails/test_no_coded_model_names.py` (chaînes de code hors docstrings + données livrées, hors `pricing.json`) ; **D17** `cinoc list models ollama` liste les modèles installés ; **D18** `OllamaAdapter.system_binaries` → `{"ollama:<tag>": digest}` au manifeste et dans la clé d'unité (une archive Ollama antérieure est ré-exécutée une fois — voulu : un autre digest est un autre modèle) ; **D13** `--check` demande chaque modèle en direct, refuse un absent, **note** sans refuser un fournisseur injoignable ✅ (vrai Ollama 0.40.18, `qwen2.5vl:3b`, page `0003` du pilote : `list models ollama` → `qwen2.5vl:3b [vision · digest fb90415cde1e]` ; `--check` vert, modèle absent refusé (code 1, liste citée), spec sans modèle refusée (liste citée), serveur injoignable → « non vérifié », code 0 ; run natif + `/v1` 2/2 unités en 142,7 s, CER 0,0179 et 0,0254, `system_binaries_lock` = `{ollama:qwen2.5vl:3b: fb90415c…}` — l'instance `/v1` n'en a pas —, `--offline` en 1,5 s, scores identiques ; `make check-fast` vert — 3 308 passés, 186 ignorés —, Python 3.11 vert — 3 211 passés, 246 ignorés —, `PYTHONIOENCODING=cp1252` vert — 3 309 passés, 186 ignorés ; vrais SDK (openai 3.60, anthropic 2.14, mistralai 3.9) : 36/36 dont les listes de modèles sous transport factice ; `pip-audit --strict` vert ; roue sans extra : `--help`, `list engines`, `list models`, `demo`, `run examples/config.yaml` ✅) — **S22 fin fait (D-294)** : jetons de cache et de raisonnement lus dans le corps — OpenAI `prompt_tokens_details.cached_tokens`/`.cache_write_tokens`, `completion_tokens_details.reasoning_tokens` ; Anthropic `cache_read_input_tokens` + `cache_creation_input_tokens` **ajoutés** à `input_tokens` (hors cache), `output_tokens_details.thinking_tokens` ; Mistral `prompt_tokens_details.cached_tokens` ; Ollama rien — dans `ResourceUsage` (`tokens_cache_read`, `tokens_cache_write`, `tokens_reasoning` : parties de `tokens_in`/`tokens_out`, `None` = non rendu), archivés et relus à l'identique `--offline` ; coût : lecture en cache au tarif `cache_read_eur_per_mtok` (sourcé pour gpt-4o-mini, gpt-4o, Haiku 4.5, Sonnet 4.6), sinon — ou à toute écriture — « jetons de cache non tarifés » (FR/EN), coût `None` ; raisonnement déjà dans la sortie, jamais recompté ; parties affichées dans les cellules de jetons ✅ (rouge prouvé : 22 échecs ; sur la cassette « cached », coût jetons OpenAI 327,97 → 220,45 µ€ (−33 %, cache payé au tarif plein), Anthropic 278,35 → 440,35 µ€ et entrée 105 → 1 905 jetons (cache ignoré) ; `make check-fast` vert — 3 332 passés, 189 ignorés —, Python 3.11 vert — 3 234 passés, 249 ignorés —, `PYTHONIOENCODING=cp1252` vert — 3 332 passés, 189 ignorés ; vrais SDK (openai 3.60, anthropic 2.14, mistralai 3.9) : 23/23) — **reste, sans session** : confirmer sur une réponse réelle les cassettes construites (Mistral OCR 4 à blocs, listes de modèles, réponses « cached ») dès qu'une clé arrive, et l'inclusion de `cached_tokens` dans `prompt_tokens` chez Mistral | aucun nom de modèle codé hors tarifs ; spec sans modèle refusée avec la liste disponible | ★ |

**Bloc 5 — Par soustraction (P5g)**

| Session | Contenu | Sortie vérifiable | |
|---|---|---|---|
| S23 ✅ | P5g 1a — **restes de S21 (D-293)** : `self_hosted` (réglage d'économie) entre dans l'empreinte et fait réexécuter l'inférence — à sortir de l'empreinte via la déclaration des paramètres ; `base_url` non normalisée (un `/` final change l'empreinte) ; rôles `zero_shot` et `text_and_image` ; déclaration des paramètres au contrat de module ; **pilote (D-281)** : (D14) un réglage inconnu (`tempreature`, `prompt_name`) est accepté par `--check` et ignoré à l'exécution → refusé, nommé ; (D15) `prompt_name` utilisable dans une spec YAML, comme au composeur | **fait (D-295)** : **déclaration des réglages** au contrat de module — `PARAMS: ClassVar[tuple[Param, ...]]` (`pipeline.params` : nom, type, libellés FR/EN, défaut, requis, choix, bornes, `secret`, `affects_output`), facultative (`None` = libre, `()` = aucun réglage), réexportée par `adapters.extension` ; les 31 briques du socle déclarent, et un garde-fou confronte chaque déclaration à son constructeur (noms, défauts) ; le registre l'applique à **chaque** construction (`ModuleRegistry.build`, réécrit 694 → 281 lignes : builders directs `Classe(**réglages)`) — donc à `cinoc run`, `--check` (`check_spec_settings`, qui refuse aussi des réglages qu'aucune étape n'emploie) et au dépôt de spec web (422) ; un module tiers sans déclaration reste libre (API publique : rien à changer), avec déclaration il est contrôlé sur sa classe une fois construit ; **D14** : « réglage inconnu 'tempreature' — vouliez-vous 'temperature' ? », `prompt_name` sur un OCR refusé ; **D15** : `prompt_name` dans `adapter_kwargs` d'une brique LLM/VLM (`prompts.resolve_prompt`, la règle du composeur) ; **restes de S21** : `self_hosted`, `api_key_env`, `timeout` et `prompt_name` hors empreinte (`affects_output=False` → `ModuleIdentity.operational`, au manifeste, jamais hachés), `base_url` sans `/` final ; **rôles** `zero_shot` et `text_and_image` (`Role.mode`), recettes `vlm_seul` et `ocr_puis_vlm` ; `cinoc list engines <brique>` décrit les réglages ✅ (rouge prouvé sur le code d'avant : 13 tests sur 17 de `test_settings_declared` ; empreintes du pilote et de l'exemple inchangées, vérifiées contre leurs valeurs d'avant ; **archives invalidées une fois** : étapes dont la spec posait `timeout`, `self_hosted` ou `api_key_env`, `base_url` à `/` final, et runs du composeur web sur Google, Azure, Mistral OCR, Kraken, PERO, Calamari — qui ne reçoivent plus de `lang` ; `make check-fast` vert — 3 464 passés, 189 ignorés —, Python 3.11 vert — 3 366 passés, 249 ignorés —, `PYTHONIOENCODING=cp1252` vert — 3 464 passés, 189 ignorés — ; mypy sous les vrais SDK : vert ; `--check` : `examples/config.yaml`, le pilote (corpus factice) et sa variante à `prompt_name` valides, variante à `tempreature` refusée) | ★ |
| S24 ✅ | P5g 1b — **restes de S23 (D-295)** : une recette dont une brique n'a pas de libellé (`presse_ancienne` : `tesseract_layout`, `alto_assembler`) ne se construit pas — nom de module `tesseract_layout:seg` ≠ `tesseract_layout` ; `POST /api/runs` (composeur) n'appelle pas `check_spec_settings` avant le lancement (une erreur de construction tombe dans le job, pas en 422) ; la déclaration d'un module tiers ne se lit qu'après construction — à trancher pour le pli de réglages ; `host` d'Ollama non normalisé (`/` final → `//api/chat`) ; catalogue de recettes branché à la page | **fait (D-296)** : dette `recettes-web` fermée — la page lit `GET /api/recipes` (`static/js/recipes.js`, onglet « Recette » du banc) : sept formes FR/EN, une ligne par étape (rôle nommé en clair, brique choisissable, indisponibles grisées avec leur raison, mode public compris, briques CLI absentes, « une fois par bloc détecté » sur le fan-out) et les seuls réglages **requis** de la brique (un modèle) ; l'entrée rejoint **la** file, lancée par `POST /api/runs/recipe` en un run comparé (`entries`, N recettes → N pipelines) ✅ ; **restes de S23** : les sept briques qui se nommaient sans libellé (`tesseract_layout`, `alto_assembler`, `page_assembler`, `alto_source`, trois segmenteurs) acceptent un `label` facultatif — nu, le nom et l'empreinte des specs d'avant ne bougent pas ; un test paramétré construit **toutes** les recettes et les passe à `check_spec_settings` (rouge : `alto_corrige`, `presse_ancienne`) ; `POST /api/runs` refuse en 422 nommé ce qui ne se construit pas (Kraken sans modèle était lancé ; le rejeu `precomputed_region` du composeur ne recevait pas son `source_label` — trouvé par le même contrôle) ; `host` d'Ollama et de Saknussemm normalisé par `validate_endpoint` ; module tiers lu sans construction : **sans consommateur en S24**, renvoyé à la tranche 5 ✅ (`make check-fast` vert — 3 492 passés, 189 ignorés —, Python 3.11 — 3 394 / 249 —, cp1252 vert, mypy sous vrais SDK vert ; navigateur : deux recettes, un run Tesseract réel, rapport servi) | ◇ |
| S25 ✅ | P5g 3 + **pilote (D-281, D24)** — **restes de S24 (D-296)** pris ici : normalisation et profil de métriques ne s'appliquent pas aux recettes (limite affichée par la page) ; la description de `alto_corrige.yaml` porte du markdown affiché tel quel ; **une seule politique de vues** ; la CLI ne compose aucun pipeline — `cinoc list recipes` décrit, rien n'instancie | même pipeline par les trois entrées → mêmes vues — **fait (D-297)** : `app/evaluation_views.plan_evaluation(pipelines, corpus, options)`, appelée par le composeur, les recettes et la correction (et donc par leurs deux transports) — une vue n'est déclarée que si un pipeline produit son candidat **et** que le corpus porte la GT qui le juge ; `texte` sous le profil de métriques choisi (`standard` par défaut, là où recettes et correction notaient `cer, wer`), `structure` et `entites` uniques ; normalisation, caractères exclus et profil de métriques appliqués aux recettes et à la correction (la limite affichée tombe, FR/EN) ✅ ; **D24** : `cinoc run CORPUS --recipe NOM [--brick [N:]étape=brique] [--set [N:]étape.réglage=valeur]` instancie par `plan_recipe_run`, la fonction de la page ✅ ; description d'`alto_corrige` en texte simple ✅ (rouge d'abord : 18 tests sur le code d'avant ; Tesseract réel, deux pages du pilote, CLI et composeur web : mêmes vues, CER `texte` 0,0902 et `texte (lignes)` 0,0914 des deux côtés ; `cinoc compare` CLI ⇄ recette web : 11 lignes sur 11 appariées, écart nul ; `make check-fast` vert — 3 535 passés, 189 ignorés —, Python 3.11 — 3 437 / 249 —, cp1252 vert, mypy sous vrais SDK vert ; `run_planning.py` 775 → 546, `benchmark.js` 790 → 786) | ★ |
| S26 ✅ | P5g 2 — **un seul constructeur** (**livré D-298**) : `run_planning` supprimé, l'hybride de `structure_planning` et `correction_planning` deviennent les recettes `segmentation_puis_lecture` et `alto_corrige` (ce qui reste de l'un est la segmentation seule de l'aperçu, de l'autre le corpus d'ALTO : `alto_corpus`) ; une seule file (`app/recipe_queue.plan_recipe_run`) pour la page, `cinoc run --recipe` (`--with` pour une étape facultative), `cinoc hybrid` et `cinoc correct` ; une seule route de lancement (`POST /api/runs`, `/api/runs/recipe` et `/api/runs/correction` retirées) ; les capacités des quatre onglets et du panneau de correction rendues par la recette (moteurs OCR cloud au rôle `ocr`, tout OCR ou VLM par bloc, étapes facultatives `ner`/`alto`, réglages déclarés au pli, prompts curés, modèles listés en direct, aperçu de segmentation) ; **restes de S24 (D-296)** fermés : recette et concurrent composé dans un même run (le message FR/EN retiré), `benchmark.js` 786 → 407 (sort de la table des budgets), `routers/runs.py` 599 → 386, `run_planning.py` 546 → 0 ; **reste de S25 (D-297)** fermé : **règle de nommage unique** — la recette, puis la brique de chaque étape à choix (et son modèle), puis les étapes facultatives retenues (`ocr_simple · tesseract`, `ocr_simple · kraken (k)`), `#n` pour ce qui reste identique | `_pipeline_for_competitor`, `_hybrid_competitor`, `_hybrid_spec` supprimés ✅ ; un même pipeline porte le même nom par toute entrée ✅ (`cinoc compare` CLI ⇄ page : toutes les lignes appariées) | ✅ |
| S27 ✅ | P5g 4 — **livré D-299** : **un secret ne sort plus** — l'export de configuration passe par le serveur (`POST /api/runs/config`), qui retire tout réglage déclaré `secret` (et les noms de `SECRET_KWARGS`) et le nomme (`withheld_secrets`) ; l'import le redemande dans la file (champ masqué, `aria-invalid`), le lanceur refuse en 422 une entrée dont le secret n'a pas été ressaisi ; un refus de réglage ne recopie plus la valeur d'un secret ; jeton du segmenteur distant absent du `RunResult`, du rapport, de l'état du job, de l'archive et des journaux (vérifié, succès et échec) ; **bouton « Arrêter »** (FR/EN, états lisibles, focus rendu) → `POST /api/runs/{id}/cancel` (`RunControl`, aucun processus tué) ; un run arrêté n'écrit pas de rapport ; une unité qui attendait son créneau réseau n'appelle plus après l'arrêt ; **porte « spec complète »** : zone de dépôt sur la page d'une instance privée, **fermée en mode public** (403) ; YAML d'un client **sans alias** (`formats.safe_load_yaml` : spec déposée et aperçu de normalisation — « billion laughs » de < 1 Ko = minutes de calcul) ; **`cinoc corpus standardize`** (face CLI de `standardize_corpus`, sans pendant web, assumé) ; restes : polices `data:` du rapport servi autorisées sous `/reports/` seulement (9 erreurs console → 0) ; brique de rejeu sans aucun de ses fichiers refusée en 422 (`check_replay_sources`, hook `unit_inputs`) ; 390 px sans défilement horizontal (coquille `minmax(0, 1fr)`, tableaux du rapport défilant dans leur boîte) ; `docs/screenshots/launcher.png` refaite. **Restes → S28** : un appel HTTP **en vol** n'est pas interrompu (`httpx.Client.close()` d'un autre fil ne coupe pas une lecture bloquante — mesuré : Ollama CPU, ~115 s entre « Arrêter » et « Arrêté ») ; vérité `LAYOUT` d'un corpus web à `.gt.txt` + ALTO (la vue `structure` comparerait `alto_corrige` à son propre ALTO) ; `precomputed_layout`/`precomputed_region` offerts sur le web alors qu'un dépôt ZIP n'accepte pas leur JSON (désormais refusés en 422) ; tranche 5 pour les modules tiers | dettes `annulation-web`, `spec-web` fermées ✅ | ★ (arrêt) |
| S28 | P5g 5 + 6 — **reste de S27 (D-299)** : `safe_load_yaml` (sans alias) protège la spec déposée et l'aperçu ; restent sur `yaml.safe_load` les specs locales de la CLI (fichiers de l'utilisateur) et le catalogue HTR-United (`parse_catalogue`, source amont fixe lue par la page d'accueil) — vérifier que le catalogue n'utilise pas d'ancres puis le passer au chargeur durci ; **restes de S27 (D-299)** : interrompre l'appel HTTP en vol à l'arrêt (Ollama en flux `stream: true`, sondage entre morceaux ; SDK cloud : même mesure à faire) ; vérité `LAYOUT` d'un corpus web à `.gt.txt` + ALTO sans auto-comparaison de `alto_corrige` en structure ; retirer de l'offre web les rejeux à JSON (`precomputed_layout`, `precomputed_region`) ou accepter leur JSON au dépôt ; tranche 5 (pli de réglages) pour un module tiers ; listes dérivées du registre ; Tesseract en un appel (2,7-3,9× plus rapide) ; `ocrd_processor` sur METS gabarit ; CSS extrait de `html.py` ; `StrictUndefined` + parité i18n ; shims retirés ; **pilote (D-281)** : `OMP_THREAD_LIMIT=1` avancé en S10b (D1 ; D-282 le pose dans l'environnement du processus, faute de prise dans `pytesseract` — lancer le binaire soi-même permettra de ne le donner qu'à l'enfant) ; (D19) données de langue Tesseract (`*.traineddata`) au manifeste et dans la clé d'unité ; (D13) `--check` refuse une langue non installée ; (D22) `cinoc compare` à décimales localisées et runs A/B discernables à `run_id` égal | — | ★ |
| S29 | P5g 7 + 8 — **reste de S22 (D-294)** : aucun job CI n'installe les SDK fournisseurs (`openai`, `anthropic`, `mistralai`) — mypy et les tests sur vrais SDK ne tournent qu'en local ; trois erreurs de typage et un import cassé (listage Mistral sous 3.x) sont passés ainsi — job CI qui installe les extras et lance mypy + `tests/adapters` ; `adapters/correction/mistral_structured.py` ne lit que `prompt_tokens`/`completion_tokens` (hors `ResourceUsage`) ; **reste de S18 (D-290)** : la parité ROVER/crowd-kit sur les 10 triplets de `bnl_mini` coûte ~90 s CPU dans la suite normale (suite locale 30 s → 75 s) — la réduire ou la marquer `slow` sans la sortir de la CI ; `qe/`, `campaigns/tooling/`, code mort, 29-30 branches (A5) ; garde-fous d'agents allégés ; `CLAUDE.md` corrigé ; images du dépôt (A4). Puis **`v1.0.0rc1`** (A8) | — | ★ |

**Bloc 6 — La preuve (P5h)**

| Session | Contenu | Sortie vérifiable | |
|---|---|---|---|
| S30-S32 | Campagne d'ablation E0-E5 (A6) sur `37-GT-BNL` et Dresden, `--repeat 5` pour les moteurs stochastiques, CER recoupé par dinglehopper ; archive (`RunResult` + sidecars + rapport) sur un dataset HF avec DOI Zenodo ; **pilote (D-281)** : (D23) conventions de la GT BNL déclarées en vues (`ſ` → `s`, `⸗` gardé, `�` dans `0003`) ; (D16) un prompt zero-shot curé pour la presse XIXᵉ, ou le prompt générique déclaré ; (D20) archive sans copie d'image par pipeline (45 Mo pour 10 pages × 4 pipelines) | un tiers re-note l'archive hors ligne et retrouve les chiffres au chiffre près | ★ |

**Bloc 7 — Vitrine et release (P5i)**

| Session | Contenu | Sortie vérifiable | |
|---|---|---|---|
| S33 | P5i 1 + 2 — **reste de S10b (D-282)** : un `RunResult` produit par la CLI puis servi par `cinoc serve --reports-dir` relit ses `image_ref` relatifs contre le dossier des corpus déposés et retombe sur l'aperçu synthétique (les chemins absolus d'avant D5 marchaient sur la même machine) — fixer la racine de relecture d'un rapport baké, parcours testé sur le paquet installé ; README court avec un vrai résultat de S30-S32 ; trois parcours testés sur le paquet installé | une personne extérieure lance un premier rapport en moins de deux minutes | ★ |
| S34 | P5i 3 — testeurs extérieurs sur `rc1` (A7) ; leurs blocages traités comme des défauts | — | ★ |
| S35 | P5i 4 + 5 + 6 — métadonnées du dépôt, `CITATION.cff`, `CHANGELOG [1.0.0]` ; **tag `v1.0.0` posé par le mainteneur** ; Space redéployé ; plans historiques retirés de l'arbre | — | ★ |

### Ligne de coupe

Environ **35 sessions**, hors temps de calcul de la campagne. Si le temps manque,
cinq items marqués **◇** glissent après la 1.0 sans fausser un chiffre : la
projection Mistral OCR 4.1 → `LAYOUT` (le markdown, lui, reste retiré), l'endpoint
par instance (sauf si un GPU est disponible pour la campagne), le catalogue de
recettes dans la page, l'unification des constructeurs (la **politique de vues
unique**, elle, reste dans la 1.0), et le dépôt de spec. Cela ramène la route à
une trentaine de sessions. **Rien de ce qui touche un nombre affiché ne se coupe.**

### Les phases en détail — items, preuves, critères

### P5d — Installable et sûr · S1-S4

| # | Item | Connu ? | Critère de sortie |
|---|---|---|---|
| 1 ✅ | **Installation nue réparée** (D-262). `cinoc --help` plante sur `ModuleNotFoundError: httpcore` (le transport des importeurs est importé par la CLI). `httpx`/`httpcore` en dépendances de base ; les extras `google`, `azure`, `ollama`, qui ne contenaient qu'eux, disparaissent ; retirés aussi de `serve` et `saknussemm`. | [audit] | — |
| 2 ✅ | **Job CI « installation nue »** (D-262, job `install-bare`) : construire le wheel, l'installer dans un venv vierge, lancer depuis un dossier temporaire `cinoc --help`, `cinoc demo`, `cinoc run examples/config.yaml`. C'est l'absence de ce job qui a laissé l'item 1 passer depuis le 16 août. | [audit] | job vert ; rouge prouvé en retirant `httpx` |
| 3 ✅ | **Aucun secret dans un rapport** (D-262 : le manifeste remplace toute valeur de réglage secret par `<secret>` — un seul point de passage, puisque tout ce qui sort d'un run sort du manifeste ; le jeton reste dans `adapter_kwargs` pour authentifier le module). Le jeton du segmenteur distant entrait dans `adapter_kwargs`, donc dans le manifeste, puis s'affichait dans la section composition. | [connu pour les recettes futures, PLAN_UI_COMPOSEUR §7] ; [audit] pour le chemin actuel | test : un run avec jeton → le JSON `RunResult` et le HTML ne contiennent pas sa valeur |
| 4 ✅ | **Ce que la page propose, le planificateur l'accepte** (D-269). `tesseract_layout` et `doclayout_yolo` étaient proposés par le `<select>` puis refusés (422) ; ce sont les deux seuls segmenteurs exécutables sans dépendance lourde. Les constantes `PIPELINE_SEGMENTERS`/`SEGMENTER_KINDS` sont remplacées par `segmenter_kinds()`/`pipeline_segmenters()`, lues sur `segmenter_statuses` — la fonction même qui remplit le `<select>` ; les deux segmenteurs, modules `IMAGE → LAYOUT` du registre, passent par les trois planificateurs (benchmark hybride, transcription hybride, segmentation seule). Le `host` ollama reçu en HTTP est confronté à la liste blanche de l'opérateur (`CINOC_OLLAMA_HOSTS`, défaut `localhost`/`127.0.0.1`, `app/security.check_ollama_host`), par la route de correction **et** par la spec déposée ; refus en 403. | [audit] | test : chaque option proposée par la page se planifie ✅ (rouge prouvé : 3 planificateurs sur 3 refusaient `tesseract_layout`) |
| 4b ✅ | **Deux fuites réseau fermées** (D-263) : le segmenteur distant validait son endpoint puis laissait `httpx` le résoudre à nouveau (DNS rebinding) — il passe par `post_json`, épinglé à l'IP validée, sans redirection ; et un en-tête d'authentification suivait une redirection dès que le **nom d'hôte** coïncidait, donc sur un changement de port ou une rétrogradation https → http — la comparaison porte désormais sur l'origine (schéma, hôte, port). | [audit de substitution] | deux tests, rouges sans le correctif |
| 5 ✅ | **Paquet propre** (D-270). Le sdist pesait 46,6 Mo (44,9 Mo de scans de `corpus/`, plus `design/`, `campaigns/`, `qe/`, `.claude/`) ; le wheel embarquait 15 `.md` internes. `MANIFEST.in` retire `corpus/`, `design/`, `campaigns/`, `qe/`, `deploy/`, `.github/`, `.claude/` ; `exclude-package-data` retire les `.md` du wheel, données du paquet intactes. `cinoc --version` (lit `resolve_code_version`). | [audit] | sdist < 5 Mo ✅ (4,15 Mo) ; wheel sans `.md` ✅ ; gardés par le job `install-bare` |
| 6 ✅ | **Publication** : `twine check --strict` vert (A1 rendu, D-261 ; D-270), désormais exécuté par le job `install-bare`. | [audit] | `twine check dist/*` vert ✅ |
| 7 ✅ | **Ce que Cinoc écrit et importe est conforme** (D-264, preuves : `docs/ANALYSE_SUBSTITUTION.md`). **7a ALTO ✅ (D-272)** : XSD ALTO 4.4 de loc.gov vendorisé octet pour octet (`tests/fixtures/xsd/`), 90/90 sorties valides (`write_alto` + assembleur, 45 ALTO du dépôt) ; `PHYSICAL_IMG_NR` lu/écrit, `Page@ID` et `ID` de bloc dérivés, type de `TextBlock` en `TAGREFS` + `<OtherTag>`, unité portée par `CanonicalLayout.coordinate_unit` ; `write_alto` n'écrit plus que l'ALTO 4. **7b PAGE ✅ (D-273)** : XSD PAGE 2019-07-15 de PRImA vendorisé, 11/11 sorties valides (`write_pagexml` + assembleur, 2 PAGE et 7 ALTO en pixels du dépôt ; les 38 ALTO `mm10` refusés) ; `Metadata` à date fixe, dimensions exigées, types hors énumération en `structure {type:…;}`, régions non textuelles écrites comme telles, géométrie inconnue marquée `coords {absent:true;}` ; `<Word>` lus ; `alto_source` contrôle toute la profondeur ; le fan-out joint ses identifiants par `.` (le `:` les rendait invalides en ALTO comme en PAGE). **7c IIIF ✅ (D-274)** : le service d'images l'emporte sur l'URL directe, en v2 comme en v3 (Wellcome sert une vignette dans les deux), et la requête suit la version de l'Image API déclarée — `full/max` n'existe pas en 1.x ni en 2.0, `full` plus en 3.0 ; un `info.json` n'est jamais pris pour une image ; `download` lit les premiers octets avant d'ouvrir le `.part` et refuse tout ce qui n'est pas JPEG, PNG, TIFF, JPEG 2000, GIF ou WebP (`NotAnImageError`, famille `CorpusHttpError` : 422 au web, échec d'unité isolé au run) — les octets magiques tranchent, pas le `Content-Type` ; manifestes réels Bodleian (v2) et Wellcome (v2, v3) en cassettes réduites, source et droits documentés. Constat d'audit d'origine : 0/21 ALTO et 0/11 PAGE écrits par Cinoc passent le XSD officiel (attributs requis absents, `TextBlock@TYPE` interdit en ALTO 4, types de région hors énumération, ImageRegion réécrite en TextRegion, sous-régions mal placées) — ce qui contredit L9 de `MIGRATION_COUCHE_2.md`. Lecture PAGE : les `<Word>` sont ignorés. `alto_source` ne vérifie pas les lignes sans ID sous un ComposedBlock. IIIF : une v2 dont l'image est l'URL de son service produit un corpus de JSON déguisés en images (Bodleian) ; une v3 prend la vignette au lieu de la pleine résolution (Wellcome : 12× moins de pixels) ; le téléchargement ne vérifie ni octets magiques ni `Content-Type`. Oracle : `lxml.XMLSchema` + XSD vendorisés en fixtures, aucune dépendance. | [audit de substitution] | test XSD sur toute sortie d'écrivain (ALTO ✅, PAGE ✅) ; les deux manifestes réels en cassette ✅ |

### P5e — Une mesure qui dit vrai · S5-S7, S11-S18

Le cœur de la 1.0. Ce qu'un instrument doit dire de chaque nombre : **ce qu'il
mesure, sur quelles unités, et si la différence est significative**.

| # | Item | Connu ? | Critère de sortie |
|---|---|---|---|
| 1 ✅ | **Le statut d'une unité est produit par l'exécution, pas reconstruit au rapport** (D-261 ; **livré D-275**). Fait : `DocumentExecution.outcome/reason/message`, motif lu sur la classe de l'erreur (`failure_reason`), image injoignable = `infrastructure` ; message caviardé (secrets d'`adapter_kwargs`, workspace temporaire → `<workspace>`) ; `DocumentUsage` porte l'issue de **chaque** unité ; `MetricScore.expected` = notés + échecs à vérité terrain présente ; `failure_policy` dans `EvaluationSpec` et au manifeste ; l'économie ne compte plus une unité en échec comme une page traitée ; le support des tests (cas complets) et des IC (marginal) est affiché à côté. *Énoncé d'origine :* Aujourd'hui l'orchestrateur écrit `results[unit] = {}` et la raison ne vit que dans un `logger.warning` : rien dans `RunResult` ne distingue un échec d'une absence. Contre-exemple reproduit sur `examples/` : pero sans sa sortie pour `folio_002` obtient **CER 0,0** (support 4), contre 0,0145 quand il la produit et **0,1667** s'il rend une page vide — **échouer rapporte plus que répondre**. `DocumentExecution` porte l'issue de l'unité — `ok` · `truncated` · `failed` + motif codé (`engine` · `infrastructure` · `unsupported` · `cancelled`) —, l'orchestrateur la conserve au lieu d'un dict vide, et l'enregistrement par unité qui existe déjà (`DocumentUsage`, un par pipeline × document) la transporte dans `RunResult`. Les cas « vérité terrain absente » et « métrique inapplicable » restent côté évaluation (score `None`), où ils sont déjà. Agrégats accompagnés de « n notés / n attendus » ; politique selon A3. | [audit] | le contre-exemple ci-contre affiche le support 4/5 et le motif, à l'écran et dans le JSON |
| 1b ✅ | **Les sorties de chaque étape restent observables, et la cible se nomme** (D-261 ; **livré D-276**). Fait : `DocumentExecution.by_step` + `step_usage`, le pool (`artifacts`) et l'agrégat (`usage`) en sont des lectures ; `PipelineOutputs` porte `by_step` jusqu'au runner, les exports (ALTO, LAYOUT, HIPE) en lisent le pool ; `target_step` utilisable en YAML, affichée au rapport (méthodologie, FR/EN), au JSON (seulement quand elle est posée) et par `cinoc run --check` ; le fan-out était **déjà** estampillé par l'exécuteur — le repli « étape inconnue » ne servait plus à aucune sortie réelle. *Énoncé d'origine :* L'exécuteur tient déjà `by_step` (toutes les sorties, étape par étape) mais ne rend que `pool`, le dernier artefact **par type** : deux étapes de même type s'écrasent. Contre-exemple reproduit : un pipeline `ocr1 (tesseract) → ocr2 (pero)` ne laisse noter que pero (0,0145) ; le 0,029 de l'étape 1 n'est plus atteignable dans le run. `DocumentExecution` rend `by_step` (le pool s'en déduit, une structure au lieu de deux) avec la consommation **par étape** ; `EvaluationView` gagne une cible d'étape facultative, la dernière par défaut — la règle actuelle de `_candidate_for`, devenue explicite ; le fan-out estampille son étape, et la précédence par type, qui ne servait plus qu'à lui, disparaît. C'est ce qui rend une ablation (OCR seul / OCR + correction) mesurable **dans un seul run, sans réexécuter le préfixe**. | [audit] | le pipeline ci-contre note ses deux étapes dans le même run |
| 2 ✅ | **La troncature se voit** (**livré D-277** : raison d'arrêt lue par les quatre fournisseurs, unité `truncated` notée et signalée, `refusal`/`error` en échec `engine`, `max_tokens` paramétrable, `num_ctx`/`num_predict` pour Ollama, troncature permanente pour la correction structurée). *Énoncé d'origine :* Les quatre fournisseurs LLM/VLM ignorent la raison d'arrêt (`stop_reason`, `finish_reason`, `done_reason`) : une page coupée à 4 096 jetons (plafond codé en dur chez Anthropic) est notée comme complète. `LLMCompletion` porte la raison d'arrêt ; `max_tokens` devient un paramètre ; Ollama reçoit `num_ctx`/`num_predict` (le correctif existe pour `ollama_structured`, pas pour l'adaptateur principal). La correction structurée ne retente plus une troncature reproductible. | [audit] ; classe Ollama [connu, MIGRATION_PLAN.md:54] | tests sur cassette par fournisseur : `max_tokens` atteint → statut `truncated` |
| 3 ✅ | **Le libellé du test est le bon test** (**livré D-283** : le payload `inference` nomme son test — Wilcoxon signé-rangs à 2, Friedman au-delà — et tourne en mode rapide, sans son IC bootstrap ; non applicable, il porte son motif — un seul pipeline, moins de 6 cas complets, aucune différence — que le rapport écrit ; un résultat antérieur dit « test non calculé »). *Énoncé d'origine :* En mode rapide (le défaut), un Friedman (k ≥ 3) s'affiche « Wilcoxon ». L'inférence (coût négligeable) tourne toujours, ou le rapport écrit « test non calculé ». | [audit] | test à 3 pipelines ✅ |
| 4 ✅ | **Nemenyi juste et lu juste** (**livré D-283** : q = `studentized_range.ppf(1 − α, k, ∞)/√2`, rangs par `rankdata`, table et extrapolation supprimées ; post-hoc seulement après un Friedman rejeté **après Holm** ; le rapport nomme les **paires** significatives et dessine des **barres CD qui se chevauchent** (`cd_groups`) ; la phrase « deux moteurs hors d'un même groupe = différence significative » est retirée). *Énoncé d'origine :* Table écrite à la main fausse pour k ≥ 30, dans le sens anti-conservateur → `scipy.stats.studentized_range` (et `rankdata` pour les rangs). Les groupes « indiscernables » sont disjoints alors que le texte en tire une significativité : afficher les paires significatives, ou des groupes qui se chevauchent ; retirer la phrase. Post-hoc conditionné au rejet de Friedman. La table servait en outre la colonne α = 0,05 pour **tout** α ≠ 0,01 (D-264). | [audit] | parité scipy ✅ ; test rangs 1,2/2,0/2,8 ✅ (1,0/1,8/2,6 ne somme pas à k(k+1)/2 : aucun jeu à 3 pipelines ne les donne) |
| 5 ✅ | **L'intervalle porte sur le chiffre affiché** (**livré D-284** : `PipelineInterval` porte `value` = l'agrégat micro du tableau, même fonction `micro_ratio`, et l'IC percentile de ce ratio, documents de poids non nul rééchantillonnés avec remise ; libellés du rapport et méthodologie alignés, FR/EN). *Énoncé d'origine :* Le tableau donne un CER micro, l'IC en dessous une moyenne macro : le chiffre peut sortir de son propre intervalle. Bootstrap du ratio micro (rééchantillonner les documents, recalculer Σ erreurs / Σ poids). | micro voulu [connu, D-016] ; décalage [audit] | test : le point affiché est dans son IC ✅ |
| 6 ✅ | **Comparaisons multiples** (**livré D-283** : Holm sur la famille des tests calculés du run — les lignes du tableau —, p brute et p corrigée côte à côte, verdict sur la corrigée ; les mesures clés ne mettent en avant que le CER). *Énoncé d'origine :* Une ligne « significatif » par (vue × métrique) sans correction, alors que le glossaire dit lui-même qu'elle est exigée. Holm sur la table ; verdict mis en avant pour la seule métrique principale. | [audit] | Holm = définition descendante sur 5 005 tests ✅ |
| 7 ✅ | **Normalisation par défaut** selon A2 (**livré D-285** : `flat_text` par défaut, seconde vue `texte (lignes)`, `null` = brute ; CER de ligne et calibration sur les textes préparés par la vue ; calibration attribuée à l'étape notée ; convention écrite à côté du chiffre). *Énoncé d'origine :* une seule définition du CER dans le rapport (l'analyse par lignes applique déjà NFC + strip) ; la calibration lit la GT normalisée comme la vue. Tests de parité étendus aux cas NFC/NFD, bords, NBSP, invisibles. | [audit] | parité jiwer/dinglehopper documentée cas par cas |
| 8 ✅ | **Des noms qui ne promettent pas plus.** (**livré D-288, S16** : `unanchored_trigrams`, `n_heavy_insertion`, `searchability` AUTO, `ner_f1_exact`, régions fantômes comptées, `fca` limitée, coût humain « simulation », historique par série, romains en contexte, méthodologie selon `failure_policy`.) `hallucination` → clé `unanchored_trigrams` (aveugle à une page dupliquée : 0,021) ; `fca` déclarée limitée (0 dès que les lignes sont fusionnées, cas typique d'un VLM) ; `searchability` à seuil relatif ; `ner_f1` reçoit une variante « nom exact » (aujourd'hui « Montfort » lu « Montfert » compte juste) et perd la mention « CoNLL/HIPE » inexacte ; `region_cer` compte le texte des régions fantômes ; coût humain étiqueté **simulation** (« hypothèse : 5 s par erreur caractère ») ; historique indexé par (corpus, profil, pipeline, vue). Au passage : taxonomie (`I→l`, `O→o` mortes car appliquées après `lower()`), pires lignes appariées par F15 comme `lines.py` (**ces deux-là livrés D-286, S14**) ; `roman.py` accepte `IIV`, `IXI`, `XIIX` (**validation stricte livrée D-287, S15**) et prend `ci`, `dix` pour des numéraux — **détection en contexte livrée D-288, S16** (le paquet `roman` en oracle de test, D-264, P5e 10). | renommages d'affichage [connu, D-194] ; le reste [audit] | — |
| 9 ✅ | **Une fiche par métrique, trois niveaux, et le classement réservé aux établies.** (**livré D-289, S17** : catégorie et unité requises au registre, 4 établies ; fiche FR/EN avec oracle pour les 29 métriques ; tests et classement réservés aux établies ; table Diagnostic ; `fca`, `unanchored_trigrams`, `air` hors de `standard` ; radar supprimé ; durée par page.) Chaque métrique du registre déclare sa catégorie — **établie** (conforme à une référence nommée), **adaptée** (variante justifiée), **exploratoire** — et son unité (caractère / mot / région). Le glossaire porte, pour chaque métrique affichée par défaut : définition implémentée, ce qu'elle mesure, limites, oracle. Les exploratoires sortent du radar et des colonnes par défaut (le radar a 5 axes quasi colinéaires sur 6) ; `char_accuracy`, `word_accuracy`, `bow_f1` quittent le radar. **Seules les métriques établies entrent dans le classement et les tests de significativité** ; adaptées et exploratoires restent au diagnostic, affichées comme telles. Une métrique exploratoire n'est pas fausse : elle n'a pas encore la validité qu'un classement lui prêterait. | glossaire corrigé sur 6 métriques le 2026-11-25 ; le reste [audit] | test : toute métrique enregistrée a catégorie, unité et fiche ; l'unité de la fiche est celle du calcul |
| 11 ✅ | **Les défauts de justesse trouvés par l'audit de substitution** (D-264 ; **partie a livrée D-286, S14** : alignement optimal partagé à la place des cinq `difflib`, confusions = S du CER, pires lignes par F15, taxonomie `I→l` ; **partie b livrée D-287, S15** : ROVER indépendant du nom des sources, ordre de lecture de Breuel, tendance par `linregress` avec sa p, `roman.py` strict, diff surligné sur l'alignement du CER — item fermé). Le vote multi-moteurs n'est pas un ROVER : alignement en étoile sur la première source par ordre alphabétique, insertions perdues, **résultat qui dépend du nom des sources** (WER fusionné 0,089 contre 0,048 pour un ROVER, à 3 moteurs) → ROVER maison (~80 LOC stdlib). Les cinq alignements `difflib` (taxonomie, hallucinations, confusions, mots manqués, modernisation) sont sous-optimaux et triplent les lacunes face au WER affiché → un helper `rapidfuzz` unique. La tendance longitudinale s'affiche sans test → `scipy.stats.linregress`. L'ordre de lecture `columns` entrelace deux colonnes sous un titre large → portage de Breuel. | [audit de substitution] | chaque défaut par un test qui le reproduit, rouge avant |
| 10 ✅ | **Oracles externes en CI** (**livré D-290, S18** : extra `oracle` + job CI `oracle` ; golden dinglehopper sur `bnl_mini`, 150/150 expliqués écart par écart ; paquet `roman` exécuté ; ROVER à parité avec crowd-kit transcrit). Un golden dinglehopper (extra dédié, comme `hipe-oracle`) sur le mini-corpus de référence, écarts documentés un par un (NFC, graphèmes, segmentation en mots). | HIPE golden [connu, SPEC_HIPE] ; dinglehopper [audit] | job opt-in vert |

### P5f — Une inférence tracée · S7-S9, S19-S22

| # | Item | Connu ? | Critère de sortie |
|---|---|---|---|
| 1 ✅ | **Mêmes réglages pour tous** (**livré D-277** : `temperature` 0, `seed` 0, `max_tokens` 8 192, `top_p` non transmis, kwargs de construction validés, transmis aux API, valeurs effectives au manifeste ; Anthropic ne peut recevoir que `max_tokens` — son API refuse `temperature`/`top_p` depuis 2026-10-21 et n'a pas de `seed` —, le manifeste l'écrit `None`). *Énoncé d'origine :* OpenAI et Mistral passent `temperature=0`, Anthropic et Ollama rien : le banc compare des réglages différents. `temperature`, `seed`, `top_p`, `max_tokens` deviennent des paramètres à défauts explicites et identiques, écrits au manifeste. | [audit] (`ANALYSE_COUCHE_5.md` ne le dit que pour OpenAI) | le manifeste d'un run porte les valeurs effectives, défauts compris |
| 2 ✅ | **Le modèle servi, pas l'alias demandé** (**livré D-279** : lu dans le corps par chaque conversion, déclaré par l'étape, estampillé dans la provenance, réuni au manifeste ; tarif sur le servi, « tarif inconnu » s'il manque à la table — **corrigé D-280** : sauf s'il est exactement l'alias demandé suivi d'une date (`-AAAA-MM-JJ` OpenAI, `-AAAAMMJJ` Anthropic), auquel cas le tarif de l'alias s'applique et le rapport le dit ; jamais par préfixe ; `dependencies_lock` = `cinoc` + ses `Requires-Dist` installés ; `unicode_version`). *Énoncé d'origine :* `response.model` lu et écrit au manifeste ; tarification indexée sur le modèle servi. `dependencies_lock` rempli (versions des distributions en jeu), et la version de la base Unicode (`unicodedata.unidata_version`), dont dépend la normalisation. | lock [connu, ANALYSE_COUCHE_6.md:252] ; le reste [audit] | — |
| 2b ✅ | **Réévaluer sans réexécuter** (**livré D-279** : une empreinte d'étape — provenance — dont dérive la clé ; binaires, réglages effectifs et endpoint lu dans l'environnement dedans, `code_version` dehors ; archive format 3 avec les échecs ; `--offline`). *Énoncé d'origine :* (D-261 ; la clé ignore aussi les binaires système, D-264). L'évaluation est déjà recalculée à chaque run et le cache de reprise garde les artefacts ; deux défauts empêchent pourtant de re-noter une campagne dans six mois. (a) La clé d'unité contient la version **du paquet entier** : une correction de métrique en 1.0.1 invalide tout le cache d'inférence et fait re-payer chaque appel. Elle porte désormais les `module_versions` des étapes (déjà au manifeste) au lieu de `code_version`. (b) Elle ignore toute configuration lue dans l'environnement : un endpoint passé par `OPENAI_BASE_URL` — le contournement vLLM d'aujourd'hui — réutilise en silence les sorties du modèle précédent (par lecture du code, non exécuté faute de clé). Toute configuration qui change une sortie passe par `adapter_kwargs`, donc dans la clé ; et la clé et le `parameters_hash` de provenance — qui ne hache aujourd'hui que `step.params`, sans le modèle ni le prompt — deviennent **une seule empreinte**. Le cache, enrichi de `by_step` (P5e 1b), de l'issue (P5e 1) et des sidecars natifs (item 3), **est** l'archive du run : `cinoc run --resume-dir <archive> --offline` re-note sans aucun appel et échoue sur une unité manquante au lieu de l'exécuter. Absorbe le « garder ce qu'un run a produit » de P5b. **Faux — était écrit « *Vérifié et écarté* : le cache ne rend pas de sortie `precomputed` périmée quand le fichier source change ».** Cette phrase était fausse : le test d'origine portait sur un corpus **sans images**, donc sans clé d'unité ni cache, et ne pouvait rien montrer. La clé hachait l'image, pas le `<page>.<label>.txt` que `precomputed` lit à côté ; une sortie pré-calculée corrigée sous la même image était **resservie périmée** (reproduit en S9, D-279 : démo dotée de vraies images, CER 0,0217 inchangé après réécriture des sorties). **Corrigé en S9b (D-280)** : chaque brique qui lit un fichier voisin de l'image le déclare (hook facultatif `unit_inputs(document)`), et la clé hache son contenu — « absent » s'il manque, pour qu'apparaître ou disparaître invalide aussi ; hors ligne, l'unité est alors absente de l'archive et le refus le dit. Même démo : CER 0,0217 → 1,0 après réécriture. L'archive web reste par job (deux visiteurs d'une instance publique ne partagent pas un cache). | [audit] | une campagne archivée se re-note après une montée de version de métrique, sans réseau |
| 3 ✅ | **Les réponses natives conservées** (**livré D-278** : `ArtifactType.NATIVE_JSON`, forme canonique `native_json_bytes` ; les sept adaptateurs distants le publient et le déclarent en `output_types`, la correction structurée aussi quand un modèle est interrogé ; les conversions lisent le corps, la relecture n'a pas de second chemin ; fan-out et appels multiples documentés ; jamais noté, hors `RunResult`, gardé dans `artifacts_dir`). *Énoncé d'origine :* aujourd'hui jetées : réévaluer impose de re-payer. Sidecar `NATIVE_JSON` (nouvelle valeur d'`ArtifactType`, sur le modèle du sidecar `CONFIDENCES`) pour tout moteur distant. | [audit] | un run cloud rejoué hors ligne depuis ses sidecars donne les mêmes métriques ✅ |
| 4 ✅ | **Mistral OCR sans perte** (**livré D-291** : `markdown_to_text` en couche 2, texte noté sans syntaxe, `mistral_ocr` 1.2 ; blocs → `LAYOUT` depuis le corps gardé, lignes sans géométrie, pas de `LAYOUT` sans bloc ; `Region.confidence` ; dormant tant que le SDK 1.x ne demande ni ne décode les blocs — reste en S22). *Énoncé d'origine :* **Mistral OCR sans perte.** Le markdown (`#`, `**`, `\|---\|`, `![img](…)`) est noté comme du texte et pénalise le moteur : projection markdown → texte. La réponse OCR 4.1 (blocs, boîtes, tableaux, en-têtes/pieds) est projetée vers `LAYOUT` **depuis le sidecar** — fonction pure, testée sur cassette. `CanonicalLayout` ne porte que ce qui est **commun** — la réponse native, elle, est le sidecar — et reçoit ce qui lui manque pour ne pas être un plus petit dénominateur : une confiance de région (le score de détection est jeté aujourd'hui). Règle de projection : **aucune information absente n'est inventée pour satisfaire le schéma** — un bloc de texte sans lignes devient une ligne **sans géométrie** (le schéma l'admet déjà), jamais une boîte fabriquée, et les métriques qui exigent une segmentation en lignes s'y déclarent non applicables. Les coordonnées restent entières (arrondi sous le pixel, documenté) ; les tableaux restent hors 1.0. | [audit] | — |
| 5 ✅ | **Azure et Google** émettent `CONFIDENCES` depuis leurs mots (**livré D-292** : `azure_di`/`google_vision` 1.2, lues dans le corps — relecture du sidecar identique —, mot sans confiance ou hors [0, 1] omis ; cassette Google `folio_mots` construite, à confirmer sur réponse réelle). *Énoncé d'origine :* aujourd'hui seulement le texte : absents de la calibration. | [audit] | — |
| 6 ✅ | **Endpoint par instance** (**livré D-293** : `base_url`, `api_key_env`, `self_hosted` par instance ; `OPENAI_BASE_URL` retirée ; liste `CINOC_MODEL_HOSTS` — celle de D-269, étendue — et `api_key_env` refusé par HTTP ; créneau par `hôte:port` ; `pricing.json` `endpoints`, « auto-hébergé » déclaré, sinon « tarif inconnu »). *Énoncé d'origine :* `base_url` et `api_key_env` par instance OpenAI-compatible (vLLM, SGLang, serveur local) ; liste blanche d'hôtes opérateur ; sémaphore par hôte, pas par fournisseur ; marqueur « auto-hébergé » pour l'économie (sinon « tarif inconnu »). | [audit] | un run compare OpenAI distant et un serveur OpenAI-compatible local |
| 7 ✅ | **Délais finis, tentatives bornées** (**livré D-292** : 600 s LLM/VLM, 120 s OCR distant, réglage `timeout` ; `call_resilient` borné par la deadline et annulable ; `max_retries=0` / `retry_config=None` ; Mistral OCR, Azure, Google enveloppés ; `billed_pages` et consommation facturée des unités en échec au coût ; règle de facturation par tentative, à confirmer par fournisseur). *Énoncé d'origine :* Aucun appelant ne passe de deadline : Ollama, Azure et Google tournent sans timeout. Délai par défaut fini ; `call_resilient` borné par la deadline et annulable ; `max_retries=0` côté SDK (aujourd'hui jusqu'à 15 tentatives) ; OCR cloud enveloppés (429) ; tentatives comptées dans le coût. | annulation [connu, ANALYSE_COUCHE_5.md:131,209] ; le reste [audit] | — |
| 8 ✅ | **Les modèles se demandent au fournisseur, ils ne se codent pas** (**livré D-294, S22** : SDK épinglés par majeure ; `available_models` en direct pour les quatre fournisseurs, web et CLI ; aucun modèle par défaut codé, spec sans modèle refusée avec la liste ; digest Ollama au manifeste ; jetons de cache et de raisonnement lus, cache tarifé ou « non tarifé »). *Énoncé d'origine :* (D-268). Aujourd'hui seuls Ollama et Mistral sont listés en direct ; OpenAI et Anthropic viennent d'une liste figée (`app/models.py`), que la route `/api/models/{provider}` et `cinoc list models` servent **pour les quatre** — le menu du composeur proposait ainsi `mistral-large-latest`, retiré par Mistral. Les API exposent pourtant ce qu'il faut : Anthropic `models.list` (capacité `image_input`, `lifecycle` actif/déprécié/retiré, `max_input_tokens`), Mistral (`capabilities.vision`, `ocr`, dépréciation), OpenAI (`id`, `shutdown_date` — **pas** la vision), Ollama (`/api/tags`, capacités par `/api/show`, non vérifié). Une seule fonction `available_models(provider)` en couche `app`, en direct, pour le web et la CLI ; la vision affichée quand le fournisseur la déclare, « inconnue » sinon (jamais devinée) ; un modèle déprécié signalé. **Plus aucun modèle par défaut codé** : les trois copies (`_DEFAULT_MODEL`, `registry.py`, `pricing.json` `default_models`) disparaissent, et une spec qui ne nomme pas son modèle est refusée avec la liste de ceux que la clé permet — un défaut implicite qui change de cible en silence contredit la reproductibilité. **Les tarifs, eux, restent une donnée** : aucune de ces API ne publie de prix ; la table est indexée sur le **modèle servi** (item 2), et un modèle absent de la table s'affiche « tarif inconnu ». Majeures des SDK `openai`/`anthropic` épinglées (`mistralai<2` à revoir face à la 3.x) ; jetons de cache et de raisonnement lus. | tarifs revérifiés aux sources primaires le 2026-11-25 (D-267) | `grep` : aucun nom de modèle dans `cinoc/` hors tests et `pricing.json` ; une spec sans modèle est refusée en nommant les modèles disponibles |

### P5g — Par soustraction · S23-S29

| # | Item | Connu ? | Critère de sortie |
|---|---|---|---|
| 1 | **P5c items 2-4** : rôles `zero_shot` et `text_and_image` ✅ · déclaration des paramètres au contrat de module ✅ (S23, D-295) · catalogue de recettes branché à la page ✅ (S24, D-296). | [connu, P5c] | dette `recettes-web` fermée ✅ |
| 2 ✅ | **P5c item 6 étendu — un seul constructeur** (**livré D-298**, S26). `run_planning` **et** deux constructeurs que P5c ignore — `structure_planning` (hybride, ~190 LOC) et `correction_planning` (~110 LOC, exactement `recipes/alto_corrige.yaml`) — deviennent des recettes. Le pli de réglages (P5c item 5) est réduit à ce que le formulaire offre déjà — *livré plus large* : tous les réglages **déclarés** d'une brique du socle (`PARAMS`), requis en clair, les autres au pli ; un module tiers n'y paraît pas encore (le catalogue ne propose que le socle). | run_planning [connu, D-258] ; les deux autres [audit] | `_pipeline_for_competitor`, `_hybrid_competitor`, `_hybrid_spec` supprimés ✅ |
| 3 | **Une seule politique de vues** ✅ (S25, D-297). Formulaire, recettes et correction produisaient **trois rapports différents** pour un même pipeline (métriques, noms de vue que `cinoc compare` n'apparie pas) ; `plan_evaluation` est désormais la seule décision. | [audit] | test : même pipeline par les trois entrées → mêmes vues ✅ |
| 4 ✅ | **P5c item 8** (**livré D-299**, S27) : bouton d'arrêt (un banc lancé du web ne peut pas être interrompu alors qu'il engage des appels facturés) · zone de dépôt de spec ou `front-absent` motivé · face ou sortie de `standardize_corpus`. — *Bouton « Arrêter » ; zone de dépôt de spec (instance privée, porte fermée en mode public) ; `cinoc corpus standardize`.* | [connu, P5c] | dettes `annulation-web`, `spec-web` fermées ✅ |
| 5 | **Listes parallèles dérivées du registre** : catalogue OCR tenu à la main en 4 endroits, défauts `"fra"` ×8 et `fr_core_news_sm` ×4 ramenés à l'adaptateur ; puis fusion des quatre garde-fous qui patrouillaient ces listes. | LLM [connu, D-233] ; OCR [audit] | — |
| 6 | **Délégations et copies** (inventaire prouvé : `docs/ANALYSE_SUBSTITUTION.md`, D-264) : Nemenyi, rangs, Jensen-Shannon et OLS vers scipy (déjà dépendance, ~−110 LOC) ; bootstrap vers `numpy.random.default_rng` (~30× plus rapide, déterminisme vérifié entre versions de numpy et de Python ; **livré D-284** : vectorisé par lots, 2 000 tirages, golden recalculé contre `scipy.stats.bootstrap`) — **D-067 amendé par D-265 : la parité avec Picarones n'est plus un critère**, un golden se recalcule contre un oracle externe (scipy), pas contre l'ancien outil ; Tesseract en **un** appel du binaire (l'OCR tournait 2 à 3 fois par page) avec `OMP_THREAD_LIMIT=1` ; `ocrd_processor` sur un METS gabarit, une chaîne de processeurs, arrêt à l'annulation ; le CSS de `reports/html.py` (~580 LOC) extrait en fichier ; `StrictUndefined` et parité FR/EN pour l'i18n web ; retrait du shim `nfc`/`diplomatic` et de `from_yaml`. **Aucune nouvelle dépendance** : ocrd, dinglehopper, LiteLLM, scikit-posthocs, statsmodels, docling-core, pagexml-tools, pygal, defusedxml, crowd-kit et iiif-prezi3 ont été mesurés et rejetés comme dépendances d'exécution. Et : cinq alignements `difflib` (qui contredisent Levenshtein dans 14 cas sur 300) → un helper sur `rapidfuzz` ; un seul `parse_layout_xml` (3 copies) ; une seule table d'extensions d'image (5 copies qui divergent) ; une seule suppression de diacritiques (3 copies). | [audit] | — |
| 7 | **Retraits sans perte** : `pricing.json` `local_kinds` (aucun consommateur) ; `ArtifactType.CANONICAL_DOCUMENT`/`READING_ORDER`/`ALIGNMENT` ; `qe/` et `campaigns/tooling/` (~4 000 lignes hors CI, remplacées) ; 29 branches distantes intégrées ou obsolètes, plus la 30ᵉ selon A5. | [audit] | — |
| 8 | **Garde-fous d'agents allégés** : `test_status_freshness` réduit à son seul contrôle de fond (commandes CLI au README) ; `test_layer_dependencies` paramétré. Corrections de `CLAUDE.md` : liste blanche de `evaluation` (contredit le test), 15 profils et non 14, version calculée par `setuptools_scm` et non son repli. | [audit] | — |

### P5h — La preuve : une campagne d'ablation publiée · S10 (pilote), S30-S32

**Un pilote d'abord, tôt** (D-261) : dès P5e items 1-1b et P5f item 3 livrés,
dix pages de `37-GT-BNL`, Tesseract et un moteur cloud, plafond de dépense bas.
Son rôle n'est pas de publier : il fait apparaître les défauts que seule une
vraie campagne trouve — comme le premier banc de presse a fait naître P5a —
pendant qu'il est encore temps de les corriger. **Fait (S10, D-281)** : en local selon A6, 24 constats rattachés — `campaigns/2026-11-26-pilote-local/`.

**La campagne publiée** s'exécute sur la **version finale** (après P5g, qui change
les rapports). Elle ne compare pas une liste de moteurs : elle répond à des
questions par **ablation**, chaque variante étant une cible d'étape (P5e 1b) d'un
pipeline à préfixe commun, donc sans réexécuter les préfixes.

| Variante | Chaîne |
|---|---|
| E0 | OCR |
| E1 | segmentation → OCR par région |
| E2 | OCR → correction LLM |
| E3 | segmentation → OCR par région → correction structurée |
| E4 | OCR → score de qualité → correction **sélective** |
| E5 | VLM direct sur la page |

Questions visées : la segmentation explicite aide-t-elle encore les VLM ? À
partir de quel CER la post-correction devient-elle bénéfique ? La correction
sélective est-elle plus rentable que l'intégrale ? Un gain de CER se paie-t-il
en fidélité philologique (métriques adaptées, lues comme diagnostic) ?

- **Corpus** : `37-GT-BNL` (presse, 37 pages, déjà au dépôt) et le dataset Dresden curé (HF) ; un corpus BnF si ses droits le permettent (A4).
- **Moteurs** : Tesseract, Kraken, Mistral OCR 4.1, un VLM zero-shot cloud, un VLM ouvert servi par vLLM si un GPU est disponible (A6), et la correction structurée `saknussemm`.
- **Protocole** :
  - défaut méthodologique de la campagne d'août corrigé : césure de la GT mêlée au texte OCR → `--ocr-sidecar` [connu, `campaigns/2026-08-14-bnl-mistral-m2`] ;
  - `--repeat 5` pour tout moteur stochastique, et dispersion publiée ;
  - CER recoupé par dinglehopper sur toutes les sorties.
- **Publication** : `RunResult`, sidecars natifs et rapport sur un dataset HF, avec un DOI Zenodo.
- **Critère de sortie** : un tiers qui télécharge l'archive publiée la re-note hors ligne (`--offline`, P5f 2b) et obtient des métriques identiques au chiffre près.

### P5i — Vitrine et release · S33-S35

| # | Item | Critère de sortie |
|---|---|---|
| 1 | **README court** : le problème en trois lignes, le Space et `pip install cinoc` en tête, **un vrai résultat de P5h**, captures en haut ; le détail (extras, architecture, extensibilité) part dans `docs/`. | une personne extérieure lance un premier rapport en moins de deux minutes |
| 2 | **Trois parcours documentés et testés** : (1) noter des sorties existantes (texte ou ALTO, sans moteur), (2) comparer des moteurs sur son corpus, (3) corriger un ALTO existant. | chacun couvert par un test de bout en bout sur le paquet installé |
| 3 | **Testeurs extérieurs** (A7) sur la pré-release (A8) ; leurs blocages traités comme des défauts. | — |
| 4 | **Dépôt public** : description, topics, champ Website = Space, `CITATION.cff`, `CHANGELOG` `[1.0.0]` réécrit. | — |
| 5 | **Tag `v1.0.0` — posé par le mainteneur**, release GitHub avec wheel et sdist, publication selon A1, Space redéployé sur le tag. | — |
| 6 | **Après le tag** : les plans historiques sortent de l'arbre (l'historique git et le tag les gardent ; `CLAUDE.md` §8.9 interdit un `docs/archive`) ; `MIGRATION_PLAN.md` devient un journal figé. | — |

### Hors 1.0 (décidé, pas oublié)

P5b (suspendue à son arbitrage ; sa moitié « conserver ce qu'un run a produit »
est absorbée par P5f 2b) · P5c item 7 (composeur contraint) et pli de réglages
généré complet · nouvelles familles de métriques, nouveaux importeurs · structure
de tableaux dans `CanonicalLayout`, `LAYOUT` pour Azure et Google · API batch des
fournisseurs · segmenteur sur le Space (T2.5) · LiteLLM, au plus en plugin tiers
(D-264) · extraction d'une bibliothèque ALTO/PAGE autonome, **seulement** quand un
consommateur réel se présente (D-266) · gel de Picarones (différé à la demande de
l'utilisateur).

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
- [ ] **P5c — joignabilité** : toute route déclarée est atteignable depuis la page, ou le dit. Né d'un audit des 31 routes — trois d'entre elles, celles des **recettes**, ont zéro appel dans le front alors que le garde-fou de parité les donne vertes. La conception ([`PLAN_UI_COMPOSEUR.md`](PLAN_UI_COMPOSEUR.md)) a trouvé la cause sous le symptôme : **deux constructeurs de pipeline parallèles**, dont l'un est à trois lignes de son budget. Huit tranches : garde-fou · deux rôles manquants · déclaration des paramètres · catalogue de recettes · pli de réglages · bascule vers un constructeur unique · composeur contraint · les deux indépendants. **Ne bloque pas le tag ; passe avant P5b**, qui est suspendue à un arbitrage.
- [ ] **P5b — persistance et calcul à la demande** : garder ce qu'un run a produit (**fait**, `RunManifest.artifacts_dir`), puis calculer une analyse au clic dans la saveur servie. Né de #139. **Ne bloque pas le tag** — et reste **suspendue** tant que l'arbitrage manifeste-porte-les-documents ⇄ serveur-retient-la-spec n'est pas rendu.
- [x] **P5d — installable et sûr ✅ (D-262 → D-274, sessions S1-S4)** : installation nue réparée et gardée par un job CI ; aucun secret dans un rapport ; ce que la page propose se planifie ; paquet publiable (A1) ; ALTO et PAGE écrits conformes aux XSD officiels ; IIIF importé en pleine résolution, téléchargement réservé aux images.
- [x] **P5e — une mesure qui dit vrai ✅ (D-275 → D-290, sessions S5-S7, S11-S18)** : statut de chaque unité et support affiché ; troncature visible ; tests statistiques corrects et correctement libellés ; normalisation par défaut (A2) ; noms, catégories et fiches de métriques ; oracle dinglehopper.
- [x] **P5f — une inférence tracée ✅ (D-277 → D-280, D-291 → D-294, sessions S7-S9, S19-S22)** : réglages identiques et écrits ; modèle servi ; réponses natives ; Mistral OCR sans perte ; endpoint par instance ; délais finis ; modèles demandés au fournisseur, aucun codé.
- [ ] **P5g — par soustraction** : un constructeur, une politique de vues, P5c items 2-4 et 8, listes dérivées du registre, retraits.
- [ ] **P5h — la preuve** : campagne de référence publiée et rejouable au chiffre près.
- [ ] **P5i — vitrine et release** : README court, trois parcours testés sur le paquet installé, testeurs extérieurs.
- [ ] **Tag `v1.0.0`** — *à poser par le mainteneur, quand il le décide*. Un tag posé le 2026-09-10 l'a été **sans son accord** et a été supprimé (D-232) : le dépôt ne porte aucun tag. **Révision 2026-11-25 (D-260)** : la phrase qui suivait ici — « le reste de la checklist étant vert, la 1.0 est prête techniquement » — était fausse. Un `pip install cinoc` sans extra ne démarrait pas, et plusieurs chiffres affichés ne mesuraient pas ce qu'annonçait leur nom. La route P5d → P5i, plus haut, ferme ces écarts ; le tag la suit.
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
