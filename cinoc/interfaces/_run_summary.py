"""Bilan des unités d'un run et code de sortie qu'il commande (couche 8).

Partagé par ``cinoc run`` et ``cinoc correct`` : les deux exécutent des unités
(pipeline × document), et un échec silencieux est le même défaut des deux côtés
— ``run`` perdait 19 unités sur 20 en sortant en code 0 (pilote D-281, D2,
corrigé en D-282) ; ``correct`` le faisait encore (reste de S10b, S20). Une
seule fonction, pas une copie.
"""

from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Sequence
from typing import TextIO

from cinoc.app.orchestrator import UnitProgress
from cinoc.evaluation.result import RunResult
from cinoc.reports.sections.overview import REASON_LABELS

#: Code de sortie d'une commande dont le rapport est écrit mais dont au moins
#: une unité (pipeline × document) a échoué. Distinct de ``1`` (rien n'a pu se
#: faire) : un script sait qu'il a un rapport, et qu'il est incomplet.
EXIT_UNITS_FAILED = 3


def unit_summary(results: Sequence[RunResult]) -> int:
    """Affiche le bilan des unités et rend le code de sortie : ``0`` si chaque
    unité a une sortie, ``EXIT_UNITS_FAILED`` si au moins une a échoué.

    Une unité **tronquée** a une sortie, notée : elle est comptée, pas en
    échec. Le bilan d'un succès va sur la sortie standard, celui d'un échec sur
    la sortie d'erreur, avec les motifs libellés comme au rapport.
    """
    units = [unit for result in results for unit in result.usage]
    failed = [unit for unit in units if unit.outcome == "failed"]
    truncated = sum(unit.outcome == "truncated" for unit in units)
    runs = f" sur {len(results)} runs" if len(results) > 1 else ""
    coupees = f", {truncated} tronquée(s)" if truncated else ""
    if not failed:
        print(f"Bilan : {len(units)} unité(s){runs}, aucune en échec{coupees}.")
        return 0
    motifs = Counter(REASON_LABELS[str(unit.reason)][0] for unit in failed)
    detail = ", ".join(f"{motif} : {n}" for motif, n in sorted(motifs.items()))
    print(
        f"Bilan : {len(failed)} unité(s) en échec / {len(units)}{runs} "
        f"({detail}){coupees} — le rapport les liste.",
        file=sys.stderr,
    )
    return EXIT_UNITS_FAILED


#: Issue d'une unité terminée, telle que la ligne de progression la dit.
_ISSUES = {
    "ok": "fait",
    "truncated": "tronquée",
    "failed": "échec",
    "resumed": "relue de l'archive",
}


def print_progress(unit: UnitProgress) -> None:
    """Une ligne par unité terminée, **sur la sortie d'erreur** (D-307).

    Le rappel est celui dont la vitrine tire sa barre (SSE) : un run de sept
    minutes ne reste plus muet en ligne de commande. La sortie standard reste
    celle qu'un script lit ; le bilan d'un échec, lui, détaille les motifs.
    """
    issue = _ISSUES.get(unit.outcome, unit.outcome)
    ligne = f"[{unit.done}/{unit.total}] {unit.pipeline} · {unit.document_id} — {issue}"
    print(console_safe(ligne, sys.stderr), file=sys.stderr, flush=True)


def console_safe(ligne: str, stream: TextIO) -> str:
    """``ligne`` telle que ``stream`` sait l'écrire : une console cp1252
    (Windows) n'a pas le « → » d'un nom de recette — il s'y écrirait
    échappé, ou lèverait —, la flèche ASCII se lit."""
    try:
        ligne.encode(getattr(stream, "encoding", None) or "utf-8")
    except (UnicodeEncodeError, LookupError):
        return ligne.replace("→", "->")
    return ligne


__all__ = ["EXIT_UNITS_FAILED", "console_safe", "print_progress", "unit_summary"]
