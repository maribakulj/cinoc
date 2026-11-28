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

from cinoc.domain.evaluation import FailurePolicy
from cinoc.domain.run import RunManifest
from cinoc.domain.usage import (
    FailureReason,
    LineOutcomes,
    ResourceUsage,
    StepIssue,
    UnitOutcome,
)
from cinoc.evaluation.analysis import Analysis
from cinoc.evaluation.statistics import ScalarReason, Statistic

#: Version du schéma. Une rupture **explicite** : un ``RunResult`` d'une autre
#: version est refusé à la lecture, jamais converti (CLAUDE.md §5.1).
SCHEMA_VERSION = 7


#: Axe 1 — la métrique s'applique-t-elle à ce document (§ 2.1 b) ? Les
#: « attendus » sont les observations ``applicable``. ``no_ground_truth`` : le
#: document n'a pas de vérité terrain de ce niveau ; ``not_transcribed`` : la
#: vérité terrain est vide parce que personne ne l'a saisie (déclaré par
#: l'importeur, P7 — ≠ une page blanche, applicable) ; ``not_in_view`` : la vue
#: ne voit pas ce que le pipeline produit (aucune étape ne rend un type
#: candidat de la vue), ou la métrique n'a pas de niveau à lire (« niveau absent
#: → non applicable », ``CLAUDE.md`` §3).
Applicability = Literal[
    "applicable", "no_ground_truth", "not_transcribed", "not_in_view"
]

#: Axe 2 — la sortie à noter existe-t-elle ? ``output_unreadable`` : une sortie
#: existe, mais ne se lit pas dans le type de la métrique (aucune projection) ;
#: ``gt_unreadable`` : de même pour la vérité terrain ; ``step_failed`` /
#: ``step_cancelled`` : l'exécution n'a rien produit (échec d'un moteur ; délai
#: ou annulation) — l'exécution est une cause, déclarée par l'exécuteur.
Availability = Literal[
    "available",
    "gt_unreadable",
    "output_missing",
    "output_unreadable",
    "step_failed",
    "step_cancelled",
]

#: Axe 3 — la sortie est-elle entière ? ``partial_output`` : l'étape l'a
#: **déclarée** incomplète (régions perdues, lignes en repli) ;
#: ``truncated_output`` : coupée par le fournisseur (``max_tokens``). Ni l'une
#: ni l'autre n'est notée par défaut (R6) : leur statistique est gardée à part
#: (``stat_partielle``), jamais jetée ni imputée en silence.
Validity = Literal["valid", "partial_output", "truncated_output"]


