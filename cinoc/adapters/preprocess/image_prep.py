"""``ImagePreprocessor`` — ``IMAGE → IMAGE`` (couche 5).

Le banc savait lire une image, la segmenter, la transcrire, la corriger. Il ne
savait pas la **préparer** — alors que tous les systèmes de référence ont cet
étage : OCR-D en fait une famille entière (binarisation, rognage, débruitage,
redressement, dé-gondolage), PP-Structure ouvre par un module d'orientation et
de rectification, et NDNP le pratique avant Tesseract.

Sans ce rôle, une question restait sans réponse mesurable : **restaurer avant de
lire, est-ce que ça paie ?** Un banc ne doit pas y répondre par un score de
qualité arbitraire — c'est ce qui a fait retirer la mesure de qualité d'image de
ce dépôt (D-190) — mais en comparant deux pipelines sur le seul critère qui
tranche, le taux d'erreur.

Le pool d'artefacts étant indexé par type, l'``IMAGE`` produite **remplace**
l'originale pour les étapes suivantes : c'est le comportement voulu. Une étape
qui tiendrait à l'image d'origine la nomme explicitement dans son ``inputs_from``.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

import numpy as np

from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.adapters.preprocess._ops import (
    binarize,
    estimate_skew,
    otsu_threshold,
    to_grayscale,
)
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

_VERSION = "1.0"

#: Opérations disponibles, dans l'ordre où elles ont un sens : on redresse avant
#: de binariser (une binarisation fige les pixels, une rotation les ré-interpole).
OPERATIONS: tuple[str, ...] = ("grayscale", "deskew", "binarize")


class ImagePreprocessor:
    """Prépare une image avant lecture. Déterministe, local, sans modèle.

    ``operations`` est une liste **séparée par des virgules** — les paramètres
    d'adapter sont plats par contrat, et une liste imbriquée n'y entrerait pas.
    L'ordre déclaré est respecté tel quel : c'est un choix de l'utilisateur, et
    deux ordres différents sont deux pipelines différents à comparer.
    """

    def __init__(
        self,
        *,
        label: str,
        operations: str = "deskew,binarize",
        skew_amplitude_deg: float = 5.0,
    ) -> None:
        self._label = label
        self._skew = skew_amplitude_deg
        demandees = [o.strip() for o in operations.split(",") if o.strip()]
        inconnues = [o for o in demandees if o not in OPERATIONS]
        if inconnues:
            raise AdapterStepError(
                f"preprocess : opération(s) inconnue(s) {inconnues} "
                f"(attendu parmi {list(OPERATIONS)})."
            )
        if not demandees:
            raise AdapterStepError(
                "preprocess : aucune opération demandée — une étape qui ne fait "
                "rien fausserait la comparaison en se faisant passer pour un "
                "traitement."
            )
        self._operations = tuple(demandees)

    @property
    def name(self) -> str:
        return f"preprocess:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def operations(self) -> tuple[str, ...]:
        return self._operations

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],  # noqa: ARG002 — contrat Module
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        image = inputs.get(ArtifactType.IMAGE)
        if image is None or image.uri is None:
            raise AdapterStepError(
                f"{self.name} : artefact IMAGE manquant ou sans URI."
            )
        source = Path(image.uri)
        if not source.is_file():
            raise AdapterStepError(f"{self.name} : image introuvable ({source}).")

        try:
            import PIL  # noqa: PLC0415
            from PIL import Image, UnidentifiedImageError  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover — dépend de l'installation
            raise AdapterStepError(
                f"{self.name} : Pillow requis pour lire l'image (extra [images])."
            ) from exc

        try:
            with Image.open(source) as ouverte:
                tableau = _en_tableau(ouverte)
        except (UnidentifiedImageError, OSError) as exc:
            raise AdapterStepError(
                f"{self.name} : image illisible ({source.name}) — {exc}"
            ) from exc

        for operation in self._operations:
            control.raise_if_cancelled()
            tableau, note = self._appliquer(operation, tableau, PIL)
            # Journalisé plutôt que silencieux : l'angle réellement mesuré et le
            # seuil réellement calculé sont ce qui distingue deux exécutions sur
            # deux pages. Les taire rendrait le traitement inexplicable.
            logger.info("[preprocess] %s · %s", context.document_id, note)

        # PNG : la sortie d'une binarisation ne survit pas à une compression avec
        # perte, et un banc ne peut pas mesurer un traitement que l'encodage a
        # déjà modifié.
        tampon = io.BytesIO()
        Image.fromarray(tableau).save(tampon, format="PNG", optimize=True)
        octets = tampon.getvalue()

        cible = (
            workspace_artifact_path(
                context.workspace_uri, context.document_id, self._label, "png"
            )
            if context.workspace_uri
            else source.with_name(f"{source.stem}.{self._label}.png")
        )
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(octets)
        return StepOutput(
            artifacts={
                ArtifactType.IMAGE: Artifact(
                    id=f"{context.document_id}:{self._label}:image",
                    document_id=context.document_id,
                    type=ArtifactType.IMAGE,
                    uri=str(cible),
                    content_hash=compute_content_hash(octets),
                    produced_by_step=self._label,
                )
            }
        )

    def _appliquer(
        self, operation: str, matrice: np.ndarray, pil: Any
    ) -> tuple[np.ndarray, str]:
        """Applique une opération, et rend la note qui dit ce qu'elle a fait."""
        if operation == "grayscale":
            return to_grayscale(matrice), "grayscale"
        if operation == "deskew":
            angle = estimate_skew(to_grayscale(matrice), amplitude_deg=self._skew)
            if angle == 0.0:
                # Le dire : « aucune rotation appliquée » et « inclinaison
                # mesurée nulle » se ressemblent dans un rapport, et ne veulent
                # pas dire la même chose.
                return matrice, "deskew : 0,00° (aucune inclinaison mesurée)"
            tournee = pil.Image.fromarray(matrice).rotate(
                -angle,
                resample=pil.Image.Resampling.BICUBIC,
                expand=False,
                fillcolor=_fond(matrice),
            )
            return np.asarray(tournee), f"deskew : {angle:+.2f}°"
        gris = to_grayscale(matrice)
        seuil = otsu_threshold(gris)
        return binarize(gris, seuil), f"binarize : seuil d'Otsu {seuil}"


def _en_tableau(ouverte: Any) -> np.ndarray:
    """Image PIL → tableau numpy, en RVB ou en gris (jamais en palette)."""
    converti = ouverte if ouverte.mode in {"L", "RGB"} else ouverte.convert("RGB")
    return np.asarray(converti)


def _fond(matrice: np.ndarray) -> int | tuple[int, int, int]:
    """Remplissage d'une rotation : le blanc du support, jamais du noir.

    Combler avec du noir créerait de fausses zones d'encre dans les coins, que
    la binarisation prendrait ensuite pour du texte.
    """
    return 255 if matrice.ndim == 2 else (255, 255, 255)


__all__ = ["OPERATIONS", "ImagePreprocessor"]
