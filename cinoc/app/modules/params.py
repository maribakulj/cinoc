"""Application de la déclaration ``PARAMS`` d'une brique (couche 6).

La déclaration vit sur la brique (``pipeline.params``) et ne fait que décrire ;
c'est ici qu'elle s'applique, **une fois**, pour les deux transports : le
registre la vérifie à chaque construction de module, donc à ``cinoc run``, à
``cinoc run --check`` et au dépôt d'une spec web — qui construisent tous trois
les modules par lui (``ModuleRegistry.build``).

Ce qui est refusé, et pourquoi on peut le refuser :

- un réglage **inconnu** (``tempreature``, un ``prompt_name`` posé sur un OCR) :
  personne ne le lirait, le run tournerait sans lui ; le message le nomme et
  propose le nom déclaré le plus proche ;
- un réglage **requis** absent ;
- une valeur d'un autre **type**, hors des **choix** ou des **bornes**.

Une brique **sans** déclaration (``PARAMS`` absent : un module tiers écrit avant
elle) n'est pas contrôlée — on ne refuse que ce qu'on peut réfuter (D-251).
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping

from cinoc.domain.errors import CinocError
from cinoc.pipeline.params import Param, value_matches


class ModuleResolutionError(CinocError):
    """``kind`` inconnu, kwargs invalides, ou nom construit incohérent."""


class ModuleSettingsError(ModuleResolutionError):
    """Un réglage d'``adapter_kwargs`` que la brique ne déclare pas, ou mal typé."""


def closest_hint(name: str, known: list[str]) -> str:
    """« — vouliez-vous 'x' ? » pour le nom connu le plus proche, sinon ``""``."""
    proche = difflib.get_close_matches(name, known, n=1, cutoff=0.6)
    return f" — vouliez-vous {proche[0]!r} ?" if proche else ""


def _check_value(adapter_name: str, param: Param, value: object) -> None:
    where = f"{adapter_name!r}, réglage {param.name!r}"
    if not value_matches(param.type, value):
        raise ModuleSettingsError(
            f"{where} : {param.type} attendu, reçu {value!r} "
            f"({type(value).__name__})."
        )
    if param.choices and value not in param.choices:
        raise ModuleSettingsError(
            f"{where} : {value!r} hors des choix "
            f"({', '.join(repr(c) for c in param.choices)})."
        )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if param.minimum is not None and value < param.minimum:
            raise ModuleSettingsError(f"{where} : {value} < {param.minimum:g}.")
        if param.maximum is not None and value > param.maximum:
            raise ModuleSettingsError(f"{where} : {value} > {param.maximum:g}.")


def check_settings(
    adapter_name: str, params: tuple[Param, ...], settings: Mapping[str, object]
) -> None:
    """Refuse, en le nommant, tout réglage que ``params`` ne déclare pas ou
    qu'il déclare autrement. Lève au **premier** manquement."""
    declared = {p.name: p for p in params}
    for name in sorted(settings):
        if name not in declared:
            accepted = sorted(declared)
            raise ModuleSettingsError(
                f"{adapter_name!r} : réglage inconnu {name!r}"
                f"{closest_hint(name, accepted) or '.'} Il ne serait lu par "
                "personne et le run tournerait sans lui. Réglages acceptés : "
                f"{', '.join(accepted) if accepted else 'aucun'}."
            )
    for param in params:
        if param.name not in settings:
            if param.required:
                raise ModuleSettingsError(
                    f"{adapter_name!r} : réglage {param.name!r} requis "
                    f"({param.label_fr})."
                )
            continue
        _check_value(adapter_name, param, settings[param.name])


def operational_names(params: tuple[Param, ...] | None) -> frozenset[str]:
    """Réglages d'**exploitation** (``affects_output=False``) : au manifeste,
    hors de l'empreinte de l'étape."""
    return frozenset(p.name for p in params or () if not p.affects_output)


def secret_names(params: tuple[Param, ...] | None) -> frozenset[str]:
    """Réglages **secrets** déclarés : jamais écrits, seul leur fait l'est."""
    return frozenset(p.name for p in params or () if p.secret)


__all__ = [
    "ModuleResolutionError",
    "ModuleSettingsError",
    "check_settings",
    "closest_hint",
    "operational_names",
    "secret_names",
]
