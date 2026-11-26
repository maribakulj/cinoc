"""Export CSV d'un ``RunResult`` (couche 7) — lecture pure, zéro recalcul.

Un seul fichier, tableur-compatible : une ligne par score, colonne ``scope``
(``aggregate`` ou ``document``). Ordre = celui du ``RunResult`` (déterministe).
``expected`` (agrégats) = « n attendus » face à ``support`` (« n notés ») ;
``outcome`` (documents) = issue de l'unité, ``failed:<motif>`` en cas d'échec —
une valeur vide n'a pas le même sens selon qu'elle vient d'un échec ou d'une
métrique inapplicable. Les lignes ``usage`` portent la durée de chaque unité
(``duration_seconds``, wall-clock de l'exécuteur, vide si non mesurée) : une
par (pipeline × document), sans vue — l'exécution n'a lieu qu'une fois. Une
unité **relue de l'archive** n'a pas été mesurée par ce run : sa ligne s'appelle
``duration_seconds_first_run`` (la durée de sa première exécution, D10).
"""

from __future__ import annotations

import csv
import io

from cinoc.evaluation.result import RunResult

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
)


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
    for pipeline in result.pipelines:
        for score in pipeline.aggregate:
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
            )
        )
    return buffer.getvalue()


__all__ = ["run_result_csv"]
