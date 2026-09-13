"""``LayoutGapFiller`` — ce que le détecteur a raté ne doit pas disparaître.

Une chaîne « segmenter → lire chaque région » a un défaut qu'aucune métrique de
texte ne désigne : **une région non détectée n'est pas mal lue, elle est
absente**. Le CER monte, et rien ne dit que la cause est un bloc manquant plutôt
qu'un OCR médiocre. NDNP-Open-OCR traite ce cas comme indispensable et le règle
en croisant deux lectures de la même page : celle par régions, et une passe
Tesseract sur la page **entière**. Tout bloc de la seconde qui ne recouvre
aucune région de la première est ajouté.

C'est une **fusion** au sens de la couche 4 (``PipelineStep.merge_from``), pas
une étape ordinaire : elle a deux sources et doit savoir laquelle fait autorité.
La première nommée est la référence — ses régions sont conservées telles quelles,
géométrie et texte compris — la seconde n'est qu'un réservoir de rattrapage.
L'inverse remplacerait le travail par région, plus fin, par une lecture de page
entière, et on aurait fait le chemin pour rien.

Deux décisions valent d'être dites :

* **Le recouvrement est jugé en surface relative au bloc candidat**, pas en
  intersection brute. Un entrefilet de 200 px² qui mord de 40 px² sur une
  colonne voisine reste un bloc distinct ; un bandeau qui couvre à 90 % une
  région déjà lue est un doublon. Un seuil sur l'aire du candidat distingue les
  deux ; un test d'intersection non nul les confondrait.
* **Un bloc ajouté est marqué** (``region_type`` suffixé ``+gapfill``). Sans
  marque, le rapport ne pourrait pas dire quelle part du texte vient du
  rattrapage — donc pas dire si le détecteur mérite qu'on lui fasse confiance.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import BBox, CanonicalLayout, LayoutPage, Region
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

_VERSION = "1.0"

#: Part de l'aire du **candidat** déjà couverte par une région retenue au-delà
#: de laquelle il est jugé redondant. 0,5 = « plus de la moitié de ce bloc est
#: déjà lue ». Réglable, parce que le bon seuil dépend de la finesse du
#: détecteur, mais jamais nul : à zéro, deux blocs qui se frôlent d'un pixel
#: s'annuleraient.
DEFAULT_OVERLAP = 0.5

#: Suffixe apposé au ``region_type`` d'un bloc rattrapé.
GAPFILL_SUFFIX = "+gapfill"


def _aire(box: BBox) -> int:
    return max(0, box.width) * max(0, box.height)


def _intersection(a: BBox, b: BBox) -> int:
    largeur = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    hauteur = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
    return max(0, largeur) * max(0, hauteur)


def _bbox(region: Region) -> BBox | None:
    return region.geometry.bbox if region.geometry else None


def couvert(candidat: Region, retenues: tuple[Region, ...], seuil: float) -> bool:
    """Le candidat est-il déjà lu ? Jugé sur **sa** surface, pas sur l'autre.

    Un bloc sans géométrie est déclaré couvert : on ne sait pas où il est, donc
    on ne peut ni le placer ni prouver qu'il manque. L'ajouter à l'aveugle
    dupliquerait du texte à une position inventée.
    """
    boite = _bbox(candidat)
    if boite is None:
        return True
    aire = _aire(boite)
    if aire <= 0:
        return True
    chevauche = sum(
        _intersection(boite, autre)
        for autre in (_bbox(r) for r in retenues)
        if autre is not None
    )
    return chevauche / aire >= seuil


def combler(
    principale: CanonicalLayout, secours: CanonicalLayout, *, seuil: float
) -> tuple[CanonicalLayout, int]:
    """``(mise en page complétée, nombre de blocs rattrapés)``.

    Page par page **par rang** : les deux lectures décrivent le même document, et
    apparier autrement (par identifiant) échouerait, les deux passes ne nommant
    pas leurs blocs de la même façon.
    """
    pages: list[LayoutPage] = []
    rattrapes = 0
    for index, page in enumerate(principale.pages):
        jumelle = secours.pages[index] if index < len(secours.pages) else None
        ajouts: list[Region] = []
        if jumelle is not None:
            for candidat in jumelle.regions:
                if couvert(candidat, page.regions + tuple(ajouts), seuil):
                    continue
                marque = f"{candidat.region_type or 'text'}{GAPFILL_SUFFIX}"
                ajouts.append(
                    candidat.model_copy(
                        update={
                            "id": f"gapfill_{candidat.id}",
                            "region_type": marque,
                        }
                    )
                )
        rattrapes += len(ajouts)
        # Ordre : celui de la lecture par régions, les rattrapages ensuite. Un
        # étage d'ordre de lecture en aval les replacera ; les intercaler ici
        # sur une intuition de position ferait deux ordres concurrents.
        pages.append(page.model_copy(update={"regions": page.regions + tuple(ajouts)}))
    return CanonicalLayout(pages=tuple(pages)), rattrapes


class LayoutGapFiller:
    """Fusionne deux ``LAYOUT`` : le fin fait autorité, l'autre comble les trous."""

    def __init__(self, *, label: str, overlap: float = DEFAULT_OVERLAP) -> None:
        if not 0.0 < overlap <= 1.0:
            raise AdapterStepError(
                f"LayoutGapFiller : overlap ∈ ]0, 1], reçu {overlap}. "
                "Zéro annulerait deux blocs qui se frôlent d'un pixel."
            )
        self._label = label
        self._overlap = overlap

    @property
    def name(self) -> str:
        return f"gap_fill:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    def execute_merge(
        self,
        sources: Mapping[str, Artifact],
        params: dict[str, ParamValue],  # noqa: ARG002 — contrat MergingModule
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        if len(sources) != 2:
            raise AdapterStepError(
                f"{self.name} : exactement deux sources attendues "
                f"(régions puis page entière), reçu {len(sources)}."
            )
        # ``merge_from`` conserve l'ordre déclaré : la **première** source est la
        # lecture qui fait autorité. Trier par nom ici rendrait le résultat
        # dépendant de l'alphabet des identifiants d'étape.
        noms = list(sources)
        principale = self._charger(sources[noms[0]], noms[0])
        secours = self._charger(sources[noms[1]], noms[1])
        complete, rattrapes = combler(principale, secours, seuil=self._overlap)
        return self._emit(complete, rattrapes, context)

    def _charger(self, artifact: Artifact, nom: str) -> CanonicalLayout:
        if artifact.uri is None:
            raise AdapterStepError(f"{self.name} : source {nom!r} sans URI.")
        try:
            return CanonicalLayout.model_validate_json(
                Path(artifact.uri).read_bytes()
            )
        except (OSError, ValueError) as exc:
            raise AdapterStepError(
                f"{self.name} : source {nom!r} illisible en layout — {exc}"
            ) from exc

    def _emit(
        self, layout: CanonicalLayout, rattrapes: int, context: RunContext
    ) -> StepOutput:
        if context.workspace_uri is None:
            raise AdapterStepError(f"{self.name} : workspace requis.")
        payload = layout.model_dump_json().encode("utf-8")
        chemin = workspace_artifact_path(
            context.workspace_uri, context.document_id, self.name, "layout.json"
        )
        chemin.write_bytes(payload)
        # Le compte est journalisé et **la marque reste dans le layout** : c'est
        # elle, pas ce message, qui permettra au rapport de dire quelle part du
        # texte vient du rattrapage.
        logger.info(
            "[gap_fill] %s : %d bloc(s) rattrapé(s) sur %s",
            self.name,
            rattrapes,
            context.document_id,
        )
        return StepOutput(
            artifacts={
                ArtifactType.LAYOUT: Artifact(
                    id=f"{context.document_id}:{self.name}:layout",
                    document_id=context.document_id,
                    type=ArtifactType.LAYOUT,
                    uri=str(chemin),
                    content_hash=compute_content_hash(payload),
                )
            }
        )


__all__ = [
    "DEFAULT_OVERLAP",
    "GAPFILL_SUFFIX",
    "LayoutGapFiller",
    "combler",
    "couvert",
]
