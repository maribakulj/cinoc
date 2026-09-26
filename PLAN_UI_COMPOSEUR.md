# PLAN_UI_COMPOSEUR.md — Le composeur de pipelines : recettes, réglages, composition contrainte

> **Document de conception**, pas de statut. Il dit *ce qu'on construit et
> pourquoi*, pour la phase **P5c** de [`PLAN_FIN_MIGRATION.md`](PLAN_FIN_MIGRATION.md).
> L'autorité de statut reste le roll-up de [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md).
>
> Il naît d'une question de l'utilisateur — « pourquoi le composeur de graphe
> est nul ? on ne peut pas créer des recettes modulaires avec des contraintes
> qui fonctionneraient comme un composeur de graphe ? » — et de l'audit qu'elle
> a déclenché (D-257).

---

## 1. Le constat qui reformule le problème

P5c est née d'un symptôme : trois routes déclarées, zéro appel depuis la page.
En cartographiant la page pour dessiner le remède, on trouve la cause, et elle
est plus profonde qu'un bouton manquant.

**Il y a deux constructeurs de pipeline, et ils ne se connaissent pas.**

| | `app/run_planning.py` | `app/recipes.py` |
|---|---|---|
| Taille | **757 lignes** — budget déclaré **760** | 471 lignes |
| Méthode | assemble les `PipelineStep` **à la main**, mode par mode | les **déduit** d'une table de rôles typés |
| Atteint par | la page web, et elle seule (`plan_benchmark_run` n'a qu'un appelant) | la CLI ; et trois routes que la page n'appelle pas |
| Importe l'autre ? | non | non |

`run_planning.py` est à **trois lignes de son plafond**. Chaque champ que
l'utilisateur réclame — `dpi`, `psm`, `timeout` — aggrave un fichier saturé,
pendant qu'à côté un mécanisme typé rend le même service pour zéro ligne de
plus. C'est la **liste parallèle** que le projet combat partout ailleurs
(`CLAUDE.md` §5.1, « rupture nette, zéro shim » ; §8.4, clause anti-doublon).

La question de P5c n'est donc pas « où mettre le bouton recettes », mais
**lequel des deux constructeurs survit**. Ce document répond : le typé.

### Correction d'une affirmation de P5c

La première rédaction de P5c portait un item 5 « les recettes manquantes »,
justifié par : « manquent au moins la chaîne segmentation → reconnaissance par
région → projection, et une forme avec préprocessing ». **C'est faux**, et
l'erreur vient de n'avoir pas lu leur contenu. `presse_ancienne.yaml` porte
exactement cette chaîne, préprocessing et paramètres compris :

```yaml
steps:
  - {id: prep,  role: preprocess,    params: {operations: deskew,binarize}}
  - {id: seg,   role: segmenter}
  - {id: reco,  role: region_recognizer}
  - {id: ordre, role: reading_order, params: {strategy: columns}}
  - {id: texte, role: projection}
```

`alto_corrige` se sert de `after`, `vote_trois_moteurs` de `merge` : le
mécanisme décrit déjà un **graphe**, pas une file. Les recettes sont meilleures
que ce qu'on en avait dit, ce qui rend leur invisibilité plus grave et non
moins : ce n'est pas un brouillon qu'on a oublié de finir, c'est la chaîne de
presse ancienne complète qui attend derrière une porte jamais percée.

---

## 2. Ce qui bloque la convergence — mesuré, pas supposé

Les quatre adapters LLM déclarent chacun quatre modes
(`llm_modes()` : `anthropic`, `mistral`, `ollama`, `openai`). La table des
rôles n'en câble que deux.

| Mode déclaré par les adapters | Rôle correspondant dans `roles()` |
|---|---|
| `text_only` — corriger un texte | `correction` ((RAW,) → (CORR,)) ✅ |
| `refine` — affiner un texte corrigé | `refine` ((CORR,) → (CORR,)) ✅ |
| `zero_shot` — le modèle lit l'image | **aucun** |
| `text_and_image` — image **+** texte OCR | **aucun** |

