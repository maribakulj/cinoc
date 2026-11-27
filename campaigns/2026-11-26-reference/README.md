# 2026-11-26 — Campagne de référence : partie sans clé (S30, D-304) et exécution Mistral (S31, D-312)

**Rôle : la campagne d'ablation publiée de P5h** (`PLAN_FIN_MIGRATION.md`
§« P5h ») — **exécutée ici en entier, pas encore publiée.** Arbitrage **A6**
(D-271) : Tesseract, un VLM **local** (Ollama, `qwen2.5vl:3b`) et Mistral ;
**plafond 10 €** pour pilote et campagne réunis (le pilote n'a rien coûté),
estimation montrée avant tout appel facturé.

S30 a fait tout ce qui ne demande ni clé ni publication (specs, conventions,
partie sans clé exécutée et recoupée, estimation). **S31** a exécuté la partie
Mistral : cinq répétitions (une pour E4 Mistral), chacune archivée à part,
re-notée hors ligne à l'identique et recoupée par dinglehopper ; **dépense réelle
2,49 € mesurés (≈ 2,51 € avec ce qu'un run interrompu a payé sans l'archiver),
contre 2,14 € estimés** pour le périmètre de S30 — détail
[ci-dessous](#fait-en-s31--lexécution-mistral). Reste :

- **S32** — la publication (dataset HF + DOI Zenodo) : attend l'**accord du
  mainteneur**.

> Les chiffres de ce dossier sont ceux d'une campagne **non publiée** et, pour
> le VLM local, d'un modèle de 3 B sur CPU : ils ne sont **pas** à citer avant
> S32. Le README du dépôt en montre cinq lignes de la partie sans clé comme
> **exemple partiel**, relues dans les `RunResult` de S30 par
> `tests/guardrails/test_readme_result.py` (S33, D-305) ; son tableau complet
> attend S32.

## Fichiers

| fichier | rôle |
|---|---|
| `bnl.yaml` | spec complète `37-GT-BNL` : 15 pipelines (5 sans clé + 10 Mistral), 4 vues — **exécutée en S31** (répétition 1) |
| `bnl-repetitions.yaml` | la même sans E4 Mistral (14 pipelines) — re-note les répétitions 2-5 |
| `bnl-sans-cle.yaml` | ses 5 pipelines sans clé, à l'identique — **exécutée en S30** |
| `bnl-mistral.yaml` | ses 10 pipelines Mistral, à l'identique — **exécutée en S31** |
| `dresden.yaml` | spec complète Dresden : 13 pipelines (4 sans clé + 9 Mistral) — **exécutée en S31** |
| `dresden-sans-cle.yaml` | ses 4 pipelines sans clé — **exécutée en S30** |
| `dresden-mistral.yaml` | ses 9 pipelines Mistral — **exécutée en S31** |
| `bnl.repetition-<k>.run_result.json` | `RunResult` v5 de la répétition `k` (1 à 5), re-notée hors ligne sur son archive (1,8 à 1,9 Mo, aucun chemin d'utilisateur) |
| `dresden.repetition-<k>.run_result.json` | idem (540 Ko) |
| `bnl.variance.json`, `dresden.variance.json` | fourchettes `--repeat 5` (min, médiane, max par pipeline × vue × métrique) |
| `bnl-sans-cle.run_result.json` | `RunResult` du run S30 (566 Ko) — **avant D-311** : ses E3/E4 « règles » sont remplacés par ceux des répétitions |
| `dresden-sans-cle.run_result.json` | idem (169 Ko) |

Chaque pipeline d'une spec sans clé est, au caractère près, un pipeline de la
spec complète, avec les mêmes réglages de briques — la clé d'unité en dérive,
donc la spec complète **relit** ces unités au lieu de les rejouer (vérifié :
`cinoc run bnl.yaml --offline` sur l'archive S30 trouve les 185 unités sans clé
et ne réclame que les 259 unités Mistral ; Dresden : 40 trouvées, 60
réclamées). Verrouillé par `tests/app/test_campaign_specs.py`.

Les specs ne tournent qu'**à côté de leur corpus importé** (chemins relatifs) :

```bash
# 37-GT-BNL (le dépôt, corpus/ — CC0, BnL)
(cd corpus/37-GT-BNL && zip -q -X /tmp/bnl37.zip *.png *.xml)
cinoc corpus import zip /tmp/bnl37.zip --dest bnl --name 37-GT-BNL   # GT dérivée de l'ALTO
cp campaigns/2026-11-26-reference/bnl*.yaml bnl/
# Dresden (dataset curé D-207, révision épinglée ; extra [huggingface])
cinoc corpus import curated Ma-Ri-Ba-Ku/Cinoc-Dresdner.Hofdiarium.1665-Mscr.Dresd.K.80 \
  --revision db171cc5d4117cfce3315ffc9bce01f29f4da7b7 --dest dresden --name dresden-k80-1665
cp campaigns/2026-11-26-reference/dresden*.yaml dresden/
```

L'import ZIP de `37-GT-BNL` (29 Mo zippé) était **refusé par la CLI** — le
quota du dépôt web (25 Mo) s'y appliquait ; corrigé en S30 (D-304).

## Protocole

**Corpus.** `37-GT-BNL` : 37 crops d'articles de presse luxembourgeoise
(FR + DE Fraktur), 300 DPI, 22 138 caractères de GT, 522 lignes. Dresden :
`Mscr.Dresd.K.80` (1665), 10 pages de Kurrent manuscrit, images IIIF 1600 px de
large servies par HF à la révision épinglée, 10 363 caractères, 218 lignes,
`ſ` conservé dans la GT. Le corpus BnF (A4) n'entre pas : arbitrage non rendu.

**Expériences** — chaque pipeline nomme `lecture` l'étape qui lit le document,
ce que la vue `lecture` note avant toute correction (ablation par cible
d'étape, P5e 1b) :

| | chaîne | BNL | Dresden | exécuté |
|---|---|---|---|---|
| E0 | OCR | `tesseract` (`Fraktur+fra`), `mistral-ocr` | `tesseract` (`Fraktur`), `mistral-ocr` | Tesseract : S30 · Mistral : S31 |
| E1 | segmentation → OCR par région | `tesseract_layout` → `tesseract` ; `tesseract_layout` → `mistral` (VLM par région) | idem | idem |
| E2 | OCR → correction LLM | `tesseract` → `mistral` ; `mistral-ocr` → `mistral` (prompt curé `correction_press_19c_european`) | idem, prompt générique | S31 |
| E3 | segmentation → OCR par région → correction structurée | `saknussemm` `rules` (validation de chaîne) ; `saknussemm` producteur `mistral` sous `mistral-small-latest`, `ministral-8b-latest`, `ministral-3b-latest` | idem | `rules` : S30, refait après D-311 · modèles : S31 |
| E3 témoin | segmentation → OCR par région → correction LLM **libre** | même lecture qu'E3, corrigée par la brique `mistral` (`text_only`, `mistral-small-latest`, température 0, `max_tokens` au défaut 8192, prompt d'E2) | idem | S31 |
| E4 | OCR → score de qualité → correction **sélective** | `saknussemm` `rules` + QE `heuristic` (validation) ; `saknussemm` `mistral` + QE `dalembert`, `qe_skip 0.5` | **non déclarée** | validation : S30 · `mistral` : S31 |
| E5 | VLM direct sur la page | `qwen2.5vl:3b` (local) ; `mistral` | idem | local : S30 · Mistral : S31 |

Modèles Mistral : `mistral-small-latest` (chat et vision ; le *snapshot* servi
est tracé par `served_models`) et `mistral-ocr-latest`, **à confirmer par
`cinoc run bnl.yaml --check` avec la clé** (S22b : le fournisseur est
interrogé) — confirmés en S31 (aucune note), comme `ministral-8b-latest` et
`ministral-3b-latest` ; `max_tokens` 2048 (page), 1024 (région). E4 n'est pas déclarée sur
Dresden : `dalembert` est un MLM du français d'Ancien Régime, et le seul autre
scoreur (`heuristic`) a une AUC de 0,500 — aucun scoreur ne sait dire quelle
ligne de Kurrent allemand corriger. Sur BNL, moitié allemande, le seuil 0,5 de
`dalembert` n'est pas calibré sur ce corpus : limite à dire au rapport de S31.

**Ce que la correction structurée reçoit (S31).** Le producteur `mistral` de
`saknussemm` est `LLMEditProducer` : **texte seul**, aucune image — la
comparaison `mistral-small` / `ministral-8b` / `ministral-3b` d'E3 est une
comparaison de **correction de texte**, que ces modèles soient multimodaux ou
non. Le producteur `mistral_vision` (`VisionEditProducer`) découpe chaque ligne
dans le scan d'après sa géométrie ; or les lignes que le fan-out tire d'une
région lue par Tesseract n'en ont pas (`pipeline/fanout.py`,
`_lignes_reconnues` : `Line` sans `geometry`, même après D-311), et le pont les
passe en `Coords(0, 0, 0, 0)` (`adapters/layout/_saknussemm_bridge.py`,
`_coords`) — il ne recevrait aucune image utile. Il n'entre pas dans la
campagne.

**Le témoin d'E3, seule comparaison qui isole `saknussemm`.** E3 et E2 diffèrent
d'au moins quatre variables (texte corrigé : page entière contre lecture
segmentée ; prompt ; `max_tokens` ; rampe de température). Le témoin garde la
lecture d'E3 et son modèle, et remplace `saknussemm` par la correction libre :
E3 (`mistral-small`) contre témoin ne diffère que par le correcteur — son prompt
(celui de `saknussemm` contre celui d'E2), son contrat (édition ligne à ligne en
JSON contre texte libre), ses reprises (3 tentatives à 0,0 / 0,3 / 0,5 contre
une à 0,0) et son plafond (aucun contre 8192). Le préfixe (segmentation,
Tesseract par région) est **ré-exécuté** dans l'unité du témoin, pas relu —
l'archive garde une unité par pipeline, sans cache par étape ; il est
déterministe, et la vue `lecture` le montre : 0,0639 (BNL) et 0,7775 (Dresden),
écart-type nul, comme E3.

**Répétitions.** `--repeat 5` pour les pipelines stochastiques (tout ce qui
appelle Mistral ; Mistral OCR compris, ce qui mesure son déterminisme au lieu de
le supposer) — **sauf E4 Mistral, une répétition** (S31 : son QE D'AlemBERT
coûte ~400 s de CPU par page partagé, ~20 h pour cinq passages ; il ne saute
qu'environ 9 % des jetons d'entrée d'E3-small — 67 628 contre 74 556 en moyenne
—, dont la dispersion est mesurée sur cinq). **Une unité déterministe
(Tesseract, règles) n'est exécutée qu'une fois et recopiée** dans chaque
répétition ; les unités `qwen2.5vl:3b` sont celles de S30 (une exécution),
recopiées, **non répétées** : aucune dispersion n'est donnée pour elles.
`--repeat` et `--resume-dir` s'excluaient : depuis S30 chaque répétition
archive dans son dossier neuf (`<archive>/repetition-<k>`) et
`--offline --repeat 5` les re-note toutes. Tesseract est déterministe (pilote
D-281 : Δ = 0 séquentiel/parallèle) ; le VLM local tourne à `temperature 0`,
`seed 0`.

**Vues** (les deux défauts de D-285, plus l'ablation et une convention) :

| vue | profil | métriques | rôle |
|---|---|---|---|
| `texte` | `flat_text` (défaut) | cer, wer, cer_diplo, cmer, mer, unanchored_trigrams | le chiffre principal : sortie la plus aval |
| `texte (lignes)` | `keep_line_breaks` (défaut) | cer | sauts de ligne comptés — le point de comparaison dinglehopper |
| `lecture` | `flat_text`, `target_step: lecture` | cer, wer, cer_diplo | ablation : la lecture avant correction |
| `sans césure` | `dehyphenated` | cer | convention `⸗` (ci-dessous) |

**Conventions de la GT BNL (D23), déclarées par les mécanismes existants —
aucun profil, aucune table neuve.** Les tables personnalisées n'existent pas au
niveau d'une spec (seul l'aperçu web en lit une, jamais persistée) ; les profils
et la métrique diplomatique suffisent :

- **`ſ` → `s`** : la GT écrit `s` partout (0 `ſ` dans les 37 GT) quand le
  modèle Fraktur de Tesseract sort `ſ`. La convention se lit sur **`cer_diplo`**
  (`texte`, `lecture`) : CER après repli `ſ` → `s` **des deux côtés**, sous la
  même convention de blancs (`cer − cer_diplo` isole `ſ`, D-285). E0 Tesseract :
  CER 0,0584, `cer_diplo` 0,0495 — 15 % de son erreur est un `ſ` fidèle à
  l'imprimé. Sur Dresden, dont la GT **garde** `ſ` (211 occurrences), `cer` est
  le chiffre de la convention et `cer_diplo` en mesure l'écart.
- **`⸗` gardé** : la GT conserve la césure telle qu'imprimée (36 `⸗` en fin de
  ligne, 9 pages). `texte` et `texte (lignes)` la comptent ; **`sans césure`**
  (`dehyphenated`) recolle `⸗`/`-`/`‐`/`‑`/`–`/`¬` + saut de ligne **des deux
  côtés** — un moteur qui recolle n'y paie pas la césure. `sans césure` compte
  les sauts de ligne : elle se compare à `texte (lignes)` (écart = la césure, à
  l'écrasement des blancs d'une ligne près), pas à `texte`. E5 qwen : 0,0485 →
  0,0415 (il recolle) ; E0 Tesseract : 0,0610 → 0,0609 (il ne recolle pas).
