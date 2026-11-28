# Réévaluations v6 de la campagne de référence (S30) — provenance

Ces deux fichiers sont les **réévaluations v6** des deux `RunResult` v5 de S30
conservés **tels quels** dans le dossier parent (`bnl-sans-cle.run_result.json`,
`dresden-sans-cle.run_result.json` : v5, jamais modifiés ; ce sont eux que lit
`tests/guardrails/test_readme_result.py`). Ils vivent ici, à part, pour que
l'avant et l'après restent comparables : un fichier v5 n'est jamais remplacé par
sa réévaluation (`CONTRATS.md` § 2.3 d : une réévaluation sous nouvelle
définition garde sa filiation, jamais l'identité d'origine).

| fichier | version | code | archive relue | unités |
|---|---|---|---|---|
| `bnl-sans-cle.run_result.json` | `RunResult` v6 | `abee7b5` (tranche 1a, D-313) **sans** correctif | archive S30 `archive-bnl` | 185/185 |
| `dresden-sans-cle.run_result.json` | `RunResult` v6 | `abee7b5` **sans** correctif | archive S30 `archive-dresden` | 40/40 (6 « arrêtée (délai) », 1 tronquée) |

## Comment

`cinoc run {bnl,dresden}-sans-cle.yaml --offline --resume-dir <archive S30>` avec
le code de `abee7b5` seul — aucun moteur appelé, aucun appel réseau (mandataire
forcé sur `127.0.0.1:9`, `HF_HUB_OFFLINE=1`), les archives intactes après
relecture. Les fichiers ne contiennent **aucun chemin local** (vérifié : aucune
occurrence de `/tmp`, `/home`, `/root` ni d'un nom de dossier de travail ; le
dossier d'archive y est relatif, `archive-bnl`, `archive-dresden`).

## Ce qui change entre le v5 et ce v6

Sur les 15 `RunResult` de S30, S31 et S31L re-notés (1 826 agrégats) : 1 559
inchangés au bit près ; 255 changés par l'alignement **canonique** S/D/I (MER,
cMER) ; **12 CER de Dresden E5 de +1 ULP** (vues `texte (lignes)` et `sans
césure`, S30 et les cinq répétitions S31) — la page 177, sortie bouclée à
CER 5,0976, valait `valeur × poids` = 6 264,999… en v5 et 6 265 en v6 : le v5
reconstituait les erreurs d'une page par un produit en flottant, le v6 somme des
entiers et convertit une fois (correction voulue, D-313) ; 0 inexpliqué. Le
support « notés / attendus » est identique sur les 1 826 agrégats.

## Ce que ce v6 n'est pas

C'est un v6 de la **tranche 1a** (`abee7b5`), antérieur à la tranche 1b : il ne
porte ni `conditional_aggregate`/`operational_aggregate`, ni couverture, ni
macro, ni supports. Il se relit avec le code actuel (les champs de 1b sont
facultatifs) et ses valeurs sont celles de 1a — notamment, la page tronquée de
Dresden E5 y est **encore notée** (support 4/10), là où la tranche 1b la sort de
l'agrégat conditionnel (3/10 + 1 tronquée, 10/10 en qualité opérationnelle). Une
réévaluation 1b se refait depuis l'archive S30 (hors de l'arbre) avec la même
commande.

## S31 et S31L (non copiées ici)

Les réévaluations v6 des campagnes S31 (Mistral, 5 répétitions BNL et Dresden)
et S31L (local) **exigent les deux correctifs gelés** `aba0fe7` et `50cad9f`
(`FANOUT_VERSION = "2"`, réglage `timeout` hors empreinte) : sans eux, la
relecture hors ligne de leurs archives échoue (« unité(s) absente(s) »).
Elles restent sur la branche d'archives `claude/campagnes-archives-2026-11`,
dossier `avant-apres-1a/` (v5, v6, détail par métrique, journaux), et ne sont
pas recopiées dans l'arbre. S30 se relit sur `abee7b5` seul : c'est ce qui les
distingue.
