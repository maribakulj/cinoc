"""``RemoteSegmenter`` — segmenteur de mise en page **par appel distant**.

Au lieu d'embarquer un modèle lourd (poids dans l'image), ce module **délègue** la
détection de régions à un modèle hébergé ailleurs : un *Inference Endpoint* HF, un
Space-modèle, ou tout service exposant l'API **object-detection** de Hugging Face.
Cinoc **orchestre**, le modèle **tourne à distance** — le Space reste léger (pas de
poids, pas d'inférence CPU locale).

C'est l'incarnation « distante » du point d'extension unique de Cinoc : il
implémente le **même ``Module`` Protocol** que ``PPDocLayoutSegmenter`` (et que les
plugins tiers), donc il apparaît comme **segmenteur sélectionnable** avant un run.
On change de modèle en changeant l'``endpoint`` — sans rien réinstaller.

Schéma de réponse attendu = sortie **object-detection** HF :
``[{"label": str, "score": float, "box": {"xmin","ymin","xmax","ymax"}}, …]``.

Le détecteur est **injectable** (``detector=``) : la conversion détections →
``CanonicalLayout`` se teste sans réseau ; le vrai appel passe par ``post_json``
(anti-SSRF **épinglé** : l'IP validée est celle à laquelle on se connecte). ``httpx``
(dépendance de base) est importé paresseusement.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.adapters.corpus._http import HttpFetchError, SsrfError, post_json
from cinoc.adapters.layout._base import (
    DetectedRegion,
    DetectorFn,
    LayoutDetection,
    layout_step_output,
    to_canonical_layout,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

#: 1.1 : le score de détection est gardé (``Region.confidence``).
#: 1.2 : un score absent ou illisible reste absent (il était lu 0,0, d'où une
#: confiance inventée sous ``min_score=0``).
_VERSION = "1.2"
_DEFAULT_MIN_SCORE = 0.5
_DEFAULT_TIMEOUT = 60.0


def parse_hf_detections(
    payload: object, *, page_width: int, page_height: int
) -> LayoutDetection:
    """Réponse object-detection HF → ``LayoutDetection`` (tolérante aux entrées
    mal formées : les boîtes invalides sont ignorées, jamais une exception)."""
    if not isinstance(payload, list):
        raise AdapterStepError(
            "remote_segmenter : réponse inattendue (liste de détections attendue)."
        )
    regions: list[DetectedRegion] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        box = item.get("box")
        if not isinstance(box, dict):
            continue
        try:
            x0, y0 = int(box["xmin"]), int(box["ymin"])
            x1, y1 = int(box["xmax"]), int(box["ymax"])
        except (KeyError, TypeError, ValueError):
            continue
        regions.append(
            DetectedRegion(
                label=str(item.get("label", "")),
                x=x0,
                y=y0,
                width=max(0, x1 - x0),
                height=max(0, y1 - y0),
                score=_score(item.get("score")),
            )
        )
    return LayoutDetection(
        page_width=page_width, page_height=page_height, regions=tuple(regions)
    )


def _score(value: object) -> float | None:
    """Score d'une détection, ou ``None`` s'il est absent ou non numérique —
    jamais 0,0 : un score qu'on n'a pas lu n'est pas une confiance nulle."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _image_dims(image_path: str) -> tuple[int, int]:
    """Dimensions ``(largeur, hauteur)`` de l'image ; ``(0, 0)`` si indisponible
    (Pillow absent / illisible) — la conversion gère les dimensions nulles."""
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return (0, 0)
    try:
        with Image.open(image_path) as opened:
            return (int(opened.width), int(opened.height))
    except (UnidentifiedImageError, OSError):
        return (0, 0)


class RemoteSegmenter:
    """Segmenteur ``IMAGE → LAYOUT`` délégué à un endpoint object-detection."""

    def __init__(
        self,
        *,
        endpoint: str,
        token: str | None = None,
        min_score: float = _DEFAULT_MIN_SCORE,
        timeout: float = _DEFAULT_TIMEOUT,
        detector: DetectorFn | None = None,
    ) -> None:
        if not endpoint:
            raise AdapterStepError("remote_segmenter : 'endpoint' requis.")
        if not 0.0 <= min_score <= 1.0:
            raise AdapterStepError(
                f"remote_segmenter : min_score ∈ [0, 1], reçu {min_score}."
            )
        self._endpoint = endpoint
        self._token = token
        self._min_score = min_score
        self._timeout = timeout
        self._detector = detector

    @property
    def name(self) -> str:
        return "remote_segmenter"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    def _detect(self, image_path: str) -> LayoutDetection:
        if self._detector is not None:
            return self._detector(image_path)
        return self._remote_detect(image_path)

    def _remote_detect(  # pragma: no cover -- réseau réel (test 'live')
        self, image_path: str
    ) -> LayoutDetection:
        headers = {"Content-Type": "application/octet-stream"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            payload = post_json(
                self._endpoint,
                content=Path(image_path).read_bytes(),
                headers=headers,
                timeout=self._timeout,
            )
        except SsrfError as exc:
            raise AdapterStepError(
                f"remote_segmenter : endpoint refusé (anti-SSRF) : {exc}"
            ) from exc
        except HttpFetchError as exc:
            raise AdapterStepError(
                f"remote_segmenter : appel à l'endpoint échoué : {exc}"
            ) from exc
        width, height = _image_dims(image_path)
        return parse_hf_detections(payload, page_width=width, page_height=height)

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
        layout = to_canonical_layout(
            self._detect(image.uri), min_score=self._min_score
        )
        return layout_step_output(layout, context, self.name)


__all__ = ["RemoteSegmenter", "parse_hf_detections"]
