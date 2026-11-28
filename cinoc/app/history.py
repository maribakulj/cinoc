"""Historique longitudinal : enregistrement d'un run + lecture analysée (couche 6).

Trait d'union entre le ``RunResult`` (couche 3, agrégats par pipeline/vue) et le
``HistoryStore`` (couche 5, qui ne connaît que des lignes primitives). C'est ici —
et pas dans le store — que vit la connaissance de la forme du ``RunResult`` :
le store reste une persistance pure, réutilisable.

Dans l'autre sens, ``series_insight`` analyse une série d'enregistrements :
conversion des horodatages ISO (stricte — ligne illisible journalisée puis
écartée, jamais un skip muet) puis tendance OLS + test de rupture de Pettitt
(``evaluation.longitudinal``). Consommé par la page ``/history``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from cinoc.adapters.storage.history_store import HistoryRecord, HistoryStore
from cinoc.evaluation.longitudinal import (
    MIN_POINTS_FOR_TEST,
    PettittResult,
    TrendResult,
    linear_trend,
    pettitt,
)
from cinoc.evaluation.result import RunResult

logger = logging.getLogger(__name__)


def records_from_run(run_result: RunResult) -> tuple[HistoryRecord, ...]:
    """Aplatit un ``RunResult`` en lignes d'historique (métriques applicables).

    Chaque ligne porte le **profil de normalisation** de sa vue, lu dans
    ``manifest.view_specs`` (D-288) : c'est, avec le corpus, ce qui distingue
    deux séries. Une vue que le manifeste ne déclare pas n'a pas de profil
    connu : ses agrégats ne sont **pas** enregistrés (avertissement), plutôt
    que rangés sous un profil deviné.
    """
    manifest = run_result.manifest
    completed_at = manifest.completed_at.isoformat()
    profiles = {view.name: view.normalization_profile for view in manifest.view_specs}
    records: list[HistoryRecord] = []
    for pipeline in run_result.pipelines:
        if pipeline.view not in profiles:
            logger.warning(
                "[history] vue %r absente du manifeste (run %s) : profil inconnu, "
                "agrégats de %s non enregistrés.",
                pipeline.view,
                manifest.run_id,
                pipeline.pipeline,
            )
            continue
        for score in pipeline.aggregate:
            if score.value is None:
                continue
            records.append(
                HistoryRecord(
                    run_id=manifest.run_id,
                    completed_at=completed_at,
                    corpus_name=manifest.corpus_name,
                    normalization_profile=profiles[pipeline.view],
                    code_version=manifest.code_version,
                    pipeline=pipeline.pipeline,
                    view=pipeline.view,
                    metric=score.metric,
                    value=score.value,
                )
            )
    return tuple(records)


def record_run(store: HistoryStore, run_result: RunResult) -> int:
    """Persiste les agrégats d'un run dans l'historique ; renvoie le compte."""
    return store.add(records_from_run(run_result))


@dataclass(frozen=True)
class SeriesInsight:
    """Tendance + rupture d'une série (corpus, profil, pipeline, vue) d'historique.

    ``rupture_run_id`` = le **premier run du nouveau régime**, renseigné dès que
    le test de Pettitt est calculable — **au moins** ``MIN_POINTS_FOR_TEST``
    (3) runs, comme la p de la pente : à 2 points la p vaut 1 par construction,
    la rupture est alors ``None`` — et **quelle que soit sa p** : filtrer sur la
    significativité serait un verdict implicite. La rupture est publiée avec sa
    p, étiquetée exploratoire (``CONTRATS.md`` § 2.1 f, révision n° 7).
    """

    trend: TrendResult | None
    rupture: PettittResult | None
    rupture_run_id: str | None


def series_insight(records: Sequence[HistoryRecord]) -> SeriesInsight:
    """Analyse une série d'enregistrements (tendance OLS + rupture Pettitt).

    Les horodatages naïfs sont supposés UTC (le store n'écrit que de
    l'ISO 8601 conscient du fuseau ; la normalisation couvre les données
    importées) ; un horodatage illisible écarte sa ligne **avec warning**.
    """
    rows: list[tuple[datetime, str, float]] = []
    for record in records:
        try:
            stamp = datetime.fromisoformat(record.completed_at)
        except ValueError:
            logger.warning(
                "[history] horodatage illisible ignoré : %r (run %s)",
                record.completed_at,
                record.run_id,
            )
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        rows.append((stamp, record.run_id, record.value))
    rows.sort(key=lambda row: (row[0], row[1]))
    trend = linear_trend([(stamp, value) for stamp, _, value in rows])
    rupture = (
        pettitt([value for _, _, value in rows])
        if len(rows) >= MIN_POINTS_FOR_TEST
        else None
    )
    rupture_run_id = rows[rupture.boundary][1] if rupture is not None else None
    return SeriesInsight(trend=trend, rupture=rupture, rupture_run_id=rupture_run_id)


__all__ = ["SeriesInsight", "record_run", "records_from_run", "series_insight"]
