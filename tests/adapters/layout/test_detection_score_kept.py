"""``to_canonical_layout`` garde le score de détection en ``Region.confidence``.

Il était jeté après le seuil : la mise en page d'un détecteur ne disait plus
quelles régions il tenait pour sûres.
"""

from __future__ import annotations

import pytest

from cinoc.adapters.layout._base import (
    DetectedRegion,
    LayoutDetection,
    to_canonical_layout,
)
from cinoc.adapters.layout.doclayout_yolo import _VERSION as YOLO
from cinoc.adapters.layout.pp_doclayout import _VERSION as PP
from cinoc.adapters.layout.remote import _VERSION as REMOTE
from cinoc.domain.errors import AdapterStepError


def _detection(*scores: float) -> LayoutDetection:
    return LayoutDetection(
        page_width=1000,
        page_height=800,
        regions=tuple(
            DetectedRegion(
                label="text", x=10, y=100 * n, width=50, height=40, score=score
            )
            for n, score in enumerate(scores)
        ),
    )


def test_le_score_devient_la_confiance_de_region() -> None:
    layout = to_canonical_layout(_detection(0.91, 0.55, 0.2), min_score=0.5)
    assert [r.confidence for r in layout.pages[0].regions] == [0.91, 0.55]


@pytest.mark.parametrize("score", [1.2, -0.1])
def test_un_score_hors_bornes_est_refuse(score: float) -> None:
    with pytest.raises(AdapterStepError, match="hors \\[0, 1\\]"):
        to_canonical_layout(_detection(score), min_score=-1.0)


def test_versions_des_segmenteurs_relevees() -> None:
    assert (PP, YOLO, REMOTE) == ("1.1", "1.1", "1.1")
