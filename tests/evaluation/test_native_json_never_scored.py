"""``NATIVE_JSON`` n'est jamais noté (P5f 3).

C'est la réponse brute d'une API ; ce qui se note, c'est sa lecture en texte.
Deux gardes : aucune vue ne peut le déclarer candidat (refus au chargement), et
la règle par défaut de ``_candidate_for`` — l'étape la plus aval qui produit un
type candidat — choisit le texte d'une étape qui publie les deux.
"""

from __future__ import annotations

import pytest

from cinoc.app.run_planning import Competitor, plan_benchmark_run
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.runner import _candidate_for


def _artifact(kind: ArtifactType, step: str) -> Artifact:
    return Artifact(
        id=f"d:{step}:{kind.value}",
        document_id="d",
        type=kind,
        uri=f"/tmp/{step}.{kind.value}",
        produced_by_step=step,
    )


def test_a_view_cannot_declare_the_native_response_a_candidate() -> None:
    with pytest.raises(CinocError, match="native_json"):
        EvaluationView(
            name="brut",
            candidate_types=frozenset(
                {ArtifactType.RAW_TEXT, ArtifactType.NATIVE_JSON}
            ),
            metric_names=("cer",),
        )


def test_the_text_of_a_remote_step_is_scored_not_its_native_response() -> None:
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT}),
    )
    by_step = {
        "__initial__": {ArtifactType.IMAGE: _artifact(ArtifactType.IMAGE, "init")},
        "ocr": {
            ArtifactType.RAW_TEXT: _artifact(ArtifactType.RAW_TEXT, "ocr"),
            ArtifactType.NATIVE_JSON: _artifact(ArtifactType.NATIVE_JSON, "ocr"),
        },
        "llm": {
            ArtifactType.CORRECTED_TEXT: _artifact(ArtifactType.CORRECTED_TEXT, "llm"),
            ArtifactType.NATIVE_JSON: _artifact(ArtifactType.NATIVE_JSON, "llm"),
        },
    }
    candidate = _candidate_for(view, "chaine", by_step)
    assert candidate is not None and candidate.type is ArtifactType.CORRECTED_TEXT
    cible = view.model_copy(update={"target_step": "ocr"})
    amont = _candidate_for(cible, "chaine", by_step)
    assert amont is not None and amont.type is ArtifactType.RAW_TEXT


def test_no_planned_view_takes_the_native_response(tmp_path: object) -> None:
    corpus = CorpusSpec(
        name="c", documents=(DocumentRef(id="d", image_uri="/tmp/d.png"),)
    )
    spec = plan_benchmark_run(
        (
            Competitor(model="m", engine="mistral_ocr"),
            Competitor(model="m", engine="openai", mode="zero_shot"),
        ),
        corpus,
        "r",
    )(tmp_path)  # type: ignore[arg-type]
    assert spec.evaluation.views
    for view in spec.evaluation.views:
        assert ArtifactType.NATIVE_JSON not in view.candidate_types