Conséquence directe : une recette **ne peut pas** décrire le zero-shot, l'un
des pipelines phares du produit. Deux entrées dans une table les ajoutent — ce
n'est pas un chantier, mais c'est un **préalable**, pas un détail qu'on glisse
à la fin.

---

## 3. Le modèle mental — ce qui ne change pas

La page du banc d'essai dit aujourd'hui : *tu empiles des concurrents dans une
file, tu lances, tu reçois un rapport qui les compare*. C'est juste, c'est
compris, et **ça ne bouge pas**. Ce qui change est en amont : **comment on
produit une entrée de file**.

Trois voies, de la plus guidée à la plus libre, produisant toutes le **même
objet** :

| Couche | Nom à l'écran | Pour qui | Produit |
|---|---|---|---|
| **1** | *Choisir une forme* | celui qui veut un résultat, pas un pipeline | une recette + ses briques |
| **2** | *Réglages* (pli par étape) | celui qui a un corpus récalcitrant | la même, + `params` |
| **3** | *Composer* | celui qui cherche une forme que personne n'a nommée | un graphe neuf, enregistrable en recette |

La couche 3 **alimente** la couche 1 : sa sortie est un YAML de recette. Le
composeur n'est pas une porte de sortie du système de recettes, c'en est la
fabrique.

---

## 4. Couche 1 — choisir une forme

