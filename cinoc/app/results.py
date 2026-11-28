"""Entrées/sorties JSON d'un ``RunResult`` (couche 6).

Sérialisation déterministe (Pydantic) pour **sauver** un run et le **comparer**
plus tard (``cinoc compare``). Aucun calcul ici — juste le round-trip.
"""

from __future__ import annotations

import json
from pathlib import Path

from cinoc.domain.errors import CinocError
from cinoc.evaluation.result import RENOTATION, RunResult


class RunResultError(CinocError):
    """Un fichier de résultat est illisible ou n'est pas un ``RunResult`` valide."""


def dump_run_result(result: RunResult, path: str | Path) -> None:
    """Écrit le ``RunResult`` en JSON (déterministe)."""
    Path(path).write_text(result.model_dump_json(indent=2), encoding="utf-8")


def load_run_result(path: str | Path) -> RunResult:
    """Charge un ``RunResult`` depuis un fichier JSON.

    Un JSON **sans** ``schema_version`` est refusé comme un JSON d'un schéma
    antérieur : le lire comme courant ferait passer pour des v7 des agrégats de
    sens antérieur (N10, rupture explicite).
    """
    try:
        brut = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(brut, dict) and "schema_version" not in brut:
            raise RunResultError(
                "RunResult sans schema_version : sa version est inconnue, le "
                f"fichier n'est ni relu ni converti. {RENOTATION}"
            )
        return RunResult.model_validate(brut)
    except (OSError, ValueError) as exc:  # ValidationError et JSONDecodeError
        raise RunResultError(f"RunResult illisible : {exc}.") from exc


__all__ = ["RunResultError", "dump_run_result", "load_run_result"]
