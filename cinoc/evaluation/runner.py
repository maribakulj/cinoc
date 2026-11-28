"""``evaluate_run`` — le runner (par-document → agrégat → inter-moteurs).

Reçoit des **artefacts déjà produits** (couche 4, via l'app) : il n'exécute aucun
moteur et n'importe pas ``pipeline``. **Trois passes** par vue : (1) par-document
— la **statistique suffisante** de chaque métrique, son scalaire et ses axes ;
(2) agrégat par pipeline — la finalisation de la **somme** des statistiques
(micro exact, K1), **support** exposé ; (3) **inter-moteurs** — chaque
``CrossEngineMetric`` compare les pipelines et écrit dans
``RunResult.cross_engine``. La notation par document (statistique, scalaire,
axes, normalisation de la vue) vit dans ``evaluation.scoring``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from cinoc.domain.artifacts import (
    Artifact,
    ArtifactType,
    StepArtifacts,
    latest_by_type,
)
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.run import RunManifest
from cinoc.evaluation._view_collectors import COLLECTEURS, ViewCollectors
from cinoc.evaluation.calibration import calibration_analysis
from cinoc.evaluation.conformity import conformity_analysis
from cinoc.evaluation.context import CrossEngineContext
from cinoc.evaluation.correction import correction_analysis
from cinoc.evaluation.decisions import decisions_analysis
from cinoc.evaluation.economics import economics_analysis
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.inference import InferenceEntry, inference_analyses
from cinoc.evaluation.metric import DocumentMetric
from cinoc.evaluation.registry import MetricRegistry
from cinoc.evaluation.result import (
    Analysis,
    DocumentUsage,
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.evaluation.scoring import metric_of, score_document, score_failed
from cinoc.evaluation.statistics import Counts, Scalar, combine

#: { pipeline_name: { document_id: { step_id: { ArtifactType: Artifact } } } } —
#: les sorties de **chaque** étape (``by_step``), dans l'ordre d'exécution.
PipelineOutputs = Mapping[str, Mapping[str, StepArtifacts]]

#: { métrique : { pipeline : [score par doc, aligné, ``None`` inclus] } }
_Series = dict[str, dict[str, list[MetricScore]]]

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
    #: Séries de chaque (vue × métrique **établie**) : la famille de Holm est
    #: le run entier, réduit aux métriques établies (D-289).
    tests: list[InferenceEntry] = []
    actives = _analyses_actives(evaluation)
    failed = frozenset(
        (u.pipeline, u.document_id) for u in usage if u.outcome == "failed"
    )
    truncated = frozenset(
        (u.pipeline, u.document_id) for u in usage if u.outcome == "truncated"
    )
    empty_page = evaluation.failure_policy == "empty_page"
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
                    scores = score_failed(view, document, registry, empty_page)
                    for score in scores:
                        if score.stat is None and score.applicability == "applicable":
                            missed[score.metric] += 1
                    # Rien n'a été produit : aucune analyse ne s'en nourrit,
                    # même notée comme une page vide (pas de texte fabriqué).
                    text_context = entity_context = None
                else:
                    candidate = _candidate_for(
                        view,
                        pipeline_name,
                        pipeline_outputs.get(pipeline_name, {}).get(document.id, {}),
                    )
                    scores, text_context, entity_context = score_document(
                        view,
                        document,
                        candidate,
                        registry,
                        (pipeline_name, document.id) in truncated,
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
                        _aggregate(
                            metric_of(registry, name),
                            series[name][pipeline_name],
                            missed[name],
                        )
                        for name in view.metric_names
                    ),
                )
            )
        cross_engine.extend(_cross_engine_scores(view, series, registry))
        tests.extend(_inference_entries(view, series, registry))
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
            # Les confiances de l'étape **notée** (D-285, D9) : celles d'un OCR
            # ne disent rien du texte qu'un LLM a corrigé derrière lui.
            calibration = calibration_analysis(
                view, corpus, _scored_steps(view, pipeline_outputs)
            )
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

    # Tests inter-moteurs **toujours** calculés (coût négligeable), corrigés
    # sur le run entier ; l'IC bootstrap, lui, reste au mode détaillé.
    analyses.extend(
        inference_analyses(
            tests, with_intervals=actives is None or "inference" in actives
        )
    )

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


def _inference_entries(
    view: EvaluationView, series: _Series, registry: MetricRegistry
) -> list[InferenceEntry]:
    """(vue, métrique, séries alignées, termes) de chaque métrique **établie**
    de la vue — les seules qu'un test départage (D-289) : une adaptée ou une
    exploratoire reste au diagnostic et ne grossit pas la famille de Holm.

    Les **mêmes séries** que la passe inter-moteurs : même index = même
    document, ``None`` = non applicable — un seul calcul des scores, deux
    lectures (scalaire ``significance_p`` + payload ``inference``). Les termes
    (numérateur, dénominateur) sont ceux de la statistique de chaque document
    qui entre au micro affiché ; ``None`` pour une métrique dont le
    dénominateur dépend de l'hypothèse : l'inférence de son micro est « non
    estimable » (B9c).
    """
    entries: list[InferenceEntry] = []
    for metric_name in registry.established(view.metric_names):
        terms = metric_of(registry, metric_name).terms
        entries.append(
            (
                view.name,
                metric_name,
                {
                    pipeline: [score.value for score in scores]
                    for pipeline, scores in series[metric_name].items()
                },
                None
                if terms is None
                else {
                    pipeline: [
                        None if score.stat is None else terms(score.stat)
                        for score in scores
                    ]
                    for pipeline, scores in series[metric_name].items()
                },
            )
        )
    return entries


def _aggregate(
    metric: DocumentMetric, scores: list[MetricScore], missed: int
) -> MetricScore:
    """Agrégat **micro** : la finalisation de la **somme** des statistiques.

    Le micro est la métrique calculée sur les comptes cumulés du corpus — pour
    un taux d'erreur, Σ erreurs / Σ longueurs de référence, comparable à
    ``jiwer`` sur le corpus entier ; pour un F1, F1(Σtp, Σfp, Σfn) ; pour une
    exactitude, max(0, 1 − Σe/Σn), plancher au corpus (B1). Une page à
    référence vide entre au micro par sa statistique (ses insertions) même si
    son scalaire est indéfini. ``support`` = documents dont la statistique
    entre au micro ; ``expected`` = ``support`` + les unités en échec qui
    auraient pu l'être (``missed``) — « n notés / n attendus » (arbitrage A3).
    """
    stats = [score.stat for score in scores if score.stat is not None]
    combined = combine(stats)
    if combined is None:
        return MetricScore(metric=metric.name, support=0, expected=missed)
    return _score(metric.name, metric.finalize, combined).model_copy(
        update={"support": len(stats), "expected": len(stats) + missed}
    )


def _score(
    name: str, finalize: Callable[[Any], Scalar], stat: Counts
) -> MetricScore:
    """Le ``MetricScore`` d'une statistique sous la finalisation de sa métrique."""
    scalar = finalize(stat)
    return MetricScore(
        metric=name,
        value=scalar.value,
        stat=stat,
        scalar_reason=scalar.reason,
        untruncated_error_rate=scalar.untruncated_error_rate,
    )