```
┌─ Concurrents ────────────────────────────────────────────────┐
│  ● Choisir une forme    ○ Composer                           │
│ ──────────────────────────────────────────────────────────── │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐  │
│  │ OCR seul   │ │ OCR puis   │ │ Presse     │ │ Trois     │  │
│  │            │ │ LLM        │ │ ancienne   │ │ moteurs,  │  │
│  │ La         │ │            │ │ multi-col. │ │ un vote   │  │
│  │ référence  │ │ Répare-t-il│ │            │ │           │  │
│  │ contre     │ │ ou         │ │ Redresse,  │ │ Vote par  │  │
│  │ laquelle   │ │ réécrit-il?│ │ détecte,   │ │ jeton     │  │
│  │ juger.     │ │            │ │ remet en   │ │           │  │
│  └────────────┘ └────────────┘ └──── ✓ ─────┘ └───────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Rien n'est réinventé.** Titre et description sont dans le YAML, déjà
bilingues, déjà écrits pour dire ce que la forme *cherche à savoir* (« répare-
t-il, ou réécrit-il ? ») et non ce qu'elle enchaîne techniquement. La carte
affiche ce que la recette dit d'elle-même ; `recipe_catalog(lang)` le rend déjà.

Une forme choisie déplie ses étapes — une ligne par étape, le rôle nommé en
clair à gauche, la brique choisissable à droite :

```
┌─ Presse ancienne multi-colonnes ─────────────────────────────┐
│                                                              │
│  1  Prétraitement      [ preprocess          ▾ ]   ⚙ réglages│
│  2  Segmentation       [ tesseract_layout    ▾ ]   ⚙         │
│  3  Reconnaissance     [ tesseract_layout    ▾ ]   ⚙         │
│     par région           ↳ une fois par bloc détecté         │
│  4  Ordre de lecture   [ reading_order       ▾ ]   ⚙         │
│  5  Projection texte   [ layout_to_text      ▾ ]             │
│                                                              │
│                                   [ + Ajouter à la file ]    │
└──────────────────────────────────────────────────────────────┘
```

**Règles de la couche 1**

- Le `<select>` d'une étape ne contient que `Role.briques` — pas le registre
  entier. La liste est ordonnée par préférence et son **premier élément est
  toujours exécutable sur une machine nue** (`tesseract_layout` ouvre la marche
  « parce qu'il est le seul à ne rien exiger — ni poids, ni SDK, ni adresse »).
- Une brique indisponible reste **affichée et désactivée**, avec sa raison,
  comme le fait déjà le formulaire actuel (`{{ t.engine_unavailable }}`). On
  montre ce qui existe ; on empêche de le choisir.
- `cli_layout` et `ocrd` restent hors de la liste web (`CLI_ONLY_KINDS`).
- Le fan-out (`Role.fanout`) s'annonce en sous-titre — « une fois par bloc
  détecté » — parce que c'est la seule étape dont le coût dépend de la page.

---

## 5. Couche 2 — les réglages, et le point dur

Le pli `⚙` ouvre les paramètres de la brique choisie :

```
│  3  Reconnaissance     [ tesseract           ▾ ]   ⚙ ouvert  │
│     ┌──────────────────────────────────────────────────────┐ │
│     │ Langue           [ fra                             ] │ │
│     │ Résolution (dpi) [ 300        ]  défaut : non fixée  │ │
│     │   ↳ Tesseract rend parfois une page vide sans lui.   │ │
│     │ Découpe (psm)    [ 6 — bloc uniforme              ▾ ] │ │
│     │ Délai (s)        [ 120        ]                      │ │
│     └──────────────────────────────────────────────────────┘ │
```

### Le problème

**Aucun module ne déclare les paramètres qu'il accepte.** Le contrat `Module`
(`pipeline/protocols.py`) porte `name`, `version`, `input_types`,
`output_types`, et un `params: dict[str, ParamValue]` **non typé**. Le
formulaire ci-dessus ne peut donc pas se générer, et rien ne peut valider ce
qu'on y tape.

### Les deux voies

**Un éditeur clé/valeur libre.** L'utilisateur tape `dpi` = `300`. Coût nul.
Mais il faut connaître le nom, et une faute de frappe est **avalée en
silence** : le paramètre entre dans le dict, personne ne le lit, le run tourne
sans lui, et rien ne le signale.

**Une déclaration sur le module** — nom, type, défaut, bornes, libellé. Le
formulaire, la validation et l'aide en ligne de commande sortent d'une **source
unique**.

### La décision : la déclaration

Le projet a **déjà tranché ce débat une fois, sur le même motif**. D-251 a
ajouté `LABELS`/`DOMAIN` aux segmenteurs parce qu'une table `psm_by_class`
écrite pour le vocabulaire d'un modèle était « **ignorée en silence** » sur un
autre, chaque région retombant sur le réglage par défaut. Le raisonnement
s'applique mot à mot à `dpi` : un réglage qu'on croit posé et qui ne l'est pas
produit un résultat faux qu'aucun signal n'annonce — et l'expérience existe,
c'est le défaut de page blanche qui a bloqué le premier banc de presse.

Deux gains qui emportent la décision :

1. **C'est une décision d'enveloppe** (`CLAUDE.md` §2, axe 1) : le contrat de
   module est dimensionné pour le scope complet, pas incrémenté au besoin.
2. **Les modules tiers l'obtiennent gratuitement.** Un YOLO branché depuis
   HuggingFace qui déclare ses paramètres reçoit son formulaire dans l'UI sans
   qu'on touche à cinoc. C'est exactement l'objectif central annoncé au
   `CLAUDE.md` §3 — « brancher facilement un module tiers est un objectif
   central du produit, pas une option ».

**Forme retenue** : un `ClassVar` déclaratif sur le module, comme `LABELS`. Pas
de schéma Pydantic par brique (une classe de plus par adapter), pas de
JSON-Schema (un second vocabulaire de types à maintenir). La déclaration reste
**passive** : elle décrit, elle n'exécute pas. La validation vit en couche
`app`, appliquée par les **deux** transports — c'est la clause anti-doublon.

**Ce que la déclaration ne fait pas** : elle n'est pas obligatoire. Un module
qui ne déclare rien garde son `params` libre et n'affiche aucun pli — on ne
refuse que ce qu'on peut réfuter, exactement comme `LABELS = None` face à
`LABELS = frozenset()` (D-251).

---

## 6. Couche 3 — le composeur contraint

```
  1  Segmentation        [ doclayout_yolo      ▾ ]
                                                     disponible : LAYOUT, IMAGE
  [ + Étape ▾ ]
     ├── Reconnaissance par région   (LAYOUT, IMAGE → LAYOUT)
     ├── Ordre de lecture            (LAYOUT → LAYOUT)
     ├── Correction structurée       (LAYOUT → LAYOUT, texte, décisions)
     ├── Projection texte            (LAYOUT → texte brut)
     ├── Export ALTO                 (LAYOUT → ALTO)
     └── Export PAGE                 (LAYOUT → PAGE)
        ─────────────────────────────────────────────
        Correction par LLM — indisponible : demande du texte brut