class MetricScore(BaseModel):
    """Valeur d'une métrique (agrégat ou par-document) et sa statistique.

    ``stat`` est la **statistique suffisante** de la famille de la métrique
    (``evaluation.statistics``) ; ``value`` en est la finalisation — celle du
    document, ou celle de la somme des statistiques pour l'agrégat (le micro,
    K1). ``value`` peut être ``None`` alors que ``stat`` existe : le scalaire
    est indéfini (``scalar_reason``, ex. ``zero_denominator`` pour une page à
    référence vide), mais la statistique contribue au micro. Sans ``stat``,
    rien n'a été mesuré. Par défaut, ``stat`` n'est présente que si les axes 1
    à 3 sont au vert ; la statistique d'une observation **partielle** ou
    **tronquée**, calculée sur ce qui a été produit, est gardée dans
    ``stat_partielle`` (§ 2.1 f) ; celle d'une unité **sans sortie exploitable**
    (échec, délai, sortie absente ou illisible), c'est-à-dire la statistique
    « sortie vide » qui entre dans la qualité opérationnelle, est dans
    ``stat_vide`` (D3).
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
    #: **Par document** : la statistique calculée sur ce qui a été produit quand
    #: la sortie est partielle ou tronquée (axe 3) — conservée, non notée par
    #: défaut. ``None`` pour une observation complète, ou sans aucune sortie.
    stat_partielle: Statistic | None = None
    #: **Par document** : la statistique « sortie vide » — celle de la référence
    #: face à une sortie vide du type noté —, présente pour toute unité attendue
    #: dont la sortie est inexploitable (échec, délai, sortie absente ou
    #: illisible). C'est ce qui entre dans la qualité **opérationnelle** à la
    #: place de la sortie (§ 2.1 c, D3) : l'archive porte tout ce qui permet de
    #: recalculer chaque agrégat. ``None`` pour une sortie lisible.
    stat_vide: Statistic | None = None
    #: **Inter-moteurs** : ``exploratory`` pour tout scalaire issu de l'ancienne
    #: inférence (``significance_p``) — jusqu'à la tranche I, aucun résultat de
    #: test n'est confirmatoire (§ 2.1 d, rév. 7). ``None`` ailleurs.
    status: Literal["exploratory"] | None = None
    #: **Agrégat** : le macro (moyenne **exacte** des scalaires sur D^M_P, par
    #: document ou par grappe selon la pondération du corpus), ``None`` si la
    #: métrique n'en a pas (dénominateur d'hypothèse) ou si D^M_P est vide ;
    #: ``macro_support`` = |D^M_P|.
    macro: float | None = None
    macro_support: int | None = Field(default=None, ge=0)
    #: **Agrégat** : ``{motif : nombre d'attendus non entrés}`` — le motif est la
    #: valeur de l'axe 2 ou 3 qui a écarté l'observation (``step_failed``,
    #: ``partial_output``…). ``{}`` : tous les attendus sont entrés. ``None``
    #: par document.
    coverage: dict[str, int] | None = None
    #: Axes de l'observation (**par document** ; ``None`` sur un agrégat).
    applicability: Applicability | None = None
    availability: Availability | None = None
    validity: Validity | None = None
    #: **Agrégat** : |D^μ_P|, le nombre d'observations dont la statistique
    #: entre dans **cet** agrégat (pages à référence vide comprises) ;
    #: **inter-moteurs** : cas complets du test. ``None`` par document (les
    #: dénominateurs sont dans ``stat``).
    support: int | None = Field(default=None, ge=0)
    #: **Agrégat seulement** — « n attendus » à côté de ``support`` (« n notés ») :
    #: les observations ``applicable`` (axe 1), qu'elles aient été notées ou non.
    #: Dans la qualité **conditionnelle**, l'écart entre les deux est ce que les
    #: axes 2 et 3 ont écarté (échecs, sorties partielles ou tronquées) ; ses
    #: motifs sont dans ``coverage``. Dans la qualité **opérationnelle**, les
    #: échecs sont notés comme une sortie vide et les partielles telles que
    #: produites : seul reste hors de ``support`` ce que rien ne permet de noter
    #: (vérité terrain illisible). ``expected`` et ``coverage`` sont les mêmes
    #: pour les deux. ``None`` par-document.
    expected: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _scalar_of_its_statistic(self) -> Self:
        if self.scalar_reason is not None and (
            self.stat is None or self.value is not None
        ):
            raise ValueError("un motif de scalaire indéfini va avec une statistique")
        if self.stat is not None and self.value is None and self.scalar_reason is None:
            raise ValueError("statistique sans scalaire : le motif est requis")
        if self.stat_partielle is not None and (
            self.validity not in ("partial_output", "truncated_output")
        ):
            raise ValueError("une statistique partielle va avec un axe 3 partiel")
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
    #: Grappe du document (``DocumentRef.cluster``) ; ``None`` si le corpus n'en
    #: déclare pas — un document sans grappe forme la sienne (B3). Portée par
    #: chaque document pour que le macro par grappe se recalcule depuis le seul
    #: JSON (D4, invariant I).
    cluster: str | None = Field(default=None, max_length=256)
    #: **Référence** image du document (chemin corpus-relatif ou URL IIIF),
    #: jamais les octets → déterminisme/hash du résultat intacts. Résolue en
    #: vignette **au rendu** (adapter, hors résultat). ``None`` = pas d'image.
    image_ref: str | None = Field(default=None, max_length=2048)


class PipelineResult(BaseModel):
    """Agrégats d'un pipeline sous une vue : deux qualités, toujours publiées.

    - ``conditional_aggregate`` — observations **complètes** seules (axes 1 à 3
      au vert) : ce que le pipeline sait faire quand il va au bout ;
    - ``operational_aggregate`` — toutes les unités attendues : partielles et
      tronquées notées telles que produites, échecs notés comme une sortie
      vide : ce que l'utilisateur reçoit réellement.

    L'agrégat **principal** n'est pas stocké : ``principal_aggregate`` le dérive
    de la politique d'échec du run (``RunManifest.failure_policy`` : ``exclude``
    → conditionnelle, ``empty_page`` → opérationnelle). Les deux portent la même
    couverture (``expected``, ``coverage``) : ni l'une ni l'autre ne s'améliore
    sans que la couverture le dise. Population cible et pondération des grappes (B3) du
    corpus sont publiées avec elles ; ``line_outcomes`` somme les issues de
    lignes des unités (correction structurée, § 2.1 f).

    Un pipeline qui **ne voit pas** la vue (aucune étape ne déclare un type
    candidat) n'a pas d'entrée ici : il n'entre dans aucun agrégat de cette vue
    (D1).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    view: str = Field(min_length=1, max_length=128)
    conditional_aggregate: tuple[MetricScore, ...] = Field(default_factory=tuple)
    operational_aggregate: tuple[MetricScore, ...] = Field(default_factory=tuple)
    target_population: str | None = Field(default=None, max_length=512)
    cluster_weighting: Literal["document", "cluster"] = "document"
    line_outcomes: LineOutcomes | None = None

    def principal_aggregate(self, policy: FailurePolicy) -> tuple[MetricScore, ...]:
        """La qualité que ``policy`` désigne comme **principale** (Q9)."""
        if policy == "empty_page":
            return self.operational_aggregate
        return self.conditional_aggregate