- **`�` de `0003`** : un `U+FFFD` isolé (« vermindern � sich », `CC="9"` à
  l'ALTO) pour un caractère illisible. **Gardé et compté**, pas exclu : un
  moteur qui lit quelque chose y paie 1 édition, un moteur qui n'écrit rien 2
  (le `�` et son espace) — au plus 2 éditions sur 22 138 caractères, soit
  < 0,0001 sur l'agrégat micro, et 1 à 2 sur les 669 de `0003`. L'exclure
  (`char_exclude`) ne l'aurait pas neutralisé : la vue retire le caractère
  **après** le profil, l'espace double qui reste coûte toujours une édition.
  Aucune page n'est retirée.

**Prompt zero-shot (D16) : le prompt générique, déclaré.** Un prompt curé
« presse XIXᵉ européenne » (FR/DE Fraktur : une ligne imprimée par ligne,
césures gardées, aucune modernisation, guillemets typographiques) a été écrit
et mesuré contre le générique avec `qwen2.5vl:3b` sur `0003`, `0006`, `0031` :
CER `texte` **0,0260 contre 0,0237** (`0003` 0,0254 contre 0,0179, les deux
autres égales), `texte (lignes)` 0,0423 contre 0,0401 ; le modèle de 3 B a
ignoré ses consignes (lignes déroulées, césures recollées, *Uebrigen* →
*Übrigen*, *hinsichts* → *hinsichtlich*). Il dégradait : il n'est **pas** livré
(sans consommateur). E5 et E1-VLM emploient le prompt de transcription
générique de Cinoc (`DEFAULT_TRANSCRIPTION_PROMPT`, au manifeste) ; E2 sur BNL
garde le prompt curé de correction du pilote, Dresden le générique. En route :
trois prompts zero-shot curés finissaient sur « Image (base64) : {image_b64} »,
envoyé tel quel au modèle — retiré, et verrouillé par un test.

**Défaut méthodologique d'août** évité par construction : aucun pipeline
n'entre par `alto_source`, aucune césure de GT n'est mêlée au texte d'un moteur.

**Oracle (D-290).** dinglehopper 0.11.0 exécuté comme sa CLI sur chaque sortie
notée de la vue `texte (lignes)`, rapproché par la chaîne d'écarts du golden
(`tests/evaluation/test_dinglehopper_golden.py` : `cinoc` → `blancs` →
`invisibles` → `sbb` → `graphemes`), dans le venv d'oracle (extra `oracle` +
dinglehopper/ocrd `--no-deps`).

