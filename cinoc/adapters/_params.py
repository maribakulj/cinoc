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


__all__ = ["TIMEOUT_MAX", "label_param", "model_param", "timeout_param"]
