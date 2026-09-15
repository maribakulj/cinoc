"""Fan-out par région — le cœur net-new de la tranche segmentation (couche 4).

``segmentation (IMAGE → LAYOUT régions-seules) → reconnaissance PAR RÉGION (remplit
le LAYOUT)``. Le ``Module`` reste **inchangé** : il renvoie *un* artefact par type ;
c'est **l'orchestration** (ici) qui boucle sur les N régions, collecte les N
sorties (estampillées ``region_id``), **tolère les échecs partiels** (une région
qui échoue n'abat pas la page) et réassemble en respectant l'ordre de lecture.

Le recognizer reçoit une IMAGE **cadrée par région**. Deux modes :
- **``precomputed``** (pas de ``cropper``) : l'IMAGE page entière est passée avec
  ``region_id`` posé (la donnée précalculée est figée par région) ;
- **hybride réel** (``cropper`` injecté) : le bloc est **découpé** de l'image — la
  pièce qui rend « segmentation externe → OCR des blocs » réel. Le découpage PIL
  vit en couche 5 (``cropper``) ; ici on ne calcule que la **boîte relative**
  (arithmétique, unités neutralisées : ALTO ``mm10`` vs pixels).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from pathlib import Path

from cinoc.domain.artifacts import (
    Artifact,
    ArtifactType,
    compute_content_hash,
)
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Line, Region
from cinoc.domain.usage import ResourceUsage
from cinoc.pipeline.protocols import Module, ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

#: Découpeur de bloc injecté (impl PIL en couche 5) :
#: ``(image_page, boîte_relative, region_id, contexte) → artefact IMAGE du bloc``.
RegionCropper = Callable[
    [Artifact, tuple[float, float, float, float], str, RunContext], Artifact
]


def _relative_bbox(
    region: Region, page: LayoutPage
) -> tuple[float, float, float, float] | None:
    """Boîte de la région en coordonnées relatives ``[0, 1]`` (unités neutralisées)."""
    geometry = region.geometry
    width, height = page.width, page.height
    if geometry is None or not width or not height:
        return None
    if geometry.bbox is not None:
        b = geometry.bbox
        x0, y0, x1, y1 = b.x, b.y, b.x + b.width, b.y + b.height
    elif geometry.polygon:
        xs = [p[0] for p in geometry.polygon]
        ys = [p[1] for p in geometry.polygon]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    else:
        return None
    return (x0 / width, y0 / height, x1 / width, y1 / height)


def run_region_fanout(
    *,
    layout: CanonicalLayout,
    page_image: Artifact,
    recognizer: Module,
    context: RunContext,
    control: RunControl,
    params: Mapping[str, ParamValue] | None = None,
    cropper: RegionCropper | None = None,
) -> tuple[CanonicalLayout, ResourceUsage]:
    """Remplit ``layout`` (régions seules) par reconnaissance région par région.

    Renvoie ``(CanonicalLayout rempli, usage)`` : chaque région porte sa ligne
    de texte reconnu ; ``usage`` somme les jetons remontés par le recognizer
    (un appel par région). Une région dont la reconnaissance échoue reste
    **vide** (texte non produit, avertissement journalisé) — la page n'est pas
    abattue. Avec un ``cropper``, chaque bloc est **découpé** de l'image avant
    OCR (pipeline réel).
    """
    step_params = dict(params) if params is not None else {}
    usage = ResourceUsage()
    pages: list[LayoutPage] = []
    for page in layout.pages:
        filled_page, page_usage = _fill_page(
            page, page_image, recognizer, context, control, step_params, cropper
        )
        pages.append(filled_page)
        usage = usage.merged_with(page_usage)
    return CanonicalLayout(pages=tuple(pages)), usage


def _fill_page(
    page: LayoutPage,
    page_image: Artifact,
    recognizer: Module,
    context: RunContext,
    control: RunControl,
    params: dict[str, ParamValue],
    cropper: RegionCropper | None,
) -> tuple[LayoutPage, ResourceUsage]:
    usage = ResourceUsage()
    filled: list[Region] = []
    for region in page.regions:
        filled_region, region_usage = _fill_region(
            region, page, page_image, recognizer, context, control, params, cropper
        )
        filled.append(filled_region)
        usage = usage.merged_with(region_usage)
    return page.model_copy(update={"regions": tuple(filled)}), usage


def _region_image(
    region: Region,
    page: LayoutPage,
    page_image: Artifact,
    context: RunContext,
    cropper: RegionCropper | None,
) -> Artifact | None:
    """IMAGE passée au recognizer : crop réel si ``cropper``, sinon image entière."""
    if cropper is None:
        return page_image.model_copy(
            update={
                "id": f"{page_image.id}:{region.id}",
                "region_id": region.id,
                "produced_by_step": None,
                "provenance": None,
            }
        )
    rel = _relative_bbox(region, page)
    if rel is None:
        logger.warning(
            "[fanout] région %r sans géométrie : non découpable, ignorée", region.id
        )
        return None
    return cropper(page_image, rel, region.id, context)


#: Clé **réservée** que le fan-out pose dans les ``params`` du reconnaisseur :
#: la classe de la région en cours (``article``, ``advertisement``, …), ou une
#: chaîne vide si la segmentation n'en donne pas.
#:
#: Le contrat du ``Module`` dit que ``params`` est une copie mutable fournie par
#: le runner : la renseigner est donc son rôle, pas un détournement. Ce qui
#: serait un détournement, c'est qu'un module **écrive** dedans.
#:
#: Sans elle, un reconnaisseur applique le même réglage à un pavé d'article et à
#: une publicité. NDNP-Open-OCR, lui, bascule de ``--psm 6`` à ``--psm 3`` selon
#: la classe : c'est cette information-là qui manquait pour le reproduire.
REGION_TYPE_PARAM = "region_type"


def _fill_region(
    region: Region,
    page: LayoutPage,
    page_image: Artifact,
    recognizer: Module,
    context: RunContext,
    control: RunControl,
    params: dict[str, ParamValue],
    cropper: RegionCropper | None,
) -> tuple[Region, ResourceUsage | None]:
    """Remplit une région de ses lignes — **en descendant** dans ses enfants.

    Un bloc composé (ALTO ``ComposedBlock``) porte ses lignes dans ses enfants, pas
    à son niveau. L'océriser lui-même accrochait le texte au parent, que la
    projection ne relit pas : elle lit ``leaf_regions()``. Le texte était donc
    produit puis **jeté sans un avertissement**.

    Le défaut a survécu parce que le corpus d'essai ne contenait aucun bloc
    composé ; la presse réelle en est pleine. C'est la même incohérence que celle
    documentée par ``LayoutPage.leaf_regions`` — des modules qui ne font pas le
    même parcours — à l'autre bout de la chaîne.
    """
    control.raise_if_cancelled()
    if region.regions:
        enfants: list[Region] = []
        usage = ResourceUsage()
        for enfant in region.regions:
            rempli, usage_enfant = _fill_region(
                enfant, page, page_image, recognizer, context, control, params, cropper
            )
            enfants.append(rempli)
            usage = usage.merged_with(usage_enfant)
        return region.model_copy(update={"regions": tuple(enfants)}), usage

    region_image = _region_image(region, page, page_image, context, cropper)
    if region_image is None:
        return region, None
    try:
        par_region = dict(params)
        par_region[REGION_TYPE_PARAM] = region.region_type or ""
        output = recognizer.execute(
            {ArtifactType.IMAGE: region_image}, par_region, context, control
        )
        lignes = _lignes_reconnues(output.artifacts, region)
    except AdapterStepError as exc:
        logger.warning(
            "[fanout] région %r non reconnue (ignorée) : %s", region.id, exc
        )
        return region, None
    return region.model_copy(update={"lines": lignes}), output.usage


def _lignes_reconnues(
    outputs: Mapping[ArtifactType, Artifact], region: Region
) -> tuple[Line, ...]:
    """Les lignes que le reconnaisseur a rendues — **plusieurs si il sait**.

    Un reconnaisseur qui déclare ``LAYOUT`` en sortie sait découper son bloc en
    lignes : on les greffe telles quelles. Celui qui ne déclare que ``RAW_TEXT``
    n'a qu'un texte à donner, et la région n'a donc qu'une ligne.

    **Le défaut que cette distinction ferme.** Le fan-off ne lisait que le texte
    plat, donc fabriquait *toujours* une ligne par région — non par choix, mais
    parce que le type ne permettait rien d'autre. Un ALTO de trois blocs sortait
    avec trois lignes pour une page qui en compte vingt : structurellement faux,
    illisible par un outil de relecture, et invisible à toute métrique de texte
    (le contenu, lui, était juste). C'est ce que NDNP évite en océrisant chaque
    région **en ALTO** plutôt qu'en chaîne.
    """
    layout = outputs.get(ArtifactType.LAYOUT)
    if layout is not None and layout.uri is not None:
        return _greffer(layout, region)
    return (Line(id=f"{region.id}:l1", text=_read_text(outputs)),)


def _greffer(layout_artifact: Artifact, region: Region) -> tuple[Line, ...]:
    """Lignes d'un sous-layout de bloc → lignes de la région, **en repères page**.

    Deux traductions, et les oublier rendrait l'ALTO faux de deux façons :

    * **les coordonnées** sont relatives à la découpe, pas à la page. Sans le
      décalage, toutes les lignes de tous les blocs se superposeraient en haut à
      gauche ;
    * **les identifiants** viennent du moteur (``line_0``, ``line_1``…) et sont
      donc les mêmes d'un bloc à l'autre. Sans préfixe, deux lignes de blocs
      différents porteraient la même identité — et l'identité de ligne est
      précisément ce que la chaîne structurée existe pour préserver.
    """
    try:
        sous = CanonicalLayout.model_validate_json(
            Path(layout_artifact.uri or "").read_bytes()
        )
    except (OSError, ValueError) as exc:
        raise AdapterStepError(
            f"fanout : sous-layout illisible pour la région {region.id!r} : {exc}"
        ) from exc
    origine = region.geometry.bbox if region.geometry else None
    dx = origine.x if origine else 0
    dy = origine.y if origine else 0
    out: list[Line] = []
    for page in sous.pages:
        for bloc in page.leaf_regions():
            for ligne in bloc.lines:
                out.append(_decalee(ligne, region.id, len(out), dx, dy))
    if not out:
        # Le moteur a rendu une mise en page vide : une région sans ligne est un
        # fait (bloc illisible), pas une erreur. La rendre vide le dit ; inventer
        # une ligne vide ferait croire à une lecture.
        return ()
    return tuple(out)


def _decalee(ligne: Line, region_id: str, rang: int, dx: int, dy: int) -> Line:
    geometrie = ligne.geometry
    if geometrie is not None and geometrie.bbox is not None:
        boite = geometrie.bbox
        decalee = boite.model_copy(update={"x": boite.x + dx, "y": boite.y + dy})
        geometrie = geometrie.model_copy(update={"bbox": decalee})
    identifiant = f"{region_id}:{ligne.id or f'l{rang + 1}'}"
    return ligne.model_copy(update={"id": identifiant, "geometry": geometrie})


def _read_text(outputs: Mapping[ArtifactType, Artifact]) -> str:
    artifact = outputs.get(ArtifactType.RAW_TEXT)
    if artifact is None or artifact.uri is None:
        raise AdapterStepError("fanout : reconnaissance sans RAW_TEXT exploitable.")
    try:
        return Path(artifact.uri).read_text(encoding="utf-8")
    except OSError as exc:
        raise AdapterStepError(f"fanout : texte de région illisible : {exc}") from exc


def execute_region_fanout(
    *,
    layout_artifact: Artifact,
    page_image: Artifact,
    recognizer: Module,
    context: RunContext,
    control: RunControl,
    params: Mapping[str, ParamValue] | None = None,
    cropper: RegionCropper | None = None,
) -> StepOutput:
    """Étage *reconnaissance par région* prêt pour l'exécuteur déclaratif.

    Charge le ``LAYOUT`` (régions seules) depuis son artefact, remplit par
    fan-out, **persiste** le ``LAYOUT`` rempli (JSON) dans le workspace et
    renvoie le ``StepOutput`` attendu par ``PipelineExecutor`` (qui estampille
    ensuite la provenance) — ``usage`` somme les jetons des N reconnaissances.
    """
    if layout_artifact.uri is None:
        raise AdapterStepError("fanout : artefact LAYOUT d'entrée sans URI.")
    try:
        layout = CanonicalLayout.model_validate_json(
            Path(layout_artifact.uri).read_bytes()
        )
    except (OSError, ValueError) as exc:
        raise AdapterStepError(f"fanout : LAYOUT d'entrée illisible : {exc}") from exc
    filled, usage = run_region_fanout(
        layout=layout,
        page_image=page_image,
        recognizer=recognizer,
        context=context,
        control=control,
        params=params,
        cropper=cropper,
    )
    payload = filled.model_dump_json().encode("utf-8")
    out_dir = (
        Path(context.workspace_uri)
        if context.workspace_uri
        else Path(layout_artifact.uri).parent
    )
    out_path = out_dir / f"{context.document_id.replace('/', '_')}.filled.layout.json"
    out_path.write_bytes(payload)
    artifacts = {
        ArtifactType.LAYOUT: Artifact(
            id=f"{context.document_id}:fanout:layout",
            document_id=context.document_id,
            type=ArtifactType.LAYOUT,
            uri=str(out_path),
            content_hash=compute_content_hash(payload),
        )
    }
    return StepOutput(artifacts=artifacts, usage=usage)


__all__ = [
    "REGION_TYPE_PARAM",
    "RegionCropper",
    "execute_region_fanout",
    "run_region_fanout",
]
