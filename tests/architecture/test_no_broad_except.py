"""Interdiction d'un ``except`` **large qui avale** (CLAUDE.md §7).

La règle CLAUDE.md est : « Jamais ``except Exception: pass`` ; toujours
``logger.warning`` **et** ne pas masquer ». L'ancienne version de ce garde-fou ne
flaggait que la forme la **plus littérale** : un corps valant exactement
``pass``. Elle laissait passer ``except Exception: return ()`` et
``except Exception: log(...)`` (avalage sans re-lever), qui sont la même faute.

Règle élargie (Phase 1) : un handler **large** (``except:``, ``except Exception``
ou ``except BaseException``) est un *avaleur* si son corps **ne contient aucun
``raise``** (re-lève) — qu'il finisse par ``pass``, ``return`` ou un simple
``log``. Les avaleurs **légitimes** (worker daemon best-effort, chargement de
plugin tiers) sont nommés dans une **allowlist temporaire** par fichier : verte
aujourd'hui, elle bloque toute **nouvelle** occurrence ailleurs.

Allowlist des avaleurs **légitimes** (chacun trace et continue ; aucun n'est un
``pass`` muet). Tous revus en Phase 6 — résolus, pas pendants :
- ``app/modules/discovery.py`` / ``app/jobs.py`` : worker daemon / sink
  best-effort qui ne doit pas mourir ou faire échouer un run réussi en silence ;
(``adapters/llm/mistral.py`` en est sorti en S22 : sa liste de modèles traduit
toute erreur du SDK en ``ModelListingError`` — elle la **re-lève**, nommée.)
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "cinoc"

#: Avaleurs larges **légitimes** (best-effort qui trace et continue ; cf. module
#: docstring pour la justification par fichier). Bloque toute NOUVELLE occurrence.
_ALLOWLIST = frozenset(
    {
        "app/modules/discovery.py",
        "app/jobs.py",
    }
)


def _is_broad(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    if t is None:  # ``except:`` nu
        return True
    return isinstance(t, ast.Name) and t.id in {"Exception", "BaseException"}


def _reraises(handler: ast.ExceptHandler) -> bool:
    return any(isinstance(node, ast.Raise) for node in ast.walk(handler))


def _swallowing_handlers(tree: ast.AST) -> list[int]:
    """Lignes des handlers larges dont le corps ne re-lève jamais."""
    return [
        handler.lineno
        for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler)
        and _is_broad(handler)
        and not _reraises(handler)
    ]


def test_no_broad_swallowing_except() -> None:
    offenders: dict[str, list[int]] = {}
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in _ALLOWLIST:
            continue
        lines = _swallowing_handlers(ast.parse(path.read_text(encoding="utf-8")))
        if lines:
            offenders[rel] = lines
    assert not offenders, (
        "`except` large qui avale (sans re-lever) interdit hors allowlist — "
        f"trace et re-lève, ou narrow le type : {offenders}"
    )


def test_allowlist_entries_still_swallow() -> None:
    """Anti-pourriture : une entrée d'allowlist qui ne contient plus d'avaleur
    large doit être retirée (sinon l'allowlist se fossilise)."""
    stale = [
        rel
        for rel in _ALLOWLIST
        if not _swallowing_handlers(
            ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        )
    ]
    assert not stale, f"Entrées d'allowlist devenues inutiles (à retirer) : {stale}"
