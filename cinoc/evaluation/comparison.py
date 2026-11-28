"""Supports apparié et global, « invention hors référence » (couche 3).

Trois supports (``CONTRATS.md`` § 2.1 c), tous **métrologiques** — ils disent
sur quoi porte un Δ ponctuel, un classement ou une couverture, sans test :

- **par pipeline** — D^μ_P et D^M_P : l'agrégat de ``evaluation.aggregation`` ;
- **apparié, par paire** — D^μ_AB = D^μ_A ∩ D^μ_B, D^M_AB = D^M ∩ D^μ_A ∩ D^μ_B :
  les Δ ponctuels et leurs p éventuelles ne se lisent que là ; deux pipelines
  ne s'ordonnent que sur leur support apparié ;
- **global, sur la famille** — l'intersection de tous : le **seul** tri
  multi-pipelines (B7) — les ordres appariés ne composent pas un classement.

D^M est fixé par la **référence** (tp + fn > 0, n_réf > 0), jamais par le
scalaire d'un pipeline : c'est le même support pour tous. Le macro ne voit donc
pas l'invention sur un document sans référence (N3) ; l'analyse
« invention hors référence » la rend visible, sur le support apparié de chaque
paire, avec la couverture des pages sans référence par pipeline.

Seules les observations **complètes** (axes 1 à 3 au vert) entrent ici : la
couverture dit ce qui manque. Ce module ne porte que les **modèles** (feuilles
de l'union ``AnalysisPayload``) ; leur calcul est dans ``evaluation.aggregation``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PairSupport(BaseModel):
    """Supports et valeurs d'une paire de pipelines sur une (vue × métrique)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: str = Field(min_length=1, max_length=128)
    b: str = Field(min_length=1, max_length=128)
    #: D^μ_AB, dans l'ordre du corpus.
    micro_documents: tuple[str, ...] = ()
    #: D^M_AB = D^M ∩ D^μ_AB.
    macro_documents: tuple[str, ...] = ()
    #: ``{pipeline : valeur sur ce support}`` — le micro (finalisation de la
    #: somme) et le macro (``None`` : métrique sans macro, ou D^M_AB vide).
    micro: dict[str, float | None] = Field(default_factory=dict)
    macro: dict[str, float | None] = Field(default_factory=dict)


class GlobalSupport(BaseModel):
    """Le support de **toute** la famille : celui du seul tri multi-pipelines."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    micro_documents: tuple[str, ...] = ()
    macro_documents: tuple[str, ...] = ()
    micro: dict[str, float | None] = Field(default_factory=dict)
    macro: dict[str, float | None] = Field(default_factory=dict)
    #: Les pipelines du meilleur au moins bon sur le micro du support global
    #: (vide : aucun document commun, ou aucune valeur définie).
    ranking: tuple[str, ...] = ()


class ComparisonPayload(BaseModel):
    """Supports apparié et global d'une (vue × métrique) — sans test."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["comparison"] = "comparison"
    metric: str = Field(min_length=1, max_length=128)
    pairs: tuple[PairSupport, ...] = ()
    global_support: GlobalSupport


class InventionPair(BaseModel):
    """L'invention de deux pipelines sur les pages sans référence qu'ils ont
    **tous deux** mesurées."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: str = Field(min_length=1, max_length=128)
    b: str = Field(min_length=1, max_length=128)
    documents: tuple[str, ...] = ()
    #: ``{pipeline : unités inventées}`` sur ``documents`` (vide : unité non
    #: définie).
    invented: dict[str, int] = Field(default_factory=dict)


class InventionPayload(BaseModel):
    """Invention **hors référence** (N3, C5) : ce que le macro ne voit pas.

    ``unit`` : ce qu'on compte — ``insertions`` (taux d'édition, exactitudes),
    ``false_positives`` (appariement) ; ``None`` = « non définie » : une
    proportion à dénominateur de référence ne compte aucune unité de
    l'hypothèse, elle est insensible à l'invention par construction.
    ``coverage`` : par pipeline, ``(mesurées, attendues)`` sur les pages sans
    référence — l'invention d'un pipeline qui échoue sur ces pages n'est pas
    comparable à celle d'un pipeline qui les lit.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["invention_outside_reference"] = "invention_outside_reference"
    metric: str = Field(min_length=1, max_length=128)
    unit: Literal["insertions", "false_positives"] | None = None
    pairs: tuple[InventionPair, ...] = ()
    coverage: dict[str, tuple[int, int]] = Field(default_factory=dict)


__all__ = [
    "ComparisonPayload",
    "GlobalSupport",
    "InventionPair",
    "InventionPayload",
    "PairSupport",
]
