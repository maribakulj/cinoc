"""Réglages **communs** aux briques du socle — une seule définition chacun.

Chaque brique déclare ses réglages (``PARAMS``, ``pipeline.params``). Ceux qui
reviennent partout — le libellé d'instance, le délai d'une étape, le modèle —
sont écrits ici une fois, pour qu'un même nom n'ait jamais deux libellés ni deux
sens selon la brique.
"""

from __future__ import annotations

from cinoc.pipeline.params import Param

#: Délai maximal d'une étape (s) — la borne de ``validate_timeout``.
TIMEOUT_MAX = 3600.0


def label_param() -> Param:
    """Le libellé d'instance : il forme le nom ``<kind>:<label>`` de la brique."""
    return Param(
        "label",
        "str",
        "Libellé d'instance (nom <brique>:<libellé>)",
        "Instance label (name <brick>:<label>)",
        required=True,
    )


def instance_label_param() -> Param:
    """Le libellé d'instance **facultatif** d'une brique qui se nomme par son
    kind : sans lui ``<kind>``, avec lui ``<kind>:<label>`` (:func:`instance_name`).

    Facultatif pour que les specs qui l'écrivaient nu gardent leur nom — donc
    leur empreinte. Il existe parce qu'une recette nomme **chaque** étape : deux
    étapes ``tesseract_layout`` (segmenter, puis lire chaque bloc) sont deux
    instances, et un nom ``tesseract_layout:seg`` que le module ne portait pas
    faisait refuser la recette à la construction.
    """
    return Param(
        "label",
        "str",
        "Libellé d'instance (facultatif : nom <brique>:<libellé>)",
        "Instance label (optional: name <brick>:<label>)",
    )


def instance_name(kind: str, label: str | None) -> str:
    """``<kind>`` sans libellé, ``<kind>:<label>`` avec — la convention du registre."""
    return f"{kind}:{label}" if label else kind


def timeout_param(default: float) -> Param:
    """Le délai d'une étape, retries compris — réglage d'**exploitation**.

    Hors de l'empreinte : il borne l'attente, il ne change aucune sortie
    produite. Le relever pour sauver une page n'a pas à faire réexécuter les
    pages déjà lues.
    """
    return Param(
        "timeout",
        "float",
        "Délai de l'étape (s, retries compris)",
        "Step time limit (s, retries included)",
        default=default,
        minimum=0.0,
        maximum=TIMEOUT_MAX,
        affects_output=False,
    )


def model_param(label_fr: str, label_en: str, *, default: str | None = None) -> Param:
    """Le modèle (un nom, un chemin de poids) — **requis** sans défaut."""
    return Param(
        "model", "str", label_fr, label_en, default=default, required=default is None
    )


__all__ = [
    "TIMEOUT_MAX",
    "instance_label_param",
    "instance_name",
    "label_param",
    "model_param",
    "timeout_param",
]
