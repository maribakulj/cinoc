"""Garde-fou : la couche 8 (routeurs web) est du **transport mince**.

Un routeur de ``interfaces/web/routers/`` parse une requête, appelle un service
de la couche ``app`` (6) et renvoie une réponse. Il ne **construit pas** lui-même
les specs d'orchestration (``RunSpec``/``PipelineSpec``/``EvaluationView``…) :
assembler une spec est un acte de la couche ``app``, jamais d'une feuille de
transport. Le test d'``layer_dependencies`` autorise (légalement) ``interfaces``
à importer ``domain`` ; il ne capture donc pas cette fuite d'orchestration.

La construction des specs vit en couche ``app`` (``recipe_queue``, ``demo``) ;
les routeurs délèguent. Verrou de non-régression : ce test échoue si un routeur
se remet à fabriquer une spec d'orchestration.

Phase 5.2 : ``demo.py`` (constructeurs de specs de la démonstration) a été
déplacé de ``interfaces`` vers ``app`` — l'exemption temporaire est **levée**.
Plus aucune feuille de transport ne fabrique de spec.
"""

from __future__ import annotations

import ast
from pathlib import Path

INTERFACES = (
    Path(__file__).resolve().parents[2] / "cinoc" / "interfaces"
)

#: Constructeurs de specs d'orchestration : leur instanciation appartient à la
#: couche ``app`` (planification du run), pas à un routeur de transport.
_SPEC_CONSTRUCTORS = frozenset(
    {
        "RunSpec",
        "PipelineSpec",
        "PipelineStep",
        "EvaluationSpec",
        "EvaluationView",
        "ProjectionSpec",
    }
)


def _spec_constructions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if name in _SPEC_CONSTRUCTORS:
            found.append(f"{name}() L{node.lineno}")
    return found


def test_interfaces_do_not_build_orchestration_specs() -> None:
    """Aucune feuille de transport (``interfaces/**``) ne fabrique de spec
    d'orchestration (la planification de run vit en couche ``app``)."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(INTERFACES.rglob("*.py")):
        hits = _spec_constructions(path)
        if hits:
            offenders[str(path.relative_to(INTERFACES))] = hits
    assert not offenders, (
        "Construction de specs d'orchestration dans une feuille de transport "
        f"(doit vivre en couche app) : {offenders}"
    )
