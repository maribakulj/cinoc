"""``evaluate_run`` — le runner (par-document → agrégat → inter-moteurs).

Reçoit des **artefacts déjà produits** (couche 4, via l'app) : il n'exécute aucun
moteur et n'importe pas ``pipeline``. **Trois passes** par vue : (1) par-document
— la **statistique suffisante** de chaque métrique, son scalaire et ses axes ;
(2) agrégat par pipeline — la finalisation de la **somme** des statistiques
(micro exact, K1), **support** exposé ; (3) **inter-moteurs** — chaque
``CrossEngineMetric`` compare les pipelines et écrit dans
``RunResult.cross_engine``. La notation par document (statistique, scalaire,
axes, normalisation de la vue) vit dans ``evaluation.scoring`` ; les agrégats
(deux qualités, couverture, macro) et les supports apparié et global, dans
``evaluation.aggregation``.
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
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.run import RunManifest
from cinoc.domain.usage import LineOutcomes
from cinoc.evaluation._view_collectors import COLLECTEURS, ViewCollectors
from cinoc.evaluation.aggregation import (
    ClusterKey,
    cluster_key,
    comparison_payload,
    complete_statistic,
    invention_payload,
    publish,
)
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
from cinoc.evaluation.scoring import (
    ReferenceProbe,
    declares_view,
    metric_of,
    score_unit,
    view_outcome,
)
from cinoc.evaluation.statistics import Counts, reference_defines

#: { pipeline_name: { document_id: { step_id: { ArtifactType: Artifact } } } } —
#: les sorties de **chaque** étape (``by_step``), dans l'ordre d'exécution.
PipelineOutputs = Mapping[str, Mapping[str, StepArtifacts]]

#: { métrique : { pipeline : [score par doc, aligné] } }
_Series = dict[str, dict[str, list[MetricScore]]]

#: { métrique : { pipeline : [statistique opérationnelle par doc, alignée] } }
_Operational = dict[str, dict[str, list[Counts | None]]]

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
    pipeline_specs = {spec.name: spec for spec in manifest.pipeline_specs}
    pipelines: list[PipelineResult] = []
    documents: list[RunDocumentResult] = []
    cross_engine: list[MetricScore] = []
    analyses: list[Analysis] = []
    #: Séries de chaque (vue × métrique **établie**) : la famille de Holm est
    #: le run entier, réduit aux métriques établies (D-289).
    tests: list[InferenceEntry] = []
    actives = _analyses_actives(evaluation)
    empty_page = evaluation.failure_policy == "empty_page"
    #: L'état d'exécution **déclaré** de chaque unité (issue, motif, issues de
    #: lignes) : lu tel quel, jamais reconstruit d'après les textes (§ 2.1 f).
    units = {(u.pipeline, u.document_id): u for u in usage}
    document_ids = [document.id for document in corpus.documents]
    #: Grappe de chaque document (un document sans grappe est la sienne, B3).
    clusters = [
        cluster_key(document.cluster, document.id) for document in corpus.documents
    ]
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
        operational: _Operational = {name: {} for name in view.metric_names}
        collectors = ViewCollectors(view, actives)
        #: La **famille** de la vue : les pipelines dont une étape déclare un type
        #: candidat. Un pipeline hors vue n'entre dans aucun agrégat, support,
        #: tri ni test de cette vue, et ses échecs ne changent le support de
        #: personne (D1).
        family = [
            name for name in pipeline_order if declares_view(view, pipeline_specs[name])
        ]
        # La référence de chaque document, lue **une fois** pour tous les pipelines.
        probes = {
            document.id: ReferenceProbe(view, document, registry)
            for document in corpus.documents
        }
        for pipeline_name in pipeline_order:
            for name in view.metric_names:
                series[name][pipeline_name] = []
                operational[name][pipeline_name] = []
            by_document = pipeline_outputs.get(pipeline_name, {})
            for document in corpus.documents:
                by_step = by_document.get(document.id, {})
                found = _scored_step(view, pipeline_name, by_step)
                candidate = None if found is None else found[1][found[2]]
                unit = units.get((pipeline_name, document.id))
                step_id = None if found is None else found[0]
                scored = score_unit(
                    view,
                    probes[document.id],
                    candidate,
                    pipeline_name in family,
                    view_outcome(unit, list(by_step), step_id),
                    None if unit is None else unit.reason,
                    registry,
                    empty_page,
                )
                collectors.observe(
                    pipeline_name,
                    document.id,
                    scored.scores,
                    scored.text_context,
                    scored.entity_context,
                )
                for name, score, stat in zip(
                    view.metric_names, scored.scores, scored.operational, strict=True
                ):
                    series[name][pipeline_name].append(score)
                    operational[name][pipeline_name].append(stat)
                documents.append(
                    RunDocumentResult(
                        document_id=document.id,
                        pipeline=pipeline_name,
                        view=view.name,
                        scores=scored.scores,
                        stratum=document.metadata.get("stratum"),
                        cluster=document.cluster,
                        image_ref=document.image_uri,
                    )
                )
            if pipeline_name in family:
                pipelines.append(
                    _pipeline_result(
                        pipeline_name,
                        view.name,
                        [metric_of(registry, name) for name in view.metric_names],
                        series,
                        operational,
                        clusters,
                        corpus,
                        _line_outcomes(pipeline_name, units),
                    )
                )
        in_family = {
            name: {
                pipeline: rows
                for pipeline, rows in by_pipeline.items()
                if pipeline in family
            }
            for name, by_pipeline in series.items()
        }
        cross_engine.extend(_cross_engine_scores(view, in_family, registry))
        tests.extend(_inference_entries(view, in_family, registry))
        analyses.extend(
            _support_analyses(
                view.name,
                [metric_of(registry, name) for name in view.metric_names],
                family,
                series,
                operational,
                document_ids,
                clusters,
                corpus.cluster_weighting,
                probes,
                empty_page,
            )
        )
        analyses.extend(
            collectors.build(
                view.name,
                document_ids,
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
        conformity_analysis(
            evaluation.views, pipelines, documents, evaluation.failure_policy
        )
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


def _pipeline_result(
    pipeline: str,
    view: str,
    metrics: list[DocumentMetric],
    series: _Series,
    operational: _Operational,
    clusters: list[ClusterKey],
    corpus: CorpusSpec,
    line_outcomes: LineOutcomes | None,
) -> PipelineResult:
    """Les agrégats d'un pipeline : les deux qualités.

    **Conditionnelle** : la finalisation de la **somme** des statistiques des
    observations complètes (le micro, K1 : Σ erreurs / Σ longueurs de référence
    pour un taux d'erreur, F1(Σtp, Σfp, Σfn) pour un F1, max(0, 1 − Σe/Σn) pour
    une exactitude — plancher au corpus, B1) ; une page à référence vide y entre
    par sa statistique. **Opérationnelle** : ce que l'utilisateur reçoit — les
    partielles et tronquées telles que produites, les échecs comme une sortie
    vide. Les deux portent la **même** couverture (« n notés / n attendus » et
    ses motifs). ``failure_policy`` choisit la principale, que
    ``RunResult.principal_aggregate`` dérive : ``exclude`` → conditionnelle,
    ``empty_page`` → opérationnelle (§ 2.1 e, f) ; elle n'est pas stockée.
    """
    conditional: list[MetricScore] = []
    operational_scores: list[MetricScore] = []
    for metric in metrics:
        scores = series[metric.name][pipeline]
        conditional.append(
            publish(
                metric,
                [
                    (index, stat)
                    for index, score in enumerate(scores)
                    if (stat := complete_statistic(score)) is not None
                ],
                scores,
                clusters,
                corpus.cluster_weighting,
            )
        )
        operational_scores.append(
            publish(
                metric,
                [
                    (index, stat)
                    for index, stat in enumerate(operational[metric.name][pipeline])
                    if stat is not None
                ],
                scores,
                clusters,
                corpus.cluster_weighting,
            )
        )
    return PipelineResult(
        pipeline=pipeline,
        view=view,
        conditional_aggregate=tuple(conditional),
        operational_aggregate=tuple(operational_scores),
        target_population=corpus.target_population,
        cluster_weighting=corpus.cluster_weighting,
        line_outcomes=line_outcomes,
    )


def _line_outcomes(
    pipeline: str, units: Mapping[tuple[str, str], DocumentUsage]
) -> LineOutcomes | None:
    """Somme des issues de lignes des unités d'un pipeline (``None`` : aucune
    étape de correction structurée n'en a déclaré)."""
    total: LineOutcomes | None = None
    for (name, _), unit in sorted(units.items()):
        if name == pipeline and unit.line_outcomes is not None:
            total = unit.line_outcomes.merged_with(total)
    return total


