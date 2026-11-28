# Réévaluations v7 de la campagne de référence (S30) — provenance

Ces deux fichiers sont les **réévaluations v7** des deux `RunResult` de S30. Ils
vivent ici, à part : les `RunResult` **v5** d'origine (dossier parent, jamais
modifiés ; ce sont eux que lit `tests/guardrails/test_readme_result.py`) et leurs
réévaluations **v6** de la tranche 1a (`../v6/`, avec [leur provenance](../v6/PROVENANCE.md))
restent des artefacts distincts. Une réévaluation sous nouvelle définition garde
sa filiation et ne remplace jamais l'identité d'origine (`CONTRATS.md` § 2.3 d).

| fichier | version | code | archive relue | unités |
|---|---|---|---|---|
| `bnl-sans-cle.run_result.json` | `RunResult` v7 | branche `claude/refonte-contrats`, correctifs de la revue de 1a + 1b (base `ec5c996`) | archive S30 `archive-bnl` | 185/185 |
| `dresden-sans-cle.run_result.json` | `RunResult` v7 | idem | archive S30 `archive-dresden` | 40/40 (6 « arrêtée (délai) », 1 tronquée) |

## Comment

`cinoc run {bnl,dresden}-sans-cle.yaml --offline --resume-dir <archive S30>`,
depuis le dossier du corpus importé (les specs ne tournent qu'à côté de leur
corpus, `../README.md`) : aucun moteur appelé, aucun appel réseau (mandataire
forcé sur `127.0.0.1:9`, `HF_HUB_OFFLINE=1`). Les archives ont été vérifiées
**intactes après relecture** (somme SHA-256 de tous leurs fichiers, avant et
après). Les fichiers ne contiennent **aucun chemin local** (aucune occurrence de
`/tmp`, `/home`, `/root` ni d'un nom de dossier de travail ; le dossier d'archive
y est relatif). Le champ `manifest.code_version` reprend la version installée de
l'environnement de relecture, non le commit : le code est celui de la branche
`claude/refonte-contrats` à la livraison des correctifs de la revue.

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
  `ok`, aucune n'est incomplète : la qualité conditionnelle égale l'opérationnelle.
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

## Limite reportée en tranche 3

Une archive au format de cache 3 **ne dit rien des issues partielles** : elle a
été écrite avant que l'état partiel d'une unité (`partial`) et l'ensemble des
issues de chaque étape existent. Ces deux archives ne portent aucune unité
partielle (BNL : 185 `ok` ; Dresden : 33 `ok`, 6 en échec, 1 tronquée), mais
leur relecture ne le **prouve** pas : elle ne peut que constater l'absence
d'issue déclarée. L'étiquetage d'une archive de format 3 et sa relecture
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
