"""``AltoLayoutSource`` — ``IMAGE → LAYOUT`` depuis un ALTO déjà là (couche 5).

Le banc sait produire une mise en page (segmenteurs) et sait en consommer une
(``to_text``, ``assembler``, métriques de structure). Il ne savait pas **en
lire une qui existe déjà** : un corpus patrimonial arrive presque toujours
accompagné de son ALTO, et rien ne permettait de le faire entrer autrement
qu'aplati en texte.

Convention de ``PrecomputedLayoutSource`` reprise telle quelle — l'ALTO est
cherché **à côté de l'image**, ``<stem>.xml`` (puis ``<stem>.alto.xml``) près
de ``<stem>.png``. C'est la façon dont les corpus de ce dépôt sont rangés, et ça
évite d'ajouter un type d'entrée initial au planificateur.

**L'ALTO qu'un pipeline Cinoc a écrit** porte un autre nom, celui que fabrique
:func:`alto_file_name` — ``<document>.<pipeline>.alto.xml``, le même pour
``cinoc run --alto-dir``, ``cinoc hybrid`` et l'export web (D-307). Le réglage
``pipeline`` le fait lire, et **seulement** lui : un ``<stem>.xml`` voisin n'est
pas un repli, ce serait lire un autre ALTO que celui qu'on a nommé.

Ce que la lecture conserve, et qui n'a de valeur que conservé : l'identifiant
de ligne (une identité, pas un rang), la géométrie, la confiance du moteur
d'origine, et la césure (``SUBS_TYPE``/``SUBS_CONTENT`` + la marque portée par
``<HYP>``). Un post-correcteur qui recolle un mot coupé a besoin des quatre.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from cinoc.adapters._params import instance_label_param, instance_name
from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import AdapterStepError, CinocError
from cinoc.domain.layout import CanonicalLayout, Line, Region
from cinoc.formats.alto.layout_map import alto_to_layout
from cinoc.formats.alto.parser import parse_alto
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"

#: Extensions tentées à côté de l'image, dans l'ordre.
_SUFFIXES = (".xml", ".alto.xml")

#: Hors de ces caractères, un nom de pipeline n'a rien à faire dans un nom de
#: fichier (``ocr_simple · tesseract``, ``… → ollama (qwen2.5vl:3b)``).
_HORS_PIPELINE = re.compile(r"[^A-Za-z0-9_-]+")
#: Un identifiant de document garde ses points (``page.v2``) : il nomme une
#: image, pas une extension. ``/`` (sous-dossier) devient ``_``.
_HORS_DOCUMENT = re.compile(r"[^A-Za-z0-9_.-]+")


def file_component(name: str) -> str:
    """Un nom de pipeline réduit à ``[A-Za-z0-9_-]`` — idempotent.

    Chaque suite de caractères hors de cet ensemble devient un ``_`` :
    ``segmentation_puis_lecture · tesseract_layout → tesseract + alto`` →
    ``segmentation_puis_lecture_tesseract_layout_tesseract_alto``.
    """
    return _HORS_PIPELINE.sub("_", name).strip("_")


def alto_file_name(document_id: str, pipeline: str) -> str:
    """Le nom de l'ALTO d'un document produit par un pipeline Cinoc.

    ``<document>.<pipeline>.alto.xml`` — **une** fonction, que l'écrivain de la
    CLI, celui du web et le lecteur (``alto_source``, réglage ``pipeline``)
    appellent : le nom écrit est le nom lu, par construction.
    """
    document = _HORS_DOCUMENT.sub("_", document_id).strip("_")
    return f"{document}.{file_component(pipeline)}.alto.xml"


class AltoLayoutSource:
    """Lit l'ALTO voisin de l'image et le projette en ``CanonicalLayout``.

    ``ocr_sidecar`` remplace le **texte** des lignes par une lecture d'OCR
    réelle, en gardant de l'ALTO tout le reste — identité, géométrie, césure.
    Sans lui, un corpus à vérité terrain fait entrer sa propre référence dans
    le banc : le correcteur n'a rien à corriger et le CER vaut zéro **par
    construction**. Un zéro tautologique ressemble à un excellent résultat, ce
    qui en fait le plus trompeur de tous.

    Format attendu (celui de
    ``campaigns/2026-07-25-bnl-mistral/ocr_spa_sidecar.json``) :
    ``{"ocr": {fichier: {line_id: texte}}}``. Une ligne absente du sidecar
    **garde son texte d'ALTO** et est comptée ; une ligne présente mais
    **vide** est une lecture d'OCR à part entière — le moteur n'a rien
    reconnu — et remplace donc le texte. Confondre les deux crédite le
    moteur d'une ligne qu'il n'a pas lue.
    """

    #: Réglages acceptés (``pipeline.params``) : tout autre est refusé, nommé.
    PARAMS: ClassVar[tuple[Param, ...]] = (
        Param("ocr_sidecar", "str", "Sidecar d'OCR du corpus (suffixe)",
              "Corpus OCR sidecar (suffix)", default=""),
        Param(
            "pipeline",
            "str",
            "Pipeline Cinoc dont lire l'ALTO (<document>.<pipeline>.alto.xml ;"
            " sans lui : <nom>.xml ou <nom>.alto.xml près de l'image)",
            "Cinoc pipeline whose ALTO to read (<document>.<pipeline>.alto.xml;"
            " without it: <name>.xml or <name>.alto.xml next to the image)",
            default="",
        ),
        instance_label_param(),
    )

    def __init__(
        self, *, ocr_sidecar: str = "", pipeline: str = "", label: str | None = None
    ) -> None:
        if pipeline and file_component(pipeline) != pipeline:
            # Refusé plutôt qu'assaini : ``../x`` n'est pas un nom de pipeline,
            # et un nom assaini en silence lirait un autre fichier que celui
            # qu'on croit avoir nommé.
            raise AdapterStepError(
                f"alto_source : réglage 'pipeline' {pipeline!r} — le nom tel "
                f"qu'il figure dans le fichier ({file_component(pipeline)!r} ?), "
                "lettres, chiffres, '_' et '-' seulement."
            )
        self._sidecar = ocr_sidecar
        self._pipeline = pipeline
        self._label = label

    @property
    def name(self) -> str:
        return instance_name("alto_source", self._label)

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    def unit_inputs(self, document: DocumentRef) -> tuple[Path, ...]:
        """Les fichiers lus pour ``document`` (hook de reprise, facultatif).

        **Chaque** emplacement tenté, pas seulement celui qui existe : qu'un
        ``.xml`` apparaisse près d'un ``.alto.xml`` change la lecture. Plus le
        sidecar OCR, dont le chemin est un réglage mais le contenu une entrée.
        """
        if document.image_uri is None:
            return ()
        sidecar = (Path(self._sidecar),) if self._sidecar else ()
        return (*self._candidates(Path(document.image_uri), document.id), *sidecar)

    def _candidates(self, image_path: Path, document_id: str) -> tuple[Path, ...]:
        """Les ALTO cherchés pour un document, dans l'ordre où ils sont tentés."""
        if self._pipeline:
            return (image_path.with_name(alto_file_name(document_id, self._pipeline)),)
        return alto_candidates(image_path)

    def _locate(self, image_path: Path, document_id: str) -> Path:
        candidats = self._candidates(image_path, document_id)
        for candidate in candidats:
            if candidate.is_file():
                return candidate
        attendus = " ou ".join(repr(c.name) for c in candidats)
        raise AdapterStepError(
            f"{self.name} : aucun ALTO près de {image_path.name!r} "
            f"({attendus} attendu dans {image_path.parent})."
        )

    def _read_sidecar(self, alto_name: str) -> dict[str, str]:
        chemin = Path(self._sidecar)
        try:
            data = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AdapterStepError(
                f"{self.name} : sidecar OCR illisible ({chemin}) — {exc}"
            ) from exc
        par_fichier = data.get("ocr") if isinstance(data, dict) else None
        if not isinstance(par_fichier, dict):
            raise AdapterStepError(
                f"{self.name} : {chemin.name!r} n'a pas de section 'ocr'."
            )
        lectures = par_fichier.get(alto_name)
        if not isinstance(lectures, dict):
            raise AdapterStepError(
                f"{self.name} : le sidecar ne connaît pas {alto_name!r}."
            )
        return {str(k): str(v) for k, v in lectures.items()}

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
        alto_path = self._locate(Path(image.uri), context.document_id)
        try:
            layout = alto_to_layout(parse_alto(alto_path.read_bytes()))
        except CinocError as exc:
            raise AdapterStepError(
                f"{self.name} : {alto_path.name!r} illisible — {exc}"
            ) from exc
        if self._sidecar:
            layout, remplacees, total = _apply_ocr(
                layout, self._read_sidecar(alto_path.name)
            )
            if remplacees == 0 and total:
                # Un sidecar qui ne touche AUCUNE ligne est presque toujours un
                # mauvais appariement de clés, pas un OCR parfait. Le dire ici
                # évite de publier un CER nul en croyant mesurer une correction.
                raise AdapterStepError(
                    f"{self.name} : le sidecar ne couvre aucune des {total} "
                    f"lignes de {alto_path.name!r} — clés de fichier ou de "
                    "ligne incompatibles."
                )

        # Une ligne sans ``id`` n'a pas d'identité stable, et un post-correcteur
        # qui reçoit un tel layout ne peut pas rendre ses décisions ligne à
        # ligne. On le dit ici plutôt que de laisser l'étape suivante échouer
        # sur une cause qui n'est pas la sienne. Toute la profondeur : les
        # lignes d'un article de presse sont sous un ``ComposedBlock``.
        sans_id = sum(
            1
            for page in layout.pages
            for region in _all_regions(page.regions)
            for line in region.lines
            if not line.id
        )
        if sans_id:
            raise AdapterStepError(
                f"{self.name} : {alto_path.name!r} porte {sans_id} ligne(s) "
                "sans attribut ID. Sans identifiant, une ligne n'a pas "
                "d'identité stable d'un artefact à l'autre."
            )

        payload = layout.model_dump_json().encode("utf-8")
        # Sans espace de travail, on écrit près de la source — même repli que
        # ``alto_assembler``.
        out = (
            workspace_artifact_path(
                context.workspace_uri, context.document_id, self.name, "layout.json"
            )
            if context.workspace_uri
            else alto_path.with_name(f"{alto_path.stem}.{self.name}.layout.json")
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(payload)
        return StepOutput(
            artifacts={
                ArtifactType.LAYOUT: Artifact(
                    id=f"{context.document_id}:{self.name}:layout",
                    document_id=context.document_id,
                    type=ArtifactType.LAYOUT,
                    uri=str(out),
                    content_hash=compute_content_hash(payload),
                )
            }
        )


def alto_candidates(image_path: Path) -> tuple[Path, ...]:
    """Les ALTO **d'un autre outil** cherchés près de l'image, dans l'ordre
    (``<stem>.xml`` puis ``<stem>.alto.xml``) — la règle que ``cinoc correct``
    reprend pour apparier un dossier."""
    return tuple(image_path.with_name(image_path.stem + s) for s in _SUFFIXES)


def _all_regions(regions: tuple[Region, ...]) -> Iterator[Region]:
    for region in regions:
        yield region
        yield from _all_regions(region.regions)


def _apply_ocr(
    layout: CanonicalLayout, lectures: dict[str, str]
) -> tuple[CanonicalLayout, int, int]:
    """Remplace le texte des lignes connues du sidecar. Renvoie ``(layout,
    remplacées, total)`` — les compteurs servent à refuser un appariement vide.

    Les **mots sont abandonnés** sur une ligne remplacée : leur géométrie
    décrivait les caractères de la vérité terrain, pas ceux que l'OCR a lus.
    """
    remplacees = 0
    total = 0

    def region(reg: Region) -> Region:
        nonlocal remplacees, total
        lignes = []
        for line in reg.lines:
            total += 1
            if line.id is not None and line.id in lectures:
                remplacees += 1
                lignes.append(
                    Line(
                        id=line.id,
                        text=lectures[line.id],
                        geometry=line.geometry,
                        baseline=line.baseline,
                        words=(),
                        confidence=line.confidence,
                    )
                )
            else:
                lignes.append(line)
        return reg.model_copy(
            update={
                "lines": tuple(lignes),
                "regions": tuple(region(r) for r in reg.regions),
            }
        )

    pages = tuple(
        page.model_copy(update={"regions": tuple(region(r) for r in page.regions)})
        for page in layout.pages
    )
    return layout.model_copy(update={"pages": pages}), remplacees, total


__all__ = ["AltoLayoutSource", "alto_candidates", "alto_file_name", "file_component"]
