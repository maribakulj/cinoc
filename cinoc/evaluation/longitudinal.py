"""Tendance & rupture d'une série longitudinale multi-runs (couche 3).

Sur l'historique des runs (PAS un payload ``RunResult`` — c'est du
multi-runs), deux questions :

- **Y a-t-il une tendance ?** ``linear_trend`` — régression des moindres
  carrés par ``scipy.stats.linregress`` sur ``(temps, valeur)``, pente
  exprimée **par jour**, **avec son test** : p-value bilatérale de l'hypothèse
  « pente nulle » (t de Student à n − 2 degrés de liberté), tendance
  **significative seulement si p ≤ α** (D-287 ; l'OLS maison d'avant donnait
  la même pente, à 4e-12, mais aucune p : une pente au hasard s'affichait
  comme une tendance). Conventions : à **2 points**, aucun test possible
  (zéro degré de liberté) → ``p_value = None``, jamais significative ; série
  **constante** → pente 0, ``r_squared = 0.0``, ``p_value = 1.0`` (ce que rend
  ``linregress`` quand il ne tombe pas sur ``nan``, ce qu'il fait selon la
  constante) ; < 2 points ou horodatages tous identiques → ``None``.
  L'origine des x est le **premier point** (l'ordonnée à l'origine est la
  valeur ajustée au premier run, pas à l'an 1).
- **Y a-t-il une rupture ?** ``pettitt`` — **vrai test de rupture**
  (Pettitt 1979, non paramétrique, fondé sur les rangs) : ``U_t = Σ_{i≤t}
  Σ_{j>t} sgn(x_j − x_i)``, ``K = max|U_t|``, approximation asymptotique
  publiée ``p ≈ 2·exp(−6K²/(n³+n²))`` (clampée ≤ 1) ; rupture **significative
  seulement si p ≤ α** — le max-diff de la source « détectait » toujours
  quelque chose (aucune statistique de test) ; réparation R11.

Entrées **déjà parsées** (``datetime``/``float``) : le parsing tolérant
multi-formats à skip silencieux de la source n'est pas porté — la conversion
vit chez l'appelant (couche app), explicite et journalisée.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean

from scipy import stats  # type: ignore[import-untyped]

#: Seuil de signification par défaut (pente et rupture).
_DEFAULT_ALPHA = 0.05

#: Secondes par jour (pente exprimée par jour).
_DAY_SECONDS = 86400.0


@dataclass(frozen=True)
class TrendResult:
    """Régression linéaire d'une série temporelle (pente par **jour**).

    ``p_value`` : test bilatéral de pente nulle (``None`` à 2 points, où aucun
    test n'est possible) ; ``significant`` n'est vrai que si
    ``p_value ≤ alpha`` — sinon la pente n'est pas une tendance établie.
    """

    slope_per_day: float
    intercept: float
    r_squared: float
    n_points: int
    p_value: float | None
    alpha: float
    significant: bool


@dataclass(frozen=True)
class PettittResult:
    """Test de rupture de Pettitt sur une série **chronologique**.

    ``boundary`` = taille du premier segment : la série se lit
    ``série[:boundary]`` (avant) / ``série[boundary:]`` (après) — le point
    d'indice ``boundary`` est le **premier du nouveau régime**. À égalité de
    ``|U|``, la plus petite frontière gagne (déterministe). ``significant``
    n'est vrai que si ``p_value ≤ alpha`` — sinon il n'y a **pas** de rupture
    à signaler, quelle que soit l'ampleur de ``delta``.
    """

    n_points: int
    boundary: int
    u_statistic: int
    p_value: float
    alpha: float
    significant: bool
    mean_before: float
    mean_after: float
    delta: float


def linear_trend(
    points: Sequence[tuple[datetime, float]], *, alpha: float = _DEFAULT_ALPHA
) -> TrendResult | None:
    """Pente par jour de ``(horodatage, valeur)`` et son test ; ``None`` si
    la pente est indéfinie.

    Horodatages **homogènes** requis (tous naïfs ou tous conscients du fuseau
    — l'appelant normalise) ; l'ordre n'importe pas (la régression est
    invariante).
    """
    if len(points) < 2:
        return None
    origin = min(stamp for stamp, _ in points)
    xs = [(stamp - origin).total_seconds() / _DAY_SECONDS for stamp, _ in points]
    ys = [value for _, value in points]
    if all(x == xs[0] for x in xs):
        return None  # horodatages tous identiques : pente indéfinie.
    if all(y == ys[0] for y in ys):
        # Testé sur les valeurs : ``linregress`` y rend r = 0 ou ``nan``
        # selon la poussière flottante de la moyenne.
        return TrendResult(
            slope_per_day=0.0,
            intercept=ys[0],
            r_squared=0.0,
            n_points=len(points),
            p_value=1.0,
            alpha=alpha,
            significant=False,
        )
    fit = stats.linregress(xs, ys)
    p_value = float(fit.pvalue) if len(points) > 2 else None
    return TrendResult(
        slope_per_day=float(fit.slope),
        intercept=float(fit.intercept),
        r_squared=float(fit.rvalue) ** 2,
        n_points=len(points),
        p_value=p_value,
        alpha=alpha,
        significant=p_value is not None and p_value <= alpha,
    )


def _sign(a: float, b: float) -> int:
    """``sgn(b − a)`` sans flottant (rang pur : les ex æquo comptent 0)."""
    return (b > a) - (b < a)


def pettitt(
    values: Sequence[float], *, alpha: float = _DEFAULT_ALPHA
) -> PettittResult | None:
    """Test de rupture de Pettitt (1979) sur une série **chronologique**.

    ``U`` est balayé incrémentalement (O(n²) : à chaque déplacement de la
    frontière, seules les paires impliquant l'élément déplacé changent).
    ``None`` si moins de 2 points. ``K = 0`` (série constante) → ``p``
    clampée à 1.0, jamais significatif.
    """
    n = len(values)
    if n < 2:
        return None
    u = sum(_sign(values[0], values[j]) for j in range(1, n))
    best_u, best_boundary = u, 1
    for boundary in range(2, n):
        moved = boundary - 1  # l'élément qui passe du 2ᵉ au 1ᵉʳ segment
        u -= sum(_sign(values[i], values[moved]) for i in range(moved))
        u += sum(_sign(values[moved], values[j]) for j in range(boundary, n))
        if abs(u) > abs(best_u):
            best_u, best_boundary = u, boundary
    k = abs(best_u)
    p_value = min(1.0, 2.0 * math.exp(-6.0 * k * k / (n**3 + n**2)))
    mean_before = fmean(values[:best_boundary])
    mean_after = fmean(values[best_boundary:])
    return PettittResult(
        n_points=n,
        boundary=best_boundary,
        u_statistic=k,
        p_value=p_value,
        alpha=alpha,
        significant=p_value <= alpha,
        mean_before=mean_before,
        mean_after=mean_after,
        delta=mean_after - mean_before,
    )


__all__ = ["PettittResult", "TrendResult", "linear_trend", "pettitt"]
