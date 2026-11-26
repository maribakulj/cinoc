"""Ce que la page propose, le planificateur l'accepte (P5d 4, D-269).

Le ``<select>`` des segmenteurs du Banc d'essai était alimenté par
``segmenter_statuses`` ; les planificateurs lisaient deux ensembles écrits à la
main (``SEGMENTER_KINDS``, ``PIPELINE_SEGMENTERS``). Les deux listes ont
divergé : ``tesseract_layout`` et ``doclayout_yolo`` étaient proposés par la
page puis refusés en 422 (« segmenteur non câblé ») — et ce sont précisément
les deux seuls segmenteurs exécutables sans PaddleX ni endpoint.

Le test part de **ce que la page reçoit** (``GET /api/recipes``, depuis que le
composeur est le catalogue de recettes, D-298), pas d'une constante : une
option ajoutée au catalogue sans être câblée le fait rougir, quelle que soit la
liste qui l'a fait entrer — pour la recette hybride comme pour l'aperçu de
segmentation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.app.engines import CLI_ONLY_KINDS
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.app.structure_planning import plan_segmentation_run, segmenter_kinds
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.run_spec import RunSpec
from cinoc.interfaces.web.app import create_app

_CORPUS = CorpusSpec(
    name="c", documents=(DocumentRef(id="d", image_uri="d.png", ground_truths=()),)
)
#: Ce qu'un utilisateur saisit pour le seul segmenteur qui exige une adresse.
_ENDPOINT = "https://segmenteur.example"


def _proposed(tmp_path: Path) -> list[str]:
    """Les segmenteurs de l'étape ``seg`` de la recette hybride, tels que la
    page les reçoit."""
    corps = (
        TestClient(create_app(reports_dir=tmp_path, rate_limit=1000))
        .get("/api/recipes")
        .json()
    )
    (recette,) = (
        r for r in corps["recipes"] if r["name"] == "segmentation_puis_lecture"
    )
    (etape,) = (e for e in recette["steps"] if e["role"] == "segmenter")
    return [b["kind"] for b in etape["bricks"]]


def _options(segmenter: str) -> dict[str, str]:
    return {"endpoint": _ENDPOINT} if segmenter == "remote_segmenter" else {}


def _first_step_is_buildable(spec: RunSpec, segmenter: str) -> None:
    """La spec nomme le segmenteur en tête, et le registre sait le construire."""
    step = spec.pipelines[0].steps[0]
    assert step.adapter_name.split(":", 1)[0] == segmenter
    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build(
        step.adapter_name, spec.adapter_kwargs.get(step.adapter_name, {})
    )
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert ArtifactType.LAYOUT in module.output_types


def test_the_page_proposes_the_two_light_segmenters(tmp_path: Path) -> None:
    """Témoin : sans eux, le test suivant ne prouverait rien du défaut."""
    proposed = _proposed(tmp_path)
    assert {"tesseract_layout", "doclayout_yolo"} <= set(proposed)


def test_the_page_proposes_no_command_line_brick(tmp_path: Path) -> None:
    assert not set(_proposed(tmp_path)) & CLI_ONLY_KINDS


@pytest.mark.parametrize("planner", ["recette", "segmentation"])
def test_every_proposed_segmenter_plans(tmp_path: Path, planner: str) -> None:
    """Chaque segmenteur proposé se planifie, en tête de la recette hybride ;
    et l'aperçu (un run de segmentation seule) accepte chaque détecteur.

    Les options grisées comptent aussi : « indisponible ici » (extra absent) se
    dit en 409 à la disponibilité, jamais en 422 à la planification. Le rejeu
    (``precomputed_layout``) n'est pas un détecteur : l'aperçu ne l'offre pas.
    """
    for segmenter in _proposed(tmp_path):
        endpoint = _options(segmenter).get("endpoint")
        if planner == "recette":
            spec = plan_recipe_run(
                _CORPUS,
                (
                    RecipeEntry(
                        recipe="segmentation_puis_lecture",
                        choices={"seg": segmenter},
                        params={"seg": {"endpoint": endpoint}} if endpoint else {},
                    ),
                ),
                run_id="r",
            )
        elif segmenter in segmenter_kinds():
            spec = plan_segmentation_run(
                _CORPUS, "r", segmenter=segmenter, endpoint=endpoint
            )(tmp_path)
        else:
            assert segmenter == "precomputed_layout"
            continue
        _first_step_is_buildable(spec, segmenter)
