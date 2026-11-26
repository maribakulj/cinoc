"""``HistoryStore`` — historique **longitudinal** des runs, en SQLite (couche 5).

Persiste, run après run, la **valeur agrégée de chaque métrique** par pipeline et
par vue, pour suivre l'évolution dans le temps (tendance) et **détecter les
régressions** (un moteur dont le CER se dégrade d'un run au suivant).

Le store ne connaît **que des enregistrements primitifs** (``HistoryRecord``) : il
n'importe pas ``RunResult`` (couche 3) — c'est la couche ``app`` qui aplatit un
``RunResult`` en enregistrements (``app/history.py``). Persistance pure, réutilisable
et testable avec de la donnée simple.

**Une série = (corpus, profil de normalisation, pipeline, vue)** (D-288) : avant,
une série n'était indexée que par (pipeline, vue), si bien qu'une « tendance »
mêlait des runs sur des corpus ou sous des profils différents — un CER qui
« baisse » parce qu'on est passé de ``nfc`` à ``flat_text`` n'est pas un progrès.
Le profil ``None`` (comparaison brute) est une série à part entière (``NULL``,
comparé par ``IS``). Une base écrite avant cette clé n'a pas la colonne : elle
est **refusée** (``HistorySchemaError``) plutôt que relue en séries mêlées — elle
ne dit pas sous quel profil ses valeurs ont été calculées.

Concurrence : **une connexion par opération** (``sqlite3.connect`` est bon marché),
donc aucun partage de connexion entre threads. Ré-enregistrer un même run est
**idempotent** (clé primaire ``(run_id, pipeline, view, metric)`` : un run a un
seul corpus et un seul profil par vue).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from cinoc.domain.errors import CinocError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_metrics (
    run_id       TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    corpus_name  TEXT NOT NULL,
    normalization_profile TEXT,
    code_version TEXT NOT NULL,
    pipeline     TEXT NOT NULL,
    view         TEXT NOT NULL,
    metric       TEXT NOT NULL,
    value        REAL NOT NULL,
    PRIMARY KEY (run_id, pipeline, view, metric)
);
CREATE INDEX IF NOT EXISTS idx_run_metrics_series
    ON run_metrics (corpus_name, normalization_profile, pipeline, view, metric,
                    completed_at);
"""

_COLUMNS = (
    "run_id, completed_at, corpus_name, normalization_profile, code_version, "
    "pipeline, view, metric, value"
)
_SERIES_ORDER = "corpus_name, normalization_profile, pipeline, view"


class HistorySchemaError(CinocError):
    """Base d'historique d'un format antérieur (séries sans profil)."""


@dataclass(frozen=True)
class SeriesKey:
    """Ce qui fait **une** série : deux runs ne se comparent que sous la même."""

    corpus_name: str
    #: ``None`` = comparaison brute (``normalization_profile: null``).
    normalization_profile: str | None
    pipeline: str
    view: str


@dataclass(frozen=True)
class HistoryRecord:
    """Une valeur de métrique agrégée pour un run (ligne d'historique)."""

    run_id: str
    completed_at: str  # ISO 8601 (UTC) — triable lexicographiquement
    corpus_name: str
    normalization_profile: str | None
    code_version: str
    pipeline: str
    view: str
    metric: str
    value: float

    @property
    def series(self) -> SeriesKey:
        return SeriesKey(
            self.corpus_name, self.normalization_profile, self.pipeline, self.view
        )


@dataclass(frozen=True)
class Regression:
    """Dégradation d'une série entre ses deux runs les plus récents."""

    corpus_name: str
    normalization_profile: str | None
    pipeline: str
    view: str
    metric: str
    previous_run_id: str
    latest_run_id: str
    previous: float
    latest: float
    delta: float  # latest - previous (signé)


