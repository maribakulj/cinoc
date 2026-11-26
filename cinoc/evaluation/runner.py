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

from cinoc.domain.artifacts import (
    Artifact,
    ArtifactType,
    StepArtifacts,
    latest_by_type,
)
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.layout import CanonicalLayout
from cinoc.domain.run import RunManifest
from cinoc.evaluation._view_collectors import COLLECTEURS, ViewCollectors
from cinoc.evaluation.calibration import calibration_analysis
from cinoc.evaluation.conformity import conformity_analysis
from cinoc.evaluation.context import CrossEngineContext, DocContext
from cinoc.evaluation.correction import correction_analysis
from cinoc.evaluation.decisions import decisions_analysis
from cinoc.evaluation.economics import economics_analysis
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.inference import inference_analysis
from cinoc.evaluation.ner import EntitySet
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

#: { pipeline_name: { document_id: { step_id: { ArtifactType: Artifact } } } } —
#: les sorties de **chaque** étape (``by_step``), dans l'ordre d'exécution.
PipelineOutputs = Mapping[str, Mapping[str, StepArtifacts]]

#: Signature d'entrée d'une métrique : ``(type_référence, type_hypothèse)``.
_Signature = tuple[ArtifactType, ArtifactType]

#: { métrique : { pipeline : [score par doc, aligné, ``None`` inclus] } }
_Series = dict[str, dict[str, list[MetricScore]]]

#: Types **inter-changeables au niveau représentation** : tous chargés en ``str``.
#: Un candidat ``CORRECTED_TEXT`` est donc noté par une métrique ``RAW_TEXT`` sans
#: projection (les post-corrections LLM passent telles quelles).
_TEXT_LIKE = frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT})


#: Les ``kind`` d'analyse que ce runner sait produire. Une spec qui en nomme un
#: autre est refusée **au chargement** plutôt que de rendre un résultat
#: silencieusement amputé — même contrat que ``metric_names`` face au registre.
ANALYSES_CONNUES: frozenset[str] = frozenset(COLLECTEURS.values()) | frozenset(
    {"calibration", "correction", "decisions", "economics", "hipe", "inference"}
)


#: Valeur de spec réclamant le **mode détaillé** — toutes les analyses.
TOUTES_LES_ANALYSES = "toutes"


def _analyses_actives(evaluation: EvaluationSpec) -> frozenset[str] | None:
    """``None`` = l'ensemble demandé ; ``None`` retourné = toutes.

    Le **défaut est le mode rapide** : une spec qui ne dit rien ne paie que ses
    métriques. ``"toutes"`` réclame le mode détaillé, entier.
    """
    if evaluation.analyses == TOUTES_LES_ANALYSES:
        return None
    if evaluation.analyses is None:
        return frozenset()
    voulues = frozenset(evaluation.analyses)
    inconnues = sorted(voulues - ANALYSES_CONNUES)
    if inconnues:
        raise EvaluationError(
            "analyses inconnues : "
            + ", ".join(repr(k) for k in inconnues)
            + f" — connues : {', '.join(sorted(ANALYSES_CONNUES))}."
        )
    return voulues



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
    actives = _analyses_actives(evaluation)
    failed = frozenset(
        (u.pipeline, u.document_id) for u in usage if u.outcome == "failed"
    )
    max_error = evaluation.failure_policy == "max_error"
    # Les analyses qui lisent la sortie **finale** d'un pipeline (calibration,
    # correction, décisions) en lisent le pool : une lecture de ``by_step``.
    pools = {
        pipeline: {
            document_id: latest_by_type(by_step)
            for document_id, by_step in by_document.items()
        }
        for pipeline, by_document in pipeline_outputs.items()
    }

    for view in evaluation.views:
        series: _Series = {name: {} for name in view.metric_names}
        collectors = ViewCollectors(view, actives)
        for pipeline_name in pipeline_order:
            for name in view.metric_names:
                series[name][pipeline_name] = []
            #: Unités en échec qui **auraient** été notées, par métrique : la
            #: différence entre « n attendus » et « n notés ».
            missed = dict.fromkeys(view.metric_names, 0)
            for document in corpus.documents:
                if (pipeline_name, document.id) in failed:
                    scores = _score_failed(view, document, registry, max_error)
                    for score in scores:
                        if score.value is None and _expects(
                            view, document, registry, score.metric
                        ):
                            missed[score.metric] += 1
                    # Rien n'a été produit : aucune analyse ne s'en nourrit,
                    # même notée à l'erreur maximale (pas de texte fabriqué).
                    text_context = entity_context = None
                else:
                    candidate = _candidate_for(
                        view,
                        pipeline_name,
                        pipeline_outputs.get(pipeline_name, {}).get(document.id, {}),
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
                        _aggregate(name, series[name][pipeline_name], missed[name])
                        for name in view.metric_names
                    ),
                )
            )
        cross_engine.extend(_cross_engine_scores(view, series, registry))
        if actives is None or "inference" in actives:
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
        calibration = None
        if actives is None or "calibration" in actives:
            calibration = calibration_analysis(view.name, corpus, pools)
        if calibration is not None:
            analyses.append(calibration)
        if "cer" in view.metric_names and (actives is None or "economics" in actives):
            economics = economics_analysis(
                view.name, "cer", series["cer"], usage, manifest
            )
            if economics is not None:
                analyses.append(economics)
        correction = None
        if actives is None or "correction" in actives:
            correction = correction_analysis(view, corpus, pools)
        if correction is not None:
            analyses.append(correction)
        # Ce qu'un correcteur a **refusé** de changer : invisible dans le texte
        # de sortie, donc invisible partout ailleurs.
        decisions = None
        if actives is None or "decisions" in actives:
            decisions = decisions_analysis(view.name, pools)
        if decisions is not None:
            analyses.append(decisions)

    # Post-passe cross-vues : la conformité HIPE lit les résultats des vues
    # raw/hipe/heritage déjà calculés (zéro re-scoring) — cf. ``conformity``.
    conformity = (
        conformity_analysis(evaluation.views, pipelines, documents)
        if actives is None or "hipe" in actives
        else None
    )
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


