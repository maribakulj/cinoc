"""``PPDocLayoutSegmenter`` — segmenteur de mise en page réel (PP-DocLayout).

Détecte les **régions** d'une page (titre, paragraphe, figure, tableau…) et émet
un ``LAYOUT`` (``CanonicalLayout`` à régions **sans lignes** — la reconnaissance
les remplit ensuite, cf. fan-out couche 4). Implémente le ``Module`` Protocol
**directement**, comme les autres adapters.

Module **maison du socle** (≠ plugin tiers découvert) : enregistré par
``register_default_modules`` → disponible **même en mode public** sur le Space
(contrairement aux plugins via entry-points, fail-closed). Son SDK (PaddleX,
Apache-2.0) est un **extra optionnel** (``cinoc[segment]``), importé
**paresseusement** : importer ce module n'exige ni la lib ni les poids — seule
l'exécution les requiert.

Le détecteur est **injectable** (``detector=``) : la conversion détections →
``CanonicalLayout`` se teste sans SDK ni poids (CI), le vrai modèle reste un test
``live``/``slow`` opt-in. Déterminisme (§12) : à modèle + poids + params figés et
seuil de score fixe, la sortie est stable ; l'ordre de lecture est **trié**
(haut→bas puis gauche→droite), indépendant de l'ordre de détection.
"""

from __future__ import annotations

from typing import ClassVar

from cinoc.adapters._params import instance_label_param, instance_name
from cinoc.adapters.layout._base import (
    DetectedRegion,
    DetectorFn,
    LayoutDetection,
    layout_step_output,
    to_canonical_layout,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

#: 1.1 : le score de détection est gardé (``Region.confidence``).
_VERSION = "1.1"
_DEFAULT_MIN_SCORE = 0.5


#: Modèle PP-DocLayout par défaut. La variante **légère** ``PP-DocLayout-S``
#: (poids ~10× plus petits) est bakable dans l'image Space pour **tester
#: l'option** sans peser sur le free-tier ; ``-L`` reste le défaut qualité.
#: Surchargé par ``CINOC_PPDOCLAYOUT_MODEL`` (lu par le builder) ou ``model=``.
_DEFAULT_MODEL = "PP-DocLayout-L"


def _detect_with_paddle(  # pragma: no cover -- SDK + poids requis (test 'live')
    image_path: str, model: str = _DEFAULT_MODEL
) -> LayoutDetection:
    """Détecte la mise en page via **PaddleX PP-DocLayout**. Isolé → mockable.

    SDK absent → ``AdapterStepError`` explicite (l'extra ``[segment]`` manque) ;
    le module reste listable, il ne plante pas à l'import. Le corps qui exécute le
    modèle n'est exercé que par un test ``live`` (SDK + poids installés). ``model``
    choisit la variante (``-L`` qualité / ``-S`` légère)."""
    try:
        from paddlex import create_model  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AdapterStepError(
            "pp_doclayout : PaddleX non installé "
            "(pip install 'cinoc[segment]' + poids PP-DocLayout)."
        ) from exc
    results = list(create_model(model).predict(image_path, batch_size=1))
    if not results:
        return LayoutDetection(page_width=0, page_height=0, regions=())
    boxes = results[0].get("boxes", [])
    regions = tuple(
        DetectedRegion(
            label=str(box.get("label", "")),
            x=int(box["coordinate"][0]),
            y=int(box["coordinate"][1]),
            width=int(box["coordinate"][2]) - int(box["coordinate"][0]),
            height=int(box["coordinate"][3]) - int(box["coordinate"][1]),
            score=float(box.get("score", 0.0)),
        )
        for box in boxes
    )
    shape = results[0].get("input_img_shape") or (0, 0)
    return LayoutDetection(
        page_width=int(shape[1]), page_height=int(shape[0]), regions=regions
    )


class PPDocLayoutSegmenter:
    """Segmenteur PP-DocLayout : ``IMAGE → LAYOUT`` (régions sans lignes)."""

    #: Réglages acceptés (``pipeline.params``) : tout autre est refusé, nommé.
    PARAMS: ClassVar[tuple[Param, ...]] = (
        Param("model", "str",
              "Variante (défaut : CINOC_PPDOCLAYOUT_MODEL, sinon PP-DocLayout-L)",
              "Variant (default: CINOC_PPDOCLAYOUT_MODEL, else PP-DocLayout-L)"),
        instance_label_param(),
    )

    def __init__(
        self,
        *,
        model: str = _DEFAULT_MODEL,
        min_score: float = _DEFAULT_MIN_SCORE,
        label: str | None = None,
        detector: DetectorFn | None = None,
    ) -> None:
        if not 0.0 <= min_score <= 1.0:
            raise AdapterStepError(
                f"PPDocLayoutSegmenter : min_score ∈ [0, 1], reçu {min_score}."
            )
        self._model = model
        self._min_score = min_score
        self._label = label
        self._detector = detector

    @property
    def name(self) -> str:
        return instance_name("pp_doclayout", self._label)

    @property
    def version(self) -> str:
        return _VERSION

    def effective_settings(self) -> dict[str, str]:
        """La variante du modèle (``PP-DocLayout-L`` / ``-S``…) : la fabrique la
        prend à ``CINOC_PPDOCLAYOUT_MODEL`` quand la spec ne la nomme pas —
        écrite ici, elle entre au manifeste et dans l'empreinte de l'étape."""
        return {"model": self._model}

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    def _detect(self, image_path: str) -> LayoutDetection:
        if self._detector is not None:
            return self._detector(image_path)
        return _detect_with_paddle(image_path, self._model)

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        image = inputs.get(ArtifactType.IMAGE)
        if image is None or image.uri is None:
            raise AdapterStepError(
                f"{self.name} : artefact IMAGE manquant ou sans URI."
            )
        if context.workspace_uri is None:
            raise AdapterStepError(
                f"{self.name} : workspace requis (RunContext.workspace_uri)."
            )
        layout = to_canonical_layout(
            self._detect(image.uri), min_score=self._min_score
        )
        return layout_step_output(layout, context, self.name)


__all__ = ["PPDocLayoutSegmenter"]
