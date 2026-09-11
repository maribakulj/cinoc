"""Étape de fusion : le contrat, et ce qu'il refuse.

C'est la seule tranche du plan qui touche le **contrat du pool d'artefacts**.
Le pool est indexé par type : deux sorties du même type s'y écrasent, et
``inputs_from`` ne nomme qu'une source par type. Une fusion ne pouvait donc pas
se déclarer — alors que la donnée existait déjà, l'exécuteur gardant les sorties
de chaque étape.

La solution est additive, comme l'a été le fan-out : un drapeau déclaratif que
l'exécuteur interprète, et un protocole **distinct** — élargir ``Module.execute``
aurait obligé les vingt-deux briques existantes à connaître un cas qui ne les
concerne pas.
"""

from __future__ import annotations

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.errors import CinocError
from cinoc.domain.pipeline import PipelineStep


def _etape(**kwargs: object) -> PipelineStep:
    base = {
        "id": "fusion",
        "kind": "merge",
        "adapter_name": "vote:v",
        "input_types": (ArtifactType.RAW_TEXT,),
        "output_types": (ArtifactType.RAW_TEXT,),
    }
    base.update(kwargs)
    return PipelineStep(**base)  # type: ignore[arg-type]


def test_a_merge_step_names_its_sources() -> None:
    etape = _etape(merge_from=("ocr_a", "ocr_b"))
    assert etape.merge_from == ("ocr_a", "ocr_b")


def test_one_source_is_refused() -> None:
    """Fusionner un seul avis ne fusionne rien — le dire plutôt que l'accepter."""
    with pytest.raises(CinocError, match="au moins deux"):
        _etape(merge_from=("ocr_a",))


def test_a_repeated_source_is_refused() -> None:
    """Le même avis compterait double et fausserait le vote en silence."""
    with pytest.raises(CinocError, match="répète"):
        _etape(merge_from=("ocr_a", "ocr_a"))


def test_merging_several_types_at_once_is_refused() -> None:
    """Une fusion porte sur **un** type : sinon « majorité » n'a pas de sens."""
    with pytest.raises(CinocError, match="un\\*\\* type|un type"):
        _etape(
            merge_from=("a", "b"),
            input_types=(ArtifactType.RAW_TEXT, ArtifactType.IMAGE),
        )


def test_a_step_cannot_merge_itself() -> None:
    with pytest.raises(CinocError, match="elle-même"):
        _etape(merge_from=("fusion", "ocr_a"))


def test_fanout_and_merge_exclude_each_other() -> None:
    """L'un démultiplie une étape par région, l'autre réunit des étapes."""
    with pytest.raises(CinocError, match="s'excluent"):
        _etape(
            merge_from=("a", "b"),
            fanout=True,
            input_types=(ArtifactType.LAYOUT,),
            output_types=(ArtifactType.LAYOUT,),
        )


def test_an_ordinary_step_is_unaffected() -> None:
    """La nouveauté est **additive** : sans ``merge_from``, rien ne change."""
    etape = _etape()
    assert etape.merge_from == ()
