# Avant / après — tranche 1a (D-313) sur les archives S30, S31, S31L

Revue de fin de la tranche 1a de la refonte des contrats : chaque métrique de chaque
vue × pipeline × corpus, **v5** (`RunResult` produits) contre **v6** (re-notation
**hors ligne** des mêmes archives par le code de `claude/refonte-contrats`,
`abee7b5`), avec la cause de chaque écart. Aucun moteur appelé, aucun appel
réseau (proxy forcé sur `127.0.0.1:9`, `HF_HUB_OFFLINE=1`), aucun code produit,
aucun commit.

## 1. En une minute

| | agrégats (15 `RunResult`) | lignes des tableaux (S31 regroupé) |
|---|---|---|
| inchangés au bit près | **1 559** | 541 |
| changés — alignement canonique S/D/I (MER, cMER) | **255** (cMER 165, MER 90) | 93 |
| changés — **autre** (non prévu) : arrondi unique, 1 ULP | **12** (2 agrégats × 6 runs Dresden) | 4 |
| changés — page à référence vide au micro | 0 | 0 |
| changés — F1 micro (ΣTP/ΣFP/ΣFN) | 0 (aucune métrique F1 déclarée) | 0 |
| changés — plancher au corpus (B1) | 0 (aucune exactitude déclarée ; voir § 3, variante) | 0 |
| changés — scalaire indéfini | 0 (aucun document à dénominateur nul) | 0 |
| changés — ECE exacte | 0 (calibration hors des vues ; voir § 8, mode détaillé) | 0 |
| inexpliqués | **0** | 0 |
| total | 1 826 | 638 |

- **Support « notés / attendus » : identique sur les 1 826 agrégats.**
- Documents : 42 416 scores par document, **1 102 changés, tous** MER/cMER par
  alignement canonique (contrôle par document, § 4).
- Aucune page à référence vide, aucun scalaire indéfini dans aucune des 15
  archives (`scalar_reason` nul partout) : CER, WER, `cer_diplo`,
  `unanchored_trigrams` ne bougent pas, sauf 12 agrégats de 1 ULP (§ 6).
- Inférence : aucun test ne bascule ; les IC du micro de MER/cMER deviennent
  « inférence non estimable » ; ceux du CER/WER sont identiques au bit près (§ 7).

## 2. Méthode et relecture des archives

| campagne | « avant » (v5) | code « après » (v6) | spec(s) | archive | unités relues |
|---|---|---|---|---|---|
| S30 | `contre-expertise/campaigns/2026-11-26-reference/{bnl,dresden}-sans-cle.run_result.json` (= `main` `04a1c17`) | worktree `renotation-v6-pur` = `abee7b5` **sans** cherry-pick, venv `renotation-venv-pur` | `{bnl,dresden}-sans-cle.yaml` (copie figée, = `main`) | `s30/archive-{bnl,dresden}` | 185/185 ; 40/40 (6 en échec « arrêtée (délai) », 1 tronquée, comme en v5) |
| S31 | `claude/gele-s31-mistral:…/{bnl,dresden}.repetition-{1..5}.run_result.json` | worktree `renotation-v6` = `abee7b5` + `cherry-pick --no-commit aba0fe7 50cad9f`, venv `renotation-venv` | rép. 1 `bnl.yaml`, rép. 2-5 `bnl-repetitions.yaml` ; `dresden.yaml` (= branche, = `s31/renote.sh`) | `s31/arch-{bnl,dresden}/repetition-<k>` | BNL 555, 518 × 4 ; Dresden 130 × 5 (6 en échec, 1 tronquée) |
| S31L | `s31l/final/*.run_result.json` | idem S31 | `bnl-local.yaml`, `bnl-local-saknussemm.yaml`, `dresden-local.yaml` (= `claude/gele-s31l-local`) | `s31l/archive-{bnl,dresden}` | 259 ; 45 ; 50 |

- **Clés d'unité.** S30 : relue entière par le code v6 nu (`FANOUT_VERSION = "1"`) ;
  avec les cherry-picks, `cinoc run bnl-sans-cle.yaml --offline` échoue
  (`ArchiveIncompleteError` : « 111 unité(s) absente(s) », toutes les unités
  à fan-out E1/E3/E4) — d'où deux worktrees. S31 et S31L : relues entières avec
  `aba0fe7` (`FANOUT_VERSION = "2"`) et `50cad9f` (réglage `timeout`, hors
  empreinte). Aucune archive n'a refusé la relecture.
- **Le « avant » est reproductible.** Chaque `RunResult` v5 a été re-noté hors
  ligne par son propre code (S30 : `04a1c17` ; S31 : venv de S31, `32a56aa` ;
  S31L : venv de S31L, `50cad9f`) : `pipelines`, `documents`, `cross_engine`,
  `analyses` **identiques** au fichier commité/gelé, 15/15. Tout écart ci-dessous
  vient donc du code (v5 → v6), non des archives.
- **Archives intactes** : nombre de fichiers et empreinte (mtime, taille, chemin)
  identiques avant et après les ~60 re-notations (`logs/archives-*.txt`).
- Le corpus BNL des archives (`s30/bnl`) est octet pour octet `corpus/37-GT-BNL`
  du dépôt (75 fichiers) ; Dresden : GT `ground_truth/` de l'import, images
  servies par l'archive (aucune requête HF).
- Hors métriques, seuls diffèrent : `manifest` (horloges, `code_version`,
  `dependencies_lock` : S30 pydantic 2.13.5 → 2.14.4, lxml, httpx… ; S31L
  `mistralai` présent) et, pour S30, `usage.resumed` (exécution → relecture).
  `usage` de S31/S31L identique. `pricing.json` (tarifs Ministral de `32a56aa`)
  n'est pas dans le worktree : sans effet sur le `RunResult` (`usage` identique,
  et en mode détaillé `economics` ne diffère que par l’arrondi du § 6).

## 3. Prévision écrite dans D-313 : vérifiée

| prévision (D-313) | constat | verdict |
|---|---|---|
| CER et WER micro BNL **inchangés** | S30 BNL : 40/40 agrégats `cer`/`cer_diplo`/`wer` identiques au bit près (et 568/568 sur S31 BNL, 128/128 sur S31L BNL) | **vérifiée** |
| CER et WER micro Dresden **inchangés** (« aucune page à référence vide n'y est attendue ») | S30 Dresden : 30/32 identiques au bit près ; **2 CER à +1 ULP** (2,2e-16 : E5 local, vues `texte (lignes)` et `sans césure`), invisibles à l'affichage (4 décimales) ; aucune page à référence vide | **vérifiée à la précision affichée** ; au bit près, 2 exceptions non prévues (§ 6) |
| `char_accuracy` Dresden E5 0,3125 → **0,0**, taux non tronqué **1,8614** et ses comptes publiés à côté | `char_accuracy` n'est déclarée dans **aucune** vue des campagnes ; vérifiée sur une **variante** des specs S30 (`texte` + `char_accuracy`, `word_accuracy`), re-notée hors ligne en v5 et en v6 : **0,3125 → 0,0**, `untruncated_error_rate` = **1,8614232209737829**, statistique `error_counts` **7 952 / 4 272**, support **4/10** ; le rapport v6 affiche « 0,0000 (erreurs 1,8614 · 7952/4272) 4/10 » | **vérifiée** (sur variante) |
| support « notés / attendus » du README inchangé | 1 826/1 826 agrégats : `support` et `expected` identiques (E5 Dresden 4/10 partout) | **vérifiée** |

Variante B1 complète (`variante/s30-*-exactitudes.v{5,6}.json` ; toutes les
autres métriques y sont identiques au run principal, v5 et v6) :

| corpus | pipeline | métrique | v5 | v6 | Δ | taux non tronqué (v6) | comptes (v6) | cause |
|---|---|---|---|---|---|---|---|---|
| BNL | E0 · tesseract | char_accuracy | 0,941594 | 0,941594 | 0 | 0,058406 | 1293/22138 | inchangé (aucune page à CER > 1) |
| BNL | E1, E3, E4 | char_accuracy | 0,936083 | 0,936083 | 0 | 0,063917 | 1415/22138 | inchangé |
| BNL | E5 · qwen2.5vl:3b (local) | char_accuracy | 0,965851 | 0,965851 | 0 | 0,034149 | 756/22138 | inchangé |
| BNL | (5 pipelines) | word_accuracy | = 1 − WER | = | 0 | WER | — | inchangé |
| Dresden | E0 · tesseract | char_accuracy | 0,243655 | 0,243655 | 0 | 0,756345 | 7838/10363 | inchangé |
| Dresden | E0 · tesseract | **word_accuracy** | 0,005185 | **0,001296** | −3,89e-03 | 0,998704 | 1541/1543 | **plancher au corpus (B1)** |
| Dresden | E1, E3 | char_accuracy | 0,222522 | 0,222522 | 0 | 0,777478 | 8057/10363 | inchangé |
| Dresden | E1, E3 | word_accuracy | 0,0 | 0,0 | 0 | 1,303953 | 2012/1543 | inchangé (déjà 0) |
| Dresden | E5 · qwen2.5vl:3b (local) | **char_accuracy** | **0,3125** | **0,0** | −3,13e-01 | **1,861423** | **7952/4272** | **plancher au corpus (B1)** — prévision D-313 |
| Dresden | E5 · qwen2.5vl:3b (local) | **word_accuracy** | 0,085950 | **0,0** | −8,60e-02 | 2,484298 | 1503/605 | **plancher au corpus (B1)** |

(`word_accuracy` Dresden E0 : v5 moyennait des planchers par page — une page à
WER < 1 donnait du crédit que le corpus, à 1 541 erreurs pour 1 543 mots, n'a
pas ; v6 = 1 − 1541/1543.)

## 4. Contrôle de la cause « alignement canonique S/D/I »

Pour **chaque** document dont MER ou cMER change (1 102) : même nombre
d'éditions E = S + D + I en v5 (valeur × poids) et en v6 (statistique), seul I
baisse (I v5 > I v6), et v6 = E / (n_réf + I v6) au plus proche. Pour chaque
agrégat (255) : v6 = ΣE / Σ(n_réf + I) et v5 = Σ(v·w)/Σw. Les CER/WER des
mêmes documents sont inchangés (E identique). Contrôle **indépendant** (DP
O(n·m) en Python pur, sans rapidfuzz, `scripts/dp_check.py`) sur le document
isolé :

> Dresden, E0 · tesseract, `Mscr.Dresd.K80_177`, vue `texte` (`flat_text`) :
> |r| = 1 229, |h| = 505, d = 972 ; parmi les alignements de coût 972, I va de
> **3 à 5**. v5 (départage de rapidfuzz) : I = 4, cMER = 972/1233 = 0,788321 ;
> v6 (max S) : I = 3, D = 727, S = 242, cMER = 972/1232 = **0,788961**. La valeur
> v5 dépendait du départage d'ex æquo ; v6 prend l'unique alignement canonique.

Effet à l'agrégat : de +1,4e-06 (S31 BNL E5 Mistral) à **+1,21e-02** (S31
Dresden E5 Mistral, cMER 0,6829 → 0,6950, rép. 4) ; toujours à la hausse
(I minimal → dénominateur minimal). Prévu par D-313 (« MER, cMER sur les
alignements ex æquo »). **Correction voulue.**

## 5. Tableaux avant/après, par campagne et corpus

Lecture : valeurs à 6 décimales (pleine précision dans `avant-apres.csv`) ;
Δ = v6 − v5 en pleine précision (« 0 » = identique au bit près) ; métrique en
**gras** = changée ; « notés/attendus » = `support`/`expected` de l'agrégat (v5 =
v6 partout). Cause : **inchangé** ; **canonique S/D/I** avec ΣI v5 → v6 (le seul
compte qui bouge) et le nombre de documents changés ; **autre : arrondi unique**
(§ 6). S31 : une ligne par vue × pipeline × métrique, moyenne et [min ; max] sur
les répétitions ; « rép. » = nombre de répétitions qui portent le pipeline
(E4 Mistral : répétition 1 seulement) ; la cause dit sur combien de
répétitions elle vaut.

### S30 · BNL (`bnl-sans-cle.yaml`, archive `s30/archive-bnl`, 185 unités)

55 agrégats : inchangé 45, canonique S/D/I 10.

