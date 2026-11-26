"""Économie d'un run : coûts estimés, débit effectif, Pareto (couche 3).

Heuristique **maison** (héritée de l'analyse de l'implémentation source,
relue au port — ``PLAN_PARITE.md`` §5.8b : valeurs de test dérivées à la main,
jamais en exécutant la source). Modèle de coût simple et auditable :

- **temps machine** : durée mesurée (E1, wall-clock exécuteur) × taux horaire
  indicatif de la table — appliqué à tout pipeline (la machine est occupée) ;
- **jetons cloud** : jetons mesurés (E1, remontés par les adapters) × tarif
  €/MTok de la table, par (kind/modèle). Le modèle est celui que le fournisseur
  dit avoir **servi** (``RunManifest.served_models``) quand il est connu, le
  modèle **demandé** sinon (réponse muette, JSON antérieur) : un alias
  (``gpt-4o-mini``) peut désigner un autre modèle, à un autre prix, d'un mois à
  l'autre. Modèle absent de la table → coût ``None`` + motif dans ``basis``
  (jamais un zéro silencieux — et l'alias ne remplace pas un servi inconnu) ;
- **débit effectif** : pages/h corrigé du temps de relecture des erreurs
  résiduelles (Σ cer·poids erreurs estimées × ``time_per_error_seconds``) ;
- **péremption** : ``valid_until`` de la table comparé à ``completed_at`` du
  manifeste — déterministe (aucune horloge au rendu).

La table vit dans ``pricing.json`` (JSON stdlib : ``yaml`` n'est pas dans la
whitelist archi de cette couche). C'est de la **donnée datée**, pas du code.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from importlib import resources
from typing import Any

from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    EconomicsPayload,
    MarginalCost,
    PipelineEconomics,
)
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.result import DocumentUsage, MetricScore


def load_pricing() -> dict[str, Any]:
    """Charge la table packagée — à l'appel, pas à l'import (zéro effet de bord)."""
    raw = (
        resources.files("cinoc.evaluation").joinpath("pricing.json").read_bytes()
    )
    table = json.loads(raw)
    if not isinstance(table, dict) or "meta" not in table:
        raise EvaluationError("pricing.json : table de tarifs invalide.")
    return table


def pareto_front(
    points: Sequence[tuple[str, float, float]],
) -> tuple[str, ...]:
    """Noms non dominés (deux axes **minimisés**) ; tri stable (x, y, nom).

    ``p`` est dominé s'il existe ``q`` au moins aussi bon sur les deux axes et
    strictement meilleur sur l'un.
    """
    front = [
        (name, x, y)
        for name, x, y in points
        if not any(
            (qx <= x and qy <= y) and (qx < x or qy < y)
            for _, qx, qy in points
        )
    ]
    return tuple(name for name, _, _ in sorted(front, key=lambda p: (p[1], p[2], p[0])))


def _page_rate(
    spec: PipelineSpec, pricing: Mapping[str, Any]
) -> float | None:
    """Tarif €/1000 pages cumulé des étages facturés à la page, sinon ``None``."""
    table = pricing.get("cloud_page_kinds", {})
    rates = [
        float(table[kind]["eur_per_1k_pages"])
        for kind in {step.adapter_name.split(":", 1)[0] for step in spec.steps}
        if kind in table
    ]
    return sum(rates) if rates else None


def _cloud_model_keys(
    spec: PipelineSpec,
    adapter_kwargs: Mapping[str, Mapping[str, object]],
    pricing: Mapping[str, Any],
    served_models: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    """Clés ``kind/modèle`` des étages cloud du pipeline (déduplication triée).

    Un *kind cloud* (facturé au jeton) = un fournisseur listé dans
    ``default_models`` de la table — la source datée fait foi (pas de liste
    codée en dur qui dériverait quand la table gagne un fournisseur). Les kinds
    **à la page** vivent dans ``cloud_page_kinds`` (cf. ``_page_rate``) ; le
    reste (``local_kinds``) : temps machine seul.

    Modèle : le(s) **servi(s)** quand le manifeste les connaît — plusieurs si un
    alias a changé de cible en cours de run, et le coût devient alors non
    ventilable —, sinon le **demandé**, sinon le défaut de la table.
    """
    defaults = pricing.get("default_models", {})
    served = served_models or {}
    keys: set[str] = set()
    for step in spec.steps:
        kind = step.adapter_name.split(":", 1)[0]
        if kind not in defaults:
            continue
        servis = served.get(step.adapter_name) or ()
        if servis:
            keys.update(f"{kind}/{model}" for model in servis)
            continue
        kwargs = adapter_kwargs.get(step.adapter_name, {})
        model = kwargs.get("model")
        if not isinstance(model, str) or not model:
            model = str(defaults.get(kind, ""))
        keys.add(f"{kind}/{model}")
    return sorted(keys)


def _token_cost(
    keys: Sequence[str],
    tokens_in: int | None,
    tokens_out: int | None,
    pricing: Mapping[str, Any],
) -> tuple[float | None, str]:
    """``(coût jetons, basis)`` — ``None`` si un modèle est hors table."""
    if not keys:
        return 0.0, "machine"
    models = pricing.get("cloud_models", {})
    unknown = [key for key in keys if key not in models]
    if unknown:
        return None, f"tarif inconnu : {', '.join(unknown)}"
    if len(keys) > 1:
        # Les jetons E1 sont agrégés par document : à plusieurs étages cloud
        # on ne peut pas les ventiler par modèle → coût non attribuable.
        return None, f"jetons non ventilables : {', '.join(keys)}"
    entry = models[keys[0]]
    cost = (tokens_in or 0) / 1e6 * float(entry["input_eur_per_mtok"]) + (
        tokens_out or 0
    ) / 1e6 * float(entry["output_eur_per_mtok"])
    return cost, "machine+jetons"


def _estimated_errors(scores: Sequence[MetricScore]) -> float | None:
    """Σ (cer_doc × poids_doc) — le poids étant le dénominateur du CER."""
    pairs = [
        (score.value, score.support or 0)
        for score in scores
        if score.value is not None
    ]
    if not pairs:
        return None
    return sum(value * weight for value, weight in pairs)


def economics_analysis(
    view: str,
    metric: str,
    series: Mapping[str, Sequence[MetricScore]],
    usage: Sequence[DocumentUsage],
    manifest: RunManifest,
    pricing: Mapping[str, Any] | None = None,
) -> Analysis | None:
    """``Analysis`` économie pour une vue ; ``None`` sans mesures E1.

    ``series`` : scores par-document de la métrique phare, par pipeline (les
    mêmes que l'agrégat). ``usage`` : mesures par (pipeline × document).
    """
    if not usage:
        return None
    table = pricing if pricing is not None else load_pricing()
    meta = table["meta"]
    rate = float(meta["hourly_rate_local_cpu_eur"])
    time_per_error = float(meta["time_per_error_seconds"])
    valid_until = str(meta["valid_until"])
    stale = manifest.completed_at.date() > date.fromisoformat(valid_until)

    specs = {spec.name: spec for spec in manifest.pipeline_specs}
    rows: list[PipelineEconomics] = []
    for name in sorted(specs):
        # Une unité en échec n'a rien produit ni rien mesuré : la compter
        # gonflerait le débit (des pages « traitées » en zéro seconde).
        entries = [
            u for u in usage if u.pipeline == name and u.outcome != "failed"
        ]
        if not entries:
            continue
        duration = sum(u.usage.duration_seconds or 0.0 for u in entries)
        tokens_in = sum(u.usage.tokens_in or 0 for u in entries) or None
        tokens_out = sum(u.usage.tokens_out or 0 for u in entries) or None
        n_documents = len(entries)
        keys = _cloud_model_keys(
            specs[name], manifest.adapter_kwargs, table, manifest.served_models
        )
        token_cost, basis = _token_cost(keys, tokens_in, tokens_out, table)
        page_rate = _page_rate(specs[name], table)
        page_cost = (
            n_documents / 1000.0 * page_rate if page_rate is not None else 0.0
        )
        if page_rate is not None:
            basis = basis + "+pages" if token_cost is not None else basis
        cost = (
            duration / 3600.0 * rate + token_cost + page_cost
            if token_cost is not None
            else None
        )
        scores = series.get(name, ())
        errors = _estimated_errors(scores)
        cer_values = [
            (s.value, s.support or 0) for s in scores if s.value is not None
        ]
        total_weight = sum(w for _, w in cer_values)
        cer = (
            sum(v * w for v, w in cer_values) / total_weight
            if total_weight > 0
            else None
        )
        pages_per_hour = (
            n_documents / (duration / 3600.0) if duration > 0 else None
        )
        effective = (
            n_documents / ((duration + errors * time_per_error) / 3600.0)
            if errors is not None and duration + errors * time_per_error > 0
            else None
        )
        rows.append(
            PipelineEconomics(
                pipeline=name,
                n_documents=n_documents,
                duration_seconds=duration,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_eur=cost,
                basis=basis,
                cer=cer,
                estimated_errors=errors,
                pages_per_hour=pages_per_hour,
                pages_per_hour_effective=effective,
            )
        )
    if not rows:
        return None

    cost_points = [
        (r.pipeline, r.cer, r.cost_eur)
        for r in rows
        if r.cer is not None and r.cost_eur is not None
    ]
    speed_points = [
        (r.pipeline, r.cer, r.duration_seconds)
        for r in rows
        if r.cer is not None and r.duration_seconds is not None
    ]
    priced = [r for r in rows if r.cost_eur is not None]
    marginal: list[MarginalCost] = []
    if len(priced) >= 2:
        baseline = min(priced, key=lambda r: (r.cost_eur or 0.0, r.pipeline))
        for row in priced:
            if row.pipeline == baseline.pipeline:
                continue
            if row.estimated_errors is None or baseline.estimated_errors is None:
                continue
            avoided = baseline.estimated_errors - row.estimated_errors
            delta = (row.cost_eur or 0.0) - (baseline.cost_eur or 0.0)
            marginal.append(
                MarginalCost(
                    pipeline=row.pipeline,
                    baseline=baseline.pipeline,
                    cost_delta_eur=delta,
                    errors_avoided=avoided,
                    eur_per_avoided_error=(
                        delta / avoided if avoided > 0 and delta >= 0 else None
                    ),
                )
            )

    payload = EconomicsPayload(
        metric=metric,
        currency=str(meta["currency"]),
        hourly_rate_eur=rate,
        time_per_error_seconds=time_per_error,
        pricing_valid_until=valid_until,
        pricing_stale=stale,
        pipelines=tuple(rows),
        pareto_cost=pareto_front(
            [(n, x, y) for n, x, y in cost_points if x is not None and y is not None]
        ),
        pareto_speed=pareto_front(
            [(n, x, y) for n, x, y in speed_points if x is not None and y is not None]
        ),
        marginal=tuple(marginal),
    )
    return Analysis(scope="corpus", view=view, payload=payload)


__all__ = ["economics_analysis", "load_pricing", "pareto_front"]
