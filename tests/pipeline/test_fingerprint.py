"""Ce que le fan-out fait des sorties d'un reconnaisseur entre dans l'empreinte
de **son** étape, et de nulle autre.

Une sortie de fan-out peut changer sans qu'aucun module ne change : c'est
l'exécuteur qui découpe le texte d'une région en lignes. Relever la version
de l'exécuteur entière ferait ré-exécuter toute une archive — un VLM sur la
page entière compris, qui ne passe jamais par le fan-out (S31L, D-311).
"""

from __future__ import annotations

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.pipeline import PipelineStep
from cinoc.pipeline import fingerprint
from cinoc.pipeline.fingerprint import ModuleIdentity, step_fingerprint

_IDENTITE = ModuleIdentity(version="1.0")


def _etape(*, fanout: bool) -> PipelineStep:
    return PipelineStep(
        id="reco",
        kind="region_recognizer",
        adapter_name="tesseract:reco",
        input_types=(ArtifactType.LAYOUT, ArtifactType.IMAGE),
        output_types=(ArtifactType.LAYOUT,),
        fanout=fanout,
        crop=fanout,
    )


def test_the_fanout_version_changes_only_fanout_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    avant_fanout = step_fingerprint(_etape(fanout=True), _IDENTITE)
    avant_page = step_fingerprint(_etape(fanout=False), _IDENTITE)
    monkeypatch.setattr(fingerprint, "FANOUT_VERSION", "test")
    assert step_fingerprint(_etape(fanout=True), _IDENTITE) != avant_fanout
    assert step_fingerprint(_etape(fanout=False), _IDENTITE) == avant_page