def _support_analyses(
    view: str,
    metrics: list[DocumentMetric],
    family: list[str],
    series: _Series,
    operational: _Operational,
    document_ids: list[str],
    clusters: list[ClusterKey],
    weighting: str,
    probes: Mapping[str, ReferenceProbe],
    empty_page: bool,
) -> list[Analysis]:
    """Supports apparié et global, et invention hors référence, par métrique.

    Seuls les pipelines de la **famille** de la vue y entrent (un pipeline hors
    vue n'est comparable à personne et ne change le support de personne), et,
    parmi eux, ceux que la métrique lit. Les observations sont celles de
    l'agrégat **principal** : complètes sous ``exclude``, opérationnelles sous
    ``empty_page`` — le Δ, le tri et le test exploratoire qui l'accompagne ont
    ainsi le même support (§ 2.1 c, A4, A6 ; D10).
    """
    out: list[Analysis] = []
    for metric in metrics:
        viewed = [
            pipeline
            for pipeline in family
            if any(
                score.applicability != "not_in_view"
                for score in series[metric.name][pipeline]
            )
        ]
        if len(viewed) < 2:
            continue
        stats = {
            pipeline: (
                list(operational[metric.name][pipeline])
                if empty_page
                else [complete_statistic(s) for s in series[metric.name][pipeline]]
            )
            for pipeline in viewed
        }
        comparison = comparison_payload(
            metric, viewed, stats, document_ids, clusters, weighting
        )
        if comparison is not None:
            out.append(Analysis(scope="corpus", view=view, payload=comparison))
        applicable = {
            pipeline: [
                s.applicability == "applicable" for s in series[metric.name][pipeline]
            ]
            for pipeline in viewed
        }
        without = [
            _without_reference(
                metric,
                probes[document_id],
                [operational[metric.name][p][index] for p in viewed],
                any(applicable[p][index] for p in viewed),
            )
            for index, document_id in enumerate(document_ids)
        ]
        invention = invention_payload(
            metric, viewed, stats, document_ids, without, applicable
        )
        if invention is not None:
            out.append(Analysis(scope="corpus", view=view, payload=invention))
    return out


def _without_reference(
    metric: DocumentMetric,
    probe: ReferenceProbe,
    stats: list[Counts | None],
    applicable: bool,
) -> bool:
    """La **référence** du document ne définit pas le scalaire de la métrique.

    Lu sur la statistique d'un pipeline qui en a une (elle porte n_réf, ou
    tp + fn), sinon sur la référence face à une sortie vide : jamais sur le
    scalaire d'un pipeline (R5)."""
    if not applicable:
        return False
    found = next((stat for stat in stats if stat is not None), None)
    if found is None:
        found = probe.empty_statistic(metric)
    return found is not None and not reference_defines(found)


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
                    status="exploratory",
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
