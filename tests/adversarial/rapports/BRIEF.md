# Contre-expertise de Cinoc au commit 04a1c17b — consignes communes

Le mainteneur ne tient plus la CI verte, la livraison des phases P5d-P5g ni le nombre de tests pour des preuves de maturité scientifique. Il demande si **les contrats fondamentaux** de Cinoc conviennent à un véritable instrument scientifique.

## Environnement (obligatoire)
- Copie figée du code : `/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/contre-expertise` (worktree détaché à `04a1c17b`). C'est **le seul** code examiné.
- Python isolé : `/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/ce-venv/bin/python` (installation éditable de la copie figée, extras dev/serve/images/saknussemm). Lance pytest **depuis la racine de la copie figée** avec ce Python : `cd <copie> && <python> -m pytest -q -p no:cacheprovider tests/adversarial/<ton_domaine>`. N'utilise pas `-n` (la machine est partagée avec des campagnes qui tournent) ; ne lance pas toute la suite.
- Vérifie une fois `<python> -c "import cinoc.evaluation as e; print(e.__file__)"` : le chemin doit être dans la copie figée.
- Le dépôt de travail `/home/user/cinoc` est **hors limites** (d'autres agents y travaillent) : n'y lis rien de neuf, n'y écris rien.

## Ce que tu as le droit d'écrire
- Uniquement des fichiers de test sous `tests/adversarial/<ton_domaine>/` dans la copie figée (avec un `__init__.py` si besoin), et ton rapport `/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/ce-findings/<ton_domaine>.md`.
- **Aucune modification du produit** (`cinoc/`), des tests existants, de la config, de la doc. Aucune commande git. Aucun réseau public, aucune clé, aucun appel facturé.

## Méthode
1. Lis `CLAUDE.md` (copie figée) en entier, puis le code et la doc de couche concernés (`ANALYSE_COUCHE_*`, `MIGRATION_COUCHE_*`, `DECISION_*` pertinents). Lis les tests existants du domaine pour savoir ce qu'ils couvrent déjà.
2. Pour **chaque affirmation** du mainteneur dans ton domaine : écris un test adversarial qui affirme le **comportement scientifiquement attendu**, sur un contre-exemple minimal et reproductible construit par les API publiques du produit (pas de monkeypatch du code testé, sauf pour simuler une panne externe — un adaptateur qui échoue, un fichier corrompu).
   - Test **rouge** ⇒ défaut **confirmé**. Test **vert** ⇒ affirmation **réfutée** (ou déjà traitée) : garde le test vert, c'est une preuve aussi.
   - **Cherche autant à réfuter qu'à confirmer.** Une affirmation du mainteneur peut être fausse ou ne valoir que dans un cas étroit : dis-le, preuve à l'appui. Ne gonfle rien.
   - Quand c'est possible, compare à une **référence indépendante** (calcul à la main dans le test, `scipy`, `numpy`, un oracle déjà installé) plutôt qu'à une autre fonction de Cinoc.
   - Nomme chaque test `test_<affirmation>__<attendu>` et donne-lui une docstring d'une phrase : le contre-exemple et ce qui est attendu.
3. Ne corrige rien. Si un correctif te semble évident, décris-le, ne l'écris pas.

## Rapport (`ce-findings/<ton_domaine>.md`), scannable, en français
Pour chaque problème :
| champ | contenu |
|---|---|
| Affirmation | ce que le mainteneur soutient |
| Verdict | **confirmé** / **réfuté** / **partiel** / **non testable ici** (et pourquoi) |
| Contre-exemple | les données minimales, et le nom du test (`fichier::test`) |
| Comportement actuel | chiffres ou sortie observés |
| Comportement attendu | et sa justification (définition, référence) |
| Tests existants | lesquels couvrent le point, et pourquoi ils ne l'ont pas vu |
| Cause architecturale | le contrat ou le type en cause (`fichier:ligne`), pas le symptôme ; dire si plusieurs symptômes ont la même cause |
| Gravité scientifique | un chiffre publié peut-il être faux, et de combien, sur quel cas réaliste ? |

Termine par : la sortie exacte de `pytest` sur ton dossier (comptes rouge/vert), et une section « Contrats en cause » qui dit, pour ton domaine, si le contrat fondamental est **adapté**, **réparable localement** ou **à revoir**, en une phrase argumentée chacun.
