# Réévaluations v7 de la campagne de référence (S30) — provenance

Ces deux fichiers sont les **réévaluations v7** des deux `RunResult` de S30. Ils
vivent ici, à part : les `RunResult` **v5** d'origine (dossier parent, jamais
modifiés ; ce sont eux que lit `tests/guardrails/test_readme_result.py`) et leurs
réévaluations **v6** de la tranche 1a (`../v6/`, avec [leur provenance](../v6/PROVENANCE.md))
restent des artefacts distincts. Une réévaluation sous nouvelle définition garde
sa filiation et ne remplace jamais l'identité d'origine (`CONTRATS.md` § 2.3 d).

| fichier | version | code | archive relue | unités |
|---|---|---|---|---|
| `bnl-sans-cle.run_result.json` | `RunResult` v7 | commit `730fabf` (branche `claude/refonte-contrats`, code final de la seconde revue de 1a + 1b) | archive S30 `archive-bnl` | 185/185 |
| `dresden-sans-cle.run_result.json` | `RunResult` v7 | idem | archive S30 `archive-dresden` | 40/40 (6 « arrêtée (délai) », 1 tronquée) |

## Comment

`cinoc run {bnl,dresden}-sans-cle.yaml --offline --resume-dir <archive S30>`,
depuis le dossier du corpus importé (les specs ne tournent qu'à côté de leur
corpus, `../README.md`) : aucun moteur appelé, aucun appel réseau (mandataire
forcé sur `127.0.0.1:9`, `HF_HUB_OFFLINE=1`). Les archives ont été vérifiées
**intactes après relecture** (somme SHA-256 de tous leurs fichiers, avant et
après : arbre `archive-bnl` `9bf28e7d…`, `archive-dresden` `863419df…`, avant et
après ; les tarballs `s30-archive-{bnl,dresden}.tar.zst` ont pour SHA-256
`7ea845e8…` et `6881fe3c…`, inchangés). Les tarballs livrent `images/` **vide** :
les images, adressées par leur SHA-256, sont rétablies depuis les corpus
(`archives-branch/images/{bnl,dresden}`) avant la relecture, comme pour la
première production de ces fichiers. Les fichiers ne contiennent **aucun chemin local** (aucune occurrence de
`/tmp`, `/home`, `/root` ni d'un nom de dossier de travail ; le dossier d'archive
y est relatif). Le champ `manifest.code_version` vaut `0.1.1.dev297+g730fabf36` :
le commit `730fabf`, arbre propre, qui produit ces fichiers.

**Environnement.** Un venv jetable (Python 3.13, `pip install -e ".[saknussemm]"`)
**sans** les paquets d'oracle (`jiwer`, `dinglehopper`, `roman`, `multimethod` et
leurs dépendances) : `dependencies_lock` ne porte que `cinoc`, `httpcore`, `httpx`,
`lxml`, `numpy`, `pydantic`, `pyyaml`, `rapidfuzz`, `saknussemm` et `scipy`. Il ne
porte plus `fastapi`, `jinja2`, `pillow`, `python-multipart` ni `uvicorn`, que la
première production avait (venv de développement, extra web installé) : la
relecture ne les utilise pas.

## Régénération du 28/11 (code final de la seconde revue)

Les deux fichiers ont été régénérés par `730fabf`. Par rapport au v7 précédent
(`0.1.1.dev271+g04a1c17b1`), **aucune valeur ne bouge** : agrégats, observations,
supports, macros, issues d'unité, analyses et `step_issues` sont identiques à
l'octet près. Seul le manifeste change : `code_version`, `dependencies_lock`
(`cinoc`, et les cinq paquets web ci-dessus), `started_at` et `completed_at`.
C'est attendu : les correctifs de la seconde revue (`stat_partielle` d'une sortie
illisible, clé de grappe singleton, `not_declared`, `n_pairs` et `n_substitutions`
obligatoires, textes et légendes du rapport) agissent sur des cas que ces deux
campagnes n'exercent pas — aucune sortie illisible, aucune grappe déclarée, mode
rapide sans les analyses `diagnostics` ni `decisions`. Le rapport, lui, change
(titres, légendes, texte des tests) : il se re-rend depuis ces JSON.

## Ce que le v7 change par rapport au v6 de la tranche 1a

Le v6 de `../v6/` est un `RunResult` de **1a** : ni agrégat conditionnel ou
opérationnel, ni couverture, ni macro, ni supports. Le v7 porte ceux de **1b**
et les correctifs de la revue indépendante (`CONTRATS.md` § 2.1 f, « Précisions
tranchées le 28/11 après la validation finale de 1a + 1b ») : `conditional_aggregate`
et `operational_aggregate` (l'agrégat principal n'est plus stocké), `stat_vide`,
`cluster`, `step_issues` en ensemble trié, `status` exploratoire de
`significance_p`.

Sur les **99 agrégats** (55 BNL, 44 Dresden), comparés à ceux du v6 :

- **BNL : 55 sur 55 identiques**, dans les deux qualités — les 185 unités sont
  relues `ok` (le cache de format 3 ne dit rien de leur complétude, voir la
  section suivante : celles de E3 et E4 sont en réalité partielles) ; lues ainsi,
  la qualité conditionnelle égale l'opérationnelle.
