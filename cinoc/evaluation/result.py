"""``RunResult`` — contrat de sortie **unique** d'un run (plein-scope, dégonflé).

Un seul format (pas de double représentation héritée). Dimensionné pour porter
toute métrique **scalaire** (texte/structure/NER/taxonomy…) et le détail
**par-document** dès sa conception, même quand seul un CER est écrit : ajouter
une métrique ou une vue est **additif**, jamais un changement d'enveloppe.
``schema_version`` couvre les évolutions structurelles ; les **clés** (``metric``,
``value``, ``support``, ``pipeline``, ``view``) sont un **contrat dur** avec le
rapport — renommer une clé est interdit (CLAUDE.md §12, déterminisme).

Contrat « analyses » (enveloppe, cf. ``PLAN_PARITE.md`` §1/E2) : les résultats
**non scalaires** (inférentiel, fronts de Pareto, paires de confusion, bins de
calibration…) passent par le canal unique ``RunResult.analyses`` — payloads
Pydantic figés (``evaluation.analysis``), **union discriminée par ``kind``**.
Règles dures : (1) les scalaires ``MetricScore`` restent la seule monnaie de
classement/historique ; (2) tout est calculé en ``evaluation/`` et écrit ici,
les rapports lisent sans recalculer ; (3) chaque payload naît **avec** son
calcul et son consommateur (même commit) — garde-fou « pas de consommateur =
supprimé ».
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cinoc.domain.run import RunManifest
from cinoc.domain.usage import FailureReason, ResourceUsage, UnitOutcome
from cinoc.evaluation.analysis import Analysis


class MetricScore(BaseModel):
    """Valeur d'une métrique (agrégat ou par-doc). ``None`` = non applicable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = Field(min_length=1, max_length=128)
    value: float | None = None
    #: « Poids de preuve » de ``value`` : par-document = le **dénominateur** de la
    #: métrique (longueur de réf…), qui pondère le micro-agrégat ; en agrégat = le
    #: **nombre de documents** applicables. Deux lectures, même intention (taille).
    support: int | None = Field(default=None, ge=0)
    #: **Agrégat seulement** — « n attendus » à côté de ``support`` (« n notés ») :
    #: les documents notés **plus** les unités en échec qui auraient pu l'être
    #: (vérité terrain présente pour cette métrique). L'écart entre les deux est
    #: exactement ce que la politique d'échec a retiré de la moyenne ; ses motifs
    #: sont dans ``RunResult.usage``. ``None`` par-document, et pour un résultat
    #: antérieur au schéma 3.
    expected: int | None = Field(default=None, ge=0)


class RunDocumentResult(BaseModel):
    """Scores d'un pipeline sur un document, sous une vue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    pipeline: str = Field(min_length=1, max_length=128)
    view: str = Field(min_length=1, max_length=128)
    scores: tuple[MetricScore, ...] = Field(default_factory=tuple)
    #: Strate du document (genre/période…) si le corpus la porte, sinon ``None``.
    #: Projection de ``DocumentRef.metadata["stratum"]`` ; consommée par la
    #: composition / filtres / CER par strate (rendus seulement si présent).
    stratum: str | None = Field(default=None, max_length=128)
    #: **Référence** image du document (chemin corpus-relatif ou URL IIIF),
    #: jamais les octets → déterminisme/hash du résultat intacts. Résolue en
    #: vignette **au rendu** (adapter, hors résultat). ``None`` = pas d'image.
    image_ref: str | None = Field(default=None, max_length=2048)


class PipelineResult(BaseModel):
    """Agrégat d'un pipeline sous une vue (moyennes ``None``-exclues + support)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    view: str = Field(min_length=1, max_length=128)
    aggregate: tuple[MetricScore, ...] = Field(default_factory=tuple)


