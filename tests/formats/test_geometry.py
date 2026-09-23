"""Tests des primitives géométriques partagées."""

from __future__ import annotations

import pytest

from cinoc.formats._geometry import format_points, parse_points


def test_parse_points_valid() -> None:
    assert parse_points("0,0 10,5 10,15") == ((0, 0), (10, 5), (10, 15))


def test_parse_points_truncates_floats() -> None:
    assert parse_points("1.9,2.1") == ((1, 2),)


@pytest.mark.parametrize("bad", ["garbage", "10", "10,", ",5", ""])
def test_parse_points_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_points(bad)


def test_format_points_roundtrip() -> None:
    pts = ((0, 0), (10, 5))
    assert parse_points(format_points(pts)) == pts


# --------------------------------------------------------------------------- #
# Les deux écritures ALTO
# --------------------------------------------------------------------------- #


def test_parse_points_accepts_the_flat_alto_notation() -> None:
    """**Régression.** Le schéma ALTO v4 admet les deux écritures, et le dit.

    ``PointsType`` documente ``"x1,y1 x2,y2"`` comme « hautement recommandée »
    *et* ``"x1 y1 x2 y2"`` comme « conservée pour compatibilité, car des outils
    l'utilisent actuellement ».

    N'accepter que la première paraissait rigoureux et ne l'était pas : le
    premier outil réellement branché — ``kraken``, qui écrit la seconde — a vu
    **toute** sa géométrie jetée. 29 lignes sur 29 sortaient sans coordonnées,
    avec pour seule trace un avertissement dans le journal.
    """
    assert parse_points("0 0 10 5 10 15") == ((0, 0), (10, 5), (10, 15))


def test_the_two_notations_describe_the_same_polygon() -> None:
    assert parse_points("1 2 3 4") == parse_points("1,2 3,4")


def test_a_flat_list_of_odd_length_is_refused() -> None:
    """Les coordonnées ne s'apparient pas : le fichier est abîmé, pas exotique."""
    with pytest.raises(ValueError, match="impaire"):
        parse_points("1 2 3")


def test_a_mixed_notation_is_refused() -> None:
    """Aucune des deux écritures n'autorise le mélange.

    L'accepter reviendrait à deviner, et masquerait un fichier réellement
    corrompu au lieu de le signaler.
    """
    with pytest.raises(ValueError):
        parse_points("1,2 3 4")
