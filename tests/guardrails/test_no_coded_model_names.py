"""Aucun nom de modèle codé dans ``cinoc/`` (P5f 8, D-268, D-294).

Un modèle par défaut codé change de cible en silence le jour où le fournisseur
le retire ou le réaffecte — l'inverse de la reproductibilité. Les modèles se
**demandent** au fournisseur (``app.models.available_models``) et une spec
nomme le sien. Seule exception : ``evaluation/pricing.json``, une **donnée**
datée (aucune API ne publie de prix), indexée sur le modèle servi.

Ce qui est cherché : les noms de modèles des fournisseurs branchés, dans le
**code** — toute chaîne littérale d'un module Python qui n'est pas une
docstring, et tout fichier de données livré (gabarits, scripts du front,
recettes, prompts, profils). Les docstrings et les commentaires sont de la
documentation : un exemple (« ``gpt-4o-mini`` demandé, ``…-2024-07-18``
servi ») n'y fixe aucun comportement. Les cassettes de test vivent sous
``tests/``, hors du champ.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CINOC = Path(__file__).resolve().parents[2] / "cinoc"

#: Familles de modèles des fournisseurs branchés (OpenAI, Anthropic, Mistral,
#: et les modèles courants servis par Ollama ou un serveur OpenAI-compatible).
_MODEL_NAME = re.compile(
    r"\b(?:"
    r"gpt-[0-9][\w.\-]*|o[1-9](?:-mini|-pro|-preview)\b|chatgpt-[\w.\-]+"
    r"|claude-[a-z0-9][\w.\-]*"
    r"|(?:mistral|pixtral|magistral|codestral|ministral|devstral|voxtral)-[\w.\-]+"
    r"|(?:llama|qwen|gemma|phi|deepseek|granite|llava|minicpm)[0-9][\w.:\-]*"
    r")",
    re.IGNORECASE,
)

#: Données livrées : la seule table qui nomme des modèles, par construction.
_DATA_EXCEPTIONS = frozenset({"evaluation/pricing.json"})
_DATA_SUFFIXES = (".html", ".js", ".yaml", ".yml", ".txt", ".json")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ids.add(id(value))
    return ids


def _code_strings(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_nodes(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            found.extend((node.lineno, m) for m in _MODEL_NAME.findall(node.value))
    return found


def test_no_model_name_in_code() -> None:
    hits = [
        f"{path.relative_to(CINOC)}:{line}: {name}"
        for path in sorted(CINOC.rglob("*.py"))
        for line, name in _code_strings(path)
    ]
    assert not hits, (
        "nom de modèle codé (aucun défaut : la spec nomme son modèle, "
        "`available_models` liste ceux du fournisseur) :\n" + "\n".join(hits)
    )


def test_no_model_name_in_shipped_data() -> None:
    hits = []
    for path in sorted(CINOC.rglob("*")):
        rel = path.relative_to(CINOC).as_posix()
        if path.suffix not in _DATA_SUFFIXES or rel in _DATA_EXCEPTIONS:
            continue
        if "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            hits.extend(f"{rel}:{number}: {m}" for m in _MODEL_NAME.findall(line))
    assert not hits, "nom de modèle dans une donnée livrée :\n" + "\n".join(hits)


def test_the_guard_sees_a_coded_default(tmp_path: Path) -> None:
    """Le garde-fou voit ce qu'il doit voir — et pas les docstrings."""
    module = tmp_path / "m.py"
    module.write_text(
        '"""Exemple : gpt-4o-mini demandé."""\n'
        '_DEFAULT = "claude-haiku-4-5-20251001"\n'
        'def f():\n    """llama3 en exemple."""\n    return "mistral-small-latest"\n',
        encoding="utf-8",
    )
    assert [name for _, name in _code_strings(module)] == [
        "claude-haiku-4-5-20251001",
        "mistral-small-latest",
    ]