## Fait en S30 — la partie sans clé

Versions : `tesseract 5.3.4`, `Fraktur.traineddata` `sha256:ac985c30…`,
`fra.traineddata` `sha256:ced03756…` (au manifeste), `ollama:qwen2.5vl:3b`
digest `fb90415c…` ; 4 cœurs CPU, `--workers 2`. **`code_version` du manifeste
périmée** (`0.1.1.dev159+g78c21e6ef`) : celle de l'installation éditable, que
`setuptools_scm` fige à l'installation — S31 réinstalle avant de lancer.

| | BNL | Dresden |
|---|---|---|
| unités | 185, **toutes `ok`** | 40 : 33 `ok`, 1 `truncated`, **6 `failed`** (E5 local, « arrêtée (délai) » à 600 s) |
| durée | 42 min 22 s (dont E5 : 4 369 s, 47 à 186 s par page) | 49 min 8 s |
| archive | **37,4 Mo** (images 34,1 Mo, une par page) | 9,0 Mo (images 8,1 Mo) |
| même archive avant D20 | 173,6 Mo (image recopiée sous chacune des 185 unités) | 33,3 Mo (40 copies) |
| re-notation `--offline` | 3,8 s ; `pipelines`, `documents`, `cross_engine`, `analyses` **identiques**, `usage` identique hors `resumed` (185/185 relues) ; manifeste : seules les deux horloges | 5,3 s ; idem (40/40) |
| dinglehopper | **185/185** : CER du `RunResult` = maillon `cinoc`, dernier maillon = dinglehopper ; 57/185 égaux sans pont, écart moyen 0,0045 — tout l'écart est `normalize_sbb` (128 unités : `’`/`'`, `⸗`/`-`) | **34/34** notées ; 33/34 égales sans pont (1 unité : espaces multiples) |

CER micro par vue (non citables) :

| BNL | `texte` | `cer_diplo` | `texte (lignes)` | `lecture` | `sans césure` | WER |
|---|---|---|---|---|---|---|
| E0 · tesseract | 0,0584 | 0,0495 | 0,0610 | 0,0584 | 0,0609 | 0,2372 |
| E1 · segmentation → tesseract | 0,0639 | 0,0550 | 0,0641 | 0,0639 | 0,0643 | 0,2521 |
| E3 · … → saknussemm (règles) | 0,0639 | 0,0550 | 0,0641 | 0,0639 | 0,0643 | 0,2521 |
| E4 · … → saknussemm sélectif (règles, QE) | 0,0639 | 0,0550 | 0,0641 | 0,0639 | 0,0643 | 0,2521 |
| E5 · qwen2.5vl:3b (local) | **0,0341** | 0,0341 | 0,0485 | 0,0341 | 0,0415 | 0,1559 |

| Dresden | `texte` | `cer_diplo` | `texte (lignes)` | notés |
|---|---|---|---|---|
| E0 · tesseract | 0,7563 | 0,7557 | 0,7683 | 10/10 |
| E1 · segmentation → tesseract | 0,7775 | 0,7766 | 0,7958 | 10/10 |
| E3 · … → saknussemm (règles) | 0,7775 | 0,7766 | 0,7958 | 10/10 |
| E5 · qwen2.5vl:3b (local) | 1,8614 | 1,8523 | 1,8706 | 4/10 |

Lecture : sur BNL la segmentation Tesseract ne fait pas mieux que la page
entière (9 pages mieux, 11 moins bien) ; les règles de `saknussemm` ne
changent rien (comme en août) — E3/E4 « règles » **valident la chaîne**
(segmentation → région → `LAYOUT` → correction structurée → `CORRECTED_TEXT`,
routage QE compris), elles ne mesurent pas une correction. Le VLM de 3 B fait
mieux que Tesseract sur 23 pages sur 37. Sur Dresden, Tesseract n'a aucun
modèle de Kurrent (CER ~0,75 à 0,84 sur deux pages quel que soit le modèle de
langue essayé : `deu`, `Fraktur`, `deu+Fraktur`, `frk`) et le VLM local
**hallucine** (CER > 1, une sortie bouclée jusqu'au plafond de 2 048 jetons) ou
dépasse 600 s par page : Dresden mesure ce qu'un moteur généraliste ne sait pas
faire, et c'est ce qu'E0/E5 Mistral y diront.

> **Après D-311 (S31)**, la ligne de layout d'une région n'est plus le bloc
> entier : les règles corrigent enfin. Les E3/E4 « règles » ci-dessus (et dans
> `*-sans-cle.run_result.json`) sont **remplacés** par ceux des répétitions :
> BNL E3 0,0550, E4 0,0624 ; Dresden E3 0,7778. Les autres lignes ne changent
> pas en vue `texte` (E1 `texte (lignes)` : 0,0641 → 0,0639 sur BNL,
> 0,7958 → 0,7949 sur Dresden).

## Fait en S31 — l'exécution Mistral

**Procédure suivie** (2026-11-27, 4 cœurs CPU partagés avec la session locale S31L) :

1. roue construite depuis le dépôt (`pip wheel --no-deps`), venv neuf, extras
   `[mistral,saknussemm,qe,huggingface,images]` — `[images]` manquait à la liste
   de S30 : sans Pillow, toute découpe de région échoue (`crop_region`), constaté
   au premier essai, sans appel payé ; `code_version` des `RunResult` :
   `0.1.1.dev274+g32a56aae4` (le code ne change plus après ce commit ;
   `torch 2.15.0+cpu`, `saknussemm 0.9.0`, `mistralai 3.9.0`) ;
2. `cinoc run bnl.yaml --check` et `dresden.yaml --check` avec la clé : modèles
   confirmés par le fournisseur, aucune note ;
3. **essai sur 3 pages BNL** (`0003`, `0006`, `0031`), toutes les chaînes Mistral :
   **0,0321 € réels contre 0,0285 € estimés au prorata** (× 1,13 ; seuil d'arrêt
   × 1,5) ; témoin d'E3 essayé à part : 0,0007 € ;
4. deux défauts trouvés en route, chacun corrigé avant la suite : (D-311, S31L)
   le fan-out donnait **une** ligne par région, sauts de ligne compris, et
   `saknussemm` refusait toute correction (trois tentatives payées puis repli) ;
   (D-312) l'archive n'était écrite qu'à la fin du run — un run coupé perdait
   tout ce qu'il avait payé ; désormais chaque unité est archivée à sa fin,
   atomiquement. D-311 change la clé des seules étapes à fan-out : E1/E3/E4 sans
   clé ont été ré-exécutés (Tesseract, règles : 111 unités BNL, 20 Dresden), une
   fois, puis **recopiés** dans chaque répétition ;
5. répétitions : chaque archive `repetition-<k>` semée de la partie sans clé
   (S30 + ré-exécution D-311), puis la partie Mistral seule
   (`*-mistral.yaml`, mêmes clés d'unité), une répétition après l'autre,
   dépense relevée après chacune ; E4 Mistral en répétition 1 seulement ;
   le témoin d'E3, ajouté après l'essai (contre-expertise), par une spec à lui
   seul, dans les mêmes archives ;
6. re-notation hors ligne, puis oracle sur chaque répétition (ci-dessous).

Durées : BNL 8 à 13 min par répétition (`--workers 3`), Dresden 6 à 8 min.
Archives : 58 à 60 Mo par répétition BNL, 16 Mo Dresden (elles gardent encore
les unités fan-out de S30, d'avant D-311, que plus aucune clé n'atteint : à
élaguer avant la publication, S32).

### Dépense réelle contre l'estimation

Dépense = jetons et pages que l'API a rendus, relus dans l'`usage` de chaque
unité archivée, × `pricing.json` (`mistral-small-latest` 0,14 / 0,55 €/Mtok,
`ministral-8b-latest` 0,14 / 0,14, `ministral-3b-latest` 0,09 / 0,09, Mistral
OCR 3,66 € / 1 000 pages). **Majorante** : l'entrée lue en cache (que Mistral
rend sur une part des appels) y est comptée au plein tarif d'entrée —
la table n'a aucun tarif de cache Mistral ; pour la même raison, la section
économie du rapport dit « jetons de cache non tarifés » et ne chiffre pas ces
chaînes. Cumul relevé après chaque répétition : jamais au-delà de 2,5 €.

| corpus | expérience | estimé € / passage (S30) | réel € / passage (moyenne) | passages | réel total |
|---|---|---|---|---|---|
| BNL | E0 · mistral-ocr | 0,1354 | 0,1354 | 5 | 0,6771 |
| BNL | E2 · tesseract → mistral | 0,0092 | 0,0071 | 5 | 0,0357 |
| BNL | E2 · mistral-ocr → mistral | 0,1446 | 0,1421 | 5 | 0,7106 |
| BNL | E1 · segmentation → mistral (VLM par région) | 0,0094 | 0,0081 | 5 | 0,0404 |
| BNL | E3 · … → saknussemm (mistral-small) | 0,0110 | 0,0241 | 5 | 0,1207 |
| BNL | E3 · … → saknussemm (ministral-8b) | ajout S31 | 0,0251 | 5 | 0,1256 |
| BNL | E3 · … → saknussemm (ministral-3b) | ajout S31 | 0,0222 | 5 | 0,1108 |
| BNL | E3 témoin · … → mistral (correction libre) | ajout S31 | 0,0072 | 5 | 0,0358 |
| BNL | E4 · … → saknussemm sélectif (mistral, QE dalembert) | ≤ 0,0110 | 0,0217 | **1** | 0,0217 |
| BNL | E5 · mistral (VLM) | 0,0087 | 0,0073 | 5 | 0,0365 |
| Dresden | E0 · mistral-ocr | 0,0366 | 0,0366 | 5 | 0,1830 |
| Dresden | E2 · tesseract → mistral | 0,0029 | 0,0018 | 5 | 0,0088 |
| Dresden | E2 · mistral-ocr → mistral | 0,0395 | 0,0408 | 5 | 0,2038 |
| Dresden | E1 · segmentation → mistral (VLM par région) | 0,0096 | 0,0106 | 5 | 0,0530 |
| Dresden | E3 · … → saknussemm (mistral-small) | 0,0052 | 0,0084 | 5 | 0,0421 |
| Dresden | E3 · … → saknussemm (ministral-8b) | ajout S31 | 0,0052 | 5 | 0,0261 |
| Dresden | E3 · … → saknussemm (ministral-3b) | ajout S31 | 0,0051 | 5 | 0,0254 |
| Dresden | E3 témoin · … → mistral (correction libre) | ajout S31 | 0,0026 | 5 | 0,0129 |
| Dresden | E5 · mistral (VLM) | 0,0050 | 0,0047 | 5 | 0,0235 |
| **total mesuré** | | | | | **2,4935 €** |

- **Périmètre de S30 : 2,16 € réels contre 2,14 € estimés** (× 1,01 ; E4 en une
  passe — à cinq, 2,24 €, × 1,05). Mistral OCR en fait 80 %, au centime près de
  l'estimation (une page facturée par page). La correction structurée coûte
  **2,2 fois** l'estimation (BNL 0,0241 contre 0,0110 € par passage) : les jetons
  de S30 avaient été mesurés sur la chaîne d'avant D-311, où chaque région
  n'était qu'une ligne refusée ; corrigée, elle envoie vraiment chaque ligne.
- **Ajouts de S31 : 0,34 €** (Ministral 8b 0,15 €, 3b 0,14 €, témoin 0,05 €).
  Les Ministral consomment 1,8 à 2,5 fois les jetons de `mistral-small` pour
  le même travail (BNL : 133 791 et 186 503 jetons d'entrée par passage contre
  74 556) — des reprises de `saknussemm` sur des éditions refusées.
- **Non mesuré, payé** : les unités d'un essai tué avant que l'archive n'écrive
  par unité (E1 × 3, E3 × 3, E4 × 1-3 pages, chaîne d'avant D-311) et au plus
  trois unités E4 en vol lors de l'arrêt de la répétition 1 (ci-dessous) :
  **≤ 0,012 €** d'après les jetons des mêmes unités archivées. **Total ≈ 2,51 €**,
  sous le plafond estimé (3,74 €) et sous les 10 € d'A6.

### Résultats — CER et WER micro, par vue, sur les répétitions

Moyenne ± écart-type (échantillon, n = 5) pour une chaîne **ré-exécutée cinq
fois** ; une valeur seule, marquée, sinon. ¹ déterministe (Tesseract, règles) :
une exécution, recopiée dans chaque répétition — **pas une mesure de
dispersion** ; ² E4 Mistral, une répétition ; ³ `qwen2.5vl:3b` local : une
exécution (S30), recopiée, non répétée (temperature 0, seed 0 ; le VLM
local relève de S31L). Les fourchettes min / médiane / max de toutes les vues et métriques
sont dans `*.variance.json`.

| BNL | n | `texte` cer | `texte` cer_diplo | `texte (lignes)` cer | `lecture` cer | `sans césure` cer | `texte` wer | notés | CER `texte` [min ; max] |
|---|---|---|---|---|---|---|---|---|---|
| E0 · tesseract ¹ | 1 | 0,0584 | 0,0495 | 0,0610 | 0,0584 | 0,0609 | 0,2372 | 37/37 | — |
| E1 · segmentation → tesseract ¹ | 1 | 0,0639 | 0,0550 | 0,0639 | 0,0639 | 0,0641 | 0,2521 | 37/37 | — |
| E3 · segmentation → tesseract → saknussemm (règles) ¹ | 1 | 0,0550 | 0,0550 | 0,0550 | 0,0639 | 0,0552 | 0,2150 | 37/37 | — |
| E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) ¹ | 1 | 0,0624 | 0,0550 | 0,0624 | 0,0639 | 0,0626 | 0,2455 | 37/37 | — |
| E5 · qwen2.5vl:3b (local) ³ | 1 | 0,0341 | 0,0341 | 0,0485 | 0,0341 | 0,0415 | 0,1559 | 37/37 | — |
| E0 · mistral-ocr | 5 | 0,0256 ± 0,0000 | 0,0256 ± 0,0000 | 0,0353 ± 0,0002 | 0,0256 ± 0,0000 | 0,0297 ± 0,0002 | 0,1322 ± 0,0002 | 37/37 | [0,0256 ; 0,0257] |
| E2 · tesseract → mistral | 5 | 0,0432 ± 0,0020 | 0,0407 ± 0,0021 | 0,0485 ± 0,0026 | 0,0584 ± 0,0000 | 0,0464 ± 0,0025 | 0,1475 ± 0,0052 | 37/37 | [0,0408 ; 0,0459] |
| E2 · mistral-ocr → mistral | 5 | 0,0352 ± 0,0022 | 0,0352 ± 0,0022 | 0,0460 ± 0,0025 | 0,0256 ± 0,0000 | 0,0403 ± 0,0023 | 0,1411 ± 0,0034 | 37/37 | [0,0333 ; 0,0388] |
| E1 · segmentation → mistral (VLM par région) | 5 | 0,0417 ± 0,0012 | 0,0415 ± 0,0009 | 0,0549 ± 0,0010 | 0,0417 ± 0,0012 | 0,0607 ± 0,0011 | 0,1662 ± 0,0051 | 37/37 | [0,0402 ; 0,0436] |
| E3 témoin · segmentation → tesseract → mistral (correction libre) | 5 | 0,0470 ± 0,0019 | 0,0443 ± 0,0020 | 0,0506 ± 0,0020 | 0,0639 ± 0,0000 | 0,0481 ± 0,0021 | 0,1621 ± 0,0045 | 37/37 | [0,0443 ; 0,0495] |
| E3 · segmentation → tesseract → saknussemm (mistral) | 5 | 0,0513 ± 0,0016 | 0,0453 ± 0,0015 | 0,0514 ± 0,0015 | 0,0639 ± 0,0000 | 0,0514 ± 0,0016 | 0,1876 ± 0,0013 | 37/37 | [0,0499 ; 0,0539] |
| E3 · segmentation → tesseract → saknussemm (ministral-8b) | 5 | 0,0636 ± 0,0065 | 0,0580 ± 0,0062 | 0,0637 ± 0,0065 | 0,0639 ± 0,0000 | 0,0638 ± 0,0066 | 0,2172 ± 0,0125 | 37/37 | [0,0565 ; 0,0733] |
| E3 · segmentation → tesseract → saknussemm (ministral-3b) | 5 | 0,0935 ± 0,0087 | 0,0860 ± 0,0084 | 0,0937 ± 0,0088 | 0,0639 ± 0,0000 | 0,0941 ± 0,0088 | 0,2748 ± 0,0113 | 37/37 | [0,0793 ; 0,1029] |
| E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) ² | 1 | 0,0533 | 0,0468 | 0,0533 | 0,0639 | 0,0534 | 0,2014 | 37/37 | — |
| E5 · mistral (VLM) | 5 | 0,0345 ± 0,0024 | 0,0343 ± 0,0020 | 0,0493 ± 0,0023 | 0,0345 ± 0,0024 | 0,0437 ± 0,0021 | 0,1654 ± 0,0061 | 37/37 | [0,0325 ; 0,0379] |

| Dresden | n | `texte` cer | `texte` cer_diplo | `texte (lignes)` cer | `lecture` cer | `sans césure` cer | `texte` wer | notés | CER `texte` [min ; max] |
|---|---|---|---|---|---|---|---|---|---|
| E0 · tesseract ¹ | 1 | 0,7563 | 0,7557 | 0,7683 | 0,7563 | 0,7681 | 0,9987 | 10/10 | — |
| E1 · segmentation → tesseract ¹ | 1 | 0,7775 | 0,7766 | 0,7949 | 0,7775 | 0,7947 | 1,3040 | 10/10 | — |
| E3 · segmentation → tesseract → saknussemm (règles) ¹ | 1 | 0,7778 | 0,7766 | 0,7953 | 0,7775 | 0,7951 | 1,3040 | 10/10 | — |
| E5 · qwen2.5vl:3b (local) ³ | 1 | 1,8614 | 1,8523 | 1,8706 | 1,8614 | 1,8717 | 2,4843 | 4/10 | — |
| E0 · mistral-ocr | 5 | 3,5902 ± 1,0550 | 3,5859 ± 1,0546 | 3,5946 ± 1,0555 | 3,5902 ± 1,0550 | 3,5955 ± 1,0557 | 4,0496 ± 0,6890 | 10/10 | [2,3922 ; 5,0602] |
| E2 · tesseract → mistral | 5 | 0,7571 ± 0,0005 | 0,7563 ± 0,0005 | 0,7691 ± 0,0004 | 0,7563 ± 0,0000 | 0,7690 ± 0,0004 | 0,9970 ± 0,0013 | 10/10 | [0,7566 ; 0,7580] |
| E2 · mistral-ocr → mistral | 5 | 0,6301 ± 0,0370 | 0,6261 ± 0,0365 | 0,6397 ± 0,0354 | 1,8294 ± 1,1579 | 0,6400 ± 0,0356 | 1,0176 ± 0,0800 | 10/10 | [0,5773 ; 0,6742] |
| E1 · segmentation → mistral (VLM par région) | 5 | 1,1532 ± 0,0293 | 1,1474 ± 0,0292 | 1,1668 ± 0,0291 | 1,1532 ± 0,0293 | 1,1679 ± 0,0292 | 1,6526 ± 0,0405 | 10/10 | [1,1196 ; 1,2000] |
| E3 témoin · segmentation → tesseract → mistral (correction libre) | 5 | 0,7780 ± 0,0052 | 0,7773 ± 0,0053 | 0,7955 ± 0,0056 | 0,7775 ± 0,0000 | 0,7953 ± 0,0056 | 1,2826 ± 0,0135 | 10/10 | [0,7745 ; 0,7872] |
| E3 · segmentation → tesseract → saknussemm (mistral) | 5 | 0,7772 ± 0,0002 | 0,7764 ± 0,0002 | 0,7946 ± 0,0001 | 0,7775 ± 0,0000 | 0,7943 ± 0,0001 | 1,3023 ± 0,0007 | 10/10 | [0,7770 ; 0,7775] |
| E3 · segmentation → tesseract → saknussemm (ministral-8b) | 5 | 0,7775 ± 0,0002 | 0,7766 ± 0,0002 | 0,7948 ± 0,0001 | 0,7775 ± 0,0000 | 0,7945 ± 0,0001 | 1,2960 ± 0,0015 | 10/10 | [0,7772 ; 0,7777] |
| E3 · segmentation → tesseract → saknussemm (ministral-3b) | 5 | 0,7773 ± 0,0003 | 0,7764 ± 0,0002 | 0,7947 ± 0,0004 | 0,7775 ± 0,0000 | 0,7945 ± 0,0004 | 1,2999 ± 0,0060 | 10/10 | [0,7771 ; 0,7778] |
| E5 · mistral (VLM) | 5 | 0,8449 ± 0,0348 | 0,8407 ± 0,0349 | 0,8592 ± 0,0358 | 0,8449 ± 0,0348 | 0,8591 ± 0,0358 | 1,1577 ± 0,0463 | 10/10 | [0,8125 ; 0,9009] |

**Lecture** (non citable avant S32) :

- **BNL.** Mistral OCR lit le mieux (0,0256) et **quasi déterministe** sur cinq
  passages (0,0256 à 0,0257) ; une correction LLM derrière lui **dégrade**
  (E2 · mistral-ocr → mistral 0,0352) quand elle améliore Tesseract
  (0,0584 → 0,0432). Le VLM Mistral sur la page (0,0345 ± 0,0024) égale le VLM
  local de 3 B (0,0341, une exécution) ; par région, il fait moins bien (0,0417).
- **Correction structurée.** Après D-311, les règles de `saknussemm` rendent
  exactement le CER diplomatique de la lecture (0,0639 → 0,0550 = `cer_diplo` de
  la lecture) : tout leur gain est le repli `ſ` → `s`. `mistral-small` corrige
  vraiment (0,0513, `cer_diplo` 0,0453) ; `ministral-8b` ne gagne rien en
  moyenne (0,0636 ± 0,0065 : sur 185 pages × passages, 55 mieux que la
  lecture, 30 moins bien — et de plus loin —, 100 inchangées ; `mistral-small` :
  116 / 14 / 55) ; `ministral-3b` **dégrade** (0,0935 ± 0,0087 ; 24 / 65 / 96).
  E4 sélectif (une répétition,
  0,0533) tombe dans la fourchette d'E3-small ([0,0499 ; 0,0539]).
- **Le témoin isole `saknussemm`** : sur la même lecture segmentée et avec le
  même modèle, la correction libre fait **mieux** que la correction structurée
  (0,0470 ± 0,0019 contre 0,0513 ± 0,0016 ; fourchettes disjointes,
  [0,0443 ; 0,0495] contre [0,0499 ; 0,0539]). Ce que `saknussemm` apporte n'est
  donc pas un meilleur CER ici : c'est l'identité des lignes préservée (un ALTO
  corrigé), au prix de 0,43 point de CER et de 3,1 fois les jetons
  (99 486 par passage contre 32 111).
- **Dresden.** Aucune chaîne ne lit le Kurrent. Mistral OCR **hallucine** et
  n'est **pas** déterministe (CER 3,59 ± 1,06, de 2,39 à 5,06 ; une page à 20,6
  en répétition 1 : sortie bouclée) ; la correction LLM derrière lui, plafonnée
  à 2 048 jetons, coupe la boucle (0,63, meilleur chiffre du corpus — par
  troncature, pas par lecture). Toute correction d'une lecture Tesseract
  (E2, E3 sous les trois modèles, témoin) reste à 0,757-0,778 : rien à
  corriger qui se lise. Le VLM Mistral (0,84) fait mieux que le local (1,86 sur
  4 pages notées), sans lire non plus.

### Re-notation hors ligne et oracle

- **Exécution = re-notation, sur chaque répétition** (`same.py` de session) :
  pour la partie Mistral et pour le témoin, `cinoc run … --offline` sur
  l'archive de la répétition rend `pipelines`, `documents`, `cross_engine`,
  `analyses` **identiques** et `usage` identique hors `resumed` (BNL 333 puis
  296 unités, Dresden 80, témoin 37 / 10) ; au manifeste, seules les deux
  horloges diffèrent — 20 comparaisons sur 20.
- **Spec complète, hors ligne, par répétition** : BNL 555 unités (répétition 1,
  `bnl.yaml`) puis 518 (`bnl-repetitions.yaml`), aucune en échec ; Dresden 130,
  dont les 6 E5 locales « arrêtée (délai) » de S30 et 1 tronquée. Ce sont les
  `*.repetition-<k>.run_result.json`. `--offline --repeat 5` (même spec sur les
  cinq) écrit `*.variance.json` ; son dernier run est identique à la
  répétition 5.
- **dinglehopper** (0.11.0, chaîne d'écarts du golden, vue `texte (lignes)`) :
  BNL **555/555** puis **518/518** × 4, Dresden **124/124** × 5 (les 6 unités
  en échec ne sont pas notées). Partout, le CER du `RunResult` = maillon
  `cinoc` et le dernier maillon = dinglehopper. Égaux sans pont : BNL 165 à 178
  unités par répétition, écart moyen 0,0055 à 0,0057, tout entier
  `normalize_sbb` (349 à 377 unités) à une unité de blancs près ; Dresden 122/124,
  écart 0,0001 (2 unités : espaces multiples).

### Traçabilité

Le manifeste ne porte l'empreinte ni des images ni des vérités terrain (constat
de la contre-expertise, au mainteneur) : elles sont ici. Image BNL hachée sur
disque après import ; image Dresden = le contenu que l'archive a rangé sous
`images/<sha256>` (re-haché pour vérification) ; GT = le `.gt.txt` que lit la
spec (BNL : dérivé de l'ALTO à l'import).

<details><summary>37-GT-BNL — 37 images, 37 GT (SHA-256)</summary>

| document | image (SHA-256) | vérité terrain (SHA-256) |
|---|---|---|
| `0000` | `d5d131f3c3c15d132b91b3dae8c372aabb634f21ebe36a7b2efda08f72ae00d1` | `4cf2b8650b1de1f3f6e308ef1472dae2af9aa4a8dbe8e66c4ed1b5e96f74c7b6` |
| `0001` | `c01e4afd754a0e12b68b04e5def9465212e1562c0d7d37e6ef4054e6fd1645b1` | `8dcc1d172ef7f6b80b40c0c57ae2f747549ef623a2529071f9e5ff06075bfb61` |
| `0002` | `228b7abdccbbeb13f8584d126afad378ab054564aa83be3bd1921558612e78cb` | `89411d49af7812df754cbe0bfa64f94dab519f846d6ff5b6885cfdd9d7ba110f` |
| `0003` | `c6b039b67aabec939d7f06be99be0a5c918feb53389c9ff3e09f76bd1dc0f605` | `bee5895099fa2f443bbb2f2b8a9310e49d72f5ba4143f55265b24201419be2fd` |
| `0004` | `fd6adf63a2d6ee77504caf9dd1207ba6702b8ed8691ba8db2eeb55d1c3cc8cff` | `79e308cb222e94ba1e475011b3b65e9e9c7e09337cfd483d926540f491618425` |
| `0006` | `76ff77512ef39022ed3ab4a920c346e9b9b17ec3144b9a554e5ccf2687614f26` | `e166487b687a7ffe3d1e694d07f4fa78d0f4decab981f2aba5c7553f3c6c4cc7` |
| `0007` | `90319ba6cca24db4cc022b5abd23fd824a8b5c5ee4dae3dc5df328d41911e731` | `4d54478d8e88ac879c4120d4f70782e7e5d66a309380370af6b4fbf728e76591` |
| `0008` | `d0b40e7f5ea57c41b81bcbb20d075d0911b7c4d75276e9d5b88371288f377b95` | `ef3499df284e2060cb8fedfe10841dae9ca8b32516e000904e36dbff3287cfd6` |
| `0009` | `31be0e2ee64e78cdb72877d67adc34b6702a92f408ce9518e19c8a12585e8326` | `463f9693eee80107747c21392a69f8eac33742daf1e3566b77d8a636d29eed11` |
| `0010` | `73d46886f159a10aee6a759f2f242a2fdc3a195f312a5347455c44d71b362f94` | `fffbbdbed195a8fcabbd29c1819d1804926af21e240c1618abbdbfa980dcc8ec` |
| `0011` | `43f1cb3c4e1c6a4ef72a05d50bee7a2bb24dc57d4ec56ded2cb9c0fa473763eb` | `3b538c7e24f73d67c4e5a15414d0958521607d88a3e23c4003c82e7cd81962d3` |
| `0012` | `10f117f540afebf5b2b062c35db02ee1c742ec155fcf59a734263d825cd69640` | `8081586e04d836de30558ef304ae31f5717b0d960f3c2e8ead9792ecd570d244` |
| `0013` | `45bc367dab914f7da3915020fa120a1a4738969bd723f8062250e11f5411bc64` | `4c8d9b7bad6a10c82f9e9221cb50b5cd3a80dff40c61ae0780a351f7a3463c7c` |
| `0014` | `107d6d0d3f0dbba87c9a5e11d5dc51524760f884aefb5f331a8a7d6cb929321a` | `61f9cf6a8429b919dfed62b4e6ae0119acacf8a777ab7b1e35185efddb24ce7b` |
| `0015` | `68b0aafb51758433cb00cc89538e67341112210977043686ce4c135afc6e3305` | `a8cfbe0e6271cbbb195bac985207751b7815a5c888c6966954d9cf2d2b166376` |
| `0016` | `7dbb646da8dee9317dac30050617543cd964d5b63bda3dd69b49ea7e97a61d9f` | `2a19d7bdb7bd15a022e3f1aaa428208ddde16ca93bc75f8eaa8a6b39408c348a` |
| `0017` | `bb3efdc9cf98e76d2bed4137d3ab4aa88131b4502fc3dcbb789a23b4436f9bc6` | `2fee07f0d57f5ea376ca629e8a50b203a05d89524e7501a94f4866357430a540` |
| `0018` | `e39e87d31591a1858f3de6fe68f6bb61c76d26c37c80acc5e87994a55cdfae9e` | `ae8da13dd090854378aa6067ec013fdcf5955bc4a7c88cb126fb016d88490878` |
| `0019` | `9a1ccdaa27da3562dd466e16aa6e42ef06dbf3dba143327d9502ecd6590087af` | `70c494ccf981cd8aa21280e80a5b1bec4ff6b7a500ca429cef2529ed0ae814d9` |
| `0020` | `c774ae0133a460ebd08672ce9c0c27cdb2f40b81ce2c640e210311bc21a71629` | `281428a76b703696a5f676a41f2fec463c1f2fd747902434cbd4bc078a53b37c` |
| `0021` | `49ee4f296649d082dd999edbad8cd929e2f4ddaea596d9c45b0297b3a856b75e` | `44d23b3cef4d42f14380e86a3d8afdfcd354ca3edce2aa4f09f7871d87547499` |
| `0022` | `491820f5973198af4fb289ec11446b12aa8e5c13bfe034bd05851cf33a13c340` | `23c00c8602ab1edc1f249a80d07dfa316117ce57f80eb1175be46cee041e3434` |
| `0023` | `ff293054502c16f882a33e514f4aec2fc77609c1c28e9eb44a665587257b81f4` | `ebcfe19d7440c8b307a59cdb34117c6e6e67bc6ec406dc682de6f170bf2e01f0` |
| `0024` | `b549289a6404a6c0352ba6bc1f184e89033b17cf0551316cb8e2f59c1eb78585` | `ed35eb92b98eec8499726a6e1073ec4a8fc7f3a4f52b12bf1443e85ee92dc50b` |
| `0025` | `9eadf05c090124f105440657a028e598b5845e6e765b8d436196a3a79a2c067e` | `7942dcb4fdbe6fca49731f9ed9ea196621111b9f6215feac22346139cf06fe17` |
| `0026` | `66dcfd40c2611a7b95079d2232e583d87f6a66de7ba28d0fa4b53be725b92f90` | `1fc0b5421dd9c39cb2698c8a37e78215be76518590a4adc2419307a6d6f3031a` |
| `0027` | `7efabbf9b539d84f3f79eb080fc295d0761d05fb4a1355f74f22af58f36b0c14` | `671edc464829a04fe6ea0255be72a7342300f6df97b38a4d1bb062fb8ba6587b` |
| `0028` | `6298974de504c48bd75eee89a69c73836ad265f35424da9793973139fbce795c` | `909b44e5ce98b58e550ea45c9091d1c8f4814ed78ecb39b2910a58543cc41e8a` |
| `0029` | `17a91b9cd83e3d3133a412d884effed4837649616018b7e633ad3b598241c7c0` | `f9bd8fc5f80869828d7d5a2c339c4463eaa57d3554acff8b447ed7dc6f63da0a` |
| `0030` | `21ed3b7021aad481b555c626531d7e2d1638ecc19f971279b50350182d48c1b6` | `dca7f06dd43e05b1d1acf78fb9cde5c837dd3de819bdf1d17b7c0aa2028eacc0` |
| `0031` | `eb91eaf71c703f6ffede01dd1f1d7d457fe35cefa2e9039c06472cdbc63ca033` | `3f281476e1534c87afcdcd416bf9549699231383e2b093a9bfe03c58003f5d8b` |
| `0032` | `2c34c0cbda278f79ddb00b55a4af335ab58a31f329de78df4ba085e28d487ab6` | `5058a4d98b543f8ac9e9527023f1ba63d3137ceedd0c17d2d6f245cf2c736bb0` |
| `0033` | `1587ebcb4fc190f4723405be24ec169870c18161f78498b0243823673451e6b4` | `d3ba8ce10da7f359e284d390ea308ffcc3ada956ad09978b295e379908b0bf86` |
| `0035` | `095cf6ad15124dd42a0d712c8f6a7261715b877fca639111fc38718305ce492f` | `5a0315b972e15e893fd1c80faff55ad3ca73493a4554bd2cc603d82a5a3647fe` |
| `0036` | `3853c21751e55f7c08073dfd80014a22fb9710e36ef104babb09917f31df2d4c` | `b8fd664c3bf3264e66fff81396b996e35e9602f18a70001137c63e78a0dc86fc` |
| `0037` | `2ffe90433a23053ee41872e47f28134bd37680db7ca3fc2c6b52c2b3c8f3d74a` | `a8f9ff4af7aa950b9be993a76a6869c184766ecc25db886c8d22b093e50a8dcf` |
| `0038` | `4adf16bc50a753a534b1c33a1f198f6efb900a506dd048dd50115a4191c30062` | `374e2b8fe4700524f5671ed7cf5af49882778b4107274425df5abbb6f4b487cc` |

</details>

<details><summary>Dresden — 10 images, 10 GT (SHA-256)</summary>

| document | image (SHA-256) | vérité terrain (SHA-256) |
|---|---|---|
| `Mscr.Dresd.K80_177` | `f7b0073a535565b692e97ea96ac3784aefa0699b2ff539f140d71369b7b2a93a` | `727153c1384649a7190d5e857f675746d83bf479608b89741c2295b639419587` |
| `Mscr.Dresd.K80_178` | `8c795ec1f6d267206118f884d1d30606d46a14b56069fcc134d8a57156dea263` | `40bb99953eaf0a213af2381c05d4e0111c0d65c58d786fbcf97b174c918acd40` |
| `Mscr.Dresd.K80_179` | `8a3e306e8e654188200917ac1117037a60848868786e62c9a155c37d3eefd2d5` | `d0ff15a7dce39706f0e855641dc895ae546539986a6c4ed1d5b4b2bc0896bb4a` |
| `Mscr.Dresd.K80_180` | `9765d35f0d8964e0321f173a0407d40ff0f7d95af3b1c6c18590d25ad6d0f53f` | `f114b41f3b14bda444cdd506d367f169ccd4cfb3e9050f7cec90e2dfd98c3655` |
| `Mscr.Dresd.K80_181` | `be3dfadd7a0a07f4df5b08a5587729f1ceb2c5fb88f19bbe3436d7e176a445da` | `060f1dd51899100993ad5543ef6fc12119f37f56829925dd86a51ada8abfe7fc` |
| `Mscr.Dresd.K80_182` | `e43d079c760f72e85b04fc054a95f08d42eab4c5224869fb03e52d3468f2cb38` | `32296006c9ff715b55ad8f4910b2cda720588b2479b14134b4a9856fbe83dec2` |
| `Mscr.Dresd.K80_183` | `f7ec3b1e222312b6dbd6de89c5ffaebbf2e4b394e8af6c59bc8dfa41bbf30597` | `89b3790389136babd04e3c2290ec472e6853698ebb568fc0a325a29d9e321c46` |
| `Mscr.Dresd.K80_184` | `1b6d4e547e637473d17164f0c7df4a0cf64d66e390baa3074a85218a06bae068` | `47280e9e1441fba7e182ede0a70f1fd98d24bb470b155ee328211c3b0e3b9ebc` |
| `Mscr.Dresd.K80_185` | `9f2638086e7e53eefc160ad71deeda13a7a20bd515b49cd5cd932c80d9629e8a` | `419b25575de3a6df8e63c029782faf2486839c9edfbd573a1045b84269100139` |
| `Mscr.Dresd.K80_186` | `0da128cdb2383cc1d3dea05389809a4416a2ef3a10fdf2bee7367839f74fbdc2` | `68ac0805240599678e62727355f42fe77112939fc77e500621eafcbf2dba7061` |

</details>

**Réglages effectifs de `saknussemm` 0.9.0** (lus dans la bibliothèque installée
et dans `adapters/layout/saknussemm_correct.py` ; le manifeste ne porte que les
réglages de la brique) :

| | producteur `rules` (E3/E4 règles) | producteur `mistral` (E3 small, 8b, 3b ; E4) |
|---|---|---|
| producteur | `RulesProducer(default_french_ocr_rules())` | `LLMEditProducer` via `MistralStructuredClient` (chat completions, `response_format` `json_schema`, repli `json_object`) — **texte seul** |
| prompt | — | `saknussemm.integrations.llm.SYSTEM_PROMPT`, 1 019 caractères, SHA-256 `9a5529ee0ad75950813ae64171f4e774d1488a8037948900c82e0facf1c2d388` |
| température | — | rampe `RetryPolicy` par défaut : 3 tentatives, 0,0 / 0,3 / 0,5 |
| `max_tokens` | — | **aucun** envoyé (défaut du fournisseur) |
| lots | `ChunkPlannerConfig` par défaut : 12 000 caractères, 80 lignes par requête, fenêtre 12 lignes (recouvrement 1) | idem |
| QE (E4) | `HeuristicQEScorer`, `qe_skip 0.5` | `DalembertQEScorer` (`pjox/dalembert`, Platt 10,9436 / 6,7179), `qe_skip 0.5` ; un fil torch (`OMP_NUM_THREADS=1`) |

Les autres briques Mistral : réglages saisis et effectifs au manifeste
(`adapter_kwargs`, `module_versions`) — `mistral` 2.1 (prompt de correction
curé `correction_press_19c_european` sur BNL, générique sur Dresden ; prompt de
transcription générique pour E1/E5 ; température 0, seed 0), `mistral_ocr` 1.3.
Modèle servi (`served_models`) : l'API rend l'alias demandé
(`mistral-small-latest`, `ministral-8b-latest`, `ministral-3b-latest`,
`mistral-ocr-latest`) ; la liste des modèles du 2026-11-27 le résout en
`mistral-small-2603`, `ministral-8b-2512`, `ministral-3b-2512`.

### Limites

- **Un SIGINT n'arrête pas `cinoc run` proprement** (constaté, non corrigé —
  modifications du produit gelées jusqu'à l'arbitrage du mainteneur sur la
  contre-expertise) : à l'interruption, `ThreadPoolExecutor.__exit__` attend
  toutes les unités en file ; celles qui finissent après sont **payées mais
  non archivées** (la boucle qui archive est sortie). Il a fallu `kill -9` pour
  arrêter la répétition 1 (E4 passée à un fil torch) ; au plus trois unités E4
  en vol perdues. Touche l'invariant « annulation coopérative ».
- La dépense est **majorante** (cache au plein tarif) et le rapport ne chiffre
  pas les chaînes qui ont lu en cache (aucun tarif de cache Mistral dans la
  table).
- E4 : le seuil 0,5 de D'AlemBERT n'est pas calibré sur BNL (moitié allemande) ;
  il ne saute qu'environ 9 % des jetons d'entrée — une répétition, faute d'en
  mesurer davantage pour ~20 h de CPU.
- Les unités recopiées (Tesseract, règles, `qwen2.5vl:3b`) n'ont **pas** de
  dispersion mesurée ; celle de Tesseract est nulle par construction (D-281),
  celle du VLM local n'est pas mesurée ici (S31L).
- Une image distante (Dresden) est encore téléchargée à la re-notation hors
  ligne ; les archives gardent des unités d'avant D-311 qu'aucune clé n'atteint.
- E5 local Dresden (6 pages « arrêtée (délai) ») n'est pas refaite ici : le VLM
  local relève de S31L.

### Estimation de S30 (montrée avant tout appel)

**Estimation du coût** — une passe, puis × 5 répétitions. Sources : tarifs
`cinoc/evaluation/pricing.json` (2026-11-25 : `mistral-small-latest`
0,14 €/Mtok entrée, 0,55 €/Mtok sortie ; `mistral_ocr` 3,66 € / 1 000 pages) ;
jetons d'image de la documentation Mistral (« Vision », FAQ, lue le
2026-11-26 : Mistral Small 3.2, image ramenée à 1540 × 1540 au plus,
≈ largeur × hauteur / 784 jetons) appliqués aux dimensions réelles des pages
et des **109 / 132 régions** que la segmentation de S30 a produites ; texte à
3,0 caractères par jeton (prudent : `qwen2.5vl` en a donné 3,8 au pilote) ;
sortie = GT + 20 % ; correction : prompt + OCR (GT + 10 %) ; `saknussemm` :
jetons **mesurés** sur la même chaîne avec le producteur `ollama` (`0003`,
`0006`, `0031` : un appel par page, 2 020 jetons d'entrée et 911 de sortie pour
2 277 caractères de GT), portés à 1,2 et 0,6 jeton par caractère. Le
**plafond** suppose que chaque appel rend son `max_tokens` (2048 par page,
1024 par région), entrée × 1,5, `saknussemm` × 3.

| corpus | expérience | jetons entrée | jetons sortie | pages OCR | € / passage | € × 5 | plafond × 5 |
|---|---|---|---|---|---|---|---|
| BNL | E0 · mistral-ocr | 0 | 0 | 37 | 0,1354 | 0,677 | 0,677 |
| BNL | E2 · tesseract → mistral | 30 823 | 8 855 | 0 | 0,0092 | 0,046 | 0,241 |
| BNL | E2 · mistral-ocr → mistral | 30 823 | 8 855 | 37 | 0,1446 | 0,723 | 0,918 |
| BNL | E1 · segmentation → mistral (VLM par région) | 32 070 | 8 855 | 0 | 0,0094 | 0,047 | 0,341 |
| BNL | E3 · … → saknussemm (mistral) | 26 566 | 13 283 | 0 | 0,0110 | 0,055 | 0,137 |
| BNL | E4 · … → saknussemm sélectif (mistral, QE) | ≤ 26 566 | ≤ 13 283 | 0 | ≤ 0,0110 | ≤ 0,055 | 0,137 |
| BNL | E5 · mistral (VLM) | 27 148 | 8 855 | 0 | 0,0087 | 0,043 | 0,237 |
| Dresden | E0 · mistral-ocr | 0 | 0 | 10 | 0,0366 | 0,183 | 0,183 |
| Dresden | E2 · tesseract → mistral | 4 573 | 4 145 | 0 | 0,0029 | 0,015 | 0,061 |
| Dresden | E2 · mistral-ocr → mistral | 4 573 | 4 145 | 10 | 0,0395 | 0,198 | 0,244 |
| Dresden | E1 · segmentation → mistral (VLM par région) | 52 640 | 4 145 | 0 | 0,0096 | 0,048 | 0,427 |
| Dresden | E3 · … → saknussemm (mistral) | 12 436 | 6 218 | 0 | 0,0052 | 0,026 | 0,064 |
| Dresden | E5 · mistral (VLM) | 19 080 | 4 145 | 0 | 0,0050 | 0,025 | 0,076 |
| **total** | | | | 94 pages × 5 | **0,43** | **2,14 €** | **3,74 €** |

**Total central 2,14 €, 4,28 € avec une marge × 2, plafond 3,74 €** : sous les
10 € d'A6, **aucun découpage nécessaire**. Mistral OCR en fait 80 % (E0 et
E2-mistral-ocr lisent chacun la page : 2 × 47 pages par passage). Si
l'accord fixe un plafond plus bas, l'ordre de coupe qui garde la question de
chaque expérience : E0 · mistral-ocr en une seule passe (son déterminisme se
lit alors sur E2, qui le relit cinq fois ; −0,69 €), puis E2 · mistral-ocr →
mistral à 3 répétitions (−0,37 €) — 1,08 € central, aucune expérience retirée.

## Attend — S32 (publication)

Dataset HF (`RunResult`, archives — images une fois chacune —, sidecars,
rapports) et DOI Zenodo : **accord du mainteneur**. La licence de Dresden
(GT `CC BY-NC-SA 4.0`, images Public Domain Mark) borne la réutilisation de
l'archive publiée ; `37-GT-BNL` est CC0. Critère de sortie : un tiers re-note
l'archive hors ligne et retrouve les chiffres au chiffre près — tenu ici pour
les cinq répétitions des deux corpus (S31) ; une image distante (Dresden) est
encore téléchargée à la re-notation (son contenu identifie l'unité). Avant de
publier : élaguer des archives les unités d'avant D-311 qu'aucune clé n'atteint
(un `cinoc run --offline` de chaque spec dit lesquelles il relit), et
remplacer le tableau partiel du README du dépôt (son garde relit chaque nombre
dans un `RunResult` commité ; une chaîne répétée s'y lira dans
`*.variance.json`, pas dans un run isolé).