def _aggregate(name: str, scores: list[MetricScore], missed: int) -> MetricScore:
    """Agrégat **micro** : Σ(valeur·poids)/Σpoids — la métrique au niveau corpus.

    Micro (et non la moyenne *macro* des taux par-document) est la métrique
    conventionnelle au niveau corpus, comparable à ``jiwer`` sur le corpus
    entier : un long document pèse à proportion de sa taille. La moyenne macro
    reste reconstructible depuis le détail par-document (``RunResult.documents``).
    Les documents à poids nul (référence vide) sont exclus du micro ; ``value``
    vaut ``None`` si aucun poids (toutes réfs vides). ``support`` = nombre de
    documents notés ; ``expected`` = ``support`` + les unités en échec qui
    auraient pu l'être (``missed``) — « n notés / n attendus » (arbitrage A3).
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
    return MetricScore(
        metric=name, value=micro, support=len(pairs), expected=len(pairs) + missed
    )


def _empty_hypothesis(hypothesis_type: ArtifactType) -> object | None:
    """Hypothèse **vide** du type : ce qu'aurait rendu un moteur sans sortie.

    Sert uniquement à demander à la métrique le **poids** de la référence ; la
    valeur notée, elle, est la borne de l'échelle (cf. ``_score_failed``).
    """
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


def _expects(
    view: EvaluationView, document: DocumentRef, registry: MetricRegistry, name: str
) -> bool:
    """Une unité de ce document est-elle **attendue** pour cette métrique ?

    Oui si sa vérité terrain l'alimente : c'est ce qui sépare un échec (l'unité
    aurait été notée) d'un cas que la métrique ne couvre de toute façon pas.
    """
    metric = registry.document_metric(name)
    if metric is None:
        raise EvaluationError(f"métrique inconnue : {name!r}.")
    return _resolve_ground_truth(document, view, metric.input_types[0]) is not None


def _score_failed(
    view: EvaluationView,
    document: DocumentRef,
    registry: MetricRegistry,
    max_error: bool,
) -> tuple[MetricScore, ...]:
    """Scores d'une unité **en échec**, selon la politique d'échec.

    ``exclude`` : tout ``None`` — l'unité sort de la moyenne, et « n attendus »
    le dit. ``max_error`` : la pire valeur de l'échelle — 1 pour un taux
    d'erreur, 0 pour un score —, avec le **poids** que la métrique donne à la
    référence face à une sortie vide (la longueur de la référence pour le CER :
    exactement le CER d'une page rendue vide). Une métrique qui ne sait pas
    peser une sortie vide reste ``None`` : on ne fabrique pas de poids.
    """
    scores: list[MetricScore] = []
    for name in view.metric_names:
        metric = registry.document_metric(name)
        if metric is None:
            raise EvaluationError(f"métrique inconnue : {name!r}.")
        if not max_error:
            scores.append(MetricScore(metric=name))
            continue
        reference_type, hypothesis_type = metric.input_types
        reference = _reference_for(view, document, reference_type)
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
        if observation is None:
            scores.append(MetricScore(metric=name))
            continue
        worst = 0.0 if metric.spec.higher_is_better else 1.0
        scores.append(
            MetricScore(metric=name, value=worst, support=observation.weight)
        )
    return tuple(scores)


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


def _candidate_for(
    view: EvaluationView, pipeline_name: str, by_step: StepArtifacts
) -> Artifact | None:
    """L'artefact à noter : la sortie candidate de l'étape que la vue **vise**.

    ``view.target_step`` nommée → cette étape. Sinon, l'étape la plus **aval**
    (``by_step`` est dans l'ordre d'exécution) qui produit un type candidat.
    Choisir par *type* notait un intermédiaire dès qu'une étape en aval
    reproduisait un type plus « brut » (``… → correction VLM → ordre de lecture
    → projection`` : texte corrigé noté **avant** la remise en ordre, CER 0,8842
    au lieu de 0,8079) — et rendait l'étape amont d'un type répété impossible à
    noter. Il n'y a plus de précédence par type : une étape qui publie plusieurs
    types candidats rend la vue ambiguë (refusée au chargement pour les types
    déclarés, ici pour ceux qu'un module publierait sans les déclarer).
    """
    if view.target_step is not None:
        steps: list[Mapping[ArtifactType, Artifact]] = [
            by_step.get(view.target_step, {})
        ]
    else:
        steps = list(reversed(list(by_step.values())))
    for outputs in steps:
        présents = sorted(
            (t for t in outputs if t in view.candidate_types), key=lambda t: t.value
        )
        if len(présents) > 1:
            raise EvaluationError(
                f"vue {view.name!r}, pipeline {pipeline_name!r} : une même étape "
                f"publie plusieurs types candidats ({', '.join(présents)}) — "
                "restreignez 'candidate_types' à celui qui doit être noté."
            )
        if présents:
            return outputs[présents[0]]
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
    if _resolve_ground_truth(document, view, reference_type) is None:
        return None
    reference = _reference_for(view, document, reference_type)
    hypothesis = _project_side(candidate.uri, candidate.type, hypothesis_type, view)
    if reference is None or hypothesis is None:
        return None
    return DocContext(
        document_id=document.id,
        reference=reference,
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
