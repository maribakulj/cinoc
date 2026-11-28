"""``RunResult`` — contrat de sortie **unique** d'un run (plein-scope, dégonflé).

Un seul format (pas de double représentation héritée). Dimensionné pour porter
toute métrique **scalaire** (texte/structure/NER/taxonomy…) et le détail
**par-document** dès sa conception, même quand seul un CER est écrit : ajouter
une métrique ou une vue est **additif**, jamais un changement d'enveloppe.
``schema_version`` couvre les évolutions structurelles ; les **clés** (``metric``,
``value``, ``support``, ``pipeline``, ``view``) sont un **contrat dur** avec le
rapport — renommer une clé est interdit (CLAUDE.md §12, déterminisme).

Contrat « analyses » (enveloppe, cf. D-066/D-067, E2) : les résultats
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

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cinoc.domain.run import RunManifest
from cinoc.domain.usage import FailureReason, ResourceUsage, UnitOutcome
from cinoc.evaluation.analysis import Analysis
from cinoc.evaluation.statistics import ScalarReason, Statistic

#: Version du schéma. Une rupture **explicite** : un ``RunResult`` d'une autre
#: version est refusé à la lecture, jamais converti (CLAUDE.md §5.1).
SCHEMA_VERSION = 6


#: Axe 1 — la métrique s'applique-t-elle à ce document (§ 2.1 b) ?
Applicability = Literal["applicable", "no_ground_truth"]

#: Axe 2 — la sortie à noter existe-t-elle ? ``output_unreadable`` : une sortie
#: existe, mais ne se lit pas dans le type de la métrique (aucune projection) ;
#: ``gt_unreadable`` : de même pour la vérité terrain.
Availability = Literal[
    "available", "gt_unreadable", "output_missing", "output_unreadable", "step_failed"
]

#: Axe 3 — la sortie est-elle entière ? (Une sortie tronquée est encore notée :
#: l'exclure par défaut relève de la tranche 1b, R6.)
Validity = Literal["valid", "truncated_output"]


class MetricScore(BaseModel):
    """Valeur d'une métrique (agrégat ou par-document) et sa statistique.

    ``stat`` est la **statistique suffisante** de la famille de la métrique
    (``evaluation.statistics``) ; ``value`` en est la finalisation — celle du
    document, ou celle de la somme des statistiques pour l'agrégat (le micro,
    K1). ``value`` peut être ``None`` alors que ``stat`` existe : le scalaire
    est indéfini (``scalar_reason``, ex. ``zero_denominator`` pour une page à
    référence vide), mais la statistique contribue au micro. Sans ``stat``,
    rien n'a été mesuré.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = Field(min_length=1, max_length=128)
    value: float | None = None
    stat: Statistic | None = None
    #: Pourquoi ``value`` est ``None`` alors que ``stat`` existe (axe 4).
    scalar_reason: ScalarReason | None = None
    #: **Exactitudes** : le taux d'erreur e/n **avant** le plancher max(0, ·)
    #: de ``value`` — publié à côté, avec les comptes de ``stat`` (B1).
    untruncated_error_rate: float | None = Field(default=None, ge=0)
    #: Axes de l'observation (**par document** ; ``None`` sur un agrégat).
    applicability: Applicability | None = None
    availability: Availability | None = None
    validity: Validity | None = None
    #: **Agrégat** : nombre de documents dont la statistique entre au micro
    #: (pages à référence vide comprises) ; **inter-moteurs** : cas complets
    #: du test. ``None`` par document (les dénominateurs sont dans ``stat``).
    support: int | None = Field(default=None, ge=0)
    #: **Agrégat seulement** — « n attendus » à côté de ``support`` (« n notés ») :
    #: les documents notés **plus** les unités en échec qui auraient pu l'être
    #: (vérité terrain présente pour cette métrique). L'écart entre les deux est
    #: exactement ce que la politique d'échec a retiré de la moyenne ; ses motifs
    #: sont dans ``RunResult.usage``. ``None`` par-document.
    expected: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _scalar_of_its_statistic(self) -> Self:
        if self.scalar_reason is not None and (
            self.stat is None or self.value is not None
        ):
            raise ValueError("un motif de scalaire indéfini va avec une statistique")
        if self.stat is not None and self.value is None and self.scalar_reason is None:
            raise ValueError("statistique sans scalaire : le motif est requis")
        return self


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
    durée mesurée ; son ``usage`` ne porte que ce qu'elle a fait **facturer**
    avant d'échouer (jetons d'une réponse refusée, page soumise), vide sinon.

    ``resumed`` : l'unité a été **relue de l'archive** (``--resume-dir``), pas
    exécutée par ce run — sa durée et ses jetons sont ceux de sa première
    exécution (D10, pilote D-281). Absent d'un JSON antérieur → ``False``, qui
    ne prétend rien : un tel JSON ne distinguait pas.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    pipeline: str = Field(min_length=1, max_length=128)
    usage: ResourceUsage
    outcome: UnitOutcome = "ok"
    reason: FailureReason | None = None
    message: str | None = Field(default=None, max_length=2000)
    resumed: bool = False

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

    #: 6 (refonte des contrats, tranche 1a, D-313) : une observation porte la
    #: **statistique suffisante** de sa famille (``stat``) et non plus un ratio
    #: et un poids ; l'agrégat est la finalisation de la somme des statistiques
    #: (micro exact), un scalaire indéfini dit pourquoi (``scalar_reason``),
    #: une exactitude publie son taux d'erreur non tronqué, et une observation
    #: ses axes. Les valeurs de plusieurs métriques changent (F1 micro, pages
    #: blanches au micro, plancher au corpus, comptes canoniques) : un JSON
    #: antérieur est **refusé** avec un message, jamais relu ni converti — on le
    #: re-note depuis son archive (``cinoc run --resume-dir … --offline``).
    schema_version: Literal[6] = 6
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

    @model_validator(mode="before")
    @classmethod
    def _refuse_other_schemas(cls, data: Any) -> Any:
        if isinstance(data, dict):
            version = data.get("schema_version", SCHEMA_VERSION)
            if version != SCHEMA_VERSION:
                raise ValueError(
                    f"RunResult au schéma v{version}, attendu v{SCHEMA_VERSION} : "
                    "les observations y étaient des ratios pondérés, sans "
                    "statistique suffisante — le fichier n'est ni relu ni "
                    "converti. Re-notez le run depuis son archive "
                    "(cinoc run --resume-dir <archive> --offline)."
                )
        return data


__all__ = [
    "SCHEMA_VERSION",
    "Analysis",
    "Applicability",
    "Availability",
    "Validity",
    "DocumentUsage",
    "MetricScore",
    "PipelineResult",
    "RunDocumentResult",
    "RunResult",
]
