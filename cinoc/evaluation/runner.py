"""``evaluate_run`` — le runner (par-document → agrégat → inter-moteurs).

Reçoit des **artefacts déjà produits** (couche 4, via l'app) : il n'exécute aucun
moteur et n'importe pas ``pipeline``. **Trois passes** par vue : (1) par-document
(``None`` = non applicable), (2) agrégat par pipeline (``None`` exclu, **support**
exposé), (3) **inter-moteurs** — chaque ``CrossEngineMetric`` compare les
pipelines et écrit dans ``RunResult.cross_engine``.

Normalisation de la vue (``normalization_profile``/``char_exclude``) appliquée
symétriquement GT/hyp ; représentation chargée+normalisée **une fois par
signature** ``(ref, hyp)``.
"""

from __future__ import annotations

from collections.abc import Mapping

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.run import RunManifest
from cinoc.evaluation._view_collectors import ViewCollectors
from cinoc.evaluation.calibration import calibration_analysis
from cinoc.evaluation.conformity import conformity_analysis
from cinoc.evaluation.context import CrossEngineContext, DocContext
from cinoc.evaluation.correction import correction_analysis
from cinoc.evaluation.decisions import decisions_analysis
from cinoc.evaluation.economics import economics_analysis
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.inference import inference_analysis
from cinoc.evaluation.projectors import get_projector
from cinoc.evaluation.registry import MetricRegistry
from cinoc.evaluation.representations import load_representation, prepare_text
from cinoc.evaluation.result import (
    Analysis,
    DocumentUsage,
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)

#: { pipeline_name: { document_id: { ArtifactType: Artifact } } }
PipelineOutputs = Mapping[str, Mapping[str, Mapping[ArtifactType, Artifact]]]

#: Signature d'entrée d'une métrique : ``(type_référence, type_hypothèse)``.
_Signature = tuple[ArtifactType, ArtifactType]

#: Précédence de **repli**, quand l'étape productrice est inconnue : du plus
#: aval (corrigé) au plus brut. Elle ne vaut que comme approximation — c'est
#: l'ordre des étapes du pipeline qui fait foi (cf. ``_candidate_for``). Jamais
#: l'ordre alphabétique des valeurs d'enum (qui ne coïncide avec l'intention
#: que par hasard).
_CANDIDATE_PRECEDENCE: tuple[ArtifactType, ...] = (
    ArtifactType.CORRECTED_TEXT,
    ArtifactType.RAW_TEXT,
)

#: { métrique : { pipeline : [score par doc, aligné, ``None`` inclus] } }
_Series = dict[str, dict[str, list[MetricScore]]]

#: Types **inter-changeables au niveau représentation** : tous chargés en ``str``.
#: Un candidat ``CORRECTED_TEXT`` est donc noté par une métrique ``RAW_TEXT`` sans
#: projection (les post-corrections LLM passent telles quelles).
_TEXT_LIKE = frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT})


def evaluate_run(
    *,
    corpus: CorpusSpec,
    evaluation: EvaluationSpec,
    pipeline_outputs: PipelineOutputs,
    registry: MetricRegistry,
    manifest: RunManifest,
    usage: tuple[DocumentUsage, ...] = (),
) -> RunResult:
    """Calcule le ``RunResult`` depuis les sorties de pipelines et la GT.

    ``usage`` (ressources mesurées par l'orchestrateur, une entrée par
    pipeline × document exécuté) est embarqué tel quel, **trié** (pipeline,
    document_id) pour un ordre déterministe.
    """
    pipeline_order = [spec.name for spec in manifest.pipeline_specs]
    pipelines: list[PipelineResult] = []
    documents: list[RunDocumentResult] = []
    cross_engine: list[MetricScore] = []
    analyses: list[Analysis] = []

    for view in evaluation.views:
        series: _Series = {name: {} for name in view.metric_names}
        collectors = ViewCollectors(view)
        for pipeline_name in pipeline_order:
            for name in view.metric_names:
                series[name][pipeline_name] = []
            step_ranks = _step_ranks(manifest, pipeline_name)
            for document in corpus.documents:
                candidate = _candidate_for(
                    pipeline_outputs,
                    pipeline_name,
                    document.id,
                    view.candidate_types,
                    step_ranks,
                )
                scores, text_context, entity_context = _score_document(
                    view, document, candidate, registry
                )
                collectors.observe(
                    pipeline_name,
                    document.id,
                    scores,
                    text_context,
                    entity_context,
                )
                for score in scores:
                    series[score.metric][pipeline_name].append(score)
                documents.append(
                    RunDocumentResult(
                        document_id=document.id,
                        pipeline=pipeline_name,
                        view=view.name,
                        scores=scores,
                        stratum=document.metadata.get("stratum"),
                        image_ref=document.image_uri,
                    )
                )
            pipelines.append(
                PipelineResult(
                    pipeline=pipeline_name,
                    view=view.name,
                    aggregate=tuple(
                        _aggregate(name, series[name][pipeline_name])
                        for name in view.metric_names
                    ),
                )
            )
        cross_engine.extend(_cross_engine_scores(view, series, registry))
        analyses.extend(_inference_analyses(view, series))
        analyses.extend(
            collectors.build(
                view.name,
                [document.id for document in corpus.documents],
                series.get("cer", {}),
            )
        )
        # Analyses **autonomes** (≠ collecteurs) : elles lisent corpus /
        # pipeline_outputs / usage directement, hors du cycle observe→build.
        calibration = calibration_analysis(view.name, corpus, pipeline_outputs)
        if calibration is not None:
            analyses.append(calibration)
        if "cer" in view.metric_names:
            economics = economics_analysis(
                view.name, "cer", series["cer"], usage, manifest
            )
            if economics is not None:
                analyses.append(economics)
        correction = correction_analysis(view, corpus, pipeline_outputs)
        if correction is not None:
            analyses.append(correction)
        # Ce qu'un correcteur a **refusé** de changer : invisible dans le texte
        # de sortie, donc invisible partout ailleurs.
        decisions = decisions_analysis(view.name, pipeline_outputs)
        if decisions is not None:
            analyses.append(decisions)

    # Post-passe cross-vues : la conformité HIPE lit les résultats des vues
    # raw/hipe/heritage déjà calculés (zéro re-scoring) — cf. ``conformity``.
    conformity = conformity_analysis(evaluation.views, pipelines, documents)
    if conformity is not None:
        analyses.append(conformity)

    return RunResult(
        manifest=manifest,
        pipelines=tuple(pipelines),
        documents=tuple(documents),
        cross_engine=tuple(cross_engine),
        usage=tuple(sorted(usage, key=lambda u: (u.pipeline, u.document_id))),
        analyses=tuple(
            sorted(
                analyses,
                key=lambda a: (
                    a.view,
                    a.payload.kind,
                    getattr(a.payload, "metric", ""),
                ),
            )
        ),
    )


