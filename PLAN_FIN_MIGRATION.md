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

> **Née de l'audit du 2026-11-25 (D-260)**, mené sur le code réel : installation
> dans un environnement Python vierge, comparaison des métriques à jiwer et
> dinglehopper, lecture des SDK installés, clone complet des branches. La
> checklist « 1.0 prête » plus bas était verte ; l'audit a montré qu'elle avait
> été cochée **sur la CI, pas sur le produit** — même leçon que P5a, un cran plus
> loin : une CI verte ne prouve ni qu'un paquet s'installe, ni qu'un chiffre
> affiché mesure ce que son nom annonce.
>
> **Cette section remplace la fin de route** (P5b, P5c, P5) ; elle n'ajoute pas un
> plan à côté. **Rien de neuf n'y entre** hors de ce que liste chaque phase. La
> règle de la phase P5h vaut pour toutes : un défaut trouvé devient un correctif,
> jamais une feature.
>
> Marqueurs : **[connu]** = déjà écrit dans un `.md` du dépôt (cité) ·
> **[audit]** = trouvé par l'audit du 2026-11-25. Budget en sessions de
> construction (une tranche par session, `CLAUDE.md` §9).

### Arbitrages à rendre (mainteneur) — avant la phase qui en dépend

| # | Question | Recommandation | Bloque |
|---|---|---|---|
| A1 | ~~**Canal de publication.**~~ **Rendu le 2026-11-25** : `saknussemm` 0.9.0 est publié sur PyPI ; l'extra l'épingle `==0.9.0` après vérification du pont (D-261). | — | — |
| A2 | **Normalisation par défaut.** Aujourd'hui aucune : un « é » composé face au même « é » décomposé donne CER 0,545 (dinglehopper : 0). Changer le défaut change **tous** les chiffres déjà publiés. | NFC + retrait des invisibles par défaut ; la comparaison brute reste une vue explicite, nommée comme telle. | P5e item 7 |
| A3 | **Politique d'échec.** Une unité en échec sort aujourd'hui de la moyenne : le moteur qui échoue sur la page difficile est avantagé. | Exclue **et** affichée (n notés / n attendus à côté de chaque agrégat) ; option « échec = erreur maximale », déjà la règle du bilan de correction (R-1.8). | P5e item 1 |
| A4 | **Images du dépôt** (`corpus/`, 43 Mo, scans BnF et BNL) : redistribuables dans un sdist ? | Les sortir du paquet dans tous les cas ; les déplacer vers un dataset HF si les droits le permettent, ne garder au dépôt que `tests/fixtures/`. | P5d item 5 |
| A5 | **Branche `claude/lucid-dirac-0s4p8r`** : seule à porter du code absent de `main` (`block_chain.py`, OCR → LLM par bloc), sans décision d'abandon trouvée. | Supprimer : le besoin est couvert par la correction structurée. | P5g item 7 |
| A6 | **Campagne de référence** : corpus, moteurs, plafond de dépense, accès à un GPU (vLLM). | Voir P5h ; fixer un plafond en euros avant le premier appel facturé. | P5h |
| A7 | **Testeurs extérieurs** : qui, combien. | Deux ou trois personnes d'institution patrimoniale, une par parcours. | P5i item 3 |
| A8 | **Pré-version.** | Une pré-release GitHub `v1.0.0rc1` (non PyPI) à la sortie de P5g, pour les testeurs ; aucun autre tag avant `v1.0.0`. | P5i |

### P5d — Installable et sûr · ~2-3 sessions

