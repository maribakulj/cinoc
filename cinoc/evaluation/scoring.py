"""Notation **par document** (couche 3) : statistique, scalaire et axes.

Pour chaque (pipeline × document × métrique) d'une vue, la statistique
suffisante de la métrique (``evaluation.statistics``), son scalaire finalisé
et les trois axes de l'observation (``CONTRATS.md`` § 2.1 b) :

- **applicabilité** — la vérité terrain du document alimente-t-elle la
  métrique, la voit-elle (``applicable`` · ``no_ground_truth`` ·
  ``not_transcribed`` · ``not_in_view``) ;
- **disponibilité** — la sortie existe-t-elle et se lit-elle dans le type de
  la métrique (``available`` · ``output_missing`` · ``output_unreadable`` ·
  ``gt_unreadable`` · ``step_failed`` · ``step_cancelled``) ;
- **validité** — est-elle entière (``valid`` · ``partial_output`` ·
  ``truncated_output``). L'état d'exécution est **lu** (``DocumentUsage``,
  déclaré par l'étape et porté par l'exécuteur) : il n'est jamais reconstruit
  d'après les textes (§ 2.1 f).

Une page à référence vide est applicable, disponible et valide : sa
statistique existe (ses insertions entrent au micro), son scalaire est
indéfini (``zero_denominator``). Par défaut, la statistique n'est présente que
si les axes 1 à 3 sont au vert ; une sortie partielle ou tronquée garde la
sienne dans ``stat_partielle`` ; sous ``empty_page``, elle est notée telle que
produite et un échec comme une sortie vide. Normalisation de la vue appliquée
symétriquement GT/hyp ; la référence est chargée **une fois** par document et
signature (``ReferenceProbe``), partagée par tous les pipelines. Le runner
(``evaluation.runner``) agrège.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.layout import CanonicalLayout
from cinoc.domain.usage import FailureReason, UnitOutcome
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation, observe
from cinoc.evaluation.ner import EntitySet
from cinoc.evaluation.projectors import get_projector
from cinoc.evaluation.registry import MetricRegistry
from cinoc.evaluation.representations import load_representation, prepare_text
from cinoc.evaluation.result import (
    Applicability,
    Availability,
    DocumentUsage,
    MetricScore,
    Validity,
)
from cinoc.evaluation.statistics import Counts

logger = logging.getLogger(__name__)

#: Signature d'entrée d'une métrique : ``(type_référence, type_hypothèse)``.
_Signature = tuple[ArtifactType, ArtifactType]

#: Types **inter-changeables au niveau représentation** : tous chargés en ``str``.
#: Un candidat ``CORRECTED_TEXT`` est donc noté par une métrique ``RAW_TEXT`` sans
#: projection (les post-corrections LLM passent telles quelles).
_TEXT_LIKE = frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT})


def metric_of(registry: MetricRegistry, name: str) -> DocumentMetric:
    """La métrique ``name`` du registre ; inconnue → ``EvaluationError``."""
    metric = registry.document_metric(name)
    if metric is None:
        raise EvaluationError(f"métrique inconnue : {name!r}.")
    return metric


def _observed(
    name: str,
    observation: Observation | None,
    axes: tuple[Applicability, Availability, Validity],
    *,
    noted: bool,
) -> MetricScore:
    """``MetricScore`` par document : l'observation et ses trois axes.

    ``noted`` : l'observation entre dans ``stat`` et ``value`` (axes au vert, ou
    politique ``empty_page``). Sinon, sa statistique est gardée à part
    (``stat_partielle``) quand la sortie est partielle ou tronquée, et dropée
    sinon (un échec n'a rien produit).
    """
    applicability, availability, validity = axes
    base = MetricScore(
        metric=name,
        applicability=applicability,
        availability=availability,
        validity=validity,
    )
    if observation is None:
        return base
    if noted:
        return base.model_copy(
            update={
                "value": observation.value,
                "stat": observation.stat,
                "scalar_reason": observation.scalar_reason,
                "untruncated_error_rate": observation.untruncated_error_rate,
                "stat_partielle": (
                    observation.stat if validity != "valid" else None
                ),
            }
        )
    return base.model_copy(update={"stat_partielle": observation.stat})


def _empty_hypothesis(hypothesis_type: ArtifactType) -> object | None:
    """Hypothèse **vide** du type : ce qu'aurait rendu un moteur sans sortie."""
    if hypothesis_type in _TEXT_LIKE:
        return ""
    if hypothesis_type is ArtifactType.LAYOUT:
        return CanonicalLayout()
    if hypothesis_type is ArtifactType.ENTITIES:
        return EntitySet(text="", entities=())
    return None


class ReferenceProbe:
    """Ce que dit la **référence** d'un document, indépendamment du pipeline.

    Chargée, projetée et préparée **une fois** par signature, partagée par tous
    les pipelines de la vue. Sert l'applicabilité (axe 1), la statistique d'une
    **sortie vide** (``empty_statistic`` : un échec noté comme une page vide, la
    mesure de la référence face à rien) et D^M : « la référence définit-elle le
    scalaire ? » ne dépend d'aucune sortie (R5).
    """

    def __init__(
        self, view: EvaluationView, document: DocumentRef, registry: MetricRegistry
    ) -> None:
        self.view = view
        self.document = document
        self._registry = registry
        self._references: dict[ArtifactType, object | None] = {}
        self._empties: dict[str, Counts | None] = {}

    def applicability(self, metric: DocumentMetric) -> Applicability:
        """``applicable`` si la vérité terrain du document alimente la métrique.

        C'est ce qui sépare un échec (l'unité aurait été notée) d'un cas que la
        métrique ne couvre de toute façon pas. Une vérité terrain déclarée
        ``not_transcribed`` sort des attendus : ce n'est pas une page blanche.
        """
        resolved = _resolve_ground_truth(
            self.document, self.view, metric.input_types[0]
        )
        if resolved is None:
            return "no_ground_truth"
        if resolved[0].status == "not_transcribed":
            return "not_transcribed"
        return "applicable"

    def reference(self, reference_type: ArtifactType) -> object | None:
        """Référence chargée, projetée et préparée comme au scoring, ou ``None``.

        Gardée pour tous les pipelines, **sauf** une mise en page : lourde, elle
        est relue par pipeline (comme avant) plutôt que gardée pour tout le
        corpus en mémoire.
        """
        if reference_type in self._references:
            return self._references[reference_type]
        reference = self._load(reference_type)
        if not isinstance(reference, CanonicalLayout):
            self._references[reference_type] = reference
        return reference

    def _load(self, reference_type: ArtifactType) -> object | None:
        resolved = _resolve_ground_truth(self.document, self.view, reference_type)
        if resolved is None:
            return None
        ground_truth, native_type = resolved
        try:
            projected = _project_side(
                ground_truth.uri, native_type, reference_type, self.view
            )
        except EvaluationError as exc:
            # Une VT illisible est un fait du document (``gt_unreadable``), pas
            # la perte du run : la couverture le dit.
            logger.warning(
                "[scoring] vérité terrain illisible (%s) : %s",
                self.document.id,
                exc,
            )
            return None
        return None if projected is None else _prepare(projected, self.view)

    def empty_statistic(self, metric: DocumentMetric) -> Counts | None:
        """La statistique de la référence face à une sortie **vide** du type
        noté (toute la référence en suppressions), ``None`` si la métrique n'en
        définit pas : on ne fabrique pas de comptes."""
        if metric.name not in self._empties:
            reference_type, hypothesis_type = metric.input_types
            reference = self.reference(reference_type)
            empty = _empty_hypothesis(hypothesis_type)
            observation = (
                metric.fn(
                    DocContext(
                        document_id=self.document.id,
                        reference=reference,
                        hypothesis=empty,
                        partial=True,
                    )
                )
                if reference is not None and empty is not None
                else None
            )
            self._empties[metric.name] = (
                None if observation is None else observation.stat
            )
        return self._empties[metric.name]


@dataclass(frozen=True)
class UnitScores:
    """Les scores d'une unité (pipeline × document) sous une vue.

    ``operational`` : la statistique de chaque métrique (alignée sur
    ``view.metric_names``) dans la qualité **opérationnelle** — la sortie telle
    que produite (complète, partielle ou tronquée), ou une sortie vide pour une
    unité sans sortie ; ``None`` quand rien n'est notable. ``text_context`` /
    ``entity_context`` : les contextes que les collecteurs d'analyse
    consomment, seulement quand la sortie est **à analyser** (complète, ou
    notée sous ``empty_page``).
    """

    scores: tuple[MetricScore, ...]
    operational: tuple[Counts | None, ...]
    text_context: DocContext | None
    entity_context: DocContext | None


def score_unit(
    view: EvaluationView,
    probe: ReferenceProbe,
    candidate: Artifact | None,
    in_view: bool,
    outcome: UnitOutcome,
    reason: FailureReason | None,
    registry: MetricRegistry,
    empty_page: bool,
) -> UnitScores:
    """Note une unité : statistique, axes, et statistique opérationnelle.

    ``outcome`` et ``reason`` : l'état d'exécution **déclaré** de l'étape que la
    vue note (``view_outcome``), lu tel quel. ``in_view`` : faux quand l'unité a
    rendu des sorties mais aucune d'un type candidat de la vue — la vue ne voit
    pas ce que ce pipeline produit.
    """
    failed = outcome == "failed"
    validity: Validity = (
        "partial_output"
        if outcome == "partial"
        else "truncated_output"
        if outcome == "truncated"
        else "valid"
    )
    lost: Availability = "step_cancelled" if reason == "cancelled" else "step_failed"
    # Représentation chargée + normalisée une seule fois par signature, partagée
    # par toutes les métriques qui la consomment (CER/WER/MER). Les contextes
    # **texte** et **entités** sont aussi renvoyés : les collecteurs (confusions,
    # pires lignes, NER) les consomment sans recharger ni renormaliser.
    contexts: dict[_Signature, tuple[DocContext | None, Availability]] = {}
    scores: list[MetricScore] = []
    operational: list[Counts | None] = []
    for name in view.metric_names:
        metric = metric_of(registry, name)
        applicability = probe.applicability(metric)
        availability: Availability
        observation: Observation | None = None
        if failed:
            availability = lost
        elif candidate is None:
            availability = "output_missing"
            if applicability == "applicable" and not in_view:
                applicability = "not_in_view"
        elif candidate.uri is None:
            availability = "output_missing"
        elif applicability != "applicable":
            availability = "available"
        else:
            signature = metric.input_types
            if signature not in contexts:
                contexts[signature] = _context_for(
                    probe, candidate, signature, partial=validity != "valid"
                )
            context, availability = contexts[signature]
            observation = None if context is None else metric.fn(context)
            if context is not None and observation is None:
                # Niveau absent (``CLAUDE.md`` §3) : la métrique n'a rien à lire.
                applicability = "not_in_view"
        applicable = applicability == "applicable"
        nothing_produced = availability in (
            "step_failed",
            "step_cancelled",
            "output_missing",
        )
        empty = (
            probe.empty_statistic(metric)
            if applicable and nothing_produced
            else None
        )
        stat = empty if observation is None else observation.stat
        operational.append(stat if applicable else None)
        if observation is None and empty is not None:
            # Sans sortie : ``empty_page`` la note comme une page vide, sous ce
            # nom ; par défaut, rien n'est noté.
            observation = observe(empty, metric.finalize) if empty_page else None
        scores.append(
            _observed(
                name,
                observation,
                (applicability, availability, validity),
                noted=validity == "valid" or empty_page,
            )
        )
    analyse = not failed and (validity == "valid" or empty_page)
    text_context = contexts.get((ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT))
    entity_context = contexts.get((ArtifactType.ENTITIES, ArtifactType.ENTITIES))
    return UnitScores(
        scores=tuple(scores),
        operational=tuple(operational),
        text_context=(
            text_context[0] if analyse and text_context is not None else None
        ),
        entity_context=(
            entity_context[0] if analyse and entity_context is not None else None
        ),
    )


def _context_for(
    probe: ReferenceProbe,
    candidate: Artifact,
    signature: _Signature,
    *,
    partial: bool,
) -> tuple[DocContext | None, Availability]:
    """Le contexte de la signature, et l'axe « disponibilité » qui le dit."""
    reference_type, hypothesis_type = signature
    if candidate.uri is None:
        return None, "output_missing"
    reference = probe.reference(reference_type)
    if reference is None:
        return None, "gt_unreadable"
    try:
        hypothesis = _project_side(
            candidate.uri, candidate.type, hypothesis_type, probe.view
        )
    except EvaluationError as exc:
        # Un artefact référencé mais absent du disque (ou illisible) n'abat que
        # son unité : le run, et les autres pipelines, sont notés (§ 2.1 b).
        logger.warning(
            "[scoring] sortie illisible (%s) : %s", probe.document.id, exc
        )
        found = Path(candidate.uri).is_file()
        return None, ("output_unreadable" if found else "output_missing")
    if hypothesis is None:
        return None, "output_unreadable"
    return (
        DocContext(
            document_id=probe.document.id,
            reference=reference,
            hypothesis=_prepare(hypothesis, probe.view),
            partial=partial,
        ),
        "available",
    )


def view_outcome(
    unit: DocumentUsage | None, steps: Sequence[str], scored_step: str | None
) -> UnitOutcome:
    """L'issue de l'unité **pour l'étape que la vue note**.

    ``failed`` et ``ok`` valent pour toutes les vues. Une unité ``partial`` ou
    ``truncated`` qui **nomme** ses étapes (``step_issues``, déclarées par
    l'étape) l'est pour la vue seulement si une étape jusqu'à celle qu'elle note
    (comprise) l'est : une correction aval coupée laisse la lecture amont
    complète (A2) ; une étape amont incomplète rend ce qui en dérive incomplet.
    Sans étapes nommées, l'issue de l'unité s'applique à toutes les vues.
    """
    if unit is None or unit.outcome in ("ok", "failed") or not unit.step_issues:
        return "ok" if unit is None else unit.outcome
    upstream = (
        steps[: steps.index(scored_step) + 1]
        if scored_step in steps
        else steps
    )
    issues = [unit.step_issues[s] for s in upstream if s in unit.step_issues]
    if "partial" in issues:
        return "partial"
    return "truncated" if "truncated" in issues else "ok"


def missing_ground_truths(
    corpus: CorpusSpec, evaluation: EvaluationSpec, registry: MetricRegistry
) -> list[tuple[str, str]]:
    """``(document, uri)`` des vérités terrain que la vue lira et qui sont
    **absentes du disque** — à refuser **avant** le premier appel de moteur
    (F8, § 2.1 e) : jamais exécuté et facturé sur tout le corpus pour
    s'effondrer à l'évaluation. Seules les vérités terrain que les métriques des
    vues liraient comptent ; un nom de métrique inconnu est refusé ailleurs."""
    missing: dict[tuple[str, str], None] = {}
    for view in evaluation.views:
        for name in view.metric_names:
            metric = registry.document_metric(name)
            if metric is None:
                continue
            for document in corpus.documents:
                resolved = _resolve_ground_truth(document, view, metric.input_types[0])
                if resolved is not None and not Path(resolved[0].uri).is_file():
                    missing[(document.id, resolved[0].uri)] = None
    return list(missing)


def _resolve_ground_truth(
    document: DocumentRef, view: EvaluationView, reference_type: ArtifactType
) -> tuple[GroundTruthRef, ArtifactType] | None:
    """GT dont le type natif **alimente** ``reference_type`` (direct ou projeté)."""
    direct = document.gt_for(reference_type)
    if direct is not None:
        return direct, reference_type
    for gt in document.ground_truths:
        spec = view.projection_for(gt.type)
        if spec is not None and spec.target_type == reference_type:
            return gt, gt.type
    return None


def _project_side(
    uri: str,
    native_type: ArtifactType,
    target_type: ArtifactType,
    view: EvaluationView,
) -> object | None:
    """Charge ``uri`` dans son type natif, projette vers ``target_type`` si besoin.

    Identité si types égaux ou tous deux *text-like* (même représentation ``str``).
    Sinon une ``ProjectionSpec`` de la vue doit pont(er) ``native → target`` ; à
    défaut, ``None`` (jonction non applicable, pas de comparaison factice).
    """
    representation = load_representation(uri, native_type)
    if native_type == target_type or (
        native_type in _TEXT_LIKE and target_type in _TEXT_LIKE
    ):
        return representation
    spec = view.projection_for(native_type)
    if spec is None or spec.target_type != target_type:
        return None
    return get_projector(spec.projector_name)(representation, spec.params)


def _prepare(representation: object, view: EvaluationView) -> object:
    """Applique la normalisation de la vue (profil + ``char_exclude``) au texte."""
    if not isinstance(representation, str):
        return representation
    return prepare_text(representation, view)


__all__ = [
    "ReferenceProbe",
    "UnitScores",
    "metric_of",
    "missing_ground_truths",
    "score_unit",
    "view_outcome",
]
