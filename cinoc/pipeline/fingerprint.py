"""Empreinte d'une étape : **une seule** fonction pour la provenance et la reprise.

Ce qui détermine la sortie d'une étape, et rien d'autre :

- l'**étape** elle-même (``PipelineStep`` : brique, ``params``, types, câblage) ;
- l'**identité du module** qui l'exécute (:class:`ModuleIdentity`) : sa version
  déclarée, ses **réglages effectifs** — saisis, défauts compris, et toute
  configuration lue dans l'environnement qui change la cible (un endpoint) — et
  les **binaires système** qu'il enveloppe (tesseract) ;
- :data:`EXECUTION_VERSION`, pour ce que l'exécuteur ajoute hors des modules
  (fan-out, découpe des régions).

La version **du paquet** n'y entre pas : une correction de métrique ne change
aucune sortie d'inférence, et la mettre dans l'empreinte faisait re-payer toute
une campagne à chaque montée de version. Ce qu'elle remplace, c'est l'engagement
de chaque module à relever sa ``version`` quand sa sortie peut changer.

``ProvenanceRecord.parameters_hash`` **est** cette empreinte (estampillée par
l'exécuteur), et la clé d'unité du cache de reprise (couche 6) en **dérive** :
un haché des empreintes des étapes, de la forme du pipeline et du contenu de
l'image. Deux calculs séparés de « ce qui a produit cet artefact » avaient
divergé (la provenance ne hachait que ``params``, la clé ignorait les binaires) ;
il n'en reste qu'un.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from cinoc.domain.artifacts import compute_content_hash
from cinoc.domain.pipeline import PipelineStep

#: Version de ce que l'**exécuteur** fait d'une étape, hors du module : le
#: fan-out par région, la découpe des blocs, la résolution des entrées. À
#: relever quand ce code peut changer une sortie — comme un module relève la
#: sienne. (La version du paquet n'est pas ce signal : elle change à chaque
#: commit, métriques comprises.)
EXECUTION_VERSION = "1"


@dataclass(frozen=True)
class ModuleIdentity:
    """Ce qui, d'un module construit, détermine ses sorties.

    ``settings`` : réglages **effectifs**, sans valeur secrète (une clé tournée ne
    change aucune sortie, et l'empreinte voyage dans le nom d'un dossier
    d'archive). ``binaries`` : versions des binaires externes enveloppés.
    """

    version: str
    settings: Mapping[str, object] = field(default_factory=dict)
    binaries: Mapping[str, str] = field(default_factory=dict)


def canonical_json(payload: object) -> bytes:
    """JSON déterministe (clés triées, UTF-8) — la forme qu'on hache."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def step_fingerprint(step: PipelineStep, identity: ModuleIdentity) -> str:
    """Empreinte SHA-256 de ``step`` exécutée par un module d'``identity``."""
    return compute_content_hash(
        canonical_json(
            {
                "execution": EXECUTION_VERSION,
                "step": step.model_dump(mode="json"),
                "module": {
                    "version": identity.version,
                    "settings": dict(identity.settings),
                    "binaries": dict(identity.binaries),
                },
            }
        )
    )


__all__ = [
    "EXECUTION_VERSION",
    "ModuleIdentity",
    "canonical_json",
    "step_fingerprint",
]