| # | Item | Connu ? | Critère de sortie |
|---|---|---|---|
| 1 ✅ | **Installation nue réparée** (D-262). `cinoc --help` plante sur `ModuleNotFoundError: httpcore` (le transport des importeurs est importé par la CLI). `httpx`/`httpcore` en dépendances de base ; les extras `google`, `azure`, `ollama`, qui ne contenaient qu'eux, disparaissent ; retirés aussi de `serve` et `saknussemm`. | [audit] | — |
| 2 ✅ | **Job CI « installation nue »** (D-262, job `install-bare`) : construire le wheel, l'installer dans un venv vierge, lancer depuis un dossier temporaire `cinoc --help`, `cinoc demo`, `cinoc run examples/config.yaml`. C'est l'absence de ce job qui a laissé l'item 1 passer depuis le 16 août. | [audit] | job vert ; rouge prouvé en retirant `httpx` |
| 3 ✅ | **Aucun secret dans un rapport** (D-262 : le manifeste remplace toute valeur de réglage secret par `<secret>` — un seul point de passage, puisque tout ce qui sort d'un run sort du manifeste ; le jeton reste dans `adapter_kwargs` pour authentifier le module). Le jeton du segmenteur distant entre dans `adapter_kwargs` (`run_planning.py`), donc dans le manifeste, puis s'affiche dans la section composition. Le jeton ne transite plus par `adapter_kwargs` (variable d'environnement ou secret de session) ; la section composition masque en plus toute clé `token`/`key`/`secret` (défense en profondeur). | [connu pour les recettes futures, PLAN_UI_COMPOSEUR §7] ; [audit] pour le chemin actuel | test : un run avec jeton → le JSON `RunResult` et le HTML ne contiennent pas sa valeur |
| 4 | **Ce que la page propose, le planificateur l'accepte.** `tesseract_layout` et `doclayout_yolo` sont proposés par le `<select>` puis refusés (422) ; ce sont les deux seuls segmenteurs exécutables sans dépendance lourde. Les ensembles `PIPELINE_SEGMENTERS`/`SEGMENTER_KINDS` dérivent du registre. Le `host` ollama reçu en HTTP est validé contre une liste blanche opérateur (SSRF sur instance privée). | [audit] | test : chaque option proposée par la page se planifie |
| 4b ✅ | **Deux fuites réseau fermées** (D-263) : le segmenteur distant validait son endpoint puis laissait `httpx` le résoudre à nouveau (DNS rebinding) — il passe par `post_json`, épinglé à l'IP validée, sans redirection ; et un en-tête d'authentification suivait une redirection dès que le **nom d'hôte** coïncidait, donc sur un changement de port ou une rétrogradation https → http — la comparaison porte désormais sur l'origine (schéma, hôte, port). | [audit de substitution] | deux tests, rouges sans le correctif |
| 5 | **Paquet propre.** Le sdist pèse 46 Mo (images de `corpus/`, `design/`, `campaigns/`, `.claude/`) ; le wheel embarque 15 `.md` internes. Exclusions explicites ; `cinoc --version`. | [audit] | sdist < 5 Mo ; wheel sans `.md` |
| 6 | **Canal de publication** selon A1 ; `twine check` vert. | [audit] | `twine check dist/*` vert |

### P5e — Une mesure qui dit vrai · ~6-8 sessions

Le cœur de la 1.0. Ce qu'un instrument doit dire de chaque nombre : **ce qu'il
mesure, sur quelles unités, et si la différence est significative**.

| # | Item | Connu ? | Critère de sortie |
|---|---|---|---|
| 1 | **Le statut d'une unité est produit par l'exécution, pas reconstruit au rapport** (D-261). Aujourd'hui l'orchestrateur écrit `results[unit] = {}` et la raison ne vit que dans un `logger.warning` : rien dans `RunResult` ne distingue un échec d'une absence. Contre-exemple reproduit sur `examples/` : pero sans sa sortie pour `folio_002` obtient **CER 0,0** (support 4), contre 0,0145 quand il la produit et **0,1667** s'il rend une page vide — **échouer rapporte plus que répondre**. `DocumentExecution` porte l'issue de l'unité — `ok` · `truncated` · `failed` + motif codé (`engine` · `infrastructure` · `unsupported` · `cancelled`) —, l'orchestrateur la conserve au lieu d'un dict vide, et l'enregistrement par unité qui existe déjà (`DocumentUsage`, un par pipeline × document) la transporte dans `RunResult`. Les cas « vérité terrain absente » et « métrique inapplicable » restent côté évaluation (score `None`), où ils sont déjà. Agrégats accompagnés de « n notés / n attendus » ; politique selon A3. | [audit] | le contre-exemple ci-contre affiche le support 4/5 et le motif, à l'écran et dans le JSON |
| 1b | **Les sorties de chaque étape restent observables, et la cible se nomme** (D-261). L'exécuteur tient déjà `by_step` (toutes les sorties, étape par étape) mais ne rend que `pool`, le dernier artefact **par type** : deux étapes de même type s'écrasent. Contre-exemple reproduit : un pipeline `ocr1 (tesseract) → ocr2 (pero)` ne laisse noter que pero (0,0145) ; le 0,029 de l'étape 1 n'est plus atteignable dans le run. `DocumentExecution` rend `by_step` (le pool s'en déduit, une structure au lieu de deux) avec la consommation **par étape** ; `EvaluationView` gagne une cible d'étape facultative, la dernière par défaut — la règle actuelle de `_candidate_for`, devenue explicite ; le fan-out estampille son étape, et la précédence par type, qui ne servait plus qu'à lui, disparaît. C'est ce qui rend une ablation (OCR seul / OCR + correction) mesurable **dans un seul run, sans réexécuter le préfixe**. | [audit] | le pipeline ci-contre note ses deux étapes dans le même run |
| 2 | **La troncature se voit.** Les quatre fournisseurs LLM/VLM ignorent la raison d'arrêt (`stop_reason`, `finish_reason`, `done_reason`) : une page coupée à 4 096 jetons (plafond codé en dur chez Anthropic) est notée comme complète. `LLMCompletion` porte la raison d'arrêt ; `max_tokens` devient un paramètre ; Ollama reçoit `num_ctx`/`num_predict` (le correctif existe pour `ollama_structured`, pas pour l'adaptateur principal). La correction structurée ne retente plus une troncature reproductible. | [audit] ; classe Ollama [connu, MIGRATION_PLAN.md:54] | tests sur cassette par fournisseur : `max_tokens` atteint → statut `truncated` |
| 3 | **Le libellé du test est le bon test.** En mode rapide (le défaut), un Friedman (k ≥ 3) s'affiche « Wilcoxon ». L'inférence (coût négligeable) tourne toujours, ou le rapport écrit « test non calculé ». | [audit] | test à 3 pipelines |
| 4 | **Nemenyi juste et lu juste.** Table écrite à la main fausse pour k ≥ 30, dans le sens anti-conservateur → `scipy.stats.studentized_range` (et `rankdata` pour les rangs). Les groupes « indiscernables » sont disjoints alors que le texte en tire une significativité : afficher les paires significatives, ou des groupes qui se chevauchent ; retirer la phrase. Post-hoc conditionné au rejet de Friedman. | [audit] | parité scipy ; test rangs 1,0/1,8/2,6 |
| 5 | **L'intervalle porte sur le chiffre affiché.** Le tableau donne un CER micro, l'IC en dessous une moyenne macro : le chiffre peut sortir de son propre intervalle. Bootstrap du ratio micro (rééchantillonner les documents, recalculer Σ erreurs / Σ poids). | micro voulu [connu, D-016] ; décalage [audit] | test : le point affiché est dans son IC |
| 6 | **Comparaisons multiples.** Une ligne « significatif » par (vue × métrique) sans correction, alors que le glossaire dit lui-même qu'elle est exigée. Holm sur la table ; verdict mis en avant pour la seule métrique principale. | [audit] | — |
| 7 | **Normalisation par défaut** selon A2 ; une seule définition du CER dans le rapport (l'analyse par lignes applique déjà NFC + strip) ; la calibration lit la GT normalisée comme la vue. Tests de parité étendus aux cas NFC/NFD, bords, NBSP, invisibles. | [audit] | parité jiwer/dinglehopper documentée cas par cas |
| 8 | **Des noms qui ne promettent pas plus.** `hallucination` → clé `unanchored_trigrams` (aveugle à une page dupliquée : 0,021) ; `fca` déclarée limitée (0 dès que les lignes sont fusionnées, cas typique d'un VLM) ; `searchability` à seuil relatif ; `ner_f1` reçoit une variante « nom exact » (aujourd'hui « Montfort » lu « Montfert » compte juste) et perd la mention « CoNLL/HIPE » inexacte ; `region_cer` compte le texte des régions fantômes ; coût humain étiqueté **simulation** (« hypothèse : 5 s par erreur caractère ») ; historique indexé par (corpus, profil, pipeline, vue). Au passage : taxonomie (`I→l`, `O→o` mortes car appliquées après `lower()`), pires lignes appariées par F15 comme `lines.py`. | renommages d'affichage [connu, D-194] ; le reste [audit] | — |
| 9 | **Une fiche par métrique, trois niveaux, et le classement réservé aux établies.** Chaque métrique du registre déclare sa catégorie — **établie** (conforme à une référence nommée), **adaptée** (variante justifiée), **exploratoire** — et son unité (caractère / mot / région). Le glossaire porte, pour chaque métrique affichée par défaut : définition implémentée, ce qu'elle mesure, limites, oracle. Les exploratoires sortent du radar et des colonnes par défaut (le radar a 5 axes quasi colinéaires sur 6) ; `char_accuracy`, `word_accuracy`, `bow_f1` quittent le radar. **Seules les métriques établies entrent dans le classement et les tests de significativité** ; adaptées et exploratoires restent au diagnostic, affichées comme telles. Une métrique exploratoire n'est pas fausse : elle n'a pas encore la validité qu'un classement lui prêterait. | glossaire corrigé sur 6 métriques le 2026-11-25 ; le reste [audit] | test : toute métrique enregistrée a catégorie, unité et fiche ; l'unité de la fiche est celle du calcul |
| 10 | **Oracles externes en CI** : un golden dinglehopper (extra dédié, comme `hipe-oracle`) sur le mini-corpus de référence, écarts documentés un par un (NFC, graphèmes, segmentation en mots). | HIPE golden [connu, SPEC_HIPE] ; dinglehopper [audit] | job opt-in vert |

### P5f — Une inférence tracée · ~5-7 sessions

| # | Item | Connu ? | Critère de sortie |
|---|---|---|---|
| 1 | **Mêmes réglages pour tous.** OpenAI et Mistral passent `temperature=0`, Anthropic et Ollama rien : le banc compare des réglages différents. `temperature`, `seed`, `top_p`, `max_tokens` deviennent des paramètres à défauts explicites et identiques, écrits au manifeste. | [audit] (`ANALYSE_COUCHE_5.md` ne le dit que pour OpenAI) | le manifeste d'un run porte les valeurs effectives, défauts compris |
| 2 | **Le modèle servi, pas l'alias demandé.** `response.model` lu et écrit au manifeste ; tarification indexée sur le modèle servi. `dependencies_lock` rempli (versions des distributions en jeu). | lock [connu, ANALYSE_COUCHE_6.md:252] ; le reste [audit] | — |
| 2b | **Réévaluer sans réexécuter** (D-261). L'évaluation est déjà recalculée à chaque run et le cache de reprise garde les artefacts ; deux défauts empêchent pourtant de re-noter une campagne dans six mois. (a) La clé d'unité contient la version **du paquet entier** : une correction de métrique en 1.0.1 invalide tout le cache d'inférence et fait re-payer chaque appel. Elle porte désormais les `module_versions` des étapes (déjà au manifeste) au lieu de `code_version`. (b) Elle ignore toute configuration lue dans l'environnement : un endpoint passé par `OPENAI_BASE_URL` — le contournement vLLM d'aujourd'hui — réutilise en silence les sorties du modèle précédent (par lecture du code, non exécuté faute de clé). Toute configuration qui change une sortie passe par `adapter_kwargs`, donc dans la clé ; et la clé et le `parameters_hash` de provenance — qui ne hache aujourd'hui que `step.params`, sans le modèle ni le prompt — deviennent **une seule empreinte**. Le cache, enrichi de `by_step` (P5e 1b), de l'issue (P5e 1) et des sidecars natifs (item 3), **est** l'archive du run : `cinoc run --resume-dir <archive> --offline` re-note sans aucun appel et échoue sur une unité manquante au lieu de l'exécuter. Absorbe le « garder ce qu'un run a produit » de P5b. *Vérifié et écarté* : le cache ne rend pas de sortie `precomputed` périmée quand le fichier source change. | [audit] | une campagne archivée se re-note après une montée de version de métrique, sans réseau |
| 3 | **Les réponses natives conservées.** Aujourd'hui jetées : réévaluer impose de re-payer. Sidecar `NATIVE_JSON` (nouvelle valeur d'`ArtifactType`, sur le modèle du sidecar `CONFIDENCES`) pour tout moteur distant. | [audit] | un run cloud rejoué hors ligne depuis ses sidecars donne les mêmes métriques |
| 4 | **Mistral OCR sans perte.** Le markdown (`#`, `**`, `\|---\|`, `![img](…)`) est noté comme du texte et pénalise le moteur : projection markdown → texte. La réponse OCR 4.1 (blocs, boîtes, tableaux, en-têtes/pieds) est projetée vers `LAYOUT` **depuis le sidecar** — fonction pure, testée sur cassette. `CanonicalLayout` ne porte que ce qui est **commun** — la réponse native, elle, est le sidecar — et reçoit ce qui lui manque pour ne pas être un plus petit dénominateur : une confiance de région (le score de détection est jeté aujourd'hui). Règle de projection : **aucune information absente n'est inventée pour satisfaire le schéma** — un bloc de texte sans lignes devient une ligne **sans géométrie** (le schéma l'admet déjà), jamais une boîte fabriquée, et les métriques qui exigent une segmentation en lignes s'y déclarent non applicables. Les coordonnées restent entières (arrondi sous le pixel, documenté) ; les tableaux restent hors 1.0. | [audit] | — |
| 5 | **Azure et Google** émettent `CONFIDENCES` depuis leurs mots (aujourd'hui seulement le texte : absents de la calibration). | [audit] | — |
| 6 | **Endpoint par instance.** `base_url` et `api_key_env` par instance OpenAI-compatible (vLLM, SGLang, serveur local) ; liste blanche d'hôtes opérateur ; sémaphore par hôte, pas par fournisseur ; marqueur « auto-hébergé » pour l'économie (sinon « tarif inconnu »). | [audit] | un run compare OpenAI distant et un serveur OpenAI-compatible local |
| 7 | **Délais finis, tentatives bornées.** Aucun appelant ne passe de deadline : Ollama, Azure et Google tournent sans timeout. Délai par défaut fini ; `call_resilient` borné par la deadline et annulable ; `max_retries=0` côté SDK (aujourd'hui jusqu'à 15 tentatives) ; OCR cloud enveloppés (429) ; tentatives comptées dans le coût. | annulation [connu, ANALYSE_COUCHE_5.md:131,209] ; le reste [audit] | — |
| 8 | **Modèles et tarifs : une seule source.** Défauts déclarés à trois endroits (`_DEFAULT_MODEL`, `registry.py`, `pricing.json`) → un seul ; défauts actuels ; majeures des SDK `openai`/`anthropic` épinglées ; `pricing.json` revérifié (alias Mistral small/large, Azure) avant `valid_until` ; jetons de cache et de raisonnement lus. | tarifs revérifiés le 2026-11-25 sauf alias Mistral et Azure | — |

### P5g — Par soustraction · ~5-7 sessions

| # | Item | Connu ? | Critère de sortie |
|---|---|---|---|
| 1 | **P5c items 2-4** : rôles `zero_shot` et `text_and_image` · déclaration des paramètres au contrat de module · catalogue de recettes branché à la page. | [connu, P5c] | dette `recettes-web` fermée |
| 2 | **P5c item 6 étendu — un seul constructeur.** `run_planning` **et** deux constructeurs que P5c ignore — `structure_planning` (hybride, ~190 LOC) et `correction_planning` (~110 LOC, exactement `recipes/alto_corrige.yaml`) — deviennent des recettes. Le pli de réglages (P5c item 5) est réduit à ce que le formulaire offre déjà. | run_planning [connu, D-258] ; les deux autres [audit] | `_pipeline_for_competitor`, `_hybrid_competitor`, `_hybrid_spec` supprimés |
| 3 | **Une seule politique de vues.** Formulaire, recettes et correction produisent aujourd'hui **trois rapports différents** pour un même pipeline (métriques, noms de vue `text`/`texte` que `cinoc compare` n'apparie pas). | [audit] | test : même pipeline par les trois entrées → mêmes vues |
| 4 | **P5c item 8** : bouton d'arrêt (un banc lancé du web ne peut pas être interrompu alors qu'il engage des appels facturés) · zone de dépôt de spec ou `front-absent` motivé · face ou sortie de `standardize_corpus`. | [connu, P5c] | dettes `annulation-web`, `spec-web` fermées |
| 5 | **Listes parallèles dérivées du registre** : catalogue OCR tenu à la main en 4 endroits, défauts `"fra"` ×8 et `fr_core_news_sm` ×4 ramenés à l'adaptateur ; puis fusion des quatre garde-fous qui patrouillaient ces listes. | LLM [connu, D-233] ; OCR [audit] | — |
| 6 | **Délégations et copies** : cinq alignements `difflib` (qui contredisent Levenshtein dans 14 cas sur 300) → un helper sur `rapidfuzz` ; un seul `parse_layout_xml` (3 copies) ; une seule table d'extensions d'image (5 copies qui divergent) ; une seule suppression de diacritiques (3 copies). | [audit] | — |
| 7 | **Retraits sans perte** : `pricing.json` `local_kinds` (aucun consommateur) ; `ArtifactType.CANONICAL_DOCUMENT`/`READING_ORDER`/`ALIGNMENT` ; `qe/` et `campaigns/tooling/` (~4 000 lignes hors CI, remplacées) ; 29 branches distantes intégrées ou obsolètes, plus la 30ᵉ selon A5. | [audit] | — |
| 8 | **Garde-fous d'agents allégés** : `test_status_freshness` réduit à son seul contrôle de fond (commandes CLI au README) ; `test_layer_dependencies` paramétré. Corrections de `CLAUDE.md` : liste blanche de `evaluation` (contredit le test), 15 profils et non 14, version calculée par `setuptools_scm` et non son repli. | [audit] | — |

### P5h — La preuve : une campagne d'ablation publiée · ~3-5 sessions + temps de calcul

**Un pilote d'abord, tôt** (D-261) : dès P5e items 1-1b et P5f item 3 livrés,
dix pages de `37-GT-BNL`, Tesseract et un moteur cloud, plafond de dépense bas.
Son rôle n'est pas de publier : il fait apparaître les défauts que seule une
vraie campagne trouve — comme le premier banc de presse a fait naître P5a —
pendant qu'il est encore temps de les corriger.

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

### P5i — Vitrine et release · ~2-3 sessions

| # | Item | Critère de sortie |
|---|---|---|
| 1 | **README court** : le problème en trois lignes, le Space et `pip install cinoc` en tête, **un vrai résultat de P5h**, captures en haut ; le détail (extras, architecture, extensibilité) part dans `docs/`. | une personne extérieure lance un premier rapport en moins de deux minutes |
| 2 | **Trois parcours documentés et testés** : (1) noter des sorties existantes (texte ou ALTO, sans moteur), (2) comparer des moteurs sur son corpus, (3) corriger un ALTO existant. | chacun couvert par un test de bout en bout sur le paquet installé |
| 3 | **Testeurs extérieurs** (A7) sur la pré-release (A8) ; leurs blocages traités comme des défauts. | — |
| 4 | **Dépôt public** : description, topics, champ Website = Space, `CITATION.cff`, `CHANGELOG` `[1.0.0]` réécrit. | — |
| 5 | **Tag `v1.0.0` — posé par le mainteneur**, release GitHub avec wheel et sdist, publication selon A1, Space redéployé sur le tag. | — |
| 6 | **Après le tag** : les plans historiques sortent de l'arbre (l'historique git et le tag les gardent ; `CLAUDE.md` §8.9 interdit un `docs/archive`) ; `MIGRATION_PLAN.md` devient un journal figé. | — |

### Hors 1.0 (décidé, pas oublié)

P5b (suspendue à son arbitrage) · P5c item 7 (composeur contraint) et pli de
réglages généré complet · nouvelles familles de métriques, nouveaux importeurs ·
structure de tableaux dans `CanonicalLayout`, `LAYOUT` pour Azure et Google ·
API batch des fournisseurs · segmenteur sur le Space (T2.5) · gel de Picarones
(différé à la demande de l'utilisateur).

### Ordre et budget

`P5d → P5e ∥ P5f → (pilote P5h) → P5g → P5h → P5i`. Critère de toute phase :
**le parcours utilisateur qu'elle touche fonctionne sur le paquet installé** —
pas « la couche est finie » ni « la couverture tient ». P5e et P5f peuvent s'entrelacer : P5e
item 2 et P5f item 1 touchent les mêmes adaptateurs, à faire dans la même
session. P5e, P5f et P5g changent des chiffres affichés : ils passent **avant**
la campagne, qui ne doit tourner qu'une fois. Environ **23 à 33 sessions** au
total, hors temps de calcul de P5h.

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
- [ ] **P5d — installable et sûr** : installation nue réparée et gardée par un job CI ; aucun secret dans un rapport ; ce que la page propose se planifie ; paquet publiable (A1).
- [ ] **P5e — une mesure qui dit vrai** : statut de chaque unité et support affiché ; troncature visible ; tests statistiques corrects et correctement libellés ; normalisation par défaut (A2) ; noms, catégories et fiches de métriques ; oracle dinglehopper.
- [ ] **P5f — une inférence tracée** : réglages identiques et écrits ; modèle servi ; réponses natives ; Mistral OCR sans perte ; endpoint par instance ; délais finis.
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
