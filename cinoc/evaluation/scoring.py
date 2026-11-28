"""Notation **par document** (couche 3) : statistique, scalaire et axes.

Pour chaque (pipeline × document × métrique) d'une vue, la statistique
suffisante de la métrique (``evaluation.statistics``), son scalaire finalisé
et les trois axes de l'observation (``CONTRATS.md`` § 2.1 b) :

- **applicabilité** — la vérité terrain du document alimente-t-elle la
  métrique (``applicable`` · ``no_ground_truth``) ;
- **disponibilité** — la sortie existe-t-elle et se lit-elle dans le type de
  la métrique (``available`` · ``output_missing`` · ``output_unreadable`` ·
  ``gt_unreadable`` · ``step_failed``) ;
- **validité** — est-elle entière (``valid`` · ``truncated_output``).

Une page à référence vide est applicable, disponible et valide : sa
statistique existe (ses insertions entrent au micro), son scalaire est
indéfini (``zero_denominator``). Normalisation de la vue appliquée
symétriquement GT/hyp ; représentation chargée+normalisée **une fois par
signature** ``(ref, hyp)``. Le runner (``evaluation.runner``) agrège.
"""

from __future__ import annotations

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.layout import CanonicalLayout
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation
from cinoc.evaluation.ner import EntitySet
from cinoc.evaluation.projectors import get_projector
from cinoc.evaluation.registry import MetricRegistry
from cinoc.evaluation.representations import load_representation, prepare_text
from cinoc.evaluation.result import (
    Applicability,
    Availability,
    MetricScore,
    Validity,
)

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
) -> MetricScore:
    """``MetricScore`` par document : l'observation et ses trois axes."""
    applicability, availability, validity = axes
    base = MetricScore(
        metric=name,
        applicability=applicability,
        availability=availability,
        validity=validity,
    )
    if observation is None:
        return base
    return base.model_copy(
        update={
            "value": observation.value,
            "stat": observation.stat,
            "scalar_reason": observation.scalar_reason,
            "untruncated_error_rate": observation.untruncated_error_rate,
        }
    )


def _empty_hypothesis(hypothesis_type: ArtifactType) -> object | None:
    """Hypothèse **vide** du type : ce qu'aurait rendu un moteur sans sortie."""
    if hypothesis_type in _TEXT_LIKE:
        return ""
    if hypothesis_type is ArtifactType.LAYOUT:
        return CanonicalLayout()
    if hypothesis_type is ArtifactType.ENTITIES:
        return EntitySet(text="", entities=())
    return None


def _reference_for(
    view: EvaluationView, document: DocumentRef, reference_type: ArtifactType
) -> object | None:
    """Référence chargée, projetée et préparée comme au scoring, ou ``None``."""
    resolved = _resolve_ground_truth(document, view, reference_type)
    if resolved is None:
        return None
    ground_truth, gt_native_type = resolved
    reference = _project_side(ground_truth.uri, gt_native_type, reference_type, view)
    return None if reference is None else _prepare(reference, view)


def _applicability(
    view: EvaluationView, document: DocumentRef, metric: DocumentMetric
) -> Applicability:
    """``applicable`` si la vérité terrain du document alimente la métrique.

    C'est ce qui sépare un échec (l'unité aurait été notée) d'un cas que la
    métrique ne couvre de toute façon pas.
    """
    if _resolve_ground_truth(document, view, metric.input_types[0]) is None:
        return "no_ground_truth"
    return "applicable"


def score_failed(
    view: EvaluationView,
    document: DocumentRef,
    registry: MetricRegistry,
    empty_page: bool,
) -> tuple[MetricScore, ...]:
    """Scores d'une unité **en échec**, selon la politique d'échec.

    ``exclude`` : aucune statistique — l'unité sort du micro, et « n attendus »
    le dit. ``empty_page`` : la statistique de la référence face à une sortie
    **vide** du type noté (une page sans texte : toute la référence en
    suppressions), sous ce nom. Une métrique sans sortie vide définie pour son
    type reste sans statistique : on ne fabrique pas de comptes.
    """
    scores: list[MetricScore] = []
    for name in view.metric_names:
        metric = metric_of(registry, name)
        applicability = _applicability(view, document, metric)
        reference_type, hypothesis_type = metric.input_types
        reference = (
            _reference_for(view, document, reference_type)
            if empty_page and applicability == "applicable"
            else None
        )
        empty = _empty_hypothesis(hypothesis_type)
        observation = (
            metric.fn(
                DocContext(
                    document_id=document.id, reference=reference, hypothesis=empty
                )
            )
            if reference is not None and empty is not None
            else None
        )
        scores.append(
            _observed(name, observation, (applicability, "step_failed", "valid"))
        )
    return tuple(scores)


def score_document(
    view: EvaluationView,
    document: DocumentRef,
    candidate: Artifact | None,
    registry: MetricRegistry,
    truncated: bool,
) -> tuple[tuple[MetricScore, ...], DocContext | None, DocContext | None]:
    # Représentation chargée + normalisée une seule fois par signature, partagée
    # par toutes les métriques qui la consomment (CER/WER/MER). Les contextes
    # **texte** et **entités** sont aussi renvoyés : les collecteurs (confusions,
    # pires lignes, NER) les consomment sans recharger ni renormaliser.
    contexts: dict[_Signature, tuple[DocContext | None, Availability]] = {}
    scores: list[MetricScore] = []
    validity: Validity = "truncated_output" if truncated else "valid"
    for name in view.metric_names:
        metric = metric_of(registry, name)
        applicability = _applicability(view, document, metric)
        signature = metric.input_types
        if signature not in contexts:
            contexts[signature] = _context_for(view, document, candidate, signature)
        context, availability = contexts[signature]
        observation = metric.fn(context) if context is not None else None
        scores.append(
            _observed(name, observation, (applicability, availability, validity))
        )
    text_context = contexts.get((ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT))
    entity_context = contexts.get((ArtifactType.ENTITIES, ArtifactType.ENTITIES))
    return (
        tuple(scores),
        None if text_context is None else text_context[0],
        None if entity_context is None else entity_context[0],
    )


def _context_for(
    view: EvaluationView,
    document: DocumentRef,
    candidate: Artifact | None,
    signature: _Signature,
) -> tuple[DocContext | None, Availability]:
    """Le contexte de la signature, et l'axe « disponibilité » qui le dit."""
    reference_type, hypothesis_type = signature
    if candidate is None or candidate.uri is None:
        return None, "output_missing"
    if _resolve_ground_truth(document, view, reference_type) is None:
        # Sans vérité terrain (axe 1), rien n'est lu : la sortie existe.
        return None, "available"
    reference = _reference_for(view, document, reference_type)
    if reference is None:
        return None, "gt_unreadable"
    hypothesis = _project_side(candidate.uri, candidate.type, hypothesis_type, view)
    if hypothesis is None:
        return None, "output_unreadable"
    return (
        DocContext(
            document_id=document.id,
            reference=reference,
            hypothesis=_prepare(hypothesis, view),
        ),
        "available",
    )


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
    "metric_of",
    "score_document",
    "score_failed",
]
