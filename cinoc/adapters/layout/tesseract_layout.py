"""``TesseractLayoutSegmenter`` — la mise en page **que Tesseract trouve lui-même**.

Le banc avait trois segmenteurs et tous supposaient un modèle en plus :
PP-DocLayout veut PaddleX, DocLayout-YOLO veut ses poids, le segmenteur distant
veut une adresse. Aucun ne faisait la chose la plus simple, et la plus utilisée :
**demander à Tesseract sa propre analyse de page**.

C'est pourtant la chaîne que la Library of Congress fait tourner en production
sur Chronicling America. Toutes les versions de NDNP-Open-OCR utilisent
« Tesseract's generalized layout detection model » ; le détecteur neuronal n'y
est qu'une **option** (v1.1+, modèle American Stories). Sans cette brique, le
banc ne pouvait pas exécuter la chaîne NDNP de référence — seulement sa variante
avancée, ce qui revenait à comparer un choix à lui-même.

Elle sert aussi de **second avis** au rattrapage (``gap_fill``) : NDNP croise la
lecture par régions avec une passe page entière, et c'est cette passe-là. Le
faire avec une mise en page pré-calculée aurait mimé la forme sans la substance.

Implémentation : une passe ``image_to_alto_xml`` sur la page, relue par le
parseur ALTO du dépôt puis projetée en ``CanonicalLayout``. Aucun code de
détection ici — la détection **est** celle de Tesseract, et c'est le but.
Contrairement aux autres segmenteurs, les régions sortent **déjà remplies** :
Tesseract lit en même temps qu'il découpe, et jeter son texte pour le
redemander bloc par bloc paierait deux fois la même lecture.
"""

from __future__ import annotations

from cinoc.adapters.layout._base import layout_step_output
from cinoc.adapters.ocr.tesseract import invoke_tesseract_alto
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError, FormatError
from cinoc.domain.layout import CanonicalLayout
from cinoc.formats.alto.layout_map import alto_to_layout
from cinoc.formats.alto.parser import parse_alto
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"

#: Défaut de NDNP-Open-OCR comme de Tesseract : analyse de page complète. C'est
#: le mode qui *fait* la segmentation ; un ``--psm 6`` traiterait la page comme
#: un bloc unique et il n'y aurait plus rien à découper.
DEFAULT_PSM = 3

_DEFAULT_TIMEOUT = 300.0


class TesseractLayoutSegmenter:
    """``IMAGE → LAYOUT`` par l'analyse de page native de Tesseract."""

    def __init__(
        self,
        *,
        lang: str = "fra",
        psm: int = DEFAULT_PSM,
        oem: int = 3,
        dpi: int | None = None,
    ) -> None:
        if not 0 <= psm <= 13:
            raise AdapterStepError(
                f"TesseractLayoutSegmenter : psm ∈ [0, 13], reçu {psm}."
            )
        if not 0 <= oem <= 3:
            raise AdapterStepError(
                f"TesseractLayoutSegmenter : oem ∈ [0, 3], reçu {oem}."
            )
        if dpi is not None and not 70 <= dpi <= 2400:
            raise AdapterStepError(
                f"TesseractLayoutSegmenter : dpi ∈ [70, 2400], reçu {dpi}."
            )
        self._lang = lang
        self._psm = psm
        self._oem = oem
        #: Résolution imposée. Sans elle, tesseract croit les métadonnées du
        #: fichier : une numérisation déclarée à 96 DPI lui fait conclure une page
        #: d'un mètre de large, et son analyse de page rend « Empty page!! ».
        self._dpi = dpi

    @property
    def name(self) -> str:
        return "tesseract_layout"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

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
        if context.workspace_uri is None:
            raise AdapterStepError(
                f"{self.name} : workspace requis (RunContext.workspace_uri)."
            )
        timeout = max(0.001, context.deadline.clamp_to_remaining(_DEFAULT_TIMEOUT))
        alto = invoke_tesseract_alto(
            image_path=image.uri,
            lang=self._lang,
            psm=self._psm,
            oem=self._oem,
            dpi=self._dpi,
            timeout=timeout,
        )
        return layout_step_output(self._to_layout(alto), context, self.name)

    def _to_layout(self, alto: bytes) -> CanonicalLayout:
        """ALTO natif → ``CanonicalLayout``, par le parseur du dépôt.

        Un ALTO illisible est une **erreur d'étape**, pas une page vide : rendre
        une page sans région ferait passer une panne de Tesseract pour un
        document blanc, et le CER l'attribuerait au moteur.
        """
        try:
            return alto_to_layout(parse_alto(alto))
        except (ValueError, FormatError) as exc:
            raise AdapterStepError(
                f"{self.name} : ALTO de Tesseract illisible — {exc}"
            ) from exc


__all__ = ["DEFAULT_PSM", "TesseractLayoutSegmenter"]
