# `campaigns/` — les runs mesurés, avec leurs relevés

Les deux premières sont des archives de campagnes menées sur `saknussemm`
avant que cette plateforme reprenne le rôle de banc ; elles arrivent avec le
corpus qu'elles mesuraient, le 2026-08-16. La troisième est le pilote de
Cinoc lui-même (S10), la quatrième la campagne de référence (S30).

Elles sont ici pour **ce qu'elles ont trouvé**, pas pour leurs chiffres.

**Leurs instruments n'y sont plus.** `campaigns/tooling/` (les
`scripts/*.py` que citent les deux README d'archive : `vision_benchmark.py`,
`ocr_corpus.py`, `run_vision.py`…) a été retiré le 2026-11-26 (D-303) : il
n'avait aucun consommateur et ne tournait plus — ses imports
(`saknussemm.integrations.vision`, `scripts.qe_data`, `scripts.providers_multimodal`)
n'existent ni dans `saknussemm` 0.9 ni dans ce dépôt. L'historique git le
garde (dernier commit qui le contient : `6d6ab0e`). Ce qui le remplace : le
banc lui-même — `cinoc run`, le rejeu `precomputed`, et `alto_source` avec
`--ocr-sidecar` (le format de `2026-07-25-bnl-mistral/ocr_spa_sidecar.json`).

## `2026-07-25-bnl-mistral/`

Première mesure réelle : corpus BnL, `mistral-medium`, chaîne vision. Deux
runs, une décimale citée. C'est cette campagne qui a fait écrire la règle
qui gouverne les suivantes : **jamais une décimale isolée.**

## `2026-08-14-bnl-mistral-m2/`

Cinq runs, pour publier une fourchette au lieu d'un nombre. Et la plus utile
des deux, parce qu'elle **invalide ses propres chiffres** :

- fourchette mesurée 0,0338 – 0,0357, écart 5,6 % ;
- puis la campagne découvre que le banc **appariait les césures sur la
  transcription humaine et non sur le texte donné au moteur**, fabriquant un
  état qu'aucun run réel ne peut atteindre ;
- le correctif est arrivé **après** les cinq runs. La fourchette publiée
  hérite donc du défaut qu'elle a trouvé, et le contrefactuel
  (0,0243 – 0,0263) est un re-calcul, pas une mesure.

Deux conclusions valent d'être reprises plutôt que redécouvertes.

**Aucune des deux campagnes n'est fiable sur les lignes césurées.** Le
défaut d'appariement les traverse toutes les deux.

**Et l'item `M4` reposait sur une lecture inversée.** Il disait « récupérer
les 16,5 % de CER dus à deux normalisations systématiques ». Compté contre
l'entrée plutôt que contre la référence : le signe de coupure `⸗`
**n'atteint jamais le modèle** (0 occurrence dans l'OCR d'entrée, 36 dans la
référence), et l'apostrophe typographique est **détruite par l'OCR puis
réparée par le modèle** — 50 lignes améliorées, 0 dégradée. La perte
récupérable, s'il en reste, est en amont dans l'OCR.

## `2026-11-26-pilote-local/`

Le pilote de S10 (D-281) : 10 pages de `37-GT-BNL`, Tesseract et un VLM local,
aucun appel facturé. Pas une publication : ses 24 constats ont été rattachés
aux sessions de la feuille de route.

## `2026-11-26-reference/`

La campagne de référence de P5h, **préparée** en S30 (D-304) : les specs E0-E5
sur `37-GT-BNL` et Dresden, les conventions de la GT BNL en vues, la partie sans
clé (Tesseract, VLM local) exécutée, archivée, re-notée hors ligne et recoupée
par dinglehopper, et l'estimation du coût Mistral (2,14 € central, plafond
3,74 €). L'exécution Mistral (S31) et la publication (S32) attendent le
mainteneur.

## Ce qu'elles impliquent ici

Une campagne rejouée sur ce banc devra fournir ce qu'aucune des deux archives
n'avait : des **runs répétés** avec leur dispersion — `cinoc run --repeat N`
(`app/variance`) écrit une fourchette par métrique, et, avec `--resume-dir`,
archive chaque répétition à part (`<archive>/repetition-<k>`) ; c'est le
protocole de la campagne publiée (P5h).
