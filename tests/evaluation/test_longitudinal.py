"""Longitudinal : tendance (``linregress``, valeurs main + p) et Pettitt.

Règle d'ancrage (D-068) : OLS = algorithme à référence externe → parité
``scipy.stats.linregress`` (oracle **exécuté**) en plus des valeurs posées à la
main ; Pettitt = formule publiée (Pettitt 1979) → U_t/K dérivés à la main sur
séries courtes + recoupement contre une implémentation **directe indépendante**
(double somme) écrite dans le test.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from scipy import stats

from cinoc.evaluation.longitudinal import linear_trend, pettitt

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _points(values: list[float]) -> list[tuple[datetime, float]]:
    """Un point par jour, à partir du 2026-01-01."""
    return [(_T0 + timedelta(days=i), v) for i, v in enumerate(values)]


class TestLinearTrend:
    def test_perfect_line_hand_derived(self) -> None:
        trend = linear_trend(_points([0.10, 0.20, 0.30]))
        assert trend is not None
        assert trend.slope_per_day == pytest.approx(0.10)
        assert trend.intercept == pytest.approx(0.10)  # origine = premier point
        assert trend.r_squared == pytest.approx(1.0)
        assert trend.n_points == 3

    def test_noisy_line_hand_derived(self) -> None:
        # x=[0,1,2], y=[0.1,0.3,0.2] : sxy=0.1, sxx=2 → pente 0.05 ;
        # intercept 0.15 ; résidus (−0.05, +0.10, −0.05) → ss_res 0.015,
        # syy 0.02 → R² = 1 − 0.75 = 0.25.
        trend = linear_trend(_points([0.1, 0.3, 0.2]))
        assert trend is not None
        assert trend.slope_per_day == pytest.approx(0.05)
        assert trend.intercept == pytest.approx(0.15)
        assert trend.r_squared == pytest.approx(0.25)

    def test_parity_with_scipy_linregress(self) -> None:
        values = [0.12, 0.31, 0.18, 0.27, 0.22]
        trend = linear_trend(_points(values))
        assert trend is not None
        oracle = stats.linregress(range(5), values)
        assert trend.slope_per_day == pytest.approx(oracle.slope)
        assert trend.intercept == pytest.approx(oracle.intercept)
        assert trend.r_squared == pytest.approx(oracle.rvalue**2)
        assert trend.p_value == pytest.approx(oracle.pvalue)

    def test_constant_series_convention(self) -> None:
        # Série constante : pente nulle, aucune tendance à expliquer — R² = 0
        # et p = 1, la valeur que rend ``linregress`` quand son calcul ne
        # tombe pas sur ``nan`` (ce qu'il fait selon la constante : 0,1 sur
        # 5 points). L'ancienne convention (R² = 1) disait « parfaitement
        # prédite » à côté d'une pente qu'aucun test ne soutient.
        for value in (0.1, 0.2, 0.3, 1 / 3):
            for n in (3, 5, 12):
                trend = linear_trend(_points([value] * n))
                assert trend is not None
                assert trend.slope_per_day == 0.0
                assert trend.r_squared == 0.0
                assert trend.p_value == 1.0
                assert not trend.significant

    def test_a_slope_carries_its_test(self) -> None:
        """Défaut 10 de l'audit D-264 : une pente s'affichait sans test. Ici
        p = 0,19 (``linregress``, test bilatéral de pente nulle) : la pente
        existe, elle n'est **pas** significative au seuil 0,05."""
        values = [0.30, 0.28, 0.31, 0.26, 0.29, 0.25]
        trend = linear_trend(_points(values))
        assert trend is not None
        oracle = stats.linregress(range(6), values)
        assert trend.p_value == pytest.approx(oracle.pvalue)
        assert trend.p_value == pytest.approx(0.1864, abs=1e-4)
        assert trend.alpha == 0.05
        assert not trend.significant

    def test_a_clear_slope_is_significant(self) -> None:
        trend = linear_trend(_points([0.30, 0.27, 0.25, 0.22, 0.20, 0.17]))
        assert trend is not None
        assert trend.p_value is not None and trend.p_value < 0.001
        assert trend.significant

    def test_two_points_give_a_slope_but_no_test(self) -> None:
        """À deux points la droite passe par les deux : zéro degré de liberté,
        aucun test possible — p absente, jamais « significative »."""
        trend = linear_trend(_points([0.30, 0.20]))
        assert trend is not None
        assert trend.slope_per_day == pytest.approx(-0.10)
        assert trend.p_value is None
        assert not trend.significant

    def test_slope_is_per_day_with_intraday_spacing(self) -> None:
        # 2 points à 12 h d'écart, +0.1 → pente +0.2 par jour.
        trend = linear_trend(
            [(_T0, 0.1), (_T0 + timedelta(hours=12), 0.2)]
        )
        assert trend is not None
        assert trend.slope_per_day == pytest.approx(0.2)

    def test_degenerate_inputs_yield_none(self) -> None:
        assert linear_trend([]) is None
        assert linear_trend([(_T0, 0.1)]) is None  # < 2 points
        assert linear_trend([(_T0, 0.1), (_T0, 0.3)]) is None  # même instant


