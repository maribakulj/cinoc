"""``LayoutToTextExtractor`` — ``LAYOUT rempli → RAW_TEXT`` (couche 5).

Quatrième étage **optionnel** d'un pipeline hybride : une fois les régions
reconnues (fan-out → ``CanonicalLayout`` rempli), on aplatit le texte dans
**l'ordre de lecture** pour le rendre **scorable** comme n'importe quelle sortie
``RAW_TEXT`` (CER/WER à la page). C'est ce qui permet à un run « segmenteur →
reconnaissance par bloc » d'être un **concurrent du Banc d'essai** comparé à un
OCR à plat, et plus seulement un ALTO produit dans son coin.

Déterministe : ordre = ``reading_order`` de la page (repli sur l'ordre déclaré),
lignes d'une région jointes par ``\\n``, régions par ``\\n``, pages par ``\\n``.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Region
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"


def _feuilles(regions: tuple[Region, ...]) -> list[Region]:
    """Régions **atomiques** : un bloc composé porte ses lignes dans ses enfants.

    Sans cette descente, tout ALTO à ``ComposedBlock`` — ce que Tesseract produit
    **toujours** — se projetait en texte **vide**, donc en CER de 1,0, sans un
    mot d'avertissement : les régions existaient, elles n'avaient simplement
    aucune ligne à leur propre niveau. Le module d'ordre de lecture descendait
    déjà ; celui-ci ne le faisait pas, et les deux lisent le même modèle.
    """
    sorties: list[Region] = []
    for region in regions:
        if region.regions:
            sorties.extend(_feuilles(region.regions))
        else:
            sorties.append(region)
    return sorties


def _page_text(page: LayoutPage) -> str:
    """Texte d'une page, régions dans l'ordre de lecture (repli ordre déclaré).

    ``reading_order`` nomme des régions qui peuvent être **composées** : on
    prend alors leurs feuilles, dans l'ordre. Un identifiant inconnu est ignoré,
    comme avant — un ordre partiel vaut mieux qu'un refus.
    """
    par_id = {region.id: region for region in _tous(page.regions)}
    ordonnees: list[Region] = []
    vues: set[str] = set()
    for rid in page.reading_order:
        region = par_id.get(rid)
        if region is None:
            continue
        for feuille in _feuilles((region,)):
            if feuille.id not in vues:
                ordonnees.append(feuille)
                vues.add(feuille.id)
    for feuille in _feuilles(page.regions):
        if feuille.id not in vues:
            ordonnees.append(feuille)
            vues.add(feuille.id)
    blocks: list[str] = []
    for region in ordonnees:
        lines = "\n".join(line.text for line in region.lines if line.text)
        if lines:
            blocks.append(lines)
    return "\n".join(blocks)


def _tous(regions: tuple[Region, ...]) -> list[Region]:
    """Toutes les régions, composées **et** feuilles : ``reading_order`` peut
    nommer les unes comme les autres."""
    out: list[Region] = []
    for region in regions:
        out.append(region)
        out.extend(_tous(region.regions))
    return out


class LayoutToTextExtractor:
    """Aplatit un ``LAYOUT`` rempli en ``RAW_TEXT`` (ordre de lecture, déterministe)."""

    def __init__(self, label: str) -> None:
        self._label = label

    @property
    def name(self) -> str:
        return f"layout_to_text:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.RAW_TEXT})

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        layout_art = inputs.get(ArtifactType.LAYOUT)
        if layout_art is None or layout_art.uri is None:
            raise AdapterStepError(
                f"{self.name} : artefact LAYOUT manquant ou sans URI."
            )
        layout_path = Path(layout_art.uri)
        try:
            layout = CanonicalLayout.model_validate_json(layout_path.read_bytes())
        except (OSError, ValueError) as exc:
            raise AdapterStepError(
                f"{self.name} : LAYOUT illisible ({layout_path.name!r}) : {exc}"
            ) from exc
        text = "\n".join(_page_text(page) for page in layout.pages)
        payload = text.encode("utf-8")
        out_dir = (
            Path(context.workspace_uri)
            if context.workspace_uri
            else layout_path.parent
        )
        out_path = out_dir / f"{context.document_id.replace('/', '_')}.layout.txt"
        out_path.write_bytes(payload)
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(out_path),
                    content_hash=compute_content_hash(payload),
                )
            }
        )


__all__ = ["LayoutToTextExtractor"]