| vue | pipeline | métrique | v5 | v6 | Δ | notés/attendus | cause |
|---|---|---|---|---|---|---|---|
| texte | E0 · tesseract | cer | 0,058406 | 0,058406 | 0 | 37/37 | inchangé |
| texte | E0 · tesseract | wer | 0,237171 | 0,237171 | 0 | 37/37 | inchangé |
| texte | E0 · tesseract | cer_diplo | 0,049462 | 0,049462 | 0 | 37/37 | inchangé |
| texte | E0 · tesseract | **cmer** | 0,057801 | 0,057814 | +1,29e-05 | 37/37 | canonique S/D/I (ΣI 232→227, 4/37 doc.) |
| texte | E0 · tesseract | **mer** | 0,231519 | 0,231582 | +6,27e-05 | 37/37 | canonique S/D/I (ΣI 88→87, 1/37 doc.) |
| texte | E0 · tesseract | unanchored_trigrams | 0,110905 | 0,110905 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → tesseract | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → tesseract | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → tesseract | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → tesseract | **cmer** | 0,062956 | 0,062970 | +1,40e-05 | 37/37 | canonique S/D/I (ΣI 338→333, 4/37 doc.) |
| texte | E1 · segmentation → tesseract | **mer** | 0,244750 | 0,244816 | +6,59e-05 | 37/37 | canonique S/D/I (ΣI 109→108, 1/37 doc.) |
| texte | E1 · segmentation → tesseract | unanchored_trigrams | 0,117700 | 0,117700 | 0 | 37/37 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **cmer** | 0,062956 | 0,062970 | +1,40e-05 | 37/37 | canonique S/D/I (ΣI 338→333, 4/37 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **mer** | 0,244750 | 0,244816 | +6,59e-05 | 37/37 | canonique S/D/I (ΣI 109→108, 1/37 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | unanchored_trigrams | 0,117700 | 0,117700 | 0 | 37/37 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | **cmer** | 0,062956 | 0,062970 | +1,40e-05 | 37/37 | canonique S/D/I (ΣI 338→333, 4/37 doc.) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | **mer** | 0,244750 | 0,244816 | +6,59e-05 | 37/37 | canonique S/D/I (ΣI 109→108, 1/37 doc.) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | unanchored_trigrams | 0,117700 | 0,117700 | 0 | 37/37 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer | 0,034149 | 0,034149 | 0 | 37/37 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | wer | 0,155895 | 0,155895 | 0 | 37/37 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer_diplo | 0,034149 | 0,034149 | 0 | 37/37 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | **cmer** | 0,034005 | 0,034008 | +3,06e-06 | 37/37 | canonique S/D/I (ΣI 94→92, 2/37 doc.) |
| texte | E5 · qwen2.5vl:3b (local) | **mer** | 0,154523 | 0,154565 | +4,25e-05 | 37/37 | canonique S/D/I (ΣI 32→31, 1/37 doc.) |
| texte | E5 · qwen2.5vl:3b (local) | unanchored_trigrams | 0,051230 | 0,051230 | 0 | 37/37 | inchangé |
| texte (lignes) | E0 · tesseract | cer | 0,060981 | 0,060981 | 0 | 37/37 | inchangé |
| texte (lignes) | E1 · segmentation → tesseract | cer | 0,064143 | 0,064143 | 0 | 37/37 | inchangé |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,064143 | 0,064143 | 0 | 37/37 | inchangé |
| texte (lignes) | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,064143 | 0,064143 | 0 | 37/37 | inchangé |
| texte (lignes) | E5 · qwen2.5vl:3b (local) | cer | 0,048514 | 0,048514 | 0 | 37/37 | inchangé |
| lecture | E0 · tesseract | cer | 0,058406 | 0,058406 | 0 | 37/37 | inchangé |
| lecture | E0 · tesseract | wer | 0,237171 | 0,237171 | 0 | 37/37 | inchangé |
| lecture | E0 · tesseract | cer_diplo | 0,049462 | 0,049462 | 0 | 37/37 | inchangé |
| lecture | E1 · segmentation → tesseract | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| lecture | E1 · segmentation → tesseract | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| lecture | E1 · segmentation → tesseract | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer | 0,034149 | 0,034149 | 0 | 37/37 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | wer | 0,155895 | 0,155895 | 0 | 37/37 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer_diplo | 0,034149 | 0,034149 | 0 | 37/37 | inchangé |
| sans césure | E0 · tesseract | cer | 0,060911 | 0,060911 | 0 | 37/37 | inchangé |
| sans césure | E1 · segmentation → tesseract | cer | 0,064328 | 0,064328 | 0 | 37/37 | inchangé |
| sans césure | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,064328 | 0,064328 | 0 | 37/37 | inchangé |
| sans césure | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,064328 | 0,064328 | 0 | 37/37 | inchangé |
| sans césure | E5 · qwen2.5vl:3b (local) | cer | 0,041458 | 0,041458 | 0 | 37/37 | inchangé |

### S30 · Dresden (`dresden-sans-cle.yaml`, archive `s30/archive-dresden`, 40 unités)

44 agrégats : inchangé 37, canonique S/D/I 5, autre : arrondi unique (1 ULP) 2.

| vue | pipeline | métrique | v5 | v6 | Δ | notés/attendus | cause |
|---|---|---|---|---|---|---|---|
| texte | E0 · tesseract | cer | 0,756345 | 0,756345 | 0 | 10/10 | inchangé |
| texte | E0 · tesseract | wer | 0,998704 | 0,998704 | 0 | 10/10 | inchangé |
| texte | E0 · tesseract | cer_diplo | 0,755669 | 0,755669 | 0 | 10/10 | inchangé |
| texte | E0 · tesseract | **cmer** | 0,752713 | 0,754742 | +2,03e-03 | 10/10 | canonique S/D/I (ΣI 50→22, 9/10 doc.) |
| texte | E0 · tesseract | mer | 0,994194 | 0,994194 | 0 | 10/10 | inchangé |
| texte | E0 · tesseract | unanchored_trigrams | 0,841243 | 0,841243 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | cer | 0,777478 | 0,777478 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | wer | 1,303953 | 1,303953 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | cer_diplo | 0,776609 | 0,776609 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | **cmer** | 0,749628 | 0,755603 | +5,98e-03 | 10/10 | canonique S/D/I (ΣI 385→300, 10/10 doc.) |
| texte | E1 · segmentation → tesseract | mer | 0,994563 | 0,994563 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | unanchored_trigrams | 0,862971 | 0,862971 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,777478 | 0,777478 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | wer | 1,303953 | 1,303953 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,776609 | 0,776609 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **cmer** | 0,749628 | 0,755603 | +5,98e-03 | 10/10 | canonique S/D/I (ΣI 385→300, 10/10 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | mer | 0,994563 | 0,994563 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | unanchored_trigrams | 0,862971 | 0,862971 | 0 | 10/10 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer | 1,861423 | 1,861423 | 0 | 4/10 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | wer | 2,484298 | 2,484298 | 0 | 4/10 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer_diplo | 1,852294 | 1,852294 | 0 | 4/10 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | **cmer** | 0,768532 | 0,769499 | +9,67e-04 | 4/10 | canonique S/D/I (ΣI 6075→6062, 3/10 doc.) |
| texte | E5 · qwen2.5vl:3b (local) | **mer** | 0,947667 | 0,948265 | +5,98e-04 | 4/10 | canonique S/D/I (ΣI 981→980, 1/10 doc.) |
| texte | E5 · qwen2.5vl:3b (local) | unanchored_trigrams | 0,555440 | 0,555440 | 0 | 4/10 | inchangé |
| texte (lignes) | E0 · tesseract | cer | 0,768310 | 0,768310 | 0 | 10/10 | inchangé |
| texte (lignes) | E1 · segmentation → tesseract | cer | 0,795812 | 0,795812 | 0 | 10/10 | inchangé |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,795812 | 0,795812 | 0 | 10/10 | inchangé |
| texte (lignes) | E5 · qwen2.5vl:3b (local) | **cer** | 1,870552 | 1,870552 | +2,22e-16 | 4/10 | **autre** : arrondi unique (7991/4272, 1 ULP) |
| lecture | E0 · tesseract | cer | 0,756345 | 0,756345 | 0 | 10/10 | inchangé |
| lecture | E0 · tesseract | wer | 0,998704 | 0,998704 | 0 | 10/10 | inchangé |
| lecture | E0 · tesseract | cer_diplo | 0,755669 | 0,755669 | 0 | 10/10 | inchangé |
| lecture | E1 · segmentation → tesseract | cer | 0,777478 | 0,777478 | 0 | 10/10 | inchangé |
| lecture | E1 · segmentation → tesseract | wer | 1,303953 | 1,303953 | 0 | 10/10 | inchangé |
| lecture | E1 · segmentation → tesseract | cer_diplo | 0,776609 | 0,776609 | 0 | 10/10 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,777478 | 0,777478 | 0 | 10/10 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | wer | 1,303953 | 1,303953 | 0 | 10/10 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,776609 | 0,776609 | 0 | 10/10 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer | 1,861423 | 1,861423 | 0 | 4/10 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | wer | 2,484298 | 2,484298 | 0 | 4/10 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer_diplo | 1,852294 | 1,852294 | 0 | 4/10 | inchangé |
| sans césure | E0 · tesseract | cer | 0,768073 | 0,768073 | 0 | 10/10 | inchangé |
| sans césure | E1 · segmentation → tesseract | cer | 0,795580 | 0,795580 | 0 | 10/10 | inchangé |
| sans césure | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,795580 | 0,795580 | 0 | 10/10 | inchangé |
| sans césure | E5 · qwen2.5vl:3b (local) | **cer** | 1,871663 | 1,871663 | +2,22e-16 | 4/10 | **autre** : arrondi unique (7992/4270, 1 ULP) |

### S31 · BNL (répétition 1 : `bnl.yaml`, 555 unités ; 2-5 : `bnl-repetitions.yaml`, 518 unités)

165 lignes (vue × pipeline × métrique), 781 agrégats sur les 5 répétitions : inchangé 663, canonique S/D/I 118.

| vue | pipeline | métrique | rép. | v5 moy. [min ; max] | v6 moy. [min ; max] | Δ moy. [min ; max] | notés/attendus | cause |
|---|---|---|---|---|---|---|---|---|
| texte | E0 · tesseract | cer | 5 | 0,058406 | 0,058406 | 0 | 37/37 | inchangé 5/5 |
| texte | E0 · tesseract | wer | 5 | 0,237171 | 0,237171 | 0 | 37/37 | inchangé 5/5 |
| texte | E0 · tesseract | cer_diplo | 5 | 0,049462 | 0,049462 | 0 | 37/37 | inchangé 5/5 |
| texte | E0 · tesseract | **cmer** | 5 | 0,057801 | 0,057814 | +1,29e-05 | 37/37 | canonique S/D/I 5/5 (ΣI −5) |
| texte | E0 · tesseract | **mer** | 5 | 0,231519 | 0,231582 | +6,27e-05 | 37/37 | canonique S/D/I 5/5 (ΣI −1) |
| texte | E0 · tesseract | unanchored_trigrams | 5 | 0,110905 | 0,110905 | 0 | 37/37 | inchangé 5/5 |
| texte | E1 · segmentation → tesseract | cer | 5 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 5/5 |
| texte | E1 · segmentation → tesseract | wer | 5 | 0,252150 | 0,252150 | 0 | 37/37 | inchangé 5/5 |
| texte | E1 · segmentation → tesseract | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| texte | E1 · segmentation → tesseract | **cmer** | 5 | 0,062956 | 0,062970 | +1,40e-05 | 37/37 | canonique S/D/I 5/5 (ΣI −5) |
| texte | E1 · segmentation → tesseract | **mer** | 5 | 0,244750 | 0,244816 | +6,59e-05 | 37/37 | canonique S/D/I 5/5 (ΣI −1) |
| texte | E1 · segmentation → tesseract | unanchored_trigrams | 5 | 0,117700 | 0,117700 | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | wer | 5 | 0,214979 | 0,214979 | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **cmer** | 5 | 0,054191 | 0,054203 | +1,21e-05 | 37/37 | canonique S/D/I 5/5 (ΣI −5) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **mer** | 5 | 0,208670 | 0,208726 | +5,62e-05 | 37/37 | canonique S/D/I 5/5 (ΣI −1) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | unanchored_trigrams | 5 | 0,094178 | 0,094178 | 0 | 37/37 | inchangé 5/5 |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 5 | 0,062381 | 0,062381 | 0 | 37/37 | inchangé 5/5 |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | wer | 5 | 0,245492 | 0,245492 | 0 | 37/37 | inchangé 5/5 |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | **cmer** | 5 | 0,061443 | 0,061457 | +1,37e-05 | 37/37 | canonique S/D/I 5/5 (ΣI −5) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | **mer** | 5 | 0,238288 | 0,238352 | +6,42e-05 | 37/37 | canonique S/D/I 5/5 (ΣI −1) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | unanchored_trigrams | 5 | 0,113735 | 0,113735 | 0 | 37/37 | inchangé 5/5 |
| texte | E5 · qwen2.5vl:3b (local) | cer | 5 | 0,034149 | 0,034149 | 0 | 37/37 | inchangé 5/5 |
| texte | E5 · qwen2.5vl:3b (local) | wer | 5 | 0,155895 | 0,155895 | 0 | 37/37 | inchangé 5/5 |
| texte | E5 · qwen2.5vl:3b (local) | cer_diplo | 5 | 0,034149 | 0,034149 | 0 | 37/37 | inchangé 5/5 |
| texte | E5 · qwen2.5vl:3b (local) | **cmer** | 5 | 0,034005 | 0,034008 | +3,06e-06 | 37/37 | canonique S/D/I 5/5 (ΣI −2) |
| texte | E5 · qwen2.5vl:3b (local) | **mer** | 5 | 0,154523 | 0,154565 | +4,25e-05 | 37/37 | canonique S/D/I 5/5 (ΣI −1) |
| texte | E5 · qwen2.5vl:3b (local) | unanchored_trigrams | 5 | 0,051230 | 0,051230 | 0 | 37/37 | inchangé 5/5 |
| texte | E0 · mistral-ocr | cer | 5 | 0,025594 [0,0256 ; 0,0257] | 0,025594 [0,0256 ; 0,0257] | 0 | 37/37 | inchangé 5/5 |
| texte | E0 · mistral-ocr | wer | 5 | 0,132205 [0,1320 ; 0,1326] | 0,132205 [0,1320 ; 0,1326] | 0 | 37/37 | inchangé 5/5 |
| texte | E0 · mistral-ocr | cer_diplo | 5 | 0,025594 [0,0256 ; 0,0257] | 0,025594 [0,0256 ; 0,0257] | 0 | 37/37 | inchangé 5/5 |
| texte | E0 · mistral-ocr | **cmer** | 5 | 0,025504 [0,0255 ; 0,0256] | 0,025506 [0,0255 ; 0,0256] | +2,30e-06 [+2,29e-06 ; +2,30e-06] | 37/37 | canonique S/D/I 5/5 (ΣI −2) |
| texte | E0 · mistral-ocr | mer | 5 | 0,130970 [0,1308 ; 0,1314] | 0,130970 [0,1308 ; 0,1314] | 0 | 37/37 | inchangé 5/5 |
| texte | E0 · mistral-ocr | unanchored_trigrams | 5 | 0,045427 [0,0454 ; 0,0455] | 0,045427 [0,0454 ; 0,0455] | 0 | 37/37 | inchangé 5/5 |
| texte | E2 · tesseract → mistral | cer | 5 | 0,043166 [0,0408 ; 0,0459] | 0,043166 [0,0408 ; 0,0459] | 0 | 37/37 | inchangé 5/5 |
| texte | E2 · tesseract → mistral | wer | 5 | 0,147462 [0,1412 ; 0,1534] | 0,147462 [0,1412 ; 0,1534] | 0 | 37/37 | inchangé 5/5 |
| texte | E2 · tesseract → mistral | cer_diplo | 5 | 0,040744 [0,0385 ; 0,0439] | 0,040744 [0,0385 ; 0,0439] | 0 | 37/37 | inchangé 5/5 |
| texte | E2 · tesseract → mistral | **cmer** | 5 | 0,042764 [0,0405 ; 0,0455] | 0,042777 [0,0405 ; 0,0455] | +1,37e-05 [+9,57e-06 ; +1,86e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −5 à −10) |
| texte | E2 · tesseract → mistral | mer | 5 | 0,144327 [0,1385 ; 0,1500] | 0,144327 [0,1385 ; 0,1500] | 0 | 37/37 | inchangé 5/5 |
| texte | E2 · tesseract → mistral | unanchored_trigrams | 5 | 0,055777 [0,0537 ; 0,0569] | 0,055777 [0,0537 ; 0,0569] | 0 | 37/37 | inchangé 5/5 |
| texte | E2 · mistral-ocr → mistral | cer | 5 | 0,035225 [0,0333 ; 0,0388] | 0,035225 [0,0333 ; 0,0388] | 0 | 37/37 | inchangé 5/5 |
| texte | E2 · mistral-ocr → mistral | wer | 5 | 0,141082 [0,1373 ; 0,1448] | 0,141082 [0,1373 ; 0,1448] | 0 | 37/37 | inchangé 5/5 |
| texte | E2 · mistral-ocr → mistral | cer_diplo | 5 | 0,035188 [0,0333 ; 0,0388] | 0,035188 [0,0333 ; 0,0388] | 0 | 37/37 | inchangé 5/5 |
| texte | E2 · mistral-ocr → mistral | **cmer** | 5 | 0,035028 [0,0332 ; 0,0386] | 0,035030 [0,0332 ; 0,0386] | +2,27e-06 [+1,49e-06 ; +5,19e-06] | 37/37 | canonique S/D/I 5/5 (ΣI −1 à −3) |
| texte | E2 · mistral-ocr → mistral | **mer** | 5 | 0,139586 [0,1359 ; 0,1432] | 0,139601 [0,1359 ; 0,1432] | +1,57e-05 [0 ; +3,93e-05] | 37/37 | inchangé 3/5, canonique S/D/I 2/5 (ΣI −1) |
| texte | E2 · mistral-ocr → mistral | unanchored_trigrams | 5 | 0,048042 [0,0465 ; 0,0509] | 0,048042 [0,0465 ; 0,0509] | 0 | 37/37 | inchangé 5/5 |
| texte | E1 · segmentation → mistral (VLM par région) | cer | 5 | 0,041747 [0,0402 ; 0,0436] | 0,041747 [0,0402 ; 0,0436] | 0 | 37/37 | inchangé 5/5 |
| texte | E1 · segmentation → mistral (VLM par région) | wer | 5 | 0,166158 [0,1628 ; 0,1750] | 0,166158 [0,1628 ; 0,1750] | 0 | 37/37 | inchangé 5/5 |
| texte | E1 · segmentation → mistral (VLM par région) | cer_diplo | 5 | 0,041548 [0,0402 ; 0,0426] | 0,041548 [0,0402 ; 0,0426] | 0 | 37/37 | inchangé 5/5 |
| texte | E1 · segmentation → mistral (VLM par région) | **cmer** | 5 | 0,041075 [0,0396 ; 0,0429] | 0,041084 [0,0396 ; 0,0429] | +9,13e-06 [+7,30e-06 ; +1,08e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −4 à −6) |
| texte | E1 · segmentation → mistral (VLM par région) | **mer** | 5 | 0,162697 [0,1596 ; 0,1711] | 0,162741 [0,1596 ; 0,1711] | +4,42e-05 [+4,34e-05 ; +4,64e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −1) |
| texte | E1 · segmentation → mistral (VLM par région) | unanchored_trigrams | 5 | 0,058216 [0,0565 ; 0,0625] | 0,058216 [0,0565 ; 0,0625] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer | 5 | 0,047032 [0,0443 ; 0,0495] | 0,047032 [0,0443 ; 0,0495] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | wer | 5 | 0,162108 [0,1581 ; 0,1695] | 0,162108 [0,1581 ; 0,1695] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer_diplo | 5 | 0,044268 [0,0412 ; 0,0466] | 0,044268 [0,0412 ; 0,0466] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | **cmer** | 5 | 0,046478 [0,0438 ; 0,0489] | 0,046500 [0,0438 ; 0,0489] | +2,13e-05 [+1,37e-05 ; +3,05e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −7 à −14) |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | **mer** | 5 | 0,158456 [0,1550 ; 0,1654] | 0,158525 [0,1551 ; 0,1655] | +6,85e-05 [+4,26e-05 ; +8,61e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −1 à −2) |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | unanchored_trigrams | 5 | 0,060847 [0,0587 ; 0,0636] | 0,060847 [0,0587 ; 0,0636] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | cer | 5 | 0,051342 [0,0499 ; 0,0539] | 0,051342 [0,0499 ; 0,0539] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | wer | 5 | 0,187573 [0,1859 ; 0,1892] | 0,187573 [0,1859 ; 0,1892] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | cer_diplo | 5 | 0,045262 [0,0437 ; 0,0478] | 0,045262 [0,0437 ; 0,0478] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | **cmer** | 5 | 0,050614 [0,0492 ; 0,0530] | 0,050626 [0,0492 ; 0,0531] | +1,17e-05 [+8,77e-06 ; +1,58e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −4 à −7) |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | mer | 5 | 0,182312 [0,1809 ; 0,1836] | 0,182312 [0,1809 ; 0,1836] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | unanchored_trigrams | 5 | 0,079589 [0,0775 ; 0,0818] | 0,079589 [0,0775 ; 0,0818] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer | 5 | 0,063628 [0,0565 ; 0,0733] | 0,063628 [0,0565 ; 0,0733] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | wer | 5 | 0,217198 [0,2017 ; 0,2311] | 0,217198 [0,2017 ; 0,2311] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer_diplo | 5 | 0,058009 [0,0515 ; 0,0674] | 0,058009 [0,0515 ; 0,0674] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | **cmer** | 5 | 0,062417 [0,0556 ; 0,0714] | 0,062440 [0,0556 ; 0,0715] | +2,28e-05 [+1,84e-05 ; +2,89e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −7 à −10) |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | mer | 5 | 0,210615 [0,1962 ; 0,2246] | 0,210615 [0,1962 ; 0,2246] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | unanchored_trigrams | 5 | 0,097361 [0,0916 ; 0,1062] | 0,097361 [0,0916 ; 0,1062] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer | 5 | 0,093513 [0,0793 ; 0,1029] | 0,093513 [0,0793 ; 0,1029] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | wer | 5 | 0,274840 [0,2555 ; 0,2840] | 0,274840 [0,2555 ; 0,2840] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer_diplo | 5 | 0,086033 [0,0724 ; 0,0951] | 0,086033 [0,0724 ; 0,0951] | 0 | 37/37 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | **cmer** | 5 | 0,089388 [0,0768 ; 0,0974] | 0,089421 [0,0768 ; 0,0974] | +3,33e-05 [+2,50e-05 ; +4,37e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −6 à −13) |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | **mer** | 5 | 0,259106 [0,2439 ; 0,2652] | 0,259174 [0,2440 ; 0,2653] | +6,78e-05 [+6,46e-05 ; +6,94e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −1) |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | unanchored_trigrams | 5 | 0,114105 [0,1104 ; 0,1175] | 0,114105 [0,1104 ; 0,1175] | 0 | 37/37 | inchangé 5/5 |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | cer | 1 | 0,053302 | 0,053302 | 0 | 37/37 | inchangé 1/1 |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | wer | 1 | 0,201387 | 0,201387 | 0 | 37/37 | inchangé 1/1 |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | cer_diplo | 1 | 0,046752 | 0,046752 | 0 | 37/37 | inchangé 1/1 |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | **cmer** | 1 | 0,052564 | 0,052575 | +1,17e-05 | 37/37 | canonique S/D/I 1/1 (ΣI −5) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | mer | 1 | 0,196163 | 0,196163 | 0 | 37/37 | inchangé 1/1 |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | unanchored_trigrams | 1 | 0,088642 | 0,088642 | 0 | 37/37 | inchangé 1/1 |
| texte | E5 · mistral (VLM) | cer | 5 | 0,034484 [0,0325 ; 0,0379] | 0,034484 [0,0325 ; 0,0379] | 0 | 37/37 | inchangé 5/5 |
| texte | E5 · mistral (VLM) | wer | 5 | 0,165437 [0,1603 ; 0,1759] | 0,165437 [0,1603 ; 0,1759] | 0 | 37/37 | inchangé 5/5 |
| texte | E5 · mistral (VLM) | cer_diplo | 5 | 0,034267 [0,0325 ; 0,0369] | 0,034267 [0,0325 ; 0,0369] | 0 | 37/37 | inchangé 5/5 |
| texte | E5 · mistral (VLM) | **cmer** | 5 | 0,034236 [0,0322 ; 0,0377] | 0,034240 [0,0322 ; 0,0377] | +4,05e-06 [+1,45e-06 ; +6,41e-06] | 37/37 | canonique S/D/I 5/5 (ΣI −1 à −4) |
| texte | E5 · mistral (VLM) | **mer** | 5 | 0,162644 [0,1580 ; 0,1726] | 0,162733 [0,1581 ; 0,1727] | +8,88e-05 [+8,64e-05 ; +9,40e-05] | 37/37 | canonique S/D/I 5/5 (ΣI −2) |
| texte | E5 · mistral (VLM) | unanchored_trigrams | 5 | 0,053851 [0,0524 ; 0,0566] | 0,053851 [0,0524 ; 0,0566] | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E0 · tesseract | cer | 5 | 0,060981 | 0,060981 | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E1 · segmentation → tesseract | cer | 5 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (règles) | cer | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 5 | 0,062381 | 0,062381 | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E5 · qwen2.5vl:3b (local) | cer | 5 | 0,048514 | 0,048514 | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E0 · mistral-ocr | cer | 5 | 0,035306 [0,0352 ; 0,0356] | 0,035306 [0,0352 ; 0,0356] | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E2 · tesseract → mistral | cer | 5 | 0,048505 [0,0454 ; 0,0522] | 0,048505 [0,0454 ; 0,0522] | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E2 · mistral-ocr → mistral | cer | 5 | 0,046002 [0,0438 ; 0,0500] | 0,046002 [0,0438 ; 0,0500] | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E1 · segmentation → mistral (VLM par région) | cer | 5 | 0,054919 [0,0534 ; 0,0562] | 0,054919 [0,0534 ; 0,0562] | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer | 5 | 0,050565 [0,0474 ; 0,0529] | 0,050565 [0,0474 ; 0,0529] | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (mistral) | cer | 5 | 0,051369 [0,0500 ; 0,0539] | 0,051369 [0,0500 ; 0,0539] | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer | 5 | 0,063673 [0,0565 ; 0,0735] | 0,063673 [0,0565 ; 0,0735] | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer | 5 | 0,093703 [0,0793 ; 0,1030] | 0,093703 [0,0793 ; 0,1030] | 0 | 37/37 | inchangé 5/5 |
| texte (lignes) | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | cer | 1 | 0,053302 | 0,053302 | 0 | 37/37 | inchangé 1/1 |
| texte (lignes) | E5 · mistral (VLM) | cer | 5 | 0,049273 [0,0472 ; 0,0529] | 0,049273 [0,0472 ; 0,0529] | 0 | 37/37 | inchangé 5/5 |
| lecture | E0 · tesseract | cer | 5 | 0,058406 | 0,058406 | 0 | 37/37 | inchangé 5/5 |
| lecture | E0 · tesseract | wer | 5 | 0,237171 | 0,237171 | 0 | 37/37 | inchangé 5/5 |
| lecture | E0 · tesseract | cer_diplo | 5 | 0,049462 | 0,049462 | 0 | 37/37 | inchangé 5/5 |
| lecture | E1 · segmentation → tesseract | cer | 5 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 5/5 |
| lecture | E1 · segmentation → tesseract | wer | 5 | 0,252150 | 0,252150 | 0 | 37/37 | inchangé 5/5 |
| lecture | E1 · segmentation → tesseract | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer | 5 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | wer | 5 | 0,252150 | 0,252150 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 5 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 5/5 |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | wer | 5 | 0,252150 | 0,252150 | 0 | 37/37 | inchangé 5/5 |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| lecture | E5 · qwen2.5vl:3b (local) | cer | 5 | 0,034149 | 0,034149 | 0 | 37/37 | inchangé 5/5 |
| lecture | E5 · qwen2.5vl:3b (local) | wer | 5 | 0,155895 | 0,155895 | 0 | 37/37 | inchangé 5/5 |
| lecture | E5 · qwen2.5vl:3b (local) | cer_diplo | 5 | 0,034149 | 0,034149 | 0 | 37/37 | inchangé 5/5 |
| lecture | E0 · mistral-ocr | cer | 5 | 0,025594 [0,0256 ; 0,0257] | 0,025594 [0,0256 ; 0,0257] | 0 | 37/37 | inchangé 5/5 |
| lecture | E0 · mistral-ocr | wer | 5 | 0,132205 [0,1320 ; 0,1326] | 0,132205 [0,1320 ; 0,1326] | 0 | 37/37 | inchangé 5/5 |
| lecture | E0 · mistral-ocr | cer_diplo | 5 | 0,025594 [0,0256 ; 0,0257] | 0,025594 [0,0256 ; 0,0257] | 0 | 37/37 | inchangé 5/5 |
| lecture | E2 · tesseract → mistral | cer | 5 | 0,058406 | 0,058406 | 0 | 37/37 | inchangé 5/5 |
| lecture | E2 · tesseract → mistral | wer | 5 | 0,237171 | 0,237171 | 0 | 37/37 | inchangé 5/5 |
| lecture | E2 · tesseract → mistral | cer_diplo | 5 | 0,049462 | 0,049462 | 0 | 37/37 | inchangé 5/5 |
| lecture | E2 · mistral-ocr → mistral | cer | 5 | 0,025639 [0,0256 ; 0,0257] | 0,025639 [0,0256 ; 0,0257] | 0 | 37/37 | inchangé 5/5 |
| lecture | E2 · mistral-ocr → mistral | wer | 5 | 0,132372 [0,1320 ; 0,1326] | 0,132372 [0,1320 ; 0,1326] | 0 | 37/37 | inchangé 5/5 |
| lecture | E2 · mistral-ocr → mistral | cer_diplo | 5 | 0,025639 [0,0256 ; 0,0257] | 0,025639 [0,0256 ; 0,0257] | 0 | 37/37 | inchangé 5/5 |
| lecture | E1 · segmentation → mistral (VLM par région) | cer | 5 | 0,041747 [0,0402 ; 0,0436] | 0,041747 [0,0402 ; 0,0436] | 0 | 37/37 | inchangé 5/5 |
| lecture | E1 · segmentation → mistral (VLM par région) | wer | 5 | 0,166158 [0,1628 ; 0,1750] | 0,166158 [0,1628 ; 0,1750] | 0 | 37/37 | inchangé 5/5 |
| lecture | E1 · segmentation → mistral (VLM par région) | cer_diplo | 5 | 0,041548 [0,0402 ; 0,0426] | 0,041548 [0,0402 ; 0,0426] | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer | 5 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 témoin · segmentation → tesseract → mistral (correction libre) | wer | 5 | 0,252150 | 0,252150 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (mistral) | cer | 5 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (mistral) | wer | 5 | 0,252150 | 0,252150 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (mistral) | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer | 5 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-8b) | wer | 5 | 0,252150 | 0,252150 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer | 5 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-3b) | wer | 5 | 0,252150 | 0,252150 | 0 | 37/37 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer_diplo | 5 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 5/5 |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | cer | 1 | 0,063917 | 0,063917 | 0 | 37/37 | inchangé 1/1 |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | wer | 1 | 0,252150 | 0,252150 | 0 | 37/37 | inchangé 1/1 |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | cer_diplo | 1 | 0,055019 | 0,055019 | 0 | 37/37 | inchangé 1/1 |
| lecture | E5 · mistral (VLM) | cer | 5 | 0,034484 [0,0325 ; 0,0379] | 0,034484 [0,0325 ; 0,0379] | 0 | 37/37 | inchangé 5/5 |
| lecture | E5 · mistral (VLM) | wer | 5 | 0,165437 [0,1603 ; 0,1759] | 0,165437 [0,1603 ; 0,1759] | 0 | 37/37 | inchangé 5/5 |
| lecture | E5 · mistral (VLM) | cer_diplo | 5 | 0,034267 [0,0325 ; 0,0369] | 0,034267 [0,0325 ; 0,0369] | 0 | 37/37 | inchangé 5/5 |
| sans césure | E0 · tesseract | cer | 5 | 0,060911 | 0,060911 | 0 | 37/37 | inchangé 5/5 |
| sans césure | E1 · segmentation → tesseract | cer | 5 | 0,064100 | 0,064100 | 0 | 37/37 | inchangé 5/5 |
| sans césure | E3 · segmentation → tesseract → saknussemm (règles) | cer | 5 | 0,055171 | 0,055171 | 0 | 37/37 | inchangé 5/5 |
| sans césure | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 5 | 0,062551 | 0,062551 | 0 | 37/37 | inchangé 5/5 |
| sans césure | E5 · qwen2.5vl:3b (local) | cer | 5 | 0,041458 | 0,041458 | 0 | 37/37 | inchangé 5/5 |
| sans césure | E0 · mistral-ocr | cer | 5 | 0,029713 [0,0296 ; 0,0300] | 0,029713 [0,0296 ; 0,0300] | 0 | 37/37 | inchangé 5/5 |
| sans césure | E2 · tesseract → mistral | cer | 5 | 0,046360 [0,0431 ; 0,0497] | 0,046360 [0,0431 ; 0,0497] | 0 | 37/37 | inchangé 5/5 |
| sans césure | E2 · mistral-ocr → mistral | cer | 5 | 0,040292 [0,0383 ; 0,0440] | 0,040292 [0,0383 ; 0,0440] | 0 | 37/37 | inchangé 5/5 |
| sans césure | E1 · segmentation → mistral (VLM par région) | cer | 5 | 0,060738 [0,0591 ; 0,0621] | 0,060738 [0,0591 ; 0,0621] | 0 | 37/37 | inchangé 5/5 |
| sans césure | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer | 5 | 0,048128 [0,0450 ; 0,0508] | 0,048128 [0,0450 ; 0,0508] | 0 | 37/37 | inchangé 5/5 |
| sans césure | E3 · segmentation → tesseract → saknussemm (mistral) | cer | 5 | 0,051390 [0,0500 ; 0,0540] | 0,051390 [0,0500 ; 0,0540] | 0 | 37/37 | inchangé 5/5 |
| sans césure | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer | 5 | 0,063790 [0,0567 ; 0,0737] | 0,063790 [0,0567 ; 0,0737] | 0 | 37/37 | inchangé 5/5 |
| sans césure | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer | 5 | 0,094105 [0,0796 ; 0,1035] | 0,094105 [0,0796 ; 0,1035] | 0 | 37/37 | inchangé 5/5 |
| sans césure | E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert) | cer | 1 | 0,053394 | 0,053394 | 0 | 37/37 | inchangé 1/1 |
| sans césure | E5 · mistral (VLM) | cer | 5 | 0,043654 [0,0419 ; 0,0470] | 0,043654 [0,0419 ; 0,0470] | 0 | 37/37 | inchangé 5/5 |