```

**Le principe, en une phrase** : à partir de l'ensemble des types déjà
produits, les rôles proposables sont ceux dont les `entrees` y sont contenues.
C'est une fonction de cinq lignes sur `roles()`.

```python
def roles_branchables(disponibles: frozenset[ArtifactType]) -> list[str]:
    return [nom for nom, role in roles().items()
            if set(role.entrees) <= disponibles | set(role.aussi)]
```

**Pourquoi ce n'est pas l'éditeur de nœuds écarté par D-239.** Un canevas où
l'on relie des boîtes n'empêche rien : on branche une sortie texte sur une
entrée image, et on découvre l'erreur à l'exécution — ou pire, on lit un
message d'erreur qui explique après coup ce qu'on n'aurait pas dû faire. Ici,
**le mauvais choix n'est jamais affiché**. Il n'y a pas de validation parce
qu'il n'y a rien à invalider. C'est la « troisième voie » de D-239 poussée d'un
cran : la forme éprouvée qu'on choisit (couche 1), et la forme neuve qu'on ne
peut construire que valide (couche 3).

**Les rôles indisponibles restent visibles, grisés, avec leur raison** — « Ordre
de lecture — demande une mise en page ». Un menu qui rétrécit sans dire pourquoi
enseigne moins qu'un menu qui montre la marche manquante.

**Sortie** : `[ Enregistrer comme recette ]` produit le YAML, validé au
chargement par `_valider` comme n'importe quelle recette livrée. De la donnée,
versionnable, relançable en CLI, qui rejoint le catalogue de la couche 1.

**Ce que la couche 3 ne fera pas** : pas de disposition libre, pas de zoom, pas
de mini-carte, pas de branches parallèles dessinées côte à côte. `merge` se
décrit par une étape qui **nomme** ses sources (c'est déjà la forme de
`RecipeStep.merge`), pas par des fils qui se rejoignent.

---

## 7. La bascule — un seul constructeur à l'arrivée

Une fois les deux rôles manquants ajoutés (§2), une recette peut décrire les
quatre modes du formulaire actuel. Les onglets deviennent alors **quatre
recettes**, et `_pipeline_for_competitor` / `_hybrid_competitor` meurent.

Ce n'est pas facultatif. Le garde-fou n° 1 du projet interdit de garder deux
chemins « le temps de migrer » (`CLAUDE.md` §5.1). Les deux constructeurs
coexistent aujourd'hui **par accident** ; les laisser coexister *par décision*
serait la faute que le garde-fou nomme. La mort de l'ancien est donc **datée**,
pas laissée ouverte : c'est l'item 6 de P5c.

**Ce que la bascule rend** : `run_planning.py` perd ~250 lignes de câblage à la
main et cesse d'être au ras de son plafond ; toute capacité nouvelle du
composeur s'écrit dès lors dans la table des rôles, donc **des deux côtés à la
fois**.

**Ce qu'il faut préserver en basculant**, et qui n'est pas dans les recettes
aujourd'hui — chacun à traiter explicitement, aucun à perdre en silence :

| À préserver | Où il vit aujourd'hui |
|---|---|
| le choix d'un prompt curé + le prompt libre | `Competitor.prompt` / `prompt_name` |
| l'autocomplétion des modèles par fournisseur | `/api/models/{provider}` + `datalist` |
| la case NER et son modèle | `Competitor.ner` / `ner_model` |
| la case « exporter l'ALTO » | `Competitor` → étape `alto_export` |
| l'aperçu de segmentation | `/api/segmentation/preview` |
| le segmenteur distant (adresse + jeton) | `Competitor.segmenter_endpoint` / `_token` |

Les quatre premiers sont des `params` ou des étapes, donc exprimables en
recette une fois la déclaration du §5 posée. L'aperçu est un **transport**, il
reste tel quel. Le segmenteur distant porte un **secret** : il ne doit pas
entrer dans un YAML enregistrable — à traiter comme un réglage de session, pas
comme un paramètre de recette.

---

## 8. Ordre de construction

L'ordre suit les dépendances, pas le confort. Chaque étape est une tranche
verticale, verte de bout en bout, fusionnée avant la suivante.

| # | Tranche | Pourquoi là |
|---|---|---|
| **1** | La troisième clause du garde-fou de parité | Elle tient tout le reste : sans elle, les sept autres sont des intentions. Rend rouges les trois routes de recette, qui s'inscrivent en dettes datées. |
| **2** | Les deux rôles manquants (`zero_shot`, `text_and_image`) | Préalable à toute convergence : sans eux, une recette ne peut pas décrire ce que le formulaire décrit déjà. |
| **3** | La déclaration des paramètres au contrat de module | Préalable à la couche 2, et d'enveloppe : on ne l'incrémente pas au besoin. |
| **4** | Couche 1 — catalogue de recettes branché à la file | La valeur visible la plus vite : cinq formes deviennent atteignables sans une ligne de nouveau pipeline. |
| **5** | Couche 2 — le pli réglages, généré depuis 3 | `--dpi 300` cesse d'être réservé au terminal. |
| **6** | La bascule : les quatre onglets deviennent des recettes ; l'ancien constructeur meurt | Interdit de traîner deux chemins. Daté ici. |
| **7** | Couche 3 — le composeur contraint + « enregistrer comme recette » | Dernier : il n'est que l'éditeur de ce que 2→6 rendent réel. |
| **8** | `standardize_corpus` : une face ou l'autre · la porte « spec complète » tranchée | Indépendants du reste, à glisser où ça tombe. |

**Ce que cette phase ne contient pas** : aucune brique de pipeline, aucune
métrique, aucune section de rapport, aucun moteur. Deux rôles, une déclaration,
du câblage, et un garde-fou.

---

## 9. Réserves consignées

**Le composeur ne peut pas tout dire.** `RecipeStep` porte `after` et `merge`,
donc des graphes ; mais le pool d'artefacts est indexé **par type**, ce qui
interdit deux sorties du même type vivant côte à côte hors d'une fusion. La
couche 3 doit donc refuser — ou plutôt ne pas proposer — une seconde étape
produisant un type déjà présent, sauf à la fusionner. À vérifier à la
construction : c'est la contrainte la moins évidente du modèle.

**Un secret n'est pas un paramètre.** Jeton de segmenteur distant, clés d'API :
ils traversent le formulaire mais ne doivent jamais entrer dans une recette
enregistrée. La déclaration du §5 doit pouvoir marquer un paramètre comme
**non sérialisable**, sinon « enregistrer comme recette » exfiltre un jeton
dans un fichier versionné.

**La page grandit.** `benchmark.html` fait 363 lignes, `benchmark.js` 750. Trois
couches de composeur ne tiennent pas en plus du formulaire actuel sans que la
bascule (§7) retire l'ancien. C'est une raison de plus pour que l'item 6 ne
glisse pas.
