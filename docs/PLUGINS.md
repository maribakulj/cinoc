# Écrire un module Cinoc (plugin tiers)

Cinoc a **un seul point d'extension** : une **brique de pipeline** (segmenteur,
OCR/HTR, VLM, post-correcteur LLM, assembleur d'ALTO, ordre de lecture, NER…).
Tout le reste — métriques, importeurs de corpus, sections de rapport, tests
statistiques — reste **interne (first-party)**, non extensible. Une seule prise,
point (cf. `CLAUDE.md` §3).

## Socle et plugins : **même contrat**, seule la livraison diffère

Un moteur du socle (`tesseract`, `kraken`, `pero`, `calamari`, `google_vision`,
`azure_di`…) et un module tiers implémentent **exactement le même** `Module`
Protocol. Il n'y a **aucune discrimination** de contrat. La seule différence :

| | Socle (first-party) | Plugin (tiers) |
|---|---|---|
| Livraison | intégré (`cinoc/adapters/`), enregistré par `register_default_modules` | paquet pip séparé, découvert par entry-points |
| Dépendance lourde | extra optionnel (`cinoc[kraken]`…) | dépendance du plugin |
| Mode public (Space exposé) | exécutable si dans `PUBLIC_ENGINE_KINDS` (socle gratuit) | **désactivé (fail-closed)** — pas de code tiers in-process |

Autrement dit : « tout est déjà module ». Mettre une brique in-tree ou en plugin
est un choix de **packaging**, pas de contrat.

## Le contrat : `Module` Protocol (couche `pipeline`)

```python
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput


class MyOCR:
    def __init__(self, *, label: str, model: str) -> None:
        self._label = label
        self._model = model

    @property
    def name(self) -> str:
        return f"my_ocr:{self._label}"      # "<kind>:<label>"

    @property
    def version(self) -> str:
        return "1.0"                        # → RunManifest (reproductibilité)

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.RAW_TEXT})

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        # … reconnaître `inputs[ArtifactType.IMAGE]`, écrire la sortie dans
        # `context.workspace_uri`, respecter `context.deadline` …
        return StepOutput(artifacts={ArtifactType.RAW_TEXT: ...})
```

Garanties (runner ↔ module) : le runner fournit tous les `input_types`, une
`Deadline` et l'annulation coopérative ; le module renseigne tous ses
`output_types`, n'avale aucune exception, et lève à l'expiration de la deadline.
Enveloppez une lib externe pour la traduire vers ce Protocol — **jamais** un
second contrat interne (la dette que Cinoc abandonne).

## Le builder + l'entry-point

Un **builder** construit l'instance depuis ses kwargs ; le paquet le déclare dans
le groupe `cinoc.modules` :

```python
# mon_paquet/seg.py
from collections.abc import Mapping
from cinoc.pipeline.protocols import Module, ParamValue

def build_my_ocr(kwargs: Mapping[str, ParamValue]) -> Module:
    return MyOCR(label=str(kwargs["label"]), model=str(kwargs["model"]))
```

```toml
# pyproject.toml du plugin
[project.entry-points."cinoc.modules"]
my_ocr = "mon_paquet.seg:build_my_ocr"
```

`pip install mon-paquet` suffit : `discover_plugins` enregistre `my_ocr` dans le
registre runtime **comme le socle**. Le `kind` (`my_ocr`) devient référençable
dans une spec (`adapter_name = "my_ocr:c0"`).

## Trois contreparties (à tenir)

1. **API publique** = engagement de stabilité → on limite les points d'extension à
   un seul (la brique de pipeline).
