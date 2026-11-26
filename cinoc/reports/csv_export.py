"""Export CSV d'un ``RunResult`` (couche 7) — lecture pure, zéro recalcul.

Un seul fichier, tableur-compatible : une ligne par score, colonne ``scope``
(``aggregate`` ou ``document``). Ordre = celui du ``RunResult`` (déterministe).
``expected`` (agrégats) = « n attendus » face à ``support`` (« n notés ») ;
``outcome`` (documents) = issue de l'unité, ``failed:<motif>`` en cas d'échec —
une valeur vide n'a pas le même sens selon qu'elle vient d'un échec ou d'une
métrique inapplicable.
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
    """CSV des agrégats puis du détail par-document (UTF-8, séparateur ``,``)."""
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
    return buffer.getvalue()


__all__ = ["run_result_csv"]