def _inference_analyses(view: EvaluationView, series: _Series) -> list[Analysis]:
    """Inférentiel corrigé par métrique de la vue (cf. ``evaluation.inference``).

    Consomme les **mêmes séries alignées** que la passe inter-moteurs : même
    index = même document, ``None`` = non applicable — un seul calcul des
    scores, deux lectures (scalaire ``significance_p`` + payload structuré).
    """
    out: list[Analysis] = []
    for metric_name in view.metric_names:
        per_pipeline = {
            pipeline: [score.value for score in scores]
            for pipeline, scores in series[metric_name].items()
        }
        analysis = inference_analysis(view.name, metric_name, per_pipeline)
        if analysis is not None:
            out.append(analysis)
    return out


def _aggregate(name: str, scores: list[MetricScore]) -> MetricScore:
    """Agrégat **micro** : Σ(valeur·poids)/Σpoids — la métrique au niveau corpus.

    Micro (et non la moyenne *macro* des taux par-document) est la métrique
    conventionnelle au niveau corpus, comparable à ``jiwer`` sur le corpus
    entier : un long document pèse à proportion de sa taille. La moyenne macro
    reste reconstructible depuis le détail par-document (``RunResult.documents``).
    Les documents à poids nul (référence vide) sont exclus du micro ; ``value``
    vaut ``None`` si aucun poids (toutes réfs vides). ``support`` = nombre de
    documents applicables.
    """
    pairs: list[tuple[float, int]] = []
    for score in scores:
        if score.value is not None:
            pairs.append((score.value, score.support or 0))
    total_weight = sum(weight for _, weight in pairs)
    micro = (
        sum(value * weight for value, weight in pairs) / total_weight
        if total_weight > 0
        else None
    )
    return MetricScore(metric=name, value=micro, support=len(pairs))


def _cross_engine_scores(
    view: EvaluationView, series: _Series, registry: MetricRegistry
) -> list[MetricScore]:
    metrics = registry.cross_engine_metrics()
    if not metrics:
        return []
    scores: list[MetricScore] = []
    for base_metric in view.metric_names:
        per_pipeline = {
            pipeline: tuple(score.value for score in scores_list)
            for pipeline, scores_list in series[base_metric].items()
        }
        context = CrossEngineContext(metric=base_metric, per_pipeline=per_pipeline)
        for metric in metrics:
            value, support = metric.fn(context)
            scores.append(
                MetricScore(
                    metric=f"{view.name}:{base_metric}:{metric.name}",
                    value=value,
                    support=support,
                )
            )
    return scores


def _step_ranks(manifest: RunManifest, pipeline_name: str) -> Mapping[str, int]:
    """``{id d'étape: rang}`` du pipeline — vide s'il n'est pas au manifeste."""
    for spec in manifest.pipeline_specs:
        if spec.name == pipeline_name:
            return {step.id: rank for rank, step in enumerate(spec.steps)}
    return {}