2. **Exécution in-process** → en mode public la découverte est **désactivée**
   (sécurité d'un serveur exposé).
3. **Version déclarée** → alimente `RunManifest.module_versions` (reproductibilité).

## Quand in-tree, quand plugin ?

- **In-tree** (comme `kraken`/`pero`/`calamari`) : moteur établi qu'on veut
  maintenir dans le socle ; dép lourde en extra ; potentiellement exécutable sur un
  Space **privé**.
- **Plugin** : module expérimental/tiers, ou qu'on ne veut pas dans la surface du
  cœur ; installé à part, **désactivé** sur le Space public.

Les deux passent par le **même** `Module` Protocol.

---

## Troisième voie : **aucun code du tout** (`cli_layout`)

Avant d'écrire un module, poser la question : **l'outil sait-il déjà écrire du
PAGE-XML ou de l'ALTO ?** Si oui, il n'y a rien à écrire.

L'interface d'un segmenteur n'est pas l'outil, c'est le **format**. Le patrimoine
s'est standardisé sur ces deux-là ; une brique qui lit *le format* branche donc
toute une famille d'outils, là où un adaptateur par *outil* n'en branche qu'un.

```yaml
steps:
  - id: seg
    kind: segmentation
    adapter_name: cli_layout:eynollah
    input_types: [image]
    output_types: [layout]

adapter_kwargs:
  cli_layout:eynollah:
    label: eynollah
    command: "eynollah -i {image} -o {out} -m ~/modeles/eynollah"
```

`{image}` est la page, `{out}` un dossier **vide** que Cinoc alloue et nettoie.
L'outil y écrit **un** fichier `.xml` ; le dialecte est reconnu à son contenu,
pas à son extension.

Les outils visés — eynollah, `kraken segment -bl`, les processeurs OCR-D,
dhSegment — écrivent tous du PAGE-XML, et c'est à ce titre qu'ils sont
branchables. **Aucun n'a été exécuté dans la suite de tests** : celle-ci vérifie
le contrat (découpage, relecture des deux dialectes, refus) contre un faux outil.
Le premier branchement réel reste à mesurer.

### Ce que la brique refuse, et pourquoi

| Refus | Raison |
|---|---|
| **Aucun shell.** La commande est découpée (`shlex`) *avant* substitution | Un chemin contenant `; rm -rf` reste **un argument**. Substituer d'abord laisserait fabriquer une seconde commande. |
| **Zéro ou plusieurs `.xml`** produits | En choisir un ferait dépendre le résultat de l'ordre du système de fichiers — l'invariant de déterminisme tombe. |
| **Un XML sans aucune région** | Bien formé mais vide, il donnerait une page blanche : un CER de 1,0 **sans message**. C'est le pire mode de défaillance d'un banc d'essai. |
| **Tout appel depuis le web** | Voir ci-dessous. |

### Pourquoi le web la refuse toujours

`cli_layout` exécute une commande **écrite dans la spec**. C'est sa raison d'être
en local, et ce serait un shell offert par HTTP.

Le refus (`cinoc.app.engines.CLI_ONLY_KINDS`) est donc **inconditionnel** : il ne
dépend pas du mode public. Le mode public borne une *exposition* ; ce verrou
borne une *capacité*. « Instance privée » veut dire « les gens que je connais »,
pas « les gens à qui je confie un shell ».

## OCR-D : une brique à part, et pourquoi

OCR-D ne rentre pas dans `cli_layout`, et c'est instructif. Ses processeurs ne
voient **pas une image** : leur unité est un *workspace METS*, ils lisent un
groupe de fichiers et en écrivent un autre. Les brancher par `cli_layout`
demanderait d'enchaîner trois commandes — donc un script shell, hors du dépôt,
sans test ni refus. Ça marche, et c'est du bricolage.

La brique `ocrd` traduit ce contrat :

```yaml
adapter_name: ocrd:segment
adapter_kwargs:
  ocrd:segment:
    label: segment
    processor: ocrd-tesserocr-segment
    parameters: {find_tables: true}
    bin_dir: ~/outils/ocrd-env/bin   # facultatif : sinon le PATH
```

Le gain est le même qu'avec `cli_layout` — *une brique, une famille* : la
centaine de processeurs OCR-D (binarisation, redressement, segmentation,
reconnaissance) devient un paramètre.

Portée assumée : **`IMAGE → LAYOUT`**. OCR-D enchaîne aussi PAGE → PAGE ;
réinjecter un layout dans un workspace est un autre travail, qu'aucun
consommateur ne demande aujourd'hui.

> `ocrd-tesserocr-*` a besoin de `TESSDATA_PREFIX` dans l'environnement
> (`/opt/homebrew/share/tessdata` sur macOS Homebrew). C'est une affaire
> d'installation, pas de spec : la brique ne fabrique pas d'environnement.

### La règle générale

L'outil parle-t-il **déjà** PAGE ou ALTO, en une commande sur une image ?
→ `cli_layout`, une ligne de YAML.
Son contrat est-il **autre** (workspace, bibliothèque, format maison) ?
→ un adaptateur, qui traduit ce contrat — et qui vit dans le dépôt, avec ses
tests et ses refus.

### Quand écrire quand même un adaptateur

- l'outil est une **bibliothèque Python**, pas une commande (pas de sous-processus
  à lancer, pas de fichier à relire) ;
- il rend un format **propre à lui** (JSON maison, masques, tenseurs) ;
- il faut le charger **une fois** pour mille pages — `cli_layout` relance la
  commande à chaque page, ce qui est rédhibitoire pour un modèle lourd.

Hors de ces trois cas, une ligne de YAML suffit.