### S31 · Dresden (`dresden.yaml`, 130 unités × 5 répétitions)

143 lignes (vue × pipeline × métrique), 715 agrégats sur les 5 répétitions : inchangé 616, canonique S/D/I 89, autre : arrondi unique (1 ULP) 10.

| vue | pipeline | métrique | rép. | v5 moy. [min ; max] | v6 moy. [min ; max] | Δ moy. [min ; max] | notés/attendus | cause |
|---|---|---|---|---|---|---|---|---|
| texte | E0 · tesseract | cer | 5 | 0,756345 | 0,756345 | 0 | 10/10 | inchangé 5/5 |
| texte | E0 · tesseract | wer | 5 | 0,998704 | 0,998704 | 0 | 10/10 | inchangé 5/5 |
| texte | E0 · tesseract | cer_diplo | 5 | 0,755669 | 0,755669 | 0 | 10/10 | inchangé 5/5 |
| texte | E0 · tesseract | **cmer** | 5 | 0,752713 | 0,754742 | +2,03e-03 | 10/10 | canonique S/D/I 5/5 (ΣI −28) |
| texte | E0 · tesseract | mer | 5 | 0,994194 | 0,994194 | 0 | 10/10 | inchangé 5/5 |
| texte | E0 · tesseract | unanchored_trigrams | 5 | 0,841243 | 0,841243 | 0 | 10/10 | inchangé 5/5 |
| texte | E1 · segmentation → tesseract | cer | 5 | 0,777478 | 0,777478 | 0 | 10/10 | inchangé 5/5 |
| texte | E1 · segmentation → tesseract | wer | 5 | 1,303953 | 1,303953 | 0 | 10/10 | inchangé 5/5 |
| texte | E1 · segmentation → tesseract | cer_diplo | 5 | 0,776609 | 0,776609 | 0 | 10/10 | inchangé 5/5 |
| texte | E1 · segmentation → tesseract | **cmer** | 5 | 0,749628 | 0,755603 | +5,98e-03 | 10/10 | canonique S/D/I 5/5 (ΣI −85) |
| texte | E1 · segmentation → tesseract | mer | 5 | 0,994563 | 0,994563 | 0 | 10/10 | inchangé 5/5 |
| texte | E1 · segmentation → tesseract | unanchored_trigrams | 5 | 0,862971 | 0,862971 | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer | 5 | 0,777767 | 0,777767 | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | wer | 5 | 1,303953 | 1,303953 | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 5 | 0,776609 | 0,776609 | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **cmer** | 5 | 0,749977 | 0,755885 | +5,91e-03 | 10/10 | canonique S/D/I 5/5 (ΣI −84) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | mer | 5 | 0,994563 | 0,994563 | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | unanchored_trigrams | 5 | 0,863489 | 0,863489 | 0 | 10/10 | inchangé 5/5 |
| texte | E5 · qwen2.5vl:3b (local) | cer | 5 | 1,861423 | 1,861423 | 0 | 4/10 | inchangé 5/5 |
| texte | E5 · qwen2.5vl:3b (local) | wer | 5 | 2,484298 | 2,484298 | 0 | 4/10 | inchangé 5/5 |
| texte | E5 · qwen2.5vl:3b (local) | cer_diplo | 5 | 1,852294 | 1,852294 | 0 | 4/10 | inchangé 5/5 |
| texte | E5 · qwen2.5vl:3b (local) | **cmer** | 5 | 0,768532 | 0,769499 | +9,67e-04 | 4/10 | canonique S/D/I 5/5 (ΣI −13) |
| texte | E5 · qwen2.5vl:3b (local) | **mer** | 5 | 0,947667 | 0,948265 | +5,98e-04 | 4/10 | canonique S/D/I 5/5 (ΣI −1) |
| texte | E5 · qwen2.5vl:3b (local) | unanchored_trigrams | 5 | 0,555440 | 0,555440 | 0 | 4/10 | inchangé 5/5 |
| texte | E0 · mistral-ocr | cer | 5 | 3,590234 [2,3922 ; 5,0602] | 3,590234 [2,3922 ; 5,0602] | 0 | 10/10 | inchangé 5/5 |
| texte | E0 · mistral-ocr | wer | 5 | 4,049644 [3,4485 ; 5,0266] | 4,049644 [3,4485 ; 5,0266] | 0 | 10/10 | inchangé 5/5 |
| texte | E0 · mistral-ocr | cer_diplo | 5 | 3,585854 [2,3893 ; 5,0549] | 3,585854 [2,3893 ; 5,0549] | 0 | 10/10 | inchangé 5/5 |
| texte | E0 · mistral-ocr | **cmer** | 5 | 0,856594 [0,8053 ; 0,9017] | 0,857822 [0,8069 ; 0,9027] | +1,23e-03 [+9,93e-04 ; +1,60e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −42 à −72) |
| texte | E0 · mistral-ocr | **mer** | 5 | 0,949669 [0,9408 ; 0,9646] | 0,950113 [0,9408 ; 0,9661] | +4,43e-04 [0 ; +1,56e-03] | 10/10 | inchangé 2/5, canonique S/D/I 3/5 (ΣI −2 à −13) |
| texte | E0 · mistral-ocr | unanchored_trigrams | 5 | 0,645667 [0,6259 ; 0,6643] | 0,645667 [0,6259 ; 0,6643] | 0 | 10/10 | inchangé 5/5 |
| texte | E2 · tesseract → mistral | cer | 5 | 0,757117 [0,7566 ; 0,7580] | 0,757117 [0,7566 ; 0,7580] | 0 | 10/10 | inchangé 5/5 |
| texte | E2 · tesseract → mistral | wer | 5 | 0,997019 [0,9948 ; 0,9981] | 0,997019 [0,9948 ; 0,9981] | 0 | 10/10 | inchangé 5/5 |
| texte | E2 · tesseract → mistral | cer_diplo | 5 | 0,756306 [0,7559 ; 0,7572] | 0,756306 [0,7559 ; 0,7572] | 0 | 10/10 | inchangé 5/5 |
| texte | E2 · tesseract → mistral | **cmer** | 5 | 0,753250 [0,7528 ; 0,7542] | 0,755615 [0,7550 ; 0,7566] | +2,36e-03 [+2,25e-03 ; +2,40e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −31 à −33) |
| texte | E2 · tesseract → mistral | **mer** | 5 | 0,993927 [0,9929 ; 0,9948] | 0,994055 [0,9935 ; 0,9948] | +1,28e-04 [0 ; +6,41e-04] | 10/10 | inchangé 4/5, canonique S/D/I 1/5 (ΣI −1) |
| texte | E2 · tesseract → mistral | unanchored_trigrams | 5 | 0,837627 [0,8351 ; 0,8400] | 0,837627 [0,8351 ; 0,8400] | 0 | 10/10 | inchangé 5/5 |
| texte | E2 · mistral-ocr → mistral | cer | 5 | 0,630107 [0,5773 ; 0,6742] | 0,630107 [0,5773 ; 0,6742] | 0 | 10/10 | inchangé 5/5 |
| texte | E2 · mistral-ocr → mistral | wer | 5 | 1,017628 [0,9456 ; 1,1303] | 1,017628 [0,9456 ; 1,1303] | 0 | 10/10 | inchangé 5/5 |
| texte | E2 · mistral-ocr → mistral | cer_diplo | 5 | 0,626074 [0,5737 ; 0,6690] | 0,626074 [0,5737 ; 0,6690] | 0 | 10/10 | inchangé 5/5 |
| texte | E2 · mistral-ocr → mistral | **cmer** | 5 | 0,553887 [0,5311 ; 0,5777] | 0,557776 [0,5377 ; 0,5813] | +3,89e-03 [+2,74e-03 ; +6,54e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −59 à −137) |
| texte | E2 · mistral-ocr → mistral | **mer** | 5 | 0,835274 [0,8281 ; 0,8432] | 0,836014 [0,8281 ; 0,8441] | +7,40e-04 [0 ; +1,43e-03] | 10/10 | inchangé 1/5, canonique S/D/I 4/5 (ΣI −1 à −3) |
| texte | E2 · mistral-ocr → mistral | unanchored_trigrams | 5 | 0,487151 [0,4787 ; 0,4953] | 0,487151 [0,4787 ; 0,4953] | 0 | 10/10 | inchangé 5/5 |
| texte | E1 · segmentation → mistral (VLM par région) | cer | 5 | 1,153160 [1,1196 ; 1,2000] | 1,153160 [1,1196 ; 1,2000] | 0 | 10/10 | inchangé 5/5 |
| texte | E1 · segmentation → mistral (VLM par région) | wer | 5 | 1,652625 [1,6111 ; 1,7168] | 1,652625 [1,6111 ; 1,7168] | 0 | 10/10 | inchangé 5/5 |
| texte | E1 · segmentation → mistral (VLM par région) | cer_diplo | 5 | 1,147448 [1,1138 ; 1,1941] | 1,147448 [1,1138 ; 1,1941] | 0 | 10/10 | inchangé 5/5 |
| texte | E1 · segmentation → mistral (VLM par région) | **cmer** | 5 | 0,732265 [0,7287 ; 0,7363] | 0,738743 [0,7352 ; 0,7425] | +6,48e-03 [+6,16e-03 ; +7,24e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −135 à −156) |
| texte | E1 · segmentation → mistral (VLM par région) | **mer** | 5 | 0,957997 [0,9570 ; 0,9587] | 0,959697 [0,9582 ; 0,9636] | +1,70e-03 [+3,70e-04 ; +4,88e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −1 à −14) |
| texte | E1 · segmentation → mistral (VLM par région) | unanchored_trigrams | 5 | 0,696202 [0,6905 ; 0,7041] | 0,696202 [0,6905 ; 0,7041] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer | 5 | 0,778018 [0,7745 ; 0,7872] | 0,778018 [0,7745 ; 0,7872] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | wer | 5 | 1,282566 [1,2618 ; 1,2994] | 1,282566 [1,2618 ; 1,2994] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer_diplo | 5 | 0,777304 [0,7737 ; 0,7866] | 0,777304 [0,7737 ; 0,7866] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | **cmer** | 5 | 0,751168 [0,7483 ; 0,7595] | 0,758159 [0,7551 ; 0,7660] | +6,99e-03 [+6,49e-03 ; +7,41e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −91 à −105) |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | mer | 5 | 0,994370 [0,9939 ; 0,9945] | 0,994370 [0,9939 ; 0,9945] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 témoin · segmentation → tesseract → mistral (correction libre) | unanchored_trigrams | 5 | 0,863723 [0,8574 ; 0,8755] | 0,863723 [0,8574 ; 0,8755] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | cer | 5 | 0,777227 [0,7770 ; 0,7775] | 0,777227 [0,7770 ; 0,7775] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | wer | 5 | 1,302268 [1,3014 ; 1,3033] | 1,302268 [1,3014 ; 1,3033] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | cer_diplo | 5 | 0,776377 [0,7761 ; 0,7766] | 0,776377 [0,7761 ; 0,7766] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | **cmer** | 5 | 0,749442 [0,7492 ; 0,7499] | 0,755416 [0,7549 ; 0,7557] | +5,97e-03 [+5,76e-03 ; +6,33e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −82 à −90) |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | mer | 5 | 0,994457 [0,9941 ; 0,9946] | 0,994457 [0,9941 ; 0,9946] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (mistral) | unanchored_trigrams | 5 | 0,862588 [0,8624 ; 0,8629] | 0,862588 [0,8624 ; 0,8629] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer | 5 | 0,777458 [0,7772 ; 0,7777] | 0,777458 [0,7772 ; 0,7777] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | wer | 5 | 1,296047 [1,2936 ; 1,2975] | 1,296047 [1,2936 ; 1,2975] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer_diplo | 5 | 0,776648 [0,7763 ; 0,7768] | 0,776648 [0,7763 ; 0,7768] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | **cmer** | 5 | 0,749693 [0,7494 ; 0,7500] | 0,756153 [0,7552 ; 0,7570] | +6,46e-03 [+5,69e-03 ; +7,54e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −81 à −107) |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | **mer** | 5 | 0,994530 [0,9945 ; 0,9945] | 0,994628 [0,9945 ; 0,9950] | +9,89e-05 [0 ; +4,94e-04] | 10/10 | inchangé 4/5, canonique S/D/I 1/5 (ΣI −1) |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-8b) | unanchored_trigrams | 5 | 0,862643 [0,8617 ; 0,8630] | 0,862643 [0,8617 ; 0,8630] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer | 5 | 0,777342 [0,7771 ; 0,7778] | 0,777342 [0,7771 ; 0,7778] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | wer | 5 | 1,299935 [1,2962 ; 1,3104] | 1,299935 [1,2962 ; 1,3104] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer_diplo | 5 | 0,776397 [0,7762 ; 0,7767] | 0,776397 [0,7762 ; 0,7767] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | **cmer** | 5 | 0,750755 [0,7502 ; 0,7514] | 0,757376 [0,7564 ; 0,7581] | +6,62e-03 [+6,27e-03 ; +6,91e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −89 à −98) |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | mer | 5 | 0,994448 [0,9941 ; 0,9945] | 0,994448 [0,9941 ; 0,9945] | 0 | 10/10 | inchangé 5/5 |
| texte | E3 · segmentation → tesseract → saknussemm (ministral-3b) | unanchored_trigrams | 5 | 0,863078 [0,8618 ; 0,8638] | 0,863078 [0,8618 ; 0,8638] | 0 | 10/10 | inchangé 5/5 |
| texte | E5 · mistral (VLM) | cer | 5 | 0,844948 [0,8125 ; 0,9009] | 0,844948 [0,8125 ; 0,9009] | 0 | 10/10 | inchangé 5/5 |
| texte | E5 · mistral (VLM) | wer | 5 | 1,157745 [1,1069 ; 1,1970] | 1,157745 [1,1069 ; 1,1970] | 0 | 10/10 | inchangé 5/5 |
| texte | E5 · mistral (VLM) | cer_diplo | 5 | 0,840664 [0,8084 ; 0,8966] | 0,840664 [0,8084 ; 0,8966] | 0 | 10/10 | inchangé 5/5 |
| texte | E5 · mistral (VLM) | **cmer** | 5 | 0,690650 [0,6829 ; 0,6969] | 0,700543 [0,6950 ; 0,7055] | +9,89e-03 [+7,84e-03 ; +1,21e-02] | 10/10 | canonique S/D/I 5/5 (ΣI −149 à −214) |
| texte | E5 · mistral (VLM) | **mer** | 5 | 0,927991 [0,9223 ; 0,9324] | 0,931293 [0,9270 ; 0,9364] | +3,30e-03 [+1,89e-03 ; +4,64e-03] | 10/10 | canonique S/D/I 5/5 (ΣI −4 à −10) |
| texte | E5 · mistral (VLM) | unanchored_trigrams | 5 | 0,591465 [0,5715 ; 0,6066] | 0,591465 [0,5715 ; 0,6066] | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E0 · tesseract | cer | 5 | 0,768310 | 0,768310 | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E1 · segmentation → tesseract | cer | 5 | 0,794944 | 0,794944 | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (règles) | cer | 5 | 0,795330 | 0,795330 | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E5 · qwen2.5vl:3b (local) | **cer** | 5 | 1,870552 | 1,870552 | +2,22e-16 | 4/10 | **autre** : arrondi unique 5/5 (1 ULP) |
| texte (lignes) | E0 · mistral-ocr | cer | 5 | 3,594615 [2,3955 ; 5,0652] | 3,594615 [2,3955 ; 5,0652] | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E2 · tesseract → mistral | cer | 5 | 0,769063 [0,7688 ; 0,7698] | 0,769063 [0,7688 ; 0,7698] | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E2 · mistral-ocr → mistral | cer | 5 | 0,639738 [0,5906 ; 0,6840] | 0,639738 [0,5906 ; 0,6840] | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E1 · segmentation → mistral (VLM par région) | cer | 5 | 1,166805 [1,1336 ; 1,2131] | 1,166805 [1,1336 ; 1,2131] | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer | 5 | 0,795523 [0,7920 ; 0,8053] | 0,795523 [0,7920 ; 0,8053] | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (mistral) | cer | 5 | 0,794577 [0,7945 ; 0,7948] | 0,794577 [0,7945 ; 0,7948] | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer | 5 | 0,794751 [0,7946 ; 0,7949] | 0,794751 [0,7946 ; 0,7949] | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer | 5 | 0,794693 [0,7942 ; 0,7951] | 0,794693 [0,7942 ; 0,7951] | 0 | 10/10 | inchangé 5/5 |
| texte (lignes) | E5 · mistral (VLM) | cer | 5 | 0,859172 [0,8274 ; 0,9171] | 0,859172 [0,8274 ; 0,9171] | 0 | 10/10 | inchangé 5/5 |
| lecture | E0 · tesseract | cer | 5 | 0,756345 | 0,756345 | 0 | 10/10 | inchangé 5/5 |
| lecture | E0 · tesseract | wer | 5 | 0,998704 | 0,998704 | 0 | 10/10 | inchangé 5/5 |
| lecture | E0 · tesseract | cer_diplo | 5 | 0,755669 | 0,755669 | 0 | 10/10 | inchangé 5/5 |
| lecture | E1 · segmentation → tesseract | cer | 5 | 0,777478 | 0,777478 | 0 | 10/10 | inchangé 5/5 |
| lecture | E1 · segmentation → tesseract | wer | 5 | 1,303953 | 1,303953 | 0 | 10/10 | inchangé 5/5 |
| lecture | E1 · segmentation → tesseract | cer_diplo | 5 | 0,776609 | 0,776609 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer | 5 | 0,777478 | 0,777478 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | wer | 5 | 1,303953 | 1,303953 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 5 | 0,776609 | 0,776609 | 0 | 10/10 | inchangé 5/5 |
| lecture | E5 · qwen2.5vl:3b (local) | cer | 5 | 1,861423 | 1,861423 | 0 | 4/10 | inchangé 5/5 |
| lecture | E5 · qwen2.5vl:3b (local) | wer | 5 | 2,484298 | 2,484298 | 0 | 4/10 | inchangé 5/5 |
| lecture | E5 · qwen2.5vl:3b (local) | cer_diplo | 5 | 1,852294 | 1,852294 | 0 | 4/10 | inchangé 5/5 |
| lecture | E0 · mistral-ocr | cer | 5 | 3,590234 [2,3922 ; 5,0602] | 3,590234 [2,3922 ; 5,0602] | 0 | 10/10 | inchangé 5/5 |
| lecture | E0 · mistral-ocr | wer | 5 | 4,049644 [3,4485 ; 5,0266] | 4,049644 [3,4485 ; 5,0266] | 0 | 10/10 | inchangé 5/5 |
| lecture | E0 · mistral-ocr | cer_diplo | 5 | 3,585854 [2,3893 ; 5,0549] | 3,585854 [2,3893 ; 5,0549] | 0 | 10/10 | inchangé 5/5 |
| lecture | E2 · tesseract → mistral | cer | 5 | 0,756345 | 0,756345 | 0 | 10/10 | inchangé 5/5 |
| lecture | E2 · tesseract → mistral | wer | 5 | 0,998704 | 0,998704 | 0 | 10/10 | inchangé 5/5 |
| lecture | E2 · tesseract → mistral | cer_diplo | 5 | 0,755669 | 0,755669 | 0 | 10/10 | inchangé 5/5 |
| lecture | E2 · mistral-ocr → mistral | cer | 5 | 1,829374 [0,9217 ; 3,8496] | 1,829374 [0,9217 ; 3,8496] | 0 | 10/10 | inchangé 5/5 |
| lecture | E2 · mistral-ocr → mistral | wer | 5 | 2,676604 [1,5100 ; 5,3798] | 2,676604 [1,5100 ; 5,3798] | 0 | 10/10 | inchangé 5/5 |
| lecture | E2 · mistral-ocr → mistral | cer_diplo | 5 | 1,826093 [0,9179 ; 3,8450] | 1,826093 [0,9179 ; 3,8450] | 0 | 10/10 | inchangé 5/5 |
| lecture | E1 · segmentation → mistral (VLM par région) | cer | 5 | 1,153160 [1,1196 ; 1,2000] | 1,153160 [1,1196 ; 1,2000] | 0 | 10/10 | inchangé 5/5 |
| lecture | E1 · segmentation → mistral (VLM par région) | wer | 5 | 1,652625 [1,6111 ; 1,7168] | 1,652625 [1,6111 ; 1,7168] | 0 | 10/10 | inchangé 5/5 |
| lecture | E1 · segmentation → mistral (VLM par région) | cer_diplo | 5 | 1,147448 [1,1138 ; 1,1941] | 1,147448 [1,1138 ; 1,1941] | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer | 5 | 0,777478 | 0,777478 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 témoin · segmentation → tesseract → mistral (correction libre) | wer | 5 | 1,303953 | 1,303953 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer_diplo | 5 | 0,776609 | 0,776609 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (mistral) | cer | 5 | 0,777478 | 0,777478 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (mistral) | wer | 5 | 1,303953 | 1,303953 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (mistral) | cer_diplo | 5 | 0,776609 | 0,776609 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer | 5 | 0,777478 | 0,777478 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-8b) | wer | 5 | 1,303953 | 1,303953 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer_diplo | 5 | 0,776609 | 0,776609 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer | 5 | 0,777478 | 0,777478 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-3b) | wer | 5 | 1,303953 | 1,303953 | 0 | 10/10 | inchangé 5/5 |
| lecture | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer_diplo | 5 | 0,776609 | 0,776609 | 0 | 10/10 | inchangé 5/5 |
| lecture | E5 · mistral (VLM) | cer | 5 | 0,844948 [0,8125 ; 0,9009] | 0,844948 [0,8125 ; 0,9009] | 0 | 10/10 | inchangé 5/5 |
| lecture | E5 · mistral (VLM) | wer | 5 | 1,157745 [1,1069 ; 1,1970] | 1,157745 [1,1069 ; 1,1970] | 0 | 10/10 | inchangé 5/5 |
| lecture | E5 · mistral (VLM) | cer_diplo | 5 | 0,840664 [0,8084 ; 0,8966] | 0,840664 [0,8084 ; 0,8966] | 0 | 10/10 | inchangé 5/5 |
| sans césure | E0 · tesseract | cer | 5 | 0,768073 | 0,768073 | 0 | 10/10 | inchangé 5/5 |
| sans césure | E1 · segmentation → tesseract | cer | 5 | 0,794711 | 0,794711 | 0 | 10/10 | inchangé 5/5 |
| sans césure | E3 · segmentation → tesseract → saknussemm (règles) | cer | 5 | 0,795097 | 0,795097 | 0 | 10/10 | inchangé 5/5 |
| sans césure | E5 · qwen2.5vl:3b (local) | **cer** | 5 | 1,871663 | 1,871663 | +2,22e-16 | 4/10 | **autre** : arrondi unique 5/5 (1 ULP) |
| sans césure | E0 · mistral-ocr | cer | 5 | 3,595502 [2,3962 ; 5,0664] | 3,595502 [2,3962 ; 5,0664] | 0 | 10/10 | inchangé 5/5 |
| sans césure | E2 · tesseract → mistral | cer | 5 | 0,768980 [0,7687 ; 0,7697] | 0,768980 [0,7687 ; 0,7697] | 0 | 10/10 | inchangé 5/5 |
| sans césure | E2 · mistral-ocr → mistral | cer | 5 | 0,639996 [0,5905 ; 0,6845] | 0,639996 [0,5905 ; 0,6845] | 0 | 10/10 | inchangé 5/5 |
| sans césure | E1 · segmentation → mistral (VLM par région) | cer | 5 | 1,167937 [1,1344 ; 1,2144] | 1,167937 [1,1344 ; 1,2144] | 0 | 10/10 | inchangé 5/5 |
| sans césure | E3 témoin · segmentation → tesseract → mistral (correction libre) | cer | 5 | 0,795290 [0,7917 ; 0,8050] | 0,795290 [0,7917 ; 0,8050] | 0 | 10/10 | inchangé 5/5 |
| sans césure | E3 · segmentation → tesseract → saknussemm (mistral) | cer | 5 | 0,794344 [0,7942 ; 0,7945] | 0,794344 [0,7942 ; 0,7945] | 0 | 10/10 | inchangé 5/5 |
| sans césure | E3 · segmentation → tesseract → saknussemm (ministral-8b) | cer | 5 | 0,794518 [0,7943 ; 0,7947] | 0,794518 [0,7943 ; 0,7947] | 0 | 10/10 | inchangé 5/5 |
| sans césure | E3 · segmentation → tesseract → saknussemm (ministral-3b) | cer | 5 | 0,794460 [0,7939 ; 0,7949] | 0,794460 [0,7939 ; 0,7949] | 0 | 10/10 | inchangé 5/5 |
| sans césure | E5 · mistral (VLM) | cer | 5 | 0,859087 [0,8274 ; 0,9170] | 0,859087 [0,8274 ; 0,9170] | 0 | 10/10 | inchangé 5/5 |

