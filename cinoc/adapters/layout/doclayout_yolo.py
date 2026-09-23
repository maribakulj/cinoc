"""``DocLayoutYoloSegmenter`` — segmenteur de mise en page réel (DocLayout-YOLO).

Jumeau de :mod:`cinoc.adapters.layout.pp_doclayout` : ``IMAGE → LAYOUT``, régions
**sans lignes** (la reconnaissance les remplit ensuite, fan-out couche 4), même
``Module`` Protocol, même conversion partagée en ``_base``. Seule diffère la
brique qui détecte.

**Pourquoi un second segmenteur.** Le banc en avait deux : PP-DocLayout, qui
exige PaddleX, et un segmenteur *distant*, qui exige une adresse. Sur une machine
sans l'un ni l'autre, aucune chaîne structurée n'était exécutable — et le
détecteur est précisément l'étage que ce banc existe pour comparer. DocLayout-YOLO
s'installe par pip, tire ses poids depuis le Hub, et tourne sur CPU : il rend la
famille hybride atteignable sans rien d'autre.

Ses poids ne voyagent pas dans le paquet : ``weights`` accepte un **chemin
local** ou, à défaut, l'entrée du Hub est téléchargée puis mise en cache. Le
détecteur reste **injectable** (``detector=``) pour que la conversion détections
→ ``CanonicalLayout`` se teste sans SDK ni poids ; le vrai modèle est un test
``live``/``slow`` opt-in.

Déterminisme (§12) : poids figés, ``conf`` fixe, et l'ordre de lecture est
**trié** par ``_base`` (haut→bas puis gauche→droite) — donc indépendant de
l'ordre dans lequel le détecteur rend ses boîtes.
"""

from __future__ import annotations

from typing import ClassVar

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

_VERSION = "1.0"

#: Seuil bas **assumé**. Une région manquée est perdue pour toute la chaîne (rien
#: ne la reconnaîtra ensuite) ; une région de trop coûte une reconnaissance et se
#: voit dans le rapport. L'asymétrie justifie de préférer le rappel.
DEFAULT_MIN_SCORE = 0.2

#: Poids de référence : DocStructBench, la variante entraînée sur des mises en
#: page **variées** (article, journal, formulaire) plutôt que sur un seul genre.
DEFAULT_REPO = "juliozhao/DocLayout-YOLO-DocStructBench"
DEFAULT_WEIGHTS = "doclayout_yolo_docstructbench_imgsz1024.pt"

#: Résolution d'inférence des poids publiés. La changer sans changer de poids
#: dégrade la détection en silence : le modèle a été entraîné à cette taille.
DEFAULT_IMGSZ = 1024


def resolve_weights(weights: str) -> str:
    """Chemin local des poids : tel quel s'il existe, sinon depuis le Hub.

    Un chemin l'emporte toujours : sur une machine hors ligne, ou avec des poids
    ré-entraînés, le Hub n'a pas à être consulté.
    """
    from pathlib import Path  # noqa: PLC0415

    if weights and Path(weights).is_file():
        return weights
    try:
        from huggingface_hub import (  # type: ignore[import-not-found,import-untyped]  # noqa: PLC0415, E501
            hf_hub_download,
        )
    except ImportError as exc:
        raise AdapterStepError(
            "doclayout_yolo : poids introuvables en local et huggingface_hub "
            "absent — installe `cinoc[yolo]` ou passe `weights=<chemin.pt>`."
        ) from exc
    return str(
        hf_hub_download(repo_id=DEFAULT_REPO, filename=weights or DEFAULT_WEIGHTS)
    )


