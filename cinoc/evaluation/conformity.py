"""Analyse de **conformité HIPE** : payload ``hipe`` depuis les vues (couche 3).

Post-passe **cross-vues** : contrairement aux autres analyses (une par vue), la
conformité lit des résultats **déjà calculés** sur plusieurs vues — la vue de
profil ``hipe`` (ancre, obligatoire), et si présentes une vue **brute**
(``normalization_profile: null`` explicite — une vue qui n'en nomme aucun reçoit
le défaut ``flat_text``, D-285) et une vue ``heritage`` pour les deltas de
normalisation. Zéro re-scoring : tout vient des ``PipelineResult`` /
``RunDocumentResult`` produits par les passes par-vue (l'invariant « calculé
une fois, lu ensuite »).

Les vues sont reconnues par leur ``normalization_profile`` (jamais par leur
nom) ; pour que les deltas isolent bien l'effet du profil, les vues comparées
doivent ne différer que par lui (responsabilité de la spec, documentée).
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean

from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.analysis import (
    Analysis,
    ConformityPayload,
    PipelineConformity,
)
from cinoc.evaluation.result import PipelineResult, RunDocumentResult


def _view_with_profile(
    views: Sequence[EvaluationView], profile: str | None
) -> EvaluationView | None:
    for view in views:
        if view.normalization_profile == profile:
            return view
    return None


def _micro(
    pipelines: Sequence[PipelineResult], view: str, pipeline: str, metric: str
) -> float | None:
    for result in pipelines:
        if result.view != view or result.pipeline != pipeline:
            continue
        for score in result.aggregate:
            if score.metric == metric:
                return score.value
    return None


def _per_document(
    documents: Sequence[RunDocumentResult], view: str, pipeline: str, metric: str
) -> list[float | None]:
    out: list[float | None] = []
    for document in documents:
        if document.view != view or document.pipeline != pipeline:
            continue
        out.append(
            next(
                (s.value for s in document.scores if s.metric == metric),
                None,
            )
        )
    return out


def _macro(values: Sequence[float | None]) -> float | None:
    """Moyenne **macro** des scores par-document (``None``-exclus) — SPEC §4.1."""
    present = [v for v in values if v is not None]
    return fmean(present) if present else None


def _delta(
    pipelines: Sequence[PipelineResult],
    other_view: EvaluationView | None,
    pipeline: str,
    hipe_micro: float | None,
) -> float | None:
    """``cmer(autre vue) − cmer(hipe)`` ; ``None`` si l'un des deux manque."""
    if other_view is None or hipe_micro is None:
        return None
    other = _micro(pipelines, other_view.name, pipeline, "cmer")
    if other is None:
        return None
    return other - hipe_micro


def conformity_analysis(
    views: Sequence[EvaluationView],
    pipelines: Sequence[PipelineResult],
    documents: Sequence[RunDocumentResult],
) -> Analysis | None:
    """Construit le payload ``hipe``, ou ``None`` sans vue portant ``cmer``.

    Ancre = la vue de profil ``hipe`` si présente (avec ``cmer``), **sinon** la
    première vue portant ``cmer`` (le profil ``standard`` en a) → cMER/wMER
    micro·macro s'affichent sur **tout** corpus. Les **deltas** de normalisation
    (norm/heritage) n'ont de sens qu'avec une vraie ancre HIPE + vues
    brute/heritage : sinon ``None``. ``wmer`` = la clé interne ``mer``.
    """
    hipe_view = _view_with_profile(views, "hipe")
    if hipe_view is not None and "cmer" not in hipe_view.metric_names:
        hipe_view = None  # vue hipe sans cmer → inutilisable comme ancre
    anchor = hipe_view or next(
        (v for v in views if "cmer" in v.metric_names), None
    )
    if anchor is None:
        return None
    # Deltas : seulement si l'ancre est une vraie vue HIPE (comparaison de profils).
    raw_view = _view_with_profile(views, None) if hipe_view is not None else None
    heritage_view = (
        _view_with_profile(views, "heritage") if hipe_view is not None else None
    )

    order: list[str] = []
    for result in pipelines:
        if result.view == anchor.name and result.pipeline not in order:
            order.append(result.pipeline)
    if not order:
        return None

    rows: list[PipelineConformity] = []
    for pipeline in order:
        cmer_values = _per_document(documents, anchor.name, pipeline, "cmer")
        cmer_micro = _micro(pipelines, anchor.name, pipeline, "cmer")
        rows.append(
            PipelineConformity(
                pipeline=pipeline,
                cmer_micro=cmer_micro,
                cmer_macro=_macro(cmer_values),
                wmer_micro=_micro(pipelines, anchor.name, pipeline, "mer"),
                wmer_macro=_macro(
                    _per_document(documents, anchor.name, pipeline, "mer")
                ),
                delta_norm=_delta(pipelines, raw_view, pipeline, cmer_micro),
                delta_heritage=_delta(
                    pipelines, heritage_view, pipeline, cmer_micro
                ),
                n_missing=sum(1 for v in cmer_values if v is None),
            )
        )
    return Analysis(
        scope="corpus",
        view=anchor.name,
        payload=ConformityPayload(
            hipe_view=anchor.name,
            raw_view=raw_view.name if raw_view is not None else None,
            heritage_view=heritage_view.name if heritage_view is not None else None,
            pipelines=tuple(rows),
        ),
    )


__all__ = ["conformity_analysis"]
