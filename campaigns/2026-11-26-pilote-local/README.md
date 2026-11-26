# 2026-11-26 — Pilote local sur `37-GT-BNL` (S10, D-281)

**Rôle : pas une publication.** Faire tourner le produit installé, comme un
utilisateur, sur de vraies pages, pour trouver ce que seule une vraie campagne
trouve — et rattacher chaque défaut à une session de la feuille de route
(`PLAN_FIN_MIGRATION.md` §« Étape 4quinquies »). Arbitrage **A6 rendu** :
Tesseract + un VLM **local** (Ollama), aucun appel facturé. Les chiffres
ci-dessous valent pour 10 pages et un modèle de 3 B : ils ne sont **pas** à
citer comme résultat.

## Protocole

| | |
|---|---|
| corpus | 10 pages de `corpus/37-GT-BNL` (crops d'articles, 300 DPI), GT = texte dérivé de l'ALTO de la page par l'import (`gt_source: layout`) |
| pages | `0000` FR (22 l.) · `0003` DE Fraktur (14 l., 4 `⸗`, un `�` dans la GT) · `0006` FR guillemets · `0009` DE Fraktur (24 l., 6 `⸗`) · `0011` DE cours du marché (3 l., chiffres) · `0012` FR avis légal, colonne étroite (31 l.) · `0015` tableau numérique FR (18 l.) · `0022` DE, page large 2047 px · `0023` FR 2 lignes · `0031` DE Fraktur (21 l., 6 `⸗`) — 5 français, 5 allemands, dont un tableau |
| construction | ZIP des 10 paires `png` + `xml` → `cinoc corpus import zip` (écrit `corpus.yaml`, GT dérivées) ; pipelines et vues ajoutés **à la main** (la CLI ne sait pas composer un pipeline, cf. D24) ; `cinoc run --check` |
| exécution | `cinoc run pilote.yaml --resume-dir <archive> --json … --csv … -o …`, puis `--offline` depuis l'archive ; `cinoc compare` |
| (a) | `tesseract_fra_deu` (`lang: fra+deu+ltz`) et `tesseract_fraktur_fra` (`lang: Fraktur+fra`), `psm 6` |
| (b) | `qwen25vl_3b_zero_shot` : `ollama`, `qwen2.5vl:3b`, `role: zero_shot`, prompt par défaut, `max_tokens: 2048` |
| (c) | `tesseract_fraktur_fra_qwen_corr` : (a) Fraktur → `ollama` `qwen2.5vl:3b` en `text_only`, prompt curé `correction_press_19c_european` **recopié** dans `prompt:` (un `prompt_name` en YAML est ignoré, cf. D15) |
| vues | `texte` (`nfc` : cer, wer, cer_diplo, mer, hallucination) · `sans_cesure` (`dehyphenated` : cer, wer) ; en re-notation seulement : `plat` (`flat_text`) et `sans_apostrophes` (`no_apostrophes`) |
| défaut d'août | évité par construction : aucun pipeline n'entre par `alto_source`, donc aucune césure de la GT n'est mêlée au texte d'un moteur ; `--ocr-sidecar` ne s'applique qu'à `cinoc correct` |

Fichiers : `pilote.yaml` (la spec exécutée — ses chemins sont relatifs au
dossier du corpus importé, elle ne tourne qu'à côté de lui) et `run_result.json`
(le `RunResult` v4 du run complet). **Pas d'images, pas d'archive** : le corpus
importé, l'archive (45 Mo, 40 unités + sidecars natifs), les rapports HTML et
les journaux sont dans le scratchpad de la session,
`/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/s10/`
(`corpus/`, `archive/`, `pilote_c.html`, `pilote_vues.html`, `*.log`) — éphémère.

## Versions (manifeste)

| | |
|---|---|
| `code_version` | `0.1.1.dev159+g78c21e6ef` (branche de S9b) |
| binaires | `tesseract 5.3.4` ; données de langue Debian `tesseract-ocr-{fra,deu,ltz,script-frak}` `4.1.0-2` (installées pour le pilote — **absentes du manifeste**, D19) |
| modules | `tesseract:*` 1.0 · `ollama:*` 2.1 |
| modèle servi | `ollama:qwen_vlm` → `qwen2.5vl:3b` (le **tag** ; digest `fb90415cde1e…` lu à la main dans `/api/tags`, absent du manifeste, D18) ; serveur Ollama 0.40.18, CPU 4 cœurs, `num_ctx 16384` |
| réglages effectifs | `temperature 0.0` · `seed 0` · `top_p` non transmis · `max_tokens 2048` · `num_ctx 16384` |
| Unicode | 15.1.0 · Python 3.13 |
| `dependencies_lock` | `cinoc`, fastapi 0.165.0, httpx 0.28.1, lxml 6.1.3, numpy 2.4.6, pillow 13.0.0.post1, pydantic 2.13.5, pytesseract 0.3.13, rapidfuzz 3.14.6, saknussemm 0.9.0, scipy 1.18.1… |

## Résultats

Agrégats (le chiffre affiché par le rapport ; **micro**, cf. D6), n notés / n attendus = **10/10 partout**, issues d'unité : **40/40 `ok`**, aucune `truncated`, aucune `failed` dans le run retenu.

| pipeline | CER `texte` | WER `texte` | cer_diplo | CER `sans_cesure` | CER `plat` | CER `sans_apostrophes` | durée totale |
|---|---|---|---|---|---|---|---|
| tesseract_fra_deu | 0,1038 | 0,3153 | 0,1038 | 0,1042 | 0,1020 | 0,1021 | 147,2 s (dont 114,6 s hérités, D10) |
| tesseract_fraktur_fra | 0,0915 | 0,3144 | 0,0763 | 0,0913 | 0,0900 | 0,0895 | 25,5 s |
| qwen25vl_3b_zero_shot | **0,0530** | **0,1545** | 0,0530 | 0,0468 | **0,0406** | 0,0488 | 634,9 s |
| tesseract_fraktur_fra_qwen_corr | 0,1110 | 0,2913 | 0,1071 | 0,1077 | 0,1052 | 0,1071 | 305,6 s |

Par page (CER `texte`, durée de l'unité) :

| page | tesseract_fra_deu | tesseract_fraktur_fra | qwen25vl_3b | fraktur → qwen |
|---|---|---|---|---|
| 0000 | 0,0773 (3,6 s) | 0,0795 (2,8 s) | 0,0430 (64,1 s) | 0,0872 (40,8 s) |
| 0003 | 0,1106 (3,3 s) | 0,0747 (2,5 s) | 0,0344 (50,4 s) | 0,1121 (22,7 s) |
| 0006 | 0,0227 (2,2 s) | 0,0140 (1,9 s) | 0,0367 (47,6 s) | 0,0350 (20,2 s) |
| 0009 | 0,1590 (6,4 s) | 0,1632 (4,5 s) | 0,0341 (85,4 s) | 0,1624 (62,1 s) |
| 0011 | 0,1837 (0,9 s) | 0,1224 (0,7 s) | 0,1020 (38,1 s) | 0,1224 (6,5 s) |
| 0012 | 0,0457 (2,6 s) | 0,0483 (2,3 s) | 0,0648 (56,2 s) | 0,0635 (34,6 s) |
| 0015 | 0,3065 (2,9 s) | 0,2903 (2,3 s) | 0,2238 (55,9 s) | 0,2903 (31,0 s) |
| 0022 | 0,0705 (6,1 s) | 0,0597 (4,8 s) | 0,0266 (135,9 s) | 0,0920 (48,9 s) |
| 0023 | 0,0000 (114,6 s) | 0,0000 (0,7 s) | 0,0196 (36,5 s) | 0,2353 (1,6 s) |
| 0031 | 0,0921 (4,6 s) | 0,0513 (3,0 s) | 0,0461 (64,7 s) | 0,0796 (37,1 s) |

- **VLM** : 36 à 136 s par page (1 106 à 2 483 jetons d'entrée, 12 à 391 de sortie), pas les ~5 min annoncées : ces pages sont des crops d'articles. Aucun préambule (« Voici le texte… ») avec le prompt par défaut ; en revanche le modèle **déroule les lignes** en paragraphes, recolle les césures, modernise (`ß` → `ss` : *weiss, dass, Kenntniss, Fass* ; `« »` → `"` : 5,9 % de ponctuation typographique gardée strictement, contre 58,8 % pour Tesseract) et lit `Luxemburg` « Lürenburg ».
- **Correction (c)** : le 3 B **dégrade** (CER 0,0915 → 0,1110 ; 1 amélioré, 7 dégradés, 2 égaux) et efface un mot sur `0023` (« accueillie. » perdu, CER 0 → 0,2353). Le bilan de correction le montre — avec `--analyses` seulement.
- **Test inter-moteurs** : « Wilcoxon p = 0,2319, non significatif » à **trois** pipelines, « p = 0,0572 » à quatre : c'est un Friedman mal étiqueté (S11, confirmé sur données réelles).
- **Re-notation `--offline`** depuis l'archive (1,9 s, aucun appel) : agrégats, scores par document, tests inter-moteurs, usages et analyses **identiques** au run d'origine ; seul le manifeste diffère — horodatage, et l'**ordre** de `candidate_types` (D4).
- **`cinoc compare`** : séquentiel (`--workers 1`) contre parallèle (`OMP_THREAD_LIMIT=1`, 4 workers) → Δ = 0 sur les 14 lignes, Tesseract est déterministe ; run (a)+(b) contre run (a)+(b)+(c) → Δ = 0 sur les pipelines communs, `—` pour le nouveau.
- **Archive réutilisée** : ajouter (c) n'a rejoué aucun appel VLM (10 unités rechargées, scores identiques) ; les 19 unités en échec du premier essai (D1) ont été retentées en reprise normale, comme prévu.

## Défauts trouvés — et leur session

Gravité : **●** fausse un chiffre ou perd des pages · **◐** trompe ou bloque l'utilisateur · **○** inconfort.

| # | | Défaut (reproduction) | Session |
|---|---|---|---|
| D1 | ● | **Tesseract en parallèle perd presque toutes les pages.** `cinoc run` au défaut (`--workers` = 4 CPU) : **19/20 unités `failed`** (« Tesseract process timeout », 120 s), pour 1,4 à 3,4 s par page en direct ; `--workers 2` échoue aussi. Cause : chaque processus `tesseract` ouvre autant de fils OpenMP que de cœurs — sursouscription. `OMP_THREAD_LIMIT=1` → 20/20 en 19 s. Tout utilisateur de Tesseract sur une machine multicœur y tombe. | **S10b** (avancé de S28) — corrigé en S10b (D-282) : 20/20 `ok` en 19 s au défaut |
| D2 | ◐ | Ce run à 19/20 échecs **sort en code 0**, sans bilan : seules 19 lignes de journal le disent. | S10b — corrigé en S10b (D-282) : bilan, code de sortie 3 |
| D3 | ○ | Le délai dépassé sous contention est classé motif **`moteur`**, alors que le moteur n'y est pour rien. | S20 |
| D4 | ◐ | **`RunResult` non déterministe octet pour octet** : `view_specs[].candidate_types` (un `frozenset`) sort `[raw_text, corrected_text]` puis `[corrected_text, raw_text]` d'un run à l'autre de la même spec (hachage des chaînes randomisé) — invariant §12 « même rapport ». Les chiffres, eux, sont identiques. | S10b — corrigé en S10b (D-282) |
| D5 | ◐ | **Chemins absolus locaux dans le `RunResult`** : `documents[].image_ref` (40 fois), `manifest.artifacts_dir`, et le message d'échec (chemin de l'image) — à publier tel quel, une archive dit l'arborescence (et le nom d'utilisateur) de qui l'a produite. | S10b — corrigé en S10b (D-282) |
| D6 | ● | **Le rapport annonce des macro-moyennes, il affiche des micro** : « Les agrégats affichés sont des macro-moyennes par document, sauf mention « micro » » ; or le CER de `tesseract_fra_deu` vaut 0,1038 (micro) quand la moyenne des pages vaut 0,1068 (µ 10,7 % de la boîte à moustaches), et aucune mention « micro ». | S12 — corrigé en S12 (D-284) : la méthodologie dit « agrégats micro, Σ erreurs / Σ longueurs de référence » (FR/EN), et l'IC est celui de ce ratio — 0,1038 [0,0676 ; 0,1504] re-noté hors ligne |
| D7 | ● | Friedman étiqueté « Wilcoxon » à 3 et 4 pipelines ; 7 lignes « significatif / non sig. » sans correction. Confirmé sur données réelles. | S11 — corrigé en S11 (D-283) : « Friedman : p = 0,2319 » (3 pipelines) et « 0,0572 » (4), corrigées de Holm sur 7 tests ; aucune paire significative avec 10 documents, dit comme tel |
| D8 | ● | **Le saut de ligne compte comme une erreur face à l'espace** : un VLM qui déroule ses lignes est pénalisé d'une substitution par ligne. CER du VLM 0,0530 en `nfc`, **0,0406** en `flat_text` (−23 %), Tesseract 0,0915 → 0,0900 ; `0023` : 0,0196 pour un texte exact sur une ligne. L'apostrophe `’`/`'` pèse aussi (0,0530 → 0,0488). La question E5 de la campagne (VLM direct) en dépend. | S13 |
| D9 | ◐ | **Calibration attribuée au mauvais étage** : le pipeline OCR → LLM affiche l'ECE de son OCR (0,1234, 1 148 jetons, identique à Tesseract seul) alors que la vue note le texte corrigé. | S13 |
| D10 | ● | **Durées héritées de l'archive sans le dire** : une unité reprise garde la durée de sa première exécution — ici 114,6 s pour `0023`, mesurée sous la contention de D1 — d'où « 147,2 s, 244,6 pages/h » pour `tesseract_fra_deu` contre 1 410 pages/h pour l'autre Tesseract. | S20 |
| D11 | ○ | Le rapport par défaut (mode rapide) ne montre **aucune durée** : qu'un VLM soit 25× plus lent que Tesseract ne se lit qu'avec `--analyses`. Ni le CSV. | S17 (colonnes par défaut) |
| D12 | ○ | « Configuration & reproductibilité » de chaque moteur affiche **Paramètres —** alors que « Composition des chaînes » montre `lang`, `model`, `prompt`… | S10b — corrigé en S10b (D-282) |
| D13 | ◐ | **`--check` valide l'invalide** : `lang: grc+frm` (non installé) et `model: qwen9:inexistant` → « Spec valide ». | S22 (modèle) · S28 (langues Tesseract) |
| D14 | ◐ | **Réglage inconnu accepté en silence** : `tempreature: 0.5`, `prompt_name: …` dans `adapter_kwargs` → « Spec valide », puis ignorés à l'exécution. | S23 |
| D15 | ◐ | `cinoc list prompts` dit « à poser en `prompt_name` d'un concurrent », mais une spec YAML ne connaît pas `prompt_name` (seul le composeur web le lit) : il faut recopier le prompt. | S23 |
| D16 | ○ | Aucun prompt curé **zero-shot** pour la presse du XIXᵉ (seulement `imprime_ancien`, médiéval) : la variante E5 n'a que le prompt générique. | S30-S32 |
| D17 | ○ | `cinoc list models ollama` répond « aucun modèle canonique » alors que le serveur sert `qwen2.5vl:3b` et que `list_installed_models` existe (le web s'en sert). | S22 |
| D18 | ● | **Modèle Ollama tracé par son tag** (`qwen2.5vl:3b`) : un `ollama pull` change les poids sous le même tag, sans toucher le manifeste ni la clé d'unité ; le digest est lisible (`/api/tags`, `/api/show`). | S22 |
| D19 | ● | **Données de langue Tesseract hors manifeste et hors clé** : seul `tesseract 5.3.4` est tracé ; changer `fra.traineddata` (paquet 4.1.0 ici) change la sortie sans invalider l'archive. | S28 |
| D20 | ◐ | Archive **45 Mo** pour 10 pages (corpus 12 Mo) : l'image de chaque page est recopiée **par pipeline** (limite connue de D-279) ; 37 pages × 6 variantes ≈ 200 Mo à publier. | S30-S32 |
| D21 | ○ | `cinoc corpus import zip` conseille de « coller son bloc `corpus:` dans un fichier de run » : collé ailleurs, il échoue sur « chemin inexistant : '0000.gt.txt' » (chemins relatifs à `corpus.yaml`, message qui ne le dit pas). Et il écrit `id: 0009` sans guillemets (un lecteur YAML 1.2 y lit l'entier 9). | S10b — corrigé en S10b (D-282) |
| D22 | ○ | `cinoc compare` : rapport français à décimales en point (`0.1042`), et A/B nommés par `run_id` — indiscernables quand il est le même (« A = pilote-bnl-s10 · B = pilote-bnl-s10 »). | S28 (parité i18n) |
| D23 | — | Conventions de la GT BNL à déclarer dans le protocole, pas à corriger : `ſ` normalisé en `s` (le modèle Fraktur sort `ſ` : CER 0,0915, cer_diplo 0,0763), `⸗` gardé en fin de ligne, `�` (U+FFFD) dans `0003` pour un caractère illisible. Vues de la campagne : `nfc` + diplomatique + sans césure + plate. | S30-S32 |
| D24 | ◐ | **La CLI ne compose pas de pipeline** : `cinoc list recipes` décrit `ocr_simple`, `ocr_puis_llm`… mais rien ne les instancie en YAML ; le composeur web, lui, construit la spec. Pipelines et vues s'écrivent à la main (règle de parité, `CLAUDE.md` §8.4). | S25-S26 |

Hors défauts : le parcours ZIP → `corpus import` → `--check` → `run` →
`--resume-dir` → `--offline` → `compare` **tient** sur le paquet installé ; la
reprise n'a rejoué aucun appel VLM ; les échecs sont listés au rapport avec leur
motif et « n notés / n attendus » ; la philologie, le bilan de correction et la
taxonomie lisent ce qu'on attend d'eux (modernisation du VLM, dégradation du
correcteur).

## Ce qui n'a pas été fait

- Aucun correctif sur place : D1, le seul qui bloquait, se contourne par
  `OMP_THREAD_LIMIT=1` ; le corriger demande de lancer le binaire soi-même
  (pytesseract ne transmet pas d'environnement), ce qui dépasse « quelques
  lignes » et recoupe « Tesseract en un appel » (S28).
- Pas de `--repeat` (le VLM tourne à `temperature 0`, `seed 0` ; la dispersion
  inter-runs reste l'affaire de S30).
- Pas de Mistral (clé non fournie) ; pas de dinglehopper (S18).
