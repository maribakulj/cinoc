"""Garde-fou : chaque brique du socle **déclare** ses réglages, et la déclaration
dit vrai.

La déclaration (``PARAMS``, ``pipeline.params``) est la source unique de ce
qu'une spec peut poser : le registre refuse tout le reste. Elle n'a de valeur
que si elle colle au constructeur qui la reçoit — un réglage déclaré que le
constructeur ne prend pas ferait planter le run ; un défaut déclaré qui n'est pas
le sien mentirait dans ``cinoc list engines`` (et, demain, dans le formulaire).
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from cinoc.app.modules.registry import (
    ModuleRegistry,
    register_default_modules,
    socle_params,
)
from cinoc.pipeline.params import Param

#: Réglages que le **registre** traduit avant le constructeur — et qui ne sont
#: donc pas des paramètres de ``__init__``.
_TRADUITS = {"prompt_name"}


def _registre() -> ModuleRegistry:
    registre = ModuleRegistry()
    register_default_modules(registre)
    return registre


def _classe(kind: str) -> Any:
    from cinoc.app.modules.registry import _SOCLE, _load_class

    chemin = next(path for k, path, _ in _SOCLE if k == kind)
    return _load_class("cinoc.adapters." + chemin)


KINDS = _registre().kinds()


@pytest.mark.parametrize("kind", KINDS)
def test_every_socle_brick_declares_its_settings(kind: str) -> None:
    """``None`` est réservé aux modules tiers qui ne se prononcent pas."""
    assert socle_params(kind) is not None, f"{kind} : aucune déclaration PARAMS"


@pytest.mark.parametrize("kind", KINDS)
def test_the_declaration_matches_the_constructor(kind: str) -> None:
    params = socle_params(kind) or ()
    signature = inspect.signature(_classe(kind).__init__).parameters
    for param in params:
        if param.name in _TRADUITS:
            continue
        assert param.name in signature, (
            f"{kind} : {param.name!r} déclaré, mais le constructeur ne le prend pas"
        )
        defaut = signature[param.name].default
        if defaut is inspect.Parameter.empty:
            assert param.required, f"{kind} : {param.name!r} est requis au constructeur"
        elif not param.required:
            # (Requis malgré un défaut : la déclaration peut être plus stricte
            # — ``cli_layout`` refuse une commande vide, ``ocrd`` un processeur.)
            if kind != "pp_doclayout":  # son défaut vient de l'environnement
                assert param.default == defaut, (
                    f"{kind} : défaut déclaré {param.default!r} ≠ {defaut!r}"
                )


@pytest.mark.parametrize("kind", KINDS)
def test_the_registry_builds_the_declaring_class(kind: str) -> None:
    """``declared_by`` nomme la classe qu'on construit : sinon la déclaration
    lue sans construire serait celle d'une autre brique."""
    params = socle_params(kind) or ()
    sac: dict[str, Any] = {}
    for param in params:
        if param.required:
            sac[param.name] = {
                "label": "x",
                "source_label": "x",
                "model": "m",
                "endpoint": "https://exemple.test",
                "command": "outil {image} {out}",
                "processor": "ocrd-tesserocr-segment",
            }[param.name]
    for nom in (kind, f"{kind}:x"):
        try:
            module = _registre().build(nom, sac)
        except Exception:  # noqa: BLE001 — l'une des deux formes de nom suffit
            continue
        assert type(module) is _classe(kind)
        return
    pytest.fail(f"{kind} : ne se construit sous aucun nom")


def test_secrets_by_name_are_declared_secret() -> None:
    """La liste de noms ``SECRET_KWARGS`` n'est plus que le filet des modules
    tiers : une brique du socle qui prend un ``token`` le **déclare** secret."""
    from cinoc.app.run_manifest import SECRET_KWARGS

    oublis = [
        f"{kind}.{p.name}"
        for kind in KINDS
        for p in socle_params(kind) or ()
        if p.name in SECRET_KWARGS and not p.secret
    ]
    assert not oublis, oublis


def test_operational_settings_are_those_that_change_no_output() -> None:
    """Hors empreinte : un délai, le nom d'une variable de clé, un marqueur
    d'économie, la façon de nommer un prompt. Rien d'autre — un réglage de plus
    ici ferait relire une archive produite autrement."""
    hors_empreinte = {
        p.name
        for kind in KINDS
        for p in socle_params(kind) or ()
        if not p.affects_output
    }
    assert hors_empreinte == {"timeout", "api_key_env", "self_hosted", "prompt_name"}


def test_a_declared_param_is_well_formed() -> None:
    from cinoc.pipeline.params import ParamDeclarationError

    with pytest.raises(ParamDeclarationError):
        Param("psm", "int", "p", "p", default="6")
    with pytest.raises(ParamDeclarationError):
        Param("lang", "str", "l", "l", minimum=0)
    with pytest.raises(ParamDeclarationError):
        Param("mal nommé", "str", "x", "x")
