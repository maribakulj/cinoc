"""Planification d'un run de **segmentation** seule (couche 6).

``IMAGE → LAYOUT``, sans score texte : la mise en page comme livrable (``cinoc
hybrid --segment-only``) et l'**aperçu** des régions du banc d'essai
(``/api/segmentation/run``). Ce n'est pas un pipeline qu'on compare : c'est un
transport de la segmentation, que ``PLAN_UI_COMPOSEUR.md`` §7 garde tel quel.

Le pipeline **hybride** (segmentation → reconnaissance par région → texte, ALTO)
est une recette — ``segmentation_puis_lecture`` —, construite par la file comme
toute autre (D-298). Ce module n'en planifie plus aucun.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cinoc.app.engines import segmenter_statuses
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationSpec
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec


class RunPlanningError(CinocError):
    """Segmenteur inconnu, ou réglage manquant d'un run de segmentation."""

#: Segmenteur de mise en page du socle **par défaut** — **source unique** du
#: *kind* (consommé par la planification du run de segmentation ET par le gate
#: du routeur).
SEGMENTER_KIND = "pp_doclayout"


def segmenter_kinds() -> tuple[str, ...]:
    """Segmenteurs du socle : **exactement** ceux que la page propose.

    Lus sur ``segmenter_statuses``, qui alimente le ``<select>`` du Banc
    d'essai — et non plus sur une constante écrite ici. Les deux listes avaient
    divergé : ``tesseract_layout`` et ``doclayout_yolo`` étaient proposés par la
    page puis refusés en 422, alors que ce sont les deux seuls segmenteurs
    exécutables sans PaddleX ni endpoint (D-269). Un segmenteur proposé mais
    absent de la machine se refuse à la **disponibilité** (409), jamais ici.
    """
    return tuple(status.kind for status in segmenter_statuses())


def _segmentation_spec(
    corpus: CorpusSpec,
    run_id: str,
    *,
    segmenter: str,
    adapter_kwargs: dict[str, dict[str, str | int | float | bool]],
) -> RunSpec:
    """Pipeline de segmentation à 1 étape : ``segmenter`` (IMAGE→LAYOUT).

    Aucune vue d'évaluation : un run de segmentation produit de la **géométrie**
    (captée par le sink), pas une métrique scalaire. Le ``RunResult`` reste
    l'output formel du run ; les régions se visualisent via l'aperçu du lanceur
    (``GET /api/segmentation/preview``).

    ``adapter_kwargs`` porte les paramètres de construction du module choisi
    (ex. ``endpoint``/``token`` du segmenteur distant) → factory + ``RunManifest``.
    """
    step = PipelineStep(
        id="seg",
        kind="layout",
        adapter_name=segmenter,
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.LAYOUT,),
    )
    return RunSpec(
        corpus=corpus,
        pipelines=(
            PipelineSpec(
                name=segmenter,
                initial_inputs=(ArtifactType.IMAGE,),
                steps=(step,),
            ),
        ),
        evaluation=EvaluationSpec(views=()),
        adapter_kwargs=adapter_kwargs,
        run_id=run_id,
    )


def plan_segmentation_run(
    corpus: CorpusSpec,
    run_id: str,
    *,
    segmenter: str = SEGMENTER_KIND,
    endpoint: str | None = None,
    token: str | None = None,
) -> Callable[[Path], RunSpec]:
    """Builder de spec d'un run de **segmentation**.

    ``segmenter`` choisit le module (l'un de ``segmenter_kinds()``). Pour
    ``remote_segmenter``, ``endpoint`` est **requis** (la cible object-detection) ;
    ``token`` est optionnel (auth de l'endpoint).
    """
    if segmenter not in segmenter_kinds():
        raise RunPlanningError(f"segmenteur inconnu : {segmenter!r}.")
    adapter_kwargs: dict[str, dict[str, str | int | float | bool]] = {}
    if segmenter == "remote_segmenter":
        if not endpoint:
            raise RunPlanningError(
                "remote_segmenter : 'endpoint' requis (cible object-detection)."
            )
        kwargs: dict[str, str | int | float | bool] = {"endpoint": endpoint}
        if token:
            kwargs["token"] = token
        adapter_kwargs[segmenter] = kwargs
    return lambda _ws: _segmentation_spec(
        corpus, run_id, segmenter=segmenter, adapter_kwargs=adapter_kwargs
    )


__all__ = [
    "SEGMENTER_KIND",
    "RunPlanningError",
    "plan_segmentation_run",
    "segmenter_kinds",
]
