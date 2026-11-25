"""Ce que la page propose, le planificateur l'accepte (P5d 4, D-269).

Le ``<select>`` des segmenteurs du Banc d'essai est alimenté par
``segmenter_statuses`` ; les planificateurs lisaient deux ensembles écrits à la
main (``SEGMENTER_KINDS``, ``PIPELINE_SEGMENTERS``). Les deux listes ont
divergé : ``tesseract_layout`` et ``doclayout_yolo`` étaient proposés par la
page puis refusés en 422 (« segmenteur non câblé ») — et ce sont précisément
les deux seuls segmenteurs exécutables sans PaddleX ni endpoint.

Le test part de la **page rendue**, pas d'une constante : une option ajoutée au
``<select>`` sans être câblée le fait rougir, quelle que soit la liste qui l'a
fait entrer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.run_planning import Competitor, plan_benchmark_run
from cinoc.app.structure_planning import plan_hybrid_run, plan_segmentation_run
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.run_spec import RunSpec
from cinoc.interfaces.web.app import create_app

_SELECT = re.compile(r'<select id="draft-segmenter"[^>]*>(.*?)</select>', re.S)
_OPTION = re.compile(r'<option value="([^"]+)"')
_CORPUS = CorpusSpec(
    name="c", documents=(DocumentRef(id="d", image_uri="d.png", ground_truths=()),)
)
#: Ce qu'un utilisateur saisit pour le seul segmenteur qui exige une adresse.
_ENDPOINT = "https://segmenteur.example"


def _proposed(tmp_path: Path) -> list[str]:
    """Les valeurs du ``<select>`` des segmenteurs, telles que la page les rend."""
    body = TestClient(create_app(reports_dir=tmp_path, rate_limit=1000)).get(
        "/benchmark"
    ).text
    select = _SELECT.search(body)
    assert select is not None, "le <select> des segmenteurs a disparu de la page"
    return _OPTION.findall(select.group(1))


def _options(segmenter: str) -> dict[str, str]:
    return {"endpoint": _ENDPOINT} if segmenter == "remote_segmenter" else {}


def _first_step_is_buildable(spec: RunSpec, segmenter: str) -> None:
    """La spec nomme le segmenteur en tête, et le registre sait le construire."""
    step = spec.pipelines[0].steps[0]
    assert step.adapter_name == segmenter
    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build(segmenter, spec.adapter_kwargs.get(segmenter, {}))
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert ArtifactType.LAYOUT in module.output_types


def test_the_page_proposes_the_two_light_segmenters(tmp_path: Path) -> None:
    """Témoin : sans eux, le test suivant ne prouverait rien du défaut."""
    proposed = _proposed(tmp_path)
    assert {"tesseract_layout", "doclayout_yolo"} <= set(proposed)


@pytest.mark.parametrize("planner", ["benchmark", "hybrid", "segmentation"])
def test_every_proposed_segmenter_plans(tmp_path: Path, planner: str) -> None:
    """Chaque option du ``<select>`` se planifie, par les trois entrées.

    Les options grisées comptent aussi : « indisponible ici » (extra absent) se
    dit en 409 à la disponibilité, jamais en 422 à la planification.
    """
    for segmenter in _proposed(tmp_path):
        endpoint = _options(segmenter).get("endpoint")
        if planner == "benchmark":
            spec = plan_benchmark_run(
                (
                    Competitor(
                        engine="tesseract",
                        segmenter=segmenter,
                        segmenter_endpoint=endpoint,
                    ),
                ),
                _CORPUS,
                "r",
            )(tmp_path)
        elif planner == "hybrid":
            spec = plan_hybrid_run(
                _CORPUS, "r", segmenter=segmenter, endpoint=endpoint
            )(tmp_path)
        else:
            spec = plan_segmentation_run(
                _CORPUS, "r", segmenter=segmenter, endpoint=endpoint
            )(tmp_path)
        _first_step_is_buildable(spec, segmenter)
