"""``Region.confidence`` : optionnelle, dans [0, 1], jamais fabriquée par défaut."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from cinoc.domain.layout import CanonicalLayout, LayoutPage, Region


def test_absente_par_defaut() -> None:
    assert Region(id="r1").confidence is None


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0, 1])
def test_bornes_admises(value: float) -> None:
    assert Region(id="r1", confidence=value).confidence == value


@pytest.mark.parametrize("value", [-0.01, 1.01, math.nan, math.inf])
def test_hors_bornes_refusee(value: float) -> None:
    with pytest.raises(ValidationError):
        Region(id="r1", confidence=value)


def test_relue_depuis_le_json() -> None:
    layout = CanonicalLayout(
        pages=(LayoutPage(regions=(Region(id="r1", confidence=0.93),)),)
    )
    relu = CanonicalLayout.model_validate_json(layout.model_dump_json())
    assert relu.pages[0].regions[0].confidence == 0.93


def test_un_json_anterieur_sans_le_champ_se_relit() -> None:
    relu = CanonicalLayout.model_validate_json(
        '{"pages": [{"regions": [{"id": "r1", "region_type": "text"}]}]}'
    )
    assert relu.pages[0].regions[0].confidence is None
