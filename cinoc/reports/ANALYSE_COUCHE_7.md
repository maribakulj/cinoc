# ANALYSE_COUCHE_7.md — `reports/` (Picarones → Cinoc)

> **Type** : session d'ANALYSE (guide de portage **durable**). **Aucun code Cinoc écrit.**
> **Couche** : 7 = `reports` dans `domain(1) ← formats(2) ← evaluation(3) ← pipeline(4) ← adapters(5) ← app(6) ← reports(7) ← interfaces(8)`.
> **Source gelée** : `../Picarones/picarones/reports/` — **91 fichiers Python / 17 726 LOC**, + **3 423 LOC JS**, **2 948 LOC CSS**, **1 117 LOC HTML/J2**, **2 380 LOC data (i18n/glossary)**, + `chart.umd.min.js` vendorisé (208 KB). **Total ≈ 27 600 LOC** — la plus grosse couche du projet.
> **Couches amont mergées dont on dépend** : `domain` (mergée), `formats` (mergée), `evaluation` (plan `MIGRATION_COUCHE_3.md`), `pipeline` (analyse `ANALYSE_COUCHE_4.md`), `adapters` (analyse `ANALYSE_COUCHE_5.md`), `app` (analyse `ANALYSE_COUCHE_6.md`).
> **Méthode** : 6 sous-agents d'exploration en parallèle (orchestration · data-layer · renderers A · renderers B · charts/views/helpers · narrative/templates) **+ recoupement personnel des points décisifs dans le code** (types d'entrée, signatures, ré-agrégation, charting, accroches narrative). **Une erreur d'agent corrigée** par recoupement : Chart.js déclaré « mort » à tort — il est **vivant** (cf. §1.4-E).
> **Partie 1 = durable** (source figée). **Partie 2 = périssable** (« à confirmer à la tranche »). Verdicts **PROVISOIRE — à confirmer au build**.

---

## PARTIE 0 — Vérification anti-contradiction (obligatoire)

Aucune conclusion ne contredit `CLAUDE.md` ni une couche mergée/planifiée. L'analyse **confirme dans le code** quatre décisions déjà actées :

