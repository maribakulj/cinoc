"""Export CSV d'un ``RunResult`` (couche 7) — lecture pure, zéro recalcul.

Un seul fichier, tableur-compatible : une ligne par score, colonne ``scope``
(``aggregate`` ou ``document``). Ordre = celui du ``RunResult`` (déterministe).
Un pipeline a **deux** lignes d'agrégat par métrique, une par qualité : la
colonne ``quality`` dit ``conditional`` ou ``operational`` (les noms des champs
stockés) et ``principal`` marque (``true``) celle que la politique d'échec du run
désigne comme principale (« publié veut dire affiché »).
``expected`` (agrégats) = « n attendus » face à ``support`` (« n notés ») ;
``outcome`` (documents) = issue de l'unité, ``failed:<motif>`` en cas d'échec —
une valeur vide n'a pas le même sens selon qu'elle vient d'un échec ou d'une
métrique inapplicable. Les lignes ``usage`` portent la durée de chaque unité
(``duration_seconds``, wall-clock de l'exécuteur, vide si non mesurée) : une
par (pipeline × document), sans vue — l'exécution n'a lieu qu'une fois. Une
unité **relue de l'archive** n'a pas été mesurée par ce run : sa ligne s'appelle
``duration_seconds_first_run`` (la durée de sa première exécution, D10).

Les trois dernières colonnes publient ce que la valeur ne dit pas seule (K1,
B1) : ``statistic`` — les comptes de la statistique suffisante
(``famille:composante=n;…``), dont la valeur est la finalisation ;
``scalar_reason`` — pourquoi une valeur est vide alors que ses comptes
existent (``zero_denominator``) ; ``untruncated_error_rate`` — le taux
d'erreur d'une exactitude avant son plancher à 0.
"""

from __future__ import annotations

import csv
import io

from cinoc.evaluation.result import MetricScore, RunResult

_HEADER = (
    "scope",
    "view",
    "pipeline",
    "document_id",
    "metric",
    "value",
    "support",
    "expected",
    "outcome",
    "statistic",
    "scalar_reason",
    "untruncated_error_rate",
    "quality",
    "principal",
)


def _published(score: MetricScore) -> tuple[str, str, str]:
    """``(statistic, scalar_reason, untruncated_error_rate)`` d'un score."""
    statistic = ""
    if score.stat is not None:
        fields = score.stat.model_dump(exclude={"family"})
        statistic = f"{score.stat.family}:" + ";".join(
            f"{name}={value}" for name, value in fields.items()
        )
    rate = score.untruncated_error_rate
    return statistic, score.scalar_reason or "", "" if rate is None else repr(rate)


def run_result_csv(result: RunResult) -> str:
    """CSV des agrégats, du détail par-document puis des durées par unité
    (UTF-8, séparateur ``,``)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_HEADER)
    outcomes = {
        (u.pipeline, u.document_id): (
            f"{u.outcome}:{u.reason}" if u.reason is not None else u.outcome
        )
        for u in result.usage
    }
    empty_page = result.manifest.failure_policy == "empty_page"
    principal = "operational" if empty_page else "conditional"
    for pipeline in result.pipelines:
        for quality, scores in (
            ("conditional", pipeline.conditional_aggregate),
            ("operational", pipeline.operational_aggregate),
        ):
            for score in scores:
                writer.writerow(
                    (
                        "aggregate",
                        pipeline.view,
                        pipeline.pipeline,
                        "",
                        score.metric,
                        "" if score.value is None else repr(score.value),
                        "" if score.support is None else score.support,
                        "" if score.expected is None else score.expected,
                        "",
                        *_published(score),
                        quality,
                        "true" if quality == principal else "false",
                    )
                )
    for document in result.documents:
        for score in document.scores:
            writer.writerow(
                (
                    "document",
                    document.view,
                    document.pipeline,
                    document.document_id,
                    score.metric,
                    "" if score.value is None else repr(score.value),
                    "" if score.support is None else score.support,
                    "",
                    outcomes.get((document.pipeline, document.document_id), ""),
                    *_published(score),
                    "",
                    "",
                )
            )
    for unit in result.usage:
        duration = unit.usage.duration_seconds
        writer.writerow(
            (
                "usage",
                "",
                unit.pipeline,
                unit.document_id,
                "duration_seconds_first_run" if unit.resumed else "duration_seconds",
                "" if duration is None else repr(duration),
                "",
                "",
                outcomes.get((unit.pipeline, unit.document_id), ""),
                "",
                "",
                "",
                "",
                "",
            )
        )
    return buffer.getvalue()


__all__ = ["run_result_csv"]