class HistoryStore:
    """Historique longitudinal sur un fichier SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        # **Initialisation paresseuse** : on ne touche pas au filesystem ici.
        # ``create_app`` peut instancier le store avec un chemin par défaut
        # (``/data`` sur un Space) non writable au moment de la construction ;
        # le dossier + le schéma sont créés à la **première** opération réelle.
        self._path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        """Ouvre une connexion, créant dossier + schéma au besoin (idempotent)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(run_metrics)")
        }
        if columns and "normalization_profile" not in columns:
            conn.close()
            raise HistorySchemaError(
                f"historique {self._path} au format antérieur : ses séries ne "
                "disent ni corpus ni profil de normalisation, et ses valeurs ne "
                "peuvent pas être rangées sans les mêler. Déplacez ce fichier "
                "pour en commencer un nouveau (les RunResult, eux, se relisent)."
            )
        conn.executescript(_SCHEMA)
        return conn

    def add(self, records: Iterable[HistoryRecord]) -> int:
        """Enregistre des lignes (``INSERT OR REPLACE``) ; renvoie le compte."""
        rows = [
            (
                r.run_id,
                r.completed_at,
                r.corpus_name,
                r.normalization_profile,
                r.code_version,
                r.pipeline,
                r.view,
                r.metric,
                r.value,
            )
            for r in records
        ]
        if not rows:
            return 0
        with closing(self._connect()) as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO run_metrics ({_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)

    def history(self, series: SeriesKey, metric: str) -> tuple[HistoryRecord, ...]:
        """Suite chronologique (croissante) d'une métrique sur **une** série."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"SELECT {_COLUMNS} FROM run_metrics "
                "WHERE corpus_name = ? AND normalization_profile IS ? "
                "AND pipeline = ? AND view = ? AND metric = ? "
                "ORDER BY completed_at, run_id",  # run_id = bris d'égalité déterministe
                (
                    series.corpus_name,
                    series.normalization_profile,
                    series.pipeline,
                    series.view,
                    metric,
                ),
            )
            return tuple(HistoryRecord(*row) for row in cur.fetchall())

    def series(
        self, view: str, metric: str, *, pipeline: str | None = None
    ) -> tuple[tuple[SeriesKey, tuple[HistoryRecord, ...]], ...]:
        """Toutes les séries d'une (vue, métrique), chacune chronologique.

        ``pipeline`` restreint à ce pipeline. Ordre déterministe : clé de série,
        puis ``completed_at``, puis ``run_id``.
        """
        query = f"SELECT {_COLUMNS} FROM run_metrics WHERE view = ? AND metric = ?"
        params: tuple[str, ...] = (view, metric)
        if pipeline is not None:
            query += " AND pipeline = ?"
            params += (pipeline,)
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        grouped: dict[SeriesKey, list[HistoryRecord]] = {}
        for row in rows:
            record = HistoryRecord(*row)
            grouped.setdefault(record.series, []).append(record)
        return tuple(
            (
                key,
                tuple(sorted(grouped[key], key=lambda r: (r.completed_at, r.run_id))),
            )
            for key in sorted(grouped, key=_sort_key)
        )

    def all_records(self, *, limit: int = 1000) -> tuple[HistoryRecord, ...]:
        """Lignes les plus récentes d'abord, **bornées** (pour la vue Historique)."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"SELECT {_COLUMNS} FROM run_metrics "
                f"ORDER BY completed_at DESC, run_id, {_SERIES_ORDER}, metric "
                "LIMIT ?",
                (limit,),
            )
            return tuple(HistoryRecord(*row) for row in cur.fetchall())

    def regressions(
        self,
        view: str,
        metric: str,
        *,
        threshold: float = 0.0,
        higher_is_better: bool = False,
    ) -> tuple[Regression, ...]:
        """Séries dont la métrique s'est dégradée entre leurs 2 derniers runs.

        ``higher_is_better=False`` (défaut, CER/WER) : régression = la valeur a
        **augmenté** de plus de ``threshold``. ``True`` inverse le sens.
        """
        out: list[Regression] = []
        for key, records in self.series(view, metric):
            if len(records) < 2:
                continue
            previous, latest = records[-2], records[-1]
            delta = latest.value - previous.value
            worse = -delta if higher_is_better else delta
            if worse > threshold:
                out.append(
                    Regression(
                        corpus_name=key.corpus_name,
                        normalization_profile=key.normalization_profile,
                        pipeline=key.pipeline,
                        view=view,
                        metric=metric,
                        previous_run_id=previous.run_id,
                        latest_run_id=latest.run_id,
                        previous=previous.value,
                        latest=latest.value,
                        delta=delta,
                    )
                )
        return tuple(out)


def _sort_key(key: SeriesKey) -> tuple[str, str, str, str]:
    """Ordre total de séries (le profil brut ``None`` avant les profils nommés)."""
    return (key.corpus_name, key.normalization_profile or "", key.pipeline, key.view)


__all__ = [
    "HistoryRecord",
    "HistorySchemaError",
    "HistoryStore",
    "Regression",
    "SeriesKey",
]
