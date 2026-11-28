"""C13 — Historique : rupture de Pettitt publiée dès 3 runs quelle que soit p ;
jamais à 2 runs. Séries plates (p = 1), bruitées (p élevée) et à rupture nette."""
from cinoc.adapters.storage.history_store import HistoryRecord
from cinoc.app.history import series_insight
def recs(values):
    return [HistoryRecord(run_id=f"r{i}", completed_at=f"2026-11-{i+1:02d}T00:00:00+00:00",
            corpus_name="c", normalization_profile=None, code_version="x", pipeline="p",
            view="v", metric="cer", value=v) for i, v in enumerate(values)]
for vals in ([0.1, 0.2], [0.1, 0.1, 0.1], [0.10, 0.12, 0.11], [0.1, 0.3, 0.2, 0.25, 0.15],
             [0.1]*5 + [0.3]*5):
    ins = series_insight(recs(vals))
    rp = ins.rupture
    print(f"{len(vals)} runs {vals[:6]}… rupture={None if rp is None else (ins.rupture_run_id, round(rp.p_value, 4), rp.significant)} pente_p={None if ins.trend is None else ins.trend.p_value}")
