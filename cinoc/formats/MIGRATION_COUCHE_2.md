# Plan de migration — Couche 2 (`formats/`) : Picarones → Cinoc

> **Statut** : plan validé, prêt à exécuter.
> **Périmètre** : uniquement la couche 2 (`formats/`).
> **Source** : `Picarones/picarones/formats/` (parsers/writer/types ALTO & PAGE, sécurité XML, normalisation).
> **Cible** : `Cinoc/cinoc/formats/`.

---

## 1. Objectif & périmètre

La couche `formats` est la **frontière entre les formats de fil** (ALTO XML, PAGE XML,
texte brut) et le reste du système. Elle lit (parse), écrit (sérialise) et normalise du
texte ; elle n'opère que sur des **bytes** et des **chaînes**, jamais sur un résultat
d'OCR ou un calcul de métrique.

**Dans le périmètre :**

- parsers + writers **ALTO** et **PAGE** (symétriques) ;
- sécurité XML (`safe_parse_xml`) ;
- lecteur de **texte brut** (`read_plaintext`) ;
- **normalisation** (profils de comparaison).

**Hors périmètre (différé, avec justification) :**

- `CanonicalLayout` (modèle structurel neutre) — payload de `ArtifactType.LAYOUT` ;
- l'**assembleur** `CanonicalLayout → AltoDocument/PageDocument` ;
- le lecteur `CANONICAL_DOCUMENT` (sortie VLM markdown/JSON) ;
- les **projecteurs** Document → texte (couche 3) et toutes les **métriques** (couche 3).

```
cinoc/formats/
├── __init__.py        API publique resserrée
├── _xml.py            safe_parse_xml (lxml durci)
├── alto/              types.py · parser.py · writer.py
├── pagexml/           types.py · parser.py · writer.py   (writer = NOUVEAU)
└── text/              normalization.py · plain.py
```

---

## 2. Principe directeur de ce plan

On ne **fige à l'avance** qu'une décision qui est **(1) irréversible**, **(2) transverse**
(façonne beaucoup de fichiers ou plusieurs couches), ou **(3) une abstraction qu'on
s'apprête à bâtir en grand et qui pourrait être fausse**. Tout le reste — local,
réversible, pas cher à changer — **se décide en codant, sous test**.