class DocumentUsage(BaseModel):
    """Enregistrement d'une unité (pipeline × document) : issue + ressources.

    L'exécution a lieu une fois par (pipeline × document) — les vues sont des
    lentilles d'évaluation, sans coût d'exécution propre. Les durées sont du
    wall-clock (mesure d'environnement, comme les horodatages du manifeste).

    ``outcome`` (``ok`` · ``truncated`` · ``failed``) est l'issue **produite par
    l'exécution** (``DocumentExecution``) et transportée telle quelle : une unité
    en échec a sa ligne, avec son motif codé (``reason``) et son message — c'est
    ce qui distingue un échec d'une absence. Une unité en échec n'a pas de
    consommation mesurée (``usage`` vide).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    pipeline: str = Field(min_length=1, max_length=128)
    usage: ResourceUsage
    outcome: UnitOutcome = "ok"
    reason: FailureReason | None = None
    message: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _reason_iff_failed(self) -> Self:
        if (self.outcome == "failed") != (self.reason is not None):
            raise ValueError(
                "un motif d'échec accompagne une issue « failed », et elle seule."
            )
        return self


class RunResult(BaseModel):
    """Sortie complète d'un run : manifeste + agrégats + détail par-document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: 3 : une ligne d'``usage`` par unité **y compris en échec** (issue + motif)
    #: et ``expected`` sur les agrégats. Un JSON v2 se recharge (issue ``ok`` par
    #: défaut, ``expected`` absent) — mais ne distingue pas un échec d'une absence.
    #: 4 : le manifeste porte ``served_models`` et ``unicode_version``, et
    #: ``adapter_kwargs`` y devient les réglages **effectifs** ; un lecteur v3
    #: (``extra="forbid"``) refuserait ces champs. Un JSON v3 se recharge (champs
    #: vides) sans prétendre savoir quel modèle a été servi.
    #: 5 : le payload ``inference`` porte le test (Wilcoxon/Friedman) ou le
    #: motif de son absence, la p corrigée de Holm, et un post-hoc conditionné
    #: au rejet — ``tied_groups`` (disjoints, faux) devient ``cd_groups``
    #: (chevauchants), ``q_alpha_extrapolated`` disparaît (q exact par scipy).
    #: Un JSON v4 **sans** payload ``inference`` (le mode rapide) se recharge ;
    #: un JSON v4 qui en porte un est refusé : ses verdicts n'étaient pas
    #: corrigés — on le re-note depuis son archive (``--resume-dir --offline``).
    #: Toujours 5 : l'IC d'un pipeline (``intervals``) est celui du ratio
    #: micro affiché (``value``), plus celui d'une moyenne macro (``mean``).
    #: La version n'avait pas été publiée ; un payload qui porte ``mean`` est
    #: refusé (champ inconnu), le reste d'un JSON v5 se relit tel quel.
    schema_version: int = 5
    manifest: RunManifest
    pipelines: tuple[PipelineResult, ...] = Field(default_factory=tuple)
    documents: tuple[RunDocumentResult, ...] = Field(default_factory=tuple)
    #: Écrit par la passe inter-moteurs ; vide tant qu'un seul pipeline court.
    cross_engine: tuple[MetricScore, ...] = Field(default_factory=tuple)
    #: Une entrée par unité (pipeline × document) exécutée, **en échec compris**,
    #: triée (pipeline, document_id) — ordre déterministe. Vide pour un résultat
    #: reconstruit sans exécution (ex. chargement d'un JSON v1).
    usage: tuple[DocumentUsage, ...] = Field(default_factory=tuple)
    #: Canal des résultats **non scalaires** (contrat E2 ci-dessus) : payloads
    #: typés par famille, calculés par le runner, triés (view, kind, métrique)
    #: — ordre déterministe. Les rapports lisent, ne recalculent pas.
    analyses: tuple[Analysis, ...] = Field(default_factory=tuple)


__all__ = [
    "Analysis",
    "DocumentUsage",
    "MetricScore",
    "PipelineResult",
    "RunDocumentResult",
    "RunResult",
]