def _detect_with_yolo(  # pragma: no cover -- SDK + poids requis (test 'live')
    image_path: str,
    *,
    weights: str,
    imgsz: int,
    min_score: float,
    device: str,
) -> LayoutDetection:
    """Détecte via **DocLayout-YOLO**. Isolé du reste → mockable.

    Le seuil est passé au modèle (``conf``) **et** re-appliqué par ``_base`` :
    l'un évite de transporter des boîtes qui seront jetées, l'autre garantit le
    contrat quel que soit le détecteur injecté.
    """
    try:
        from doclayout_yolo import (  # type: ignore[import-not-found,import-untyped]  # noqa: PLC0415, E501
            YOLOv10,
        )
    except ImportError as exc:
        raise AdapterStepError(
            "doclayout_yolo : SDK non installé (pip install 'cinoc[yolo]')."
        ) from exc

    modele = YOLOv10(resolve_weights(weights))
    resultats = modele.predict(
        image_path, imgsz=imgsz, conf=min_score, device=device, verbose=False
    )
    if not resultats:
        return LayoutDetection(page_width=0, page_height=0, regions=())
    premier = resultats[0]
    noms = getattr(premier, "names", {}) or {}
    boites = getattr(premier, "boxes", None)
    regions: list[DetectedRegion] = []
    if boites is not None:
        # ``strict`` : les trois listes décrivent les mêmes boîtes. Si elles
        # divergeaient, apparier en silence attribuerait un score à la mauvaise
        # région — mieux vaut que ça éclate.
        for xyxy, score, classe in zip(
            boites.xyxy.tolist(),
            boites.conf.tolist(),
            boites.cls.tolist(),
            strict=True,
        ):
            x1, y1, x2, y2 = (int(v) for v in xyxy)
            regions.append(
                DetectedRegion(
                    label=str(noms.get(int(classe), int(classe))),
                    x=x1,
                    y=y1,
                    width=x2 - x1,
                    height=y2 - y1,
                    score=float(score),
                )
            )
    forme = getattr(premier, "orig_shape", (0, 0))
    return LayoutDetection(
        page_width=int(forme[1]), page_height=int(forme[0]), regions=tuple(regions)
    )


class DocLayoutYoloSegmenter:
    """Segmenteur DocLayout-YOLO : ``IMAGE → LAYOUT`` (régions sans lignes)."""

    #: Étiquettes que ce modèle **sait** poser, lues sur les poids publiés.
    #:
    #: Les déclarer sert à valider : une table « classe → réglage » écrite pour
    #: un autre détecteur ne matcherait rien et se tairait. C'est arrivé — une
    #: table ``plain text:6,title:6`` appliquée au modèle American Stories, dont
    #: les classes sont ``article``/``author``, serait passée sans un mot et
    #: chaque région serait retombée sur le réglage par défaut.
    LABELS: ClassVar[frozenset[str]] = frozenset({
        "abandon", "figure", "figure_caption", "formula_caption",
        "isolate_formula", "plain text", "table", "table_caption",
        "table_footnote", "title",
    })

    #: Corpus d'entraînement, en clair. **DocStructBench ne contient aucun
    #: journal** : articles académiques, manuels scolaires, rapports de marché,
    #: documents financiers. Le dire évite de le découvrir après coup — le CER
    #: a doublé sur de la presse ancienne, et rien ne prévenait.
    DOMAIN: ClassVar[str] = "documents de bureau (DocStructBench — sans presse)"

    def __init__(
        self,
        *,
        weights: str = "",
        imgsz: int = DEFAULT_IMGSZ,
        min_score: float = DEFAULT_MIN_SCORE,
        device: str = "cpu",
        detector: DetectorFn | None = None,
    ) -> None:
        if not 0.0 <= min_score <= 1.0:
            raise AdapterStepError(
                f"DocLayoutYoloSegmenter : min_score ∈ [0, 1], reçu {min_score}."
            )
        if imgsz <= 0:
            raise AdapterStepError(
                f"DocLayoutYoloSegmenter : imgsz doit être > 0, reçu {imgsz}."
            )
        self._weights = weights
        self._imgsz = imgsz
        self._min_score = min_score
        self._device = device
        self._detector = detector

    @property
    def name(self) -> str:
        return "doclayout_yolo"

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
        return _detect_with_yolo(
            image_path,
            weights=self._weights,
            imgsz=self._imgsz,
            min_score=self._min_score,
            device=self._device,
        )

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


__all__ = [
    "DEFAULT_IMGSZ",
    "DEFAULT_MIN_SCORE",
    "DEFAULT_REPO",
    "DEFAULT_WEIGHTS",
    "DocLayoutYoloSegmenter",
    "resolve_weights",
]