Ce document fige donc un **noyau court** (§3–§6) et **renvoie explicitement au codage**
le reste (§8). Sur-spécifier des politiques locales en prose serait du gaspillage : un
test les tranche mieux (cf. la correction de l'ordre de normalisation, trouvée tardivement
en raisonnant dans l'abstrait — voir §5, D8).

---

## 3. Noyau verrouillé

Décisions qui passent le filtre (1/2/3) et qui sont **figées**.

| # | Décision | Filtre | Détail |
|---|----------|--------|--------|
| **L1** | **lxml** pour tout parsing/écriture XML | (2)+(1) | Toute la couche en dépend ; déterminisme (C14N), namespaces thread-safe, parsing tolérant. Changer de lib ensuite toucherait tous les fichiers. |
| **L2** | **Entonnoir unique `safe_parse_xml`** + durcissement explicite | (1)+(2) | Tous les parsers passent par lui. Config : `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`, **rejet de tout `<!DOCTYPE>`**. Une faille livrée est irréversible. Un test de sécurité dédié (XXE, billion laughs, DOCTYPE distant) est obligatoire. |
| **L3** | **Frontière `bytes`, zéro I/O** | (2) | `parse_alto`/`parse_pagexml`/`read_plaintext` prennent des **bytes** ; la lecture disque est au caller (couche 3). Les payloads de corpus portent des bytes, **pas** des `str` pré-décodés. |
| **L4** | **Forme du modèle de types** : géométrie **numérique** (pas de chaînes), ordre de lecture en **arbre**, régions modélisées largement, confidences présentes | (3)+(2) | Façonne parser, writer, futures métriques structurelles et l'adaptateur vers `CanonicalLayout`. Re-façonner ensuite = cher. Le *détail des champs* reste du codage. |
| **L5** | **Géométrie native au format** | (2) | ALTO : `bbox` + `polygon` + `baseline` ; PAGE : `coords` (polygone) + `baseline`. Points **entiers**. **Unité de coordonnées + dimensions de page capturées** (la réconciliation inter-unités est couche 3). Pas de fusion neutre ici (différée avec `CanonicalLayout`). |
| **L6** | **Writers symétriques, riches, depuis le standard** | (2) | `write_alto(AltoDocument)` **et** `write_pagexml(PageDocument)` → bytes. `write_pagexml` est **nouveau** (absent de Picarones). Sortie ALTO v4 / PAGE PRImA 2019-07-15 ; parsers tolérants aux versions antérieures en entrée. `write_alto` n'écrit **que** l'ALTO 4 (D-272 : l'option v2/v3/sans namespace n'avait que des tests pour consommateurs, et aucune de ces sorties n'était valide dans sa version) ; `write_pagexml` n'écrit **que** le PAGE 2019 (D-273 : un PAGE 2013 lu est réécrit en 2019 ; seul l'`PageAssembler` écrit du PAGE, et toujours en 2019). |
| **L7** | **Déterminisme du writer** | (1) | Garantie = **idempotence de contenu** (`parse(write(x)) == x`), pas l'égalité octet vs un fichier d'origine quelconque. Sérialisation **C14N** (lxml), **aucun horodatage réel ni UUID** émis (le `Metadata` que PAGE exige porte une date fixe, `1970-01-01T00:00:00Z`, D-273), ordre d'attributs figé, sérialisation **sans état global** (nsmap par élément). Ce que le XSD exige et que le document ne porte pas (`Page@ID`, `PHYSICAL_IMG_NR`, `ID` de bloc ; en PAGE, `id` de région/ligne/mot/groupe) est **dérivé du rang**, hors des identifiants pris (D-272, D-273) — ce qui n'a pas de valeur dérivable honnête est **dit absent** (géométrie inconnue → polygone nul marqué `coords {absent:true;}`) ou **refusé** (dimensions de page inconnues, unité non pixel en PAGE) : l'idempotence vaut pour un document complet, et `write` est un point fixe dès le second passage. |
| **L8** | **Pas de passthrough** : modèle **fermé** + `logger.warning` | (3) | Aucun scénario benchmark ne re-sérialise une entrée parsée → le passthrough n'a **aucun consommateur dans le scope**. La règle « rien en silence » est honorée par un `warning` sur élément structurel non modélisé. (Décision de *scope*, pas de difficulté : lxml le rendrait faisable, mais ce serait de la surface « au cas où ».) |
| **L9** | **Sorties validées au XSD officiel, en test ; entrée tolérante** — *renverse la décision initiale « pas de validation XSD »* (arbitrage A9, D-271) | (1) | Décision initiale : sortie « conforme par construction », garantie par round-trip C14N, aucune mention de XSD. **Infirmée par la mesure (D-264)** : 0/21 ALTO et 0/11 PAGE écrits passaient le XSD officiel — un round-trip prouve la fidélité à soi-même, pas la conformité. Désormais : XSD officiels vendorisés **octet pour octet** dans `tests/fixtures/xsd/` (empreintes vérifiées, import redirigé par résolveur lxml, aucun réseau), toute sortie d'écrivain validée par `lxml.etree.XMLSchema` **dans les tests** ; **aucune** validation à l'entrée ni à l'exécution, aucune dépendance. **ALTO livré (D-272)** : `write_alto` et le chemin de l'`AltoAssembler`, sur les 45 ALTO du dépôt (`tests/formats/alto/test_alto_xsd.py`). **PAGE livré (D-273)** : `write_pagexml` et le chemin du `PageAssembler`, sur les PAGE **et** les ALTO du dépôt (`tests/formats/pagexml/test_page_xsd.py`). |
| **L10** | **`CanonicalLayout` différé** | (3) | Le **nom** `ArtifactType.LAYOUT` est réservé en couche 1. La **forme** (sans standard externe, sans consommateur) serait spéculative → co-conçue avec la tranche segmentation. |
| **L11** | **7 leviers de normalisation** | (2) | `unicode_form` (`none/NFC/NFD/NFKC/NFKD`, défaut NFC) · `caseless` · `whitespace` (`none/intra_line/flat`) · `strip_diacritics` · hygiène toujours active (control / zero-width / soft-hyphen / BOM) · `diplomatic_table` (mono-passe, cf. F12) · `exclude_chars` (+ `exclude_mode` `delete/space`). |
| **L12** | **12 profils, anglais-neutres, défaut `nfc`** | (2) | `nfc`, `nfkc`, `caseless`, `minimal`, `no_diacritics`, `flat_text`, `keep_line_breaks`, `no_punctuation`, `no_apostrophes`, `medieval_french`, `early_modern_french`, `medieval_latin`. **Aucun profil privilégié par défaut.** Profils anglais (`*_english`, `secretary_hand`) **supprimés**. |
| **L13** | **Dépendances dures** | (2) | `lxml`, `pyyaml`. Sécurité XML par **durcissement lxml natif** (pas de `defusedxml` : son support lxml est déprécié — décision A). À déclarer dans `pyproject.toml` + mettre à jour le test de whitelist d'architecture (`formats/` n'importe que `domain` + ces libs ; **jamais** `jiwer`/`rapidfuzz`/un moteur OCR). |
| **L14** | **Erreurs rattachées au domaine** | (2) | Base `FormatError(CinocError)` dans `domain/errors.py` ; `AltoParseError(FormatError)` / `PageParseError(FormatError)` dans leurs modules. Permet `except FormatError` et `except CinocError`. |
| **L15** | **API publique resserrée** | (2) | `safe_parse_xml` · `parse_alto`/`write_alto`/`AltoDocument`(+enfants)/`AltoParseError` · `parse_pagexml`/`write_pagexml`/`PageDocument`(+enfants)/`PageParseError` · `read_plaintext` · `NormalizationProfile`/`get_builtin_profile`/`NORMALIZATION_PROFILES`. Les internes restent privés. |

---

## 4. G-A — La décision porteuse : les types de format sont la cible **permanente** du parsing

C'est le **(3)** central. On s'engage sur :

> **Les types de format (`AltoDocument`/`PageDocument`) sont la cible *permanente* du
> parsing et la *source de vérité structurelle*. Le modèle neutre (`CanonicalLayout`,
> plus tard) est *toujours en aval*, atteint par un *adaptateur* — jamais une cible de
> parsing directe.**

Flux engagé :

```
écriture :  CanonicalLayout ─[adaptateur]→ AltoDocument/PageDocument ─[writer]→ bytes
lecture  :  bytes ─[parser]→ AltoDocument/PageDocument ─┬─[projecteur]→ texte   (métriques texte)
                                                         └─[adaptateur]→ CanonicalLayout (métriques structurelles)
```

**Pourquoi figer ça maintenant** : sans cet engagement, on risquerait un jour de « réécrire
les parsers pour qu'ils émettent `CanonicalLayout` » → réécriture **transverse**. S'y engager
ferme cette porte **et** justifie l'investissement riche d'aujourd'hui dans les types format
(ils ne sont pas du jetable). Conséquence assumée : on maintiendra **deux** représentations
structurelles riches (par-format + neutre) reliées par des adaptateurs — c'est le prix d'une
E/S fidèle par format **plus** un intérieur neutre propre, sans bâtir le modèle neutre de façon
spéculative.

---

## 5. Contrats transverses (G-B, G-C, G-D)

**G-B — Le profil de normalisation voyage comme valeur autonome, jamais par son nom.**
`(2)+(1)` (Picarones avait le bug du profil non propagé + un `Literal` de noms codé en dur).
Le `NormalizationProfile` est un **objet-valeur autonome** (pydantic figé, `as_dict()`),
**identifié et transmis par son contenu**, jamais par un nom de registre. Tout en aval
(RunSpec couche 4, fingerprint couche 6, API couche 8) thread la **valeur**, valide
**dynamiquement** contre le registre vivant, et **hashe le contenu** (pas le nom). `as_dict()`
a une forme **déterministe** : clés de table **triées**, `exclude_chars` en **liste triée**,
`unicode_form`/`whitespace`/`exclude_mode` comme chaînes d'énum. Pas de champ
`schema_version` (le jeu de champs fait foi ; un levier ajouté plus tard change `as_dict` →
invalide le cache, ce qui est correct).

**G-C — Convention de projection texte (frontière projection↔normalisation).** `(2)`.
Le levier `whitespace=intra_line` et le **CER inter-format** n'ont de sens que si la projection
émet des frontières de ligne/bloc **cohérentes et identiques** entre ALTO et PAGE. Contrat :
**un projecteur-vers-texte unique, `\n` entre lignes, `\n\n` entre blocs, à l'identique pour
les deux formats**, consommant l'arbre d'ordre de lecture de la même façon. *(Implémentation
en couche 3 ; la convention est fixée ici car transverse.)*

**G-D — Base des types : pydantic v2 figé.** `(2)+(1)`. Tous les types format sont des modèles
**pydantic v2 figés** (cohérent avec `domain`), **coût de validation assumé** sur les gros
documents. On ne revisite ce choix que si un profilage le justifie (le changer serait
transverse).

---

## 6. Risques de transfert Picarones → Cinoc

**MIG-1 — Portage des corrections scientifiques (F-audits).** `(1)+(3)`. Chaque couche
réécrite **inventorie et porte** ses corrections « F-x ». Pour la couche 2, deux seulement :
- **F11** : la table diplomatique s'applique à **toutes** les occurrences, **des deux côtés**
  (GT *et* OCR) → CER sur les classes d'équivalence (quotient), non biaisé. ⇒ **invariant de
  symétrie** (le même profil est appliqué aux deux textes), **érigé en test**.
- **F12** : substitution **mono-passe** (regex d'alternation, clé la plus longue d'abord)
  contre les cascades. ⇒ conservé, avec un test du cas d'échange (`u→v` **et** `v→u`).

**MIG-2 — Rupture nette, non rétro-compatible (à graver).** `(1)`. Cinoc change la
normalisation (nouveaux leviers, ordre corrigé). **Même profil + même entrée → CER différent
de Picarones.** Conséquence à acter : **Cinoc n'est pas numériquement compatible avec
Picarones ; toute « validation » par égalité de chiffres avec Picarones est invalide par
conception.** Cela protège la correction d'ordre (ci-dessous) contre une « remise en
conformité » avec le comportement bogué d'origine.

**MIG-3 — Dépouiller la narration, garder le raisonnement.** `(2)`. On supprime les étiquettes
de sprint/audit (`Audit scientifique F12`, `Sprint A14-S9`, `reporté…`) **mais on conserve la
justification** (p. ex. « mono-passe pour éviter les cascades »). Règle : *garder le pourquoi,
jeter la datation.* Aucune mention d'« optionnel non fait » dans le repo.

**MIG-4 — Placement.** La normalisation vit en **`formats/text` (couche 2)**, sans dépendances,
consommée vers l'extérieur. Délibéré et correct.

### Correction d'ordre de normalisation à porter (le bug D8)

Picarones applique `casefold` **avant** la table mais **sans casefolder les clés**, ce qui fait
qu'un profil `caseless` + table à clés minuscules **ne neutralise pas la casse** sur le texte
majuscule (`"U"` survit au lieu de devenir la cible de `u→…`). Règle correcte à implémenter :

> Sous `caseless`, **le casefold précède la table** **et** **les clés de table comme
> l'ensemble `exclude_chars` sont casefoldés** pour la correspondance ; on **ré-applique
> `unicode_form` après le casefold** (le casefold peut dé-normaliser).

Ordre canonique de `normalize()` (à **verrouiller par un test**, pas par la prose) :
`hygiène → unicode_form → casefold(si caseless, + folding des clés/exclude) → exclude_chars →
diplomatic_table → strip_diacritics → whitespace`. Aucun profil builtin ne combine
`caseless`+table, mais un profil **custom** le peut → piège silencieux, donc test obligatoire
(`caseless + {u:v}` sur `"Uu"`).

---

## 7. Inventaire source → cible

| Picarones (`formats/`) | → Cinoc (`formats/`) | Transformation principale |
|---|---|---|
| `_xml_utils.py` | `_xml.py` | Réécrit sur **lxml durci** (L2) ; **tous** les parsers passent par lui (Picarones les court-circuitait). |
| `alto/types.py` | `alto/types.py` | **Enrichi** : polygone + baseline + confidence ; régions non-texte (`ComposedBlock` récursif, `Illustration`, `GraphicalElement`, marges) ; arbre d'ordre de lecture ; géométrie numérique ; contraintes rejetant du valide **supprimées** (cf. §8). |
| `alto/parser.py` | `alto/parser.py` | lxml (xpath par nom local, `recover=True`+`warning`) ; passe par `safe_parse_xml` ; extraction de l'ordre de lecture + régions complètes. |
| `alto/writer.py` | `alto/writer.py` | **Réécriture quasi-totale** : sérialise toute la structure riche, C14N, sans état global ni horodatage. |
| `pagexml/types.py` | `pagexml/types.py` | **Enrichi** symétriquement ; régions non-texte + imbrication ; géométrie numérique ; baseline ; confidence ; **lignes et mots** (`PageWord` depuis D-273 : les ignorer perdait 161 et 258 mots sur deux pages OCR-D ; pas de glyphe, sans consommateur). |
| `pagexml/parser.py` | `pagexml/parser.py` | lxml ; `TextEquiv` par `index` le plus bas (corrige le bug « premier `Unicode` descendant ») ; toutes les régions retenues. |
| *(absent)* | `pagexml/writer.py` | **NOUVEAU** : `write_pagexml` symétrique. |
| `text/normalization.py` | `text/normalization.py` | Profil **pydantic figé** ; 7 leviers (L11) ; ordre corrigé (§6) ; 12 profils (L12) ; `from_yaml`/`from_dict`/`model_copy` ; suppression des profils & tables anglais. |
| *(absent)* | `text/plain.py` | **NOUVEAU** : `read_plaintext(bytes, encoding) → str` (décodage + BOM + fins de ligne). |
| `formats/__init__.py` | `formats/__init__.py` | API publique **resserrée** (L15) ; docstring **vraie** (pas de « validator », lxml mentionné car réellement utilisé). |

---

## 8. Explicitement laissé au codage (sous test)

Local, réversible, additif → **tranché en codant**, contre des **fixtures réelles**
(Tesseract-ALTO, Transkribus/eScriptorium-PAGE, Kraken, Gallica). Orientations
**non contraignantes** ci-dessous (point de départ, à valider par test) :

- **Tolérances parser** : conserver les coordonnées **négatives** (pas de clip) ; **pas** de
  caps de longueur arbitraires ; `SUBS_TYPE` libre (ne pas rejeter `Abbreviation`) ; honorer
  les `<SP>` ALTO ; **ne pas** `.strip()` le texte au parsing ; `recover=True` **avec
  `warning`** ; réfs d'ordre de lecture pendantes ignorées (+`warning`), régions orphelines
  rattachées en fin ; `huge_tree=False` assumé (échec clair sur fichier pathologique).
- **IDs** : génération **déterministe** pour les éléments sans `id`, **préfixe réservé** (ex.
  `cinoc-gen-…`) anti-collision, **un seul passage** partagé parser/writer/fan-out (contrat
  R6 : les `id` de région = ceux portés par `Artifact.region_id`).
- **Sémantique fine des leviers** : classe d'espaces de `whitespace` (Unicode + insécables) ;
  `strip_diacritics` = catégorie **`Mn`** ; `exclude_chars` = ensemble des caractères de la
  chaîne, **sans séparateur magique**, un codepoint par item, normalisé selon `unicode_form`,
  sérialisé en liste triée.
- **Confidences** : valeur **brute** stockée (réconciliation d'échelle = couche 3) ; **niveau
  mot/ligne** seulement (pas le par-caractère `CC`).
- **Normalisation hors chemin entités** (F1) : le `NormalizationProfile` ne s'applique
  **jamais** au niveau `ENTITIES` (offsets caractère) ni aux métriques MUFI/typographie (texte
  brut). Contrat à respecter côté couche 3.
- **`from_yaml`** : affordance **CLI/locale** uniquement ; le web n'accepte **jamais** un chemin
  YAML arbitraire (lecture de fichier) — builtin ou profil inline validé.
- **Encodage `.txt`** : défaut UTF-8 + gestion BOM + fins de ligne ; politique de secours à
  fixer au codage.

---

## 9. Tests & budgets

- **Round-trip** par **égalité structurelle via C14N** (et non par comparaison de compteurs,
  comme Picarones) + **fixtures réelles** par outil (R13).
- **Tests obligatoires** : sécurité (XXE / billion laughs / DOCTYPE), ordre de normalisation
  (`caseless + {u:v}` sur `"Uu"`), échange `u/v` mono-passe (F12), symétrie GT/OCR (F11),
  déterminisme writer (C14N stable).
- **Budgets de fichiers** honnêtes : `types.py`/`parser.py`/`writer.py` riches dépasseront
  400 LOC **par nature** ; découpage possible (`geometry.py`, `regions.py`). La règle est
  « croissance assumée », pas « petits fichiers ».

---

## 10. DoD vivante (couche 2) — **autorité de détail** ; le `MIGRATION_PLAN.md` indexe

> Tri-état : `[x]` fait **+ preuve** · `[ ]` à faire · `[~]` différé/réserve + raison.
> Mise à jour dans le **même commit** que le code. **Statut couche 2 : ✅ vert** (2026-05-31).

- [x] Parsers + writers **ALTO et PAGE** symétriques (writer PAGE = nouveau). — *preuve : `cinoc/formats/{alto,pagexml}/writer.py` ; `pytest tests/formats` vert*
- [x] **Sécurité XML** durcie (`safe_parse_xml`) : XXE / billion-laughs / DOCTYPE échouent. — *preuve : `tests/formats/test_xml.py`*
- [x] **Normalisation** : 7 leviers, 12 profils, ordre corrigé (bug D8). — *preuve : `tests/formats/text/test_normalization_edges.py` (cas `caseless + {u:v}` sur `"Uu"`)*
- [x] `read_plaintext` (bytes → str, BOM, fins de ligne). — *preuve : `tests/formats/text/test_plain.py`*
- [x] Round-trip par **égalité structurelle C14N** + fixtures réelles (Tesseract/Gallica/Transkribus/eScriptorium). — *preuve : `tests/formats/test_real_fixtures.py`*
- [x] Whitelist d'archi `formats` = `domain` + stdlib + `lxml`/`yaml`/`pydantic` (jamais jiwer/moteur). — *preuve : `tests/architecture/test_layer_dependencies.py::test_formats_imports_are_allowed`*
- [x] `mypy` + `ruff` verts ; import sans effet de bord. — *preuve : `mypy -p cinoc.formats` Success ; `test_no_side_effect_imports`*
- [~] **Divergence plan↔build actée** : §9 prédisait `types/parser/writer` > 400 LOC « par nature ». Réalité : **max 373** (`normalization.py`). — *aucun split nécessaire ; `test_file_budgets` veille. Bon signe : les types riches tiennent sous le seuil. (cf. journal `MIGRATION_PLAN.md` — à ajouter si récurrent).*
- [x] **T5** : `CanonicalLayout` (payload `LAYOUT`, en `domain`) + mappers **`alto_to_layout`** / **`layout_to_alto`** (`formats/alto/layout_map.py`, ALTO ↔ neutre, round-trip texte octet-stable) + **`page_to_layout`** (`formats/pagexml/layout_map.py`, PAGE → neutre : polygones, ordre de lecture aplati). — *preuves : `tests/formats/alto/test_alto_layout_map.py`, `tests/formats/pagexml/test_page_layout_map.py`* (l'assemblage en artefact `ALTO_XML` vit en couche 5, `AltoAssembler` : `pipeline` ne peut pas importer `formats`).
- [x] **Conformité XSD des ALTO écrits** (L9 renversée, A9 / D-271 → D-272) : ALTO 4.4 officiel vendorisé (`tests/fixtures/xsd/`, provenance + SHA-256 au `README.md`), **90/90** sorties valides — `write_alto` et chemin `AltoAssembler` sur les 45 ALTO du dépôt (rouge prouvé : 90/90 invalides, 268 erreurs). `Page@PHYSICAL_IMG_NR` lu et écrit ; `Page@ID`/`ID` de bloc dérivés s'ils manquent ; type de `TextBlock` en `TAGREFS` + `<OtherTag>` (convention eScriptorium, relue par le parser) au lieu du `TYPE` interdit ; unité de mesure portée par `CanonicalLayout.coordinate_unit` (aller-retour BNL `mm10` sans perte). — *preuves : `tests/formats/alto/test_alto_xsd.py`, `tests/formats/alto/test_alto.py`, `tests/formats/alto/test_alto_layout_map.py::test_layout_round_trip_is_lossless_on_bnl_gt`, `tests/adapters/layout/test_alto_assembler.py::test_segmenter_layout_assembles_into_valid_alto_4`*
- [x] **Conformité XSD des PAGE écrits** (même oracle, PAGE 2019 — A9 / D-271 → D-273) : `pagecontent.xsd` 2019-07-15 de PRImA vendorisé (empreinte = copie de l'audit D-264, provenance au `README.md`), **11/11** sorties valides — `write_pagexml` et chemin `PageAssembler` sur les 2 PAGE et les 7 ALTO en pixels du dépôt ; les 38 ALTO `mm10` **refusés** (`PageWriteError`) plutôt qu'écrits faux (rouge prouvé : 49/49 invalides). `Metadata` à date fixe ; `imageWidth`/`imageHeight` exigés (sinon refus), `imageFilename` vide s'il est inconnu ; identifiants dérivés, `NCName` vérifiés, références d'ordre de lecture suivies ; type de région hors énumération en `custom="structure {type:…;}"` (Transkribus/eScriptorium, relu) ; ImageRegion/SeparatorRegion/GraphicRegion écrites comme telles ; sous-régions avant les lignes ; géométrie inconnue → `0,0 0,0` marqué `coords {absent:true;}` (relu `None`). `<Word>` PAGE lus et écrits (texte, polygone, confiance). — *preuves : `tests/formats/pagexml/test_page_xsd.py`, `tests/formats/pagexml/test_page_writer.py`, `tests/formats/pagexml/test_layout_to_page.py`, `tests/adapters/layout/test_page_assembler.py::test_hybrid_output_is_valid_page_2019`, `tests/pipeline/test_fanout.py::test_fanout_line_ids_survive_both_exports`*
- [~] **Différé-par-design** : lecteur `CANONICAL_DOCUMENT`, projecteur `layout→texte` (couche 3). — *épaississements T5 ultérieurs.* (L'assembleur `layout→PAGE` existe : `layout_to_page` + `PageAssembler` en couche 5, conforme au XSD depuis D-273.)