class DocumentUsage(BaseModel):
    """Enregistrement d'une unité (pipeline × document) : issue + ressources.

    L'exécution a lieu une fois par (pipeline × document) — les vues sont des
    lentilles d'évaluation, sans coût d'exécution propre. Les durées sont du
    wall-clock (mesure d'environnement, comme les horodatages du manifeste).

    ``outcome`` (``ok`` · ``truncated`` · ``partial`` · ``failed``) est l'issue
    **produite par l'exécution** (``DocumentExecution``) et transportée telle
    quelle : une unité en échec a sa ligne, avec son motif codé (``reason``) et
    son message — c'est ce qui distingue un échec d'une absence. Une unité en
    échec n'a pas de durée mesurée ; son ``usage`` ne porte que ce qu'elle a
    fait **facturer** avant d'échouer (jetons d'une réponse refusée, page
    soumise), vide sinon.

    ``partial`` : l'étape a **déclaré** sa sortie incomplète (régions perdues,
    lignes de correction en repli) — l'évaluation lit cet état, ne le
    reconstruit jamais. ``line_outcomes`` : les issues des lignes d'une
    correction structurée (corrigées, à revoir, abstentions, refus et replis par
    code) quand l'unité en traverse une.

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
    line_outcomes: LineOutcomes | None = None
    #: L'état déclaré **par étape** : l'ensemble **trié** de ses issues
    #: (``partial`` · ``truncated``, les deux si l'étape est coupée et incomplète),
    #: vide si l'unité est complète. Chaque vue lit celui de **son** étape et des
    #: étapes qui la précèdent ; absent d'une unité qui ne nomme pas ses étapes,
    #: ``outcome`` s'applique à toutes les vues (la tranche 2 le porte au
    #: ``StepRecord``, sans changer sa sémantique).
    step_issues: dict[str, tuple[StepIssue, ...]] = Field(default_factory=dict)
    resumed: bool = False

    @model_validator(mode="after")
    def _reason_iff_failed(self) -> Self:
        if (self.outcome == "failed") != (self.reason is not None):
            raise ValueError(
                "un motif d'échec accompagne une issue « failed », et elle seule."
            )
        for issues in self.step_issues.values():
            if not issues or list(issues) != sorted(set(issues)):
                raise ValueError(
                    "les issues d'une étape forment un ensemble trié, non vide."
                )
        return self


class RunResult(BaseModel):
    """Sortie complète d'un run : manifeste + agrégats + détail par-document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: 7 (refonte des contrats, D-313). v6 (tranches 1a, 1b) : une observation
    #: porte la **statistique suffisante** de sa famille (``stat``) et non plus
    #: un ratio et un poids ; l'agrégat est la finalisation de la somme des
    #: statistiques (micro exact), un scalaire indéfini dit pourquoi
    #: (``scalar_reason``), une exactitude publie son taux d'erreur non tronqué,
    #: une observation ses axes. v7 (revue de 1a + 1b) : ``aggregate`` n'est plus
    #: stocké (``principal_aggregate`` le dérive de ``failure_policy``), chaque
    #: observation porte sa statistique « sortie vide » (``stat_vide``) et chaque
    #: document sa grappe (``cluster``) — tout agrégat se recalcule depuis le
    #: JSON —, ``step_issues`` est un ensemble trié d'issues par étape, un
    #: pipeline hors vue n'a pas d'entrée d'agrégat. Les valeurs de plusieurs
    #: métriques changent d'une version à l'autre : un JSON antérieur est
    #: **refusé** avec un message, jamais relu ni converti — on le re-note depuis
    #: son archive (``cinoc run --resume-dir … --offline``).
    schema_version: Literal[7] = 7
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

    def principal_aggregate(self, entry: PipelineResult) -> tuple[MetricScore, ...]:
        """L'agrégat **principal** d'un pipeline, dérivé de la politique d'échec
        du run : ``exclude`` → la qualité conditionnelle, ``empty_page`` → la
        qualité opérationnelle. Jamais stocké une seconde fois (Q9)."""
        return entry.principal_aggregate(self.manifest.failure_policy)

    @model_validator(mode="before")
    @classmethod
    def _refuse_other_schemas(cls, data: Any) -> Any:
        if isinstance(data, dict):
            version = data.get("schema_version", SCHEMA_VERSION)
            if version != SCHEMA_VERSION:
                raise ValueError(
                    f"RunResult au schéma v{version}, attendu v{SCHEMA_VERSION} : "
                    "le sens ou la forme des agrégats a changé depuis — le "
                    "fichier n'est ni relu ni converti. Re-notez le run depuis "
                    "son archive (cinoc run --resume-dir <archive> --offline)."
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
