"""Garde-fou contre la croissance silencieuse des fichiers (`CLAUDE.md` §5).

Tout fichier de ``cinoc/`` qui atteint le seuil doit avoir une entrée
**justifiée** dans :data:`FILE_BUDGETS`. Sinon le test échoue et force un choix
conscient :

1. **Refactor** pour rentrer sous le seuil (extraire un sous-module, élaguer).
2. **Relever le budget délibérément** : ajouter une entrée ici, justifiée dans le
   message de commit. La hausse devient un acte conscient, pas une dérive.

Cinoc démarre avec une table **vide** : aucun fichier ≥ 600 LOC aujourd'hui. La
table se remplira au fil des tranches, chaque entrée portant sa justification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CINOC = Path(__file__).resolve().parents[2] / "cinoc"

#: Seuil de surveillance. Sous ce seuil, la couverture suffit ; au-dessus, une
#: entrée justifiée est obligatoire. (Détendu de 400 → 600 : changement de règle.)
THRESHOLD = 600

#: Chemin relatif (depuis ``cinoc/``) → budget en lignes. Vide au démarrage.
FILE_BUDGETS: dict[str, int] = {
    # Hub des payloads ``analyses`` : une **union discriminée** unique (un
    # membre par famille de métriques) + ses sous-modèles. La cohésion du
    # contrat prime sur l'éclatement (CLAUDE.md §5.2) — on ne fragmente pas
    # ``AnalysisPayload``. Le fichier grandit **par construction** d'un membre
    # par famille (axe 2). Budget re-basé aux payloads **par document**
    # (``document_lines`` + ``document_taxonomy``, vue document recentrée :
    # 1102 LOC) + ~15 %.
    "evaluation/analysis.py": 1265,
    # CSS **inline** du rapport autonome : une chaîne `_CSS` unique (contrainte
    # d'autonomie — aucun fichier externe) + helpers d'assemblage. Cohésion du
    # design system > éclatement ; grandit avec les composants (axe 2). Budget
    # re-basé au courant (611 LOC, refonte mise en page R1→R5) + ~15 %.
    "reports/html.py": 730,
    # Planification de run **benchmark** (couche 6) : **source unique** des specs
    # texte à partir des choix UI/CLI — catalogue moteurs par rôle, profils de
    # métriques, vues d'évaluation par type de GT, composition des pipelines par
    # concurrent (OCR/zero-shot/chaîne LLM-VLM + étape NER optionnelle). La
    # planification de run **structure** (segmentation + hybride *autonome*
    # seg→reco→ALTO) vit dans ``app/structure_planning.py`` (extraite au seuil de
    # découpe). Ce fichier garde le **benchmark**, dont le mode **hybride comme
    # concurrent** (segmenteur → reconnaissance par bloc → texte scoré CER/WER,
    # comparé côte à côte avec un pipeline à plat) — concern benchmark, distinct
    # du run structure autonome. Budget re-basé au courant (~727 LOC) + ~5 %.
    "app/run_planning.py": 760,
    # Helpers SVG **serveur** déterministes (un par type de graphe : dispersion,
    # Venn, barres, calibration, heatmap, radar, bulles, box plot, camembert,
    # haltère, colonnes groupées, bump). Cohésion d'un même contrat de rendu
    # (coords ``num`` octet-stables, accents passés par l'appelant) > éclatement ;
    # grandit d'un graphe à la fois (axe 2). Budget re-basé au courant (703 LOC)
    # + ~15 %.
    "reports/svg.py": 810,
    # Catalogue des briques (couche 6) : **un builder par ``kind``**, chacun
    # court et indépendant — il traduit des ``adapter_kwargs`` en module et
    # refuse ce qui manque. C'est une table, pas un algorithme : l'éclater par
    # famille ajouterait de l'indirection sans rien rendre plus lisible, et
    # CLAUDE.md §5.2 tranche dans ce sens (« un fichier cohérent plutôt qu'une
    # floraison de petits modules éclatés »). Il grandit **par construction**
    # d'une brique à la fois (axe 2) — ``cli_layout`` puis ``ocrd`` l'ont fait
    # franchir le seuil. Budget re-basé au courant (613 LOC) + ~15 %.
    "app/modules/registry.py": 705,
}


#: Seuil de surveillance des assets front (JS/CSS) — plus bas que le Python : un
#: rapport/coquille autonome embarque ces fichiers, ils enflent en silence
#: (``test_file_budgets`` ne scannait QUE ``*.py``). Au-dessus, entrée justifiée.
ASSET_THRESHOLD = 500

#: Chemin relatif (depuis ``cinoc/``) → budget en lignes pour les assets front.
#: Budgets re-basés au courant + ~15 %. Cibles de réduction (Phase 3/6) : la
#: coquille tend vers « pas de SPA » — ``benchmark.js``/``shell.css`` à surveiller.
ASSET_BUDGETS: dict[str, int] = {
    # CSS de la coquille web (design system inline auto-hébergé).
    "interfaces/web/static/css/shell.css": 1477,
    # Script du composeur Banc d'essai (formulaire interactif) : + mode **hybride**
    # (segmenteur + reconnaisseur par bloc), **aperçu de mise en page** (lance une
    # segmentation et injecte le SVG des régions — remplace l'ancienne page
    # dédiée) et **post-correction structurée** (D-229 : seconde forme de run
    # lançable depuis la page).
    # Hausse **délibérée** 730 → 790 : la page sait démarrer deux formes de run,
    # pas une. Le dépassement a d'abord servi à **factoriser** — `launchAndFollow`
    # est désormais l'unique chemin « poster, gérer l'erreur, suivre en SSE,
    # rendre la main », partagé par les deux boutons (−15 LOC et une divergence
    # de moins). Ce qui reste est la surface propre de la capacité.
    # Re-basé au courant (~750 LOC) + ~5 %.
    "interfaces/web/static/js/benchmark.js": 790,
    # Script du rapport autonome (enrichissement progressif, CSP-hashé).
    "reports/_assets/report.js": 714,
}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


@pytest.mark.parametrize(("rel_path", "budget"), sorted(FILE_BUDGETS.items()))
def test_file_size_within_budget(rel_path: str, budget: int) -> None:
    path = CINOC / rel_path
    assert path.exists(), (
        f"Fichier disparu : {rel_path}. Retire l'entrée de FILE_BUDGETS."
    )
    actual = _line_count(path)
    assert actual <= budget, (
        f"\n{rel_path} a {actual} lignes (budget {budget}).\n"
        "Refactor pour rentrer dans le budget, ou relève-le consciemment ici "
        "avec une justification dans le message de commit."
    )


def test_no_orphaned_budget_entries() -> None:
    missing = [p for p in FILE_BUDGETS if not (CINOC / p).exists()]
    assert not missing, f"Entrées orphelines dans FILE_BUDGETS : {missing}."


@pytest.mark.parametrize(("rel_path", "budget"), sorted(ASSET_BUDGETS.items()))
def test_asset_size_within_budget(rel_path: str, budget: int) -> None:
    path = CINOC / rel_path
    assert path.exists(), (
        f"Asset disparu : {rel_path}. Retire l'entrée de ASSET_BUDGETS."
    )
    actual = _line_count(path)
    assert actual <= budget, (
        f"\n{rel_path} a {actual} lignes (budget {budget}).\n"
        "Refactor/élague, ou relève le budget consciemment dans ASSET_BUDGETS."
    )


def test_no_orphaned_asset_budget_entries() -> None:
    missing = [p for p in ASSET_BUDGETS if not (CINOC / p).exists()]
    assert not missing, f"Entrées orphelines dans ASSET_BUDGETS : {missing}."


def test_asset_budget_covers_all_large_assets() -> None:
    """Tout ``*.js``/``*.css`` ≥ ASSET_THRESHOLD doit avoir une entrée justifiée."""
    untracked: list[tuple[str, int]] = []
    for pattern in ("*.js", "*.css"):
        for path in CINOC.rglob(pattern):
            rel = path.relative_to(CINOC).as_posix()
            if rel in ASSET_BUDGETS:
                continue
            count = _line_count(path)
            if count >= ASSET_THRESHOLD:
                untracked.append((rel, count))
    assert not untracked, (
        f"\nAssets ≥ {ASSET_THRESHOLD} lignes non surveillés :\n"
        + "\n".join(f"  {p} ({n} lignes)" for p, n in sorted(untracked))
        + "\n\nAjoute-les à ASSET_BUDGETS (budget = current + ~15 %), ou splitte."
    )


def test_budget_table_covers_all_large_files() -> None:
    """Tout fichier ≥ THRESHOLD lignes doit avoir une entrée justifiée.

    Empêche un fichier nouveau ou subitement gros d'échapper à la surveillance.
    """
    untracked: list[tuple[str, int]] = []
    for path in CINOC.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(CINOC).as_posix()
        if rel in FILE_BUDGETS:
            continue
        count = _line_count(path)
        if count >= THRESHOLD:
            untracked.append((rel, count))
    assert not untracked, (
        f"\nFichiers ≥ {THRESHOLD} lignes non surveillés :\n"
        + "\n".join(f"  {p} ({n} lignes)" for p, n in sorted(untracked))
        + "\n\nAjoute-les à FILE_BUDGETS avec budget = current + ~15 %, "
        "ou splitte-les."
    )