### S31L · BNL (`bnl-local.yaml`, 259 unités)

77 agrégats : inchangé 64, canonique S/D/I 13.

| vue | pipeline | métrique | v5 | v6 | Δ | notés/attendus | cause |
|---|---|---|---|---|---|---|---|
| texte | E0 · tesseract | cer | 0,058406 | 0,058406 | 0 | 37/37 | inchangé |
| texte | E0 · tesseract | wer | 0,237171 | 0,237171 | 0 | 37/37 | inchangé |
| texte | E0 · tesseract | cer_diplo | 0,049462 | 0,049462 | 0 | 37/37 | inchangé |
| texte | E0 · tesseract | **cmer** | 0,057801 | 0,057814 | +1,29e-05 | 37/37 | canonique S/D/I (ΣI 232→227, 4/37 doc.) |
| texte | E0 · tesseract | **mer** | 0,231519 | 0,231582 | +6,27e-05 | 37/37 | canonique S/D/I (ΣI 88→87, 1/37 doc.) |
| texte | E0 · tesseract | unanchored_trigrams | 0,110905 | 0,110905 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → tesseract | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → tesseract | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → tesseract | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → tesseract | **cmer** | 0,062956 | 0,062970 | +1,40e-05 | 37/37 | canonique S/D/I (ΣI 338→333, 4/37 doc.) |
| texte | E1 · segmentation → tesseract | **mer** | 0,244750 | 0,244816 | +6,59e-05 | 37/37 | canonique S/D/I (ΣI 109→108, 1/37 doc.) |
| texte | E1 · segmentation → tesseract | unanchored_trigrams | 0,117700 | 0,117700 | 0 | 37/37 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | wer | 0,214979 | 0,214979 | 0 | 37/37 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **cmer** | 0,054191 | 0,054203 | +1,21e-05 | 37/37 | canonique S/D/I (ΣI 338→333, 4/37 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **mer** | 0,208670 | 0,208726 | +5,62e-05 | 37/37 | canonique S/D/I (ΣI 109→108, 1/37 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | unanchored_trigrams | 0,094178 | 0,094178 | 0 | 37/37 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,062381 | 0,062381 | 0 | 37/37 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | wer | 0,245492 | 0,245492 | 0 | 37/37 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | **cmer** | 0,061443 | 0,061457 | +1,37e-05 | 37/37 | canonique S/D/I (ΣI 338→333, 4/37 doc.) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | **mer** | 0,238288 | 0,238352 | +6,42e-05 | 37/37 | canonique S/D/I (ΣI 109→108, 1/37 doc.) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | unanchored_trigrams | 0,113735 | 0,113735 | 0 | 37/37 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer | 0,034149 | 0,034149 | 0 | 37/37 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | wer | 0,155895 | 0,155895 | 0 | 37/37 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer_diplo | 0,034149 | 0,034149 | 0 | 37/37 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | **cmer** | 0,034005 | 0,034008 | +3,06e-06 | 37/37 | canonique S/D/I (ΣI 94→92, 2/37 doc.) |
| texte | E5 · qwen2.5vl:3b (local) | **mer** | 0,154523 | 0,154565 | +4,25e-05 | 37/37 | canonique S/D/I (ΣI 32→31, 1/37 doc.) |
| texte | E5 · qwen2.5vl:3b (local) | unanchored_trigrams | 0,051230 | 0,051230 | 0 | 37/37 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | cer | 0,073313 | 0,073313 | 0 | 37/37 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | wer | 0,239112 | 0,239112 | 0 | 37/37 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | cer_diplo | 0,068073 | 0,068073 | 0 | 37/37 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | **cmer** | 0,072520 | 0,072546 | +2,59e-05 | 37/37 | canonique S/D/I (ΣI 242→234, 7/37 doc.) |
| texte | E2 · tesseract → qwen2.5:3b (local) | mer | 0,233985 | 0,233985 | 0 | 37/37 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | unanchored_trigrams | 0,097352 | 0,097352 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer | 0,083702 | 0,083702 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | wer | 0,211928 | 0,211928 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer_diplo | 0,083702 | 0,083702 | 0 | 37/37 | inchangé |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | **cmer** | 0,079012 | 0,079019 | +6,74e-06 | 37/37 | canonique S/D/I (ΣI 1314→1312, 2/37 doc.) |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | **mer** | 0,198493 | 0,198545 | +5,16e-05 | 37/37 | canonique S/D/I (ΣI 244→243, 1/37 doc.) |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | unanchored_trigrams | 0,079202 | 0,079202 | 0 | 37/37 | inchangé |
| texte (lignes) | E0 · tesseract | cer | 0,060981 | 0,060981 | 0 | 37/37 | inchangé |
| texte (lignes) | E1 · segmentation → tesseract | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| texte (lignes) | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,062381 | 0,062381 | 0 | 37/37 | inchangé |
| texte (lignes) | E5 · qwen2.5vl:3b (local) | cer | 0,048514 | 0,048514 | 0 | 37/37 | inchangé |
| texte (lignes) | E2 · tesseract → qwen2.5:3b (local) | cer | 0,082708 | 0,082708 | 0 | 37/37 | inchangé |
| texte (lignes) | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer | 0,096169 | 0,096169 | 0 | 37/37 | inchangé |
| lecture | E0 · tesseract | cer | 0,058406 | 0,058406 | 0 | 37/37 | inchangé |
| lecture | E0 · tesseract | wer | 0,237171 | 0,237171 | 0 | 37/37 | inchangé |
| lecture | E0 · tesseract | cer_diplo | 0,049462 | 0,049462 | 0 | 37/37 | inchangé |
| lecture | E1 · segmentation → tesseract | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| lecture | E1 · segmentation → tesseract | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| lecture | E1 · segmentation → tesseract | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,063917 | 0,063917 | 0 | 37/37 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | wer | 0,252150 | 0,252150 | 0 | 37/37 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer_diplo | 0,055019 | 0,055019 | 0 | 37/37 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer | 0,034149 | 0,034149 | 0 | 37/37 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | wer | 0,155895 | 0,155895 | 0 | 37/37 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer_diplo | 0,034149 | 0,034149 | 0 | 37/37 | inchangé |
| lecture | E2 · tesseract → qwen2.5:3b (local) | cer | 0,058406 | 0,058406 | 0 | 37/37 | inchangé |
| lecture | E2 · tesseract → qwen2.5:3b (local) | wer | 0,237171 | 0,237171 | 0 | 37/37 | inchangé |
| lecture | E2 · tesseract → qwen2.5:3b (local) | cer_diplo | 0,049462 | 0,049462 | 0 | 37/37 | inchangé |
| lecture | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer | 0,083702 | 0,083702 | 0 | 37/37 | inchangé |
| lecture | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | wer | 0,211928 | 0,211928 | 0 | 37/37 | inchangé |
| lecture | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer_diplo | 0,083702 | 0,083702 | 0 | 37/37 | inchangé |
| sans césure | E0 · tesseract | cer | 0,060911 | 0,060911 | 0 | 37/37 | inchangé |
| sans césure | E1 · segmentation → tesseract | cer | 0,064100 | 0,064100 | 0 | 37/37 | inchangé |
| sans césure | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,055171 | 0,055171 | 0 | 37/37 | inchangé |
| sans césure | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,062551 | 0,062551 | 0 | 37/37 | inchangé |
| sans césure | E5 · qwen2.5vl:3b (local) | cer | 0,041458 | 0,041458 | 0 | 37/37 | inchangé |
| sans césure | E2 · tesseract → qwen2.5:3b (local) | cer | 0,078405 | 0,078405 | 0 | 37/37 | inchangé |
| sans césure | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer | 0,089841 | 0,089841 | 0 | 37/37 | inchangé |

### S31L · BNL (`bnl-local-saknussemm.yaml`, 45 unités, sous-ensemble de 5 pages)

99 agrégats : inchangé 85, canonique S/D/I 14.

| vue | pipeline | métrique | v5 | v6 | Δ | notés/attendus | cause |
|---|---|---|---|---|---|---|---|
| texte | E0 · tesseract | cer | 0,086259 | 0,086259 | 0 | 5/5 | inchangé |
| texte | E0 · tesseract | wer | 0,309609 | 0,309609 | 0 | 5/5 | inchangé |
| texte | E0 · tesseract | cer_diplo | 0,077785 | 0,077785 | 0 | 5/5 | inchangé |
| texte | E0 · tesseract | **cmer** | 0,084847 | 0,084897 | +5,05e-05 | 5/5 | canonique S/D/I (ΣI 55→53, 2/5 doc.) |
| texte | E0 · tesseract | **mer** | 0,302083 | 0,302609 | +5,25e-04 | 5/5 | canonique S/D/I (ΣI 14→13, 1/5 doc.) |
| texte | E0 · tesseract | unanchored_trigrams | 0,161916 | 0,161916 | 0 | 5/5 | inchangé |
| texte | E1 · segmentation → tesseract | cer | 0,118341 | 0,118341 | 0 | 5/5 | inchangé |
| texte | E1 · segmentation → tesseract | wer | 0,377224 | 0,377224 | 0 | 5/5 | inchangé |
| texte | E1 · segmentation → tesseract | cer_diplo | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| texte | E1 · segmentation → tesseract | **cmer** | 0,113038 | 0,113104 | +6,54e-05 | 5/5 | canonique S/D/I (ΣI 155→153, 2/5 doc.) |
| texte | E1 · segmentation → tesseract | **mer** | 0,350413 | 0,350993 | +5,80e-04 | 5/5 | canonique S/D/I (ΣI 43→42, 1/5 doc.) |
| texte | E1 · segmentation → tesseract | unanchored_trigrams | 0,186381 | 0,186381 | 0 | 5/5 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | wer | 0,346975 | 0,346975 | 0 | 5/5 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **cmer** | 0,104944 | 0,105004 | +6,07e-05 | 5/5 | canonique S/D/I (ΣI 155→153, 2/5 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **mer** | 0,322314 | 0,322848 | +5,34e-04 | 5/5 | canonique S/D/I (ΣI 43→42, 1/5 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | unanchored_trigrams | 0,166422 | 0,166422 | 0 | 5/5 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,115920 | 0,115920 | 0 | 5/5 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | wer | 0,371886 | 0,371886 | 0 | 5/5 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer_diplo | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | **cmer** | 0,110726 | 0,110790 | +6,41e-05 | 5/5 | canonique S/D/I (ΣI 155→153, 2/5 doc.) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | **mer** | 0,345455 | 0,346026 | +5,72e-04 | 5/5 | canonique S/D/I (ΣI 43→42, 1/5 doc.) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | unanchored_trigrams | 0,181391 | 0,181391 | 0 | 5/5 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer | 0,023002 | 0,023002 | 0 | 5/5 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | wer | 0,124555 | 0,124555 | 0 | 5/5 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer_diplo | 0,023002 | 0,023002 | 0 | 5/5 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cmer | 0,022961 | 0,022961 | 0 | 5/5 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | mer | 0,123894 | 0,123894 | 0 | 5/5 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | unanchored_trigrams | 0,038862 | 0,038862 | 0 | 5/5 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | cer | 0,082627 | 0,082627 | 0 | 5/5 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | wer | 0,279359 | 0,279359 | 0 | 5/5 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | cer_diplo | 0,079600 | 0,079600 | 0 | 5/5 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | **cmer** | 0,081129 | 0,081178 | +4,82e-05 | 5/5 | canonique S/D/I (ΣI 61→59, 2/5 doc.) |
| texte | E2 · tesseract → qwen2.5:3b (local) | mer | 0,272569 | 0,272569 | 0 | 5/5 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | unanchored_trigrams | 0,135217 | 0,135217 | 0 | 5/5 | inchangé |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer | 0,047821 | 0,047821 | 0 | 5/5 | inchangé |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | wer | 0,154804 | 0,154804 | 0 | 5/5 | inchangé |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer_diplo | 0,047821 | 0,047821 | 0 | 5/5 | inchangé |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | **cmer** | 0,046649 | 0,046663 | +1,38e-05 | 5/5 | canonique S/D/I (ΣI 83→82, 1/5 doc.) |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | mer | 0,150519 | 0,150519 | 0 | 5/5 | inchangé |
| texte | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | unanchored_trigrams | 0,048744 | 0,048744 | 0 | 5/5 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | cer | 0,144068 | 0,144068 | 0 | 5/5 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | wer | 0,407473 | 0,407473 | 0 | 5/5 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | cer_diplo | 0,137712 | 0,137712 | 0 | 5/5 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | **cmer** | 0,134085 | 0,134160 | +7,56e-05 | 5/5 | canonique S/D/I (ΣI 246→244, 2/5 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | **mer** | 0,367576 | 0,368167 | +5,91e-04 | 5/5 | canonique S/D/I (ΣI 61→60, 1/5 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | unanchored_trigrams | 0,182104 | 0,182104 | 0 | 5/5 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | cer | 0,117433 | 0,117433 | 0 | 5/5 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | wer | 0,377224 | 0,377224 | 0 | 5/5 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | cer_diplo | 0,109564 | 0,109564 | 0 | 5/5 | inchangé |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | **cmer** | 0,112204 | 0,112269 | +6,49e-05 | 5/5 | canonique S/D/I (ΣI 154→152, 2/5 doc.) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | **mer** | 0,350413 | 0,350993 | +5,80e-04 | 5/5 | canonique S/D/I (ΣI 43→42, 1/5 doc.) |
| texte | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | unanchored_trigrams | 0,183608 | 0,183608 | 0 | 5/5 | inchangé |
| texte (lignes) | E0 · tesseract | cer | 0,086864 | 0,086864 | 0 | 5/5 | inchangé |
| texte (lignes) | E1 · segmentation → tesseract | cer | 0,118341 | 0,118341 | 0 | 5/5 | inchangé |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| texte (lignes) | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,115920 | 0,115920 | 0 | 5/5 | inchangé |
| texte (lignes) | E5 · qwen2.5vl:3b (local) | cer | 0,036320 | 0,036320 | 0 | 5/5 | inchangé |
| texte (lignes) | E2 · tesseract → qwen2.5:3b (local) | cer | 0,089588 | 0,089588 | 0 | 5/5 | inchangé |
| texte (lignes) | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer | 0,057506 | 0,057506 | 0 | 5/5 | inchangé |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | cer | 0,144673 | 0,144673 | 0 | 5/5 | inchangé |
| texte (lignes) | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | cer | 0,117433 | 0,117433 | 0 | 5/5 | inchangé |
| lecture | E0 · tesseract | cer | 0,086259 | 0,086259 | 0 | 5/5 | inchangé |
| lecture | E0 · tesseract | wer | 0,309609 | 0,309609 | 0 | 5/5 | inchangé |
| lecture | E0 · tesseract | cer_diplo | 0,077785 | 0,077785 | 0 | 5/5 | inchangé |
| lecture | E1 · segmentation → tesseract | cer | 0,118341 | 0,118341 | 0 | 5/5 | inchangé |
| lecture | E1 · segmentation → tesseract | wer | 0,377224 | 0,377224 | 0 | 5/5 | inchangé |
| lecture | E1 · segmentation → tesseract | cer_diplo | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,118341 | 0,118341 | 0 | 5/5 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | wer | 0,377224 | 0,377224 | 0 | 5/5 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,118341 | 0,118341 | 0 | 5/5 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | wer | 0,377224 | 0,377224 | 0 | 5/5 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer_diplo | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer | 0,023002 | 0,023002 | 0 | 5/5 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | wer | 0,124555 | 0,124555 | 0 | 5/5 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer_diplo | 0,023002 | 0,023002 | 0 | 5/5 | inchangé |
| lecture | E2 · tesseract → qwen2.5:3b (local) | cer | 0,086259 | 0,086259 | 0 | 5/5 | inchangé |
| lecture | E2 · tesseract → qwen2.5:3b (local) | wer | 0,309609 | 0,309609 | 0 | 5/5 | inchangé |
| lecture | E2 · tesseract → qwen2.5:3b (local) | cer_diplo | 0,077785 | 0,077785 | 0 | 5/5 | inchangé |
| lecture | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer | 0,047821 | 0,047821 | 0 | 5/5 | inchangé |
| lecture | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | wer | 0,154804 | 0,154804 | 0 | 5/5 | inchangé |
| lecture | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer_diplo | 0,047821 | 0,047821 | 0 | 5/5 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | cer | 0,118341 | 0,118341 | 0 | 5/5 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | wer | 0,377224 | 0,377224 | 0 | 5/5 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | cer_diplo | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | cer | 0,118341 | 0,118341 | 0 | 5/5 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | wer | 0,377224 | 0,377224 | 0 | 5/5 | inchangé |
| lecture | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | cer_diplo | 0,109867 | 0,109867 | 0 | 5/5 | inchangé |
| sans césure | E0 · tesseract | cer | 0,086439 | 0,086439 | 0 | 5/5 | inchangé |
| sans césure | E1 · segmentation → tesseract | cer | 0,118204 | 0,118204 | 0 | 5/5 | inchangé |
| sans césure | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,109957 | 0,109957 | 0 | 5/5 | inchangé |
| sans césure | E4 · segmentation → tesseract → saknussemm sélectif (règles, QE heuristique) | cer | 0,115761 | 0,115761 | 0 | 5/5 | inchangé |
| sans césure | E5 · qwen2.5vl:3b (local) | cer | 0,029627 | 0,029627 | 0 | 5/5 | inchangé |
| sans césure | E2 · tesseract → qwen2.5:3b (local) | cer | 0,086133 | 0,086133 | 0 | 5/5 | inchangé |
| sans césure | E1 · segmentation → qwen2.5vl:3b (VLM par région, local) | cer | 0,051008 | 0,051008 | 0 | 5/5 | inchangé |
| sans césure | E3 · segmentation → tesseract → saknussemm (qwen2.5:3b, local) | cer | 0,144777 | 0,144777 | 0 | 5/5 | inchangé |
| sans césure | E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b, QE dalembert, local) | cer | 0,117288 | 0,117288 | 0 | 5/5 | inchangé |

### S31L · Dresden (`dresden-local.yaml`, 50 unités)

55 agrégats : inchangé 49, canonique S/D/I 6.

| vue | pipeline | métrique | v5 | v6 | Δ | notés/attendus | cause |
|---|---|---|---|---|---|---|---|
| texte | E0 · tesseract | cer | 0,756345 | 0,756345 | 0 | 10/10 | inchangé |
| texte | E0 · tesseract | wer | 0,998704 | 0,998704 | 0 | 10/10 | inchangé |
| texte | E0 · tesseract | cer_diplo | 0,755669 | 0,755669 | 0 | 10/10 | inchangé |
| texte | E0 · tesseract | **cmer** | 0,752713 | 0,754742 | +2,03e-03 | 10/10 | canonique S/D/I (ΣI 50→22, 9/10 doc.) |
| texte | E0 · tesseract | mer | 0,994194 | 0,994194 | 0 | 10/10 | inchangé |
| texte | E0 · tesseract | unanchored_trigrams | 0,841243 | 0,841243 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | cer | 0,777478 | 0,777478 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | wer | 1,303953 | 1,303953 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | cer_diplo | 0,776609 | 0,776609 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | **cmer** | 0,749628 | 0,755603 | +5,98e-03 | 10/10 | canonique S/D/I (ΣI 385→300, 10/10 doc.) |
| texte | E1 · segmentation → tesseract | mer | 0,994563 | 0,994563 | 0 | 10/10 | inchangé |
| texte | E1 · segmentation → tesseract | unanchored_trigrams | 0,862971 | 0,862971 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,777767 | 0,777767 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | wer | 1,303953 | 1,303953 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,776609 | 0,776609 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | **cmer** | 0,749977 | 0,755885 | +5,91e-03 | 10/10 | canonique S/D/I (ΣI 384→300, 10/10 doc.) |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | mer | 0,994563 | 0,994563 | 0 | 10/10 | inchangé |
| texte | E3 · segmentation → tesseract → saknussemm (règles) | unanchored_trigrams | 0,863489 | 0,863489 | 0 | 10/10 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer | 2,202355 | 2,202355 | 0 | 10/10 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | wer | 3,606610 | 3,606610 | 0 | 10/10 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | cer_diplo | 2,194731 | 2,194731 | 0 | 10/10 | inchangé |
| texte | E5 · qwen2.5vl:3b (local) | **cmer** | 0,790763 | 0,792163 | +1,40e-03 | 10/10 | canonique S/D/I (ΣI 18499→18448, 7/10 doc.) |
| texte | E5 · qwen2.5vl:3b (local) | **mer** | 0,957502 | 0,957996 | +4,94e-04 | 10/10 | canonique S/D/I (ΣI 4269→4266, 2/10 doc.) |
| texte | E5 · qwen2.5vl:3b (local) | unanchored_trigrams | 0,520818 | 0,520818 | 0 | 10/10 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | cer | 0,759336 | 0,759336 | 0 | 10/10 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | wer | 0,997408 | 0,997408 | 0 | 10/10 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | cer_diplo | 0,758564 | 0,758564 | 0 | 10/10 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | **cmer** | 0,755400 | 0,757800 | +2,40e-03 | 10/10 | canonique S/D/I (ΣI 54→21, 9/10 doc.) |
| texte | E2 · tesseract → qwen2.5:3b (local) | mer | 0,995472 | 0,995472 | 0 | 10/10 | inchangé |
| texte | E2 · tesseract → qwen2.5:3b (local) | unanchored_trigrams | 0,841603 | 0,841603 | 0 | 10/10 | inchangé |
| texte (lignes) | E0 · tesseract | cer | 0,768310 | 0,768310 | 0 | 10/10 | inchangé |
| texte (lignes) | E1 · segmentation → tesseract | cer | 0,794944 | 0,794944 | 0 | 10/10 | inchangé |
| texte (lignes) | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,795330 | 0,795330 | 0 | 10/10 | inchangé |
| texte (lignes) | E5 · qwen2.5vl:3b (local) | cer | 2,215092 | 2,215092 | 0 | 10/10 | inchangé |
| texte (lignes) | E2 · tesseract → qwen2.5:3b (local) | cer | 0,771205 | 0,771205 | 0 | 10/10 | inchangé |
| lecture | E0 · tesseract | cer | 0,756345 | 0,756345 | 0 | 10/10 | inchangé |
| lecture | E0 · tesseract | wer | 0,998704 | 0,998704 | 0 | 10/10 | inchangé |
| lecture | E0 · tesseract | cer_diplo | 0,755669 | 0,755669 | 0 | 10/10 | inchangé |
| lecture | E1 · segmentation → tesseract | cer | 0,777478 | 0,777478 | 0 | 10/10 | inchangé |
| lecture | E1 · segmentation → tesseract | wer | 1,303953 | 1,303953 | 0 | 10/10 | inchangé |
| lecture | E1 · segmentation → tesseract | cer_diplo | 0,776609 | 0,776609 | 0 | 10/10 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,777478 | 0,777478 | 0 | 10/10 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | wer | 1,303953 | 1,303953 | 0 | 10/10 | inchangé |
| lecture | E3 · segmentation → tesseract → saknussemm (règles) | cer_diplo | 0,776609 | 0,776609 | 0 | 10/10 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer | 2,202355 | 2,202355 | 0 | 10/10 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | wer | 3,606610 | 3,606610 | 0 | 10/10 | inchangé |
| lecture | E5 · qwen2.5vl:3b (local) | cer_diplo | 2,194731 | 2,194731 | 0 | 10/10 | inchangé |
| lecture | E2 · tesseract → qwen2.5:3b (local) | cer | 0,756345 | 0,756345 | 0 | 10/10 | inchangé |
| lecture | E2 · tesseract → qwen2.5:3b (local) | wer | 0,998704 | 0,998704 | 0 | 10/10 | inchangé |
| lecture | E2 · tesseract → qwen2.5:3b (local) | cer_diplo | 0,755669 | 0,755669 | 0 | 10/10 | inchangé |
| sans césure | E0 · tesseract | cer | 0,768073 | 0,768073 | 0 | 10/10 | inchangé |
| sans césure | E1 · segmentation → tesseract | cer | 0,794711 | 0,794711 | 0 | 10/10 | inchangé |
| sans césure | E3 · segmentation → tesseract → saknussemm (règles) | cer | 0,795097 | 0,795097 | 0 | 10/10 | inchangé |
| sans césure | E5 · qwen2.5vl:3b (local) | cer | 2,215616 | 2,215616 | 0 | 10/10 | inchangé |
| sans césure | E2 · tesseract → qwen2.5:3b (local) | cer | 0,770389 | 0,770389 | 0 | 10/10 | inchangé |

<!-- comptes : par agrégat de RunResult {'=': 1559, 'C': 255, 'R': 12} ; par ligne de tableau {'=': 541, 'C': 93, 'R': 4} -->

## 6. Changements non prévus par le contrat (catégorie « autre »)

**Un seul motif, 12 agrégats** : CER micro de `E5 · qwen2.5vl:3b (local)` sur
Dresden, vues `texte (lignes)` et `sans césure`, **+1 ULP** (+2,22e-16), dans S30
et dans les cinq répétitions S31 (mêmes unités E5 locales, recopiées de S30).
Rien d'autre n'est inexpliqué (0 « ? »).

**Document isolé** : `Mscr.Dresd.K80_177` (E5 local, sortie bouclée jusqu'au
plafond de 2 048 jetons, `validity = truncated_output`), vue `texte (lignes)` :
CER page = 6 265 / 1 229 = 5,097640358014646.

| page | CER v5 = v6 | poids v5 | v5 : v·w en flottant | v6 : E (entier) | N |
|---|---|---|---|---|---|
| K80_177 | 5,097640358014646 | 1 229 | **6 264,999999999999** | **6 265** | 1 229 |
| K80_179 | 0,7260416666666667 | 960 | 697,0 | 697 | 960 |
| K80_180 | 0,4129821260583255 | 1 063 | 439,0 | 439 | 1 063 |
| K80_182 | 0,5784313725490197 | 1 020 | 590,0 | 590 | 1 020 |
| **corpus** | | | Σ = 7 990,999999999999 → **1,8705524344569286** | 7 991 / 4 272 → **1,8705524344569289** | 4 272 |

Valeur exacte : 7 991 / 4 272 = 1,87055243445692883895… ; v6 est le flottant le
plus proche (écart 3,1e-17), v5 en est à 1,9e-16 (le voisin d'en dessous). v5
reconstituait les erreurs de la page par `valeur × poids` en flottant
(`micro_ratio`), qui perd l'entier 6 265 dès que le CER de la page n'est pas
exact en binaire ; v6 somme les entiers puis convertit **une** fois
(`int / int`, correctement arrondi). `sans césure` : même page, 7 992 / 4 270,
même mécanisme. Les autres CER sont restés au bit près par chance de
l'arrondi (aucun autre agrégat ne bouge, 12/12 contrôlés : v5 reproduit par
Σ(v·w)/Σw, v6 = ΣE/ΣN au plus proche). Même cause, en mode détaillé, dans
`economics` (§ 8) : `estimated_errors` 7 991,999999999999 → 7 992,0,
`errors_avoided` −33,99999999999909 → −34,0.

**Verdict : correction voulue, pas une régression.** C'est la conséquence
directe du principe de 1a (« une seule conversion flottante », R1), mais D-313
n'annonçait un effet au dernier ULP que pour ECE/MCE, et « CER micro
inchangé » : la prévision est vraie à toute précision affichée, fausse au bit
près sur ces 12 agrégats. À noter dans D-313 au remplacement des JSON commités
(le JSON Dresden v6 n'est pas identique au v5 sur ces deux CER).

## 7. Inférences

**Familles à dénominateur d'hypothèse (B9c) : MER et cMER** (les seules des vues
de ces campagnes ; `ins_rate`/`del_rate`, MER ligne, etc. ne sont pas déclarés).

| | v5 | v6 |
|---|---|---|
| `InferencePayload.micro_estimable` | absent | `false` pour `texte:mer`, `texte:cmer` (30 analyses sur 15 runs) ; `true` pour les 90 autres (CER, WER) |
| IC du micro, **runs publiés** (mode standard) | aucun (IC = mode détaillé seulement) | aucun ; le rapport ajoute « Intervalle du micro : inférence non estimable (dénominateur dépendant de la sortie ; aucune procédure validée) » sous les rangs de `texte · mer` et `texte · cmer` |
| IC du micro, **mode détaillé** (variante `--analyses toutes`, `detaille/`) | 64 IC MER/cMER : S30 BNL 2 × 5, S31 BNL rép. 1 2 × 15, S31L `bnl-local` 2 × 7, S31L `dresden-local` 2 × 5 | **0** : les 64 passent à « inférence non estimable » |
| Friedman (rangs par document) MER/cMER | p calculé | **toujours calculé** (tranche I) ; change là où des valeurs par document changent (canonique) |

Friedman MER/cMER changés (aucune bascule de significativité, aucun groupe de
distance critique modifié, ordre des rangs moyens identique) :

| run | vue · métrique | p v5 | p v6 | p Holm v5 → v6 | rang moyen, écart max |
|---|---|---|---|---|---|
| S31 BNL rép. 2 | texte · cmer | 1,269e-07 | 1,149e-07 | 6,34e-07 → 5,75e-07 | 0,027 |
| S31 BNL rép. 5 | texte · cmer | 1,037e-08 | 1,001e-08 | 5,19e-08 → 5,00e-08 | 0,014 |
| S31L `bnl-local` | texte · cmer | 0,005084 | 0,004473 | 0,0254 → 0,0249 | 0,014 |
| S31L `dresden-local` | texte · cmer | 0,7034 | 0,7281 | 1,0 → 1,0 | 0,05 |

(`cross_engine` porte les mêmes p : `texte:cmer:significance_p`, mêmes 4 cas.)
Dresden S30/S31 et S31L saknussemm : aucun IC ni Friedman en v5 comme en v6
(« 4 cas complets, il en faut au moins 6 » ; 5 pages pour le sous-ensemble).

**CER (et WER)** : `micro_estimable = true` ; en mode détaillé les **192 IC**
CER/WER (6 analyses × 5, 15, 7, 5 pipelines) sont **identiques au bit près**
(bornes, point, `n_documents`) — aucune page à référence vide, donc le même
ensemble rééchantillonné qu'en v5 ; p de Friedman CER/WER inchangés partout.

## 8. Annexe — mode détaillé (variante, non publiée)

Les campagnes ont tourné en mode standard ; pour voir les analyses que 1a
touche, chaque run S30, S31 rép. 1 et S31L a été re-noté **aussi** avec
`--analyses toutes`, en v5 et en v6 (`detaille/*.v{5,6}.json`, 14 fichiers).
Champs changés, sommés sur les 7 runs :

| analyse · champ | changements | cause | prévu ? |
|---|---|---|---|
| `calibration` `ece` / `mce` | 15 / 8 | ECE exacte (Σ en `Fraction`, une conversion) : ≤ 4 ULP | oui (« ECE/MCE au dernier ULP ») |
| `calibration` `bins[].mean_confidence` | 80 | même cause, ≤ 1 ULP (0,013250000000000001 → 0,01325) | oui (même famille) |
| `calibration` `bins[].correct`, `confidence_sum` | 330 + 330 | champs nouveaux (statistique de bin) | oui |
| `hipe` `cmer_micro`/`cmer_macro`/`wmer_*` | 57 / 57 / 34 / 34 | canonique S/D/I (mêmes comptes que `cmer`) | oui |
| `correction` `char_ins_ratio`, `change_ratio`, `pcis_*`, `ccr`, `worst_regressions` | 116, 104, 104 + 26, 56, 20 (+ contenu) | canonique S/D/I (`char_mer` partagé) | oui (« partagés par `cmer` et l'analyse de correction ») |
| `correction` `improvement_rate`/`regression_rate`/`no_change_rate`/`pref_score` | 19 / 20 / 15 / 27 (Dresden seulement) | canonique S/D/I : des pages « régressées » ou « améliorées » par simple départage d'ex æquo deviennent « sans changement » | oui dans sa cause ; **l'effet sur les taux n'est pas chiffré par D-313** |
| `economics` `cer`, `estimated_errors`, `errors_avoided`, `pages_per_hour_effective` | 4 × 4 (Dresden E5 local) | arrondi unique (§ 6) | **non** (même motif que § 6) |
| `inference` `intervals` (MER/cMER), `micro_estimable`, p/rangs cMER | 8 + 56 + 18 | B9c ; canonique (§ 7) | oui |

Exemple isolé de l'effet sur la correction (prévu, mais le plus visible) :
S31L Dresden, `E3 · segmentation → tesseract → saknussemm (règles)`,
`Mscr.Dresd.K80_177`, vue `texte` — les règles ne changent qu'un caractère
(`Criſi` → `Crisi`), à distance de Levenshtein égale (937 avant et après). v5
(départage rapidfuzz) : I = 17 avant, 16 après → cMER 0,752006 → 0,752610,
« **régression** » ; v6 (canonique, I = 11 des deux côtés, contrôlé par la DP
indépendante) : 0,755645 = 0,755645, « sans changement ». Taux de régression
d'E3 règles, vue `texte` : **0,4 → 0,3** ; « sans changement » 0,6 → 0,7.
**Correction voulue** : v5 comptait comme régression un artefact du départage.

## 9. Fichiers

Tout sous `/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/avant-apres/` :

| chemin | contenu |
|---|---|
| `v6/*.json` (15) | **`RunResult` v6** re-notés hors ligne : `s30-{bnl,dresden}`, `s31-{bnl,dresden}-{1..5}`, `s31l-{bnl-local,bnl-local-saknussemm,dresden-local}` ; aucun chemin local |
| `v5/*.json` (15) | les `RunResult` v5 comparés (copies des fichiers commités/gelés) |
| `v5-renote/*.json` (15) | re-notation v5 par le code d'origine — identique à `v5/` (preuve de reproductibilité) |
| `variante/s30-{bnl,dresden}-exactitudes.v{5,6}.json` | variante B1 (`char_accuracy`, `word_accuracy` ajoutées à `texte`) |
| `detaille/*.v{5,6}.json` (14) | mode détaillé (`--analyses toutes`), § 7-8 |
| `avant-apres.csv` | les 1 826 agrégats, valeurs pleine précision, statistique v6, cause |
| `scripts/compare.py`, `tables.py`, `detail_diff.py`, `dp_check.py`, `rows.json` | comparaison, contrôles par document, tableaux, DP indépendante |
| `work/{s30,s31,s31l}/{bnl,dresden}/` | corpus copiés + specs (copies des branches ; `*-exactitudes.yaml` = variante) |
| `logs/` | journaux des runs, rapports HTML v6/v5, empreintes des archives avant/après |

Worktrees jetables (détachés, aucune branche) : `…/scratchpad/renotation-v6`
(`abee7b5` + `aba0fe7` + `50cad9f` non commités) et `…/scratchpad/renotation-v6-pur`
(`abee7b5`) ; venvs `…/scratchpad/renotation-venv`, `renotation-venv-pur`
(installés sans réseau : `site-packages` du venv S31, `setuptools_scm` du cache
local, `pip install --no-index --no-deps -e`). À retirer par
`git worktree remove` quand la revue est close.
