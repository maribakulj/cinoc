"""Ce qui distingue deux chaînes **de même nom** (couche 7).

Un nom de pipeline dit ses briques, pas ses réglages : ``ocr_simple ·
tesseract`` en ``lang=eng`` et en ``lang=fra`` portent le même nom d'un run à
l'autre, et ``tesseract`` / ``tesseract #2`` dans un même run. La règle de
nommage ne change pas — le nom entre dans la clé d'archive, le changer ferait
ré-exécuter les archives ; ce module **dit** la différence, là où on lit les
noms.

Tout vient du ``RunManifest`` — ``pipeline_specs``, ``adapter_kwargs``,
``module_versions`` —, rien n'est deviné. Le manifeste ne sépare pas les
réglages d'exploitation (un délai, un hôte) de ceux qui changent la sortie : ils
sont nommés aussi, et c'est au lecteur de juger ; ``label`` et ``source_label``,
qui ne nomment que des fichiers, sont tus (comme dans la section composition).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from cinoc.domain.run import RunManifest

#: Réglages qui ne nomment que des fichiers du workspace (cf. ``composition``).
_BRUIT = frozenset({"label", "source_label"})
#: Le suffixe ``#n`` que la file de recettes donne à un homonyme (D-298).
_HOMONYME = re.compile(r" #\d+$")
#: Champs d'une étape qui ne sont pas des réglages.
BRICK = "@brick"
VERSION = "@version"


@dataclass(frozen=True)
class SettingDifference:
    """Un champ d'une étape qui n'a pas la même valeur des deux côtés.

    ``field`` : un réglage (``lang``), ou :data:`BRICK` (la brique employée),
    ou :data:`VERSION` (sa version déclarée). ``None`` = absent de ce côté."""

    step: str
    field: str
    value_a: str | None
    value_b: str | None

    def label(self) -> str:
        """``ocr.lang`` — la forme de ``--set`` ; ``ocr`` pour la brique,
        ``ocr (version)`` pour sa version."""
        if self.field == BRICK:
            return self.step
        if self.field == VERSION:
            return f"{self.step} (version)"
        return f"{self.step}.{self.field}"


def composition(manifest: RunManifest, pipeline: str) -> dict[tuple[str, str], str]:
    """``{(étape, champ): valeur}`` d'une chaîne du manifeste ; vide si absente."""
    spec = next((p for p in manifest.pipeline_specs if p.name == pipeline), None)
    if spec is None:
        return {}
    champs: dict[tuple[str, str], str] = {}
    for step in spec.steps:
        champs[(step.id, BRICK)] = step.adapter_name.split(":", 1)[0]
        version = manifest.module_versions.get(step.adapter_name)
        if version is not None:
            champs[(step.id, VERSION)] = version
        reglages = {**step.params, **manifest.adapter_kwargs.get(step.adapter_name, {})}
        for nom, valeur in reglages.items():
            if nom not in _BRUIT:
                champs[(step.id, nom)] = "—" if valeur is None else str(valeur)
    return champs


def _differences(
    a: dict[tuple[str, str], str], b: dict[tuple[str, str], str]
) -> tuple[SettingDifference, ...]:
    return tuple(
        SettingDifference(step, field, a.get((step, field)), b.get((step, field)))
        for step, field in sorted(set(a) | set(b))
        if a.get((step, field)) != b.get((step, field))
    )


@dataclass(frozen=True)
class PairedDifference:
    """Une chaîne appariée par son nom entre deux runs, qui n'a pas la même
    composition des deux côtés."""

    pipeline: str
    differences: tuple[SettingDifference, ...]


def paired_differences(
    manifest_a: RunManifest, manifest_b: RunManifest
) -> tuple[PairedDifference, ...]:
    """Les chaînes présentes **des deux côtés** sous le même nom et composées
    différemment — celles dont un delta mêle l'effet d'un réglage à celui du
    changement qu'on croit mesurer."""
    noms_b = {p.name for p in manifest_b.pipeline_specs}
    paires: list[PairedDifference] = []
    for nom in sorted({p.name for p in manifest_a.pipeline_specs} & noms_b):
        diff = _differences(composition(manifest_a, nom), composition(manifest_b, nom))
        if diff:
            paires.append(PairedDifference(nom, diff))
    return tuple(paires)


def homonym_hints(manifest: RunManifest) -> dict[str, str]:
    """``{pipeline: "ocr.lang=fra"}`` pour les chaînes d'un run qui ne se
    distinguent que par le suffixe ``#n`` : ce qui varie dans leur groupe.

    Vide pour une chaîne sans homonyme — son nom suffit."""
    groupes: dict[str, list[str]] = {}
    for spec in manifest.pipeline_specs:
        groupes.setdefault(_HOMONYME.sub("", spec.name), []).append(spec.name)
    hints: dict[str, str] = {}
    for membres in groupes.values():
        if len(membres) < 2:
            continue
        compos = {nom: composition(manifest, nom) for nom in membres}
        toutes = {k for c in compos.values() for k in c}
        cles = sorted(k for k in toutes if len({c.get(k) for c in compos.values()}) > 1)
        for nom in membres:
            hints[nom] = _hint(compos[nom], cles)
    return {nom: hint for nom, hint in hints.items() if hint}


def _hint(champs: dict[tuple[str, str], str], cles: Iterable[tuple[str, str]]) -> str:
    morceaux = []
    for step, field in cles:
        valeur = champs.get((step, field), "—")
        cle = SettingDifference(step, field, None, None).label()
        morceaux.append(f"{cle}={valeur}")
    return " · ".join(morceaux)


__all__ = [
    "PairedDifference",
    "SettingDifference",
    "homonym_hints",
    "paired_differences",
]
