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
    # Rév. n° 7 / tranche 1b : statut ``exploratory`` de l'inférence, chemin
    # d'alignement et concordance des confusions / taxonomie / diff (1295 LOC ;
    # les deux payloads de supports vivent à part, ``evaluation/comparison.py``).
    # Revue de 1a + 1b : chemin d'alignement de ``word_errors``, ``textual_
    # fidelity`` et ``correction`` (D8), classes déclarées du bilan des décisions
    # (D6) — moins le booléen de Nemenyi (D11) : 1316 LOC.
    "evaluation/analysis.py": 1350,
    # ``evaluate_run`` : les trois passes d'une vue (par document, agrégats,
    # inter-moteurs) et les supports forment un seul flux. Revue de 1a + 1b : la
    # famille de la vue (``declares_view``, D1) et les supports sur l'agrégat
    # principal (D10) y entrent (610 LOC).
    "evaluation/runner.py": 640,
    # Orchestrateur de run (couche 6) : la boucle de reprise, d'exécution
    # parallèle et d'assemblage déterministe forme un seul flux. Tranche 1b :
    # refus des vérités terrain absentes avant le premier appel, issues de
    # lignes et états d'étape portés par l'unité (605 LOC).
    "app/orchestrator.py": 700,
    # Helpers SVG **serveur** déterministes (un par type de graphe : dispersion,
    # Venn, barres, calibration, heatmap, radar, bulles, box plot, camembert,
    # haltère, colonnes groupées, bump). Cohésion d'un même contrat de rendu
    # (coords ``num`` octet-stables, accents passés par l'appelant) > éclatement ;
    # grandit d'un graphe à la fois (axe 2). Budget re-basé au courant (703 LOC)
    # + ~15 %.
    "reports/svg.py": 810,
}


#: Seuil de surveillance des assets front (JS/CSS) — plus bas que le Python : un
#: rapport/coquille autonome embarque ces fichiers, ils enflent en silence
#: (``test_file_budgets`` ne scannait QUE ``*.py``). Au-dessus, entrée justifiée.
ASSET_THRESHOLD = 500

#: Chemin relatif (depuis ``cinoc/``) → budget en lignes pour les assets front.
#: Budgets re-basés au courant + ~15 %. Cibles de réduction (Phase 3/6) : la
#: coquille tend vers « pas de SPA » — ``shell.css`` à surveiller. ``benchmark.js`` est
#: sorti de la table en S26 (786 → ~400 lignes : l'ancien composeur retiré, D-298).
ASSET_BUDGETS: dict[str, int] = {
    # CSS de la coquille web (design system inline auto-hébergé).
    "interfaces/web/static/css/shell.css": 1477,
    # Script du rapport autonome (enrichissement progressif, CSP-hashé).
    "reports/_assets/report.js": 714,
    # CSS du rapport autonome, sorti de ``reports/html.py`` (D-301 : il en
    # occupait ~580 lignes, l'exemption Python est libérée) ; inliné à la
    # génération. Une ligne par fragment, commentée : 576 lignes + ~15 %.
    "reports/_assets/report.css": 660,
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