| Décision actée (où) | Confirmé dans le code Picarones (preuve) |
|---|---|
| **Moteur narratif SUPPRIMÉ entièrement** (`CLAUDE.md` §6/D2) | `reports/narrative/` = 2 162 LOC, **feuille du DAG** (n'importe que `domain.facts`) ; **3 accroches** seulement (`generator.py:254-255`, `web/routers/synthesis.py`, `domain/__init__` ré-exports `Fact*`). Suppression chirurgicale. |
| **Renderers HTML sans interface commune → un `Protocol Section`** (`CLAUDE.md` §8.2) | `section_registry.py:50` `ArgKind = Literal["report","engines","subkey","custom"]` → **4 signatures** réelles ; 37 renderers (8 167 LOC). Confirmé. |
| **Data-layer qui ré-agrège `evaluation/` → consommer `RunResult` direct** (`CLAUDE.md` §8.3) | `html/data/` ré-agrège : `statistics.py:41` reconstruit les listes CER + recalcule Friedman/Nemenyi/bootstrap ; `pareto.py:66` recalcule `sum(durs)/len(durs)` ; `:104` recalcule 3 fronts Pareto. Anti-pattern confirmé. |
| **`RunResult` = format unique, reports le lit direct** (`MIGRATION_COUCHE_3.md` §8/§9 ; `ANALYSE_COUCHE_6.md` L62-65) | Picarones est **en mi-migration** : `render.py`/`csv`/`json` consomment **déjà `RunResult`** ; le gros `generator.py:137` consomme encore `BenchmarkResult`. La ligne de partage du portage est **déjà tracée dans la source** (cf. §1.2). |

> **Note de placement (vérifiée, pas de contradiction)** : `ReportRenderer` (Callable) vit dans `pipeline/run_result.py` en source **par contournement d'un import illégal `reports→app`** (`ANALYSE_COUCHE_4.md` L107). En Cinoc il appartient à la frontière `app`/`reports` (app **injecte** un renderer). `reports` ne dépend que de couches internes — **jamais** `app`/`interfaces` (vérifié : 0 import `app.`/`interfaces.` dans tout `reports/`). Direction de couche **saine**.

---

# PARTIE 1 — ANALYSE DE LA SOURCE PICARONES (durable)

## 1.1 Inventaire exact (91 py / 17 726 LOC + assets)

| Sous-paquet | Fichiers | LOC py | Rôle vérifié |
|---|---:|---:|---|
| **`/`** (`__init__.py`) | 1 | 26 | Docstring de couche. Docstring **aspirationnelle** : promet « consomme `RunManifest`+`view_results.jsonl` » — **faux** pour le chemin réel (`generator` lit `BenchmarkResult`). |
| **`html/`** (orchestration) | 6 | **2 196** | `generator`(458, legacy) · `render`(643, propre) · `section_registry`(379) · `comparison`(409) · `snapshot`(280) · `__init__`(27). **Deux chemins** (§1.2). |
| **`html/data/`** (data-layer) | 9 | **1 614** | Construit `report_data: dict` pour les templates ; **ré-agrège l'évaluation** (stats, pareto, difficulté, métriques extra). Entrée = `BenchmarkResult`. |
| **`html/renderers/`** | 37 | **8 167** | Le **gros morceau**. Chaque renderer = `build_*_html(...) → str`. 4 signatures (§1.4-A). 7-8 domaines (§1.5). |
| **`html/renderers/charts/`** | 8 | **1 056** | Graphiques **SVG/HTML côté serveur** (radar, venn, cer_distribution, confusion_unicode, correlation, wilcoxon, `_svg` helpers). Déterministes. |
| **`html/views/`** | 6 | **1 053** | **Orchestrateurs** : une *view* compose N *renderers* via lazy-import + shell `<details>` partagé (`_render_view_shell`). Masquage adaptatif corpus-wide. |
| **`_helpers/`** | 6 | **1 019** | `render_helpers`(422, coloration cellules) · `engine_palette`(183) · `engine_badges`(121) · `colors`(76) · `assets`(203, inline image+vendor JS) · `__init__`. |
| **`narrative/`** (+`detectors/`) | 12 | **2 162** | Moteur narratif (arbiter, registry, renderer, 20 détecteurs). **SUPPRIMÉ** (D2). Feuille (n'importe que `domain.facts`). |
| **`csv/`** | 2 | 131 | `CsvReportRenderer.render(RunResult)` → 1 ligne/(doc,vue,métrique). **Propre.** |
| **`json/`** | 2 | 114 | `JsonReportRenderer.render(RunResult)` → dict consolidé déterministe. **Propre.** |
| **`i18n/`** | 1 | 128 | `get_labels(lang)` ; **635 clés × 2 langues** (fr/en, **1 274 LOC json**). Importé par **`generator.py` seul**, puis threadé en `labels`. |
| **`glossary/`** | 1 | 60 | `load_glossary(lang)` ; **25 termes × 2** (**878 LOC yaml**). Consommé **côté template (UI)** uniquement, jamais par du Python. |
| **Assets** (`templates/`, `vendor/`) | — | — | **3 423 LOC JS** (`_app.js` 2 588 + routing/compare/tables/documents) · **2 948 LOC CSS** (`_styles.css` 2 735 + `_design_tokens` 213) · **1 117 LOC HTML/J2** (16 fichiers) · `chart.umd.min.js` 208 KB. |

## 1.2 LE fait décisif : deux chemins de rapport HTML parallèles (vérifié)

La source documente **elle-même** la dualité (`render.py:9-11`) :

| Chemin | Entrée | Moteur | Surface mobilisée | Statut |
|---|---|---|---|---|
| **Legacy** `generator.ReportGenerator` (`generator.py:137`) | **`BenchmarkResult`** | **Jinja2** (`base.html.j2`) | data-layer (ré-agrège) + 37 renderers + 6 views + charts SVG **+ Chart.js client** + narrative + snapshots + i18n + SPA JS/CSS | **chemin vivant** (CLI/web l'utilisent via conversion `RunResult→BenchmarkResult`) |
| **Propre** `render.HtmlReportRenderer` (`render.py:197`) | **`RunResult`** | **f-strings** (zéro Jinja2) | minimal, **lit `RunResult` direct**, **zéro ré-agrégation** | germe naissant (peu de sections) |
| **Propre** `csv` / `json` (`render.py:69/57`) | **`RunResult`** | stdlib | sérialisation déterministe verbatim | **déjà propres** |

**C'est exactement la ligne de partage du portage.** Le chemin `RunResult`-direct (`render`/`csv`/`json`) est le **germe** de Cinoc ; le chemin `BenchmarkResult` + data-layer + 37 renderers + Jinja2 + SPA est la **masse accrétée** à ne **pas** reporter en bloc. La conversion `RunResult→BenchmarkResult` (couche 6) **n'existe que pour nourrir les renderers legacy** (`ANALYSE_COUCHE_6.md` L62-65) → elle disparaît avec eux.

## 1.3 Consommateurs réels & couplages (grep hors `tests/`)

| Symbole `reports/` | Consommateur (couche) | Note |
|---|---|---|
| `html.generator.ReportGenerator` | `interfaces/cli/__init__.py:307,394`, `cli/_workflows.py:599`, `web/benchmark_utils.py:558` | chemin legacy ; reçoit un `BenchmarkResult` (converti depuis `RunResult`) |
| `html.comparison.compare_benchmarks` | `interfaces/cli/_workflows.py:850` | commande `compare` (lit du JSON de run) |
| `narrative.build_synthesis` | `interfaces/web/routers/synthesis.py:101` | **disparaît** (narratif supprimé) |
| `csv`/`json`/`render` (RunResult) | (peu câblé en prod — germe) | chemin propre |

**Couplage de couche** : `reports/` n'importe **que** des couches internes — `domain` (`evaluation_spec`, `run_manifest`), `evaluation` (`benchmark_result`, `statistics`, `metrics.*`, `views`), `pipeline` (`run_result.RunResult`/`PipelineResult`). **0 import `app.`/`interfaces.`** → direction saine, **à préserver** (en Cinoc, `RunResult` migrant en `evaluation/`, reports lira la couche 3, pas la 4).

## 1.4 Constats transverses durables (vérifiés dans le code)

| # | Constat | Preuve (file:line) |
|---|---|---|
| **A** | **4 signatures de renderers** (= la dette « pas d'interface commune »). `report` : `fn(report_data, labels)` (~25) · `engines` : `fn(engines, labels)` (~4) · `subkey` : `fn(report_data[k], labels)` (~5) · `custom` : multi-args exotiques gérés hors registre (~6, ex. `build_crosses_section_html(report_data, labels, divergence_html, oracle_html, …)`). | `section_registry.py:50,81` ; `build_standard_sections` **ignore** `custom` (`:338`), géré à la main dans `generator._build_section_html`. |
| **B** | **Data-layer ré-agrège l'évaluation** (recalcul à chaque rendu, pas une lecture). `statistics`(stats inférentielles), `pareto`(moyennes+fronts), `documents`(difficulté), `extra_metrics`(rare-token/taxo/coût). `engines`/`scatter` sont, eux, **lecture pure**. | `statistics.py:41` `for dr in report.document_results` + `:26` `friedman_test`/`nemenyi_posthoc` ; `pareto.py:66,104`. |
| **C** | **Renderers qui recalculent** au lieu d'afficher. | `crosses.py:537-551` (rebuild 4 scatters) ; `specialization.py:51-54` (`compute_specialization_matrix`) ; `worst_lines.py:169` (`compute_char_diff`) ; `documents_gallery.py:232` (re-normalise strates+badges). |
| **D** | **Narrative = feuille propre.** 2 162 LOC, n'importe que `domain.facts` ; 20 détecteurs ; **3 accroches** à couper. | `narrative/arbiter.py:24` ; hooks `generator.py:254`, `overview.html:43` (`{% include '_narrative_summary.html' %}`), `web/routers/synthesis.py`. |
| **E** | **DOUBLE moteur de graphiques** (tension/doublon). (1) **SVG serveur** dans `charts/*.py` (déterministe) **+** (2) **Chart.js client** : `chart.umd.min.js` (208 KB) inliné et **piloté par `_app.js:buildCharts()`**. ⚠️ **Chart.js est VIVANT** (agent corrigé). | `generator.py:246,275` (`_load_vendor_js("chart.umd.min.js")`) ; `base.html.j2:18` (`{{ chartjs_inline\|safe }}`) ; `_app.js:747` (`destroyChart`) ; `engines_table.html:16` (`buildCharts()`). |
| **F** | **« Rapport-application » (SPA), pas document factuel.** ~3 423 LOC JS (routing/drill-in/comparaison/tables) + ~2 948 LOC CSS. La suppression du narratif n'y change rien. | `_app.js` 2 588 LOC ; `_routing.js` 249 ; `_styles.css` 2 735. |
| **G** | **i18n threadée, pas dispersée.** Chargée **une fois** dans `generator.py`, passée en `labels: dict` à chaque renderer (qui ne connaît pas `i18n`). 635 clés × 2 langues. Glossary = **UI seule**, 0 conso Python. | `get_labels` importé par `generator.py` + `i18n/__init__` only. |
| **H** | **Snapshots de reproductibilité** embarqués (sain). 4 instantanés (pricing, glossary, normalization, environment) → `report_data["snapshots"]`, dégradables. Recoupe l'invariant `§12`. | `snapshot.py:69-249` ; `generator.py:239`. |
| **I** | **Docstrings/réfs périmées.** `__init__.py` promet `RunManifest`+`view_results` (faux) ; réfs « Sprint S22 », « 22 vues » (`render.py:12`). | `reports/__init__.py:11` ; `render.py:12`. |

## 1.5 Verdicts par fichier — **PROVISOIRE — à confirmer au build**

> Légende : **G** garder (concept ~tel quel) · **M** modifier (concept gardé, forme revue) · **C** changer de couche · **S** supprimer · **I** incrémental (rebâti à la tranche qui le consomme, pas avant).
> Principe directeur (`MIGRATION_COUCHE_3.md` §9) : le **cadre** du rapport est plein-scope **maintenant** ; le **contenu** (sections) grossit **au rythme des métriques** (couche 3). Donc la plupart des renderers ne sont **pas portés** : ils sont **rebâtis en sections incrémentales**.

### Orchestration `html/` (2 196 LOC)
| Fichier | LOC | Rôle vérifié | Verdict PROVISOIRE + raison |
|---|---:|---|---|
| `render.py` | 643 | `HtmlReportRenderer.render(RunResult)` (f-strings, lit direct) | **G (germe) + M** — c'est le **cadre** à garder ; le reshaper en **`Protocol Section`** typé. **Trim <400** (split frame/sections). |
| `csv/render.py` | 115 | `render(RunResult)` → lignes tidy | **G** — déjà propre, déterministe ; aligner sur l'API de sortie. |
| `json/render.py` | 100 | `render(RunResult)` → dict canonique | **G** — déjà propre. |
| `comparison.py` | 409 | `compare_benchmarks` (2 runs, JSON, Jinja2) | **M** — commande `compare` retenue (`CLAUDE.md` §8.4) ; **reconsommer 2 `RunResult`**, drop Jinja2 + format-dict flexible ; <400. |
| `snapshot.py` | 280 | 4 snapshots repro embarqués | **M / ABSORBER** — la repro vient du **`RunManifest`** (déjà `domain`) ; le rapport l'**affiche**. Pricing → lié à la métrique économie (incrémental). |
| `generator.py` | 458 | Orchestrateur **legacy** `BenchmarkResult` + Jinja2 + data-layer + narrative + 6 views custom | **S (tel quel)** — masse accrétée. Le **concept** « assembler des sections en 1 HTML autonome » est rebâti **minimalement** autour du `Protocol Section` consommant `RunResult`. |
| `section_registry.py` | 379 | Dispatch à **4 `arg_kind`** | **S** — remplacé par le **`Protocol Section` unique** (une seule signature). |
| `html/__init__.py` / `__init__.py` | 53 | façades | **M** — mince, zéro effet de bord. |

### Data-layer `html/data/` (1 614 LOC) — **S en bloc**
| Verdict | Raison |
|---|---|
| **SUPPRIMER les 9 fichiers** | Anti-pattern `CLAUDE.md` §8.3 : ré-agrège `evaluation/` à chaque rendu (§1.4-B). En Cinoc, **tout calcul vit en couche 3** (`evaluation/runner` écrit dans `RunResult`) ; le rapport **lit** `RunResult`. `engines.py`/`scatter.py` (lecture pure) : leur logique d'**accès** trivial est absorbée par les sections. |

### Renderers `html/renderers/` (37 fichiers, 8 167 LOC) — **rebâtis en sections INCRÉMENTALES**
> Verdict global : **ni « garder », ni « porter en bloc »**. Chaque renderer devient (ou non) une **section `Protocol Section`** lit-`RunResult`, **ajoutée quand sa métrique atterrit en couche 3** (axe surface). Regroupement durable (rôle vérifié) :

| Domaine | Renderers (LOC) | Tranche probable | Verdict |
|---|---|---|---|
| **Cadre/overview** | `overview`(302), `engines_table`(467), `documents_gallery`(381), `view_results`(262) | **squelette texte** (1ʳᵉ section) | **M→section** (overview/engines = la 1ʳᵉ section vraie) |
| **Inter-moteurs** | `crosses`(650), `inter_engine`(248), `specialization`(113) | épaississement texte (cross_engine) | **I** — à la métrique cross_engine |
| **Stats/diagnostics** | `engines_diagnostics`(203), `engines_stability`(171) (composites) | au fil des métriques | **M** — recomposés par le cadre, pas des « views » à part |
| **Philologie** | `philological`(602), `over_normalization`(141), `lexical_modernization`(114), `numerical_sequences`(149) | tranche philologie | **I** |
| **Taxonomie d'erreur** | `taxonomy_comparison`(238), `taxonomy_cooccurrence`(161), `taxonomy_intra_doc`(148) | tranche taxonomie | **I** |
| **Calibration/NER/rare** | `calibration`(330), `ner`(224), `rare_token_recall`(116), `readability`(127), `searchability`(103) | par métrique | **I** |
| **Économie/robustesse/longi** | `marginal_cost`(111), `throughput`(154), `incremental_comparison`(205), `robustness_projection`(252), `longitudinal`(167), `baseline`(242), `multirun_stability`(151), `error_absorption`(210), `image_predictive`(207) | tranches dédiées (longi = store tidy `adapters/storage`) | **I** |
| **Structure/pipeline** | `pipeline_dag`(319), `stratification`(190), `worst_lines`(178) | tranche structure / pipeline | **I** (worst_lines : vient d'`evaluation`, `MIGRATION_COUCHE_3.md` §11) |
| **Couplés à du mort/déplacé** | `difficulty`(51), `module_audit`(175), `levers`(295) | — | **S/I** — `difficulty` (métrique destinée à partir, couche 3) ; `levers`/`module_audit` (synthèse type-narrative / `module_policy` mort) → ne pas porter sans consommateur |

### Charts `html/renderers/charts/` (8 fichiers, 1 056 LOC)
| Verdict | Raison |
|---|---|
| **G (concept SVG serveur) + I** | SVG **côté serveur** = **déterministe** (invariant §12) + **autonome** (pas de CDN). À rebâtir par section, au besoin. `cer_distribution`/`confusion_unicode` viennent d'`evaluation` (`cdd_render`, `MIGRATION_COUCHE_3.md` §11). |
| **Chart.js client : S** | `chart.umd.min.js` (208 KB) + `_app.js:buildCharts()` = JS client **non déterministe**, « rapport-application ». Le SVG serveur **le remplace**. ⇒ supprime aussi l'essentiel du SPA (§1.4-F). |

### Views `html/views/` (6, 1 053 LOC), Helpers `_helpers/` (6, 1 019 LOC), i18n/glossary
| Fichier/groupe | Verdict PROVISOIRE + raison |
|---|---|
| `html/views/*` | **S (mécanisme) / M** — l'orchestration « view = N renderers + shell `<details>` + masquage adaptatif » est remplacée par le **cadre `Protocol Section`**. Le concept « masquer une section vide » est **gardé** (une section sans donnée → `None`). |
| `_helpers/{engine_palette,engine_badges,colors}` | **G (consolidé)** — identité couleur stable par moteur (utile au rapport). **Fusionner en 1 module <400**, sans le doublon de palettes. |
| `_helpers/render_helpers`(422) | **M** — coloration cellules/SVG ; **porter seulement les helpers utilisés** par les sections bâties ; <400. |
| `_helpers/assets`(203) | **M** — garder l'**inline image b64** (HTML autonome) ; **drop** le loader de vendor JS (Chart.js parti). |
| `i18n/` (635×2) | **S/perissable** — surface, pas enveloppe. Démarrer **mono-langue** (labels inline) ; réintroduire un registre fr/en **seulement si un consommateur le réclame** (« pas de conso = supprimé »). Ne pas porter **1 274 LOC** de labels d'avance. |
| `glossary/` (25×2) | **S** — 0 consommateur Python (UI seule). Réintroduire si une section le réclame. |
| `templates/` (JS/CSS) | **S majoritaire** — le SPA (routing/drill-in, 3 423 JS) contredit « document factuel ». Garder un **shell minimal** + style de tableaux ; pas de routeur SPA. *(Périssable mais fortement indiqué.)* |
| `narrative/` (12, 2 162) | **S total** (D2) — couper 3 accroches (§1.4-D). |

---

# PARTIE 2 — RÉORGANISATION CIBLE Cinoc (périssable — « à confirmer à la tranche »)

> ⚠️ Périssable : le contact du code amont (evaluation/pipeline/app non encore implémentés) corrigera ces formes. **On ne construit PAS `reports` de haut en bas** : le **cadre** naît au squelette ambulant, les **sections** se remplissent **une par une**, au rythme des métriques (`MIGRATION_COUCHE_3.md` §9).

## 2.1 Rôle de `reports` en Cinoc & les deux axes

`reports` est une **vue en lecture seule** d'un `RunResult` : il **n'agrège jamais**, **ne recalcule jamais** un score, **ne génère aucune prose** (anti-hallucination §12). Tout nombre est une fonction auditable de `RunResult`.

| Axe | Contenu `reports` | Quand |
|---|---|---|
| **Enveloppe (plein-scope, maintenant)** | **`Protocol Section` typé unique** (1 signature) ; consommation **directe de `RunResult`** ; **`ReportRenderer`** (Callable injecté par `app`) ; 1 format HTML autonome déterministe ; sorties `csv`/`json` alignées ; charts **SVG serveur** déterministes | conçu au squelette |
| **Surface (incrémentale, élaguée)** | les **sections** (overview → engines → CER → … → philologie/taxo/structure) ; ajoutées **une par métrique** ; `compare` ; longitudinal (store tidy) | une tranche à la fois |

## 2.2 Le cadre (enveloppe — à figer au squelette)

```
RunResult ──> [ ReportRenderer ]  (Callable injecté par app)
                    │
                    ├─ HTML  : assemble des Section (Protocol unique) en 1 page autonome
                    ├─ CSV   : lignes tidy (run, doc, vue, métrique, valeur, statut)
                    └─ JSON  : dict canonique déterministe
```
- **`Protocol Section`** (1 seule signature, ex. `render(result: RunResult, ctx) -> SectionHtml | None` ; `None` = pas de donnée → section masquée). **Remplace** les 4 `arg_kind` + le `section_registry`.
- **Pas de data-layer** : une section lit `RunResult` (qui porte déjà taxonomy/NER/calibration/structure par conception, `MIGRATION_COUCHE_3.md` §8).
- **Charts = SVG serveur** (déterministe, autonome) ; **aucun JS client de charting**, aucun CDN.

## 2.3 Où va chaque concept Picarones (table de transfert)

| Concept Picarones (`reports`) | Destination Cinoc | Note |
|---|---|---|
| `render.py` (cadre RunResult) | **`reports`** — cœur du `ReportRenderer` HTML | germe à reshaper en `Protocol Section` |
| `csv`/`json` (RunResult) | **`reports`** | déjà propres |
| `comparison.py` | **`reports`** (commande `compare`) | reconsomme 2 `RunResult` |
| 37 renderers + 6 views + charts | **`reports`** — **sections incrémentales** | 1 section/métrique, pas en bloc |
| `_helpers` couleur + assets(image) | **`reports`** (1 module consolidé <400) | drop vendor JS |
| `snapshot` (repro) | **lecture du `RunManifest`** (domain) | reports affiche, n'embarque pas |
| **`html/data/`** (ré-agrégation) | **`evaluation/runner`** (couche 3) | le calcul y vit déjà |
| **`generator` legacy + `section_registry` + Jinja2 + SPA JS/CSS + i18n d'office + glossary + narrative** | **SUPPRIMÉ** | masse accrétée / shim / surface spéculative |
| `ReportRenderer` (Callable, en `pipeline` chez Picarones) | frontière **`app`→`reports`** | app injecte ; placement corrigé |

## 2.4 Esquisse d'arborescence cible (à confirmer en codant)

```
cinoc/reports/
├── __init__.py        mince, zéro effet de bord, docstring vraie
├── section.py         Protocol Section (1 signature) + types SectionHtml
├── html.py            ReportRenderer HTML : assemble les Section → page autonome (<400)
├── sections/          1 fichier/section, ajouté à la tranche de sa métrique
│   └── overview.py    (1ʳᵉ section : overview/engines/CER — squelette)
├── charts.py          primitives SVG serveur déterministes (au besoin)
├── csv.py             sortie tidy (RunResult)
├── json.py            sortie canonique (RunResult)
├── compare.py         compare 2 RunResult
└── _style.py          CSS minimal inline + couleurs moteur consolidées (<400)
```
*(Tous <400 LOC. Pas de `data/`, pas de `section_registry`, pas de `narrative/`, pas de `i18n/` au départ, pas de vendor JS.)*

## 2.5 Apparition par tranches (≠ couche complète)

| Tranche (cf. `MIGRATION_COUCHE_3.md` §15) | Ce que `reports` matérialise |
|---|---|
| **1. Squelette `demo`** (corpus pré-calculé → 1 CER → `RunResult`) | `Protocol Section` + `html.py` + **1 section** (overview/engines/CER), sur le **cadre définitif**. Prouve que le cadre tient. |
| **2. Épaississement texte** (WER/MER, cross_engine, `compare`) | + sections engines/cross + `compare.py` ; charts SVG au besoin |
| **3. Tranche structure** | + section structure (region/line/reading_order) lit `RunResult` |
| **4. Longitudinal / économie / philologie / taxo** | + 1 section par métrique, store tidy via `adapters/storage` |

## 2.6 Les 5 garde-fous appliqués

1. **Rupture nette, zéro shim** : 1 seul format d'entrée (`RunResult`) ; **pas** de `BenchmarkResult`, **pas** de data-layer de ré-agrégation, **pas** de double chemin `generator`/`render`.
2. **Budgets <400** : `render`(643)/`crosses`(650)/`philological`(602)/`engines_table`(467) **doivent** être splittés ; une section = un fichier court.
3. **Pas de consommateur = supprimé** : narrative, glossary, i18n d'office, Chart.js vendor, SPA JS, renderers de métriques non encore portées → **non créés** tant que la métrique n'existe pas.
4. **Tests d'archi jour 1** : `layer-deps` (`reports` n'importe que `domain`+`evaluation`+stdlib+`jinja2?`/aucun moteur) ; `no-side-effect-import` ; `file-budgets` ; **golden HTML déterministe** (même `RunResult` → mêmes octets).
5. **Une section = entière, en budget, en élaguant** : ajoutée avec sa métrique, testée, sans annotation de sprint.

## 2.7 Contrat de câblage métrique↔section & interactivité (enveloppe — périssable)

> Encode le correctif des **deux pires erreurs de Picarones** (métriques déconnectées ; rapport en avance sur sa donnée). À confirmer à S1.

**A. Câblage — rend la déconnexion *impossible*, pas juste déconseillée :**
- La **`Section` déclare ses `requires`** (les clés de `RunResult` qu'elle consomme).
- **Test no-orphan-métrique** : toute clé écrite dans `RunResult` est consommée par ≥1 section (ou listée « data-only ») → détecte « calculée mais non affichée » (= « pas de conso = supprimé » à la frontière rapport).
- **Test no-orphan-section** : tout `requires` pointe vers une métrique réellement enregistrée → détecte « section pour une métrique morte/inexistante ».
- **Masquage adaptatif** : donnée absente *pour ce run* → la section rend `None` (pas une erreur). Distingue « ce run n'a pas la donnée » de « la métrique n'existe pas ».

**B. Interactivité (what-if) — feature tardive, mécanisme à trancher à sa tranche :**
- **Invariant non négociable** : le rapport **ne re-mesure jamais** (anti-hallucination §12). Toute interactivité = **sélection / ré-agrégation** de données **déjà calculées en couche 3** ; jamais un détecteur ou une métrique relancés côté client. Curseur (ex. seuil d'hallucination) = un **`WHERE`** sur des docs déjà mesurés.
- **Descriptif** (moyenne/médiane/taux + support) ré-agrégeable ; **inférentiel** (Wilcoxon/Friedman/IC) → **gelé** sur le corpus complet (re-filtrer = re-mesure + 2ᵉ implémentation de scipy).
- **Mécanisme = QUESTION OUVERTE** (pas de consommateur aujourd'hui → on ne le fige pas, `CLAUDE.md` §9) : **(a, recommandé)** le **runner pré-calcule** les états what-if (`EvaluationView` dédiées) → le rapport **sélectionne**, **zéro calcul client** (marche générique *et* custom) ; **(b)** ré-agrégation côté client (micro-JS déterministe inliné) sur les valeurs par-doc (continu, mais 2ᵉ implémentation à golden-tester, agrégateurs simples). `RunResult` **porte déjà les résultats par-doc** → pas de changement d'enveloppe forcé. → **`MIGRATION_COUCHE_3.md §8`** (décision au build).

---

# PARTIE 3 — RISQUES DE TRANSFERT & DETTES (+ détection)

| # | Risque / dette | Détection | Désamorçage |
|---|---|---|---|
| **R1** | **Reporter le chemin `BenchmarkResult`** (les 37 renderers + data-layer) « pour aller vite » | `test_no_legacy_imports` (interdire `benchmark_result`, `build_report_data`) ; revue : toute section lit `RunResult` | rebâtir **section par section** sur `RunResult` ; 0 data-layer |
| **R2** | **Recréer une data-layer** qui recalcule (stats/pareto/difficulté) dans `reports` | `test_layer_deps` : `reports` n'appelle **pas** `evaluation.statistics`/`metrics.*` pour **calculer** ; revue « lit, ne calcule pas » | tout calcul en `evaluation/runner` → écrit dans `RunResult` ; reports lit |
| **R3** | **Réintroduire les 4 signatures** / un `section_registry` | revue : **1 seule** signature `Protocol Section` ; grep `arg_kind` | `Protocol` unique, implémenté directement |
| **R4** | **Bâtir toutes les sections d'avance** (rapport en avance sur ses données) | « pas de conso = supprimé » ; chaque section a une métrique réelle en CI | 1 section/métrique, à sa tranche |
| **R5** | **JS client non déterministe** (Chart.js, SPA routing) qui casse le golden octet-stable | golden HTML byte-stable ; grep `chart.umd`/`buildCharts`/CDN | charts **SVG serveur** ; pas de routeur SPA ; HTML autonome |
| **R6** | **Prose générée / narratif** ressuscité | grep `narrative`/`synthesis`/`facts` ; invariant anti-hallucination | tous les nombres = fonction auditable de `RunResult` |
| **R7** | **i18n/glossary portés d'office** (1 274 + 878 LOC de data spéculative) | « pas de conso = supprimé » ; revue | mono-langue inline ; registre fr/en seulement sur demande réelle |
| **R8** | **Budgets explosés** (render 643, crosses 650, philological 602…) | `test_file_budgets` strict | 1 section = 1 fichier court ; split aux coutures |
| **R9** | **Clés de métrique** changées → sections/CSV/JS cassés | contrat dur (`MIGRATION_COUCHE_3.md` §3.9, §12.3) ; golden | renommer un fichier = libre ; **renommer une clé = interdit** |
| **R10** | **Couplage de couche inversé** : `reports`→`app` (pour `ReportRenderer`) | `test_layer_deps` | `ReportRenderer` = Callable **injecté par `app`** ; `reports` ne connaît pas `app` |
| **R11** | **Repro perdue** : reports ré-embarque des snapshots au lieu de lire le `RunManifest` | golden `RunManifest` ; revue | reports **affiche** la repro portée par `RunManifest` (domain) |
| **R12** | **Docstrings/réfs périmées recopiées** (`Sprint S22`, « 22 vues », `RunManifest+view_results` faux) | grep anti-narration | « garder le pourquoi, jeter la datation » |
| **R13** | **Numérique non rétro-compatible** : normalisation Cinoc ≠ Picarones | goldens **refaits**, pas hérités | aucune « validation » par égalité de chiffres avec Picarones |
| **R14** | **Interactivité qui re-mesure** : un curseur relance un détecteur/une métrique côté client, ou un 2ᵉ agrégateur dérive de la vue canonique | revue anti-hallucination ; si option (b) ré-agrégation client : golden d'équivalence à plusieurs seuils | **candidat (a)** : runner pré-calcule les états what-if, le rapport **sélectionne** (zéro calcul client) ; sinon golden-tester l'équivalence (§2.7-B) |

---

## Résumé pour la session de CONSTRUCTION (3-5 points)

1. **La ligne de partage est DÉJÀ dans la source.** Picarones a **deux chemins** : `generator`(`BenchmarkResult`, Jinja2, data-layer, 37 renderers, SPA, narrative) = **masse accrétée à NE PAS porter** ; `render`/`csv`/`json`(`RunResult` direct) = **germe à garder**. Cinoc garde le **cadre** du chemin propre et rebâtit le **contenu** par sections. La conversion `RunResult→BenchmarkResult` (couche 6) **disparaît** avec les renderers legacy.
2. **Enveloppe à figer au squelette, plein-scope :** un **`Protocol Section` typé unique** (remplace les 4 `arg_kind` + `section_registry`), **consommation directe de `RunResult`** (zéro data-layer, zéro recalcul — tout calcul vit en `evaluation/runner`), **`ReportRenderer` injecté par `app`**, 1 HTML autonome **déterministe**. **Câblage métrique↔section** par `requires` + tests no-orphan (§2.7-A) → la déconnexion (erreur n°1 de Picarones) devient **impossible**. **Interactivité (what-if) = sélection, jamais re-mesure** (anti-hallucination) : feature tardive, **mécanisme non figé** — candidat = le runner pré-calcule les états what-if, le rapport *sélectionne* (§2.7-B) ; `RunResult` porte déjà les résultats par-doc → pas de changement d'enveloppe forcé.
3. **Surface incrémentale, jamais d'avance :** **1 section par métrique**, ajoutée quand la métrique atterrit en couche 3 (overview/CER au squelette, puis cross_engine/philologie/taxo/structure/longitudinal). Charts = **SVG côté serveur** (déterministe, autonome) ; **supprimer Chart.js + le SPA** (~3 400 LOC JS) — Cinoc est un **document factuel**, pas une application.
4. **Suppressions nettes :** `narrative/`(2 162 LOC, 3 accroches), `html/data/`(1 614, ré-agrégation), `section_registry`, `generator` legacy, vendor `chart.umd.min.js`, i18n/glossary d'office. « Pas de consommateur = supprimé », budgets <400 (render/crosses/philological/engines_table à splitter).
5. **Invariants à tenir :** `reports` **lit, ne calcule pas, ne narre pas** (anti-hallucination) ; **clés de métrique = contrat dur** avec les sections/CSV ; **golden HTML byte-stable** (déterminisme §12) ; la repro s'**affiche** depuis le `RunManifest`, ne se ré-embarque pas ; direction de couche `reports→{domain,evaluation}` seulement (jamais `app`/`interfaces`).

## DoD vivante (couche 7) — **autorité de détail** ; le `MIGRATION_PLAN.md` indexe

> **T9 (D-067)** : `cross_engine` rend les payloads `inference` (rangs moyens, CD Nemenyi, groupes indiscernables, IC bootstrap) en **lecture seule** (aucun recalcul — anti data-layer) ; `synthesis` applique la règle anti-contradiction (groupe Nemenyi sur la paire de tête → « égalité statistique » ; sinon « écart confirmé » ; sans post-hoc → p-value brute). Preuves : `tests/reports/test_cross_engine_section.py` · `test_synthesis_section.py`.
>
> **T10 (D-068)** : `+ sections/economics.py` (6ᵉ section du socle) — coûts/débits/Pareto/marginal en lecture seule du payload, avertissement de péremption explicite ; la **démo** filtre `usage` + `economics` avant rendu (canaux environnementaux) pour rester octet-stable. Preuves : `tests/reports/test_economics_section.py` · `tests/interfaces/test_cli_demo.py`.
>
> **T11 (D-069)** : `+ sections/diagnostics.py` (7ᵉ section du socle) — confusions, pires lignes (extraits verbatim **échappés**), documents difficiles ; lecture seule, déterministe (rendu dans la démo sans filtrage). Preuves : `tests/reports/test_diagnostics_section.py`.
>
> **T12 (D-070)** : `+ sections/calibration.py` (8ᵉ section) — ECE/MCE + table de fiabilité par bin, lecture seule. Preuves : `tests/reports/test_calibration_section.py`.
>
> **T13 (D-071)** : `+ sections/taxonomy.py` (9ᵉ section) — occurrences + parts par classe, lecture seule. Preuves : `tests/reports/test_taxonomy_section.py`.
>
> **S7.a (D-074)** : `+ csv_export.py` — export tableur en lecture pure du `RunResult`. Preuves : `tests/reports/test_csv_export.py`.

> **P5e 1 (D-275)** : « n notés / n attendus » à côté de tout agrégat incomplet (`_tables.coverage`, dans `bar_cell` — vue d'ensemble, comparaison — et dans les cellules des mesures clés), bloc **« Unités en échec »** dans la vue d'ensemble (motif localisé + message, règle `exclude`/`max_error` lue au manifeste) ; Wilcoxon suivi de ses cas complets, n du dot plot en fourchette quand les IC marginaux diffèrent ; CSV : colonnes `expected` (agrégats) et `outcome` (documents, `failed:<motif>`). FR/EN par `localized`. Preuves : `tests/app/test_unit_outcome.py::test_html_shows_scored_over_expected_and_the_reason`, `tests/reports/test_key_measures_section.py`, `tests/reports/test_csv_export.py`.

> **P5e 1b (D-276)** : la méthodologie affiche « Étape notée » / « Scored step » pour toute vue dont `target_step` est posée (rien pour une vue sans cible : rapport inchangé, démo octet pour octet). Preuve : `tests/app/test_step_target.py::test_report_says_which_step_a_view_scores`.

> **P5e 2 (D-277)** : bloc « Unités tronquées » / « Truncated units » dans la vue d'ensemble, à la suite des unités en échec (`failures_note` → `_failed_note` + `_truncated_note`) : unité, document, message (étape, plafond), et la règle — notées sur leur sortie réelle, `failure_policy` ne s'y applique pas. CSV : `outcome` = `truncated`. Composition : les réglages effectifs du manifeste s'y lisent, un réglage non transmis (`None`) s'écrit « — ». Preuves : `tests/adapters/llm/test_stop_reasons.py::{test_the_report_and_the_csv_show_the_truncation,test_the_composition_shows_the_effective_settings}`.

> **P5f 2 (D-279)** : méthodologie — « Modèles servis / Served models » et « Base Unicode / Unicode database » rejoignent les verrous dépliables (binaires, modules, dépendances). Composition : une valeur de plus de 60 caractères (le prompt, écrit désormais défaut compris) est abrégée, entière dans son infobulle. Preuves : `tests/reports/test_methodology_section.py::test_served_models_and_unicode_database_are_shown_in_both_languages`, `tests/reports/test_composition.py::test_a_long_setting_is_abbreviated_and_kept_whole_in_its_tooltip`.

> **S10b (D-282)** : la fiche moteur (« Configuration & reproductibilité » / « Configuration ») remplit **Paramètres / Parameters** avec les réglages effectifs du module (`manifest.adapter_kwargs`, même lecture que la composition : `composition.settings_html`, `label` masqué), puis ceux de l'étape ; « — » seulement quand il n'y en a aucun. Le libellé des motifs d'échec (`overview.REASON_LABELS`) sert aussi au bilan de `cinoc run`. Preuve : `tests/reports/test_engine_profile_section.py::test_profile_parameters_are_the_effective_module_settings`.

> **P5e 3, 4, 6 (D-283)** : mesures clés et significativité lisent le payload `inference` (`sections/_inference_text.py`, partagé : un libellé par test, motif et verdict). Mesures clés : « Friedman : p = …, corrigée de Holm sur m test(s) : … → différence (non) significative entre les k moteurs », puis les paires que Nemenyi sépare — ou « test non calculé : <motif> » ; la phrase « deux moteurs hors d'un même groupe = différence significative » est retirée. Tableau : colonnes Test · p brute · p (Holm) · n · verdict (sur la p corrigée) ; une ligne sans payload (JSON antérieur) dit « non corrigé ». Blocs de rangs en mode rapide (sans colonnes d'IC), post-hoc : paires significatives + barres CD chevauchantes, ou « post-hoc non effectué ». Glossaire `significance_p` aligné (FR/EN). Pas de diagramme CD en SVG : les barres sont écrites, pas dessinées (D-067 le gardait différé, aucun consommateur ne l'a demandé). Preuves : `tests/reports/test_cross_engine_section.py`, `tests/reports/test_key_measures_section.py::{test_three_engines_are_a_friedman_with_its_pairs,test_a_friedman_not_rejected_after_holm_says_so,test_test_not_computed_says_why}`.

> **P5e 5 (D-284)** : le bloc de rangs (`cross_engine`) met l'IC à côté de l'**agrégat (micro)** qu'il encadre (`PipelineInterval.value`, colonne « moyenne » retirée) ; le dot plot des mesures clés place le point sur le CER du tableau, légende « point = CER du tableau (micro : Σ erreurs / Σ caractères de référence), barre = son IC 95 % (bootstrap des documents) » ; la méthodologie ne dit plus « macro-moyennes par document, sauf mention micro » mais « agrégats par moteur **micro** : Σ (valeur × poids) / Σ poids… leur IC est un bootstrap de ce même ratio ; une moyenne des taux par document est nommée comme telle » — FR et EN. Preuves : `tests/reports/test_methodology_section.py::test_conventions_say_the_aggregate_is_micro_in_both_languages`, `test_cross_engine_section.py::{test_inference_block_renders_ranks_posthoc_and_intervals,test_renders_english_labels}`, `test_key_measures_section.py::test_dot_plot_with_ci_when_inference_present`.

> **P5e 7 (D-285)** : la convention est écrite **à côté du chiffre** — `sections/_profile_text.py` dérive la définition d'un profil de ses leviers (jamais une phrase tenue à la main), plus une phrase de comparabilité aux outils de référence ; mesures clés (sous chaque vue) et méthodologie (ligne « Normalisation » des seules vues texte) la lisent, FR/EN. **Une seule définition du CER** : le glossaire (points de code, après le profil de la vue, CER par ligne = même formule plafonnée à 1) ; la méthodologie y renvoie et dit le défaut et `null`. `cer_diplo` : l'écart CER − CER diplomatique isole ſ sous le défaut. Libellé de vue « Texte brut » → « Texte » / « Text » (+ « Texte (lignes) » / « Text (lines) »). Calibration : « pipeline · étape `ocr` », dernier bin « [0,9 ; 1,0] » (il s'écrivait « [0,9 ; 1,0[ »), glossaire ECE complété. — *preuve : `test_key_measures_section.py::test_the_convention_is_written_next_to_the_figure`, `test_methodology_section.py::test_view_profile_is_named_and_defined_text_views_only`, `test_calibration_section.py`*

> **P5e 11a (D-286)** : les pires lignes disent comment elles sont appariées (« appariées par alignement des lignes, comme la distribution par ligne ») et passent en FR/EN (titre, note, colonnes — les documents difficiles restent FR, jalon i18n) ; le flux de confusions dit qu'il montre « les substitutions que compte le CER » ; la prose de la taxonomie dit que chaque édition du WER reçoit une classe et une seule (omissions = suppressions, insertions = insertions, hors fusions/scissions). Le diff surligné (`text_diff.py`) reste sur `difflib` — affichage, hors des cinq. — *preuve : `test_diagnostics_section.py::test_worst_lines_say_how_lines_are_paired_in_both_languages`, `test_taxonomy_section.py::test_prose_says_the_classes_partition_the_wer_edits`*

> **P5e 11b (D-287)** : le diff surligné (`text_diff.char_diff`) aligne par `evaluation._alignment.opcodes` — l'alignement du CER — au lieu de `difflib` : chaque côté surligne exactement S + D (GT) et S + I (sortie) caractères ; des éditions contiguës forment un seul surlignage. Plus aucun `difflib` importé dans `cinoc/`. — *preuve : `tests/reports/test_text_diff.py` (« un un » lu « uaun » ; 150 couples `bnl_mini`, dont 34 où `difflib` surlignait plus que le CER — rouge prouvé)*

> **P5e 8 (D-288)** : glossaire FR/EN — `unanchored_trigrams` (limite : page dupliquée 0,021), `searchability` (« tolérance selon la longueur », échelle AUTO), `ner_f1` (empan, seuil dit convention de Cinoc) et `ner_f1_exact` (nom exact), `region_cer` (régions fantômes), `fca` (fiche nouvelle, titre « limitée : lignes fusionnées → 0 ») ; radar : axe `fca` nommé « FCA » (plus « Fidél. »), `unanchored_trigrams` = « Ancrage » ; économie : débit effectif étiqueté **simulation** (« hypothèse : 5 s par erreur caractère », en-tête et prose) ; méthodologie : la phrase sur les unités en échec suit `failure_policy` (`exclude` : exclu, « n notés / n attendus » ; `max_error` : erreur maximale, pondérée par la référence). — *preuve : `test_metric_renaming.py`, `test_glossary.py`, `test_economics_section.py`, `test_methodology_section.py` (FR et EN, rouge prouvé)*

> **P5e 9 (D-289)** : `metric_categories.py` lit catégorie et unité au registre (`evaluation.registry.metric_specs`) et les nomme FR/EN — marque `≈` (adaptée) / `∗` (exploratoire) en en-tête (`_tables.metric_th`, `overview`) et légende. **Mesures clés** : les seules établies de la vue (fin de `_HEADLINE`) + **durée par page** (Σ durées des unités produites / leur nombre ; note quand le run a une archive : une unité reprise garde sa durée d'origine — pilote D11). **Comparaison** : table des établies (triable, dispersion), puis table **Diagnostic** (adaptées puis exploratoires, super-en-tête par catégorie, sans tri ni test). **Significativité** : « seules les métriques établies sont testées ». **Radar supprimé** (`engine_radar.py`, `svg.radar_chart`, CSS) : retirés `char_accuracy`, `word_accuracy`, `bow_f1` et les exploratoires, il ne lui restait que `fca` et `searchability` — moins des 3 axes qu'il exige, donc plus aucun rendu. Glossaire : 9 fiches neuves (`char_accuracy`, `word_accuracy`, `bow_*`, `line_identity_*`, `reading_order_*`), champ `oracle` partout, la fiche affiche catégorie et unité du registre ; CSV : lignes `usage` (`duration_seconds`). Méthodologie : catégories et durées. Preuve : `tests/reports/test_metric_cards.py`, `test_key_measures_section.py`, `test_by_engine_section.py`, `test_glossary.py`, `test_csv_export.py`.

> **P5f 7 (D-292)** : Mesures clés — cellule s/page marquée ↺ quand le pipeline a une unité reprise ; la note sépare, par pipeline, durées mesurées par ce run et durées reprises (ou dit qu'aucune n'est mesurée) — remplace la note générique de S17. Économie — durée marquée ↺, note des unités reprises, pages facturées dans la base. CSV — `duration_seconds_first_run` pour une unité reprise. Méthodologie FR/EN. *Preuve : `tests/reports/test_key_measures_section.py`, `tests/app/test_resumed_units.py`.*

> **P5f 6 (D-293)** : Économie — la cellule « base » d'un pipeline auto-hébergé ajoute « auto-hébergé : <modèle> » / « self-hosted: <model> », et une note sous le tableau dit qu'aucun tarif de fournisseur n'est appliqué (FR/EN). *Preuve : `tests/reports/test_economics_section.py`, `tests/app/test_self_hosted_run.py`.*

> **S22 fin (D-294, P5f 8)** : Économie — les cellules « jetons in » / « jetons out » ajoutent sous le total les parties rendues (« dont N lus en cache, N écrits en cache » / « incl. N read from cache… », « dont N de raisonnement » / « incl. N reasoning ») — aucune colonne ni section nouvelle, rien quand le fournisseur ne les rend pas ; la cellule « base » d'un pipeline à jetons de cache non tarifés le dit dans la langue du rapport (« jetons de cache non tarifés : … » / « cache tokens not priced: … »). Preuve : `tests/reports/test_economics_section.py` (3 tests).

> **S27 (D-299)** : sous 720 px, `table.data` défile dans sa boîte (la page ne défile plus en largeur) ; le tableau de la section composition (`class="tbl"`, non stylé) rejoint la forme commune `.table-scroll` + `table.data`. — *preuves : `tests/reports/test_html.py::test_a_wide_table_scrolls_in_its_own_box_on_a_phone`, `test_composition.py::test_the_table_scrolls_inside_its_frame_on_a_narrow_screen` ; navigateur à 390 px (D-299)*

> **Refonte des contrats, tranche 1a (D-313)** : `_tables.format_value` rend un scalaire indéfini (statistique sans scalaire, `zero_denominator`) « indéfini » / « undefined » — distinct du « — » non mesuré — et, pour une exactitude **bornée à 0**, le taux d'erreur non tronqué et les comptes à côté (`(erreurs 4,4000 · 44/10)`, B1) ; NER : précision, rappel, F1 indéfinis → « indéfini » (catégorie seulement prédite, M3) ; bloc de rangs : « inférence non estimable » pour le micro d'un MER/cMER (B9c) ; méthodologie FR/EN réécrite (micro = comptes cumulés, plancher au corpus, comptes canoniques, `empty_page` remplace `max_error`) ; glossaire `char_accuracy`, `bow_f1`, `reading_order_tau` ; CSV : colonnes `statistic`, `scalar_reason`, `untruncated_error_rate`. Preuves : `tests/reports/test_tables.py::test_an_undefined_scalar_is_not_a_dash`, `::test_a_floored_accuracy_shows_its_untruncated_rate_and_counts`, `tests/reports/test_ner_section.py::test_a_predicted_only_category_reads_undefined_recall`, `tests/reports/test_cross_engine_section.py::test_a_hypothesis_denominator_micro_says_not_estimable`, `tests/reports/test_csv_export.py`, `tests/reports/test_methodology_section.py`.
> **Refonte des contrats, revue de 1a + 1b (D-313, `RunResult` v7)** : « publié » veut dire affiché (D7). Vue d'ensemble : la population cible et la pondération du macro (B3), et, là où elles diffèrent, les **deux qualités** avec leur couverture par motif. Comparaison des moteurs et mesures clés : lignes et points **triés selon le support global** publié, jamais selon les valeurs propres de chaque pipeline. Nouvelle section `paired_comparison` (groupe « Comparaison ») : supports par paire, support global, invention hors référence. Décisions : comptes **déclarés** par classes disjointes lus dans `PipelineResult.line_outcomes` (sans l'analyse `decisions`), refus et replis dans deux listes distinctes. `reports/sections/_alignment_note.py` écrit le chemin d'alignement à côté des confusions, de la taxonomie, des cartes de mots, de la fidélité, du bilan de correction et du diff ; sans `matches_canonical_counts`, aucune phrase ne les donne pour la décomposition des comptes canoniques (D8). Plus de « verdict » dans les textes livrés (glossaires, `i18n`, sections) ; les paires que Nemenyi sépare se lisent dans les barres CD (D11). Tous les consommateurs lisent `RunResult.principal_aggregate`, `compare.js` aussi (Q9). Preuves : `tests/adversarial/rapports/test_ce_revue_1ab_rapport.py`.
> **Refonte des contrats, tranche 1b (D-313)** : aucun verdict de test (rév. 7, § 2.1 d) — `_inference_text` (`is_significant` et `significant_pairs` retirés ; `exploratory_label`, `separated_pairs`), `cross_engine` (colonne « résultat », statut `exploratoire`, post-hoc : paires **séparées par la distance critique**) et `key_measures` (« résultat (exploratoire) » entre les k moteurs) n'écrivent ni « significatif » ni son contraire ; les p restent des nombres. `overview` : unités **partielles** et **tronquées** dites « non notées par défaut » (« notées sur leur sortie réelle » sous `empty_page`) ; méthodologie FR/EN : exclusion des sorties incomplètes, qualités conditionnelle/opérationnelle ; l'aide `cinoc` compte les unités partielles. Le rendu des deux qualités et de la couverture par motif reste à faire (le tableau montre la qualité principale et « n notés / n attendus »).

> Tri-état : `[x]` fait **+ preuve** · `[ ]` à faire · `[~]` différé/réserve + raison.
> Maj dans le **même commit** que le code. **Statut : ✅ T2** — cadre `Section` + assembleur autonome + sections **overview** & **cross_engine** + rapport de **comparaison** (deltas 2 runs) verts. **+ T7 `synthesis`** : section verdict factuel par vue (meilleur pipeline CER · Δ au suivant · significativité `cross_engine`), gatée `requires=("cer",)`, déterministe — **toutes les vues S4 au design désormais livrées**. Différé : importeurs cœur · longitudinal (T7), interactivité client-side.

**Enveloppe (cadre, plein-scope dès T1) :**
- [x] **`Protocol Section` unique** (1 signature `render(RunResult, ctx) → Html|None`, `requires` déclarés ; `Html` NewType anti-XSS) ; 0 registry. — *preuve : `reports/section.py` ; `isinstance(OverviewSection(), Section)`*
- [x] Consommation **directe de `RunResult`**, **zéro data-layer**. — *preuve : `test_reports_imports_are_allowed` (`reports → {domain, evaluation}`)*
- [x] `ReportRenderer` **injectable** (sections en paramètre ; `default_report_renderer` = socle). — *preuve : `test_renderer`*
- [ ] charts **SVG serveur** déterministes (pas de Chart.js/CDN). — *avec la 1ʳᵉ section graphique (T2+)*
- [x] **Rapport = artefact autonome** : HTML déterministe **sans backend ni CDN** (ouvrable hors-ligne) — y compris ses **polices incorporées en data-URI** (Fluxisch Else + OCR-A, S4.b.1a · `_style.font_face_css`), donc **aucune** ressource externe. — *preuve : `cinoc demo` (~227 Ko, octet-stable) + `test_cli_demo` + `test_renderer` (ni `@import`/`https`/`<link>`).* `[~]` interactivité client-side : avec les sections (surface).

**Garde-fous :**
- [x] `layer_dependencies` (`reports → {domain, evaluation}`) · **`no-orphan section↔métrique`** (le renderer saute les `requires` non couverts) · **golden HTML byte-stable** (2 runs identiques) · `file_budgets`. — *preuve : `test_renderer` (no-orphan + déterminisme) + suite archi*

**Validation inter-couches :** `MIGRATION_PLAN.md` §3-T1 (1 section overview/CER lit `RunResult` → HTML déterministe).

- [~] **Supprimé** : `narrative/` (D2) · `generator` legacy + `html/data/` + i18n/glossary d'office + Chart.js + SPA. **Différé** : 1 section/métrique à sa tranche (jamais en avance). **Interactivité what-if** = question ouverte (sélection, jamais re-mesure ; cf. §2.7).
- [x] **S28b (D-301)** : le CSS du rapport vit dans `reports/_assets/report.css` (une ligne par fragment, commentée ; lignes concaténées et commentaires retirés au chargement) — `html.py` 702 → 147 lignes, exemption de budget libérée, rapport **identique à l'octet** (démo comparée avant/après), toujours inliné (autonome ; `style-src 'unsafe-inline'`, aucune empreinte) ; `cinoc compare` FR/EN (`--lang`), décimales localisées, chaque côté nommé par son run, le **nom** de son fichier et son heure (D22).
- [x] **S34a (D-307)** : une vue sans aucun chiffre dit pourquoi (pas de vérité terrain, ou toutes ses unités en échec), FR/EN, au lieu d'un tableau d'en-têtes vide (`overview._unscored_note`). — *preuve : `test_no_ground_truth_says_why_the_table_is_empty`, `test_an_ocr_alto_no_longer_scores_against_itself`*
- [x] **S34b (D-308)** : `composition_diff` — ce qui distingue deux chaînes de même nom, lu au manifeste (brique, réglages, version) : `homonym_hints` écrit l'écart à côté du nom d'un homonyme (`engine_cell(hint=)`, classement, mesures clés, composition), `paired_differences` alimente l'avertissement de `render_comparison` (FR/EN) ; le test de significativité nomme sa vue quand le run en a plusieurs ; Fluxisch Else sans U+0027 (`unicode-range`) ; vignettes de galerie en `contain`. — *preuve : `tests/reports/test_composition_diff.py`, `test_each_test_names_the_view_it_judges`, `tests/interfaces/web/test_page_polish.py`*

### i18n FR/EN du rapport (D-136) — **R7 honorée : inline, sur demande réelle**

Mécanisme retenu = `html.localized(lang, fr, en)` (deux formulations adjacentes,
sélection `SectionContext.lang`, repli FR). **Pas** de registre/catalogue (le
« i18n d'office » de Picarones reste supprimé). Consommateur réel : route web
`?lang=en` → `renderer.render(lang="en")`. Conversion **par onglet, incrémentale** :

- [x] **Vue d'ensemble** : `overview` · `corpus_composition` · `synthesis` (D-136).
- [x] **Déjà bilingues** (dicts `_TEXT`, équivalents) : `word_errors` · `taxonomy`
  (profil) · `diagnostics` (flux). Migration vers `localized` opportuniste.
- [x] **Par moteur** : `dispersion`·`calibration`·`conformity` (D-138) ·
  `structured_data`·`lines`·`ner`·`economics` (D-139) ·
  `engine_profile`·`philology` (D-140) ·
  `by_engine`·`correction`·`textual_fidelity`·`taxonomy` (D-141) — **onglet clos (13/13)**.
- [x] **Par document** : `documents` · `gallery` · `by_document` · `image_quality`
  (D-137) · `document_detail` (D-138) — **onglet clos**.
- [x] **Croisements** : `cross_engine` (significativité/oracle/divergence) ✅ (D-142).
- [x] **Renderer** : `_SECTION_LABELS_EN` + aria-label des blocs bilingue ✅ (D-142).

**✅ Chantier i18n CLOS (D-142)** : tout le rapport (chrome + héros + 4 onglets +
toutes les sections + aria) est bilingue FR/EN via `SectionContext.lang` (route
web `?lang=en`), mécanisme unique `html.localized` inline (R7 honorée).

Convention : FR = défaut (tests FR inchangés) ; **+1 test EN par section convertie**.

---

*Tous les verdicts de la Partie 1.5 sont **PROVISOIRE — à confirmer au build** : le contact du code amont (evaluation/app non encore implémentés) prévaut.*