- **Dresden : 33 sur 44 identiques** dans la qualité conditionnelle, **34** dans
  l'opérationnelle ; ceux qui bougent (11 et 10) sont tous du pipeline **E5
  qwen2.5vl:3b (local)**, dont 6 pages sont « arrêtées (délai) » et 1 est tronquée
  (la page 177, sortie bouclée jusqu'à 2 048 jetons) :
  - le v6 (1a) notait la page tronquée et excluait les six arrêtées : CER
    `texte` **1,8614**, support 4/10 ;
  - le v7 **conditionnel** exclut aussi la page tronquée (R6) : CER `texte`
    **0,5613**, support **3/10**, couverture `step_cancelled` 6 et
    `truncated_output` 1 ;
  - le v7 **opérationnel** note les six arrêtées comme des pages vides et la
    tronquée telle que produite : CER `texte` **1,3551**, support 10/10 ; les
    autres métriques et vues d'E5 (`wer`, `cer_diplo`, `cmer`, `mer`,
    `unanchored_trigrams`, `texte (lignes)`, `lecture`, `sans césure`) bougent
    de même.
- La couverture (`expected`, `coverage`) est la même dans les deux qualités.
- Aucun pipeline de ces deux campagnes n'est hors vue : les 36 entrées
  (20 + 16) sont celles du v6.

Le macro, par document (aucune grappe n'est déclarée) et exact (moyenne en
`Fraction`, une conversion flottante), est publié avec chaque agrégat qui en a un.

## Replis déclarés par les sidecars : E3 et E4 non conformes au § 2.1 f

Les sidecars de décision de ces deux archives (`*.decisions.json`, un par unité
de correction, au statut et au `reason_code` de l'époque, **sans** `line_class`
ni `class_code`) déclarent des **replis** : toutes les lignes en repli portent le
code `all_attempts_exhausted` (aucun `chunk_error_absorbed`). Mesuré par un
script de lecture seule sur les sidecars des archives `archive-dresden` et
`archive-bnl` (aucun appel, archives non modifiées) :

| campagne | pipeline | lignes en repli / lignes | unités avec au moins un repli / unités | dont unités entièrement en repli |
|---|---|---|---|---|
| Dresden | E3 | 129/132 | 10/10 | 7 |
| BNL | E3 et E4 (confondus¹) | 110/218 | 39/74 | 34 |

¹ Les sidecars sont rangés par clé de cache, sans le nom du pipeline : E3 et E4
partagent les 74 unités (37 pages chacun), et le décompte ne les sépare pas.

Selon le § 2.1 f, une unité qui a un repli est **partielle** (seul le repli rend
une étape partielle) : la qualité conditionnelle exclut ces unités. Or ces
archives ont été écrites au format de cache 3, qui **ne porte pas l'état de
l'étape** : leur relecture les rend `ok`, et la qualité **conditionnelle v7 de E3
et E4** (BNL et Dresden) compte donc des observations que le § 2.1 f exclut.
Elle est **non conforme au § 2.1 f** et **ne doit pas être citée**, pas plus que
la couverture et le support qui l'accompagnent. Sur ces mêmes lignes, l'analyse
des décisions n'a aucune classe à lire : le rapport écrit « classes non déclarées
par l'archive » (N3), jamais un zéro.

**Arbitrage posé au mainteneur (tranche 3).** Comment relire une archive dont le
cache ne porte pas l'état de l'étape : (a) l'adaptateur re-déclare l'état depuis
le rapport archivé de la bibliothèque ; (b) l'archive est relue avec l'étiquette
« complétude non enregistrée » ; (c) elle est refusée. Aucun choix n'est fait
ici : tant qu'il n'est pas rendu, les v7 de E3 et E4 ne sont pas citables.

## Limite reportée en tranche 3

Une archive au format de cache 3 **ne dit rien des issues partielles** : elle a
été écrite avant que l'état partiel d'une unité (`partial`) et l'ensemble des
issues de chaque étape existent. La relecture ne peut que constater l'absence
d'issue déclarée — elle ne la prouve pas, et la section précédente montre qu'elle
la masque pour E3 et E4. L'étiquetage d'une archive de format 3 et sa relecture
sémantique (chaque scalaire égal à la finalisation de sa statistique, chaque
agrégat à la combinaison des observations conservées, sinon refus) relèvent de
la **tranche 3** (archive et validation sémantique), pas de ce commit. Une entrée
de cache dont `step_issues` est à l'ancienne forme (une chaîne par étape, écrite
par la tranche 1b) n'est plus relue : l'unité est rejouée.

## S31 et S31L (non copiées ici)

Comme pour le v6, les réévaluations des campagnes S31 (Mistral, 5 répétitions
BNL et Dresden) et S31L (local) exigent les deux correctifs gelés `aba0fe7` et
`50cad9f` (`FANOUT_VERSION = "2"`, réglage `timeout` hors empreinte) : sans eux,
la relecture hors ligne de leurs archives échoue (« unité(s) absente(s) »). Elles
restent sur la branche d'archives `claude/campagnes-archives-2026-11` et ne sont
pas recopiées dans l'arbre ; leur réévaluation v7 n'a pas été faite ici. S30 se
relit sur le code de la branche seul : c'est ce qui la distingue.