def _u_direct(values: list[float], boundary: int) -> int:
    """U(frontière) par la double somme **directe** (oracle indépendant)."""
    return sum(
        (values[j] > values[i]) - (values[j] < values[i])
        for i in range(boundary)
        for j in range(boundary, len(values))
    )


class TestPettitt:
    def test_clear_shift_hand_derived(self) -> None:
        # 6 × 0.1 puis 6 × 0.5 (n=12) : à la frontière 6, les 36 paires
        # croisées valent toutes +1 → K = 36 ; ailleurs U_t = 6·min(t, 12−t).
        # p = 2·exp(−6·36²/(12³+12²)) = 2·exp(−7776/1872) ≈ 0.0314 ≤ 0.05.
        result = pettitt([0.1] * 6 + [0.5] * 6)
        assert result is not None
        assert result.boundary == 6
        assert result.u_statistic == 36
        assert result.p_value == pytest.approx(0.0314, abs=1e-3)
        assert result.significant is True
        assert result.mean_before == pytest.approx(0.1)
        assert result.mean_after == pytest.approx(0.5)
        assert result.delta == pytest.approx(0.4)

    def test_short_shift_is_not_significant(self) -> None:
        # Même décalage mais n=6 : K = 9, p = 2·exp(−486/252) ≈ 0.29 > 0.05 —
        # le test dit « preuve insuffisante » là où le max-diff de la source
        # aurait « détecté » une rupture (delta 0.4 ≫ son seuil 0.01). R11.
        result = pettitt([0.1] * 3 + [0.5] * 3)
        assert result is not None
        assert result.u_statistic == 9 and result.boundary == 3
        assert result.p_value == pytest.approx(0.2907, abs=1e-3)
        assert result.significant is False

    def test_constant_series_never_significant(self) -> None:
        result = pettitt([0.2] * 8)
        assert result is not None
        assert result.u_statistic == 0
        assert result.p_value == 1.0  # clampée (la formule donnerait 2)
        assert result.significant is False

    def test_p_value_clamped_at_one(self) -> None:
        result = pettitt([0.1, 0.5])  # K=1, formule → 2·e^(−0.5) ≈ 1.21
        assert result is not None
        assert result.p_value == 1.0

    def test_matches_direct_double_sum(self) -> None:
        # Recoupement contre l'implémentation directe (indépendante du
        # balayage incrémental) sur une série non triviale.
        values = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
        result = pettitt(values)
        assert result is not None
        direct = {b: abs(_u_direct(values, b)) for b in range(1, len(values))}
        assert result.u_statistic == max(direct.values())
        assert direct[result.boundary] == result.u_statistic
        p_expected = min(
            1.0,
            2.0
            * math.exp(
                -6.0 * result.u_statistic**2 / (len(values) ** 3 + len(values) ** 2)
            ),
        )
        assert result.p_value == pytest.approx(p_expected)

    def test_rank_based_invariance(self) -> None:
        # Fondé sur les signes : toute transformation strictement croissante
        # des valeurs laisse K et la frontière inchangés.
        base = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        scaled = [v * 100 + 7 for v in base]
        a, b = pettitt(base), pettitt(scaled)
        assert a is not None and b is not None
        assert (a.boundary, a.u_statistic, a.p_value) == (
            b.boundary,
            b.u_statistic,
            b.p_value,
        )

    def test_fewer_than_two_points_yields_none(self) -> None:
        assert pettitt([]) is None
        assert pettitt([0.3]) is None
