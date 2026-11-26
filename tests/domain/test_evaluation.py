from __future__ import annotations

from cinoc.domain import (
    ArtifactType,
    EvaluationView,
    MetricSpec,
    ProjectionSpec,
)


def test_metric_spec_is_declarative():
    assert "func" not in MetricSpec.model_fields
    m = MetricSpec(
        name="cer", input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    )
    assert m.higher_is_better is False


def test_view_accepts():
    v = EvaluationView(name="text", candidate_types=frozenset({ArtifactType.RAW_TEXT}))
    assert v.accepts(ArtifactType.RAW_TEXT)
    assert not v.accepts(ArtifactType.ALTO_XML)


def test_projection_for_resolution():
    proj = ProjectionSpec(
        source_type=ArtifactType.ALTO_XML,
        target_type=ArtifactType.RAW_TEXT,
        projector_name="alto_to_text",
    )
    v = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT, ArtifactType.ALTO_XML}),
        projection=proj,
    )
    assert v.projection_for(ArtifactType.ALTO_XML) is proj
    assert v.projection_for(ArtifactType.RAW_TEXT) is None


#: Sérialise une vue et une métrique à ensembles de 3 éléments. Exécuté sous
#: plusieurs ``PYTHONHASHSEED`` : l'ordre d'itération d'un ``frozenset`` de
#: chaînes en dépend, et c'est ce qui rendait le ``RunResult`` instable (D-282).
_DUMP_SETS = """
from cinoc.domain import ArtifactType as T, EvaluationView, MetricSpec
v = EvaluationView(
    name="v",
    candidate_types=frozenset({T.RAW_TEXT, T.CORRECTED_TEXT, T.ALTO_XML}),
)
m = MetricSpec(name="m", input_types=(T.RAW_TEXT, T.RAW_TEXT), tags=frozenset("cab"))
print(v.model_dump_json(), m.model_dump_json())
"""


def test_set_fields_serialize_sorted_whatever_the_hash_seed():
    import os
    import subprocess
    import sys

    sorties = {
        subprocess.run(
            [sys.executable, "-c", _DUMP_SETS],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
        ).stdout
        for seed in range(8)
    }
    assert len(sorties) == 1, sorties
    assert '"candidate_types":["alto_xml","corrected_text","raw_text"]' in sorties.pop()


def test_set_fields_round_trip_from_sorted_json():
    v = EvaluationView(
        name="v",
        candidate_types=frozenset({ArtifactType.RAW_TEXT, ArtifactType.ALTO_XML}),
    )
    again = EvaluationView.model_validate_json(v.model_dump_json())
    assert again == v
    assert isinstance(again.candidate_types, frozenset)
    tags = MetricSpec(
        name="m",
        input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
        tags=frozenset({"b", "a"}),
    ).model_dump(mode="json")["tags"]
    assert tags == ["a", "b"]


def test_view_without_profile_gets_the_default_and_null_means_raw() -> None:
    """D-271, D-285 : omis → ``flat_text`` ; ``null`` explicite → brute.

    Le nom est toujours écrit au JSON : un ``RunResult`` dit sous quelle
    convention son chiffre a été calculé, et un JSON d'avant (``null`` = la
    comparaison brute d'alors) se relit avec le même sens.
    """
    from cinoc.domain.evaluation import DEFAULT_NORMALIZATION_PROFILE

    types = frozenset({ArtifactType.RAW_TEXT})
    default = EvaluationView(name="texte", candidate_types=types)
    assert default.normalization_profile == DEFAULT_NORMALIZATION_PROFILE == "flat_text"
    assert '"normalization_profile":"flat_text"' in default.model_dump_json()
    raw = EvaluationView.model_validate(
        {"name": "brut", "candidate_types": ["raw_text"], "normalization_profile": None}
    )
    assert raw.normalization_profile is None
    assert '"normalization_profile":null' in raw.model_dump_json()
    assert EvaluationView.model_validate_json(raw.model_dump_json()) == raw