def _cross_engine_scores(
    view: EvaluationView, series: _Series, registry: MetricRegistry
) -> list[MetricScore]:
    metrics = registry.cross_engine_metrics()
    if not metrics:
        return []
    scores: list[MetricScore] = []
    # Le scalaire ``significance_p`` est la p du même test : établies seules.
    for base_metric in registry.established(view.metric_names):
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
    """L'artefact à noter (cf. :func:`_scored_step`)."""
    scored = _scored_step(view, pipeline_name, by_step)
    return None if scored is None else scored[1][scored[2]]


def _scored_step(
    view: EvaluationView, pipeline_name: str, by_step: StepArtifacts
) -> tuple[str, Mapping[ArtifactType, Artifact], ArtifactType] | None:
    """``(étape, ses sorties, type noté)`` : l'étape dont la vue note la sortie.

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
        steps: list[tuple[str, Mapping[ArtifactType, Artifact]]] = [
            (view.target_step, by_step.get(view.target_step, {}))
        ]
    else:
        steps = list(reversed(list(by_step.items())))
    for step_id, outputs in steps:
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
            return step_id, outputs, présents[0]
    return None


def _scored_steps(
    view: EvaluationView, pipeline_outputs: PipelineOutputs
) -> dict[str, dict[str, tuple[str, Mapping[ArtifactType, Artifact]]]]:
    """``{pipeline: {document: (étape notée, ses sorties)}}`` pour la vue."""
    out: dict[str, dict[str, tuple[str, Mapping[ArtifactType, Artifact]]]] = {}
    for pipeline, by_document in pipeline_outputs.items():
        for document_id, by_step in by_document.items():
            scored = _scored_step(view, pipeline, by_step)
            if scored is not None:
                out.setdefault(pipeline, {})[document_id] = scored[:2]
    return out


__all__ = ["PipelineOutputs", "evaluate_run"]
