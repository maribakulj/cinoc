# 2026-11-26 — Campagne de référence : préparation et partie sans clé (S30, D-304)

**Rôle : la campagne d'ablation publiée de P5h** (`PLAN_FIN_MIGRATION.md`
§« P5h ») — **préparée ici, pas encore exécutée en entier ni publiée.**
Arbitrage **A6** (D-271) : Tesseract, un VLM **local** (Ollama,
`qwen2.5vl:3b`) et Mistral ; **plafond 10 €** pour pilote et campagne réunis
(le pilote n'a rien coûté), estimation montrée avant tout appel facturé.

S30 a fait tout ce qui ne demande ni clé ni publication : les specs E0-E5 des
deux corpus, les conventions de vérité terrain déclarées en vues, la décision
de prompt, la partie sans clé **exécutée, archivée, re-notée hors ligne et
recoupée par dinglehopper**, l'estimation du coût Mistral. Restent :

- **S31** — l'exécution Mistral : attend la **clé** et l'**accord du mainteneur
  sur l'estimation** ci-dessous ;
- **S32** — la publication (dataset HF + DOI Zenodo) : attend l'**accord du
  mainteneur**.

> Les chiffres de ce dossier sont ceux d'une campagne **non publiée** et, pour
> le VLM, d'un modèle de 3 B sur CPU : ils ne sont **pas** à citer. Le README du
> dépôt en montre cinq lignes comme **exemple partiel**, dites telles (un run,
> sans répétition, non publié) et relues dans ces `RunResult` par
> `tests/guardrails/test_readme_result.py` (S33, D-305).

## Fichiers

| fichier | rôle |
|---|---|
| `bnl.yaml` | spec complète `37-GT-BNL` : 12 pipelines (5 sans clé + 7 Mistral), 4 vues — **déclarée, exécutée en S31** |
| `bnl-sans-cle.yaml` | ses 5 pipelines sans clé, à l'identique — **exécutée en S30** |
| `dresden.yaml` | spec complète Dresden : 10 pipelines (4 sans clé + 6 Mistral) — **déclarée** |
| `dresden-sans-cle.yaml` | ses 4 pipelines sans clé — **exécutée en S30** |
| `bnl-sans-cle.run_result.json` | `RunResult` v5 du run S30 (566 Ko, aucun chemin local) |
| `dresden-sans-cle.run_result.json` | idem (169 Ko) |
| `v6/` | les **réévaluations v6** des deux `RunResult` ci-dessus (code `abee7b5`, tranche 1a), à part, avec leur provenance ([`v6/PROVENANCE.md`](v6/PROVENANCE.md)) ; les v5 restent intacts |

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
| E3 | segmentation → OCR par région → correction structurée | `saknussemm` `rules` (validation de chaîne) ; `saknussemm` `mistral` | idem | `rules` : S30 · `mistral` : S31 |
| E4 | OCR → score de qualité → correction **sélective** | `saknussemm` `rules` + QE `heuristic` (validation) ; `saknussemm` `mistral` + QE `dalembert`, `qe_skip 0.5` | **non déclarée** | validation : S30 · `mistral` : S31 |
| E5 | VLM direct sur la page | `qwen2.5vl:3b` (local) ; `mistral` | idem | local : S30 · Mistral : S31 |

Modèles Mistral : `mistral-small-latest` (chat et vision ; le *snapshot* servi
est tracé par `served_models`) et `mistral-ocr-latest`, **à confirmer par
`cinoc run bnl.yaml --check` avec la clé** (S22b : le fournisseur est
interrogé) ; `max_tokens` 2048 (page), 1024 (région). E4 n'est pas déclarée sur
Dresden : `dalembert` est un MLM du français d'Ancien Régime, et le seul autre
scoreur (`heuristic`) a une AUC de 0,500 — aucun scoreur ne sait dire quelle
ligne de Kurrent allemand corriger. Sur BNL, moitié allemande, le seuil 0,5 de
`dalembert` n'est pas calibré sur ce corpus : limite à dire au rapport de S31.

**Répétitions.** `--repeat 5` pour les pipelines stochastiques (tout ce qui
appelle Mistral ; Mistral OCR compris, ce qui mesure son déterminisme au lieu de
le supposer). `--repeat` et `--resume-dir` s'excluaient : depuis S30 chaque
répétition archive dans son dossier neuf (`<archive>/repetition-<k>`) et
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

## Attend — S31 (exécution Mistral)

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

**Procédure S31**, dans cet ordre :

1. réinstaller `cinoc` (version du manifeste), extras `[mistral,saknussemm,qe,huggingface]` ;
   clé `MISTRAL_API_KEY` ;
2. `cinoc run bnl.yaml --check` et `dresden.yaml --check` avec la clé : modèles confirmés par le fournisseur ;
3. un essai sur 3 pages (≈ 0,03 €) : jetons mesurés contre l'estimation ; s'arrêter si l'écart dépasse × 2 ;
4. semer les répétitions : `cinoc run bnl-sans-cle.yaml --resume-dir arch/repetition-1`, puis copier
   `arch/repetition-1` en `repetition-2` … `repetition-5` (l'archive de S30 est éphémère) ;
5. `cinoc run bnl.yaml --repeat 5 --resume-dir arch --json … -o …` : seules les unités Mistral s'exécutent,
   cinq fois ; idem Dresden ;
6. `--offline --repeat 5` : fourchettes identiques ; oracle dinglehopper sur chaque répétition ;
7. dépense réelle (économie du rapport) contre l'estimation, au README.

Questions ouvertes pour S31 : refaire E5 local Dresden avec `timeout: 1800` et
`--workers 1` (réglage hors empreinte : seules les 6 unités échouées repartent,
~1 h), ou le laisser tel quel — ses échecs disent déjà le résultat.

## Attend — S32 (publication)

Dataset HF (`RunResult`, archives — images une fois chacune —, sidecars,
rapports) et DOI Zenodo : **accord du mainteneur**. La licence de Dresden
(GT `CC BY-NC-SA 4.0`, images Public Domain Mark) borne la réutilisation de
l'archive publiée ; `37-GT-BNL` est CC0. Critère de sortie : un tiers re-note
l'archive hors ligne et retrouve les chiffres au chiffre près — tenu ici pour
la partie sans clé ; une image distante (Dresden) est encore téléchargée à la
re-notation (son contenu identifie l'unité).