def _candidate_for(
    pipeline_outputs: PipelineOutputs,
    pipeline_name: str,
    document_id: str,
    candidate_types: frozenset[ArtifactType],
    step_ranks: Mapping[str, int],
) -> Artifact | None:
    """L'artefact à noter : la sortie de l'étape la plus **aval** du pipeline.

    Choisir par *type* d'artefact note un intermédiaire dès qu'une étape en aval
    reproduit un type plus « brut ». Cas réel : ``segmentation → OCR par région
    → correction VLM → ordre de lecture → projection`` publie un
    ``CORRECTED_TEXT`` au milieu et finit sur un ``RAW_TEXT`` ; la précédence par
    type notait le texte corrigé, donc **avant** l'ordre de lecture — mêmes mots,
    mauvaise séquence, et un CER de 0,8842 au lieu de 0,8079.

    L'ordre des étapes du pipeline tranche sans ambiguïté, et ``produced_by_step``
    le rattache à l'artefact. La précédence par type ne sert plus que de repli,
    pour les artefacts dont l'étape est inconnue — ceux du fan-out, qui la
    laissent à ``None``, et les entrées initiales.
    """
    by_document: Mapping[str, Mapping[ArtifactType, Artifact]] = (
        pipeline_outputs.get(pipeline_name, {})
    )
    outputs: Mapping[ArtifactType, Artifact] = by_document.get(document_id, {})
    présents = [(t, a) for t, a in outputs.items() if t in candidate_types]
    if not présents:
        return None

    #: Départage deux artefacts d'une **même** étape (un module peut en publier
    #: plusieurs) : on retombe alors sur la précédence par type.
    def rang_de_type(artifact_type: ArtifactType) -> int:
        if artifact_type in _CANDIDATE_PRECEDENCE:
            return _CANDIDATE_PRECEDENCE.index(artifact_type)
        return len(_CANDIDATE_PRECEDENCE)

    datés = [
        (step_ranks[a.produced_by_step], -rang_de_type(t), t.value, a)
        for t, a in présents
        if a.produced_by_step is not None and a.produced_by_step in step_ranks
    ]
    if datés:
        # Trier sur les trois premiers champs seulement : le quatrième est un
        # ``Artifact``, qui n'a pas d'ordre. Ils ne peuvent pas s'égaliser
        # aujourd'hui (``outputs`` est indexé par type, donc ``t.value`` est
        # unique) — mais c'est un invariant implicite, et le laisser décider
        # ferait lever un ``TypeError`` obscur le jour où il cesse de tenir.
        return max(datés, key=lambda entrée: entrée[:3])[3]

    ordered = [t for t in _CANDIDATE_PRECEDENCE if t in candidate_types]
    ordered.extend(
        sorted(
            (t for t in candidate_types if t not in _CANDIDATE_PRECEDENCE),
            key=lambda t: t.value,
        )
    )
    for artifact_type in ordered:
        if artifact_type in outputs:
            return outputs[artifact_type]
    return None


def _score_document(
    view: EvaluationView,
    document: DocumentRef,
    candidate: Artifact | None,
    registry: MetricRegistry,
) -> tuple[tuple[MetricScore, ...], DocContext | None, DocContext | None]:
    # Représentation chargée + normalisée une seule fois par signature, partagée
    # par toutes les métriques qui la consomment (CER/WER/MER). Les contextes
    # **texte** et **entités** sont aussi renvoyés : les collecteurs (confusions,
    # pires lignes, NER) les consomment sans recharger ni renormaliser.
    contexts: dict[_Signature, DocContext | None] = {}
    scores: list[MetricScore] = []
    for name in view.metric_names:
        metric = registry.document_metric(name)
        if metric is None:
            raise EvaluationError(f"métrique inconnue : {name!r}.")
        signature = metric.input_types
        if signature not in contexts:
            contexts[signature] = _context_for(view, document, candidate, signature)
        context = contexts[signature]
        observation = metric.fn(context) if context is not None else None
        scores.append(
            MetricScore(
                metric=name,
                value=observation.value if observation is not None else None,
                support=observation.weight if observation is not None else None,
            )
        )
    text_context = contexts.get((ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT))
    entity_context = contexts.get((ArtifactType.ENTITIES, ArtifactType.ENTITIES))
    return tuple(scores), text_context, entity_context


def _context_for(
    view: EvaluationView,
    document: DocumentRef,
    candidate: Artifact | None,
    signature: _Signature,
) -> DocContext | None:
    reference_type, hypothesis_type = signature
    if candidate is None or candidate.uri is None:
        return None
    resolved = _resolve_ground_truth(document, view, reference_type)
    if resolved is None:
        return None
    ground_truth, gt_native_type = resolved
    reference = _project_side(ground_truth.uri, gt_native_type, reference_type, view)
    hypothesis = _project_side(candidate.uri, candidate.type, hypothesis_type, view)
    if reference is None or hypothesis is None:
        return None
    return DocContext(
        document_id=document.id,
        reference=_prepare(reference, view),
        hypothesis=_prepare(hypothesis, view),
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


__all__ = ["PipelineOutputs", "evaluate_run"]
