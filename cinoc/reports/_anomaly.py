"""Détection d'anomalies par document pour le triage **Explorer** (couche 7).

Quatre signaux **factuels et auditables** dérivés du ``RunResult`` (présentation
seule — la donnée reste dans le ``RunResult``). **Aucun seuil absolu arbitraire** :
les trois signaux quantitatifs utilisent un **cutoff relatif** = le quantile
``_QUANTILE`` (P90) de la distribution **observée** dans ce run. Pour chaque
document, on renvoie l'ensemble des types déclenchés par **au moins un** moteur.

- ``cer``        — un moteur a un CER ≥ P90 des CER par (doc, moteur).
- ``unanchored`` — un moteur a une part de texte non ancré ≥ P90.
- ``disagree``   — l'écart max−min de CER entre moteurs ≥ P90 des écarts (≥ 2 moteurs).
- ``inserted``   — l'analyse signale ≥ 1 bloc inséré sans appui GT (fait déjà calculé).

Les **cutoffs** sont renvoyés pour être **affichés** (le critère est sous les yeux).
"""

from __future__ import annotations

import math

from cinoc.evaluation.analysis import DocumentHallucinationPayload
from cinoc.evaluation.result import RunResult

#: Quantile servant de seuil **relatif** (P90 = les 10 % les plus élevés observés).
_QUANTILE = 0.90

#: Ordre canonique de rendu des facettes + libellés bilingues (FR, EN).
ANOMALY_ORDER: tuple[str, ...] = ("cer", "unanchored", "disagree", "inserted")
ANOMALY_LABELS: dict[str, tuple[str, str]] = {
    "cer": ("CER élevé", "High CER"),
    "unanchored": ("Texte non ancré", "Unanchored text"),
    "disagree": ("Désaccord moteurs", "Engine disagreement"),
    "inserted": ("Bloc inséré sans appui GT", "Inserted block (no GT)"),
}


def _percentile(values: list[float], q: float) -> float | None:
    """Cutoff par **rang le plus proche** (déterministe) : valeur au rang ``⌈q·N⌉``.

    Pas d'interpolation (octet-stable) ; ``None`` si pas de valeur."""
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[k]


def _by_doc(result: RunResult, view: str, metric: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for doc in result.documents:
        if doc.view != view:
            continue
        for score in doc.scores:
            if score.metric == metric and score.value is not None:
                out.setdefault(doc.document_id, []).append(score.value)
    return out


def _inserted_docs(result: RunResult) -> set[str]:
    """Documents portant ≥ 1 bloc inséré sans appui GT (collecteur = blocs présents)."""
    flagged: set[str] = set()
    for analysis in result.analyses:
        payload = analysis.payload
        if isinstance(payload, DocumentHallucinationPayload):
            for row in payload.documents:
                if any(p.blocks for p in row.pipelines):
                    flagged.add(row.document_id)
    return flagged


def compute_anomalies(
    result: RunResult, view: str
) -> tuple[dict[str, set[str]], dict[str, float]]:
    """``(anomalies_par_doc, cutoffs_affichables)`` pour la vue ``view``.

    ``anomalies_par_doc[doc_id]`` = ensemble des types déclenchés (≥ 1 moteur).
    ``cutoffs`` = seuil retenu par type quantitatif (pour l'affichage du critère)."""
    cer = _by_doc(result, view, "cer")
    unanchored = _by_doc(result, view, "unanchored_trigrams")
    cer_cut = _percentile([v for vs in cer.values() for v in vs], _QUANTILE)
    unanch_cut = _percentile([v for vs in unanchored.values() for v in vs], _QUANTILE)
    spreads = {
        doc_id: max(vs) - min(vs) for doc_id, vs in cer.items() if len(vs) >= 2
    }
    spread_cut = _percentile(list(spreads.values()), _QUANTILE)
    inserted = _inserted_docs(result)

    # Comparaison **stricte** (``>``) au cutoff : on ne flague que ce qui dépasse
    # *réellement* le P90 — sinon, sur un corpus petit/uniforme, les ex-aequo au
    # rang P90  feraient flaguer tout le monde (bruit, pas un signal d'anomalie).
    flags: dict[str, set[str]] = {}
    for doc_id, vs in cer.items():
        tags: set[str] = set()
        if cer_cut is not None and max(vs) > cer_cut:
            tags.add("cer")
        if unanch_cut is not None and doc_id in unanchored:
            if max(unanchored[doc_id]) > unanch_cut:
                tags.add("unanchored")
        if spread_cut is not None and spreads.get(doc_id, -1.0) > spread_cut:
            tags.add("disagree")
        if doc_id in inserted:
            tags.add("inserted")
        if tags:
            flags[doc_id] = tags

    cutoffs: dict[str, float] = {}
    if cer_cut is not None:
        cutoffs["cer"] = cer_cut
    if unanch_cut is not None:
        cutoffs["unanchored"] = unanch_cut
    if spread_cut is not None:
        cutoffs["disagree"] = spread_cut
    return flags, cutoffs


__all__ = ["ANOMALY_LABELS", "ANOMALY_ORDER", "compute_anomalies"]
